"""Structured Context Windows — an addressable context runtime for loop engineering.

A context window is treated as an addressable runtime with regions rather than
a flat token buffer. Partition it into typed regions, bind a loop's execution
scope to one of them, and the boundaries between regions become enforceable
instead of conventional.

    from scw_runtime import ContextWindow

    w = ContextWindow(total_budget=32_000)
    spec = w.create_scw("Task spec", "reference")
    notes = w.create_scw("Findings", "episodic")
    pad = w.create_scw("Scratchpad", "scratchpad")

    w.write(spec.scw_id, "Summarize the incident reports.")
    w.bind_scope("refine", pad.scw_id, max_iterations=5)

    w.write(pad.scw_id, "draft 1", loop_id="refine")
    w.read(notes.scw_id, loop_id="refine")     # IsolationViolation: no bridge
    w.loop_tick("refine")                       # prices the iteration, clears the pad

The MCP server lives in :mod:`scw_runtime.server`; the inspector reads the
event log this runtime emits.
"""

from .attest import Attestation, Criterion
from .cache import CachePlan, Snapshot
from .errors import (
    AttestationViolation,
    BudgetExceeded,
    ChainBroken,
    CriterionViolation,
    DisjointnessViolation,
    HarnessViolation,
    IsolationViolation,
    LoopExhausted,
    NestingViolation,
    PolicyViolation,
    PromptViolation,
    RegionClosed,
    SCWError,
    UnknownBridge,
    UnknownHarness,
    UnknownLoop,
    UnknownPrompt,
    UnknownRegion,
)
from .events import EventLog, iter_records, verify_records
from .harness import HarnessProfile, Skill
from .model import Bridge, Entry, Loop, Policy, Region, preset_for
from .partition import disjointness, read_closure, write_closure
from .prompt import PromptRevision, PromptSpec
from .replay import replay, replay_file, replay_prefix, split_runs
from .window import ContextWindow

__version__ = "0.3.1"

__all__ = [
    "ContextWindow",
    "Policy",
    "Region",
    "Entry",
    "Loop",
    "Bridge",
    "preset_for",
    "PromptSpec",
    "PromptRevision",
    "HarnessProfile",
    "Skill",
    "Criterion",
    "Attestation",
    "read_closure",
    "write_closure",
    "disjointness",
    "EventLog",
    "iter_records",
    "verify_records",
    "replay",
    "replay_file",
    "replay_prefix",
    "split_runs",
    "CachePlan",
    "Snapshot",
    "SCWError",
    "IsolationViolation",
    "PolicyViolation",
    "BudgetExceeded",
    "RegionClosed",
    "LoopExhausted",
    "PromptViolation",
    "HarnessViolation",
    "DisjointnessViolation",
    "CriterionViolation",
    "AttestationViolation",
    "NestingViolation",
    "UnknownRegion",
    "UnknownLoop",
    "UnknownBridge",
    "UnknownPrompt",
    "UnknownHarness",
    "ChainBroken",
    "__version__",
]
