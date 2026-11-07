"""The simulated workday (REQ-8): synthetic workers, synthetic schedules, event streams at the producers' typical rates, and the four
conditions of ``evals/attention/PLAN.md`` run over the SAME timeline and the SAME raw events (common random numbers).

EVERYTHING HERE IS SIMULATED. Nobody is real. Every rate, every reaction probability and every cost below is an assumption of mine, fixed
before any run and written in this file (``RATES``, ``FOLLOW``, ``COST``). They exist to make the comparison explicit, not to describe people.

Conditions
  R          the attention layer: ``AttentionService`` driven as the adapter drives it (admission for cues, polls for the rest, feedback back)
  R-nolearn  R with the learned quieting switched off
  B1         show everything immediately: every raise is displayed at once on the type's loudest channel, nothing coalesced, no quiet rule
  B2         one daily digest only: nothing is displayed all day except one summary at the first activity of the day; safety waits for it

The worker's state does not depend on the condition (an interruption costs attention seconds; it does not move the schedule). A
needs-you item is handled ``H`` seconds after the worker first SEES it by any route (a toast, a tray glance, a summary), whatever they did
to the toast; reactions (followed, dismissed, ignored) feed the router's learning and the acceptance metric, not the handling.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from . import vocab as V
from .events import Event
from .router import is_natural_break
from .service import AttentionService
from .state import DEFAULT, Params, Settings, WorkerState
from .store import AttentionStore

STEP = 5.0                                     # seconds per tick
TPD = int(86400 / STEP)                        # ticks per calendar day
BASE_T = 1794182400.0                          # Mon 9 Nov 2026 00:00 UTC (the weekday is nominal: the schedules carry their own)
ARCHETYPES = ("nine-to-five", "night-owl", "shift-worker", "irregular")

# ------------------------------------------------------------------------------------------------ assumptions (fixed before any run)
# per working day unless stated; scaled by the worker's multiplier. Cue's numbers are per working hour.
RATES = {
    "cue_stuck_per_h": 1.2, "cue_false_per_h": 0.5, "cue_ask_share": 0.15, "cue_offer_share": 0.3, "cue_stall_median_s": 80.0, "cue_stall_sd": 0.7,
    "cue_daily_budget": 12, "cue_cap_n": 3, "cue_cap_window_s": 600.0, "cue_skill_gap_s": 90.0,    # Cue's own gate, emulated: its real caps
    "proposal_p": 0.7, "proposal_reoffer_s": 7200.0, "proposal_max_reoffers": 2,
    "approval_waiting_per_night": 0.8, "approval_blocking": 0.6, "irreversible_per_night": 0.15,
    "run_finished_per_night": 2.0, "run_finished_bg": 1.5, "blocked_target": 0.5, "blocked_error": 0.4, "injection": 0.05,
    "deadline": 0.5, "service": 0.2, "level": 0.4, "kill": 0.03, "reraise_s": 300.0,
}
# base probability that a worker follows (opens or acts within 10 s) a display of this type, times the person's acceptance propensity
FOLLOW = {"cue_cue": 0.55, "cue_ask": 0.7, "cue_offer": 0.3, "voice_line": 0.3, "routine_proposal": 0.35, "briefing_ready": 0.4, "approval_blocking": 0.8,
          "approval_waiting": 0.6, "run_blocked_target": 0.8, "run_blocked_error": 0.8, "calendar_deadline": 0.7, "attention_digest": 0.6,
          "help_level_changed": 0.2, "run_finished": 0.3, "morning_report": 0.3, "irreversible_decision": 0.95, "injection_pause": 0.95,
          "kill_engaged": 0.95, "kill_cleared": 0.1, "service_degraded": 0.3}
FLOW_FOLLOW_MULT, BREAK_FOLLOW_MULT = 0.4, 1.2
# seconds of lost focus per interrupting display, by what the worker was doing
COST = {"flow": 25.0, "flow_chip": 10.0, "pause": 8.0, "break": 3.0, "hard_quiet": 30.0}
WINDOW_S = {V.SAFETY: 60.0, V.TIME: 900.0, "approval_waiting": 1800.0}
HANDLE_MEDIAN_S, HANDLE_SD = 120.0, 0.7
GLANCE_PER_S = 1.0 / 480.0                     # a present worker looks at the tray about every 8 minutes
DASHBOARD_PER_DAY = 3


# ------------------------------------------------------------------------------------------------ deterministic draws
def _u(*keys: Any) -> float:
    h = hashlib.blake2b("|".join(map(str, keys)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2.0 ** 64


def _lognorm(median: float, sd: float, *keys: Any) -> float:
    u1, u2 = max(_u(*keys, "a"), 1e-12), _u(*keys, "b")
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return median * math.exp(sd * z)


def _seed(*keys: Any) -> int:
    return int.from_bytes(hashlib.blake2b("|".join(map(str, keys)).encode(), digest_size=4).digest(), "big")


# ------------------------------------------------------------------------------------------------ workers and schedules
@dataclass(frozen=True)
class WorkerSpec:
    wid: str
    persona: str
    seed: int
    mult: float = 1.0               # event-rate multiplier (person effect)
    accept: float = 1.0             # acceptance propensity
    typing: float = 1.0             # typing share
    dismiss_all: bool = False       # S4: closes every non-safety display within a second


@dataclass(frozen=True)
class DaySched:
    kind: str
    windows: tuple[tuple[float, float], ...]


def _persona_days(name: str, root: Path | None) -> list[DaySched] | None:
    p = (root or Path(__file__).resolve().parents[4] / "data") / "synthetic" / name / "truth.json"
    try:
        d = json.loads(p.read_text())["daily"]
        return [DaySched(x["kind"], tuple((float(a), float(b)) for a, b in x["windows"])) for x in d]
    except (OSError, ValueError, KeyError):
        return None


def _built_in_day(persona: str, d: int, seed: int) -> DaySched:
    dow = d % 7
    if persona == "nine-to-five":
        return DaySched("normal", ((9.0, 17.25),)) if dow < 4 else DaySched("off", ())
    if persona == "night-owl":
        return DaySched("normal", ((13.0, 26.5),)) if dow != 1 else DaySched("holiday", ())
    if persona == "shift-worker":
        return DaySched("normal", ((6.0, 14.25),)) if dow in (0, 1, 6) else (DaySched("normal", ((14.0, 22.25),)) if dow == 4 else DaySched("off", ()))
    a = 7.0 + 3.0 * _u(seed, d, "ia")
    return DaySched("normal", ((a, a + 3.0 + 3.0 * _u(seed, d, "ib")), (19.5 + _u(seed, d, "ic"), 22.0 + _u(seed, d, "id")))) if dow not in (1, 5) else DaySched("off", ())


def schedule(spec: WorkerSpec, n_work_days: int, *, source: str = "auto", root: Path | None = None) -> tuple[list[DaySched], str]:
    """Consecutive calendar days from a random offset into the persona's cycle until ``n_work_days`` days with a window have passed."""
    persona_days = _persona_days(spec.persona, root) if source in ("auto", "persona_truth") else None
    days: list[DaySched] = []
    worked = 0
    off = int(_u(spec.seed, spec.wid, "off") * 20)
    d = 0
    while worked < n_work_days and d < 60:
        ds = persona_days[(off + d) % len(persona_days)] if persona_days else _built_in_day(spec.persona, d + off, spec.seed)
        days.append(ds)
        worked += int(bool(ds.windows))
        d += 1
    return days, ("persona_truth" if persona_days else "built_in")


