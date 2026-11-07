"""``python -m understudy_engine.study``: the facilitator's tools for the live study.

    roster add <person> expert|novice | roster list | roster remove <person>
    mode --person P --block train|post_test|off --on SKILL --level L1 [--participant P1 --block-no 1]
    mode --show | mode --clear
    session set P1 --person p_xxx [--sequence S1] [--exclude REASON]   |   session note P1 --block 1 --text "..."
    export [--out PATH] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import roster as roster_mod
from .state import StudyError, atomic_write, clear_state, read_state, sessions_path, write_state


def _sessions() -> dict:
    p = sessions_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.study", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("roster", help="who is an expert or a novice in the real cohort")
    rs = r.add_subparsers(dest="rcmd", required=True)
    ra = rs.add_parser("add")
    ra.add_argument("person")
    ra.add_argument("level", choices=roster_mod.LEVELS)
    rs.add_parser("list")
    rr = rs.add_parser("remove")
    rr.add_argument("person")

    m = sub.add_parser("mode", help="set or show the per-skill coach switch")
    m.add_argument("--person")
    m.add_argument("--block", choices=("train", "post_test", "off"))
    m.add_argument("--on", dest="skill_on", help="the one skill the coach may act on (check-the-cliff, reconcile-before-noting, cliff, reconcile)")
    m.add_argument("--level", default="L1", choices=("L1", "L2", "L3", "L4"))
    m.add_argument("--participant", help="P1..P4, recorded in the log for the export")
    m.add_argument("--block-no", type=int, dest="block_no")
    m.add_argument("--steps-off", dest="steps_off", help="comma list of steps the coach should not wait for (default calc_c,cliff_c: two calculators)")
    m.add_argument("--show", action="store_true")
    m.add_argument("--clear", action="store_true")

    s = sub.add_parser("session", help="map participants to person ids, record exclusions and notes")
    ss = s.add_subparsers(dest="scmd", required=True)
    sset = ss.add_parser("set")
    sset.add_argument("participant")
    sset.add_argument("--person", required=True)
    sset.add_argument("--sequence")
    sset.add_argument("--exclude", help="reason (applies to both blocks of the participant)")
    sn = ss.add_parser("note")
    sn.add_argument("participant")
    sn.add_argument("--block", type=int, required=True)
    sn.add_argument("--text", required=True)
    ss.add_parser("list")

    e = sub.add_parser("export", help="write participants.csv for evals/study/analyze.py")
    e.add_argument("--out", help="default: evals/study/results/participants.csv")
    e.add_argument("--dry-run", action="store_true", help="print the rows and problems, write nothing")
    e.add_argument("--force", action="store_true", help="overwrite an existing results file")
    e.add_argument("--partition", choices=("real", "synthetic", "both"), default="both")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "roster":
            if a.rcmd == "add":
                out = roster_mod.add(a.person, a.level)
            elif a.rcmd == "remove":
                out = roster_mod.remove(a.person)
            else:
                out = roster_mod.load()
            print(json.dumps(out, indent=2))
            return 0
        if a.cmd == "mode":
            if a.clear:
                print("cleared" if clear_state() else "no state file")
                return 0
            if a.show or not a.block:
                cur = read_state()
                print(json.dumps(cur.to_dict() if cur else None, indent=2))
                return 0
            if not a.person:
                raise StudyError("--person is required")
            off = [x for x in a.steps_off.split(",") if x] if a.steps_off is not None else None
            mode = write_state(a.person, a.block, a.skill_on, a.level, steps_off=off, participant=a.participant, block_no=a.block_no)
            print(json.dumps(mode.to_dict(), indent=2))
            return 0
        if a.cmd == "session":
            data = _sessions()
            if a.scmd == "set":
                cur = data.setdefault(a.participant, {})
                cur["person"] = a.person
                if a.sequence:
                    cur["sequence"] = a.sequence
                if a.exclude is not None:
                    cur["exclusion"] = a.exclude
                atomic_write(sessions_path(), json.dumps(data, indent=2, sort_keys=True) + "\n")
            elif a.scmd == "note":
                data.setdefault(a.participant, {}).setdefault("notes", {})[str(a.block)] = a.text
                atomic_write(sessions_path(), json.dumps(data, indent=2, sort_keys=True) + "\n")
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        if a.cmd == "export":
            from .export import build_rows, load_analyze, results_dir, write_csv

            rows, problems = build_rows(partition=a.partition)
            for p in problems:
                print("note:", p, file=sys.stderr)
            if a.dry_run:
                print(json.dumps(rows, indent=2))
                return 0
            out = Path(a.out) if a.out else results_dir() / "participants.csv"
            if out.exists() and not a.force:
                raise StudyError(f"{out} already exists; use --force to overwrite it, or --out for another file.")
            write_csv(rows, out)
            print(f"wrote {len(rows)} rows to {out}")
            an = load_analyze()
            issues = an.design_problems(an.load(out), json.loads((Path(an.__file__).parent / "assignments.json").read_text()))
            for p in issues:
                print("design:", p, file=sys.stderr)
            return 0
    except StudyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
