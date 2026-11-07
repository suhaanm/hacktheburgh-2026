"""``python -m understudy_engine.calendar synth [--canary] | evaluate [--fast] | week PERSON``."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="understudy_engine.calendar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synth", help="write the synthetic calendars (deterministic) under data/synthetic/calendars")
    s.add_argument("--canary", action="store_true", help="write the canary-seeded variants instead")
    s.add_argument("--out", help="data root (default: UNDERSTUDY_DATA_DIR or <repo>/data)")
    e = sub.add_parser("evaluate", help="run the calendar evaluation and print it as JSON")
    e.add_argument("--fast", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "synth":
        from . import synth
        print(json.dumps(synth.generate(args.out, canary=args.canary)))
        return 0
    from .evaluate import evaluate_calendar
    print(json.dumps(evaluate_calendar(fast=args.fast), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
