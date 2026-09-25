"""The runtime: an addressable context window.

A :class:`ContextWindow` is the whole thing — a set of typed regions with
policies, the loops bound to them, the bridges between them, and the event log
that describes every transition.

Four ideas hold it together:

1. **Addressing.** Regions have ids and a render order, so control flow can
   name a region as its execution scope instead of operating on one
   undifferentiated buffer.
2. **Isolation.** :mod:`scw_runtime.isolation` gates every access. A bound
   loop reaches its own region and nothing else unless a bridge says otherwise,
   and refusals are logged rather than silently coerced.
3. **Policy.** Volatile / durable / read-only, budgets, eviction, per-tick
   reset, promotion — decided up front, enforced here.
4. **Billing.** Structure is what makes prefix caching possible, so the runtime
   prices every iteration and names the region that is costing you tokens.

Every mutation is written to the event log with a payload complete enough for
:mod:`scw_runtime.replay` to rebuild state from the log alone.
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable, Optional, Sequence

from . import tokens as tok
from .attest import Attestation, Criterion, validate_kind
from .cache import RegionCost, Snapshot, compute_plan, ordering_advisories
from .errors import (
    AttestationViolation,
    BudgetExceeded,
    CriterionViolation,
    DisjointnessViolation,
    DuplicateId,
    HarnessViolation,
    IsolationViolation,
    LoopExhausted,
    NestingViolation,
    PolicyViolation,
    PromptViolation,
    RegionClosed,
    UnknownBridge,
    UnknownHarness,
    UnknownLoop,
    UnknownPrompt,
    UnknownRegion,
)
from .events import EventLog
from .harness import (
    ARCHITECTURES,
    EVIDENCE_POLICIES,
    SANDBOXES,
    VERIFICATION_POLICIES,
    HarnessProfile,
    Skill,
)
from .isolation import ORCHESTRATOR, Decision, Scope, descendants, resolve_scope
from .partition import (
    disjointness,
    grant_visible_subtree,
    record_exposure_ceiling,
    loop_ancestors,
    loop_descendants,
    read_closure,
    write_closure,
)
from .model import (
    Bridge,
    Entry,
    Loop,
    OBJECTIVE_ZONE,
    Region,
    TERMINAL_STATES,
    TRIGGERS,
    TYPE_ORDER,
    VERIFICATION_LADDER,
    preset_for,
)
from .prompt import PromptRevision, PromptSpec, declared_variables, fill

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    out = _SLUG.sub("-", text.strip().lower()).strip("-")
    return out or "scw"


def _dedupe_id(candidate: str, existing: dict, explicit: bool) -> str:
    """Resolve an id against a namespace, deduplicating a derived slug with
    `-2`, `-3`... An explicitly requested id that collides is a hard error."""
    if candidate not in existing:
        return candidate
    if explicit:
        raise DuplicateId(f"id {candidate!r} already exists")
    suffix = 2
    while f"{candidate}-{suffix}" in existing:
        suffix += 1
    return f"{candidate}-{suffix}"


class ContextWindow:
    """One structured context window and everything bound to it."""

    def __init__(
        self,
        total_budget: Optional[int] = None,
        event_log: Optional[EventLog] = None,
        strict_scope: bool = False,
        log_content: bool = True,
        name: str = "window",
        emit_init: bool = True,
        host_only_bridges: bool = False,
        require_bounded_loops: bool = False,
        max_total_iterations: Optional[int] = None,
        max_loop_depth: Optional[int] = None,
    ) -> None:
        self.name = name
        self.total_budget = total_budget
        self.strict_scope = strict_scope
        self.log_content = log_content
        # When true, only the unbound host may mint bridges. Default false: a
        # loop may grant itself access to regions the host marked bridgeable,
        # and every grant is logged with a reason and a TTL. Turn it on when
        # the set of crossings must be decided entirely outside the loop.
        self.host_only_bridges = host_only_bridges
        # A loop with no ceiling is the "unattended runaway" anti-pattern with
        # the brakes left as a comment. When this is on, bind_scope refuses a
        # loop that declares no max_iterations, so the ceiling is a
        # precondition of running rather than a habit of the author.
        self.require_bounded_loops = require_bounded_loops
        self.max_total_iterations = max_total_iterations
        self.max_loop_depth = max_loop_depth
        self.regions: dict[str, Region] = {}
        self.loops: dict[str, Loop] = {}
        self.bridges: dict[str, Bridge] = {}
        self.prompts: dict[str, PromptSpec] = {}
        self.harnesses: dict[str, HarnessProfile] = {}
        self.criteria: dict[str, Criterion] = {}
        self.evidence: dict[str, Attestation] = {}
        #: scope root region id -> the widest handoff surface ever declared for
        #: it. Monotonically narrowing: a later binding of *any* loop to that
        #: root may declare a subset, never a superset. Keyed on the region
        #: because the region is what determines a write closure; keying it only
        #: on the loop id let a fresh id reset the ceiling (see `bind_scope`).
        self.exposure_ceiling: dict[str, tuple[str, ...]] = {}
        self.roots: list[str] = []
        self.tick = 0
        self.total_iterations = 0
        self.last_tick_seq = -1
        # Start of the current iteration: the later of the last tick and the
        # last scope binding. A region counts as "active" when it has been
        # written since this point, which is what the inspector colours.
        self.iteration_boundary_seq = -1
        self.log = event_log if event_log is not None else EventLog()
        self._tick_snapshot = Snapshot()
        # Render baselines are per-caller. Different scopes see different
        # windows now that render() is scope-true, so one global baseline
        # would price every loop against whatever another loop last rendered.
        self._render_snapshots: dict[Optional[str], Snapshot] = {}
        self._bridge_seq = 0
        self._entry_seq = 0
        self._criterion_seq = 0
        self._evidence_seq = 0
        # scw_id -> (revision_key, rendered_text, token_count)
        self._footprints: dict[str, tuple[str, str, int]] = {}
        if not emit_init:
            # Used by :mod:`scw_runtime.replay`, which rebuilds state from an
            # existing log and must not append to it.
            return
        self.log.emit(
            "window.init",
            ORCHESTRATOR,
            {
                "name": name,
                "total_budget": total_budget,
                "strict_scope": strict_scope,
                "log_content": log_content,
                "host_only_bridges": host_only_bridges,
                "require_bounded_loops": require_bounded_loops,
                "max_total_iterations": max_total_iterations,
                "max_loop_depth": max_loop_depth,
                "tokenizer": tok.tokenizer_name(),
                "schema_version": 2,
                # Ties this run's chain to the one before it in the same file.
                # None for the first run, or for a window that was not created
                # by resetting a previous one.
                "prev_run": self.log.prev_run,
            },
        )

    @classmethod
    def hardened(cls, total_budget: Optional[int] = None, **kwargs) -> "ContextWindow":
        """A window with the strict dials on, ready to be sealed.

        The default constructor stays permissive on purpose: it is the
        configuration the v0.2.0 corpus study measured, and silently tightening
        it would invalidate those numbers. This is the opposite default — what
        to reach for when a loop will run unattended, and the configuration
        whose guarantees the enforcement claims describe.

        Sets ``host_only_bridges`` (crossings decided outside the loop) and
        ``require_bounded_loops`` (no loop without a ceiling). It deliberately
        does **not** set ``strict_scope``, because the host has to be able to
        build the window before there is any loop to attribute the building
        to. Call :meth:`seal` once setup is done; that is the moment the
        privileged unbound path closes.
        """
        kwargs.setdefault("host_only_bridges", True)
        kwargs.setdefault("require_bounded_loops", True)
        return cls(total_budget=total_budget, **kwargs)

    def seal(self) -> dict:
        """Close the privileged unbound path for the rest of the run.

        Setup and operation are different phases with different threat models:
        during setup the host is the only actor and must be able to create
        regions and seed read-only material; once loops are bound, an
        unattributed call is exactly what should not exist. ``strict_scope``
        expresses the second phase, and sealing is the transition — recorded,
        like everything else, so an auditor can see when the window stopped
        accepting anonymous calls.
        """
        self._commit(
            "window.seal",
            ORCHESTRATOR,
            {
                "strict_scope": True,
                "regions": len(self.regions),
                "loops": sorted(self.loops),
                "tick": self.tick,
            },
            lambda seq: setattr(self, "strict_scope", True),
        )
        return {"sealed": True, "strict_scope": True, "regions": len(self.regions)}

    # ------------------------------------------------------------------
    # closures — what a scope can reach, as a set rather than one answer
    # ------------------------------------------------------------------
    def read_closure(self, loop_id: Optional[str]) -> set[str]:
        """Every region ``loop_id`` can obtain bytes from. See
        :mod:`scw_runtime.partition`."""
        return read_closure(self, loop_id)

    def write_closure(self, loop_id: Optional[str]) -> set[str]:
        """Every region ``loop_id`` can put bytes into."""
        return write_closure(self, loop_id)

    def disjointness(self, maker_id: str, judge_id: Optional[str]) -> dict:
        """Would ``judge_id``'s verdict on ``maker_id`` be accepted, and why?

        Pure and side-effect free, so this is askable before the tick that
        would be refused. The report it returns is the same one the refusal
        carries.
        """
        return disjointness(self, maker_id, judge_id)

    def resolve_actor(self, name: Optional[str]) -> Optional[Loop]:
        """Resolve an asserted actor name to a currently bound loop.

        Returns ``None`` for an unknown name, a released loop, or ``None``
        itself. The runtime had no such resolution before: ``verified_by`` was
        compared as a string, so any value other than the caller's own id
        passed every check while naming nobody.
        """
        if name is None:
            return None
        loop = self.loops.get(name)
        return loop if loop is not None and loop.status == "bound" else None

    # ------------------------------------------------------------------
    # lookups and guards
    # ------------------------------------------------------------------
    def _region(self, scw_id: str) -> Region:
        region = self.regions.get(scw_id)
        if region is None:
            raise UnknownRegion(f"no region {scw_id!r}", scw_id=scw_id, known=sorted(self.regions))
        return region

    def _open_region(self, scw_id: str) -> Region:
        region = self._region(scw_id)
        if region.lifecycle != "open":
            raise RegionClosed(
                f"region {scw_id!r} is {region.lifecycle}", scw_id=scw_id, lifecycle=region.lifecycle
            )
        return region

    def _deny(
        self,
        op: str,
        scw_id: Optional[str],
        loop_id: Optional[str],
        reason: str,
        actor: str,
        hint: str = "",
        scope_root: Optional[str] = None,
        **extra: object,
    ) -> None:
        """Record a refusal. Every rejected operation goes through here.

        Denials are events, not exceptions-and-forget: an SCW deployment should
        be able to answer "what did this loop try to reach that it could not?"
        from the log alone.
        """
        payload = {
            "op": op,
            "scw_id": scw_id,
            "loop_id": loop_id,
            "scope_root": scope_root,
            "reason": reason,
            "hint": hint,
        }
        payload.update(extra)
        self.log.emit("scw.denied", actor, payload)
        loop = self.loops.get(loop_id) if loop_id else None
        if loop is not None:
            loop.denials += 1

    def _authorize(self, op: str, scw_id: str, loop_id: Optional[str]) -> tuple[Scope, Decision]:
        """Resolve the caller's scope and enforce it, logging any refusal.

        Nothing mutates before this returns, so a denied call leaves the window
        byte-identical to how it was found.
        """
        scope = resolve_scope(self, loop_id)
        decision = scope.check(op, scw_id)
        if not decision.allowed:
            self._deny(
                op,
                scw_id,
                loop_id,
                decision.reason,
                scope.actor,
                hint=decision.hint,
                scope_root=scope.root,
            )
            raise IsolationViolation(decision.reason, scw_id=scw_id, loop_id=loop_id, hint=decision.hint)
        return scope, decision

    def _touch(self, region: Region, seq: int) -> None:
        region.revision += 1
        region.last_mutation_seq = seq

    def _commit(self, type: str, actor: str, payload: dict, apply: "Callable[[int], None]") -> dict:
        """Write the record describing a change, *then* make the change.

        The log is meant to be a complete description of the window rather than
        a commentary on it, and that ordering is what makes the claim true.
        :meth:`EventLog.emit` performs a real, fallible disk write; if it
        raises — a full disk, a revoked handle — ``apply`` never runs and the
        window is left byte-identical to how it was found. Mutating first and
        emitting second inverts that: the in-memory state moves, the log does
        not, and a replay of that log rebuilds a window that never existed.

        ``apply`` receives the sequence number the record was assigned, since
        entries and revisions are stamped with it.
        """
        record = self.log.emit(type, actor, payload)
        apply(record["seq"])
        return record

    # ------------------------------------------------------------------
    # ordering, rendering, token accounting
    # ------------------------------------------------------------------
    def _ordered_children(self, scw_id: Optional[str]) -> list[str]:
        ids = self.roots if scw_id is None else self.regions[scw_id].children
        return sorted(ids, key=lambda i: (self.regions[i].order, self.regions[i].created_seq, i))

    def _subtree_pairs(self, scw_id: str) -> list[tuple[str, int]]:
        region = self.regions[scw_id]
        pairs = [(scw_id, region.revision)]
        for child in self._ordered_children(scw_id):
            pairs.extend(self._subtree_pairs(child))
        return pairs

    def _revision_key(self, scw_id: str) -> str:
        """Cheap memo key: any mutation anywhere in the subtree changes it."""
        return "|".join(f"{sid}@{rev}" for sid, rev in self._subtree_pairs(scw_id))

    def _render_region(
        self, scw_id: str, indent: int = 0, allowed: Optional[set[str]] = None
    ) -> str:
        """Render a region's subtree.

        ``allowed``, when given, restricts which descendants are rendered.
        This is how a read taken *through a grant* stops leaking children that
        declared ``bridgeable=False``: the wall those children put up has to
        hold against a read of their parent, or it is not a wall.
        """
        region = self.regions[scw_id]
        pad = "  " * indent
        head = (
            f'{pad}<scw id="{region.scw_id}" label="{region.label}" '
            f'type="{region.region_type}" policy="{region.policy.mutability}">'
        )
        lines = [head]
        for entry in region.entries:
            body = entry.data if entry.key is None else f"{entry.key}: {entry.data}"
            lines.extend(f"{pad}  {line}" for line in (body.splitlines() or [""]))
        for child in self._ordered_children(scw_id):
            if allowed is not None and child not in allowed:
                continue
            lines.append(self._render_region(child, indent + 1, allowed))
        lines.append(f"{pad}</scw>")
        return "\n".join(lines)

    def footprint(self, scw_id: str) -> tuple[str, int]:
        """Rendered text and exact token cost of a region's whole subtree.

        Delimiters are counted, because they are real tokens in the prompt.
        """
        key = self._revision_key(scw_id)
        cached = self._footprints.get(scw_id)
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        text = self._render_region(scw_id)
        count = tok.count_tokens(text)
        self._footprints[scw_id] = (key, text, count)
        return text, count

    def signature(self, scw_id: str) -> str:
        """Content fingerprint of a subtree.

        Deliberately derived from the *rendered bytes*, not from revision
        counters: a prefix cache keys on bytes, so a region written and then
        restored to identical text is genuinely still cached.
        """
        text, _ = self.footprint(scw_id)
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def _costs(self) -> list[RegionCost]:
        costs = []
        for scw_id in self._ordered_children(None):
            text, count = self.footprint(scw_id)
            costs.append(
                RegionCost(
                    scw_id=scw_id,
                    tokens=count,
                    signature=hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
                    cache_hint=self.regions[scw_id].policy.cache,
                )
            )
        return costs

    def _region_tokens(self) -> dict[str, int]:
        """Subtree token counts for every region — authoritative numbers for the UI."""
        return {scw_id: self.footprint(scw_id)[1] for scw_id in self.regions}

    def used_tokens(self) -> int:
        return sum(c.tokens for c in self._costs())

    def _snapshot_now(self) -> Snapshot:
        costs = self._costs()
        return Snapshot(
            order=[c.scw_id for c in costs],
            signatures={c.scw_id: c.signature for c in costs},
        )

    def _depth(self, scw_id: str) -> int:
        depth = 0
        parent = self.regions[scw_id].parent_id
        while parent is not None:
            depth += 1
            parent = self.regions[parent].parent_id
        return depth

    def _occupants(self, scw_id: str) -> list[str]:
        out = []
        for loop in self.loops.values():
            if loop.status != "bound" or loop.scw_id not in self.regions:
                continue
            if loop.scw_id == scw_id or (loop.descend and scw_id in descendants(self, loop.scw_id)):
                out.append(loop.loop_id)
        return sorted(out)

    def _bound_region_ids(self) -> set[str]:
        occupied: set[str] = set()
        for loop in self.loops.values():
            if loop.status != "bound" or loop.scw_id not in self.regions:
                continue
            occupied.add(loop.scw_id)
            if loop.descend:
                occupied |= descendants(self, loop.scw_id)
        return occupied

    # ------------------------------------------------------------------
    # regions
    # ------------------------------------------------------------------
    def create_scw(
        self,
        label: str,
        region_type: str = "working",
        policy: Optional[dict] = None,
        parent_scw_id: Optional[str] = None,
        order: Optional[int] = None,
        scw_id: Optional[str] = None,
        loop_id: Optional[str] = None,
    ) -> Region:
        """Create a region, optionally nested inside another.

        A bound loop may only create regions inside its own scope. Creating a
        top-level region while bound is an isolation violation: a loop that can
        add siblings can escape its partition by construction.
        """
        resolved_policy = preset_for(region_type, policy)

        if parent_scw_id is not None:
            self._authorize("write", parent_scw_id, loop_id)
            parent = self._open_region(parent_scw_id)
            if parent.policy.mutability == "readonly" and loop_id is not None:
                raise PolicyViolation(f"parent {parent_scw_id!r} is read-only", scw_id=parent_scw_id)
        else:
            parent = None
            scope = resolve_scope(self, loop_id)
            if scope.loop_id is not None or scope.unbound_denied:
                reason = (
                    "a bound loop cannot create top-level regions; nest under its scope instead"
                    if scope.loop_id is not None
                    else "strict_scope is on and the caller supplied no loop_id"
                )
                self._deny("create", None, loop_id, reason, scope.actor, scope_root=scope.root)
                raise IsolationViolation(reason, loop_id=loop_id)

        candidate = scw_id or slugify(label)
        if candidate in self.regions:
            if scw_id is not None:
                raise DuplicateId(f"region id {scw_id!r} already exists", scw_id=scw_id)
            suffix = 2
            while f"{candidate}-{suffix}" in self.regions:
                suffix += 1
            candidate = f"{candidate}-{suffix}"

        siblings = parent.children if parent is not None else self.roots
        resolved_order = order if order is not None else TYPE_ORDER[region_type] * 1000 + len(siblings)

        created: dict[str, Region] = {}

        def apply(seq: int) -> None:
            region = Region(
                scw_id=candidate,
                label=label,
                region_type=region_type,
                policy=resolved_policy,
                order=resolved_order,
                created_seq=seq,
                parent_id=parent_scw_id,
            )
            self.regions[candidate] = region
            siblings.append(candidate)
            if parent is not None:
                self._touch(parent, seq)
            created["region"] = region

        self._commit(
            "scw.create",
            resolve_scope(self, loop_id).actor,
            {
                "scw_id": candidate,
                "label": label,
                "region_type": region_type,
                "policy": resolved_policy.to_dict(),
                "parent_id": parent_scw_id,
                "order": resolved_order,
                "loop_id": loop_id,
            },
            apply,
        )
        return created["region"]

    def write(
        self,
        scw_id: str,
        data: str,
        loop_id: Optional[str] = None,
        mode: str = "append",
        key: Optional[str] = None,
    ) -> dict:
        """Write content into a region.

        ``mode="append"`` adds an entry; ``mode="replace"`` clears the region
        first. Supplying ``key`` gives memory-block semantics: the entry with
        that key is upserted in place, so a slot stays addressable across
        iterations instead of accumulating duplicates.
        """
        if mode not in ("append", "replace"):
            raise ValueError("mode must be 'append' or 'replace'")
        scope, decision = self._authorize("write", scw_id, loop_id)
        region = self._open_region(scw_id)

        if region.policy.mutability == "readonly" and loop_id is not None:
            reason = "region policy is read-only; only the unbound host may seed it"
            self._deny("write", scw_id, loop_id, reason, scope.actor, scope_root=scope.root)
            raise PolicyViolation(reason, scw_id=scw_id, mutability="readonly")

        rendered = data if key is None else f"{key}: {data}"
        new_tokens = tok.count_tokens(rendered)
        budget = region.policy.token_budget

        replaced_id: Optional[str] = None
        replaced_tokens = 0
        if key is not None and mode == "append":
            for existing in region.entries:
                if existing.key == key:
                    replaced_id = existing.entry_id
                    replaced_tokens = existing.tokens
                    break

        base_tokens = 0 if mode == "replace" else region.own_tokens - replaced_tokens
        if budget is not None and region.policy.eviction == "reject":
            if self._would_exceed(region, new_tokens, base=base_tokens) is not None:
                self._deny(
                    "write",
                    scw_id,
                    loop_id,
                    "token_budget would be exceeded and eviction policy is 'reject'",
                    scope.actor,
                    scope_root=scope.root,
                    budget=budget,
                    would_be=base_tokens + new_tokens,
                )
                raise BudgetExceeded(
                    f"write of {new_tokens} tokens would exceed budget {budget} for {scw_id!r}",
                    scw_id=scw_id,
                    budget=budget,
                    would_be=base_tokens + new_tokens,
                )

        # Everything below is computed first, emitted second, applied third.
        # `_commit` is what enforces that ordering; see its docstring.
        entry_id = f"e{self._entry_seq + 1}"
        cleared: list[str] = [e.entry_id for e in region.entries] if mode == "replace" else []

        payload = {
            "scw_id": scw_id,
            "entry_id": entry_id,
            "key": key,
            "mode": mode,
            "tokens": new_tokens,
            "loop_id": loop_id,
            "via": decision.via,
            "tick": self.tick,
            "revision": region.revision + 1,
            "replaced_entry_id": replaced_id,
            "cleared_entry_ids": cleared,
        }
        if self.log_content:
            payload["data"] = data
        else:
            payload["data_sha256"] = hashlib.sha256(data.encode("utf-8")).hexdigest()

        def apply(seq: int) -> None:
            self._entry_seq += 1
            entry = Entry(
                entry_id=entry_id,
                data=data,
                tokens=new_tokens,
                key=key,
                written_by=scope.actor,
                tick=self.tick,
                seq=seq,
            )
            if mode == "replace":
                if region.policy.versioned:
                    region.history.extend(region.entries)
                region.entries = [entry]
            elif replaced_id is not None:
                index = next(i for i, e in enumerate(region.entries) if e.entry_id == replaced_id)
                if region.policy.versioned:
                    region.history.append(region.entries[index])
                region.entries[index] = entry
            else:
                region.entries.append(entry)
            self._touch(region, seq)

        self._commit("scw.write", scope.actor, payload, apply)

        evicted = self._enforce_budget(region, scope.actor, reason="budget")
        loop = self.loops.get(loop_id) if loop_id else None
        if loop is not None:
            loop.writes += 1

        return {
            "scw_id": scw_id,
            "entry_id": entry_id,
            "tokens_written": new_tokens,
            "region_tokens": region.own_tokens,
            "token_budget": budget,
            "evicted": evicted,
            "via": decision.via,
            "cache_impact": self._cache_impact(scw_id),
        }

    def _would_exceed(self, region: Region, incoming: int, base: Optional[int] = None) -> Optional[int]:
        """The post-write total when a ``reject`` budget would be broken.

        Returns ``None`` when the write is fine or the policy is not
        ``reject``. Both callers that add tokens — :meth:`write` and
        :meth:`promote` — consult this *before* mutating, which is what makes
        "refuses the write and mutates nothing" true rather than aspirational.
        """
        budget = region.policy.token_budget
        if budget is None or region.policy.eviction != "reject":
            return None
        total = (region.own_tokens if base is None else base) + incoming
        return total if total > budget else None

    def _enforce_budget(self, region: Region, actor: str, reason: str) -> list[str]:
        budget = region.policy.token_budget
        if budget is None or region.own_tokens <= budget:
            return []
        if region.policy.eviction == "reject":
            # `reject` means "refuse the write", not "drop the oldest". Falling
            # through to FIFO here silently destroyed content in the strictest
            # tier — the one the `reference` preset uses — and logged the
            # eviction under the very policy that forbids it. Callers pre-check
            # via _would_exceed, so reaching this point means nothing was added.
            return []
        # Choose the victims without removing them, so the record can be
        # written before the content is gone.
        remaining = list(region.entries)
        victims: list[Entry] = []
        freed = 0
        total = region.own_tokens
        while remaining and total > budget:
            if region.policy.eviction == "lru":
                victim = min(remaining, key=lambda e: (e.last_read_seq, e.seq))
            else:  # fifo
                victim = remaining[0]
            remaining.remove(victim)
            victims.append(victim)
            freed += victim.tokens
            total -= victim.tokens
        evicted = [v.entry_id for v in victims]

        def apply(seq: int) -> None:
            for victim in victims:
                region.entries.remove(victim)
                if region.policy.versioned:
                    region.history.append(victim)
            region.evicted_tokens += freed
            self._touch(region, seq)

        self._commit(
            "scw.evict",
            actor,
            {
                "scw_id": region.scw_id,
                "entry_ids": evicted,
                "tokens_freed": freed,
                "policy": region.policy.eviction,
                "reason": reason,
                "revision": region.revision + 1,
            },
            apply,
        )
        return evicted

    def read(
        self,
        scw_id: str,
        loop_id: Optional[str] = None,
        include_children: bool = True,
    ) -> dict:
        """Read a region. Refused if the caller's scope does not reach it.

        When access was authorized by a *grant* rather than by the caller's own
        scope, the subtree returned is pruned of any descendant declaring
        ``bridgeable=False``. Without that, "no grant can ever be minted into
        this region, by anyone" was defeated by nesting it under a bridgeable
        parent and reading the parent — which is the default call shape.
        """
        scope, decision = self._authorize("read", scw_id, loop_id)
        region = self._region(scw_id)
        via_grant = decision.via not in ("scope", "descend", ORCHESTRATOR)
        allowed: Optional[set[str]] = None
        elided: list[str] = []
        if include_children and via_grant:
            allowed = grant_visible_subtree(self, scw_id)
            elided = sorted(descendants(self, scw_id) - allowed)

        if include_children:
            if allowed is None:
                text, count = self.footprint(scw_id)
            else:
                text = self._render_region(scw_id, allowed=allowed)
                count = tok.count_tokens(text)
        else:
            text = "\n".join(
                (e.data if e.key is None else f"{e.key}: {e.data}") for e in region.entries
            )
            count = tok.count_tokens(text)

        if include_children:
            visible = sorted(
                descendants(self, scw_id) if allowed is None else (allowed - {scw_id})
            )
        else:
            visible = []
        touched = [scw_id] + visible
        if elided:
            # A pruned read is a refusal in miniature and is recorded as one,
            # so "what did this loop try to reach that it could not?" stays
            # answerable from the log.
            self._deny(
                "read",
                scw_id,
                loop_id,
                f"{len(elided)} descendant region(s) declare bridgeable=false and were "
                f"elided from a read taken through {decision.via}",
                scope.actor,
                hint="bind the loop to a common ancestor if it legitimately needs them",
                scope_root=scope.root,
                elided=elided,
            )
        def apply(seq: int) -> None:
            # Stamping read recency is a real mutation — it steers LRU
            # eviction — so it waits for the record like every other one.
            for read_id in touched:
                target = self.regions[read_id]
                for entry in target.entries:
                    entry.last_read_seq = seq
                target.last_read_seq = seq
            loop = self.loops.get(loop_id) if loop_id else None
            if loop is not None:
                loop.reads += 1

        self._commit(
            "scw.read",
            scope.actor,
            {
                "scw_id": scw_id,
                "loop_id": loop_id,
                "via": decision.via,
                "tokens": count,
                "entry_count": len(region.entries),
                "include_children": include_children,
                "elided": elided,
            },
            apply,
        )
        return {
            "scw_id": scw_id,
            "label": region.label,
            "region_type": region.region_type,
            "lifecycle": region.lifecycle,
            "content": text,
            "tokens": count,
            "entries": [e.to_dict() for e in region.entries],
            "via": decision.via,
        }

    def close_scw(self, scw_id: str, loop_id: Optional[str] = None, cascade: bool = False) -> dict:
        """Seal a region — or destroy its content, if the policy says so."""
        scope, _ = self._authorize("write", scw_id, loop_id)
        region = self._open_region(scw_id)

        open_children = [c for c in region.children if self.regions[c].lifecycle == "open"]
        if open_children and not cascade:
            raise PolicyViolation(
                f"region {scw_id!r} has open children: {open_children}",
                scw_id=scw_id,
                open_children=open_children,
                hint="close the children first, or pass cascade=True",
            )

        # Validate the *whole* subtree before touching any of it. Checking one
        # region at a time and recursing meant a refusal partway down left
        # earlier children sealed, their close events already in the chain, and
        # the parent still open — a half-applied operation in a runtime whose
        # contract is that a denied call leaves the window byte-identical.
        targets = [scw_id]
        if cascade:
            stack = list(open_children)
            while stack:
                current = stack.pop()
                if self.regions[current].lifecycle != "open":
                    continue
                targets.append(current)
                stack.extend(
                    c for c in self.regions[current].children
                    if self.regions[c].lifecycle == "open"
                )
        for target_id in targets:
            occupants = self._occupants(target_id)
            if occupants:
                raise PolicyViolation(
                    f"region {target_id!r} still has bound loops: {occupants}",
                    scw_id=target_id,
                    occupants=occupants,
                    hint="call unbind_scope for each loop first",
                )
            if target_id != scw_id:
                self._authorize("write", target_id, loop_id)

        closed_children: list[str] = []
        if cascade:
            for child in list(open_children):
                self.close_scw(child, loop_id=loop_id, cascade=True)
                closed_children.append(child)

        purged = region.policy.purge_on_close
        dropped_tokens = region.own_tokens if purged else 0
        dropped_ids = [e.entry_id for e in region.entries] if purged else []
        lifecycle = "purged" if purged else "sealed"

        def apply_close(seq: int) -> None:
            region.lifecycle = lifecycle
            self._touch(region, seq)

        self._commit(
            "scw.close",
            scope.actor,
            {
                "scw_id": scw_id,
                "lifecycle": lifecycle,
                "loop_id": loop_id,
                "cascade": cascade,
                "closed_children": closed_children,
                "revision": region.revision + 1,
            },
            apply_close,
        )
        if purged:
            def apply_purge(seq: int) -> None:
                if region.policy.versioned:
                    region.history.extend(region.entries)
                region.entries = []

            self._commit(
                "scw.purge",
                scope.actor,
                {
                    "scw_id": scw_id,
                    "entry_ids": dropped_ids,
                    "tokens_dropped": dropped_tokens,
                    "reason": "purge_on_close",
                },
                apply_purge,
            )

        revoked = self._revoke_bridges_for(scw_id, reason="region_closed", actor=scope.actor)
        return {
            "scw_id": scw_id,
            "lifecycle": region.lifecycle,
            "tokens_dropped": dropped_tokens,
            "closed_children": closed_children,
            "bridges_revoked": revoked,
        }

    # ------------------------------------------------------------------
    # loops
    # ------------------------------------------------------------------
    def bind_scope(
        self,
        loop_id: str,
        scw_id: str,
        descend: bool = True,
        max_iterations: Optional[int] = None,
        trigger: str = "manual",
        goal: Optional[str] = None,
        verification_level: Optional[int] = None,
        prompt_id: Optional[str] = None,
        harness_id: Optional[str] = None,
        exposes: Optional[Sequence[str]] = None,
        criterion_id: Optional[str] = None,
        parent_loop_id: Optional[str] = None,
    ) -> Loop:
        """Bind a loop's execution scope to one region, and declare its spec.

        This is the join between SCWs and loop engineering: from here until
        :meth:`unbind_scope`, every call carrying ``loop_id`` resolves against
        ``scw_id`` (plus its subtree when ``descend``) and is refused anywhere
        else.

        ``trigger``, ``goal`` and ``verification_level`` are the loop
        specification (the loop layer), declared as data instead of left
        implicit in a script. ``prompt_id`` and ``harness_id`` extend that
        declaration across the other two layers of the progression this
        runtime targets: which instruction artifact governs this loop (the
        prompt layer) and which environment/architecture/skill set it runs
        under (the harness layer). Declaring all four at one call is
        deliberate — it is the single point where a loop's full position in
        the stack becomes a fact in the log rather than four separate claims
        that can drift apart.

        The runtime holds every declaration to account: a loop that claims the
        autonomous zone (level 1–2) but never supplies a verdict, or one that
        judges its own work at level 4, is flagged rather than believed; a
        prompt that changes version out from under a still-bound loop is
        flagged the same way (``prompt.version_drift``); a loop bound to a
        ``maker_checker`` harness is refused outright, not flagged, if it
        tries to approve its own work at `loop_tick`.
        """
        if trigger not in TRIGGERS:
            raise ValueError(f"trigger must be one of {TRIGGERS}")
        if verification_level is not None and verification_level not in VERIFICATION_LADDER:
            raise ValueError(f"verification_level must be one of {sorted(VERIFICATION_LADDER)}")
        region = self._open_region(scw_id)
        existing = self.loops.get(loop_id)
        if existing is not None and existing.status == "bound":
            raise PolicyViolation(
                f"loop {loop_id!r} is already bound to {existing.scw_id!r}",
                loop_id=loop_id,
                bound_to=existing.scw_id,
                hint="call unbind_scope first to rebind",
            )
        if max_iterations is not None and max_iterations <= 0:
            raise ValueError("max_iterations must be positive or None")
        if self.require_bounded_loops and max_iterations is None:
            raise PolicyViolation(
                f"this window requires every loop to declare a ceiling; {loop_id!r} declared none",
                loop_id=loop_id,
                hint="pass max_iterations=<N> to bind_scope — an unbounded loop is the "
                "runaway anti-pattern with its brakes left as a comment",
            )

        prompt_version_at_bind: Optional[int] = None
        if prompt_id is not None:
            prompt = self.prompts.get(prompt_id)
            if prompt is None:
                raise UnknownPrompt(f"no prompt {prompt_id!r}", prompt_id=prompt_id)
            prompt_version_at_bind = prompt.version
        if harness_id is not None and harness_id not in self.harnesses:
            raise UnknownHarness(f"no harness {harness_id!r}", harness_id=harness_id)

        if criterion_id is not None:
            criterion = self.criteria.get(criterion_id)
            if criterion is None or criterion.status != "pinned":
                raise CriterionViolation(
                    f"no pinned criterion {criterion_id!r}",
                    criterion_id=criterion_id,
                    hint="call pin_criterion(scw_id) first; a criterion must be frozen "
                    "before a loop can be graded against it",
                )

        # --- control-flow nesting -------------------------------------------
        depth = 0
        parent: Optional[Loop] = None
        if parent_loop_id is not None:
            if parent_loop_id == loop_id:
                raise NestingViolation(
                    f"{loop_id!r} cannot be its own parent",
                    loop_id=loop_id,
                )
            parent = self.loops.get(parent_loop_id)
            if parent is None:
                raise UnknownLoop(f"no loop {parent_loop_id!r}", loop_id=parent_loop_id)
            if parent.status != "bound":
                raise NestingViolation(
                    f"parent loop {parent_loop_id!r} is {parent.status}, not bound",
                    loop_id=loop_id,
                    parent_loop_id=parent_loop_id,
                )
            if parent_loop_id == loop_id or loop_id in (
                [parent_loop_id] + loop_ancestors(self, parent_loop_id)
            ):
                raise NestingViolation(
                    f"binding {loop_id!r} under {parent_loop_id!r} would create a cycle; a "
                    f"sub-loop may never invoke, directly or indirectly, the loop that "
                    f"invoked it",
                    loop_id=loop_id,
                    parent_loop_id=parent_loop_id,
                    ancestors=loop_ancestors(self, parent_loop_id),
                )
            depth = parent.depth + 1
            if self.max_loop_depth is not None and depth > self.max_loop_depth:
                raise NestingViolation(
                    f"nesting {loop_id!r} at depth {depth} exceeds max_loop_depth="
                    f"{self.max_loop_depth}",
                    loop_id=loop_id,
                    depth=depth,
                )
            # Containment: a child's partition must sit inside its parent's, or
            # the "sub-loop" is really a sibling with a misleading name and the
            # parent's ceiling does not bound its blast radius.
            parent_reach = read_closure(self, parent_loop_id)
            if scw_id not in parent_reach:
                raise NestingViolation(
                    f"sub-loop {loop_id!r} would bind {scw_id!r}, which is outside its parent "
                    f"{parent_loop_id!r}'s reach",
                    loop_id=loop_id,
                    parent_loop_id=parent_loop_id,
                    hint="bind the sub-loop inside the parent's subtree, or open a grant first",
                )
            # Cost multiplies with depth rather than adding, so the ceiling has
            # to be declared against the product.
            if parent.max_iterations is not None and max_iterations is not None:
                product = parent.max_iterations * max_iterations
                if self.max_total_iterations is not None and product > self.max_total_iterations:
                    raise NestingViolation(
                        f"{parent_loop_id!r}×{loop_id!r} declares up to {product} iterations "
                        f"({parent.max_iterations}×{max_iterations}), over max_total_iterations="
                        f"{self.max_total_iterations}",
                        loop_id=loop_id,
                        multiplicative_ceiling=product,
                    )

        # --- exposure surface -------------------------------------------------
        # Host-authored by construction: bind_scope carries no caller identity,
        # so only the party that owns the window can declare what a loop
        # publishes. That is the whole reason the disjointness proof is worth
        # anything — a loop that could widen its own exposure could satisfy it
        # vacuously.
        exposed = tuple(exposes or ())
        for exposed_id in exposed:
            if exposed_id not in self.regions:
                raise UnknownRegion(
                    f"no region {exposed_id!r} to expose", scw_id=exposed_id
                )
        # Exposure is monotonically non-widening, and it is keyed to the
        # *region* as well as to the loop id. Both keys are needed, and an
        # earlier version of this guard used only the second — which left the
        # bypass it was written to close wide open:
        #
        #   bind("maker", R, exposes=[])          -> verdict refused by R4
        #   bind("maker2", R, exposes=["art"])    -> a fresh id has no prior
        #                                            generation to compare, so
        #                                            nothing refused it
        #   loop_tick("maker2", verified_by=judge) -> accepted
        #
        # Three calls, same region, wider surface, R4 satisfied vacuously. The
        # runtime cannot authenticate who calls bind_scope, so the guard has to
        # be on the *value*; and the value that determines a write closure is
        # the scope root, not the name bound to it.
        # The ceiling is consulted, and moved, only by bindings a disjointness
        # proof could actually be enforced against — those whose harness
        # declares `verification_policy="disjoint"`. A binding that will never
        # have R4 applied to it contributes no exposure to escalate from, and
        # constraining it would refuse ordinary single-loop work for no gain.
        # This is not a loophole: a non-enforced binding cannot *widen* what an
        # enforced one may later declare, because it never sets the ceiling.
        binding_harness = self.harnesses.get(harness_id) if harness_id else None
        governs_exposure = (
            binding_harness is not None
            and binding_harness.verification_policy == "disjoint"
        )
        root_ceiling = self.exposure_ceiling.get(scw_id) if governs_exposure else None
        if root_ceiling is not None:
            widened = set(exposed) - set(root_ceiling)
            if widened:
                raise DisjointnessViolation(
                    f"region {scw_id!r} was first bound exposing "
                    f"{sorted(root_ceiling) or 'nothing'}; no loop bound to it may widen that "
                    f"to include {sorted(widened)}",
                    loop_id=loop_id,
                    scw_id=scw_id,
                    previous_exposes=sorted(root_ceiling),
                    widened=sorted(widened),
                    hint="a region's handoff surface may narrow but never widen, whichever loop "
                    "declares it — binding a fresh loop_id to the same region does not reset "
                    "it. Bind a different root if the partition genuinely changed shape.",
                )
        if existing is not None:
            # The same rule applied to the actor rather than the region, which
            # catches a loop id rebinding to a *different* root with a wider
            # surface than it previously published.
            widened = set(exposed) - set(existing.exposes)
            if widened:
                raise DisjointnessViolation(
                    f"loop {loop_id!r} was first bound exposing "
                    f"{sorted(existing.exposes) or 'nothing'}; rebinding cannot widen that to "
                    f"include {sorted(widened)}",
                    loop_id=loop_id,
                    previous_exposes=sorted(existing.exposes),
                    widened=sorted(widened),
                    hint="a handoff surface may narrow on rebind but never widen — otherwise "
                    "unbind+rebind defeats the partition.",
                )

        # --- identity ----------------------------------------------------------
        generation = 1
        lifetime: dict = {}
        if existing is not None:
            # Rebinding used to construct a fresh Loop, wiping accepted /
            # self_approved / denials and every advisory computed from them —
            # so unbind+rebind laundered a loop's record out of live state.
            generation = existing.generation + 1
            lifetime = existing.lifetime_totals()

        loop = Loop(
            loop_id=loop_id,
            scw_id=scw_id,
            descend=descend,
            bound_seq=self.log.next_seq,
            max_iterations=max_iterations,
            trigger=trigger,
            goal=goal,
            verification_level=verification_level,
            prompt_id=prompt_id,
            prompt_version_at_bind=prompt_version_at_bind,
            harness_id=harness_id,
            exposes=exposed,
            criterion_id=criterion_id,
            parent_loop_id=parent_loop_id,
            depth=depth,
            generation=generation,
            lifetime=lifetime,
        )
        def apply_bind(seq: int) -> None:
            loop.bound_seq = seq
            self.loops[loop_id] = loop
            if parent is not None and loop_id not in parent.child_loop_ids:
                parent.child_loop_ids.append(loop_id)
            self.iteration_boundary_seq = seq
            if governs_exposure:
                record_exposure_ceiling(self, scw_id, exposed)

        self._commit(
            "loop.bind",
            f"loop:{loop_id}",
            {
                "loop_id": loop_id,
                "scw_id": scw_id,
                "descend": descend,
                "max_iterations": max_iterations,
                "region_label": region.label,
                "trigger": trigger,
                "goal": goal,
                "verification_level": verification_level,
                "prompt_id": prompt_id,
                "prompt_version_at_bind": prompt_version_at_bind,
                "harness_id": harness_id,
                "exposes": list(exposed),
                "criterion_id": criterion_id,
                "parent_loop_id": parent_loop_id,
                "depth": depth,
                "generation": generation,
                "lifetime": lifetime,
            },
            apply_bind,
        )
        return loop

    def loop_tick(
        self,
        loop_id: str,
        note: Optional[str] = None,
        verified: Optional[bool] = None,
        verified_by: Optional[str] = None,
        evidence_id: Optional[str] = None,
    ) -> dict:
        """Advance one iteration.

        A tick is the billing boundary. It prices the window against the state
        at the previous tick, folds the result into the loop's ledger, clears
        every ``reset_each_tick`` region in scope, and expires bridges whose
        TTL has run out — so a grant taken for one iteration cannot quietly
        outlive it.

        ``verified`` records the iteration's verdict: ``True`` if the check
        passed, ``False`` if it failed, ``None`` if no check ran. That third
        case is the honest one and the runtime counts it separately — a loop
        that declared the autonomous zone and then never supplied a verdict is
        not autonomous, it is unverified, and the advisories say so.

        ``verified_by`` names who judged. Leaving it unset (or naming the loop
        itself) records a self-approval; at declared level 4 or 5 that is the
        maker grading its own work, which is the failure mode the literature
        singles out.
        """
        loop = self.loops.get(loop_id)
        if loop is None:
            raise UnknownLoop(f"no loop {loop_id!r}", loop_id=loop_id)
        if loop.status != "bound":
            raise PolicyViolation(
                f"loop {loop_id!r} is {loop.status}", loop_id=loop_id, status=loop.status
            )
        if loop.max_iterations is not None and loop.iteration >= loop.max_iterations:
            loop.status = "exhausted"
            raise LoopExhausted(
                f"loop {loop_id!r} reached max_iterations={loop.max_iterations}",
                loop_id=loop_id,
                iteration=loop.iteration,
            )

        harness = self.harnesses.get(loop.harness_id) if loop.harness_id else None

        # --- ceilings, checked before anything mutates ------------------------
        if harness is not None and harness.iteration_budget is not None:
            if harness.iterations_run >= harness.iteration_budget:
                raise LoopExhausted(
                    f"harness {harness.harness_id!r} has spent its iteration_budget of "
                    f"{harness.iteration_budget} across every loop bound to it",
                    loop_id=loop_id,
                    harness_id=harness.harness_id,
                    iterations_run=harness.iterations_run,
                    hint="raise iteration_budget, or close the loop with terminal_state='exhausted'",
                )
        if self.max_total_iterations is not None and self.total_iterations >= self.max_total_iterations:
            raise LoopExhausted(
                f"window reached max_total_iterations={self.max_total_iterations} across all loops",
                loop_id=loop_id,
                total_iterations=self.total_iterations,
            )

        # --- the frozen yardstick has not moved -------------------------------
        criterion = self.criteria.get(loop.criterion_id) if loop.criterion_id else None
        if criterion is not None and criterion.status == "pinned":
            current = self.signature(criterion.scw_id)
            if current != criterion.signature:
                criterion.drift_detected += 1
                raise CriterionViolation(
                    f"criterion {criterion.criterion_id!r} (region {criterion.scw_id!r}) has "
                    f"changed since {loop_id!r} was bound to it — this iteration would be "
                    f"scored against a different yardstick than the last one",
                    loop_id=loop_id,
                    criterion_id=criterion.criterion_id,
                    scw_id=criterion.scw_id,
                    pinned_signature=criterion.signature,
                    current_signature=current,
                    hint="repin_criterion() to accept the new yardstick deliberately and "
                    "restart comparability, or restore the region's content",
                )

        # --- the verdict prologue --------------------------------------------
        # Every check here runs before any pricing, reset, or counter advances,
        # so a refused verdict leaves the window byte-identical. The order is
        # attribution -> disjointness -> evidence: each stage assumes the one
        # before it passed, and the earlier the stage the cheaper the fix.
        policy = harness.verification_policy if harness is not None else "declared"
        evidence: Optional[Attestation] = None
        if verified is True:
            judge_candidate = verified_by or loop_id

            # Under `disjoint`, identity is rule R1 of the proof itself, so it
            # is checked there and the whole decision — pass or fail — lands in
            # the log as one record. Checking it separately first would leave
            # the commonest refusal (a self-approval) with no partition.check
            # event, which is precisely the case an auditor most wants to find.
            if policy == "attributed":
                resolved = self.resolve_actor(verified_by)
                if resolved is None or judge_candidate == loop_id:
                    raise HarnessViolation(
                        f"harness {harness.harness_id!r} requires verification_policy="
                        f"{policy!r}: {judge_candidate!r} does not resolve to a distinct, "
                        f"currently bound loop, so it names nobody the runtime can hold to "
                        f"a boundary",
                        loop_id=loop_id,
                        harness_id=harness.harness_id,
                        verified_by=verified_by,
                        bound_loops=sorted(
                            lid for lid, lp in self.loops.items()
                            if lp.status == "bound" and lid != loop_id
                        ),
                        hint="bind the checker as its own loop and pass its loop_id as "
                        "verified_by — naming a string that is not a loop is not a checker",
                    )

            if policy == "disjoint":
                report = disjointness(self, loop_id, verified_by)
                self.log.emit(
                    "partition.check",
                    f"loop:{loop_id}",
                    {
                        "loop_id": loop_id,
                        "judge": verified_by,
                        "disjoint": report["disjoint"],
                        "failed": report["failed"],
                        "reason": report["reason"],
                        "rules": report["rules"],
                    },
                )
                if not report["disjoint"]:
                    raise DisjointnessViolation(
                        f"harness {harness.harness_id!r} declares architecture="
                        f"{harness.architecture!r}, so a verdict on {loop_id!r} requires a "
                        f"judge whose context is provably separate. {report['reason']}",
                        loop_id=loop_id,
                        harness_id=harness.harness_id,
                        judge=verified_by,
                        failed=report["failed"],
                        report=report,
                        hint="bind the judge to a region outside the maker's write closure, "
                        "and declare the handoff explicitly with bind_scope(exposes=[...])",
                    )

            if harness is not None and harness.evidence_policy != "none":
                level = loop.verification_level
                needs = harness.evidence_policy == "all" or (
                    harness.evidence_policy == "objective"
                    and level is not None
                    and level in OBJECTIVE_ZONE
                )
                if needs:
                    evidence = self._consume_evidence(loop, evidence_id, level)

        # Price the iteration that just ended, before any boundary cleanup.
        plan = compute_plan(self._costs(), self._tick_snapshot)
        actor = f"loop:{loop_id}"

        resets = self._reset_tick_regions(loop, actor)
        expired = self._expire_bridges(actor, next_tick=self.tick + 1, owner=loop_id)
        # Sizes are snapshotted *after* cleanup so that consumers folding the
        # log in order (the inspector) see numbers that match the state they
        # have already applied.
        region_tokens = self._region_tokens()

        # Compute the post-tick values without applying them, so the record
        # that describes the iteration reaches the log before the iteration
        # counter moves.
        judge = verified_by or loop_id
        next_tick = self.tick + 1
        next_iteration = loop.iteration + 1
        next_status = loop.status
        if loop.max_iterations is not None and next_iteration >= loop.max_iterations:
            next_status = "exhausted"

        def apply(seq: int) -> None:
            self.tick = next_tick
            self.total_iterations += 1
            loop.iteration = next_iteration
            loop.cached_tokens += plan.cached_tokens
            loop.reprocessed_tokens += plan.reprocessed_tokens
            loop.recoverable_tokens += plan.recoverable_tokens
            if harness is not None:
                harness.iterations_run += 1
            if evidence is not None:
                evidence.consumed_by_tick = next_tick
                loop.attested += 1
            if verified is True:
                loop.accepted += 1
                loop.unverified_streak = 0
            elif verified is False:
                loop.rejected += 1
                loop.unverified_streak += 1
            else:
                loop.unverified += 1
                loop.unverified_streak += 1
            # Only a self-issued *pass* is the hazard. A loop rejecting its own
            # work is not inflating a score; reward hacking is what happens
            # when the maker approves itself.
            if verified is True and judge == loop_id:
                loop.self_approved += 1
            loop.status = next_status
            self.last_tick_seq = seq
            self.iteration_boundary_seq = seq

        self._commit(
            "loop.tick",
            actor,
            {
                "loop_id": loop_id,
                "iteration": next_iteration,
                "tick": next_tick,
                "note": note,
                "cache": plan.to_dict(),
                "region_tokens": region_tokens,
                "resets": resets,
                "expired_bridges": expired,
                "status": next_status,
                "verified": verified,
                "verified_by": judge if verified is not None else None,
                "evidence_id": evidence.evidence_id if evidence is not None else None,
                "verification_policy": policy,
            },
            apply,
        )
        self._tick_snapshot = self._snapshot_now()

        return {
            "loop_id": loop_id,
            "iteration": loop.iteration,
            "tick": self.tick,
            "status": loop.status,
            "cache": plan.to_dict(),
            "reset_regions": resets,
            "expired_bridges": expired,
            "verification": loop.to_dict()["verification"],
            "ledger": loop.to_dict()["ledger"],
        }

    def _reset_tick_regions(self, loop: Loop, actor: str) -> list[str]:
        scope = resolve_scope(self, loop.loop_id)
        reset: list[str] = []
        for scw_id in sorted(scope.reachable):
            region = self.regions.get(scw_id)
            if region is None or region.lifecycle != "open":
                continue
            if not region.policy.reset_each_tick or not region.entries:
                continue
            freed = region.own_tokens
            entry_ids = [e.entry_id for e in region.entries]

            def apply(seq: int, region: Region = region) -> None:
                if region.policy.versioned:
                    region.history.extend(region.entries)
                region.entries = []
                self._touch(region, seq)

            self._commit(
                "scw.evict",
                actor,
                {
                    "scw_id": scw_id,
                    "entry_ids": entry_ids,
                    "tokens_freed": freed,
                    "policy": region.policy.eviction,
                    "reason": "tick_reset",
                    "revision": region.revision + 1,
                },
                apply,
            )
            reset.append(scw_id)
        return reset

    def _expire_bridges(self, actor: str, next_tick: int, owner: Optional[str] = None) -> list[str]:
        """Expire TTL'd grants belonging to the loop that just ticked.

        A TTL is measured in *the owner's* iterations. Expiring every grant in
        the window on every tick meant that with two loops bound, ``ttl_ticks=1``
        silently became "dies at whichever loop ticks next" — loop A's tick
        would revoke loop B's grant and B's next read would be refused for a
        reason it did not cause. Host-minted grants (no owner) still expire on
        the global tick, because the host has no iteration of its own.
        """
        expired: list[str] = []
        for bridge in self.bridges.values():
            if bridge.status != "open" or bridge.expires_at_tick is None:
                continue
            if bridge.owner_loop_id is not None and bridge.owner_loop_id != owner:
                continue
            if next_tick >= bridge.expires_at_tick:
                expired.append(bridge.bridge_id)
                self._commit(
                    "bridge.close",
                    actor,
                    {
                        "bridge_id": bridge.bridge_id,
                        "status": "expired",
                        "reason": "ttl_ticks elapsed",
                        "from_scw_id": bridge.from_scw_id,
                        "to_scw_id": bridge.to_scw_id,
                    },
                    (lambda b: lambda seq: setattr(b, "status", "expired"))(bridge),
                )
        return expired

    def unbind_scope(self, loop_id: str, terminal_state: Optional[str] = None) -> dict:
        """Release a loop's scope, naming the state it ended in.

        ``terminal_state`` is one of ``success``, ``no_op``, ``blocked``,
        ``stalled``, ``exhausted``. Naming it is what stops "I got tired of
        iterating" from being recorded as a win.

        The runtime enforces one rule rather than trusting the caller for it:
        **``success`` requires at least one accepted iteration.** A loop that
        never passed a verification, or that ran out of budget, cannot be
        closed as a success — that refusal is the whole point of naming
        terminal states at all.
        """
        loop = self.loops.get(loop_id)
        if loop is None:
            raise UnknownLoop(f"no loop {loop_id!r}", loop_id=loop_id)
        if terminal_state is not None and terminal_state not in TERMINAL_STATES:
            raise ValueError(f"terminal_state must be one of {TERMINAL_STATES}")
        if terminal_state == "success" and loop.accepted == 0:
            raise PolicyViolation(
                f"loop {loop_id!r} recorded no accepted iteration, so it cannot close as "
                f"'success' ({loop.rejected} rejected, {loop.unverified} unverified)",
                loop_id=loop_id,
                accepted=loop.accepted,
                hint=(
                    "pass verified=True to loop_tick when a check actually passes, or close "
                    "as 'stalled' / 'exhausted' / 'blocked' — an error is never a success"
                ),
            )

        def apply_unbind(seq: int) -> None:
            loop.status = "unbound"
            loop.terminal_state = terminal_state

        self._commit(
            "loop.unbind",
            f"loop:{loop_id}",
            {
                "loop_id": loop_id,
                "scw_id": loop.scw_id,
                "iterations": loop.iteration,
                "reads": loop.reads,
                "writes": loop.writes,
                "denials": loop.denials,
                "terminal_state": terminal_state,
                "spec": {**loop.to_dict()["spec"], "terminal_state": terminal_state},
                "verification": loop.to_dict()["verification"],
                "ledger": loop.to_dict()["ledger"],
            },
            apply_unbind,
        )
        return loop.to_dict()

    # ------------------------------------------------------------------
    # bridges and promotion
    # ------------------------------------------------------------------
    def open_bridge(
        self,
        from_scw_id: str,
        to_scw_id: str,
        mode: str = "read",
        reason: str = "",
        ttl_ticks: Optional[int] = None,
        loop_id: Optional[str] = None,
    ) -> Bridge:
        """Mint an explicit cross-region grant.

        Bridges are the only legitimate hole in a wall. The target must declare
        ``bridgeable=True``: a region that does not is unreachable from outside
        no matter who asks. ``ttl_ticks=1`` means the grant dies at the end of
        the iteration that opened it.
        """
        if mode not in ("read", "write", "read_write"):
            raise ValueError("mode must be 'read', 'write' or 'read_write'")
        # Both endpoints must be open. A grant minted into a sealed region
        # re-opened access that close_scw had just revoked, so sealing stopped
        # writes without durably stopping reads.
        source = self._open_region(from_scw_id)
        target = self._open_region(to_scw_id)
        if from_scw_id == to_scw_id:
            raise PolicyViolation("a bridge must connect two distinct regions", scw_id=from_scw_id)

        scope = resolve_scope(self, loop_id)
        if scope.loop_id is not None and self.host_only_bridges:
            reason_text = "host_only_bridges is on; only the unbound host may mint grants"
            self._deny("bridge", to_scw_id, loop_id, reason_text, scope.actor, scope_root=scope.root)
            raise IsolationViolation(reason_text, scw_id=to_scw_id, loop_id=loop_id)

        if scope.loop_id is not None and from_scw_id not in scope.reachable:
            reason_text = (
                f"loop {loop_id!r} is bound to {scope.root!r} and cannot mint a bridge "
                f"originating at {from_scw_id!r}"
            )
            self._deny("bridge", from_scw_id, loop_id, reason_text, scope.actor, scope_root=scope.root)
            raise IsolationViolation(reason_text, scw_id=from_scw_id, loop_id=loop_id)

        if not target.policy.bridgeable:
            reason_text = f"region {to_scw_id!r} declares bridgeable=false; no grant can be minted"
            self._deny("bridge", to_scw_id, loop_id, reason_text, scope.actor, scope_root=scope.root)
            raise PolicyViolation(reason_text, scw_id=to_scw_id)

        if mode in ("write", "read_write") and target.policy.mutability == "readonly":
            reason_text = f"region {to_scw_id!r} is read-only; only a 'read' bridge is possible"
            self._deny("bridge", to_scw_id, loop_id, reason_text, scope.actor, scope_root=scope.root)
            raise PolicyViolation(reason_text, scw_id=to_scw_id)

        self._bridge_seq += 1
        bridge = Bridge(
            bridge_id=f"br{self._bridge_seq}",
            from_scw_id=from_scw_id,
            to_scw_id=to_scw_id,
            mode=mode,
            reason=reason,
            opened_seq=self.log.next_seq,
            opened_tick=self.tick,
            ttl_ticks=ttl_ticks,
            owner_loop_id=loop_id,
        )
        def apply_open(seq: int) -> None:
            bridge.opened_seq = seq
            self.bridges[bridge.bridge_id] = bridge

        self._commit(
            "bridge.open",
            scope.actor,
            {
                **bridge.to_dict(),
                "loop_id": loop_id,
                "from_label": source.label,
                "to_label": target.label,
            },
            apply_open,
        )
        return bridge

    def close_bridge(self, bridge_id: str, loop_id: Optional[str] = None) -> dict:
        """Revoke a grant.

        A bound loop may only close a grant it owns or one that originates in
        its own scope. Without that check any loop could revoke any other
        loop's grants mid-iteration — a cross-partition denial of service in a
        runtime whose premise is that loops cannot affect each other.
        """
        bridge = self.bridges.get(bridge_id)
        if bridge is None:
            raise UnknownBridge(f"no bridge {bridge_id!r}", bridge_id=bridge_id)
        scope = resolve_scope(self, loop_id)
        if scope.loop_id is not None:
            owns = bridge.owner_loop_id == loop_id or bridge.from_scw_id in scope.reachable
            if not owns:
                reason = (
                    f"loop {loop_id!r} did not mint {bridge_id!r} and does not hold its source "
                    f"region {bridge.from_scw_id!r}"
                )
                self._deny(
                    "bridge", bridge.to_scw_id, loop_id, reason, scope.actor,
                    scope_root=scope.root, bridge_id=bridge_id,
                )
                raise IsolationViolation(reason, loop_id=loop_id, bridge_id=bridge_id)
        if bridge.status != "open":
            # Do not rewrite the terminal status of an already-expired grant.
            return bridge.to_dict()
        def apply_close(seq: int) -> None:
            bridge.status = "closed"

        self._commit(
            "bridge.close",
            resolve_scope(self, loop_id).actor,
            {
                "bridge_id": bridge_id,
                "status": "closed",
                "reason": "explicit close",
                "from_scw_id": bridge.from_scw_id,
                "to_scw_id": bridge.to_scw_id,
            },
            apply_close,
        )
        return bridge.to_dict()

    def _revoke_bridges_for(self, scw_id: str, reason: str, actor: str) -> list[str]:
        revoked = []
        for bridge in self.bridges.values():
            if bridge.status != "open":
                continue
            if scw_id in (bridge.from_scw_id, bridge.to_scw_id):
                revoked.append(bridge.bridge_id)
                self._commit(
                    "bridge.close",
                    actor,
                    {
                        "bridge_id": bridge.bridge_id,
                        "status": "closed",
                        "reason": reason,
                        "from_scw_id": bridge.from_scw_id,
                        "to_scw_id": bridge.to_scw_id,
                    },
                    (lambda b: lambda seq: setattr(b, "status", "closed"))(bridge),
                )
        return revoked

    def promote(
        self,
        from_scw_id: str,
        to_scw_id: str,
        keys: Optional[Sequence[str]] = None,
        entry_ids: Optional[Sequence[str]] = None,
        loop_id: Optional[str] = None,
        mode: str = "move",
    ) -> dict:
        """Move or copy content across a tier boundary, with provenance.

        Promotion is the controlled way volatile work becomes durable: it needs
        read access to the source *and* write access to the destination, so a
        bound loop cannot launder scratchpad content into persistent memory
        without a bridge that says it may.
        """
        if mode not in ("move", "copy"):
            raise ValueError("mode must be 'move' or 'copy'")
        self._authorize("read", from_scw_id, loop_id)
        if mode == "move":
            # A move *deletes* from the source. Authorizing it with a read
            # grant let a loop empty a read-only `reference` region using the
            # very grant it legitimately needed to cite that region — which
            # made "a loop cannot edit the check it is graded against" false
            # by exactly one keyword argument.
            self._authorize("write", from_scw_id, loop_id)
        scope, decision = self._authorize("write", to_scw_id, loop_id)
        source = self._open_region(from_scw_id) if mode == "move" else self._region(from_scw_id)
        target = self._open_region(to_scw_id)

        if mode == "move" and source.policy.mutability == "readonly" and loop_id is not None:
            reason = (
                f"source {from_scw_id!r} is read-only; a bound loop cannot move content out "
                f"of it (use mode='copy')"
            )
            self._deny("write", from_scw_id, loop_id, reason, scope.actor, scope_root=scope.root)
            raise PolicyViolation(reason, scw_id=from_scw_id, mutability="readonly")
        if target.policy.mutability == "readonly":
            raise PolicyViolation(f"destination {to_scw_id!r} is read-only", scw_id=to_scw_id)

        selected = list(source.entries)
        if entry_ids is not None:
            wanted = set(entry_ids)
            selected = [e for e in selected if e.entry_id in wanted]
        if keys is not None:
            wanted_keys = set(keys)
            selected = [e for e in selected if e.key in wanted_keys]
        if not selected:
            return {"from": from_scw_id, "to": to_scw_id, "mode": mode, "promoted": [], "tokens": 0}

        # Pre-check the destination's budget, like write() does. Promotion used
        # to append first and let _enforce_budget sort it out, which under a
        # `reject` policy silently destroyed existing content in the region
        # whose whole policy is that it refuses rather than drops.
        incoming = sum(e.tokens for e in selected)
        would_be = self._would_exceed(target, incoming)
        if would_be is not None:
            self._deny(
                "write",
                to_scw_id,
                loop_id,
                "token_budget would be exceeded and eviction policy is 'reject'",
                scope.actor,
                scope_root=scope.root,
                budget=target.policy.token_budget,
                would_be=would_be,
            )
            raise BudgetExceeded(
                f"promoting {incoming} tokens would exceed budget "
                f"{target.policy.token_budget} for {to_scw_id!r}",
                scw_id=to_scw_id,
                budget=target.policy.token_budget,
                would_be=would_be,
            )

        # Allocate the new entry ids and build the record before anything moves.
        promoted = []
        for offset, entry in enumerate(selected, start=1):
            promoted.append(
                {
                    "entry_id": f"e{self._entry_seq + offset}",
                    "source_entry_id": entry.entry_id,
                    "key": entry.key,
                    "tokens": entry.tokens,
                    "data": entry.data if self.log_content else None,
                }
            )

        def apply(seq: int) -> None:
            for item, entry in zip(promoted, selected):
                self._entry_seq += 1
                target.entries.append(
                    Entry(
                        entry_id=item["entry_id"],
                        data=entry.data,
                        tokens=entry.tokens,
                        key=entry.key,
                        written_by=scope.actor,
                        tick=self.tick,
                        seq=seq,
                        provenance={
                            "from_scw_id": from_scw_id,
                            "source_entry_id": entry.entry_id,
                            "source_tick": entry.tick,
                            "loop_id": loop_id,
                            "promoted_at_seq": seq,
                            "via": decision.via,
                        },
                    )
                )
                if mode == "move":
                    source.entries.remove(entry)
                    if source.policy.versioned:
                        source.history.append(entry)
            self._touch(target, seq)
            if mode == "move":
                self._touch(source, seq)

        self._commit(
            "promote",
            scope.actor,
            {
                "from_scw_id": from_scw_id,
                "to_scw_id": to_scw_id,
                "mode": mode,
                "loop_id": loop_id,
                "via": decision.via,
                "tick": self.tick,
                "entries": promoted,
                "tokens": sum(p["tokens"] for p in promoted),
                "source_revision": source.revision + (1 if mode == "move" else 0),
                "target_revision": target.revision + 1,
            },
            apply,
        )
        self._enforce_budget(target, scope.actor, reason="budget")
        return {
            "from": from_scw_id,
            "to": to_scw_id,
            "mode": mode,
            "promoted": [{k: v for k, v in p.items() if k != "data"} for p in promoted],
            "tokens": sum(p["tokens"] for p in promoted),
            "via": decision.via,
        }

    # ------------------------------------------------------------------
    # prompts — the prompt layer
    # ------------------------------------------------------------------
    def create_prompt(
        self,
        label: str,
        template: str,
        variables: Optional[Sequence[str]] = None,
        prompt_id: Optional[str] = None,
        locked: bool = False,
        loop_id: Optional[str] = None,
    ) -> PromptSpec:
        """Declare a prompt-layer instruction artifact.

        Host-only: ``loop_id`` must be ``None``. A bound loop can never author
        or revise a prompt, under any bridge — prompts do not participate in
        the region/scope model, so there is no grant that could ever legalize
        it. This is the structural answer to an agent rewriting its own
        instructions mid-run.

        ``variables`` defaults to the ``{{slot}}`` names found in ``template``.
        """
        if loop_id is not None:
            raise PromptViolation(
                "prompts are host-authored only; a bound loop cannot create one",
                loop_id=loop_id,
            )
        candidate = _dedupe_id(prompt_id or slugify(label), self.prompts, explicit=prompt_id is not None)
        resolved_vars = tuple(variables) if variables is not None else declared_variables(template)
        spec = PromptSpec(
            prompt_id=candidate,
            label=label,
            template=template,
            variables=resolved_vars,
            created_seq=self.log.next_seq,
            locked=locked,
        )

        def apply(seq: int) -> None:
            spec.created_seq = seq
            self.prompts[candidate] = spec

        self._commit(
            "prompt.create",
            ORCHESTRATOR,
            {
                "prompt_id": candidate,
                "label": label,
                "template": template,
                "variables": list(resolved_vars),
                "locked": locked,
            },
            apply,
        )
        return spec

    def revise_prompt(
        self,
        prompt_id: str,
        template: str,
        variables: Optional[Sequence[str]] = None,
        lock: bool = False,
        loop_id: Optional[str] = None,
    ) -> PromptSpec:
        """Edit a prompt, keeping the superseded version as history.

        Host-only, for the same reason `create_prompt` is: no bound loop may
        call this. Refused if the prompt is already ``locked``. Pass
        ``lock=True`` to freeze the prompt as part of this revision.
        """
        if loop_id is not None:
            raise PromptViolation(
                "prompts are host-authored only; a bound loop cannot revise one",
                loop_id=loop_id,
            )
        spec = self.prompts.get(prompt_id)
        if spec is None:
            raise UnknownPrompt(f"no prompt {prompt_id!r}", prompt_id=prompt_id)
        if spec.locked:
            raise PromptViolation(
                f"prompt {prompt_id!r} is locked; it cannot be revised",
                prompt_id=prompt_id,
            )
        new_vars = tuple(variables) if variables is not None else declared_variables(template)
        prior_version, prior_template = spec.version, spec.template
        will_lock = bool(lock or spec.locked)

        def apply(seq: int) -> None:
            spec.history.append(
                PromptRevision(version=prior_version, template=prior_template, revised_seq=seq)
            )
            spec.template = template
            spec.variables = new_vars
            spec.version = prior_version + 1
            spec.locked = will_lock

        self._commit(
            "prompt.revise",
            ORCHESTRATOR,
            {
                "prompt_id": prompt_id,
                "template": template,
                "variables": list(new_vars),
                "version": prior_version + 1,
                "locked": will_lock,
            },
            apply,
        )
        return spec

    def render_prompt(
        self,
        prompt_id: str,
        bindings: Optional[dict[str, str]] = None,
        loop_id: Optional[str] = None,
    ) -> dict:
        """Materialize a prompt against variable bindings.

        Refused if a binding names a variable the prompt never declared — the
        prompt-layer equivalent of a `BudgetExceeded` write, catching a typo'd
        slot before it silently renders as nothing. A declared variable with
        no binding is not an error: it renders empty and comes back in
        ``unbound_variables`` so the caller can decide whether that is fine.
        """
        spec = self.prompts.get(prompt_id)
        if spec is None:
            raise UnknownPrompt(f"no prompt {prompt_id!r}", prompt_id=prompt_id)
        bindings = bindings or {}
        unknown = sorted(set(bindings) - set(spec.variables))
        if unknown:
            raise PromptViolation(
                f"prompt {prompt_id!r} does not declare variable(s) {unknown}",
                prompt_id=prompt_id,
                unknown_variables=unknown,
                declared_variables=list(spec.variables),
            )
        unbound = [v for v in spec.variables if v not in bindings]
        text = fill(spec.template, bindings)
        count = tok.count_tokens(text)
        payload: dict = {
            "prompt_id": prompt_id,
            "loop_id": loop_id,
            "version": spec.version,
            "tokens": count,
            "unbound_variables": unbound,
        }
        if self.log_content:
            payload["text"] = text
            payload["bindings"] = bindings
        else:
            payload["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._commit(
            "prompt.render", resolve_scope(self, loop_id).actor, payload,
            lambda seq: setattr(spec, "render_count", spec.render_count + 1),
        )
        return {
            "prompt_id": prompt_id,
            "version": spec.version,
            "text": text,
            "tokens": count,
            "unbound_variables": unbound,
        }

    # ------------------------------------------------------------------
    # harnesses — the harness layer
    # ------------------------------------------------------------------
    def create_harness(
        self,
        label: str,
        architecture: str = "solo",
        skills: Optional[Sequence[dict]] = None,
        strict_skills: bool = False,
        tool_grants: Sequence[str] = (),
        sandbox: str = "shared",
        iteration_budget: Optional[int] = None,
        requires_approval: Sequence[str] = (),
        harness_id: Optional[str] = None,
        loop_id: Optional[str] = None,
        verification_policy: Optional[str] = None,
        evidence_policy: str = "none",
    ) -> HarnessProfile:
        """Declare the environment, tools, and architecture a loop runs inside.

        Unlike prompts, a harness may be declared from inside a bound loop —
        a manager loop fanning out to helpers needs to be able to declare
        their harness. The hazard harnesses guard against is a maker
        approving its own work, which is enforced separately at `loop_tick`,
        not who is allowed to describe the environment.
        """
        if architecture not in ARCHITECTURES:
            raise ValueError(f"architecture must be one of {ARCHITECTURES}")
        if sandbox not in SANDBOXES:
            raise ValueError(f"sandbox must be one of {SANDBOXES}")
        if verification_policy is not None and verification_policy not in VERIFICATION_POLICIES:
            raise ValueError(f"verification_policy must be one of {VERIFICATION_POLICIES}")
        if evidence_policy not in EVIDENCE_POLICIES:
            raise ValueError(f"evidence_policy must be one of {EVIDENCE_POLICIES}")
        candidate = _dedupe_id(
            harness_id or slugify(label), self.harnesses, explicit=harness_id is not None
        )
        resolved_skills: dict[str, Skill] = {}
        for item in skills or ():
            name = item["name"]
            skill_id = item.get("skill_id") or slugify(name)
            resolved_skills[skill_id] = Skill(
                skill_id=skill_id,
                name=name,
                description=item.get("description", ""),
                verified=bool(item.get("verified", False)),
            )
        profile = HarnessProfile(
            harness_id=candidate,
            label=label,
            created_seq=self.log.next_seq,
            architecture=architecture,
            skills=resolved_skills,
            strict_skills=strict_skills,
            tool_grants=tuple(tool_grants),
            sandbox=sandbox,
            iteration_budget=iteration_budget,
            requires_approval=tuple(requires_approval),
            verification_policy=verification_policy,
            evidence_policy=evidence_policy,
        )
        self._commit(
            "harness.create",
            resolve_scope(self, loop_id).actor,
            {**profile.to_dict(), "loop_id": loop_id},
            lambda seq: self.harnesses.__setitem__(candidate, profile),
        )
        return profile

    def harness_call(
        self,
        harness_id: str,
        skill_id: str,
        loop_id: Optional[str] = None,
        action: Optional[str] = None,
        approved: Optional[bool] = None,
    ) -> dict:
        """Record a loop invoking a named skill under a harness profile.

        Refused if `skill_id` is not one of the harness's declared skills and
        the harness declares `strict_skills=True` — the harness-layer version
        of "a while-true wrapped around a stranger" becomes a structural
        refusal instead of a code smell. Refused if `action` names one of the
        harness's `requires_approval` patterns and `approved` is not `True`.

        An undeclared call under a *non*-strict harness is not refused, but it
        is counted and surfaced by `inspect_window`'s advisories — the same
        "logged, not silently allowed" treatment a bridge-less cross-region
        read gets. Every attempt is logged before it is judged, refused ones
        included — like `_deny`, a refusal here is an informative outcome
        recorded in the stream, not a silent early return.
        """
        harness = self.harnesses.get(harness_id)
        if harness is None:
            raise UnknownHarness(f"no harness {harness_id!r}", harness_id=harness_id)

        declared = skill_id in harness.skills
        # Glob, not equality. These are documented as "action patterns"
        # everywhere, so `deploy_*` has to be able to fire — and an exact-match
        # gate that a trailing space defeats is worse than no gate, because it
        # reads as protection in the profile and never triggers.
        gated = harness.approval_required_for(action)
        refused_reason: Optional[str] = None
        if not declared and harness.strict_skills:
            refused_reason = "undeclared_skill"
        if gated and approved is not True:
            refused_reason = refused_reason or "approval_required"

        def apply(seq: int) -> None:
            if not declared:
                harness.undeclared_calls += 1
            if gated:
                harness.approvals_required += 1
                if refused_reason is None:
                    harness.approvals_granted += 1
            if refused_reason is None:
                harness.calls += 1

        # Emitted for every attempt, refused ones included, and *before* the
        # refusal is raised — so replay reconstructs every counter from the log
        # alone even for a call that failed.
        self._commit(
            "harness.call",
            resolve_scope(self, loop_id).actor,
            {
                "harness_id": harness_id,
                "skill_id": skill_id,
                "loop_id": loop_id,
                "declared": declared,
                "action": action,
                "approved": approved,
                "gated": gated,
                "refused_reason": refused_reason,
            },
            apply,
        )

        if refused_reason == "undeclared_skill":
            raise HarnessViolation(
                f"harness {harness_id!r} declares strict_skills=True; "
                f"{skill_id!r} is not one of its declared skills",
                harness_id=harness_id,
                skill_id=skill_id,
                declared_skills=sorted(harness.skills),
                hint="call create_harness again with this skill added, or use a declared skill_id",
            )
        if refused_reason == "approval_required":
            raise HarnessViolation(
                f"action {action!r} requires human approval under harness {harness_id!r}",
                harness_id=harness_id,
                action=action,
                hint="call harness_call again with approved=True once a human has signed off",
            )

        return {
            "harness_id": harness_id,
            "skill_id": skill_id,
            "declared": declared,
            "gated": gated,
            "ledger": harness.to_dict()["ledger"],
        }

    # ------------------------------------------------------------------
    # criteria and evidence — the attestation layer
    # ------------------------------------------------------------------
    def pin_criterion(
        self,
        scw_id: str,
        criterion_id: Optional[str] = None,
        label: str = "",
        loop_id: Optional[str] = None,
    ) -> Criterion:
        """Freeze a region as an acceptance criterion, recording its signature.

        Host-only, unconditionally, on the same principle as `create_prompt`:
        a yardstick the graded party can pin, repin, or release is not a
        yardstick. Making the region read-only stops the *loop* editing it;
        pinning is what catches the *host* editing it mid-run, which is the
        quieter and commoner version of the same failure.
        """
        if loop_id is not None:
            raise CriterionViolation(
                "criteria are host-authored; a bound loop cannot pin the yardstick it is "
                "graded against",
                loop_id=loop_id,
                hint="call pin_criterion from the unbound host, before bind_scope",
            )
        region = self._open_region(scw_id)
        candidate = _dedupe_id(
            criterion_id or slugify(label or f"criterion-{scw_id}"),
            self.criteria,
            explicit=criterion_id is not None,
        )
        criterion = Criterion(
            criterion_id=candidate,
            scw_id=scw_id,
            label=label or region.label,
            signature=self.signature(scw_id),
            pinned_seq=self.log.next_seq,
            pinned_tick=self.tick,
        )
        self._commit(
            "criterion.pin", ORCHESTRATOR, {**criterion.to_dict(), "loop_id": None},
            lambda seq: self.criteria.__setitem__(candidate, criterion),
        )
        return criterion

    def repin_criterion(self, criterion_id: str, loop_id: Optional[str] = None) -> Criterion:
        """Accept the criterion's current bytes as the new yardstick.

        Deliberately not automatic. Re-pinning restarts comparability: rounds
        scored before it and after it are no longer measuring the same thing,
        and that fact belongs in the log as an explicit act rather than as a
        silent tolerance.
        """
        if loop_id is not None:
            raise CriterionViolation(
                "criteria are host-authored; a bound loop cannot repin its own yardstick",
                loop_id=loop_id,
            )
        criterion = self.criteria.get(criterion_id)
        if criterion is None:
            raise CriterionViolation(f"no criterion {criterion_id!r}", criterion_id=criterion_id)
        previous = criterion.signature
        current = self.signature(criterion.scw_id)

        def apply(seq: int) -> None:
            criterion.signature = current
            criterion.pinned_seq = seq
            criterion.pinned_tick = self.tick

        self._commit(
            "criterion.pin",
            ORCHESTRATOR,
            {
                **criterion.to_dict(),
                "signature": current,
                "pinned_tick": self.tick,
                "loop_id": None,
                "repinned_from": previous,
            },
            apply,
        )
        return criterion

    def unpin_criterion(self, criterion_id: str, loop_id: Optional[str] = None) -> dict:
        if loop_id is not None:
            raise CriterionViolation(
                "criteria are host-authored; a bound loop cannot release its own yardstick",
                loop_id=loop_id,
            )
        criterion = self.criteria.get(criterion_id)
        if criterion is None:
            raise CriterionViolation(f"no criterion {criterion_id!r}", criterion_id=criterion_id)
        self._commit(
            "criterion.unpin", ORCHESTRATOR, {"criterion_id": criterion_id},
            lambda seq: setattr(criterion, "status", "released"),
        )
        return criterion.to_dict()

    def attest_evidence(
        self,
        loop_id: str,
        kind: str = "command",
        command: Optional[str] = None,
        argv: Sequence[str] = (),
        exit_code: Optional[int] = None,
        output_sha256: Optional[str] = None,
        output_bytes: Optional[int] = None,
        artifact_sha256: Optional[str] = None,
        criterion_id: Optional[str] = None,
        score: Optional[float] = None,
        approver: Optional[str] = None,
        note: str = "",
    ) -> Attestation:
        """Record external evidence in support of a forthcoming verdict.

        The evidence is bound to ``loop_id`` and to the signature of that
        loop's region *right now*. A tick citing it re-checks both, so
        evidence cannot be borrowed from another loop, replayed across
        iterations, or claimed after the loop has rewritten the work the
        evidence described.

        This is an assertion by the caller, not an interception of a real
        command — see :mod:`scw_runtime.attest`.
        """
        loop = self.loops.get(loop_id)
        if loop is None or loop.status != "bound":
            raise UnknownLoop(
                f"no bound loop {loop_id!r} to attest for",
                loop_id=loop_id,
                hint="evidence is attributed to the loop that gathered it",
            )
        validate_kind(
            kind,
            command=command,
            exit_code=exit_code,
            artifact_sha256=artifact_sha256,
            criterion_id=criterion_id,
            approver=approver,
        )
        if criterion_id is not None and criterion_id not in self.criteria:
            raise CriterionViolation(f"no criterion {criterion_id!r}", criterion_id=criterion_id)
        attestation = Attestation(
            evidence_id=f"ev{self._evidence_seq + 1}",
            loop_id=loop_id,
            kind=kind,
            attested_seq=self.log.next_seq,
            attested_tick=self.tick,
            scope_signature=self.signature(loop.scw_id),
            command=command,
            argv=tuple(argv),
            exit_code=exit_code,
            output_sha256=output_sha256,
            output_bytes=output_bytes,
            artifact_sha256=artifact_sha256,
            criterion_id=criterion_id,
            score=score,
            approver=approver,
            note=note,
        )
        def apply(seq: int) -> None:
            self._evidence_seq += 1
            attestation.attested_seq = seq
            self.evidence[attestation.evidence_id] = attestation

        self._commit("evidence.attest", f"loop:{loop_id}", attestation.to_dict(), apply)
        return attestation

    def _consume_evidence(
        self, loop: Loop, evidence_id: Optional[str], level: Optional[int]
    ) -> Attestation:
        """Validate the attestation a verdict cites. Mutates nothing — the
        caller marks it consumed only once the tick is certain to proceed."""
        if evidence_id is None:
            raise AttestationViolation(
                f"loop {loop.loop_id!r} declares verification_level={level} and its harness "
                f"requires evidence, but the verdict cited none",
                loop_id=loop.loop_id,
                verification_level=level,
                hint="call attest_evidence(...) and pass its evidence_id to loop_tick",
            )
        attestation = self.evidence.get(evidence_id)
        if attestation is None:
            raise AttestationViolation(
                f"no evidence {evidence_id!r}", loop_id=loop.loop_id, evidence_id=evidence_id
            )
        if attestation.loop_id != loop.loop_id:
            raise AttestationViolation(
                f"evidence {evidence_id!r} was attested by {attestation.loop_id!r}, not by "
                f"{loop.loop_id!r}",
                loop_id=loop.loop_id,
                evidence_id=evidence_id,
                attested_by=attestation.loop_id,
            )
        if attestation.consumed:
            raise AttestationViolation(
                f"evidence {evidence_id!r} was already cited at tick "
                f"{attestation.consumed_by_tick}; one check, one iteration",
                loop_id=loop.loop_id,
                evidence_id=evidence_id,
                consumed_by_tick=attestation.consumed_by_tick,
            )
        if not attestation.passes():
            raise AttestationViolation(
                f"evidence {evidence_id!r} records exit_code={attestation.exit_code}, which is "
                f"not a pass; it cannot support verified=True",
                loop_id=loop.loop_id,
                evidence_id=evidence_id,
                exit_code=attestation.exit_code,
            )
        current = self.signature(loop.scw_id)
        if current != attestation.scope_signature:
            raise AttestationViolation(
                f"evidence {evidence_id!r} describes region {loop.scw_id!r} as it was when the "
                f"check ran; the loop has changed it since, so the evidence no longer describes "
                f"the work being graded",
                loop_id=loop.loop_id,
                evidence_id=evidence_id,
                attested_signature=attestation.scope_signature,
                current_signature=current,
                hint="re-run the check after the last edit, then attest again",
            )
        return attestation

    # ------------------------------------------------------------------
    # observation
    # ------------------------------------------------------------------
    def _visible_roots(self, visible: Optional[set[str]]) -> list[str]:
        """The maximal visible subtrees, in render order.

        A region is a root of the caller's view when it is visible and its
        parent is not — so a loop bound to a nested region gets that region as
        a top-level segment rather than its parent's wrapper, and never sees
        the wrapper's other children.
        """
        if visible is None:
            return self._ordered_children(None)
        roots = [
            scw_id
            for scw_id in self.regions
            if scw_id in visible
            and (self.regions[scw_id].parent_id is None
                 or self.regions[scw_id].parent_id not in visible)
        ]
        return sorted(
            roots, key=lambda i: (self.regions[i].order, self.regions[i].created_seq, i)
        )

    def _visible_costs(self, visible: Optional[set[str]]) -> list[RegionCost]:
        if visible is None:
            return self._costs()
        costs = []
        for scw_id in self._visible_roots(visible):
            text = self._render_region(scw_id, allowed=visible)
            costs.append(
                RegionCost(
                    scw_id=scw_id,
                    tokens=tok.count_tokens(text),
                    signature=hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
                    cache_hint=self.regions[scw_id].policy.cache,
                )
            )
        return costs

    def render(
        self, loop_id: Optional[str] = None, commit: bool = True, scope: str = "caller"
    ) -> dict:
        """Materialize the caller's view of the window as prompt text.

        **This is scope-true.** A bound loop gets only the regions in its read
        closure, with grant-reached subtrees pruned exactly as :meth:`read`
        prunes them. Previously this method performed no authorization at all
        and returned every region's bytes to any caller, which made the
        isolation model true of `read`/`write` and false of the runtime — a
        loop that could not read a sibling region could render the window and
        get it anyway. The partition is only worth something if the text
        actually sent to the model respects it.

        ``scope="window"`` asks for the whole window regardless of the caller,
        and is refused for a bound loop; it exists so a host can deliberately
        materialize everything for logging or debugging.

        Returns the text, one segment per visible top-level subtree with token
        offsets, and the cache breakpoint — the last region of the stable
        prefix, where a ``cache_control`` marker belongs.
        """
        if scope not in ("caller", "window"):
            raise ValueError("scope must be 'caller' or 'window'")
        scope_obj = resolve_scope(self, loop_id)
        if scope == "window" and loop_id is not None:
            reason = "a bound loop cannot render outside its own scope"
            self._deny("read", None, loop_id, reason, scope_obj.actor, scope_root=scope_obj.root)
            raise IsolationViolation(reason, loop_id=loop_id)
        if loop_id is None and self.strict_scope:
            reason = "strict_scope is on and render() was called with no loop_id"
            self._deny("read", None, None, reason, scope_obj.actor)
            raise IsolationViolation(reason, hint="pass loop_id, or build the window without strict_scope")

        visible: Optional[set[str]] = None
        if loop_id is not None and scope == "caller":
            visible = read_closure(self, loop_id)

        costs = self._visible_costs(visible)
        baseline = self._render_snapshots.get(loop_id, Snapshot())
        plan = compute_plan(costs, baseline)
        cacheable = set(plan.order[: plan.breakpoint_index])
        segments = []
        parts = []
        offset = 0
        for cost in costs:
            if visible is None:
                text, count = self.footprint(cost.scw_id)
            else:
                text = self._render_region(cost.scw_id, allowed=visible)
                count = cost.tokens
            region = self.regions[cost.scw_id]
            parts.append(text)
            segments.append(
                {
                    "scw_id": cost.scw_id,
                    "label": region.label,
                    "region_type": region.region_type,
                    "mutability": region.policy.mutability,
                    "token_start": offset,
                    "token_end": offset + count,
                    "tokens": count,
                    "cacheable": cost.scw_id in cacheable,
                }
            )
            offset += count
        elided = (
            sorted(set(self.regions) - visible) if visible is not None else []
        )
        self.log.emit(
            "window.render",
            scope_obj.actor,
            {
                "loop_id": loop_id,
                "tokens": plan.total_tokens,
                "segments": [s["scw_id"] for s in segments],
                "region_tokens": self._region_tokens(),
                "cache": plan.to_dict(),
                "committed": commit,
                "scope": scope,
                "elided": elided,
            },
        )
        if commit:
            # Baselines are per-caller: two loops rendering their own views
            # must not price each other's iterations.
            self._render_snapshots[loop_id] = Snapshot(
                order=[c.scw_id for c in costs],
                signatures={c.scw_id: c.signature for c in costs},
            )
        return {
            "text": "\n".join(parts),
            "tokens": plan.total_tokens,
            "segments": segments,
            "cache_breakpoint_after": plan.breakpoint_scw_id,
            "cache": plan.to_dict(),
            "elided": elided,
        }

    def advisories(self) -> list[dict]:
        """Actionable findings about layout, budgets, and standing grants."""
        costs = self._costs()
        out = ordering_advisories(costs, self._tick_snapshot)

        for region in self.regions.values():
            budget = region.policy.token_budget
            if budget and region.lifecycle == "open":
                used = region.own_tokens
                if used >= budget * 0.9:
                    out.append(
                        {
                            "code": "budget.pressure",
                            "severity": "warn",
                            "scw_id": region.scw_id,
                            "message": (
                                f"{region.scw_id!r} is at {used}/{budget} tokens; eviction policy "
                                f"{region.policy.eviction!r} will start dropping content"
                            ),
                            "remedy": "raise token_budget, promote content to a durable region, or compress",
                        }
                    )

        if self.total_budget:
            used = sum(c.tokens for c in costs)
            if used >= self.total_budget * 0.9:
                out.append(
                    {
                        "code": "window.pressure",
                        "severity": "error" if used >= self.total_budget else "warn",
                        "scw_id": None,
                        "message": f"window is at {used}/{self.total_budget} tokens",
                        "remedy": "close a region, tighten a budget, or move reference material behind retrieval",
                    }
                )

        # --- the declaration held to account -------------------------------
        # A declared verification level is a claim. These checks compare the
        # claim against what the loop actually did, which is the difference
        # between a taxonomy and a contract.
        for loop in self.loops.values():
            if loop.iteration == 0:
                continue
            level, zone = loop.verification_level, loop.verification_zone
            if level is None:
                out.append(
                    {
                        "code": "verification.undeclared",
                        "severity": "info",
                        "scw_id": loop.scw_id,
                        "message": f"loop {loop.loop_id!r} ran {loop.iteration} iterations without "
                        f"declaring a verification level",
                        "remedy": "pass verification_level=1..5 to bind_scope so the claim is on record",
                    }
                )
            elif zone == "autonomous" and loop.accepted == 0 and loop.rejected == 0:
                out.append(
                    {
                        "code": "verification.overclaimed",
                        "severity": "error",
                        "scw_id": loop.scw_id,
                        "message": (
                            f"loop {loop.loop_id!r} declares level {level} (autonomous zone) but "
                            f"supplied no verdict in {loop.iteration} iterations — it is unverified, "
                            f"not autonomous"
                        ),
                        "remedy": "pass verified=True/False to loop_tick, or declare the level you truly sit at",
                    }
                )
            if level is not None and level >= 4 and loop.self_approved > 0:
                out.append(
                    {
                        "code": "verification.self_approving",
                        "severity": "error",
                        "scw_id": loop.scw_id,
                        "message": (
                            f"loop {loop.loop_id!r} judged its own work at level {level} on "
                            f"{loop.self_approved} of {loop.iteration} iterations; maker and checker "
                            f"share a scope"
                        ),
                        "remedy": "bind a second loop to a separate region and pass verified_by=<that loop>",
                    }
                )
            if loop.unverified_streak >= 3 and loop.status == "bound":
                out.append(
                    {
                        "code": "loop.stalled",
                        "severity": "warn",
                        "scw_id": loop.scw_id,
                        "message": f"loop {loop.loop_id!r} has gone {loop.unverified_streak} iterations "
                        f"without a passing check",
                        "remedy": "stop on stagnation: unbind with terminal_state='stalled' rather than burning budget",
                    }
                )
            if loop.status == "unbound" and loop.terminal_state is None:
                out.append(
                    {
                        "code": "loop.unnamed_terminal",
                        "severity": "warn",
                        "scw_id": loop.scw_id,
                        "message": f"loop {loop.loop_id!r} was released without naming a terminal state",
                        "remedy": "unbind_scope(terminal_state='success'|'no_op'|'blocked'|'stalled'|'exhausted')",
                    }
                )

        # --- cross-layer checks: prompt and harness declarations held to the
        # same account as the verification declaration above. Unlike the
        # block above, these do not wait for a first iteration: a prompt can
        # drift, or a judge go unhardened, the moment it is declared. ---
        for loop in self.loops.values():
            if loop.status == "bound" and loop.prompt_id is not None:
                prompt = self.prompts.get(loop.prompt_id)
                if prompt is not None and prompt.version != loop.prompt_version_at_bind:
                    out.append(
                        {
                            "code": "prompt.version_drift",
                            "severity": "warn",
                            "scw_id": loop.scw_id,
                            "message": (
                                f"loop {loop.loop_id!r} bound to prompt {loop.prompt_id!r} at version "
                                f"{loop.prompt_version_at_bind}, which is now version {prompt.version} — "
                                f"iterations are no longer being scored against the same instruction"
                            ),
                            "remedy": "unbind_scope and rebind with the new prompt version, or avoid revising "
                            "a prompt that a loop is still bound to",
                        }
                    )
            level = loop.verification_level
            if level is not None and level >= 4:
                harness = self.harnesses.get(loop.harness_id) if loop.harness_id else None
                if harness is None or harness.architecture == "solo":
                    out.append(
                        {
                            "code": "harness.judge_unhardened",
                            "severity": "warn",
                            "scw_id": loop.scw_id,
                            "message": (
                                f"loop {loop.loop_id!r} declares verification_level={level} (a model "
                                f"judge) but its harness is "
                                + (f"architecture={harness.architecture!r}" if harness else "undeclared")
                                + " rather than 'maker_checker'"
                            ),
                            "remedy": "bind_scope(..., harness_id=<a harness with architecture='maker_checker'>) "
                            "so a self-approval is refused rather than merely flagged",
                        }
                    )

        # A maker whose declared exposure covers everything it can write has
        # satisfied R4 by declaring the test away. The rule still holds
        # formally; it has stopped meaning anything, and that is worth saying
        # out loud rather than leaving as a silent pass.
        for loop in self.loops.values():
            if loop.status != "bound" or not loop.exposes:
                continue
            writes = write_closure(self, loop.loop_id)
            if writes and writes <= set(loop.exposes):
                out.append(
                    {
                        "code": "partition.vacuous_exposure",
                        "severity": "warn",
                        "scw_id": loop.scw_id,
                        "message": (
                            f"loop {loop.loop_id!r} exposes {sorted(loop.exposes)}, which covers "
                            f"its entire write closure {sorted(writes)} — a judge of this loop "
                            f"can see everything it wrote, so the disjointness rule passes "
                            f"without constraining anything"
                        ),
                        "remedy": "expose only the artifact region the judge needs to grade, "
                        "not the region the work was reasoned in",
                    }
                )

        for bridge in self.bridges.values():
            if bridge.status == "open" and bridge.ttl_ticks is None and bridge.mode != "read":
                out.append(
                    {
                        "code": "bridge.unbounded",
                        "severity": "warn",
                        "scw_id": bridge.to_scw_id,
                        "message": (
                            f"{bridge.bridge_id} grants {bridge.mode!r} from {bridge.from_scw_id!r} "
                            f"to {bridge.to_scw_id!r} with no TTL"
                        ),
                        "remedy": "pass ttl_ticks so the grant expires with the iteration that needed it",
                    }
                )

        for harness in self.harnesses.values():
            if harness.undeclared_calls:
                out.append(
                    {
                        "code": "harness.undeclared_calls",
                        "severity": "warn",
                        "scw_id": None,
                        "message": (
                            f"harness {harness.harness_id!r} recorded {harness.undeclared_calls} call(s) "
                            f"to skills it never declared"
                        ),
                        "remedy": "add the skill to create_harness, or turn on strict_skills to refuse "
                        "undeclared calls instead of merely counting them",
                    }
                )

        for region in self.regions.values():
            if region.lifecycle != "open" or not region.entries:
                continue
            if region.last_read_seq < 0 and region.region_type in ("reference", "durable"):
                _, count = self.footprint(region.scw_id)
                if count >= 200:
                    out.append(
                        {
                            "code": "region.unread",
                            "severity": "info",
                            "scw_id": region.scw_id,
                            "message": f"{region.scw_id!r} carries {count} tokens that no scope has read",
                            "remedy": "drop it from the window or move it behind retrieval",
                        }
                    )
        return out

    def region_map(
        self, include_content: bool = False, visible: Optional[set[str]] = None
    ) -> list[dict]:
        """Flat, ordered description of every region — what the inspector draws.

        ``visible``, when given, restricts which regions have their *content*
        returned. Structure, sizes and policies stay in the map so an operator
        can still see the shape of the window; only bytes are withheld.
        """
        occupied = self._bound_region_ids()
        out: list[dict] = []

        def walk(scw_id: str) -> None:
            region = self.regions[scw_id]
            _, subtree_tokens = self.footprint(scw_id)
            if region.lifecycle != "open":
                activity = region.lifecycle
            elif scw_id in occupied or region.last_mutation_seq > self.iteration_boundary_seq:
                activity = "active"
            else:
                activity = "idle"
            in_view = visible is None or scw_id in visible
            entry = region.to_dict(include_content=include_content and in_view)
            entry.update(
                {
                    "depth": self._depth(scw_id),
                    "subtree_tokens": subtree_tokens,
                    "activity": activity,
                    "occupants": self._occupants(scw_id),
                    "signature": self.signature(scw_id),
                    "visible": in_view,
                }
            )
            out.append(entry)
            for child in self._ordered_children(scw_id):
                walk(child)

        for root in self._ordered_children(None):
            walk(root)
        return out

    def inspect(self, include_content: bool = False, loop_id: Optional[str] = None) -> dict:
        """Full state: regions, loops, bridges, next-tick cache plan, advisories.

        ``include_content=True`` returns region bytes, so it is scope-filtered
        the same way :meth:`render` is: with ``loop_id`` set, only regions in
        that loop's read closure carry content. Without it, this is a host
        call, and ``strict_scope`` refuses it — previously
        ``inspect(include_content=True)`` was an unauthenticated full-window
        read available over MCP with no loop identity at all.
        """
        if include_content and loop_id is None and self.strict_scope:
            reason = "strict_scope is on and inspect(include_content=True) supplied no loop_id"
            self._deny("read", None, None, reason, ORCHESTRATOR)
            raise IsolationViolation(reason, hint="pass loop_id to scope the content")
        visible = read_closure(self, loop_id) if loop_id is not None else None
        costs = self._costs()
        plan = compute_plan(costs, self._tick_snapshot)
        used = plan.total_tokens
        return {
            "window": {
                "name": self.name,
                "run_id": self.log.run_id,
                "total_budget": self.total_budget,
                "used_tokens": used,
                "utilization": round(used / self.total_budget, 4) if self.total_budget else None,
                "tokenizer": tok.tokenizer_name(),
                "tick": self.tick,
                "total_iterations": self.total_iterations,
                "strict_scope": self.strict_scope,
                "host_only_bridges": self.host_only_bridges,
                "require_bounded_loops": self.require_bounded_loops,
                "max_total_iterations": self.max_total_iterations,
                "max_loop_depth": self.max_loop_depth,
                "event_count": self.log.next_seq,
                "region_count": len(self.regions),
                "viewer": loop_id,
            },
            "regions": self.region_map(include_content=include_content, visible=visible),
            "loops": [loop.to_dict() for loop in self.loops.values()],
            "loop_tree": self.loop_tree(),
            "bridges": [b.to_dict() for b in self.bridges.values()],
            "prompts": [p.to_dict() for p in self.prompts.values()],
            "harnesses": [h.to_dict() for h in self.harnesses.values()],
            "criteria": [c.to_dict() for c in self.criteria.values()],
            "evidence": [e.to_dict() for e in self.evidence.values()],
            "cache": plan.to_dict(),
            "advisories": self.advisories(),
        }

    def loop_tree(self) -> list[dict]:
        """Depth-annotated control-flow tree of every loop, roots first."""
        out: list[dict] = []

        def walk(loop_id: str) -> None:
            loop = self.loops[loop_id]
            out.append(
                {
                    "loop_id": loop_id,
                    "parent_loop_id": loop.parent_loop_id,
                    "depth": loop.depth,
                    "scw_id": loop.scw_id,
                    "status": loop.status,
                    "iteration": loop.iteration,
                    "max_iterations": loop.max_iterations,
                    "multiplicative_ceiling": self._multiplicative_ceiling(loop_id),
                }
            )
            for child in loop.child_loop_ids:
                if child in self.loops:
                    walk(child)

        for loop_id, loop in self.loops.items():
            if loop.parent_loop_id is None:
                walk(loop_id)
        return out

    def _multiplicative_ceiling(self, loop_id: str) -> Optional[int]:
        """The worst-case iterations this loop can cost, counting its ancestors.

        Nested loops multiply rather than add: a parent capped at 10 running a
        child capped at 10 is a hundred iterations, not twenty. A ceiling that
        does not account for nesting is not a ceiling.
        """
        chain = loop_ancestors(self, loop_id) + [loop_id]
        product = 1
        for link in chain:
            loop = self.loops.get(link)
            if loop is None or loop.max_iterations is None:
                return None
            product *= loop.max_iterations
        return product

    def _cache_impact(self, scw_id: str) -> dict:
        """How much cacheable prefix a write to ``scw_id`` just invalidated."""
        costs = self._costs()
        index = next((i for i, c in enumerate(costs) if c.scw_id == scw_id), None)
        if index is None:
            # A nested region: attribute the impact to its top-level ancestor.
            ancestor = scw_id
            while self.regions[ancestor].parent_id is not None:
                ancestor = self.regions[ancestor].parent_id
            index = next((i for i, c in enumerate(costs) if c.scw_id == ancestor), None)
            if index is None:
                return {"invalidated_tokens": 0, "position": None, "of": len(costs)}
        signatures = self._tick_snapshot.signatures
        blocked = 0
        for cost in costs[index + 1:]:
            if self.regions[cost.scw_id].policy.cache == "never":
                continue
            if signatures.get(cost.scw_id) == cost.signature:
                blocked += cost.tokens
        return {
            "invalidated_tokens": blocked,
            "position": index,
            "of": len(costs),
            "note": (
                "tokens behind this region that were cacheable and must now be re-processed"
                if blocked
                else "this region renders after every stable region; no cached prefix was lost"
            ),
        }
