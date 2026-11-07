"""A coherent demo state for the three-minute demo: ``python -m understudy_engine.demo seed [--reset]``.

Seeds ONE isolated state home so the demo runs with no manual steps. It only ever touches the directory named by
``UNDERSTUDY_HOME`` (``make demo`` points it at ``data/demo-home``); with the variable unset it refuses, so it can never
write the owner's real ``~/.understudy``. Everything goes through the same code the API uses, as the worker:

* onboarding for the benefits-processor role with desk capture on (the ``Capture: times only`` line), person ``p_learn01``;
* the Skill state line for ``enter-household-once`` at L4 (the routine's cogs), so the calculator-entry routine is eligible
  for consent without an override;
* the ``calc-entry-3x`` routine detected by the real finder and listed as proposed: rung A0, nothing consented. The finder reads
  the nine-to-five persona's traces for it (the learner trajectories are one task type and hold no calculator-entry routine);
* ``p_learn01`` at learner case 24 (coach level and chip from the analytics track's SkillTracker). Case 24, not 20: that is
  the first case range where the learner's own ENTER_HOUSEHOLD level is L4, so the skill gate agrees with the memory file;
* three consistent corrections already recorded, so one rule proposal is waiting for the worker's approval.

``--reset`` wipes only the files this seed made in that home (and only if the home carries the demo marker or is empty).
Re-running without ``--reset`` changes nothing.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .memory import MemoryStore, RuleEngine, load_pack, onboard
from .memory import doc as D
from .memory.paths import data_dir, home_dir
from .memory.shadow import ExpertPolicy

DEMO_PERSON = "p_learn01"
DEMO_CASE = 24
DEMO_ROLE = "benefits-processor"
DEMO_ROUTINE = "calc-entry-3x"
ROUTINE_SOURCE = "p_ninetofive"
MARKER = ".understudy-demo-home"
STATE_FILES = ("memory.md", "memory_state.json", "routines_state.json", ".memory.lock")
ROUTINE_FILES = ("consent.json", "shadow_log.jsonl", "recording.json")


class DemoError(RuntimeError):
    pass


def _routine_dirs() -> Path:
    return data_dir() / "routines" / DEMO_ROUTINE


def reset_home(home: Path, out: Callable[[str], None]) -> None:
    if (home / "memory.md").exists() and not (home / MARKER).exists():
        raise DemoError(f"{home} holds a memory file the demo did not create, so I will not reset it. Point UNDERSTUDY_HOME at an empty or demo home.")
    removed = []
    for name in STATE_FILES:
        f = home / name
        if f.exists():
            f.unlink()
            removed.append(name)
    for name in ROUTINE_FILES:  # side files the consent flow wrote for the demo routine; compiled bundles (steps.json) are never touched
        f = _routine_dirs() / name
        if f.exists():
            f.unlink()
            removed.append(f"routines/{DEMO_ROUTINE}/{name}")
    out(f"reset: removed {', '.join(removed) if removed else 'nothing (already empty)'}")


def seed(*, reset: bool = False, now: datetime | None = None, out: Callable[[str], None] = print) -> dict[str, Any]:
    if not os.environ.get("UNDERSTUDY_HOME"):
        raise DemoError("UNDERSTUDY_HOME is not set. I will not touch the default ~/.understudy; set UNDERSTUDY_HOME (make demo uses data/demo-home).")
    home = home_dir()
    for slug in ("learners", "nine-to-five"):
        if not (data_dir() / "synthetic" / slug / "events.jsonl").exists():
            raise DemoError(f"synthetic data is missing ({slug}). Run `uv run understudy synth --all` first.")
    home.mkdir(parents=True, exist_ok=True)
    out(f"state home: {home}")
    if reset:
        reset_home(home, out)
    store = MemoryStore(home)
    if (home / "memory.md").exists() and not (home / MARKER).exists():
        raise DemoError(f"{home} already holds a memory file that is not a demo seed. Use an empty directory (or a demo home with --reset).")
    st = store.load_state()
    if (st.get("demo") or {}).get("seeded"):
        out(f"already seeded (memory revision {store.revision()}); nothing changed. Use --reset to start over.")
        return {"seeded": False, "revision": store.revision(), "person": (st.get("profile") or {}).get("person")}

    t = now or datetime.now(timezone.utc)
    (home / MARKER).write_text("created by understudy_engine.demo seed; safe to reset\n")

    # 1. onboarding, as the worker, with capture on
    res = onboard(store, DEMO_ROLE, {"capture": True}, person=DEMO_PERSON, now=t)
    out(f"onboarding: role {res['role']}, person {res['person']}, memory revision {res['revision']}, capture {'on' if res['capture'] else 'off'}")

    # 2. skill state at L4 for the routine's cogs
    pack = load_pack(DEMO_ROLE)
    tmpl = pack.template(DEMO_ROUTINE)
    cogs = set((tmpl or {}).get("cogs", [])) | set((tmpl or {}).get("skill_cogs", []))
    levelled = []
    doc = store.read()
    sec = doc.section("Skill state", create=False)
    skills = {str(s["id"]): s for s in pack.skills}
    for ln in (sec.lines() if sec else []):
        p = D.parse_skill_line(ln.text)
        if p and set(skills.get(p["skill"], {}).get("cogs", [])) & cogs:
            store.update_line(ln.id, actor="worker", text=f"{p['skill']}: L4, streak 3, last seen {t.date().isoformat()}", note="demo seed")
            levelled.append(p["skill"])
    out(f"skill state: L4 on {', '.join(levelled) or 'nothing'} (the routine's cogs: {', '.join(sorted(cogs))})")

    # 3. three consistent corrections: one pending rule proposal
    rules = RuleEngine(store, policy=ExpertPolicy.from_pack(pack))
    prop = None
    for k, ago in enumerate((timedelta(days=2), timedelta(days=1), timedelta(hours=3))):
        r = rules.record_correction("summary_length", "detailed", actor="worker", ceiling="A2", now=t - ago)
        prop = r["proposal"] or prop
    out(f"rule proposal waiting for approval: {prop['id']} ({prop['rule']!r}, {prop['evidence_count']} corrections, ceiling {prop['ceiling']})" if prop else "no proposal was raised")

    # 4. demo configuration (read by coach/state, routines and graph/work) and the routine through the real finder
    s2 = store.load_state()
    s2["demo"] = {"seeded": True, "person": DEMO_PERSON, "case": DEMO_CASE, "routine_source": ROUTINE_SOURCE,
                  "routine_ids": [DEMO_ROUTINE], "seeded_at": t.replace(microsecond=0).isoformat()}
    store.save_state(s2, actor="worker")
    from . import routes_handoff as rh

    pd = rh._src().load(DEMO_PERSON)
    if pd is None:
        raise DemoError(f"no events for {DEMO_PERSON}; run `uv run understudy synth --all`.")
    rstore = rh._sync_routines(pd, rh._mem())
    routine = next((r for r in rstore.list() if r["id"] == DEMO_ROUTINE), None)
    if routine is None:
        raise DemoError(f"the finder did not produce {DEMO_ROUTINE}; check the nine-to-five persona data and the pack template.")
    coach = rh.coach_state(person=None, step=None, case=None)
    out(f"routine: {routine['id']} status {routine['status']}, rung {routine['rung']}, consent {routine['consent']['mode']}, "
        f"gate eligible {routine['skill_gate']['eligible']} ({routine['skill_gate']['reason']}), about {routine['value']['hours_saved'][0]} to "
        f"{routine['value']['hours_saved'][1]} hours over {routine['value']['horizon_weeks']} weeks")
    out(f"coach: {DEMO_PERSON} at case {coach.get('case')} of {coach.get('cases_total')}: level {coach['level']}, chip {coach['chip']}")
    problems = []
    if routine["status"] != "proposed" or routine["rung"] != "A0" or routine["consent"]["mode"] != "none":
        problems.append("the routine is not in its proposed, unconsented state")
    if not routine["skill_gate"]["eligible"]:
        problems.append("the routine is not eligible without an override")
    if not prop:
        problems.append("no rule proposal")
    if problems:
        raise DemoError("seeded, but the state is not what the demo needs: " + "; ".join(problems))
    out("done. Start the engine with this UNDERSTUDY_HOME to run the demo.")
    return {"seeded": True, "revision": store.revision(), "person": DEMO_PERSON, "routine": routine["id"], "proposal": prop["id"],
            "coach": {"level": coach["level"], "chip": coach["chip"], "case": coach.get("case")}}


def status(out: Callable[[str], None] = print) -> int:
    home = home_dir()
    store = MemoryStore(home)
    st = store.load_state()
    d = st.get("demo") or {}
    out(f"state home: {home} (UNDERSTUDY_HOME {'set' if os.environ.get('UNDERSTUDY_HOME') else 'NOT set: this is the default home'})")
    out(f"memory revision {store.revision()}, demo seeded: {bool(d.get('seeded'))}, person {(st.get('profile') or {}).get('person')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.demo", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed", help="populate the isolated demo state home named by UNDERSTUDY_HOME")
    sp.add_argument("--reset", action="store_true", help="wipe the demo files in that home first")
    sub.add_parser("status", help="show what the home holds")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "status":
            return status()
        seed(reset=args.reset)
        return 0
    except DemoError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
