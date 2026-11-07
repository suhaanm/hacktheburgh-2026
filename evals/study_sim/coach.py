"""The coach path of the harness: poll the engine like the desktop app, show what it decides, report how the participant answered.

The coach itself is the real one (engine ``GET /coach/next``, ``POST /coach/feedback``, rule based, no model). Only the renderer
is simulated: ``runner`` draws the overlay in the page the participant is on. This module holds the pure rules (what counts
as following, as a false prompt, as a study-mode violation) and the async poller.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from .observe import Executed

POLL_S = 3.0
LAG_S = 6.0                       # a step done this long before the prompt arrived counts as a lagged prompt, not a false one
SHOWN_ACTIONS = ("annotate", "nudge", "takeover_offer")
CLIFF_STEPS = {"cliff_a": 1, "cliff_b": 2, "cliff_c": 3}
# the zones of the control a prompt may point at for each skill. The engine's reconcile target was results_tabs (no page element) when the plan was
# written and became reconcile_control (the case note's reconciliation dropdown) while the build was going on; both are the reconcile control.
EXPECTED_ZONES = {"cliff": {"cliff_button"}, "reconcile": {"results_tabs", "reconcile_control"}}
RECONCILE_IDS = {"reconciliation", "cn-recon"}


def skill_of_step(step: str | None) -> str | None:
    if not step:
        return None
    if step.startswith("cliff_"):
        return "cliff"
    if step == "reconcile":
        return "reconcile"
    return None


def target_step(decision: dict) -> str | None:
    missed = decision.get("missed") or []
    if missed:
        return missed[0]
    cand = decision.get("candidate") or {}
    return cand.get("step") or decision.get("step")


def followed_by(skill: str | None, e: Executed) -> bool:
    """Did this executed action do the missed step? cliff: pressed Check cliff edges. reconcile: made the comparison choice on the
    case note form or switched between the calculator tabs (the engine's own RECONCILE cog is a tab switch)."""
    if not e.ok:
        return False
    if skill == "cliff":
        return e.kind == "click" and e.dom_id == "cliff-btn"
    if skill == "reconcile":
        return (e.kind == "select" and e.dom_id in RECONCILE_IDS) or e.kind == "switch_tab"
    return False


def false_nudge(skill: str | None, step: str | None, executed: list[Executed], t: float, lag_s: float = LAG_S) -> str:
    """'' (the step was still open), 'lag' (done less than lag_s before the prompt arrived) or 'false' (done earlier than that)."""
    done_at: float | None = None
    if skill == "cliff":
        need = CLIFF_STEPS.get(step or "", 1)
        seen: dict[str, float] = {}
        for e in executed:
            if e.t <= t and followed_by("cliff", e) and e.site is not None and e.site not in seen:
                seen[e.site] = e.t
        times = sorted(seen.values())
        if len(times) >= need:
            done_at = times[need - 1]
    elif skill == "reconcile":
        for e in executed:
            if e.t <= t and followed_by("reconcile", e):
                done_at = e.t
                break
    if done_at is None:
        return ""
    return "lag" if t - done_at < lag_s else "false"


def first_note_interaction(executed: list[Executed]) -> float | None:
    """When the participant first acted on the case note page (the moment the missed step starts to matter)."""
    for e in executed:
        if e.ok and e.path.startswith("/casenote") and e.kind in ("click", "fill", "select", "switch_tab", "goto"):
            return e.t
    return None


@dataclass
class Mode:
    """What study mode the harness has set on the engine (for the enforcement check)."""
    block: str = "off"            # train | post_test | off
    skill: str | None = None      # cliff | reconcile (the trained skill) when block is train
    label: str = ""               # e.g. "p_sim01 block 1 practice"


def violation_of(mode: Mode, decision: dict) -> str:
    """A study-mode violation: the coach acted when this mode says it must not. '' when fine."""
    if decision.get("action", "silent") == "silent":
        return ""
    if mode.block in ("post_test", "off"):
        return f"coach acted ({decision.get('action')}) in a {mode.block} block"
    if mode.block == "train":
        sk = skill_of_step(target_step(decision))
        if sk != mode.skill:
            return f"coach acted on {sk or target_step(decision)} while only {mode.skill} was switched on"
    return ""


@dataclass
class Shown:
    decision_id: str
    action: str
    message: str
    zone: str | None
    step: str | None
    skill: str | None
    missed: list[str]
    trigger: str | None
    t_wall: float                  # time.time() when the poll answered
    t_mono: float
    ring_found: bool | None = None
    ring_on_arrival: bool | None = None
    outcome: str | None = None     # followed | dismissed | ignored
    t_outcome: float | None = None
    false: str = ""                # '' | lag | false
    delay_s: float | None = None   # from the first interaction with the case note page to the overlay
    level: str = ""
    p_source: str | None = None


@dataclass
class PollRec:
    t_wall: float
    status: int
    action: str
    trigger: str | None
    reason_codes: list[str]
    p_source: str | None
    step: str | None
    zone: str | None
    level: str
    chip: str
    decision_id: str | None
    violation: str = ""
    mode: str = ""


class CoachPoller:
    """Polls ``GET /coach/next?person=`` every POLL_S seconds (steady pace, a committing poll like the desktop app's), queues what
    the coach wants shown, and posts ``POST /coach/feedback``."""

    def __init__(self, client, person: str, executed_ref: list[Executed], interval: float = POLL_S) -> None:
        self.client = client                  # httpx.AsyncClient with base_url = the engine
        self.person = person
        self.executed = executed_ref
        self.interval = interval
        self.mode = Mode()
        self.polls: list[PollRec] = []
        self.shown: list[Shown] = []
        self.violations: list[str] = []
        self.errors: list[str] = []
        self.queue: asyncio.Queue[Shown] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def poll_once(self) -> PollRec | None:
        t_wall = time.time()
        try:
            r = await self.client.get("/coach/next", params={"person": self.person}, timeout=10)
        except Exception as exc:  # noqa: BLE001 - recorded as an engine error, the run goes on
            self.errors.append(f"coach/next: {type(exc).__name__}")
            return None
        if r.status_code != 200:
            self.errors.append(f"coach/next status {r.status_code}")
            rec = PollRec(t_wall, r.status_code, "error", None, [], None, None, None, "", "", None)
            self.polls.append(rec)
            return rec
        d = r.json().get("data", {})
        tgt = d.get("target") or {}
        rec = PollRec(t_wall, 200, d.get("action", "silent"), d.get("trigger"), list(d.get("reason_codes") or []), d.get("p_source"),
                      target_step(d), tgt.get("zone"), d.get("level", ""), d.get("chip", ""), d.get("decision_id"))
        rec.violation = violation_of(self.mode, d)
        rec.mode = self.mode.block
        if rec.violation:
            self.violations.append(f"{self.mode.label}: {rec.violation}")
        self.polls.append(rec)
        if rec.action in SHOWN_ACTIONS and d.get("decision_id"):
            step = target_step(d)
            skill = skill_of_step(step)
            sh = Shown(decision_id=d["decision_id"], action=rec.action, message=str(d.get("message", "")), zone=tgt.get("zone"), step=step,
                       skill=skill, missed=list(d.get("missed") or []), trigger=d.get("trigger"), t_wall=t_wall, t_mono=time.monotonic(),
                       level=d.get("level", ""), p_source=d.get("p_source"))
            sh.false = false_nudge(skill, step, self.executed, time.monotonic())
            note_t = first_note_interaction(self.executed)
            sh.delay_s = None if note_t is None else round(sh.t_mono - note_t, 2)
            self.shown.append(sh)
            await self.queue.put(sh)
        return rec

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            await self.poll_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0.0, self.interval - (time.monotonic() - t0)))
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None

    async def feedback(self, sh: Shown, outcome: str) -> None:
        """outcome is what is posted to the engine: followed | dismissed."""
        try:
            r = await self.client.post("/coach/feedback", json={"decision_id": sh.decision_id, "outcome": outcome}, timeout=10)
            if r.status_code != 200:
                self.errors.append(f"coach/feedback status {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"coach/feedback: {type(exc).__name__}")


@dataclass
class NudgeCounts:
    shown: int = 0
    followed: int = 0
    dismissed: int = 0            # explicit dismiss plus ignored-at-case-end (both posted as dismissed)
    ignored: int = 0
    explicit_dismissed: int = 0
    false_nudges: int = 0
    lag_prompts: int = 0
    rings_drawn: int = 0
    banners_only: int = 0
    delays_s: list[float] = field(default_factory=list)
    zones: list[tuple[str | None, str | None]] = field(default_factory=list)   # (zone shown, expected zone for the step)

    @classmethod
    def of(cls, shown: list[Shown]) -> "NudgeCounts":
        c = cls()
        expected = EXPECTED_ZONES
        for s in shown:
            c.shown += 1
            c.followed += s.outcome == "followed"
            if s.outcome == "dismissed":
                c.explicit_dismissed += 1
            c.ignored += s.outcome == "ignored"
            c.false_nudges += s.false == "false"
            c.lag_prompts += s.false == "lag"
            if s.ring_found is True:
                c.rings_drawn += 1
            elif s.zone:
                c.banners_only += 1
            if s.delay_s is not None:
                c.delays_s.append(s.delay_s)
            if s.action in ("annotate", "takeover_offer"):
                c.zones.append((s.zone, s.zone if s.zone in expected.get(s.skill or "", set()) else None))
        c.dismissed = c.explicit_dismissed + c.ignored
        return c
