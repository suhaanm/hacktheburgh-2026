"""Evaluation of the proactive layer (PRO-1, PRO-3, NFR-11): ``evaluate_proactive(fast=False) -> dict``.

What is measured, on synthetic personas, learners and git learners with planted truth (nobody is real):

1. **Structure (PRO-1 acceptance).** Over every replayed briefing: the card cap of three always holds; not one card fires, enqueues or
   starts a run without a press (calls to the approval queue, the agent service and ``fire`` are counted while the briefings are
   built, and must be zero; a press on a sample of cards makes exactly one thing each); stale cards are dropped when the world changes
   and kept when it does not.
2. **Worth surfacing.** Briefings are replayed at fixed decision points (persona days, learner cases, each git learner's repository).
   At each point the data is cut at that time, the real finder, skill tracker and git analysis run, and the real judge, verify and
   prepare pass produce the cards. They are scored against the planted truth: precision (the share of surfaced cards that were
   planted opportunities) and recall (the share of planted opportunities, capped at what the judge may show of that kind, that were
   surfaced). Compared with three baselines (top three by raw value with no checks, three at random, everything with no cap) and a
   placebo (the same cards scored against another person's truth).
3. **Acceptance learning (PRO-3).** A simulated worker with fixed accept rates per kind: how well the per-kind estimate recovers them
   after k labels. A simulation, not people.

Truth definitions, fixed before any run (and printed in the output):

* automate: a planted routine of kind ``calc3`` or ``note`` (the automatable kinds) that is planted at 10 minutes a week or more, seen
  at least 8 times so far, and, for ``calc3`` (learning relevant), with the planted skill at least 0.85 (the level-4 line). The decoy
  kinds (queue sweep, cliff re-check, weekly report) are never worth proposing.
* practice, personas: the planted skill is below 0.65 (level 1 or 2: full or small help; at level 3 the help is already a dot), or it
  is below 0.85 while a worthwhile ``calc3`` routine is held back only by the skill gate (practising is what unlocks it).
  Practice, learners: a skill is in play when its cogs overlap the cogs the truth file lists for a planted deficit whose probability is
  at least 0.25 per case.
* git habit: a habit planted in the learner's repository, through its catalogue template.

Revision log: the first run (fast replay) used "at least 15 minutes a week so far" for automate and no unlock clause for practice; it
scored the early days unfairly (minutes so far over a calendar week under-counts a routine that has only run for three days) and ignored
the product's own "coach first, then automate" rule. Both were changed once, after seeing that run, and not tuned again; the earlier
persona practice definition is reported under ``sensitivity_persona_practice_truth``.

Intervals: Wilson on pooled counts (which treats decision points as independent and so is too narrow) and a bootstrap that resamples
whole people (the honest one, with 7 people and 4 git learners). Limitations are in the output and in the register.
"""
from __future__ import annotations

import json
import os
import random
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import briefing as B
from . import fire as F
from . import judge as J
from .acceptance import AcceptanceModel
from .candidates import KINDS, Candidate, Ctx, FireSpec, Reading, collect
from .paths import data_dir
from .sources import Readers, routine_rows, skill_rows_from_levels, skill_rows_from_tracker
from .store import BriefingStore

PERSONAS = (("nine-to-five", "p_ninetofive"), ("night-owl", "p_nightowl"), ("shift-worker", "p_shiftwkr"), ("irregular", "p_irregular"))
AUTOMATABLE_KINDS = ("calc3", "note")
MIN_INSTANCES, MIN_MPW, SKILL_L4, SKILL_L3 = 8, 10.0, 0.85, 0.65
LEARNER_P_GAP = 0.25
LEARNER_SKILL_OF = {"idle_before_enter": "enter-household-once", "skipped_check_cliff": "check-the-cliff", "copy_error": "note-with-evidence"}
GIT_TEMPLATE_OF = {"big_commits": "smaller_commits", "tests_with_changes": "tests_with_changes", "fix_after_fix": "run_tests_before_commit",
                   "reverts": "run_tests_before_commit", "vague_messages": "clearer_messages", "late_night": "protect_late_night"}
CAL_PROBLEM_TEMPLATES = {"fragmented_days": ("batch_similar_work",), "no_focus_blocks": ("protect_focus_block", "auto_hold_scheduling"),
                         "back_to_back_days": ("reduce_back_to_back",), "recurring_in_peak": ("move_recurring_out_of_peak",),
                         "no_review_slot": ("add_review_slot",), "no_breaks": ("offcomputer_break",),
                         "unbuffered_external_days": ("buffer_before_external",), "late_days": ("protect_working_edges",)}
EVAL_KINDS = ("automate", "practice", "git_habit", "focus_block")
WILDCARD = "skill:*"
ACCEPT_TRUE = {"practice": 0.7, "automate": 0.25, "focus_block": 0.5, "git_habit": 0.4, "agent_result": 0.8}


# ------------------------------------------------------------------------------------------------------------ environment
@contextmanager
def _env(**kv: str) -> Iterator[None]:
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update(kv)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _wilson(k: int, n: int) -> list[float]:
    from ..trust.stats import wilson_interval

    lo, hi = wilson_interval(k, n)
    return [round(lo, 3), round(hi, 3)]


def _ratio(k: int | float, n: int | float) -> float | None:
    return None if n == 0 else round(float(k) / float(n), 3)


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ------------------------------------------------------------------------------------------------------------ decision points
@dataclass
class Point:
    group: str                 # person the point belongs to (cluster for the bootstrap)
    source: str                # persona | learner | git
    label: str                 # "day 7", "case 15", "repo"
    person: str
    now: datetime
    readers: Readers
    truth: dict[str, set[str]]
    role: str = "benefits-processor"
    index: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _unavailable(note: str) -> Callable[[Ctx], Reading]:
    return lambda ctx: Reading([], False, note)


