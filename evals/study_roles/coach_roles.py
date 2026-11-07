"""The coach path of the role harness: poll the engine like the desktop app, show what it decides, report how the participant answered. The coach is the real
one (engine ``GET /coach/next``, ``POST /coach/feedback``, rule based, no model); only the overlay renderer is simulated. Pure rules (what counts as following a
prompt, as a false one, as a study-mode violation) are role-generic: the step -> skill map comes from the PACK's expert steps and the controls that do a step from
``roles.follow_zones`` (zones, so they hold in both page layouts). The poller copies the idea of ``evals/study_sim/coach.CoachPoller`` with those rules injected.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from evals.study_sim.coach import Mode, PollRec, Shown            # noqa: F401  (plain data classes, shared)
from evals.study_sim.observe import Executed

from .roles import cfg, expected_zones, step_skill_key

POLL_S = 3.0
LAG_S = 6.0
SHOWN_ACTIONS = ("annotate", "nudge", "takeover_offer")
ACTION_KINDS = ("click", "fill", "select", "replace")


def target_step(decision: dict) -> str | None:
    missed = decision.get("missed") or []
    if missed:
        return missed[0]
    cand = decision.get("candidate") or {}
    return cand.get("step") or decision.get("step")


class Rules:
    """The role-specific rules, built once per role."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.follow = cfg(role).follow_zones

    def skill_of_step(self, step: str | None) -> str | None:
        return step_skill_key(self.role, step)

    def followed_by(self, step: str | None, e: Executed) -> bool:
        """Did this executed action do the missed step? An action on a control in one of the step's zones."""
        if not e.ok or e.kind not in ACTION_KINDS or not step:
            return False
        return (e.extra.get("zone") or "") in self.follow.get(step, ())

    def false_nudge(self, step: str | None, executed: list[Executed], t: float, lag_s: float = LAG_S) -> str:
        """'' (the step was still open), 'lag' (done less than lag_s before the prompt arrived) or 'false' (done earlier than that)."""
        done_at = next((e.t for e in executed if e.t <= t and self.followed_by(step, e)), None)
        if done_at is None:
            return ""
        return "lag" if t - done_at < lag_s else "false"

    def violation_of(self, mode: Mode, decision: dict) -> str:
        if decision.get("action", "silent") == "silent":
            return ""
        if mode.block in ("post_test", "off"):
            return f"coach acted ({decision.get('action')}) in a {mode.block} block"
        if mode.block == "train":
            sk = self.skill_of_step(target_step(decision))
            if sk != mode.skill:
                return f"coach acted on {sk or target_step(decision)} while only {mode.skill} was switched on"
        return ""

    def first_action_time(self, executed: list[Executed]) -> float | None:
        return next((e.t for e in executed if e.ok and e.kind in ACTION_KINDS), None)


class CoachPoller:
    """Polls ``GET /coach/next?person=`` every POLL_S seconds (steady pace, committing polls like the desktop app), queues what the coach wants shown, posts feedback."""

    def __init__(self, client, person: str, executed_ref: list[Executed], rules: Rules, interval: float = POLL_S) -> None:
        self.client, self.person, self.executed, self.rules, self.interval = client, person, executed_ref, rules, interval
        self.mode = Mode()
        self.polls: list[PollRec] = []
        self.shown: list[Shown] = []
        self.violations: list[str] = []
        self.errors: list[str] = []
        self.queue: asyncio.Queue[Shown] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.t_start = time.monotonic()

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
        rec = PollRec(t_wall, 200, d.get("action", "silent"), d.get("trigger"), list(d.get("reason_codes") or []), d.get("p_source"), target_step(d), tgt.get("zone"),
                      d.get("level", ""), d.get("chip", ""), d.get("decision_id"))
        rec.violation = self.rules.violation_of(self.mode, d)
        rec.mode = self.mode.block
        if rec.violation:
            self.violations.append(f"{self.mode.label}: {rec.violation}")
        self.polls.append(rec)
        if rec.action in SHOWN_ACTIONS and d.get("decision_id"):
            step = target_step(d)
            sh = Shown(decision_id=d["decision_id"], action=rec.action, message=str(d.get("message", "")), zone=tgt.get("zone"), step=step, skill=self.rules.skill_of_step(step),
                       missed=list(d.get("missed") or []), trigger=d.get("trigger"), t_wall=t_wall, t_mono=time.monotonic(), level=d.get("level", ""), p_source=d.get("p_source"))
            sh.false = self.rules.false_nudge(step, self.executed, time.monotonic())
            t0 = self.rules.first_action_time(self.executed)
            sh.delay_s = round(sh.t_mono - (t0 if t0 is not None else self.t_start), 2)
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
    dismissed: int = 0
    ignored: int = 0
    explicit_dismissed: int = 0
    false_nudges: int = 0
    lag_prompts: int = 0
    rings_drawn: int = 0
    banners_only: int = 0
    zone_ok: int = 0
    delays_s: list[float] = field(default_factory=list)

    @classmethod
    def of(cls, shown: list[Shown], role: str) -> "NudgeCounts":
        c = cls()
        for s in shown:
            c.shown += 1
            c.followed += s.outcome == "followed"
            c.explicit_dismissed += s.outcome == "dismissed"
            c.ignored += s.outcome == "ignored"
            c.false_nudges += s.false == "false"
            c.lag_prompts += s.false == "lag"
            if s.ring_found is True:
                c.rings_drawn += 1
            elif s.zone:
                c.banners_only += 1
            if s.delay_s is not None:
                c.delays_s.append(s.delay_s)
            if s.action in ("annotate", "takeover_offer") and s.skill and s.zone in expected_zones(role, s.skill):
                c.zone_ok += 1
        c.dismissed = c.explicit_dismissed + c.ignored
        return c
