"""Crossover tests: prove nothing leaks between models, planes, or SCWs.

Every test here is a correctness test, not a performance one. A cache that
returns the right value faster is an optimization; a cache that returns another
model's or another SCW's value is a defect that looks like a working feature.
"""
import pytest

from maxey0_ss.cache import (
    CacheConfig,
    MaxeyCache,
    ModelIdentity,
    Namespace,
    NotCacheable,
    SemanticPlane,
    assert_cacheable,
    digest,
)

PROMPT = "Describe the SCW address space."
GPT = ModelIdentity("claude-opus-5", "2026-05-01", {"temperature": 0.0})


class Clock:
    """Controllable time, so TTL behavior is asserted rather than slept through."""

    def __init__(self, start: int = 1_000_000) -> None:
        self.now = start

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


def cache(**kw) -> MaxeyCache:
    return MaxeyCache(CacheConfig(**kw))


# --- per-model identity -----------------------------------------------------


def test_a_different_model_never_reads_another_models_answer():
    c = cache()
    ns = Namespace(SemanticPlane.MODEL)
    view = c.view(ns)
    view.put_model(GPT, PROMPT, "answer-from-opus")

    other = ModelIdentity("claude-sonnet-5", "2026-05-01", {"temperature": 0.0})
    assert c.view(ns).get_model(other, PROMPT) is None
    assert c.view(ns).get_model(GPT, PROMPT) == "answer-from-opus"


def test_a_version_bump_invalidates_by_identity():
    c = cache()
    view = c.view(Namespace(SemanticPlane.MODEL))
    view.put_model(GPT, PROMPT, "old-version-answer")
    bumped = ModelIdentity(GPT.model_id, "2026-09-01", GPT.params)
    assert view.get_model(bumped, PROMPT) is None


def test_decoding_parameters_are_part_of_model_identity():
    c = cache()
    view = c.view(Namespace(SemanticPlane.MODEL))
    view.put_model(GPT, PROMPT, "deterministic")
    hot = ModelIdentity(GPT.model_id, GPT.version, {"temperature": 1.0})
    assert view.get_model(hot, PROMPT) is None


def test_a_different_tool_schema_is_a_different_request():
    c = cache()
    view = c.view(Namespace(SemanticPlane.MODEL))
    view.put_model(GPT, PROMPT, "answered-with-tools", tool_schema=[{"name": "a"}])
    assert view.get_model(GPT, PROMPT, tool_schema=[{"name": "a", "extra": 1}]) is None
    assert view.get_model(GPT, PROMPT, tool_schema=[{"name": "a"}]) == "answered-with-tools"


def test_model_identity_refuses_to_exist_without_a_version():
    with pytest.raises(ValueError, match="version is required"):
        ModelIdentity("claude-opus-5", "")
    with pytest.raises(ValueError):
        ModelIdentity("", "2026-05-01")


# --- semantic plane isolation ----------------------------------------------


def test_planes_do_not_contaminate_each_other():
    c = cache()
    c.view(Namespace(SemanticPlane.CONTEXT, "SCW0")).put("window", value="context-value")
    assert c.view(Namespace(SemanticPlane.EXECUTION, "SCW0")).get("window") is None
    assert c.view(Namespace(SemanticPlane.CONTEXT, "SCW0")).get("window") == "context-value"


def test_every_plane_pair_is_disjoint_for_the_same_identity(subtests):
    c = cache()
    planes = [p for p in SemanticPlane if p is not SemanticPlane.PROTOCOL]
    for plane in planes:
        c.view(Namespace(plane, "SCW0")).put("same-identity", value=plane.value)
    for plane in planes:
        with subtests.test(plane=plane.value):
            assert c.view(Namespace(plane, "SCW0")).get("same-identity") == plane.value


def test_the_protocol_plane_is_server_scoped_by_definition():
    with pytest.raises(ValueError, match="server-scoped"):
        Namespace(SemanticPlane.PROTOCOL, "SCW0")


# --- SCW isolation ----------------------------------------------------------


def test_one_scw_never_reads_another_scws_entry():
    c = cache()
    c.view(Namespace(SemanticPlane.CONTEXT, "SCW0")).put("observation", value="scw0-only")
    assert c.view(Namespace(SemanticPlane.CONTEXT, "SCW1")).get("observation") is None


def test_closing_an_scw_drops_its_entries_across_every_plane():
    c = cache()
    for plane in (SemanticPlane.CONTEXT, SemanticPlane.EXECUTION, SemanticPlane.OBSERVATION):
        c.view(Namespace(plane, "SCW0")).put("k", value="doomed")
        c.view(Namespace(plane, "SCW1")).put("k", value="survivor")
    c.view(Namespace(SemanticPlane.PROTOCOL)).put("tools:list", value="server-wide")

    dropped = c.invalidate_scw("SCW0")

    assert dropped == 3
    for plane in (SemanticPlane.CONTEXT, SemanticPlane.EXECUTION, SemanticPlane.OBSERVATION):
        assert c.view(Namespace(plane, "SCW0")).get("k") is None
        assert c.view(Namespace(plane, "SCW1")).get("k") == "survivor"
    assert c.view(Namespace(SemanticPlane.PROTOCOL)).get("tools:list") == "server-wide"


def test_a_reused_scw_id_does_not_inherit_the_previous_one():
    c = cache()
    ns = Namespace(SemanticPlane.CONTEXT, "SCW0")
    c.view(ns).put("state", value="first-life")
    c.invalidate_scw("SCW0")
    assert c.view(ns).get("state") is None


