"""Data model: regions, policies, loops, bridges.

A *region* (an SCW) is an addressable, typed slice of the context window. It
has a policy that says what may happen to it, a position in the rendered
window, and an optional parent, because regions nest.

Nothing here mutates itself — :class:`~scw_runtime.window.ContextWindow` owns
all transitions so that every one of them can be logged first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- vocabularies ------------------------------------------------------------

REGION_TYPES = ("reference", "durable", "episodic", "working", "scratchpad")
MUTABILITY = ("readonly", "durable", "volatile")
EVICTION = ("fifo", "lru", "reject")
CACHE_HINTS = ("auto", "always", "never")
BRIDGE_MODES = ("read", "write", "read_write")
LIFECYCLE = ("open", "sealed", "purged")

# Regions render in this tier order by default. The ordering is not cosmetic:
# prompt caches are prefix caches, so anything that mutates invalidates every
# token after it. Putting read-only and durable tiers first and the volatile
# scratchpad last is the cache-optimal default layout, and the runtime will
# tell you (via advisories) when an explicit `order` breaks it.
TYPE_ORDER = {
    "reference": 10,
    "durable": 20,
    "episodic": 30,
    "working": 40,
    "scratchpad": 50,
}


@dataclass
class Policy:
    """What a region is allowed to do. The wall, expressed as data.

    Attributes
    ----------
    mutability:
        ``readonly`` rejects all writes; ``durable`` accumulates; ``volatile``
        accumulates but is expected to be cleared (see ``reset_each_tick`` and
        ``purge_on_close``).
    eviction:
        What happens when ``token_budget`` would be exceeded: drop oldest
        (``fifo``), drop least-recently-read (``lru``), or refuse the write
        (``reject``).
    token_budget:
        Hard cap on the region's rendered token footprint. ``None`` is
        unbounded (still counted against the window budget).
    purge_on_close:
        Destroy content when the region is closed, rather than sealing it.
    bridgeable:
        Whether another scope may ever be granted access via a bridge. A region
        with ``bridgeable=False`` is unreachable from outside, full stop.
    versioned:
        Retain overwritten/promoted entries as history with provenance.
    reset_each_tick:
        Clear the region at every loop iteration boundary. This is what makes a
        scratchpad a scratchpad rather than an accumulator.
    cache:
        Hint for the cache planner. ``never`` marks a region as always-dirty
        even if its bytes did not change (useful for regions the host rewrites
        out-of-band); ``always`` asserts stability.
    """

    mutability: str = "durable"
    eviction: str = "fifo"
    token_budget: Optional[int] = None
    purge_on_close: bool = False
    bridgeable: bool = True
    versioned: bool = False
    reset_each_tick: bool = False
    cache: str = "auto"

    def __post_init__(self) -> None:
        if self.mutability not in MUTABILITY:
            raise ValueError(f"mutability must be one of {MUTABILITY}")
        if self.eviction not in EVICTION:
            raise ValueError(f"eviction must be one of {EVICTION}")
        if self.cache not in CACHE_HINTS:
            raise ValueError(f"cache must be one of {CACHE_HINTS}")
        if self.token_budget is not None and self.token_budget <= 0:
            raise ValueError("token_budget must be positive or None")

    def to_dict(self) -> dict:
        return {
            "mutability": self.mutability,
            "eviction": self.eviction,
            "token_budget": self.token_budget,
            "purge_on_close": self.purge_on_close,
            "bridgeable": self.bridgeable,
            "versioned": self.versioned,
            "reset_each_tick": self.reset_each_tick,
            "cache": self.cache,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Policy":
        return cls(**(data or {}))


#: Preset policies per region type. ``create_scw(region_type=...)`` starts from
#: one of these; any field can be overridden per region.
PRESETS: dict[str, Policy] = {
    "reference": Policy(
        mutability="readonly", eviction="reject", bridgeable=True,
        versioned=True, cache="always",
    ),
    "durable": Policy(
        mutability="durable", eviction="lru", bridgeable=True, versioned=True,
    ),
    "episodic": Policy(
        mutability="durable", eviction="fifo", bridgeable=True, versioned=True,
        purge_on_close=False,
    ),
    "working": Policy(
        mutability="durable", eviction="fifo", bridgeable=False, versioned=False,
    ),
    "scratchpad": Policy(
        mutability="volatile", eviction="fifo", token_budget=2048,
        purge_on_close=True, bridgeable=False, versioned=False,
        reset_each_tick=True,
    ),
}


def preset_for(region_type: str, overrides: dict | None = None) -> Policy:
    """Build a policy from a region-type preset plus explicit overrides."""
    if region_type not in PRESETS:
        raise ValueError(f"region_type must be one of {REGION_TYPES}")
    base = PRESETS[region_type].to_dict()
    base.update(overrides or {})
    return Policy(**base)


@dataclass
class Entry:
    """One unit of content inside a region."""

    entry_id: str
    data: str
    tokens: int
    key: Optional[str]
    written_by: str
    tick: int
    seq: int
    provenance: Optional[dict] = None
    last_read_seq: int = -1

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "data": self.data,
            "tokens": self.tokens,
            "key": self.key,
            "written_by": self.written_by,
            "tick": self.tick,
            "seq": self.seq,
            "provenance": self.provenance,
        }


@dataclass
class Region:
    """An addressable region of the context window — one SCW."""

    scw_id: str
    label: str
    region_type: str
    policy: Policy
    order: int
    created_seq: int
    parent_id: Optional[str] = None
    children: list[str] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    history: list[Entry] = field(default_factory=list)
    lifecycle: str = "open"
    revision: int = 0
    last_mutation_seq: int = -1
    last_read_seq: int = -1
    evicted_tokens: int = 0

    # -- derived ---------------------------------------------------------
    @property
    def own_tokens(self) -> int:
        """Token cost of this region's own entries, excluding children."""
        return sum(e.tokens for e in self.entries)

    def to_dict(self, include_content: bool = False) -> dict:
        out = {
            "scw_id": self.scw_id,
            "label": self.label,
            "region_type": self.region_type,
            "policy": self.policy.to_dict(),
            "order": self.order,
            "parent_id": self.parent_id,
            "children": list(self.children),
            "lifecycle": self.lifecycle,
            "revision": self.revision,
            "entry_count": len(self.entries),
            "own_tokens": self.own_tokens,
            "last_mutation_seq": self.last_mutation_seq,
            "last_read_seq": self.last_read_seq,
            "evicted_tokens": self.evicted_tokens,
            "created_seq": self.created_seq,
        }
        if include_content:
            out["entries"] = [e.to_dict() for e in self.entries]
        return out