def population(seed: int, per_archetype: int, *, dismiss_all: bool = False, rate_scale: float = 1.0) -> list[WorkerSpec]:
    out = []
    for p in ARCHETYPES:
        for k in range(per_archetype):
            wid = f"w{seed}_{p[:3]}{k}"
            out.append(WorkerSpec(wid, p, seed, mult=rate_scale * _lognorm(1.0, 0.25, seed, wid, "mult"), accept=min(1.6, _lognorm(1.0, 0.25, seed, wid, "acc")),
                                  typing=_lognorm(1.0, 0.25, seed, wid, "typ"), dismiss_all=dismiss_all))
    return out


# ------------------------------------------------------------------------------------------------ the state timeline
@dataclass
class Timeline:
    n: int
    typing: np.ndarray
    quiet: np.ndarray
    in_task: np.ndarray
    task_marker: np.ndarray
    away: np.ndarray
    away_s: np.ndarray
    locked: np.ndarray
    meeting: np.ndarray
    call: np.ndarray
    share: np.ndarray
    dnd: np.ndarray
    deep: np.ndarray
    present: np.ndarray

    def ws(self, t: float, *, known: bool = True) -> WorkerState:
        i = min(self.n - 1, max(0, int((t - BASE_T) // STEP)))
        tm = float(self.task_marker[i])
        return WorkerState(now=t, known=known, typing_burst=bool(self.typing[i]), quiet_s=float(self.quiet[i]), deep_work=bool(self.deep[i]),
                           task_in_progress=bool(self.in_task[i]), task_marker_s=None if tm < 0 else tm, away=bool(self.away[i]), away_s=float(self.away_s[i]),
                           locked=bool(self.locked[i]), dnd=bool(self.dnd[i]), screen_sharing=bool(self.share[i]), on_call=bool(self.call[i]),
                           in_meeting=bool(self.meeting[i]), local_hour=int(((t - BASE_T) // 3600) % 24))

    def idx(self, t: float) -> int:
        return min(self.n - 1, max(0, int((t - BASE_T) // STEP)))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def build_timeline(spec: WorkerSpec, days: list[DaySched], *, scripted: dict[str, list[tuple[float, float]]] | None = None) -> Timeline:
    """Per-tick state for the whole stretch. ``scripted`` puts meeting, call, share and dnd blocks at fixed hours (scenarios)."""
    n = len(days) * TPD + TPD // 2
    rng = np.random.default_rng(_seed(spec.seed, spec.wid, "tl"))
    present = np.zeros(n, bool)
    for d, ds in enumerate(days):
        for a, b in ds.windows:
            present[int((d * 24 + a) * 3600 / STEP): min(n, int((d * 24 + b) * 3600 / STEP))] = True
    # coffee gaps (about every 90 minutes of presence) and lunch
    for s, e in _runs(present):
        i = s + int(rng.uniform(40, 120) * 60 / STEP)
        while i < e - 30 * 60 // STEP:
            g = int(rng.uniform(3, 10) * 60 / STEP)
            present[i:i + g] = False
            i += g + int(rng.uniform(70, 110) * 60 / STEP)
    for d, ds in enumerate(days):
        for a, b in ds.windows:
            if a < 12.5 < b - 1.5 and b - a >= 6:
                i = int((d * 24 + 12.0 + 1.2 * rng.random()) * 3600 / STEP)
                present[i:i + int(rng.uniform(30, 60) * 60 / STEP)] = False
    typing = np.zeros(n, bool)
    in_task = np.zeros(n, bool)
    gap_ends: list[int] = []
    for s, e in _runs(present):
        i = s
        while i < e:
            task_end = min(e, i + int(rng.uniform(300, 900) / STEP))
            j = i
            while j < task_end:
                r = rng.random()
                if r < 0.55:
                    kind, dur = "type", rng.exponential(240.0 * spec.typing)
                elif r < 0.8:
                    kind, dur = "think", rng.exponential(25.0)
                else:
                    kind, dur = "read", rng.exponential(60.0)
                j2 = min(task_end, j + max(1, int(np.clip(dur, 10.0 if kind == "type" else 5.0, 900 if kind == "type" else 300) / STEP)))
                in_task[j:j2] = True
                typing[j:j2] = kind == "type"
                j = j2
            gap_ends.append(task_end)
            i = min(e, task_end + int(rng.uniform(30, 150) / STEP))
    meeting = np.zeros(n, bool)
    call = np.zeros(n, bool)
    share = np.zeros(n, bool)
    dnd = np.zeros(n, bool)

    def block(mask: np.ndarray, a_h: float, b_h: float, day: int) -> None:
        mask[int((day * 24 + a_h) * 3600 / STEP): int((day * 24 + b_h) * 3600 / STEP)] = True

    if scripted is not None:
        for name, spans in scripted.items():
            for a_h, b_h in spans:                                   # scripted hours are absolute from the start of the timeline
                if name in ("meeting", "call", "share", "dnd"):
                    {"meeting": meeting, "call": call, "share": share, "dnd": dnd}[name][int(a_h * 3600 / STEP): int(b_h * 3600 / STEP)] = True
    else:
        for d, ds in enumerate(days):
            if not ds.windows:
                continue
            a, b = ds.windows[0]
            if b - a >= 4 and _u(spec.seed, spec.wid, d, "meet") < 0.25:
                m0 = a + 1.0 + (b - a - 3.5) * _u(spec.seed, spec.wid, d, "m0")
                m1 = m0 + 0.5 + 1.5 * _u(spec.seed, spec.wid, d, "m1")
                block(meeting, m0, m1, d)
                if _u(spec.seed, spec.wid, d, "shr") < 0.3:
                    block(share, m0 + 0.2, min(m1, m0 + 0.2 + 0.33 + 0.4 * _u(spec.seed, spec.wid, d, "s1")), d)
            if b - a >= 4 and _u(spec.seed, spec.wid, d, "call") < 0.2:
                c0 = a + 0.5 + (b - a - 1.5) * _u(spec.seed, spec.wid, d, "c0")
                block(call, c0, c0 + 0.25 + 0.5 * _u(spec.seed, spec.wid, d, "c1"), d)
            if b - a >= 4 and _u(spec.seed, spec.wid, d, "dnd") < 0.1:
                d0 = a + 0.5 + (b - a - 1.5) * _u(spec.seed, spec.wid, d, "d0")
                block(dnd, d0, d0 + 1.0, d)
    if scripted is not None and scripted.get("typing"):
        for a_h, b_h in scripted["typing"]:                          # a long run of focused work: typing throughout, no gaps
            i0, i1 = int(a_h * 3600 / STEP), int(b_h * 3600 / STEP)
            present[i0:i1] = True
            typing[i0:i1] = True
            in_task[i0:i1] = True
            meeting[i0:i1] = call[i0:i1] = share[i0:i1] = False
    in_talk = (meeting | call | share) & present
    typing &= ~in_talk
    in_task &= ~in_talk
    sparse = in_talk & (rng.random(n) < 0.02)
    inp = typing | sparse
    idx = np.arange(n)
    last_in = np.maximum.accumulate(np.where(inp, idx, -1))
    quiet = np.where(last_in < 0, 600.0, (idx - last_in) * STEP + 2.0)
    quiet = np.where(typing, rng.uniform(0.2, 1.5, n), quiet)
    quiet = np.where(present, quiet, quiet)
    end_mark = np.zeros(n, bool)
    for ge in gap_ends:
        if ge < n:
            end_mark[ge] = True
    last_end = np.maximum.accumulate(np.where(end_mark, idx, -1))
    task_marker = np.where(last_end < 0, -1.0, (idx - last_end) * STEP)
    away = ~present
    act = present & (quiet < 120.0)
    cs = np.cumsum(act)
    run = cs - np.maximum.accumulate(np.where(~act, cs, 0))
    deep = (run * STEP) >= 1500.0
    # seconds since the current away spell began
    away_idx = np.maximum.accumulate(np.where(~away, idx, -1))
    away_s = np.where(away, (idx - away_idx) * STEP, 0.0)
    locked = away & (away_s >= 600.0)
    return Timeline(n, typing, quiet, in_task, task_marker, away, away_s, locked, meeting, call, share, dnd, deep, present)


# ------------------------------------------------------------------------------------------------ the raw events
@dataclass
class Raw:
    t: float
    type: str
    subject: str
    kw: dict[str, Any] = field(default_factory=dict)
    producer: str = ""
    reraise: bool = False                  # the producer will raise this again every 5 minutes while it is unresolved
    reoffer: int = 0                       # a proposal: re-offered up to this many more times, two hours apart, while unanswered
    resolve_after: float | None = None     # a health note: the producer resolves it by itself after this long


def _present_ticks(tl: Timeline, lo: float, hi: float) -> np.ndarray:
    a, b = tl.idx(lo), tl.idx(hi)
    return np.flatnonzero(tl.present[a:b]) + a


def gen_events(spec: WorkerSpec, tl: Timeline, days: list[DaySched], *, gate_leak: float = 0.0, extra: list[Raw] | None = None, background: bool = True) -> list[Raw]:
    out: list[Raw] = list(extra or [])
    if not background:
        return sorted(out, key=lambda r: r.t)
    m = spec.mult

    def poisson(rate: float, *keys: Any) -> int:
        lam = max(0.0, rate * m)
        k, p, L = 0, 1.0, math.exp(-lam)
        j = 0
        while True:
            p *= max(_u(spec.seed, spec.wid, *keys, j), 1e-12)
            j += 1
            if p <= L:
                return k
            k += 1
            if k > 40:
                return k

    for d, ds in enumerate(days):
        d0 = BASE_T + d * 86400.0
        lo, hi = d0, d0 + 86400.0
        pres = _present_ticks(tl, lo, hi + 12 * 3600.0)
        pres = pres[(pres >= tl.idx(lo)) & (pres < tl.idx(hi))] if len(pres) else pres
        hours = len(pres) * STEP / 3600.0
        # ---- overnight (the worker is away): runs, approvals, a morning report
        for k in range(poisson(RATES["run_finished_per_night"], d, "rn")):
            t = d0 + (1.0 + 5.0 * _u(spec.seed, spec.wid, d, "rnt", k)) * 3600.0
            o = "done" if _u(spec.seed, spec.wid, d, "rno", k) < 0.85 else ("failed" if _u(spec.seed, spec.wid, d, "rno2", k) < 0.67 else "paused")
            out.append(Raw(t, "run_finished", f"n{d}_{k}", {"outcome": o, "run_mode": "overnight"}, "agent"))
        for k in range(poisson(RATES["approval_waiting_per_night"], d, "an")):
            out.append(Raw(d0 + (1.0 + 5.0 * _u(spec.seed, spec.wid, d, "ant", k)) * 3600.0, "approval_waiting", f"qn{d}_{k}", {}, "queue", reraise=True))
        for k in range(poisson(RATES["irreversible_per_night"], d, "irn")):
            out.append(Raw(d0 + (1.0 + 5.0 * _u(spec.seed, spec.wid, d, "irt", k)) * 3600.0, "irreversible_decision", f"irn{d}_{k}", {"run_mode": "overnight", "risk_class": "irreversible"}, "agent", reraise=True))
        if any(r.type == "run_finished" and r.subject.startswith(f"n{d}_") for r in out):
            out.append(Raw(d0 + 6.5 * 3600.0, "morning_report", f"rep{d}", {"count": 1}, "agent"))
        if len(pres) == 0:
            continue
        first = tl.present[tl.idx(lo): tl.idx(hi)].argmax() * STEP + lo if tl.present[tl.idx(lo): tl.idx(hi)].any() else None

        def at(*keys: Any) -> float:
            return BASE_T + float(pres[int(_u(spec.seed, spec.wid, d, *keys) * len(pres))]) * STEP

        # ---- the briefing: at the first activity, and a regeneration twelve hours later
        if first is not None:
            out.append(Raw(first + 30.0 + 90.0 * _u(spec.seed, spec.wid, d, "br"), "briefing_ready", f"gen{d}a", {"count": 1 + int(_u(spec.seed, spec.wid, d, "brc") * 3)}, "proactive"))
            late = first + 12 * 3600.0
            if tl.present[tl.idx(late)] and tl.idx(late) < tl.idx(hi):
                out.append(Raw(late, "briefing_ready", f"gen{d}b", {"count": 1 + int(_u(spec.seed, spec.wid, d, "brd") * 3)}, "proactive"))
        if _u(spec.seed, spec.wid, d, "rp") < RATES["proposal_p"] * min(1.5, m):
            out.append(Raw(at("rpt"), "routine_proposal", f"rt{d}", {}, "routines", reoffer=int(RATES["proposal_max_reoffers"])))
        for k in range(poisson(RATES["approval_blocking"], d, "ab")):
            out.append(Raw(at("abt", k), "approval_blocking", f"qb{d}_{k}", {"blocks_run": True}, "queue", reraise=True))
        for k in range(poisson(RATES["run_finished_bg"], d, "rb")):
            out.append(Raw(at("rbt", k), "run_finished", f"b{d}_{k}", {"outcome": "done" if _u(spec.seed, spec.wid, d, "rbo", k) < 0.9 else "failed", "run_mode": "background"}, "agent"))
        for k in range(poisson(RATES["blocked_target"], d, "bt")):
            out.append(Raw(at("btt", k), "run_blocked_target", f"bt{d}_{k}", {"run_mode": "foreground"}, "agent", reraise=True))
        for k in range(poisson(RATES["blocked_error"], d, "be")):
            out.append(Raw(at("bet", k), "run_blocked_error", f"be{d}_{k}", {"run_mode": "foreground"}, "agent", reraise=True))
        for k in range(poisson(RATES["injection"], d, "ij")):
            out.append(Raw(at("ijt", k), "injection_pause", f"ij{d}_{k}", {"run_mode": "foreground"}, "agent", reraise=True))
        for k in range(poisson(RATES["deadline"], d, "dl")):
            out.append(Raw(at("dlt", k), "calendar_deadline", f"dl{d}_{k}", {"deadline_in_s": 1800.0 + 5400.0 * _u(spec.seed, spec.wid, d, "dld", k)}, "calendar"))
        for k in range(poisson(RATES["service"], d, "sv")):
            svc = ("engine", "agent", "model", "calendar")[int(_u(spec.seed, spec.wid, d, "svs", k) * 4)]
            out.append(Raw(at("svt", k), "service_degraded", f"svc{d}_{k}", {"service": svc}, "health", resolve_after=600.0 + 3000.0 * _u(spec.seed, spec.wid, d, "svr", k)))
        for k in range(poisson(RATES["level"], d, "lv")):
            out.append(Raw(at("lvt", k), "help_level_changed", f"lv{d}_{k}", {"expires_in_s": 60.0}, "coach"))
        for k in range(poisson(RATES["kill"], d, "kl")):
            t = at("klt", k)
            out.append(Raw(t, "kill_engaged", f"kill{d}_{k}", {}, "kill"))
            out.append(Raw(t + 300.0, "kill_cleared", f"kill{d}_{k}", {}, "kill"))
        # ---- Cue: stuck episodes and false nudges, through Cue's own gate (never while typing or within 2 s of input) and its caps
        eps: list[tuple[float, bool, str]] = []
        for k in range(poisson(RATES["cue_stuck_per_h"] * hours, d, "cs") if hours else 0):
            eps.append((at("cst", k), True, f"e{d}s{k}"))
        for k in range(poisson(RATES["cue_false_per_h"] * hours, d, "cf") if hours else 0):
            eps.append((at("cft", k), False, f"e{d}f{k}"))
        eps.sort()
        shown: list[float] = []
        last_ep = -1e18
        for k, (t0, stuck, subj) in enumerate(eps):
            t = t0
            for _ in range(24):                                       # Cue waits for 2 s of quiet; give it two minutes
                i = tl.idx(t)
                if not tl.typing[i] and tl.quiet[i] >= 2.0 and tl.present[i]:
                    break
                t += STEP
            else:
                if _u(spec.seed, spec.wid, d, "leak", k) >= gate_leak:
                    continue
            if t - last_ep < RATES["cue_skill_gap_s"] or len([x for x in shown if t - x < RATES["cue_cap_window_s"]]) >= RATES["cue_cap_n"] or len(shown) >= RATES["cue_daily_budget"]:
                continue
            last_ep = t
            shown.append(t)
            stall = _lognorm(RATES["cue_stall_median_s"], RATES["cue_stall_sd"], spec.seed, spec.wid, d, "stall", k) if stuck else 0.0
            ask = _u(spec.seed, spec.wid, d, "ask", k) < RATES["cue_ask_share"]
            out.append(Raw(t, "cue_ask" if ask else "cue_cue", subj, {"expires_in_s": 12.0}, "cue"))
            if not ask and stall > 25.0:
                out.append(Raw(t + 25.0, "cue_cue", subj, {"expires_in_s": 12.0}, "cue"))
            if stall > 90.0 and _u(spec.seed, spec.wid, d, "off", k) < RATES["cue_offer_share"]:
                out.append(Raw(t + 90.0, "cue_offer", subj, {"expires_in_s": 12.0}, "cue"))
    out.sort(key=lambda r: (r.t, r.type, r.subject))
    return out


# ------------------------------------------------------------------------------------------------ the ledger and metrics
@dataclass
class Arr:
    type: str
    subject: str
    cls: str
    important: bool
    needs_you: bool
    t: float
    expire: float
    start: float | None = None             # when the clock for "seen in window" starts (arrival, or the worker's return)
    seen: float | None = None
    resolved: float | None = None
    reminders: int = 0
    raises: int = 1
    never_present: bool = False


@dataclass
class WorkerResult:
    wid: str
    persona: str
    condition: str
    days: int = 0
    work_h: float = 0.0
    flow_h: float = 0.0
    displays: int = 0
    displays_nonsafety: int = 0
    flow_displays: int = 0
    flow_displays_nonsafety: int = 0
    hq_breaches: int = 0
    exposure: int = 0
    cost_s: float = 0.0
    shown_labelled: int = 0
    followed: int = 0
    dismissed_fast: int = 0
    dup_displays: int = 0
    reminder_displays: int = 0
    important_n: int = 0
    important_seen: int = 0
    safety_n: int = 0
    safety_missed: int = 0
    time_n: int = 0
    time_missed: int = 0
    delays: list[float] = field(default_factory=list)       # seconds, one per important item (inf when never seen in time)
    needs_reminders: list[int] = field(default_factory=list)
    digest_lines: list[int] = field(default_factory=list)
    digest_folded: list[int] = field(default_factory=list)
    per_day: list[dict[str, int]] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    held_peak: int = 0
    ctx_counts: dict[str, int] = field(default_factory=dict)   # interrupting displays by cost class: flow, flow_chip, pause, break, hard_quiet

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["delays"] = [None if math.isinf(x) else round(x, 1) for x in self.delays]
        return d


def _important(type_id: str) -> bool:
    return V.TYPES[type_id].cls in (V.SAFETY, V.TIME) or type_id == "approval_waiting"


def _window(a: Arr) -> float:
    base = WINDOW_S.get(a.type) or WINDOW_S.get(V.TYPES[a.type].cls) or 900.0
    return base


def _ctx(ws: WorkerState, p: Params) -> str:
    if ws.hard_quiet():
        return "hard_quiet"
    if ws.typing_burst or ws.deep_work:
        return "flow"
    return "break" if is_natural_break(ws, p) else "pause"


def _cost(ctx: str, channel: str) -> float:
    if ctx == "flow":
        return COST["flow_chip"] if channel in ("chip", "voice") else COST["flow"]
    return COST[ctx]


def _react(spec: WorkerSpec, key: Any, type_id: str, ctx: str) -> tuple[str, float]:
    """The worker's reaction to a display: (label, seconds). Deterministic per (worker, key): conditions share the draw."""
    if spec.dismiss_all and V.TYPES[type_id].cls != V.SAFETY:
        return "dismissed_fast", 0.5 + 0.4 * _u(spec.wid, key, "dq")
    base = FOLLOW.get(type_id, 0.3) * spec.accept
    mult = FLOW_FOLLOW_MULT if ctx == "flow" else (BREAK_FOLLOW_MULT if ctx == "break" else 1.0)
    p = min(0.98, base * mult)
    if _u(spec.wid, key, "f") < p:
        return "followed", 1.0 + 8.0 * _u(spec.wid, key, "fs")
    pf = (1.0 - p) * (0.4 if ctx == "flow" else 0.2)
    u = _u(spec.wid, key, "d")
    if u < pf:
        return "dismissed_fast", 0.5 + 3.0 * _u(spec.wid, key, "ds")
    if u < pf + 0.3:
        return "dismissed", 5.0 + 10.0 * _u(spec.wid, key, "dl")
    return "ignored", 20.0


@dataclass
class World:
    """Everything about one worker that does not depend on the condition: built once, replayed under every condition."""
    spec: WorkerSpec
    days: list[DaySched]
    tl: Timeline
    events: list[Raw]
    glances: np.ndarray                    # tray glances (times)
    dashes: np.ndarray                     # dashboard opens (times)
    source: str = "built_in"

    @property
    def work_h(self) -> float:
        tl = self.tl
        return float((tl.present & ~(tl.meeting | tl.call | tl.share | tl.dnd)).sum()) * STEP / 3600.0

    @property
    def flow_h(self) -> float:
        tl = self.tl
        return float((tl.present & (tl.typing | tl.deep)).sum()) * STEP / 3600.0


def build_world(spec: WorkerSpec, n_work_days: int, *, source: str = "auto", root: Path | None = None, gate_leak: float = 0.0,
                scripted: dict[str, list[tuple[float, float]]] | None = None, days: list[DaySched] | None = None, extra: list[Raw] | None = None,
                background: bool = True) -> World:
    sched, src = (days, "scripted") if days is not None else schedule(spec, n_work_days, source=source, root=root)
    tl = build_timeline(spec, sched, scripted=scripted)
    events = gen_events(spec, tl, sched, gate_leak=gate_leak, extra=extra, background=background)
    rng = np.random.default_rng(_seed(spec.seed, spec.wid, "glance"))
    nd = len(sched)
    pres = np.flatnonzero(tl.present[: nd * TPD])
    g = pres[rng.random(len(pres)) < GLANCE_PER_S * STEP]
    dash: list[float] = []
    for d in range(nd):
        pd_ = np.flatnonzero(tl.present[d * TPD:(d + 1) * TPD]) + d * TPD
        if len(pd_):
            dash += [BASE_T + float(pd_[int(_u(spec.wid, d, "dash", k) * len(pd_))]) * STEP for k in range(DASHBOARD_PER_DAY)]
    return World(spec, sched, tl, events, BASE_T + g.astype(float) * STEP, np.array(sorted(dash)), src)


class Runner:
    """One worker, one condition, over the whole timeline."""

    def __init__(self, world: World, condition: str, *, params: Params = DEFAULT, settings: Settings | None = None, unknown_poll_rate: float = 0.0,
                 cost_scale: float = 1.0, trace: bool = False) -> None:
        self.w = world
        self.spec, self.tl, self.days, self.events, self.cond = world.spec, world.tl, world.days, world.events, condition
        self.p = params
        self.pid = "p_" + "".join(c if c.isalnum() else "_" for c in self.spec.wid.lower())[:28]
        self.unknown_rate = unknown_poll_rate
        self.cost_scale = cost_scale
        self.trace: list[dict[str, Any]] | None = [] if trace else None
        self.res = WorkerResult(self.spec.wid, self.spec.persona, condition, days=sum(1 for d in self.days if d.windows))
        self.arr: dict[tuple[str, str], Arr] = {}
        self.displayed: dict[str, float] = {}               # family:subject -> last display time (duplicates)
        self.feedbacks: list[tuple[float, int, str, str, float]] = []   # (t, n, item_id, event, seconds)
        self.resolves: list[tuple[float, int, Arr]] = []
        self.reraises: list[tuple[float, int, Raw]] = []
        self.health: list[tuple[float, int, Raw]] = []
        self.cue_active: dict[str, float] = {}
        self._n = 0
        self._hint = 5.0
        self._t = BASE_T                                     # the current tick (costs and flow are judged on the TRUE state at it)
        self.svc: AttentionService | None = None
        if condition.startswith("R"):
            p2 = params if condition == "R" else replace(params, n_min=1e12, never_subjects_for_max=10 ** 9)
            self.svc = AttentionService(AttentionStore(params=p2), p2, retain_s=3600.0, prune_above=30)
            if settings is not None:
                self.svc.store.person(self.pid).settings = settings.to_dict()
        self.pd: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _day(self, t: float) -> int:
        return int((t - BASE_T) // 86400)

    def _push(self, heap: list, t: float, obj: Any) -> None:
        self._n += 1
        heapq.heappush(heap, (t, self._n, obj))

    # -------------------------------------------------------------------------------------------- ledger
    def _arrive(self, r: Raw, t: float) -> Arr:
        key = (r.type, r.subject)
        a = self.arr.get(key)
        if a is not None:
            a.raises += 1
            return a
        sp = V.TYPES[r.type]
        life = r.kw.get("deadline_in_s") if r.type == "calendar_deadline" else r.kw.get("expires_in_s", sp.ttl_s)
        a = Arr(r.type, r.subject, sp.cls, _important(r.type), sp.needs_you, t, t + min(float(life), sp.ttl_s if r.type != "calendar_deadline" else 1e9))
        i0 = self.tl.idx(t)
        if a.important:
            if self.tl.present[i0]:
                a.start = t
            else:
                nxt = np.flatnonzero(self.tl.present[i0:])
                if len(nxt) and BASE_T + (i0 + int(nxt[0])) * STEP < a.expire:
                    a.start = BASE_T + (i0 + int(nxt[0])) * STEP
                else:
                    a.never_present = True
        self.arr[key] = a
        return a

    def _see(self, a: Arr, t: float) -> None:
        if a.seen is None and a.t <= t <= a.expire and a.resolved is None:
            a.seen = t
            if a.needs_you and a.type != "kill_engaged":          # the stopped state ends when the worker resumes, not when they have read about it
                self._push(self.resolves, t + _lognorm(HANDLE_MEDIAN_S, HANDLE_SD, self.spec.wid, a.type, a.subject, "handle"), a)

    def _see_open_needs_you(self, t: float) -> None:
        for a in self.arr.values():
            if a.needs_you and a.resolved is None and a.t <= t <= a.expire:
                self._see(a, t)

    def _display(self, t: float, type_id: str, subject: str, channel: str, *, reminder: bool = False, item_id: str | None = None) -> None:
        sp = V.TYPES[type_id]
        r = self.res
        ws = self.tl.ws(t)
        ctx = _ctx(ws, self.p)
        r.displays += 1
        key = f"{sp.family}:{subject}"
        if key in self.displayed and not reminder:
            r.dup_displays += 1
        self.displayed[key] = t
        r.reminder_displays += int(reminder)
        safety = sp.cls == V.SAFETY
        r.displays_nonsafety += int(not safety)
        if ctx == "flow":
            r.flow_displays += 1
            r.flow_displays_nonsafety += int(not safety)
        if ctx == "hard_quiet":
            r.exposure += int(ws.screen_sharing)
            r.hq_breaches += int(not safety)
        r.cost_s += _cost(ctx, channel) * self.cost_scale
        ck = "flow_chip" if (ctx == "flow" and channel in ("chip", "voice")) else ctx
        r.ctx_counts[ck] = r.ctx_counts.get(ck, 0) + 1
        if self.trace is not None:
            self.trace.append({"t": t, "e": "display", "type": type_id, "subject": subject, "channel": channel, "reminder": reminder, "ctx": ctx})
        d = self._day(t)
        self.pd[d]["displays"] += 1
        self.pd[d][f"cls_{sp.cls}"] += 1
        self.pd[d][f"type_{type_id}"] += 1
        if sp.cls == V.WAIT and channel == "toast":
            self.pd[d]["wait_toasts"] += 1
        a = self.arr.get((type_id, subject))
        if a is not None:
            a.reminders += int(reminder)
            self._see(a, t)
        if type_id == "attention_digest":
            return
        label, secs = _react(self.spec, f"{type_id}|{subject}|{'r' if reminder else 'n'}|{int(t // 60)}", type_id, ctx)
        r.shown_labelled += 1
        r.followed += int(label == "followed")
        r.dismissed_fast += int(label == "dismissed_fast")
        if a is not None and label == "followed" and not a.needs_you:
            a.resolved = t + secs                            # the worker acted on a proposal or a note: it is not re-offered
        if self.svc is not None and item_id and label != "ignored":
            self._push(self.feedbacks, t + secs, (item_id, "followed" if label == "followed" else "dismissed", secs))

    # -------------------------------------------------------------------------------------------- run
    def run(self) -> WorkerResult:
        tl = self.tl
        ev = self.events
        ei = gi = di = 0
        t = BASE_T
        t_end = BASE_T + tl.n * STEP
        digest_days: set[int] = set()
        last_poll = -1e18
        glances, dashes = self.w.glances, self.w.dashes
        prev_present = False
        while t < t_end:
            i = tl.idx(t)
            present = bool(tl.present[i])
            self._t = t
            cache: list[WorkerState] = []

            def get_ws() -> WorkerState:
                if not cache:
                    wt = tl.ws(t)
                    cache.append(replace(wt, known=False) if (self.svc is not None and self.unknown_rate > 0 and _u(self.spec.wid, i, "unk") < self.unknown_rate) else wt)
                return cache[0]

            while self.feedbacks and self.feedbacks[0][0] <= t:
                ft, _, (iid, evn, secs) = heapq.heappop(self.feedbacks)
                try:
                    self.svc.feedback(self.pid, iid, evn, secs, now=ft)       # type: ignore[union-attr]
                except Exception:
                    pass
            while self.resolves and self.resolves[0][0] <= t:
                rt, _, a = heapq.heappop(self.resolves)
                if a.resolved is None:
                    a.resolved = rt
                    if self.svc is not None:
                        self.svc.submit(Event(type=a.type, person=self.pid, subject=a.subject, op="resolve"), get_ws(), now=rt)
            while self.health and self.health[0][0] <= t:
                ht, _, r0 = heapq.heappop(self.health)
                a = self.arr.get((r0.type, r0.subject))
                if a is not None and a.resolved is None:
                    a.resolved = ht
                    if self.svc is not None:
                        self.svc.submit(Event(type=r0.type, person=self.pid, subject=r0.subject, op="resolve"), get_ws(), now=ht)
            fired = False
            while ei < len(ev) and ev[ei].t <= t:
                r = ev[ei]
                ei += 1
                fired = True
                self._raise(r, get_ws(), t, present, again=False)
            while self.reraises and self.reraises[0][0] <= t:
                _, _, r = heapq.heappop(self.reraises)
                a = self.arr.get((r.type, r.subject))
                if a is None or a.resolved is not None or t > a.expire:
                    continue
                fired = True
                self._raise(r, get_ws(), t, present, again=True)
            while gi < len(glances) and glances[gi] <= t:
                g = glances[gi]
                gi += 1
                if self.svc is not None:
                    b = self.svc.badges(self.pid)["badges"]
                    if b["needs_you"] > 0 or b["marker"] == "stopped":
                        self._see_open_needs_you(g)
            while di < len(dashes) and dashes[di] <= t:
                dt = dashes[di]
                di += 1
                if self.svc is not None:
                    self._see_open_needs_you(dt)
            if self.svc is not None:
                hint = self._hint * 2.0 if self._hint >= 15.0 else self._hint        # idle: ask half as often as the adapter would
                interval = max(STEP, hint) if present else 300.0
                if fired or self.feedbacks:
                    interval = STEP
                if (present and not prev_present) or t - last_poll >= interval - 1e-9:
                    last_poll = t
                    self._poll(get_ws(), t)
            elif self.cond == "B2" and present:
                day = self._day(t)
                if day not in digest_days:
                    digest_days.add(day)
                    self._b2_digest(t)
            prev_present = present
            if not present:
                cand = [t + 300.0 if self.svc is not None else t + 600.0]
                if ei < len(ev):
                    cand.append(ev[ei].t)
                for h in (self.feedbacks, self.resolves, self.reraises, self.health):
                    if h:
                        cand.append(h[0][0])
                if gi < len(glances):
                    cand.append(float(glances[gi]))
                nxt = np.flatnonzero(tl.present[i:i + 2 * TPD])
                if len(nxt):
                    cand.append(BASE_T + (i + int(nxt[0])) * STEP)
                t = max(t + STEP, min(cand))
            else:
                t += STEP
        r = self.res
        r.work_h = self.w.work_h
        r.flow_h = self.w.flow_h
        self._finish()
        r.per_day = [dict(self.pd.get(d, {})) for d in range(len(self.days))]
        return r

    def _open_items(self) -> bool:
        ps = self.svc.store.person(self.pid)               # type: ignore[union-attr]
        return any(i.state not in V.TERMINAL for i in ps.items.values())

    # -------------------------------------------------------------------------------------------- producers raise
    def _raise(self, r: Raw, ws: WorkerState, t: float, present: bool, *, again: bool) -> None:
        sp = V.TYPES[r.type]
        a = self.arr.get((r.type, r.subject)) if again else self._arrive(r, t)
        if a is None:
            return
        if r.reraise:
            self._push(self.reraises, t + RATES["reraise_s"], r)
        if r.reoffer > 0:
            self._push(self.reraises, t + RATES["proposal_reoffer_s"], replace(r, reoffer=r.reoffer - 1))
        if r.resolve_after is not None and not again:
            self._push(self.health, t + r.resolve_after, r)
        kw = {k: v for k, v in r.kw.items() if k in Event.__dataclass_fields__}
        cont = False
        if sp.family == "cue":
            last = self.cue_active.get(r.subject)
            cont = last is not None and t - last < 12.0      # a tier escalation of the cue already up is the same cue growing, in every condition
            self.cue_active[r.subject] = t
        if self.svc is not None:
            self._r_submit(r, kw, ws, t)
        elif self.cond == "B1":
            chan = sp.modes["loud"][0]
            if chan not in V.PASSIVE and not cont and present:
                self._display(t, r.type, r.subject, chan)

    def _r_submit(self, r: Raw, kw: dict[str, Any], ws: WorkerState, t: float) -> None:
        ev = Event(type=r.type, person=self.pid, subject=r.subject, **kw)
        out = self.svc.submit(ev, ws, now=t)                     # type: ignore[union-attr]
        if V.TYPES[r.type].cls in (V.HELPFUL, V.INFO):
            if out["show"] and not out["coalesced"]:
                self._display(t, r.type, r.subject, out["decision"]["channel"], item_id=out["item_id"])
            elif not out["show"] and out["decision"] and not out["coalesced"]:
                code = out["decision"]["reason_code"]
                self.res.dropped[code] = self.res.dropped.get(code, 0) + 1

    def _b2_digest(self, t: float) -> None:
        open_ = [a for a in self.arr.values() if a.t <= t <= a.expire and a.resolved is None and a.type != "kill_cleared"]
        if not open_:
            return
        ws = self.tl.ws(t)
        ctx = _ctx(ws, self.p)
        r = self.res
        r.displays += 1
        r.displays_nonsafety += 1
        r.flow_displays += int(ctx == "flow")
        r.flow_displays_nonsafety += int(ctx == "flow")
        r.hq_breaches += int(ctx == "hard_quiet")
        r.cost_s += _cost(ctx, "toast") * self.cost_scale
        r.ctx_counts[ctx] = r.ctx_counts.get(ctx, 0) + 1
        r.digest_lines.append(min(7, len(open_)))
        r.digest_folded.append(len(open_))
        self.pd[self._day(t)]["displays"] += 1
        label, _ = _react(self.spec, f"digest|{int(t // 3600)}", "attention_digest", ctx)
        r.shown_labelled += 1
        r.followed += int(label == "followed")
        r.dismissed_fast += int(label == "dismissed_fast")
        for a in open_:
            self._see(a, t)

    # -------------------------------------------------------------------------------------------- router poll
    def _poll(self, ws: WorkerState, t: float) -> None:
        out = self.svc.next(self.pid, ws)                        # type: ignore[union-attr]
        self.res.held_peak = max(self.res.held_peak, out["badges"]["needs_you"])
        self._hint = float(out["poll_after_s"])
        if self.trace is not None:
            self.trace.append({"t": t, "e": "poll", "badges": dict(out["badges"]), "item": out["item"]["type"] if out.get("item") else None})
        it = out.get("item")
        if not it:
            return
        item = self.svc.store.person(self.pid).items[it["id"]]   # type: ignore[union-attr]
        if it["type"] == "attention_digest":
            pl = it["digest"] or {}
            self.res.digest_lines.append(len(pl.get("lines", [])))
            self.res.digest_folded.append(int(pl.get("can_ignore", 0)) + int(pl.get("ran", 0)))
            self._display(t, "attention_digest", item.subject, it["channel"], item_id=it["id"])
            self._see_open_needs_you(t)
            return
        self._display(t, it["type"], item.subject, it["channel"], reminder=bool(it["reminder"]), item_id=it["id"])

    # -------------------------------------------------------------------------------------------- finish
    def _finish(self) -> None:
        r = self.res
        for a in self.arr.values():
            if a.needs_you:
                r.needs_reminders.append(a.reminders)
            if not a.important or a.never_present or a.start is None:
                continue
            win = min(_window(a), max(1.0, a.expire - a.start))
            ok = a.seen is not None and a.seen - a.start <= win
            r.important_n += 1
            r.important_seen += int(ok)
            r.delays.append(a.seen - a.start if ok and a.seen is not None else math.inf)
            if a.cls == V.SAFETY:
                r.safety_n += 1
                r.safety_missed += int(not ok)
            if a.cls == V.TIME:
                r.time_n += 1
                r.time_missed += int(not ok)


def run_condition(world: World, condition: str, **kw: Any) -> WorkerResult:
    return Runner(world, condition, **kw).run()
