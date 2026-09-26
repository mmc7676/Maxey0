"""Verify Maxey0 evidence files offline: attestations, the Gate journal, the ledger.

A thin wrapper over ``maxey0_ss/containment/verify_cli.py`` (installed as the
``maxey0-verify`` console script). The module is loaded by file path rather
than imported as a package, so running this from a checkout neither needs an
install nor executes ``maxey0_ss/__init__`` -- the verifier stays stdlib-only
and independent of the code that produced the evidence.

    python scripts/verify_records.py attestation export.json --key-file key.hex
    python scripts/verify_records.py gate ~/.scw/gate.jsonl
    python scripts/verify_records.py ledger ~/.scw/events.jsonl --strict-runs
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "maxey0_ss" / "containment" / "verify_cli.py"


def _load():
    spec = importlib.util.spec_from_file_location("maxey0_verify_cli", _MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    sys.exit(_load().main())
