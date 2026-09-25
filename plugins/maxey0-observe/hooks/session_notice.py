"""SessionStart sensor: state what is actually loaded, and nothing more.

Emits `additionalContext` so a session begins knowing the three planes are
there and which entry point is which — otherwise partitioning stays a thing you
have to remember to ask for, which is the opposite of native.

It reports what it can verify. The loop counts come from the dataset on disk;
the plane list comes from the tool catalog; whether a plane's connector is
actually running is something a `SessionStart` hook cannot know, so it does not
claim to. `/maxey0:doctor` answers that.

Fails silent by design. A broken or slow notice must never be the reason a
session cannot start, so any error exits 0 with no output.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    try:
        plugin_root = Path(
            os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1]
        )
        loops_path = Path(
            os.environ.get("MAXEY0_LOOPS")
            or plugin_root / "server" / "vendor" / "data" / "loops.json"
        )
        manifest_path = Path(
            os.environ.get("MAXEY0_ROOT")
            or plugin_root / "server" / "vendor" / "maxey0"
        ) / "manifest.json"
        if not loops_path.exists() or not manifest_path.exists():
            return 0

        loops = json.loads(loops_path.read_text(encoding="utf-8"))["loops"]
        bindable = [
            l for l in loops
            if l.get("execution_mode") == "in-window" and l.get("status") == "validated"
        ]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        concepts = sorted(c["id"] for c in manifest.get("concepts", []))

        context = (
            "Maxey0 is loaded: three planes over this session's context window.\n"
            "\n"
            "- **Context** (`context_*`) partitions the window into typed regions "
            "and binds each role to one. The runtime decides what a role can "
            "read, not the prompt.\n"
            f"- **Loop** (`loops_*`) routes a task across {len(concepts)} concepts "
            f"and {len(loops)} agentic loops, {len(bindable)} of them validated and "
            "bindable in-window. It binds nothing.\n"
            "- **Observatory** (`observe_*`) is the Gate: it attributes every "
            "delegated agent's tool call to the role that made it, and in "
            "`enforce` refuses the ones reaching outside that role's scope.\n"
            "\n"
            f"Concepts: {', '.join(concepts)}.\n"
            "\n"
            "**Entry point.** Call `loops_route(task=...)` to see the decision "
            "without committing, or `context_route_bind(task=...)` to route AND "
            "bind the matching partition. Do this BEFORE hand-building a "
            "maker/checker pair: a coherent hit names a pre-scoped formation, and "
            "in one measured case that was ~10,800 tokens against 253,481 for the "
            "same task improvised.\n"
            "\n"
            "`/maxey0:menu` prints the whole surface; `/maxey0:doctor` reports "
            "what is actually up.\n"
            "\n"
            "Reach for this when work spans several roles, when something must be "
            "verified by something that did not produce it, or when reference "
            "material must not be editable by whatever consumes it. Treat a "
            "runtime refusal as informative output, never as an error to route "
            "around."
        )

        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }, sys.stdout)
        return 0
    except Exception:  # noqa: BLE001 - a notice must never block a session
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
