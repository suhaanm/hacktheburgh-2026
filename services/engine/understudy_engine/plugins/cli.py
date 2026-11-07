"""``python -m understudy_engine.plugins validate`` and ``understudy plugin validate`` (PLG-1).

Exit code 0 when every manifest validates, 1 otherwise, 2 for a usage error. Output lists ids, enabled state and problems;
it never prints anything read from a source.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import validate_paths


def validate_command(paths: list[str] | None = None, quiet: bool = False) -> int:
    results = validate_paths([Path(p) for p in paths] if paths else None)
    bad = 0
    for r in results:
        if r.ok:
            if not quiet:
                state = "on" if r.enabled else "off by default"
                print(f"ok    {r.id:<14} {state:<15} {r.path}")
        else:
            bad += 1
            print(f"FAIL  {r.id or '?':<14} {r.path}")
            for p in r.problems:
                print(f"        {p}")
    print(f"{len(results) - bad} of {len(results)} plugin manifests valid")
    return 1 if bad or not results else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="understudy_engine.plugins", description="Source plugin tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate plugin manifests (default: every bundled and registered one)")
    v.add_argument("paths", nargs="*", help="plugin.yaml files or directories")
    v.add_argument("--quiet", action="store_true")
    sub.add_parser("list", help="list discoverable plugins")
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return validate_command(args.paths, args.quiet)
    from .loader import discover, is_enabled
    for pid, m in sorted(discover().items()):
        print(f"{pid:<14} {m.kind:<7} {'on' if is_enabled(m) else 'off':<4} {m.schema or '-':<18} {m.description}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
