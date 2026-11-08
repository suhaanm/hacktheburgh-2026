"""CLI: ``python -m understudy_engine.eval [--out evals/report.json] [--sections a,b,c] [--fast]``.

Exit codes: 0 report written; 2 written but at least one section failed (a bug in an owner's code, shown as ``failed``);
3 the report did not validate against report.schema.json (not written unless --force).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import SECTION_NAMES
from .assemble import build_report, default_out, dumps, merge_report, write_atomic
from .facts import build_facts
from .fixture import dumps_min, trim
from .render_md import render
from .schema import errors
from .wording import reword_tree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.eval", description="Write evals/report.json and evals/report.md")
    ap.add_argument("--out", default=None, help="report path (default: evals/report.json); the markdown goes beside it as .md")
    ap.add_argument("--sections", default=None, help=f"comma-separated subset of: {', '.join(SECTION_NAMES)}, limitations")
    ap.add_argument("--only", default=None, help="comma-separated sections to run; with --merge, only these are re-run and merged into the existing report")
    ap.add_argument("--merge", action="store_true", help="merge the --only sections into the existing report (--out, default evals/report.json) and re-assemble the limitations register, "
                                                         "findings, evidence map, markdown, facts and fixture from the merged sections (about a minute; no full run)")
    ap.add_argument("--reword", action="store_true", help="re-emit the existing report (--out) in the app's wording (D57) and regenerate the markdown, facts and --fixture from it: "
                                                          "no section is run, no number changes (a second)")
    ap.add_argument("--fast", action="store_true", help="fewer bootstrap resamples (CI and dev); the default is the full run")
    ap.add_argument("--seed", type=int, default=0, help="base seed handed to the owners' evaluators (default 0)")
    ap.add_argument("--data", default=None, help="data root (default: UNDERSTUDY_DATA_DIR or <repo>/data)")
    ap.add_argument("--no-generate", action="store_true", help="do not regenerate missing data; the sections become pending")
    ap.add_argument("--no-md", action="store_true", help="skip report.md")
    ap.add_argument("--fixture", default=None, help="also write a trimmed copy for the dashboard fixture to PATH (for example apps/dashboard/src/fixtures/eval-report.json)")
    ap.add_argument("--no-facts", action="store_true", help="skip report.facts.json (the headline counts docs quote by key)")
    ap.add_argument("--force", action="store_true", help="write even if the report fails schema validation")
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else default_out()
    pick = args.only or args.sections
    sections = [s.strip() for s in pick.split(",") if s.strip()] if pick else None
    try:
        if args.reword:
            try:
                base = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"eval: --reword needs an existing report at {out} ({type(e).__name__})", file=sys.stderr)
                return 2
            report = reword_tree(base)
            errs = errors(report)
            if errs and not args.force:
                print("eval: reworded report does not match report.schema.json; nothing written:", file=sys.stderr)
                for e in errs[:30]:
                    print("  " + e, file=sys.stderr)
                return 3
            write_atomic(out, dumps(report))
            if not args.no_md:
                write_atomic(out.with_suffix(".md"), render(report))
            if not args.no_facts:
                write_atomic(out.with_suffix(".facts.json"), dumps(build_facts(report)))
            if args.fixture:
                write_atomic(Path(args.fixture), dumps_min(trim(report)))
            print(f"eval: re-emitted {out} in the app's wording (no section was run)")
            return 0
        if args.merge:
            if not sections:
                print("eval: --merge needs --only <sections>", file=sys.stderr)
                return 2
            try:
                base = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"eval: --merge needs an existing report at {out} ({type(e).__name__}); run the full eval first", file=sys.stderr)
                return 2
            unknown = [s for s in sections if s not in SECTION_NAMES and s != "limitations"]
            if unknown:
                raise ValueError(f"unknown section(s): {', '.join(unknown)}; choose from {', '.join(SECTION_NAMES)}")
            report = merge_report(base, only=sections, root=args.data)
        else:
            report = build_report(fast=args.fast, sections=sections, root=args.data, seed=args.seed, regenerate=not args.no_generate)
    except ValueError as e:
        print(f"eval: {e}", file=sys.stderr)
        return 2
    errs = errors(report)
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
    if not args.no_facts:
        write_atomic(out.with_suffix(".facts.json"), dumps(build_facts(report)))
    if args.fixture:
        write_atomic(Path(args.fixture), dumps_min(trim(report)))
    secs = report["sections"]
    status = {k: (v.get("status", "ok") if isinstance(v, dict) else "ok") for k, v in secs.items() if k != "limitations"}
    bad = [k for k, v in status.items() if v == "failed"]
    how = f"merged {','.join(report['run']['merged'][-1]['sections'])} in {report['run']['merged'][-1]['seconds']}s" if args.merge else f"{report['run']['seconds_total']}s, {'fast' if args.fast else 'full'}"
    print(f"eval: wrote {out} ({how}; mock={report['mock']}); "
          f"{sum(v == 'ok' for v in status.values())} ok, {sum(v == 'pending' for v in status.values())} pending, "
          f"{sum(v == 'not_run' for v in status.values())} not run, {len(bad)} failed; {len(secs.get('limitations', []))} limitations")
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
