"""Seed the Privacy screen for the offline demo: genuine ``egress.send`` calls with a test port, marked mock.

``python -m understudy_engine.privacy.demo [--reset] [--canary]`` (or ``demo.seed()`` from the demo seeder) runs the privacy
layer's reference flows on fixtures WITHOUT planted tokens through a capturing port, so the ledger has real lines made by the
real guard code (bucketed payloads, schema ids, byte counts) and every one is labelled mock: nothing reached a model. With
``--canary`` it also runs the evaluation and records its aggregate, so the screen's canary figures are filled in.
Nothing is invented: no ledger line is written except by ``egress.send``.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import ledger
from .evaluate import _brief_fixture, _brief_run, _cal_fixture, _cal_run, _digest_fixture, _digest_run, _git_fixture, _git_run, evaluate_privacy
from .testing import CapturingPort


def seed(*, reset: bool = False, canary: bool = False, rounds: int = 2) -> dict[str, Any]:
    """Write demo ledger lines (all mock). Returns ``{lines, canary}``."""
    if reset:
        ledger.reset_all()
    port = CapturingPort()
    before = ledger.count()
    for _ in range(max(1, rounds)):
        for fixture, run in ((_cal_fixture, _cal_run), (_git_fixture, _git_run), (_brief_fixture, _brief_run), (_digest_fixture, _digest_run)):
            run(fixture(), port)
    out: dict[str, Any] = {"lines": ledger.count() - before, "canary": None}
    if canary:
        rep = evaluate_privacy(seeds=range(4), record=True)
        out["canary"] = {k: rep["headline"][k] for k in ("planted", "leaked", "flows", "requests")}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.privacy.demo")
    ap.add_argument("--reset", action="store_true", help="delete the existing ledger first (no trace)")
    ap.add_argument("--canary", action="store_true", help="also run the evaluation and record its aggregate")
    a = ap.parse_args(argv)
    print(json.dumps(seed(reset=a.reset, canary=a.canary)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