# --- what must never be cached ---------------------------------------------


def test_stateful_tools_are_refused_by_name(subtests):
    for name in ("maxey0-ss.scw.create", "maxey0-ss.scw.close", "maxey0-ss.scw.describe",
                 "maxey0-ss.scw.observe_host_window", "maxey0-ss.auth.manifest",
                 "maxey0-ss.gate.inspect", "maxey0-ss.scw.drift",
                 "maxey0-ss.deployment", "maxey0-ss.provider.status",
                 "maxey0-ss.provider.complete"):
        with subtests.test(tool=name):
            with pytest.raises(NotCacheable):
                assert_cacheable(name)


def test_a_gate_decision_is_never_cached():
    """`gate.inspect` moved onto the never-cache list in 0.2.0.

    It was listed as deterministic, and it is — while the provider is
    `DisabledSemanticGate`, which is a pure function of the address. But
    `gate.inspect` now routes through whichever `SemanticGateProvider`
    configuration selected, and a provider may consult an external policy
    service. A cached allow then outlives the policy that produced it, which is
    the one direction a gate must never fail. Caching a *decision* is different
    from caching a *fact*, and the distinction does not depend on which
    provider happens to be installed today.
    """
    with pytest.raises(NotCacheable):
        assert_cacheable("maxey0-ss.gate.inspect")


def test_deterministic_tools_are_allowed():
    for name in ("maxey0-ss.health", "maxey0-ss.distribution",
                 "maxey0-ss.app.artifact"):
        assert_cacheable(name)  # must not raise


def test_every_cacheable_tool_is_actually_wired(subtests):
    """The two lists must agree, and both must reach the dispatch path.

    `CACHEABLE_PLANES` selects what gets a cache wrapper; `NEVER_CACHE` names
    what must not. Before 0.2.0 neither had a call site: `assert_cacheable` was
    exported and invoked nowhere outside this file, and no `CacheView` was ever
    created, so `MaxeyCache` could not hold an entry. A list of correctness
    rules enforced at zero call sites is a label.
    """
    from maxey0_ss.mcp_surface import CACHEABLE_PLANES, build_surface

    surface_tools = {t.name for t in build_surface().tools}
    for name in CACHEABLE_PLANES:
        with subtests.test(tool=name):
            assert name in surface_tools, f"{name} is cached but is not a tool"
            assert_cacheable(name)  # cannot be on both lists


# --- freshness, bypass, limits ---------------------------------------------


def test_an_entry_expires_at_its_ttl():
    clock = Clock()
    c = MaxeyCache(CacheConfig(), clock=clock)
    ns = Namespace(SemanticPlane.CONTEXT, "SCW0")
    c.view(ns).put("k", value="v", ttl_ms=1_000)
    assert c.view(ns).get("k") == "v"
    clock.advance(1_001)
    assert c.view(ns).get("k") is None
    assert c.metrics.expirations == 1


def test_a_zero_ttl_means_do_not_cache():
    c = cache()
    ns = Namespace(SemanticPlane.CONTEXT, "SCW0")
    c.view(ns).put("k", value="v", ttl_ms=0)
    assert c.view(ns).get("k") is None
    assert len(c) == 0


def test_bypass_disables_reads_and_writes_and_is_counted():
    c = cache(bypass=True)
    ns = Namespace(SemanticPlane.MODEL)
    c.view(ns).put_model(GPT, PROMPT, "never-stored")
    assert c.view(ns).get_model(GPT, PROMPT) is None
    assert len(c) == 0
    assert c.metrics.bypasses == 2


def test_disabling_the_cache_is_distinct_from_bypassing_it():
    c = cache(enabled=False)
    assert c.config.active is False


def test_the_cache_evicts_rather_than_growing_without_bound():
    clock = Clock()
    c = MaxeyCache(CacheConfig(max_entries=3), clock=clock)
    ns = Namespace(SemanticPlane.CONTEXT, "SCW0")
    for i in range(6):
        clock.advance(10)
        c.view(ns).put(f"k{i}", value=i)
    assert len(c) <= 3
    assert c.metrics.evictions > 0


# --- keys and observability -------------------------------------------------


def test_key_order_does_not_change_identity():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_adjacent_parts_cannot_be_confused():
    """"ab"+"c" must not digest the same as "a"+"bc"."""
    assert digest("ab", "c") != digest("a", "bc")


def test_metrics_track_hits_and_misses_per_plane():
    c = cache()
    ns = Namespace(SemanticPlane.CONTEXT, "SCW0")
    c.view(ns).put("k", value="v")
    c.view(ns).get("k")
    c.view(ns).get("absent")
    assert c.metrics.hits == 1
    assert c.metrics.misses == 1
    assert c.metrics.hit_rate == 0.5
    assert c.metrics.by_plane["context"]["hits"] == 1


def test_status_reports_shape_without_leaking_contents():
    c = cache()
    c.view(Namespace(SemanticPlane.MODEL)).put_model(GPT, "secret prompt", "secret answer")
    status = c.status()
    blob = repr(status)
    assert "secret prompt" not in blob
    assert "secret answer" not in blob
    assert status["entries"] == 1
    assert status["entries_by_plane"]["model"] == 1
    assert "maxey0-ss.scw.create" in status["never_cached"]


def test_configuration_is_explicit_and_inspectable():
    cfg = CacheConfig().as_dict()
    assert cfg["ttl_ms"]["protocol"] == 300_000
    assert cfg["ttl_ms"]["context"] == 30_000
    assert cfg["active"] is True
