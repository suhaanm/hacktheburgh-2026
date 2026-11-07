"""python -m understudy_engine.evidence schema | eval [--fast]"""
from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "eval"
    if cmd == "schema":
        from .packet import write_schema

        print(write_schema())
        return 0
    if cmd == "eval":
        from .evaluate import evaluate_evidence

        print(json.dumps(evaluate_evidence(fast="--fast" in argv), indent=2))
        return 0
    print("usage: python -m understudy_engine.evidence schema | eval [--fast]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
