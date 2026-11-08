"""The worker's captured events for one role, twelve weeks of them, written as a top-up (``seedroles.seed_role``).

What it writes, for the worker ``PERSON`` under ``role`` (programmer or data analyst):

* ``<data>/history/<person>/<day>-<role code>.jsonl``: schema-valid L0 events (what ``PersonSource`` reads beside the live capture in ``<data>/real/<person>/``): the work
  ribbon and the hours (``/presence``), the routines the finder proposes (``/routines``), the routines map (``/graph/work``) and the steps (``/coach/state``). One file per UTC day, the
  role in the file name so two roles never collide. The events keep the data enum ``origin: synthetic``, so they never go into the ``real`` partition (which holds only real
  capture) nor into the shared ``synthetic`` dataset; ``PersonSource`` merges the folder in (additive, ``routines/sources.py``).
* for the programmer only, ``<data>/git/<person>/repo``: a real git repository with twelve weeks of commits (``gitanalysis.synth.make_repo``), which ``/git/habits`` finds as the
  worker's own learner repository (additive, ``gitanalysis/service.py``).

How it is made, all from existing generators and the role pack's own files: ``personas_v2.generate_workweeks`` (circadian windows, days off, interruptions, background activity, routines
that emerge, a novice's practice curve) with the role's frozen spec EXTENDED by the pack: every cog of the pack's ``mapping.yaml`` gets its event rule as its emission, its dwell time
from the pack's ``priors.yaml`` ``cog_dwell_s``, and the routines planted are four of the pack's own ``routines.yaml`` templates (so the finder matches them by their cog skeleton and the
Routines screen shows the pack's wording). The pace of work is the pack's ``persona.yaml`` ``tasks_per_active_hour``. A week off is cut out. Nothing is typed into a screen.

Idempotent through ``<data>/.seed-events-<role>`` (written last). Only a demo data directory is ever written. Nothing here calls a model or the network; ``now`` is the only clock.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from . import PERSON

CODE = {"programmer": "pg", "data-analyst": "da"}
#: which of the pack's own routine templates are planted, in order of preference (the first four whose every cog the pack's mapping can emit are used)
PLANTED = {
    "programmer": ("rerun-failed-ci", "ci-status-sweep", "post-release-watch", "open-pr-from-branch", "docs-lookup-and-apply", "add-failure-log-line"),
    "data-analyst": ("weekly-metric-refresh", "parameterised-weekly-query", "interval-for-a-rate", "draft-metric-definition", "join-check-and-count", "reload-and-reprofile"),
}
#: first seed tried per role; the first seed that gives a person the whole planted set is used (a fixed search, so the same inputs always give the same history)
FIRST_SEED = {"programmer": 11, "data-analyst": 21}
FAMILY = "latent_skill"
WEEKS = 12
#: the generator's own knobs for this worker (drawn ranges are in personas_v2/params.py): a calm event rate (a thin L0 capture), a worker whose routines are a large and steady share of
#: the day (so the finder sees them often enough to be worth proposing) and a pace a little above the pack's mean tasks per hour
HYPER = {"expert_share": 0.25, "event_rate_per_s": 0.06, "wk_routine_share": 0.6, "wk_routine_drift": 0.04, "wk_split_p": 0.0, "wk_interleave_p": 0.02}
PACE_FACTOR = {"programmer": 2.4, "data-analyst": 4.5}      # the analyst's routines are shorter, so they must come round more often before one is worth proposing
#: cogs that change something (the progress report of a step is a commit); everything else the pack adds is reading or looking
_COMMIT_PREFIX = ("WRITE_", "OPEN_", "ADD_", "ROLL_", "SCHEDULE_", "PARAMETERISE_", "DOCUMENT_", "MAKE_", "SET_", "JOIN_", "GROUP_")


def _pack_dir(role: str) -> Path:
    from ..memory.paths import packs_dir

    return packs_dir() / role


def derived_spec(role: str):
    """The role's frozen generator spec, extended with the pack's own cogs, timings and routine templates. Pure; reads only the pack's files."""
    from ..memory import load_pack
    from ..personas_v2.roles import Emit, RoutineT, get_role

    base = get_role(role)
    pack = load_pack(role)
    mapping = yaml.safe_load((_pack_dir(role) / "mapping.yaml").read_text(encoding="utf-8")) or {}
    prior = dict((pack.priors or {}).get("cog_dwell_s") or {})
    emit, dwell, labels, act = dict(base.emit), dict(base.dwell), dict(base.labels), dict(base.act_class)
    cogs = list(base.cogs)
    for rule in mapping.get("rules") or []:
        cog, m = rule.get("cog"), rule.get("match") or {}
        zone = m.get("zone")
        if not cog or not zone or rule.get("starts") or cog in emit:
            continue
        types = m.get("type")
        types = tuple([types] if isinstance(types, str) else types or ())
        if not types:
            continue
        emit[cog] = Emit("single" if len(types) == 1 else "ticks", types, zone, "region")
        dwell.setdefault(cog, (float(prior.get(cog, 45)), 0.45))
        labels.setdefault(zone, [zone.replace("_", " ")])
        act[cog] = "commit" if cog.startswith(_COMMIT_PREFIX) else "read"
        # ``zones`` (what the wrong-zone capture noise draws from) is deliberately left as the frozen spec has it, so a mis-captured click never invents a rollback
        if cog not in cogs:
            cogs.append(cog)
    chosen: list[Any] = []
    by_id = {t["id"]: t for t in pack.templates}
    for tid in PLANTED[role]:
        t = by_id.get(tid)
        if t is not None and t.get("automatable", True) and all(c in emit for c in t["cogs"]):
            chosen.append(RoutineT(tid, head=tuple(t["cogs"])))
        if len(chosen) == 4:
            break
    return dataclasses.replace(base, cogs=tuple(cogs), dwell=dwell, emit=emit, labels=labels, act_class=act, pool=tuple(base.pool) + tuple(c for c in cogs if c not in base.cogs and c not in base.pool), routines=tuple(chosen))