def _nothing(ctx: Ctx) -> Reading:
    return Reading([], False, "not part of this replay")


class _LevelSource:
    """A skill source for the routine gate: every cog at one level (the persona's planted skill, mapped through the level ladder)."""

    COGS = ("ENTER_HOUSEHOLD", "OPEN_CALCULATOR", "CHECK_CLIFF", "READ", "RECONCILE", "COPY_TO_NOTE", "READ_RESULT")

    def __init__(self, level: int) -> None:
        self.level = level

    def snapshot(self, t: float) -> dict[str, dict[str, Any]]:
        return {c: {"level": self.level} for c in self.COGS}


def persona_points(root: Path, days: tuple[int, ...], draws: int, workdir: Path) -> list[Point]:
    from ..memory import MemoryStore, load_pack
    from ..routines.detect import DetectConfig, detect_routines
    from ..routines.sources import PersonSource
    from ..routines.store import RoutineStore
    from ..skills.levels import cap_for_mastery

    src = PersonSource(root)
    pts: list[Point] = []
    for slug, person in PERSONAS:
        pd = src.load(person)
        if pd is None or not pd.truth:
            continue
        eps = src.episodes(pd)
        truth, pack = pd.truth, load_pack(pd.role)
        start = datetime.fromisoformat(truth["start_date"]).replace(tzinfo=timezone.utc)
        for day in days:
            cut_dt = start + timedelta(days=day)
            cut = cut_dt.timestamp()
            skill = float(truth["skill"]["by_day"][day - 1])
            lvl = cap_for_mastery(skill)
            sub = [e for e in eps if e.t1 <= cut]

            def routines(ctx: Ctx, sub=sub, lvl=lvl, cut=cut, person=person, pack=pack, idx=len(pts)) -> Reading:
                det = detect_routines(sub, pack, person=person, now=cut, skills=_LevelSource(lvl), cfg=DetectConfig(forecast_draws=draws))
                st = RoutineStore(MemoryStore(workdir / f"home_{idx}"))
                st.merge(det)
                return Reading(routine_rows(st, person), True, None)

            def skills(ctx: Ctx, lvl=lvl, cut=cut, pack=pack) -> Reading:
                levels = {str(s["id"]): {"level": lvl, "last_seen": None} for s in pack.skills}
                return Reading(skill_rows_from_levels(levels, pack, cut), True, "planted skill mapped to a level on every skill")

            automate: set[str] = set()
            blocked_worthwhile = False        # a worthwhile learning-relevant routine that only the skill gate is holding back
            for r in truth["routines"]:
                inst = [i for i in r["instances"] if _ts(i["t1"]) <= cut]
                ok = r["kind"] in AUTOMATABLE_KINDS and len(inst) >= MIN_INSTANCES and float(r["minutes_per_week"]) >= MIN_MPW
                if ok and r["kind"] == "calc3" and skill < SKILL_L4:
                    ok, blocked_worthwhile = False, True
                if ok:
                    automate.add(f"routine:{r['name']}")
            practice = {WILDCARD} if (skill < SKILL_L3 or blocked_worthwhile) else set()
            rd = Readers(routines=routines, skills=skills, calendar=_nothing, git=_nothing, runs=_nothing)
            pts.append(Point(person, "persona", f"day {day}", person, cut_dt, rd, {"automate": automate, "practice": practice}, pd.role, len(pts),
                             {"skill": skill}))
    return pts


def learner_points(root: Path, cases: tuple[int, ...]) -> list[Point]:
    from ..memory import load_pack
    from ..routines.learners import tracker_at

    truth_p = root / "synthetic" / "learners" / "truth.json"
    if not truth_p.exists():
        return []
    truth = json.loads(truth_p.read_text())
    pack = load_pack(truth.get("role", "benefits-processor"))
    pts: list[Point] = []
    for person in [p["person"] for p in truth["people"]]:
        traces = sorted((t for t in truth["traces"] if t["person"] == person), key=lambda t: t["case"])
        for case in cases:
            if case > len(traces):
                continue
            tr = traces[case - 1]
            now_ts = _ts(tr["t1"])
            st = tracker_at(person, case, root)
            if st is None:
                continue

            def skills(ctx: Ctx, st=st, pack=pack, now_ts=now_ts) -> Reading:
                return Reading(skill_rows_from_tracker(st, pack, now_ts), True, "from the skill tracker")

            live = [d for d, p in tr["p_deficit"].items() if p >= LEARNER_P_GAP]
            # the truth file says which cogs each planted deficit lives in; a skill is in play when its cogs overlap one
            practice = {f"skill:{sk['id']}" for d in live for sk in pack.skills if set(sk.get("cogs", [])) & set(truth["deficit_types"][d]["cogs"])}
            hand = {f"skill:{LEARNER_SKILL_OF[d]}" for d in live if d in LEARNER_SKILL_OF}
            rd = Readers(routines=_nothing, skills=skills, calendar=_nothing, git=_nothing, runs=_nothing)
            pts.append(Point(person, "learner", f"case {case}", person, datetime.fromtimestamp(now_ts, timezone.utc), rd,
                             {"automate": set(), "practice": practice}, truth.get("role", "benefits-processor"), len(pts), {"hand_truth": hand}))
    return pts


def git_points(root: Path, only: int | None = None) -> list[Point]:
    """One point per git learner: the real git analysis (flag on, in the evaluation's own data dir) against the planted habits."""
    from ..gitanalysis import service as gsvc

    pts: list[Point] = []
    try:
        people = [p["person"] for p in gsvc.people()["learners"]]
    except Exception:
        return []
    from ..gitanalysis.synth import load_truth

    cohort = gsvc.cohort()
    for person in people[:only] if only else people:
        try:
            planted = load_truth(cohort["learners"][person]).get("planted", [])
        except Exception:
            continue
        truth = {f"git:{GIT_TEMPLATE_OF[h]}" for h in planted if h in GIT_TEMPLATE_OF}
        from .sources import read_git

        rd = Readers(routines=_nothing, skills=_nothing, calendar=_nothing, git=read_git, runs=_nothing)
        pts.append(Point(person, "git", "repository", person, datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc), rd, {"git_habit": truth},
                         "programmer", 0))
    return pts