# --- loop specification vocabulary ------------------------------------------
# From Macedo, "Stop Hand-Holding Your Coding Agent: Engineering the Loops that
# Replace Step-by-Step Prompting" (arXiv:2607.00038, cs.SE, 28 Jun 2026). The
# paper defines a loop specification as trigger + goal + verification + stopping
# rule + memory, and closes by asking that harnesses "expose trigger,
# verification level, architecture, terminal states and memory as first-class
# configuration, so that a loop's position in our taxonomy is declared rather
# than buried in a script." These vocabularies are that declaration surface.

TRIGGERS = ("manual", "scheduled", "event")

#: The five-level verification ladder. 1–2 are the autonomous zone (checks that
#: run unattended); 1–3 are the objective zone; 4–5 are assisted flow, where a
#: model or a human stands in for a check. Declaring a level is a claim the
#: runtime will hold you to — see the `verification.*` advisories.
VERIFICATION_LADDER = {
    1: "deterministic — assertion, exit code, golden output",
    2: "rule — linter, schema, policy constraint over the text",
    3: "delayed field truth — tests, deploy, real response; true but slow",
    4: "model as judge — a rubric score; opinion, not field truth",
    5: "human checkpoint — supervision, not automated verification",
}
AUTONOMOUS_ZONE = (1, 2)
OBJECTIVE_ZONE = (1, 2, 3)

#: Named terminal states. The paper's rule is absolute: an error or an
#: exhausted budget never counts as success, so the runtime refuses to record
#: `success` for a loop that produced no accepted iteration.
TERMINAL_STATES = ("success", "no_op", "blocked", "stalled", "exhausted")