def _window(now: datetime) -> tuple[date, int]:
    """``(Monday the history starts, days)``: twelve weeks and up to six days, ending the UTC day before ``now`` (so it never touches today's live capture file)."""
    last = now.astimezone(timezone.utc).date() - timedelta(days=1)
    start = last - timedelta(days=WEEKS * 7 - 1)
    start -= timedelta(days=start.weekday())
    return start, (last - start).days + 1


def build_rows(role: str, now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The history as event rows for ``PERSON`` (not yet written) and a summary. Deterministic for a given ``now`` date."""
    from ..memory import load_pack
    from ..personas_v2 import generate_workweeks

    spec = derived_spec(role)
    if len(spec.routines) < 3:
        raise RuntimeError(f"the {role} pack gives fewer than three routine templates the generator can emit")
    pack = load_pack(role)
    pace = float(((pack.persona or {}).get("tasks_per_active_hour") or {}).get("mean", 0.7))      # the pack's own pace (tasks per active hour), scaled by PACE_FACTOR
    start, n_days = _window(now)
    today = now.astimezone(timezone.utc).date().isoformat()
    for k in range(40):
        seed = FIRST_SEED[role] + k
        ww = generate_workweeks(FAMILY, role, n_people=4, n_days=n_days, seed=seed, role_spec=spec, hyper_overrides={**HYPER, "wk_tasks_per_h": pace * PACE_FACTOR[role]},
                                start=datetime(start.year, start.month, start.day, tzinfo=timezone.utc))
        truth = {p["person"]: p for p in ww.truth["people"]}
        # a learner who works most weekdays (the days worked are the person's own schedule draw), on days, with every planted routine repeated often enough to be found
        who = next((p for p in ww.people if p.level == "novice" and len(truth[p.id]["routines"]) == len(spec.routines) and not truth[p.id]["night_shift"]
                    and truth[p.id]["days_worked"] >= 0.62 * n_days and all(r["n_instances"] >= 12 for r in truth[p.id]["routines"])), None)
        if who is not None:
            break
    else:
        raise RuntimeError(f"no seed gave a learner with every planted routine for {role}")
    code = CODE[role]
    off_week = 4 + seed % 5                                               # one week away, somewhere in the middle: the hours and the week show a gap
    off0 = start + timedelta(days=7 * off_week)
    off = {(off0 + timedelta(days=i)).isoformat() for i in range(7)}
    rows: list[dict[str, Any]] = []
    for r in ww.rows:
        if r["person"] != who.id:
            continue
        day = r["t"][:10]
        if day >= today or day in off:
            continue
        r = dict(r)
        r["person"], r["id"] = PERSON, f"{code}{r['id']}"[:64]
        if r.get("task_id"):
            r["task_id"] = ("t_" + code + r["task_id"][2:])[:34]
            r["task_id"] = r["task_id"][:34]
        rows.append(r)
    rows.sort(key=lambda r: (r["t"], r["id"]))
    info = {"seed": seed, "days": n_days, "start": start.isoformat(), "off_week": off0.isoformat(), "routines": [r["name"] for r in truth[who.id]["routines"]],
            "night_shift": bool(truth[who.id]["night_shift"]), "tasks": sum(1 for r in rows if r["type"] == "task_start")}
    return rows, info


def _repo_spec(role: str, now: datetime):
    from ..gitanalysis.synth import RepoSpec

    start, n_days = _window(now)
    # twelve weeks of a developer's commits: two habits partly planted (committing without tests, vague messages), the rest at the baseline; the seed fixes the history
    return RepoSpec(person=PERSON, level="learner", seed=FIRST_SEED[role] * 7, days=n_days, start=start.isoformat(), planted=("tests_with_changes", "vague_messages"),
                    strength=0.6, tz_min=0, commits_per_day=2.6)


def seed(dd: Path, role: str, now: datetime, out: Callable[[str], None] = print) -> dict[str, Any]:
    """Write the role's events (and, for the programmer, the commit history) under the demo data directory ``dd``. Idempotent."""
    from ..demo import is_demo_data_dir
    from ..store.jsonl import EventStore

    if role not in CODE:
        raise ValueError(f"no events to seed for {role!r}")
    if not is_demo_data_dir(dd):
        out(f"events ({role}): {dd} is not a demo data dir; not written.")
        return {"events": False}
    marker = dd / f".seed-events-{role}"
    if marker.exists():
        out(f"events ({role}): already seeded; nothing changed.")
        return {"events": True, "written": False}
    rows, info = build_rows(role, now)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_day[r["t"][:10]].append(r)
    folder = dd / "history" / PERSON
    store = EventStore(dd)
    n_files = skipped = 0
    for day, rs in sorted(by_day.items()):
        path = folder / f"{day}-{CODE[role]}.jsonl"
        if path.exists():
            skipped += 1
            continue
        store.write_file(path, rs, overwrite=False)
        n_files += 1
    git = None
    if role == "programmer":
        repo = dd / "git" / PERSON
        if (repo / "repo" / ".git").exists():
            git = "already there"
        else:
            from ..gitanalysis.synth import make_repo

            make_repo(_repo_spec(role, now), repo)
            git = "written"
    marker.write_text(json.dumps({"seeded": now.astimezone(timezone.utc).isoformat(timespec="seconds"), "role": role, "events": len(rows), "files": n_files, **info}) + "\n")
    out(f"events ({role}): {len(rows)} events on {n_files} days for {PERSON} ({info['tasks']} tasks, routines {', '.join(info['routines'])}; one week away from {info['off_week']})"
        + (f"; commit history {git}" if git else "") + f"; written to {folder}")
    return {"events": True, "written": True, "rows": len(rows), "files": n_files, "skipped_days": skipped, "git": git, **info}
