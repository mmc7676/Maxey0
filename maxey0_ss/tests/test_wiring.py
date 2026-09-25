"""The containment machinery has to be attached to the system that runs.

A full-repo audit found the same shape in five places: a mechanism built, tested
and wired into nothing. The constitution tree and the denial breaker existed but
`containment_provider()` constructed neither, so the reach ceiling and the spawn
caps were inert for every SCW the MCP surface and the HTTP API created. Closing
a window flipped a display flag. `.env` was never loaded, so every authorization
variable documented as wired was ignored. These tests hold the wiring in place.
"""
import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.containment.hierarchy import ConstitutionViolation
from maxey0_ss.execution.chartered import CharteredFormation
from maxey0_ss.models import SCWSpec
from maxey0_ss.semantic.runtime import SemanticRuntime, UnanchoredWindow
from maxey0_ss.system import SuperSpaceSystem


def spec(scw_id: str, parent: str | None = None) -> SCWSpec:
    return SCWSpec(scw_id, parent, "Concept", [])


# --- the hierarchy is attached to the running system ------------------------


def test_the_running_system_has_a_constitution_tree_and_a_breaker():
    context = SuperSpaceSystem().context
    assert context.tree is not None
    assert context.breaker is not None


def test_the_root_is_chartered_and_the_grant_is_attested():
    context = SuperSpaceSystem().context
    assert context.tree.is_chartered(context.ROOT_SCW)
    reasons = [e.decision.reason for e in context.isolation.log.entries()]
    assert any("root chartered" in r for r in reasons)


def test_a_spec_is_chartered_under_its_declared_parent():
    """parent_id was validated and then read by nothing."""
    context = SuperSpaceSystem().context
    context.create_spec(spec("SCW1"))
    context.create_spec(spec("SCW2", "SCW1"))
    assert context.tree.parent_of("SCW2") == "SCW1"
    assert context.tree.parent_of("SCW1") == context.ROOT_SCW


def test_a_spec_naming_an_unchartered_parent_is_refused():
    context = SuperSpaceSystem().context
    with pytest.raises(ConstitutionViolation, match="not chartered"):
        context.create_spec(spec("SCW5", "SCW9"))


def test_a_bounded_root_bounds_every_spec_beneath_it():
    from maxey0_ss.context.service import ContextService

    context = ContextService(root_reach={"SCW1"})
    context.create_spec(spec("SCW1"))
    assert not context.tree.permits("SCW1", "SCW9")


# --- closing a window revokes it --------------------------------------------


def test_closing_a_window_revokes_its_reach():
    """close() flipped a flag no decision path read."""
    context = SuperSpaceSystem().context
    context.create_spec(spec("SCW1"))
    instance = context.instantiate("SCW1", "owner", "rt")
    assert context.isolation.can_read(instance.id, instance.id)
    context.close(instance.id)
    assert not context.isolation.can_read(instance.id, instance.id)
    assert not context.isolation.can_write(instance.id, instance.id)


def test_a_closed_window_cannot_admit_context():
    context = SuperSpaceSystem().context
    context.create_spec(spec("SCW1"))
    instance = context.instantiate("SCW1", "owner", "rt")
    context.close(instance.id)
    with pytest.raises(PermissionError, match="closed"):
        context.admit(instance.id, instance.id, "payload")


def test_revocation_is_attested():
    context = SuperSpaceSystem().context
    context.create_spec(spec("SCW1"))
    instance = context.instantiate("SCW1", "owner", "rt")
    context.close(instance.id)
    assert any("revoked" in e.decision.reason for e in context.isolation.log.entries())


def test_an_unregistered_window_cannot_read_itself():
    """The same-window shortcut ran before any lookup."""
    context = SuperSpaceSystem().context
    assert not context.isolation.can_read("SCW9@rt", "SCW9@rt")


# --- drift no longer fails open ---------------------------------------------


def test_inspecting_an_unanchored_window_is_refused():
    """setdefault made the first inspection always report distance 0.0."""
    with pytest.raises(UnanchoredWindow, match="no anchored baseline"):
        SemanticRuntime().inspect("SCW7", [0.0, 1.0, 0.0], 0.15)