def calendar_points(root: Path, latest_only: bool = False, fast_people: tuple[str, ...] | None = None) -> list[Point]:
    """One point per person and week: the calendar track's suggestions for that week against the planted problems. The experts have
    none planted, so every card for an expert is a false alarm."""
    try:
        from ..calendar import service as csvc
        from ..calendar.store import CalendarStore
    except Exception:
        return []
    if not (root / "synthetic" / "calendars" / "truth.json").exists():
        return []
    store = CalendarStore(root=root)
    truth = store.truth() or {}
    pts: list[Point] = []
    for person, info in sorted((truth.get("people") or {}).items()):
        if fast_people is not None and person not in fast_people:
            continue
        weeks = sorted(info["weeks"])
        for week in weeks[-1:] if latest_only else weeks:
            wk = info["weeks"][week]
            planted = []
            for prob, templates in CAL_PROBLEM_TEMPLATES.items():
                present = (wk.get("recurring_in_peak_h_planted", 0) or 0) > 0 if prob == "recurring_in_peak" else bool(wk.get(prob))
                if present:
                    planted.append("|".join(f"cal:{t}" for t in templates))

            def calendar(ctx: Ctx, person=person, week=week) -> Reading:
                from .sources import calendar_items

                return Reading(calendar_items(csvc.suggestions_report(store, person, week)), True, None)

            rd = Readers(routines=_nothing, skills=_nothing, calendar=calendar, git=_nothing, runs=_nothing)
            pts.append(Point(person, "calendar", week, person, datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc), rd, {"focus_block": set(planted)},
                             info.get("role", "benefits-processor"), len(pts), {"group": info.get("group")}))
    return pts


# ------------------------------------------------------------------------------------------------------------ scoring
def _hit(item: str, subject: str) -> bool:
    """A truth item may list alternatives (``a|b``): any of them counts."""
    return subject in item.split("|")


def _score(subjects: dict[str, list[str]], truth: dict[str, set[str]], kinds: tuple[str, ...] = EVAL_KINDS) -> dict[str, dict[str, int]]:
    """Per kind: tp, fp, fn (capacity adjusted: a kind can only show ``MAX_PER_KIND`` cards, so that is all it can be asked to find)."""
    out: dict[str, dict[str, int]] = {}
    for kind in kinds:
        T = truth.get(kind, set())
        surf = subjects.get(kind, [])
        if WILDCARD in T:
            tp = 1 if surf else 0
            need = 1
            fp = max(0, len(surf) - 1) if surf else 0
        else:
            tp = sum(1 for item in T if any(_hit(item, s_) for s_ in surf))
            need = len(T)
            fp = sum(1 for s_ in surf if not any(_hit(item, s_) for item in T))
        cap = J.MAX_PER_KIND.get(kind, 1)
        out[kind] = {"tp": tp, "fp": fp, "fn": max(0, min(need, cap) - tp), "opp": min(need, cap)}
    return out


def _pool(rows: list[dict[str, dict[str, int]]], kinds: tuple[str, ...] = EVAL_KINDS) -> dict[str, int]:
    t = {"tp": 0, "fp": 0, "fn": 0, "opp": 0}
    for r in rows:
        for k in kinds:
            for f in t:
                t[f] += r.get(k, {}).get(f, 0)
    return t


def _pr(t: dict[str, int]) -> dict[str, Any]:
    p, r = t["tp"] + t["fp"], t["tp"] + t["fn"]
    return {"tp": t["tp"], "fp": t["fp"], "fn": t["fn"], "surfaced": p, "opportunities": r,
            "precision": _ratio(t["tp"], p), "precision_wilson": _wilson(t["tp"], p) if p else None,
            "recall": _ratio(t["tp"], r), "recall_wilson": _wilson(t["tp"], r) if r else None}


def _cluster_boot(by_group: dict[str, list[dict[str, dict[str, int]]]], kinds: tuple[str, ...], B_: int = 1000, seed: int = 11) -> dict[str, Any]:
    groups = sorted(by_group)
    pooled = {g: _pool(by_group[g], kinds) for g in groups}
    rng = np.random.default_rng(seed)
    ps, rs = [], []
    for _ in range(B_):
        pick = rng.integers(0, len(groups), len(groups))
        t = {"tp": 0, "fp": 0, "fn": 0, "opp": 0}
        for i in pick:
            for f in t:
                t[f] += pooled[groups[i]][f]
        if t["tp"] + t["fp"]:
            ps.append(t["tp"] / (t["tp"] + t["fp"]))
        if t["tp"] + t["fn"]:
            rs.append(t["tp"] / (t["tp"] + t["fn"]))

    def ci(x: list[float]) -> list[float] | None:
        return [round(float(np.percentile(x, 2.5)), 3), round(float(np.percentile(x, 97.5)), 3)] if len(x) >= 50 else None

    return {"precision_ci": ci(ps), "recall_ci": ci(rs), "n_people": len(groups), "draws": B_}


@dataclass
class Replay:
    point: Point
    cards: list[Any]
    candidates: list[Candidate]
    store: BriefingStore
    dropped: list[dict[str, str]] = field(default_factory=list)


def _replay(pt: Point, workdir: Path, allow_empty_reader: bool = True) -> Replay:
    store = BriefingStore(workdir / f"b_{pt.source}_{pt.person}_{pt.index}.json")
    ctx = Ctx(person=pt.person, now=pt.now, role=pt.role)
    cands = collect(ctx, pt.readers).candidates
    b = B.build(pt.person, store=store, readers=pt.readers, now=pt.now, role=pt.role, force=True)
    return Replay(pt, b.cards, cands, store, b.dropped)