@dataclass
class Loop:
    """A control-flow scope bound to exactly one region.

    This is the loop-engineering primitive: while a loop is bound, every read
    and write it performs resolves against its assigned region (and, if
    ``descend``, that region's subtree) and nothing else.

    A loop also carries its *specification* — trigger, goal, declared
    verification level — as data rather than as prose in a script, so the
    runtime can check the declaration against what the loop actually did.
    """

    loop_id: str
    scw_id: str
    descend: bool
    bound_seq: int
    max_iterations: Optional[int] = None
    iteration: int = 0
    status: str = "bound"  # bound | unbound | exhausted
    reads: int = 0
    writes: int = 0
    denials: int = 0
    cached_tokens: int = 0
    reprocessed_tokens: int = 0
    recoverable_tokens: int = 0

    # -- declared specification -----------------------------------------
    trigger: str = "manual"
    goal: Optional[str] = None
    verification_level: Optional[int] = None
    terminal_state: Optional[str] = None
    prompt_id: Optional[str] = None
    prompt_version_at_bind: Optional[int] = None
    harness_id: Optional[str] = None

    # -- declared partition surface --------------------------------------
    #: Regions this loop's work is deliberately published to, and the *only*
    #: regions a judge of this loop may share with it. Host-authored at bind:
    #: a bound loop cannot widen its own exposure, which is what stops the
    #: disjointness check from being satisfied vacuously by the party it
    #: constrains. Empty means "a judge may see none of what I wrote".
    exposes: tuple[str, ...] = ()
    #: A pinned acceptance criterion this loop is graded against (see
    #: :mod:`scw_runtime.attest`). Frozen at bind; drift is refused at tick.
    criterion_id: Optional[str] = None

    # -- control-flow nesting ---------------------------------------------
    #: Loops nest the way regions do. Without this the runtime could not tell
    #: a sub-loop from a sibling, could not refuse a cycle, and could not
    #: price nesting — whose cost multiplies rather than adds.
    parent_loop_id: Optional[str] = None
    child_loop_ids: list[str] = field(default_factory=list)
    depth: int = 0

    # -- identity ---------------------------------------------------------
    #: Rebinding the same id starts a new generation. Counters reset per
    #: generation but the lifetime totals carry forward, so unbind+rebind
    #: cannot launder a loop's accountability record out of live state.
    generation: int = 1
    lifetime: dict = field(default_factory=dict)

    # -- observed against the declaration -------------------------------
    accepted: int = 0            # iterations whose verification passed
    rejected: int = 0            # iterations whose verification failed
    unverified: int = 0          # iterations that carried no verdict at all
    unverified_streak: int = 0   # consecutive iterations without a pass
    self_approved: int = 0       # verdicts supplied by the loop itself
    attested: int = 0            # verdicts that carried external evidence

    def lifetime_totals(self) -> dict:
        """Counters for this generation folded into every prior one."""
        base = {
            "iterations": self.iteration,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "unverified": self.unverified,
            "self_approved": self.self_approved,
            "denials": self.denials,
            "generations": self.generation,
        }
        for key, value in self.lifetime.items():
            if key == "generations":
                continue
            base[key] = base.get(key, 0) + value
        return base

    def to_dict(self) -> dict:
        billed = self.cached_tokens + self.reprocessed_tokens
        return {
            "loop_id": self.loop_id,
            "scw_id": self.scw_id,
            "descend": self.descend,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "status": self.status,
            "reads": self.reads,
            "writes": self.writes,
            "denials": self.denials,
            "spec": {
                "trigger": self.trigger,
                "goal": self.goal,
                "verification_level": self.verification_level,
                "verification_zone": self.verification_zone,
                "terminal_state": self.terminal_state,
                "prompt_id": self.prompt_id,
                "prompt_version_at_bind": self.prompt_version_at_bind,
                "harness_id": self.harness_id,
                "exposes": list(self.exposes),
                "criterion_id": self.criterion_id,
            },
            "nesting": {
                "parent_loop_id": self.parent_loop_id,
                "child_loop_ids": list(self.child_loop_ids),
                "depth": self.depth,
            },
            "identity": {
                "generation": self.generation,
                "lifetime": self.lifetime_totals(),
            },
            "verification": {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "unverified": self.unverified,
                "unverified_streak": self.unverified_streak,
                "self_approved": self.self_approved,
                "attested": self.attested,
            },
            "ledger": {
                "cached_tokens": self.cached_tokens,
                "reprocessed_tokens": self.reprocessed_tokens,
                "recoverable_tokens": self.recoverable_tokens,
                "cache_hit_ratio": round(self.cached_tokens / billed, 4) if billed else 0.0,
                "billed_tokens": billed,
                "cost_per_accepted_change": (
                    round(billed / self.accepted, 1) if self.accepted else None
                ),
            },
        }

    @property
    def verification_zone(self) -> Optional[str]:
        """Which zone of the ladder the *declared* level sits in."""
        if self.verification_level is None:
            return None
        if self.verification_level in AUTONOMOUS_ZONE:
            return "autonomous"
        if self.verification_level in OBJECTIVE_ZONE:
            return "objective"
        return "assisted"


@dataclass
class Bridge:
    """An explicit, logged grant that punches through one wall.

    Bridges are the *only* way a bound scope reaches another region. They name
    a direction, a reason, and optionally a TTL in loop ticks, so a grant that
    was meant for one iteration cannot quietly become permanent.
    """

    bridge_id: str
    from_scw_id: str
    to_scw_id: str
    mode: str
    reason: str
    opened_seq: int
    opened_tick: int
    ttl_ticks: Optional[int] = None
    status: str = "open"  # open | closed | expired
    #: Which loop minted this grant, or ``None`` for a host-minted one. A TTL
    #: is measured in *the owner's* iterations: without an owner, "expires at
    #: the end of the iteration that opened it" silently means "expires at
    #: whichever loop happens to tick next" as soon as two loops are bound.
    owner_loop_id: Optional[str] = None

    @property
    def expires_at_tick(self) -> Optional[int]:
        return None if self.ttl_ticks is None else self.opened_tick + self.ttl_ticks

    def grants(self, op: str) -> bool:
        if self.status != "open":
            return False
        if self.mode == "read_write":
            return True
        return self.mode == op

    def to_dict(self) -> dict:
        return {
            "bridge_id": self.bridge_id,
            "from_scw_id": self.from_scw_id,
            "to_scw_id": self.to_scw_id,
            "mode": self.mode,
            "reason": self.reason,
            "ttl_ticks": self.ttl_ticks,
            "opened_tick": self.opened_tick,
            "expires_at_tick": self.expires_at_tick,
            "status": self.status,
            "opened_seq": self.opened_seq,
            "owner_loop_id": self.owner_loop_id,
        }
