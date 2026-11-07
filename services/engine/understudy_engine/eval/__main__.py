"""CLI: ``python -m understudy_engine.eval [--out evals/report.json] [--sections a,b,c] [--fast]``.

Exit codes: 0 report written; 2 written but at least one section failed (a bug in an owner's code, shown as ``failed``);
3 the report did not validate against report.schema.json (not written unless --force).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters import SECTION_NAMES
from .assemble import build_report, default_out, dumps, write_atomic
from .render_md import render
from .schema import errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.eval", description="Write evals/report.json and evals/report.md")
    ap.add_argument("--out", default=None, help="report path (default: evals/report.json); the markdown goes beside it as .md")
    ap.add_argument("--sections", default=None, help=f"comma-separated subset of: {', '.join(SECTION_NAMES)}, limitations")
    ap.add_argument("--fast", action="store_true", help="fewer bootstrap resamples (CI and dev); the default is the full run")
    ap.add_argument("--seed", type=int, default=0, help="base seed handed to the owners' evaluators (default 0)")
    ap.add_argument("--data", default=None, help="data root (default: UNDERSTUDY_DATA_DIR or <repo>/data)")
    ap.add_argument("--no-generate", action="store_true", help="do not regenerate missing synthetic data; the sections become pending")
    ap.add_argument("--no-md", action="store_true", help="skip report.md")
    ap.add_argument("--force", action="store_true", help="write even if the report fails schema validation")
    args = ap.parse_args(argv)

    sections = [s.strip() for s in args.sections.split(",") if s.strip()] if args.sections else None
    try:
        report = build_report(fast=args.fast, sections=sections, root=args.data, seed=args.seed, regenerate=not args.no_generate)
    except ValueError as e:
        print(f"eval: {e}", file=sys.stderr)
        return 2
    errs = errors(report)
    out = Path(args.out) if args.out else default_out()
    if errs and not args.force:
        print("eval: report does not match report.schema.json; nothing written (use --force to write anyway):", file=sys.stderr)
        for e in errs[:30]:
            print("  " + e, file=sys.stderr)
        return 3
    if errs:
        print(f"eval: WARNING {len(errs)} schema error(s); written because of --force", file=sys.stderr)
    write_atomic(out, dumps(report))
    if not args.no_md:
        write_atomic(out.with_suffix(".md"), render(report))
    secs = report["sections"]
    status = {k: (v.get("status", "ok") if isinstance(v, dict) else "ok") for k, v in secs.items() if k != "limitations"}
    bad = [k for k, v in status.items() if v == "failed"]
    print(f"eval: wrote {out} ({report['run']['seconds_total']}s, {'fast' if args.fast else 'full'}; mock={report['mock']}); "
          f"{sum(v == 'ok' for v in status.values())} ok, {sum(v == 'pending' for v in status.values())} pending, "
          f"{sum(v == 'not_run' for v in status.values())} not run, {len(bad)} failed; {len(secs.get('limitations', []))} limitations")
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