def _subjects(cards: list[Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in cards:
        out.setdefault(c.kind, []).append(c.subject)
    return out


def _cand_subjects(cands: list[Candidate]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in cands:
        out.setdefault(c.kind, []).append(c.subject)
    return out


# ------------------------------------------------------------------------------------------------------------ structure checks
class _Spy:
    """Counts every way a card could leave the briefing: ``fire``, the default queue port and the default spawner."""

    def __init__(self) -> None:
        self.calls = {"fire": 0, "queue_port": 0, "spawner": 0}
        self._saved: dict[str, Any] = {}

    def __enter__(self) -> _Spy:
        for name, key in (("fire", "fire"), ("default_queue_port", "queue_port"), ("default_spawner", "spawner")):
            self._saved[name] = getattr(F, name)

            def wrap(*a: Any, _n=name, _k=key, **kw: Any):
                self.calls[_k] += 1
                return self._saved[_n](*a, **kw)

            setattr(F, name, wrap)
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, fn in self._saved.items():
            setattr(F, name, fn)


def _stale_mutation(readers: Readers, card: Any) -> Readers:
    """The world changes under a card: the routine is switched on elsewhere, or the skill reaches level 4."""
    kind, subject = card.kind, card.subject
    if kind == "automate":
        rid = subject.split(":", 1)[1]
        inner = readers.routines
        return Readers(routines=lambda ctx: _edit(inner(ctx), lambda r: {**r, "status": "approval"} if r["id"] == rid else r),
                       skills=readers.skills, calendar=readers.calendar, git=readers.git, runs=readers.runs, in_flight=readers.in_flight)
    if kind == "practice":
        sid = subject.split(":", 1)[1]
        inner = readers.skills
        return Readers(routines=readers.routines, skills=lambda ctx: _edit(inner(ctx), lambda r: {**r, "level": 4, "mastery": 0.95} if r["id"] == sid else r),
                       calendar=readers.calendar, git=readers.git, runs=readers.runs, in_flight=readers.in_flight)
    return readers


def _edit(rd: Reading, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Reading:
    return Reading([fn(r) for r in rd.items], rd.available, rd.note, rd.meta)


def _stale_tests(replays: list[Replay], workdir: Path) -> dict[str, Any]:
    from datetime import timedelta as td

    by_kind: dict[str, dict[str, int]] = {}
    kept = {"n": 0, "kept": 0, "confirmed": 0}
    for rp in replays:
        for c in rp.cards:
            if c.kind not in ("automate", "practice"):
                continue
            after = _stale_mutation(rp.point.readers, c)
            store = BriefingStore(workdir / f"stale_{rp.point.source}_{rp.point.person}_{rp.point.index}_{c.id}.json")
            # a fresh store holding exactly this briefing, then the world changes and the briefing is read again an hour later
            store.mutate(rp.point.person, lambda st, s=rp.store.person(rp.point.person): st.update(s))
            b = B.build(rp.point.person, store=store, readers=after, now=rp.point.now + td(hours=1), role=rp.point.role)
            row = by_kind.setdefault(c.kind, {"n": 0, "dropped": 0, "shown_after": 0})
            row["n"] += 1
            row["dropped"] += int(any(d["id"] == c.id for d in b.dropped))
            row["shown_after"] += int(any(x.id == c.id for x in b.cards))
            # control: nothing changed, only an hour passed
            store2 = BriefingStore(workdir / f"same_{rp.point.source}_{rp.point.person}_{rp.point.index}_{c.id}.json")
            store2.mutate(rp.point.person, lambda st, s=rp.store.person(rp.point.person): st.update(s))
            b2 = B.build(rp.point.person, store=store2, readers=rp.point.readers, now=rp.point.now + td(hours=1), role=rp.point.role)
            kept["n"] += 1
            kept["kept"] += int(any(x.id == c.id for x in b2.cards))
            kept["confirmed"] += int(any(x.id == c.id and x.verdict == "confirmed" for x in b2.cards))
    scripted = _scripted_stale(workdir)
    rows = []
    for k, v in sorted(by_kind.items()):
        rows.append({"kind": k, "source": "replay", **v, "drop_rate": _ratio(v["dropped"], v["n"]), "drop_wilson": _wilson(v["dropped"], v["n"])})
    rows += scripted["rows"]
    n = sum(r["n"] for r in rows)
    d = sum(r["dropped"] for r in rows)
    return {"rows": rows, "overall": {"n": n, "dropped": d, "drop_rate": _ratio(d, n), "drop_wilson": _wilson(d, n) if n else None,
                                      "still_shown_after_change": sum(r["shown_after"] for r in rows)},
            "unchanged": {"n": kept["n"], "kept": kept["kept"], "kept_rate": _ratio(kept["kept"], kept["n"]),
                          "kept_wilson": _wilson(kept["kept"], kept["n"]) if kept["n"] else None,
                          "confirmed": kept["confirmed"]},
            "no_verify_baseline": {"note": "Without the verify step every one of these cards would still be shown after the world changed.",
                                   "still_shown": n}}


def _scripted_stale(workdir: Path, n_per_kind: int = 8, seed: int = 5) -> dict[str, Any]:
    """Stale checks for the kinds the replays cannot reach (calendar, git, finished runs), on scripted readings with varied numbers."""
    rng = random.Random(seed)
    now = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)
    rows = []
    for kind in ("focus_block", "git_habit", "agent_result"):
        n = dropped = shown_after = 0
        for i in range(n_per_kind):
            def make(present: bool, ci_noise: bool = False):
                cal = [{"id": "protect_focus_block", "template": "protect_focus_block", "can_draft": True,
                        "numbers": {"longest_focus_min": rng_i.randint(30, 80), "gain_h": round(rng_i.uniform(1, 4), 1)}, "expert_ref": {}}] if present else []
                git = [{"id": "smaller_commits", "learner": 0.25, "expert": 0.03, "delta": 0.22,
                        "ci": ([-0.05, 0.3] if ci_noise else [0.12, 0.3]), "n_commits": 80}] if present else []
                runs = [{"run_id": f"r_{i}", "kind": "programming.commit_analyst", "state": "done", "finished_at": now.timestamp() - 3600, "children": 2,
                         "viewed": not present}]
                return Readers(routines=_nothing, skills=_nothing, calendar=lambda c: Reading(cal, True), git=lambda c: Reading(git, True),
                               runs=lambda c: Reading(runs, True))

            rng_i = random.Random(rng.random())
            person = f"p_scripted_{kind}_{i}"
            store = BriefingStore(workdir / f"scripted_{kind}_{i}.json")
            b = B.build(person, store=store, readers=make(True), now=now)
            card = next((c for c in b.cards if c.kind == kind), None)
            if card is None:
                continue
            after = B.build(person, store=store, readers=make(False, ci_noise=True), now=now + timedelta(hours=1))
            n += 1
            dropped += int(any(d["id"] == card.id for d in after.dropped))
            shown_after += int(any(x.id == card.id for x in after.cards))
        rows.append({"kind": kind, "source": "scripted", "n": n, "dropped": dropped, "shown_after": shown_after,
                     "drop_rate": _ratio(dropped, n), "drop_wilson": _wilson(dropped, n) if n else None})
    return {"rows": rows}


def _random_candidates(rng: random.Random, n: int) -> list[Candidate]:
    out = []
    for i in range(n):
        out.append(Candidate(kind=rng.choice(KINDS), title="t", why="w", numbers={}, source_tags=["routines"], risk_class="normal",
                             value=rng.random(), urgency=rng.random(), freshness=rng.random(), prepared_template={}, fire=FireSpec("queue"),
                             subject=f"s{rng.randrange(40)}", person="p_x", effort=rng.random()))
    return out


def _cap_stress(seed: int = 3, n_sets: int = 500) -> dict[str, Any]:
    rng = random.Random(seed)
    worst, kind_viol, zero = 0, 0, 0
    for _ in range(n_sets):
        res = J.rank(_random_candidates(rng, rng.randint(0, 40)), p_accept=lambda k: rng.random(), now_ts=0)
        worst = max(worst, len(res.selected))
        zero += int(not res.selected)
        counts: dict[str, int] = {}
        for r in res.selected:
            counts[r.candidate.kind] = counts.get(r.candidate.kind, 0) + 1
        kind_viol += int(any(v > J.MAX_PER_KIND[k] for k, v in counts.items()))
    return {"random_candidate_sets": n_sets, "largest_briefing": worst, "cap": J.CAP, "cap_violations": int(worst > J.CAP),
            "per_kind_limit_violations": kind_viol, "empty_briefings": zero}


def _press_sample(replays: list[Replay], workdir: Path, limit: int = 15) -> dict[str, Any]:
    """Prompted presses on a sample: each makes exactly one thing, and an irreversible card never starts a run."""
    queue_calls: list[dict[str, Any]] = []
    spawn_calls: list[Any] = []

    def q(**kw: Any) -> dict[str, Any]:
        queue_calls.append(kw)
        return {"id": f"q_eval{len(queue_calls):04d}"}

    def sp(kind: str, params: dict[str, Any], mode: str) -> dict[str, Any]:
        spawn_calls.append((kind, params, mode))
        return {"run_id": f"r_eval{len(spawn_calls):04d}"}

    pressed = both = neither = 0
    sample = [rp for rp in replays if rp.cards][:limit]
    for rp in sample:
        store = BriefingStore(workdir / f"press_{rp.point.source}_{rp.point.person}_{rp.point.index}.json")
        store.mutate(rp.point.person, lambda st, s=rp.store.person(rp.point.person): st.update(s))
        for c in rp.cards:
            try:
                out = F.fire(c.id, actor="worker", store=store, readers=rp.point.readers, now=rp.point.now, queue=q, spawn=sp)
            except F.FireError:
                continue
            pressed += 1
            has_q, has_r = "queue_id" in out, "run_id" in out
            both += int(has_q and has_r)
            neither += int(not has_q and not has_r)
    return {"presses": pressed, "queue_items": len(queue_calls), "agent_runs": len(spawn_calls), "presses_that_made_both": both,
            "presses_that_made_nothing": neither, "all_queue_items_pending_by_construction": True}


# ------------------------------------------------------------------------------------------------------------ baselines
def _baselines(replays: list[Replay], placebo_truth: dict[int, dict[str, set[str]]], kinds: tuple[str, ...], seeds: int = 200) -> dict[str, Any]:
    raw_rows, all_rows, rand_tot = [], [], {"tp": 0, "fp": 0, "fn": 0, "opp": 0}
    rng = random.Random(23)
    cards_all = []
    for rp in replays:
        cands = sorted(rp.candidates, key=lambda c: (-c.value, c.id))
        raw_rows.append(_score(_cand_subjects(cands[:J.CAP]), rp.point.truth, kinds))
        all_rows.append(_score(_cand_subjects(cands), rp.point.truth, kinds))
        cards_all.append(len(cands))
        for _ in range(seeds):
            pick = rng.sample(rp.candidates, min(J.CAP, len(rp.candidates)))
            s = _score(_cand_subjects(pick), rp.point.truth, kinds)
            for k in kinds:
                for f in rand_tot:
                    rand_tot[f] += s[k][f] / seeds
    mean_raw = float(np.mean([min(J.CAP, len(r.candidates)) for r in replays])) if replays else None
    return {"raw_value_top3_no_checks": {**_pr(_pool(raw_rows, kinds)), "mean_cards_per_briefing": round(mean_raw, 2) if mean_raw is not None else None,
                                         "note": "may show three cards of one kind, so its recall can be higher than the judge's, which limits each kind; its precision is far lower"},
            "random_3": {**{k: round(v, 2) for k, v in rand_tot.items()}, "precision": _ratio(rand_tot["tp"], rand_tot["tp"] + rand_tot["fp"]),
                         "recall": _ratio(rand_tot["tp"], rand_tot["tp"] + rand_tot["fn"]), "draws": seeds, "note": "mean over draws, no interval"},
            "everything_no_cap": {**_pr(_pool(all_rows, kinds)), "mean_cards_per_briefing": round(float(np.mean(cards_all)), 2) if cards_all else None}}


# ------------------------------------------------------------------------------------------------------------ acceptance (PRO-3)
def acceptance_simulation(seed: int = 9, workers: int = 200, ks: tuple[int, ...] = (0, 4, 10, 20, 40)) -> dict[str, Any]:
    """A simulated worker with fixed accept rates per kind: how close the per-kind estimate gets after k labels (a label is one
    press or one dismissal), and whether the kinds come out in the right order. Simulated, not people."""
    rng = np.random.default_rng(seed)
    kinds = list(ACCEPT_TRUE)
    true = np.array([ACCEPT_TRUE[k] for k in kinds])
    rows = []
    for k in ks:
        maes, taus = [], []
        for _ in range(workers):
            m = AcceptanceModel()
            for _ in range(k):
                i = int(rng.integers(0, len(kinds)))
                m.observe(kinds[i], bool(rng.random() < true[i]))
            est = np.array([m.p(x) for x in kinds])
            maes.append(float(np.mean(np.abs(est - true))))
            from scipy.stats import kendalltau

            tau = kendalltau(est, true).statistic if k else float("nan")
            taus.append(float(tau) if tau == tau else 0.0)
        rows.append({"labels": k, "mean_abs_error": round(float(np.mean(maes)), 3),
                     "mae_interval": [round(float(np.percentile(maes, 2.5)), 3), round(float(np.percentile(maes, 97.5)), 3)],
                     "rank_agreement_tau": None if k == 0 else round(float(np.mean(taus)), 3),
                     "tau_interval": None if k == 0 else [round(float(np.percentile(taus, 2.5)), 3), round(float(np.percentile(taus, 97.5)), 3)]})
    return {"true_rates": ACCEPT_TRUE, "workers": workers, "rows": rows,
            "note": "Generated worker with fixed accept rates; the estimate starts at the role prior (0.4) and moves with each label. "
                    "Real acceptance behaviour has not been measured on any person."}


# ------------------------------------------------------------------------------------------------------------ limitations
def proactive_limitations() -> list[dict[str, str]]:
    return [
        {"id": "pro-synthetic", "severity": "high",
         "text": "Every figure for the proactive layer comes from generated personas, learners and git learners with planted structure we wrote. "
                 "It shows that the judge, verify and prepare steps recover what was planted, not that real workers would find these cards useful."},
        {"id": "pro-truth-ours", "severity": "high",
         "text": "The definition of 'worth surfacing' is ours and was fixed before the runs (see the output). For the personas, the planted skill is mapped to "
                 "a level and fed to both the gate and the truth, so agreement on practice cards for personas is partly built in; the learner and git truths are "
                 "more independent of the code under test."},
        {"id": "pro-iterated-on-eval", "severity": "high",
         "text": "The truth definitions and one part of the practice scoring were revised after looking at the first replays (listed under design.truth_revisions "
                 "and design.code_revision, with the first-run figures). There is no held-out data: the reported precision and recall are development-set "
                 "figures on the same generated personas and learners, and are optimistic for that reason."},
        {"id": "pro-weights-handset", "severity": "medium",
         "text": "The ranking weights, the minimum score of 0.30, the cap of three and the per-kind limits are hand-set constants, not fitted to any data. "
                 "A different choice would move precision and recall; no sensitivity sweep is claimed."},
        {"id": "pro-small-n", "severity": "high",
         "text": "There are 4 personas, 3 learners and 4 git learners, with several decision points each. Decision points inside one person are correlated, so the "
                 "pooled Wilson intervals are too narrow; the person-level bootstrap is the honest interval and it is wide."},
        {"id": "pro-capacity-recall", "severity": "medium",
         "text": "Recall is capped at what the judge is allowed to show of each kind (one practice card, one git card, two automations): a person with three "
                 "planted git habits is credited for finding one. That is the design, not a flaw in the metric, but it hides how much was left unsaid."},
        {"id": "pro-calendar-truth", "severity": "medium",
         "text": "Calendar cards are scored against the calendar track's planted problems; the suggestion thresholds and the planted structure come from the same "
                 "generator family, and a week can carry several planted problems of which the judge may show one. Finished-run cards are covered by scripted "
                 "checks only, and so are stale calendar and git cards."},
        {"id": "pro-acceptance-simulated", "severity": "high",
         "text": "Acceptance learning is shown on a generated worker with fixed rates. It has not been validated on people, and a real person's accepts and "
                 "declines may depend on time of day, mood and the card's wording, none of which are modelled."},
        {"id": "pro-rules-not-model", "severity": "low",
         "text": "No model decides what is surfaced; a model may reword the reason line through the egress guard. Wording quality is not evaluated here."},
        {"id": "pro-stale-injected", "severity": "medium",
         "text": "Staleness is injected by changing a reading (a routine switched on, a skill at level 4). Real staleness has more forms, and a source that "
                 "cannot be read is never treated as stale, which can leave a card up for a few hours after it stopped being true."},
    ]


# ------------------------------------------------------------------------------------------------------------ the entry point
def evaluate_proactive(fast: bool = False, *, root: Path | str | None = None) -> dict[str, Any]:
    """Run the replay and return ``{meta, design, structure, stale, worth, acceptance, coverage, limitations}``.
    Hermetic: its own temporary data directory and home; reads the shared synthetic data only."""
    from ..trust.meta import analytic_meta

    root = Path(root) if root else data_dir()
    days = (3, 10, 21) if fast else (1, 2, 3, 5, 7, 10, 14, 17, 21)
    cases = (5, 15, 30) if fast else (3, 6, 10, 15, 20, 25, 30)
    draws = 300 if fast else 600
    with tempfile.TemporaryDirectory(prefix="understudy-proactive-eval-") as td:
        tmp = Path(td)
        data, home, work = tmp / "data", tmp / "home", tmp / "work"
        (data / "synthetic" / "git").mkdir(parents=True)
        home.mkdir()
        work.mkdir()
        for p in (root / "synthetic").iterdir() if (root / "synthetic").exists() else []:
            if p.is_dir() and p.name != "git":
                (data / "synthetic" / p.name).symlink_to(p.resolve())
        with _env(UNDERSTUDY_DATA_DIR=str(data), UNDERSTUDY_HOME=str(home), UNDERSTUDY_X_GIT="1", UNDERSTUDY_MOCK="1"):
            os.environ.pop("UNDERSTUDY_X_PROACTIVE", None)
            pts = persona_points(data, days if not fast else days, draws, work)
            if fast:
                pts = [p for p in pts if p.group in ("p_ninetofive", "p_nightowl")]
            pts += learner_points(data, cases)
            if fast:
                pts = [p for p in pts if p.source != "learner" or p.group in ("p_learn01", "p_learn02")]
            gpts = git_points(data, only=2 if fast else None)
            cpts = calendar_points(data, latest_only=fast, fast_people=("p_ninetofive", "p_nightowl", "p_shiftwkr", "p_irregular", "p_exp01", "p_exp02") if fast else None)
            all_pts = pts + gpts + cpts
            if not all_pts:
                return {"meta": analytic_meta("synthetic", 0, "decisions", None, "No generated data was found, so nothing was replayed."),
                        "status": "not_run", "limitations": proactive_limitations()}
            with _Spy() as spy:
                replays = [_replay(p, work) for p in all_pts]
            queue_files = len(list((data / "queue").glob("*.json"))) if (data / "queue").exists() else 0
            drafts = len(list((data / "briefing" / "drafts").glob("*.json"))) if (data / "briefing" / "drafts").exists() else 0
            sizes = [len(r.cards) for r in replays]
            structure = {
                "briefings": len(replays), "largest_briefing": max(sizes), "cap": J.CAP, "cap_violations": sum(1 for s in sizes if s > J.CAP),
                "empty_briefings": sum(1 for s in sizes if s == 0), "mean_cards": round(float(np.mean(sizes)), 2),
                "unprompted_fires": spy.calls["fire"], "unprompted_queue_port_uses": spy.calls["queue_port"], "unprompted_agent_spawns": spy.calls["spawner"],
                "queue_items_on_disk_after_replay": queue_files, "draft_files_after_replay": drafts,
                "cap_stress": _cap_stress(), "prompted_presses": _press_sample(replays, work)}
            stale = _stale_tests(replays, work)

            # worth surfacing
            def rows_of(rs: list[Replay], kinds: tuple[str, ...]) -> list[dict[str, dict[str, int]]]:
                return [_score(_subjects(r.cards), r.point.truth, kinds) for r in rs]

            by_group: dict[str, list[dict[str, dict[str, int]]]] = {}
            for r in replays:
                by_group.setdefault(r.point.group, []).append(_score(_subjects(r.cards), r.point.truth))
            allk = rows_of(replays, EVAL_KINDS)
            worth: dict[str, Any] = {"overall": {**_pr(_pool(allk)), **_cluster_boot(by_group, EVAL_KINDS)}, "by_kind": {}, "by_source": {}, "by_person": []}
            for kind in EVAL_KINDS:
                sub = [r for r in replays if kind in r.point.truth]
                if not sub:
                    continue
                grp: dict[str, list] = {}
                for r in sub:
                    grp.setdefault(r.point.group, []).append(_score(_subjects(r.cards), r.point.truth, (kind,)))
                worth["by_kind"][kind] = {**_pr(_pool(rows_of(sub, (kind,)), (kind,))), **_cluster_boot(grp, (kind,)), "briefings": len(sub)}
            for source in ("persona", "learner", "git", "calendar"):
                sub = [r for r in replays if r.point.source == source]
                if sub:
                    worth["by_source"][source] = {**_pr(_pool(rows_of(sub, EVAL_KINDS))), "briefings": len(sub)}
            for g in sorted(by_group):
                worth["by_person"].append({"person": g, "source": next(r.point.source for r in replays if r.point.group == g), **_pr(_pool(by_group[g])),
                                           "briefings": len(by_group[g])})
            quiet = [r for r in replays if not any(r.point.truth.get(k) for k in EVAL_KINDS)]
            worth["quiet_when_nothing_worth"] = {"points": len(quiet), "no_card": sum(1 for r in quiet if not r.cards),
                                                 "rate": _ratio(sum(1 for r in quiet if not r.cards), len(quiet)),
                                                 "wilson": _wilson(sum(1 for r in quiet if not r.cards), len(quiet)) if quiet else None}
            worth["points"] = [{"person": r.point.group, "source": r.point.source, "at": r.point.label,
                                "surfaced": [{"kind": c.kind, "subject": c.subject, "score": round(c.score, 3)} for c in r.cards],
                                "truth": {k: sorted(v) for k, v in r.point.truth.items() if v},
                                "candidates": len(r.candidates)} for r in replays]
            worth["baselines"] = _baselines(replays, {}, EVAL_KINDS)
            # placebo: the same cards scored against another person's truth at the same decision point
            plc = []
            for src in ("persona", "learner", "git", "calendar"):
                grp = [r for r in replays if r.point.source == src]
                labels: dict[str, list[Replay]] = {}
                for r in grp:
                    labels.setdefault(r.point.label, []).append(r)
                for lab, rs in labels.items():
                    if len(rs) < 2:
                        continue
                    for i, r in enumerate(rs):
                        other = rs[(i + 1) % len(rs)]
                        plc.append(_score(_subjects(r.cards), other.point.truth))
            worth["placebo_other_persons_truth"] = _pr(_pool(plc)) if plc else None
            # sensitivity of the persona practice truth to its definition
            variants: dict[str, Callable[[float], bool]] = {
                "level_1_or_2_only": lambda sk: sk < SKILL_L3,
                "any_gap_below_level_4": lambda sk: sk < SKILL_L4}
            sens: dict[str, Any] = {}
            for name, rule in variants.items():
                rows = []
                for r in replays:
                    if r.point.source != "persona":
                        continue
                    rows.append(_score(_subjects(r.cards), {**r.point.truth, "practice": {WILDCARD} if rule(r.point.extra["skill"]) else set()}, ("practice",)))
                sens[name] = _pr(_pool(rows, ("practice",))) if rows else None
            worth["sensitivity_persona_practice_truth"] = sens
            hand = [_score(_subjects(r.cards), {**r.point.truth, "practice": r.point.extra["hand_truth"]}, ("practice",))
                    for r in replays if r.point.source == "learner"]
            worth["sensitivity_learner_practice_truth_hand_mapping"] = _pr(_pool(hand, ("practice",))) if hand else None
        meta = analytic_meta("synthetic", len(replays), "decisions", "replay at fixed decision points; rules, nothing trained",
                             "Generated personas, learners and git learners with planted truth. Intervals: Wilson on pooled counts (too narrow, points are "
                             "correlated) and a bootstrap over people (the honest one).")
    return {
        "meta": meta,
        "design": {"decision_points": {"persona_days": list(days), "learner_cases": list(cases), "git": "one per git learner",
                                       "calendar": "one per person and week (28 people, 3 weeks; 8 experts are negatives)" if not fast else "latest week of 4 personas and 2 experts"},
                   "judge": {"weights": J.WEIGHTS, "effort_penalty": J.EFFORT_PENALTY, "min_score": J.MIN_SCORE, "cap": J.CAP,
                             "max_per_kind": J.MAX_PER_KIND, "cooldown_days": J.COOLDOWN_DAYS},
                   "truth": {"automate": f"a planted routine of kind {'/'.join(AUTOMATABLE_KINDS)}, at least {MIN_INSTANCES} seen and {MIN_MPW:g} min a week so far; "
                                         f"calc3 also needs planted skill >= {SKILL_L4}",
                             "practice_personas": f"planted skill < {SKILL_L3} (level 1 or 2)",
                             "practice_learners": f"a curriculum skill whose cogs overlap the cogs of a planted deficit with probability >= {LEARNER_P_GAP} per case (cogs as listed in the truth file)",
                             "git_habit": "a habit planted in the learner's repository, through its catalogue template",
                             "focus_block": "a problem planted in that person's calendar week (fragmented days, no focus blocks, back-to-back runs, recurring meetings in "
                                            "peak hours, no review slot, no breaks, unbuffered external calls, late meetings), through the matching suggestion template; "
                                            "no focus-block problem planted in a week or in any expert's calendar means no card is worth showing"},
                   "truth_revisions": [{"what": "automate: minutes so far over a calendar week (15) replaced by the planted weekly minutes (10) with at least 8 sightings",
                                        "why": "the first definition under-counted routines early in the window", "after_seeing": "first fast replay"},
                                       {"what": "practice for learners: the hand-written deficit-to-skill map (3 skills) replaced by the truth file's own cog lists per deficit",
                                        "why": "the hand map ignored that the skipped-check deficit re-enters the household and the copy deficit lives in the reconcile cog",
                                        "after_seen": "first full replay (learner precision 0.06, recall 0.11)"},
                                       {"what": "practice for personas: added the unlock clause (below 0.85 while a worthwhile calc3 routine is held back by the gate)",
                                        "why": "the product's rule is coach first, then automate", "after_seeing": "first fast replay"}],
                   "first_run_numbers": {"note": "first full replay, before any revision", "overall": {"precision": 0.721, "recall": 0.803},
                                         "learners": {"precision": 0.059, "recall": 0.111}, "personas": {"precision": 0.936, "recall": 0.917}},
                   "code_revision": {"what": "practice value now weighs recent errors in the tracker window, ignores teaching-order prerequisites for a skill the worker is "
                                             "visibly getting wrong, and halves the value of a skill with no counted attempts",
                                     "why": "the first full replay surfaced skills the learner had no evidence of struggling with", "after_seeing": "first full replay"},
                   "replay": "Each point cuts the data at that time, runs the real finder, skill tracker or git analysis, then the real judge, verify and prepare; "
                             "no press is ever invented inside the replay."},
        "structure": structure, "stale": stale, "worth": worth, "acceptance": acceptance_simulation(workers=100 if fast else 200),
        "coverage": {"automate": "evaluated (personas)", "practice": "evaluated (personas and learners)", "git_habit": "evaluated (git learners)",
                     "focus_block": "evaluated (calendar track's planted problems); stale checks scripted",
                     "agent_result": "scripted stale checks only"},
        "limitations": proactive_limitations(),
    }


if __name__ == "__main__":  # python -m understudy_engine.proactive.evaluate [--fast]
    import sys

    print(json.dumps(evaluate_proactive(fast="--fast" in sys.argv), indent=1))