def test_an_anchored_window_measures_real_drift():
    runtime = SemanticRuntime()
    runtime.anchor("SCW8", [1.0, 0.0, 0.0])
    record = runtime.inspect("SCW8", [0.0, 1.0, 0.0], 0.15)
    assert record.drifted and record.distance > 0.15


def test_inspecting_does_not_silently_re_anchor():
    runtime = SemanticRuntime()
    runtime.anchor("SCW8", [1.0, 0.0, 0.0])
    runtime.inspect("SCW8", [0.0, 1.0, 0.0], 0.15)
    assert runtime.baselines["SCW8"] == [1.0, 0.0, 0.0]


# --- the REST surface enforces the capability model -------------------------


def public_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    return TestClient(create_app())


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/v1/context/scws", {"id": "SCW9", "concept": "x"}),
        ("post", "/v1/scw/default-deploy", {"task": "t"}),
        ("post", "/v1/execution/agents", {"id": "a", "role": "r", "scw_id": "SCW1"}),
        ("get", "/v1/observability/trace", None),
        ("get", "/v1/context/graph", None),
    ],
)
def test_the_rest_surface_refuses_an_anonymous_caller(monkeypatch, method, path, body):
    """/v1 is mounted beside /mcp and enforced none of the tiers."""
    client = public_client(monkeypatch)
    response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert response.status_code == 403


def test_scw_lifecycle_routes_are_gated(monkeypatch):
    client = public_client(monkeypatch)
    assert client.post("/v1/context/scws/SCW1/close").status_code == 403
    assert client.post("/v1/context/scws/SCW1/anchor", json={"vector": [1.0]}).status_code == 403


def test_rest_close_needs_the_same_capability_as_mcp_close(monkeypatch):
    """REST close required gate.write (admin) while MCP scw.close required
    scw.admit (builder): the same operation behind two different doors."""
    from maxey0_ss.auth.policy import token_hash_entry

    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKEN_HASHES", ",".join([
        token_hash_entry("builder-caller-token", "builder", "b"),
        token_hash_entry("operator-caller-token", "operator", "o"),
    ]))
    client = TestClient(create_app())
    as_operator = {"Authorization": "Bearer operator-caller-token"}
    as_builder = {"Authorization": "Bearer builder-caller-token"}
    assert client.post("/v1/context/scws/SCW1/close", headers=as_operator).status_code == 403
    assert client.post("/v1/context/scws/SCW1/close", headers=as_builder).status_code != 403


def test_health_stays_public(monkeypatch):
    assert public_client(monkeypatch).get("/health").status_code == 200


# --- the chartered formation attests its own root ---------------------------


def test_a_chartered_formation_records_its_root_grant():
    """The chain verified as intact while omitting the bound that made it valid."""
    formation = CharteredFormation("SCW0", reach={"SCW1"})
    reasons = [c["reason"] for c in formation.crossings()]
    assert any("root chartered" in r for r in reasons)


def test_the_root_reach_is_visible_in_the_evidence():
    """An unbounded root must not look like a bounded one in the record."""
    bounded = CharteredFormation("SCW0", reach={"SCW1"})
    unbounded = CharteredFormation("SCW0")
    bounded_reason = [c["reason"] for c in bounded.crossings() if "root chartered" in c["reason"]][0]
    unbounded_reason = [c["reason"] for c in unbounded.crossings() if "root chartered" in c["reason"]][0]
    assert bounded_reason != unbounded_reason
    assert "SCW1" in bounded_reason and "unbounded" in unbounded_reason


# --- the console entrypoints resolve ----------------------------------------


