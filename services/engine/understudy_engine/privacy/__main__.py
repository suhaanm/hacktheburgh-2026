"""``python -m understudy_engine.privacy [--out FILE] [--seeds N]``: run the privacy evaluation and print the headline.

Offline, no model, no network; uses a temporary data directory. ``--record`` also writes the aggregate canary result to the
real data dir for ``GET /privacy/summary``.
"""
from __future__ import annotations

import argparse
import json
import sys

from .evaluate import evaluate_privacy


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.privacy")
    ap.add_argument("--out", help="write the full report JSON here")
    ap.add_argument("--seeds", type=int, default=8, help="seeds per flow (default 8)")
    ap.add_argument("--record", action="store_true", help="record the canary aggregate for /privacy/summary")
    a = ap.parse_args(argv)
    rep = evaluate_privacy(seeds=range(a.seeds), record=a.record)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1)
    h = rep["headline"]
    print(json.dumps(h, indent=1))
    for c in rep["negative_controls"] + rep["image"]["controls"]:
        print(("ok   " if c["passed"] else "FAIL ") + c["name"])
    img = rep["image"]
    ok = h["leaked"] == 0 and h["artifact_leaked"] == 0 and h["ledger_complete"] and h["controls_passed"] == h["controls_total"] \
        and h["bucketing_failures"] == 0 and h["static_guard_violations"] == 0 and img["leaks"] == 0 \
        and all(c["passed"] for c in img["controls"]) and img["gate"]["failures"] == 0 \
        and not img["static_guard"]["provider_endpoint_violations"] and not img["static_guard"]["sandbox_claim_violations"]
    print("PRIVACY EVALUATION:", "clean" if ok else "NOT CLEAN (see the report)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
