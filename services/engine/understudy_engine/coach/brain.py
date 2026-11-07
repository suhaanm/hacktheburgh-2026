"""The live coach: events in, one decision out (COA-3, COA-4, PR1: code decides, no model call).

For one person it keeps a small state folded from their events in time order:

  - the open task window (events since the last ``task_start``) and a SkillTracker built from finished tasks;
  - the dignity gate state (consecutive signals, last time the coach spoke);
  - what was shown and how the worker answered.

``next_step(person, now)`` maps the open window to cogs (``cogs`` module, the pack's mapping), checks them against the
pack's expert policy (``steps``), and turns what it sees into a signal:

  expert_policy   a step was started before a critical step it needs was done (the signature case: copying toward
                  the note without the cliff check)
  stuck           the hazard model's P(no progress in the next minute) is at or above the gate threshold

``policy.gate`` (two consecutive signals, a cooldown, silent when unsure) decides whether the coach may speak at all.
The level engine (``skills.SkillTracker``) decides how much help: L1 annotate with a ring target, L2 one-line nudge,
L3 a dot (silent, the text waits behind it), L4 silent unless the worker asks. A takeover is only ever an *offer*.
Every acting decision is recorded as a ``coach_shown`` event; ``feedback`` records the worker's answer as
``coach_followed`` / ``coach_dismissed`` and feeds the skill state (assisted runs are neutral).
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..cogs import to_cogs
from ..core import Cog, Event
from ..packs import PackError, load_pack
from ..policy.gate import GateParams, GateState, gate_step
from ..skills import SkillTracker
from ..store import EventStore, fmt_t
from ..study.state import StudyMode, read_state
from .messages import message_for, target_for

from .models import OUTCOMES, CoachDecision
from .signals import StuckScorer
from .skillstate import cog_outcomes, fold_episode
from .steps import Progress, StepPolicy

GATE = GateParams(need=2, cooldown_s=120.0, p_signal=0.6, min_confidence=0.5)
GATE_CLOCK = "events"             # see CoachBrain.gate_clock; "polls" is the original one-signal-per-poll rule
AWAY_S = 90.0                     # no event for this long: the worker is away, the coach is unsure and silent
FOLLOW_WINDOW_S = 30.0            # a missed step done this soon after a prompt counts as followed
RULE_CONFIDENCE = 0.9
# sessions without task markers: a case opens at the first calculator page after a quiet spell and closes after the note or a long idle
IMPLICIT_START_GAP_S = 120.0
IMPLICIT_CLOSE_IDLE_S = 600.0
IMPLICIT_NOTE_IDLE_S = 120.0


class CoachError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _ts(now: datetime | float | None) -> float:
    if now is None:
        return time.time()
    if isinstance(now, datetime):
        return (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).timestamp()
    return float(now)


def _iso(t: float) -> str:
    return fmt_t(datetime.fromtimestamp(t, tz=timezone.utc))


@dataclass(frozen=True)
class CogView:
    """One cog of the open window: its id and when it started (unix seconds). No event payloads."""
    id: str
    t0: float


@dataclass(frozen=True)
class SkillView:
    """What the level engine and the tracer hold for one cog."""
    cog: str
    level: int
    mastery: float


@dataclass(frozen=True)
class CoachSnapshot:
    """A read-only picture of one person's live state for other engines (the cue engine). Immutable, plain values only: no events,
    no payloads, nothing to mutate. ``p_source`` is "model" (the hazard model) or "rule" (the time-since-progress fallback)."""
    person: str
    t: float
    role: str
    origin: str
    task_open: bool
    task_id: str | None
    implicit: bool
    cogs: tuple[CogView, ...]
    current_cog: str | None
    last_progress_t: float | None
    last_input_t: float | None
    p_stuck: float | None
    p_source: str | None
    skills: tuple[SkillView, ...]
    tasks_finished: int


@dataclass
class _Bundle:
    pack: object
    policy: StepPolicy
    mapping: object
    curriculum: dict


@dataclass
class _Record:
    person: str
    task_id: str | None
    step: str
    cogs: tuple[str, ...]
    t: float
    level: int
    origin: str
    role: str
    labelled: str | None = None
    block: str | None = None          # study mode: "train"
    skill: str | None = None


@dataclass
class _Person:
    person: str
    role: str = "benefits-processor"
    origin: str = "real"
    open: list[Event] | None = None
    open_task: str | None = None
    tracker: SkillTracker = field(default_factory=SkillTracker)
    gate: GateState = field(default_factory=GateState)
    last_key: tuple[float, str] = (-1.0, "")
    last_event_t: float = 0.0
    followed: dict[str, set[str]] = field(default_factory=dict)       # task -> steps done after a followed prompt
    assisted_done: dict[str, set[str]] = field(default_factory=dict)  # task -> steps already counted as assisted
    unfollowed: dict[str, dict[str, int]] = field(default_factory=dict)   # task -> step -> times the worker did not follow
    repeated: dict[str, set[str]] = field(default_factory=dict)       # task -> steps whose issue recurred right after a prompt
    prompted: dict[str, set[str]] = field(default_factory=dict)       # task -> steps already prompted this task
    offered: dict[str, set[str]] = field(default_factory=dict)        # task -> steps already offered a takeover
    own_ids: set[str] = field(default_factory=set)
    n_tasks: int = 0
    implicit: bool = False               # the open window was opened by the zone fallback, not by a task_start marker
    last_calc_nav_t: float = 0.0         # the last calculator page opened (any window state)
    closed_flag: bool = False            # a case was closed since the last calculator page: the next one starts a new case


class CoachBrain:
    def __init__(self, store: EventStore | None = None, *, scorer: StuckScorer | None = None, gate: GateParams = GATE,
                 tone: str | None = None, away_s: float = AWAY_S, root: Path | str | None = None, gate_clock: str | None = None) -> None:
        self.store = store or EventStore(root)
        self.scorer = scorer if scorer is not None else StuckScorer(root)
        self.gate = gate
        self.tone = tone                      # None: read the worker's memory preference
        self.away_s = away_s
        # "events": a policy signal counts one for every worker event since the violation began (event timestamps), so a prompt
        # can arrive after one poll when two signals are already in the window. "polls": one per poll (the original rule).
        self.gate_clock = (gate_clock or os.environ.get("UNDERSTUDY_COACH_GATE") or GATE_CLOCK).lower()
        if self.gate_clock not in ("events", "polls"):
            raise ValueError("gate_clock must be 'events' or 'polls'")
        self._people: dict[str, _Person] = {}
        self._bundles: dict[str, _Bundle | None] = {}
        self._records: dict[str, _Record] = {}
        self._lock = threading.RLock()
        self._variants: dict = {}
        self._tone_cache: tuple[float, str] | None = None

    # ------------------------------------------------------------------ packs and tone
    def _bundle(self, role: str) -> _Bundle | None:
        if role not in self._bundles:
            try:
                pack = load_pack(role)
                policy = StepPolicy.from_pack(pack)
                try:
                    curriculum = pack.file("curriculum")
                except PackError:
                    curriculum = {}
                self._bundles[role] = _Bundle(pack, policy, pack.cog_mapping(), curriculum)
            except (PackError, KeyError, FileNotFoundError):
                self._bundles[role] = None
        return self._bundles[role]

    def _study(self, person: str) -> StudyMode | None:
        """Study mode for this person, if the facilitator has switched it on (data/study/state.json)."""
        mode = read_state()
        return mode if (mode is not None and mode.person == person) else None

    def _policy(self, bundle: _Bundle, mode: StudyMode | None) -> StepPolicy:
        if mode is None or not mode.steps_off:
            return bundle.policy
        key = (id(bundle), mode.steps_off)
        if key not in self._variants:
            self._variants[key] = bundle.policy.without(mode.steps_off)
        return self._variants[key]

    def _tone(self) -> str:
        if self.tone:
            return self.tone
        try:
            from ..memory import MemoryStore
            ms = MemoryStore()
            mtime = ms.path.stat().st_mtime if ms.path.exists() else 0.0
            if self._tone_cache and self._tone_cache[0] == mtime:
                return self._tone_cache[1]
            sec = ms.read().section("Preferences", create=False)
            detailed = any("Summaries: detailed" in ln.text for ln in (sec.lines() if sec else []))
            self._tone_cache = (mtime, "detailed" if detailed else "short")
            return self._tone_cache[1]
        except Exception:
            return "short"

    # ------------------------------------------------------------------ folding events
    def _state(self, person: str) -> _Person:
        st = self._people.get(person)
        if st is None:
            st = self._people[person] = _Person(person)
        return st

    def reset(self, person: str | None = None) -> None:
        with self._lock:
            if person is None:
                self._people.clear()
                self._records.clear()
            else:
                self._people.pop(person, None)

    def feed(self, person: str, events, upto: float | None = None) -> int:
        """Fold events (time ordered) into the person's state. Events at or before what was already seen are skipped,
        and so are events after ``upto``. Returns how many were applied."""
        n = 0
        with self._lock:
            st = self._state(person)
            for ev in events:
                if ev.person != person:
                    continue
                key = (ev.t.timestamp(), ev.id)
                if key <= st.last_key:
                    continue
                if upto is not None and key[0] > upto:
                    break
                self._apply(st, ev)
                st.last_key = key
                n += 1
        return n

    def _apply(self, st: _Person, ev: Event) -> None:
        t = ev.t.timestamp()
        st.role, st.origin = ev.role, ev.origin
        if ev.type in ("coach_shown", "coach_followed", "coach_dismissed"):
            self._apply_coach_event(st, ev)
            if st.open is not None and ev.task_id in (None, st.open_task):
                st.open.append(ev)
            return
        prev_t = st.last_event_t
        st.last_event_t = max(st.last_event_t, t)
        if ev.type == "task_start":
            st.open, st.open_task, st.implicit = [ev], ev.task_id, False
            if ev.task_id:
                self._reset_task(st, ev.task_id)
            return
        if st.open is not None and st.implicit and prev_t > 0 and t - prev_t >= IMPLICIT_CLOSE_IDLE_S:
            self._finish_task(st, prev_t)                         # ten minutes of nothing: that case is over
        is_calc_nav = ev.type == "nav" and ev.meta.get("zone") == "calc_site"
        last_calc = st.last_calc_nav_t
        if is_calc_nav:
            st.last_calc_nav_t = t
        if st.open is None:
            # no marker: a case opens at the first calculator page after a quiet spell, after a closed case, or after ten minutes
            # away from the calculators (reading the record just before does not stop it)
            if (ev.task_id is None and is_calc_nav
                    and (prev_t <= 0 or t - prev_t >= IMPLICIT_START_GAP_S or st.closed_flag or t - last_calc >= IMPLICIT_CLOSE_IDLE_S)):
                st.open, st.open_task, st.implicit, st.closed_flag = [ev], f"t_imp{int(t)}", True, False
                self._reset_task(st, st.open_task)
            return
        if ev.task_id not in (None, st.open_task):
            return
        st.open.append(ev)
        if ev.type == "task_end" or (st.implicit and ev.type == "progress" and ev.meta.get("kind") == "note_field"):
            self._finish_task(st, t)

    @staticmethod
    def _reset_task(st: _Person, task_id: str) -> None:
        for d in (st.followed, st.assisted_done, st.unfollowed, st.repeated, st.prompted, st.offered):
            d.pop(task_id, None)

    def _apply_coach_event(self, st: _Person, ev: Event) -> None:
        if ev.id in st.own_ids:
            return
        meta, task = ev.meta, ev.task_id
        if ev.type == "coach_shown" and ev.actor == "agent":
            st.gate = GateState(0, ev.t.timestamp())                   # restart-safe: the cooldown and what was said come from the log
            step_id = meta.get("step")
            bundle = self._bundle(ev.role)
            if task and isinstance(step_id, str) and bundle and step_id in bundle.policy.steps:
                mates = bundle.policy.pattern_mates(step_id)
                st.prompted.setdefault(task, set()).update(mates)
                if meta.get("action") == "takeover_offer":
                    st.offered.setdefault(task, set()).update(mates)
            return
        step = meta.get("step")
        if not task or not isinstance(step, str):
            return
        if ev.type == "coach_followed":
            st.followed.setdefault(task, set()).add(step)
        else:
            st.unfollowed.setdefault(task, {}).setdefault(step, 0)
            st.unfollowed[task][step] += 1
            if meta.get("outcome") == "repeated":
                st.repeated.setdefault(task, set()).add(step)

    def _finish_task(self, st: _Person, t: float) -> None:
        bundle = self._bundle(st.role)
        window, task = st.open or [], st.open_task
        st.open, st.open_task, st.implicit, st.closed_flag = None, None, False, True
        if bundle is None or not task:
            return
        cogs = to_cogs(window, bundle.mapping)
        policy = self._policy(bundle, self._study(st.person))
        prog = policy.track(cogs, self._sites(window, cogs))
        outcomes = cog_outcomes(policy, prog, st.followed.get(task, ()), st.assisted_done.get(task, ()))
        fold_episode(st.tracker, outcomes, t)
        st.n_tasks += 1

    @staticmethod
    def _sites(window: list[Event], cogs: list[Cog]) -> list[str | None]:
        """The site token of the nav event that opened each OPEN_CALCULATOR cog (None when the cog is not a calculator)."""
        navs = sorted((e.t.timestamp(), e.meta.get("site")) for e in window if e.type == "nav" and e.meta.get("site"))
        out: list[str | None] = []
        for c in cogs:
            site = None
            if c.id == "OPEN_CALCULATOR":
                for tt, s in navs:
                    if abs(tt - c.t0) < 1.0:
                        site = str(s)
                        break
            out.append(site)
        return out

    def _sync(self, st: _Person, now: float) -> None:
        for part in ("real", "synthetic"):
            since = _iso(st.last_key[0]) if st.last_key[0] > 0 else None
            evs = self.store.read(part, person=st.person, since=since)
            self.feed(st.person, evs, upto=now)

    # ------------------------------------------------------------------ the decision
    def next_step(self, person: str, now: datetime | float | None = None, *, events=None, commit: bool = True, ask: bool = False,
                  tone: str | None = None) -> CoachDecision:
        with self._lock:
            return self._next_step(person, _ts(now), events, commit, ask, tone)

    def _next_step(self, person: str, now: float, events, commit: bool, ask: bool, tone: str | None) -> CoachDecision:
        st = self._state(person)
        if now < st.last_event_t - 1e-6 and events is None:
            self._people.pop(person, None)                    # time went backwards (a replay restarted): rebuild from the store
            st = self._state(person)
        if events is not None:
            self.feed(person, events, upto=now)
        else:
            self._sync(st, now)
        dec = CoachDecision(person=person, t=_iso(now), task_id=st.open_task)
        if st.last_key[0] <= 0:
            dec.reason_codes = ["no_events"]
            return dec
        bundle = self._bundle(st.role)
        if bundle is None:
            dec.reason_codes = ["no_pack"]
            return dec
        study = self._study(person)
        if study is not None and not study.coaching:             # post_test, off, or train with nothing switched on: always silent
            dec.level, dec.chip = "L4", "gone"
            dec.reason_codes = ["study_mode", f"study_{study.block}"]
            return dec
        policy = self._policy(bundle, study)
        only_skill = study.skill_id if study else None
        ask = ask and study is None                              # in a study block the coach does not speak when asked
        if st.open is None:
            lvl, chip, mast = self._overall(st, bundle, now)
            dec.level, dec.chip, dec.mastery = f"L{lvl}", chip, mast
            dec.reason_codes = ["no_active_task"]
            st.gate = GateState(0, st.gate.last_act_t)
            return dec

        window = [e for e in st.open if e.t.timestamp() <= now]
        cogs = to_cogs(window, bundle.mapping)
        if st.implicit:
            idle = now - st.last_event_t
            if idle >= IMPLICIT_CLOSE_IDLE_S or (cogs and cogs[-1].id == "COPY_TO_NOTE" and idle >= IMPLICIT_NOTE_IDLE_S):
                self._finish_task(st, st.last_event_t)           # the note is written, or the worker left: the case is closed
                lvl, chip, mast = self._overall(st, bundle, now)
                dec.level, dec.chip, dec.mastery, dec.task_id = f"L{lvl}", chip, mast, None
                dec.reason_codes = ["no_active_task"]
                return dec
            dec.reason_codes.append("implicit_task")
        prog = policy.track(cogs, self._sites(window, cogs))
        task = st.open_task or ""
        self._auto_label(st, prog, now, commit)

        # --- the signal
        # one prompt per step pattern per task, unless the issue recurred right after a prompt (then one takeover offer)
        exclude = (st.prompted.get(task, set()) - st.repeated.get(task, set())) | st.offered.get(task, set())
        missed_id, violating, missing_all, viol_t = None, None, [], None
        for v in reversed(prog.unresolved()):
            cand = policy.pick_missed(v.missing, prog, exclude=tuple(exclude), only_skill=only_skill)
            if cand is not None:
                missed_id, violating, missing_all, viol_t = cand, policy.steps[v.step], list(v.missing), v.t
                break
        if missed_id is None and any(policy.pick_missed(v.missing, prog, only_skill=only_skill) for v in prog.unresolved()):
            dec.reason_codes.append("already_prompted")                    # the worker has seen it; do not nag
        current_id = prog.current or (policy.next_ready(prog) or [None])[0]
        dec.step = current_id
        away = (now - st.last_event_t) > self.away_s
        p_stuck, p_src = self.scorer.p_stuck(cogs=cogs, progress_t=[e.t.timestamp() for e in window if e.type == "progress"],
                                             t0=window[0].t.timestamp(), now=now, person=person, role=st.role)
        dec.p_stuck, dec.p_source = round(p_stuck, 4), p_src
        cur = policy.steps.get(current_id) if current_id else None
        occ = prog.occurrences.get(current_id) if current_id else None
        in_step_s = (now - occ.t0) if occ else None
        slow = in_step_s is None or cur is None or cur.median_s is None or in_step_s >= cur.median_s     # longer than the expert takes

        trigger, signal_p, conf, step_id = None, 0.0, 0.0, None
        if missed_id is not None:
            trigger, signal_p, conf, step_id = "expert_policy", 1.0, RULE_CONFIDENCE, missed_id
            dec.missed = [missed_id] + [m for m in missing_all if m != missed_id and policy.steps[m].critical
                                        and (only_skill is None or policy.steps[m].skill == only_skill)]
        elif (p_stuck >= self.gate.p_signal and current_id is not None and slow and current_id not in exclude
              and (only_skill is None or (cur is not None and cur.skill == only_skill))):
            trigger, signal_p, conf, step_id = "stuck", p_stuck, p_stuck, current_id
        if ask and step_id is None:
            step_id = current_id or (policy.next_ready(prog) or [None])[0]
            trigger = "ask" if step_id else None

        step = policy.steps.get(step_id) if step_id else None
        cur_step = policy.steps.get(current_id) if current_id else None
        cogs_for_level = list(step.cogs) if step else (list(cur_step.cogs) if cur_step else [c for s in policy.steps.values() if s.critical for c in s.cogs])
        cs = st.tracker.coach_state(cogs_for_level, now)
        level = int(cs["level"][1:])
        dec.level, dec.chip, dec.mastery = cs["level"], cs["chip"], {k: round(v, 3) for k, v in cs["mastery"].items()}
        if study is not None:                                   # the facilitator fixes the help level for the block
            level = study.level_n
            dec.level, dec.chip = study.level, {1: "full", 2: "small", 3: "dot", 4: "gone"}[level]
        dec.confidence = round(conf, 3)
        tone_v = tone or self._tone()

        if trigger is not None and step is not None:
            kind = "annotate" if (level <= 1 and trigger == "expert_policy") else "nudge"
            msg, why = message_for(kind, missed=step if trigger == "expert_policy" else None, violating=violating, current=step,
                                   level=level, tone=tone_v, curriculum=bundle.curriculum, stuck=(trigger == "stuck"))
            tgt = target_for(step, bundle.mapping, site=self._site_for(prog, step.id, policy))
            dec.candidate = {"action": kind, "message": msg, "why": why, "target": tgt if kind == "annotate" else None, "missed": dec.missed,
                             "trigger": trigger, "step": step.id}
        dec.trigger = trigger

        # --- who may speak: level first (a quiet level never burns the cooldown), then the gate
        if trigger is None:
            gd = gate_step(st.gate, 0.0, now, unsure=away, confidence=None, params=self.gate)
            if commit:
                st.gate = gd.state
            dec.gate = {"consecutive": gd.state.consecutive, "reason": "unsure" if away else "on_track"}
            dec.reason_codes.append("unsure_away" if away else "on_track")
            return dec
        dec.reason_codes.append("policy_violation" if trigger == "expert_policy" else ("asked" if trigger == "ask" else "stuck_signal"))
        if trigger == "expert_policy":
            dec.reason_codes.append("critical_step_missed")
        if ask and trigger in ("ask", "expert_policy", "stuck"):
            return self._act(st, dec, bundle, step, violating, "nudge", 2, tone_v, now, commit, bypass=True, trigger=trigger)
        if level >= 3:
            dec.reason_codes.append(f"level_{level}")
            if level == 3 and dec.candidate:
                dec.message = message_for("silent", missed=step, violating=violating, current=step, level=3,
                                          tone=tone_v, curriculum=bundle.curriculum)[0]
                dec.why = dec.candidate["why"]
            return dec
        gate_in = st.gate
        if self.gate_clock == "events" and trigger == "expert_policy" and viol_t is not None:
            # two worker events since the violation began are two signals, whenever the polls happen to land
            n_since = sum(1 for e in window if e.source != "coach" and e.type not in ("progress", "task_start", "task_end")
                          and e.t.timestamp() >= viol_t)
            prior = min(self.gate.need - 1, max(0, n_since - 1))
            if prior > gate_in.consecutive:
                gate_in = GateState(prior, gate_in.last_act_t)
        gd = gate_step(gate_in, signal_p, now, unsure=away, confidence=conf, params=self.gate)
        if commit:
            st.gate = gd.state
        dec.gate = {"consecutive": gd.state.consecutive, "reason": gd.reason}
        if not gd.act:
            dec.reason_codes.append(f"gate_{gd.reason}")
            return dec
        if not commit:                                   # a look, not a prompt: say what would happen, change nothing
            dec.reason_codes.append("dry_run_would_act")
            return dec
        dec.reason_codes.append("gate_act")
        action = "annotate" if (level <= 1 and trigger == "expert_policy") else "nudge"        # a stuck worker gets a question, not a ring
        if step.id in st.repeated.get(task, set()) and trigger == "expert_policy":
            action = "takeover_offer"
            dec.reason_codes.append("issue_repeated")
        return self._act(st, dec, bundle, step, violating, action, level, tone_v, now, commit, bypass=False, trigger=trigger)

    @staticmethod
    def _site_for(prog: Progress, step_id: str, policy: StepPolicy | None = None) -> str | None:
        """The site the worker would act on: the step's own, else that of the calculator step it follows."""
        occ = prog.occurrences.get(step_id)
        if occ and occ.site:
            return occ.site
        if policy is not None:
            for pre in policy.steps[step_id].after:
                po = prog.occurrences.get(pre)
                if po and po.site:
                    return po.site
        return None

    def _act(self, st: _Person, dec: CoachDecision, bundle: _Bundle, step, violating, action: str, level: int, tone: str, now: float,
             commit: bool, *, bypass: bool, trigger: str) -> CoachDecision:
        missed = step if trigger == "expert_policy" else None
        msg, why = message_for(action, missed=missed, violating=violating, current=step, level=level, tone=tone,
                               curriculum=bundle.curriculum, stuck=(trigger == "stuck"))
        dec.action, dec.message, dec.why = action, msg, why
        dec.target = target_for(step, bundle.mapping, site=self._site_for_step(st, bundle, step)) if action in ("annotate", "takeover_offer") else None
        if bypass:
            dec.reason_codes.append("worker_asked")
            dec.gate = {"consecutive": st.gate.consecutive, "reason": "asked"}
        if not commit:
            return dec
        did = "d_" + uuid.uuid4().hex[:12]
        dec.decision_id = did
        study = self._study(st.person)
        task = st.open_task
        row = {
            "schema": 1, "id": "coach-" + uuid.uuid4().hex[:16], "t": _iso(now), "origin": st.origin, "actor": "agent", "person": st.person,
            "role": st.role, "source": "coach", "type": "coach_shown",
            "meta": {"decision": did, "step": step.id, "level": level, "action": action, "trigger": trigger},
        }
        if study is not None:                                  # additive: lets analyze.py split events by study block
            row["meta"]["block"] = study.block
            if study.skill_id:
                row["meta"]["skill"] = study.skill_id[:32]
        if task:
            row["task_id"] = task
        ev = self.store.append(row)
        st.own_ids.add(ev.id)
        st.last_key = max(st.last_key, (ev.t.timestamp(), ev.id))
        if not bypass:
            st.gate = GateState(0, now)
        if task:
            mates = bundle.policy.pattern_mates(step.id)
            st.prompted.setdefault(task, set()).update(mates)
            if action == "takeover_offer":
                st.offered.setdefault(task, set()).update(mates)
        self._records[did] = _Record(st.person, task, step.id, step.cogs, now, level, st.origin, st.role,
                                     block=study.block if study else None, skill=(study.skill_id[:32] if study and study.skill_id else None))
        return dec

    def _site_for_step(self, st: _Person, bundle: _Bundle, step) -> str | None:
        window = st.open or []
        cogs = to_cogs(window, bundle.mapping)
        prog = bundle.policy.track(cogs, self._sites(window, cogs))
        return self._site_for(prog, step.id, bundle.policy)

    def _overall(self, st: _Person, bundle: _Bundle, now: float) -> tuple[int, str, dict]:
        cogs = sorted({c for s in bundle.policy.steps.values() if s.critical for c in s.cogs})
        cs = st.tracker.coach_state(cogs, now)
        return int(cs["level"][1:]), cs["chip"], {k: round(v, 3) for k, v in cs["mastery"].items()}

    # ------------------------------------------------------------------ labels
    def _auto_label(self, st: _Person, prog: Progress, now: float, commit: bool) -> None:
        """The missed step got done soon after the prompt: that is 'followed' without anyone clicking anything."""
        if not commit:
            return
        for did, rec in list(self._records.items()):
            if rec.person != st.person or rec.labelled or rec.task_id != st.open_task:
                continue
            if rec.step in prog.done and 0 <= now - rec.t <= FOLLOW_WINDOW_S:
                self._record_feedback(did, "followed", now, implicit=True)

    def feedback(self, decision_id: str, outcome: str, now: datetime | float | None = None) -> dict:
        if outcome not in OUTCOMES:
            raise CoachError("bad_outcome", f"outcome must be one of {', '.join(OUTCOMES)}.", 422)
        with self._lock:
            rec = self._records.get(decision_id)
            if rec is None:
                rec = self._find_in_store(decision_id)
            if rec is None:
                raise CoachError("no_such_decision", f"There is no recorded coach decision {decision_id}.", 404)
            return self._record_feedback(decision_id, outcome, _ts(now), implicit=False)

    def _find_in_store(self, decision_id: str) -> _Record | None:
        for part in ("real", "synthetic"):
            for ev in self.store.read(part):
                if ev.type == "coach_shown" and ev.meta.get("decision") == decision_id:
                    step = str(ev.meta.get("step", ""))
                    bundle = self._bundle(ev.role)
                    cogs = bundle.policy.steps[step].cogs if bundle and step in bundle.policy.steps else ()
                    rec = _Record(ev.person, ev.task_id, step, cogs, ev.t.timestamp(), int(ev.meta.get("level", 1)), ev.origin, ev.role,
                                  block=ev.meta.get("block"), skill=ev.meta.get("skill"))
                    self._records[decision_id] = rec
                    return rec
        return None

    def _record_feedback(self, did: str, outcome: str, now: float, *, implicit: bool) -> dict:
        rec = self._records[did]
        if rec.labelled and not implicit and rec.labelled == outcome:
            return {"decision_id": did, "outcome": outcome, "recorded": False, "note": "already recorded"}
        st = self._state(rec.person)
        followed = outcome == "followed"
        meta = {"decision": did, "step": rec.step, "level": rec.level, "outcome": outcome}
        if implicit:
            meta["implicit"] = True
        if rec.block:
            meta["block"] = rec.block
            if rec.skill:
                meta["skill"] = rec.skill
        row = {
            "schema": 1, "id": "coach-" + uuid.uuid4().hex[:16], "t": _iso(now), "origin": rec.origin, "actor": "human", "person": rec.person,
            "role": rec.role, "source": "coach", "type": "coach_followed" if followed else "coach_dismissed", "meta": meta,
        }
        if rec.task_id:
            row["task_id"] = rec.task_id
        ev = self.store.append(row)
        st.own_ids.add(ev.id)
        st.last_key = max(st.last_key, (ev.t.timestamp(), ev.id))
        rec.labelled = outcome
        task = rec.task_id or ""
        skill = {}
        if followed:
            st.followed.setdefault(task, set()).add(rec.step)
            st.assisted_done.setdefault(task, set()).add(rec.step)
            for cog in rec.cogs:                                       # assisted: neutral for the level, recorded for mastery
                st.tracker.observe(cog, "assisted", now)
        else:
            st.unfollowed.setdefault(task, {}).setdefault(rec.step, 0)
            st.unfollowed[task][rec.step] += 1
            if outcome == "repeated":
                st.repeated.setdefault(task, set()).add(rec.step)
        snap = st.tracker.snapshot(now)
        for cog in rec.cogs:
            if cog in snap:
                skill[cog] = {"level": f"L{snap[cog]['level']}", "chip": snap[cog]["chip"], "mastery": round(snap[cog]["mastery"], 3)}
        return {"decision_id": did, "outcome": outcome, "recorded": True, "event_id": ev.id, "implicit": implicit, "skill": skill}

    # ------------------------------------------------------------------ read-only view for other engines
    def snapshot(self, person: str, now: datetime | float | None = None, *, sync: bool = True) -> CoachSnapshot:
        """The person's live state as an immutable value: open-window cogs (ids and start times), last progress and input times,
        the stuck probability with its source, and the level and mastery of every cog the tracker knows. Reads the store for new
        events when ``sync`` (that is how the brain stays current); it never acts, never writes an event, never moves the gate."""
        with self._lock:
            t = _ts(now)
            st = self._state(person)
            if sync:
                if t < st.last_event_t - 1e-6:
                    self._people.pop(person, None)
                    st = self._state(person)
                self._sync(st, t)
            bundle = self._bundle(st.role)
            cogs: list[Cog] = []
            window: list[Event] = []
            if st.open is not None and bundle is not None:
                window = [e for e in st.open if e.t.timestamp() <= t]
                cogs = to_cogs(window, bundle.mapping)
            progress_t = [e.t.timestamp() for e in window if e.type == "progress"]
            p, src = None, None
            if cogs and window:
                p, src = self.scorer.p_stuck(cogs=cogs, progress_t=progress_t, t0=window[0].t.timestamp(), now=t, person=person, role=st.role)
                src = "model" if src == "hazard" else "rule"
            skills = tuple(SkillView(c, int(v["level"]), float(v["mastery"])) for c, v in sorted(st.tracker.snapshot(t).items()))
            return CoachSnapshot(
                person=person, t=t, role=st.role, origin=st.origin, task_open=st.open is not None, task_id=st.open_task, implicit=st.implicit,
                cogs=tuple(CogView(c.id, c.t0) for c in cogs), current_cog=cogs[-1].id if cogs else None,
                last_progress_t=max(progress_t) if progress_t else None, last_input_t=st.last_event_t if st.last_event_t > 0 else None,
                p_stuck=None if p is None else round(float(p), 4), p_source=src, skills=skills, tasks_finished=st.n_tasks,
            )

    # ------------------------------------------------------------------ for the Today screen and tests
    def skill_snapshot(self, person: str, now: datetime | float | None = None) -> dict:
        with self._lock:
            st = self._state(person)
            return st.tracker.snapshot(_ts(now))