def test_the_declared_console_entrypoints_are_callable():
    """Both crashed: one had no main, the other pointed at a FastAPI instance."""
    import tomllib

    from maxey0_ss import __main__ as entry

    assert callable(entry.main)
    config = tomllib.loads(
        (__import__("pathlib").Path(__file__).parents[2] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    for target in config["project"]["scripts"].values():
        module_name, _, attribute = target.partition(":")
        module = __import__(module_name, fromlist=[attribute])
        assert callable(getattr(module, attribute)), f"{target} is not callable"


# --- the correctness and security mediums -----------------------------------


def test_a2a_refuses_when_no_secret_is_configured_on_a_public_deployment(monkeypatch):
    """The one authenticated REST route was unauthenticated by default."""
    from maxey0_ss.adapters.a2a import a2a_credential_valid

    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    assert a2a_credential_valid(None, "") is False


def test_a2a_stays_permissive_locally_with_no_secret(monkeypatch):
    from maxey0_ss.adapters.a2a import a2a_credential_valid

    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    assert a2a_credential_valid(None, "") is True


def test_a_configured_secret_is_still_required(monkeypatch):
    from maxey0_ss.adapters.a2a import a2a_credential_valid

    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    assert a2a_credential_valid("Bearer wrong", "right") is False
    assert a2a_credential_valid("Bearer right", "right") is True


def test_the_default_deployer_produces_an_instantiable_spec():
    """It named a skill registered in no context graph, so every SCW it made
    raised KeyError at instantiation."""
    from maxey0_ss.scw_deployer import deploy_default_scw

    context = SuperSpaceSystem().context
    context.create_spec(deploy_default_scw("a task", scw_id="SCW4"))
    instance = context.instantiate("SCW4", "owner", "rt")
    assert instance.spec_id == "SCW4"


def test_disjointness_sees_a_shared_third_window():
    """Masking the intersection to {a, b} hid everything they both held."""
    from maxey0_ss.containment import Operation, StructuralContainment
    from maxey0_ss.models import SCWInstance, SemanticAddress

    def make(scw_id, readable):
        return SCWInstance(scw_id, scw_id, "o", "rt",
                           SemanticAddress("m", "c", "f", scw_id),
                           set(readable), {scw_id})

    provider = StructuralContainment()
    provider.register(make("SCW1", {"SCW1", "SCW3"}))
    provider.register(make("SCW2", {"SCW2", "SCW3"}))
    decision = provider.decide(Operation.DISJOINTNESS, "SCW1", "SCW2")
    assert not decision.allowed
    assert "SCW3" in decision.reason


def test_genuinely_disjoint_windows_still_pass():
    from maxey0_ss.containment import Operation, StructuralContainment
    from maxey0_ss.models import SCWInstance, SemanticAddress

    def make(scw_id, readable):
        return SCWInstance(scw_id, scw_id, "o", "rt",
                           SemanticAddress("m", "c", "f", scw_id),
                           set(readable), {scw_id})

    provider = StructuralContainment()
    provider.register(make("SCW1", {"SCW1"}))
    provider.register(make("SCW2", {"SCW2"}))
    assert provider.decide(Operation.DISJOINTNESS, "SCW1", "SCW2").allowed


def test_the_plugin_description_counts_come_from_the_registry():
    """The text said nine slash commands while the catalog declared ten."""
    import sys

    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    for extra in (root / "scripts", root / "server"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    import build_planes
    from planes import catalog

    text = build_planes.describe("maxey0")
    assert "{command_count}" not in text and "{tool_count}" not in text
    assert f"{len(catalog.ALL)} tools" in text


# --- a refused create or instantiate leaves nothing behind ------------------


def test_a_refused_create_does_not_take_the_id():
    """The spec was stored before the parent check, so the id was burned."""
    context = SuperSpaceSystem().context
    with pytest.raises(ConstitutionViolation):
        context.create_spec(spec("SCW7", "SCW123"))
    assert "SCW7" not in context.graph.scw_specs
    context.create_spec(spec("SCW7"))
    assert context.tree.parent_of("SCW7") == context.ROOT_SCW


def test_a_non_string_concept_is_refused_before_anything_is_stored():
    context = SuperSpaceSystem().context
    with pytest.raises(TypeError):
        context.create_spec(SCWSpec("SCW9", None, {"a": 1}, []))
    assert "SCW9" not in context.graph.scw_specs
    assert not context.tree.is_chartered("SCW9")


def test_a_refused_instantiation_leaves_no_ghost_instance():
    context = SuperSpaceSystem().context
    # A spec containment never chartered, placed the way an orphan used to be.
    context.graph.add_scw_spec(spec("SCW5"))
    with pytest.raises(ConstitutionViolation):
        context.instantiate("SCW5", "owner", "rt")
    assert not any(i.startswith("SCW5@") for i in context.instances)
