"""A session simulator for Cue (CUE-3 evaluation, STU-4 groundwork): synthetic workers, planted stuck episodes, an attention-cost model for
interruptions, a FAKE grounding port that is right at a configurable rate, and the REAL decision gate in the loop.

SIMULATED. The world model below is mine, written down in ``evals/cue/PLAN.md`` before any held-out run. It shows how the policy behaves
under these assumptions; it does not show that Cue works on people. All numbers in this file are assumptions, not measurements.

World (every constant is in ``ASSUME``):
* A worker does cases of the benefits pack: a random linear extension of the pack's order (people differ in how often they batch the
  cliff checks). Each step has a lead and then work. The lead is either a stuck STALL (the worker does not know what to do next; heavy
  tailed), or a thinking PAUSE (the worker knows; this is NOT stuck and is where false nudges come from), or nothing. Work follows, with
  typing most of the time (so the flow rule keeps Cue quiet).
* The probability of a stall at a skill step is ``base * (1 - mastery)^1.2`` with the worker's true mastery of that skill; mastery rises
  with practice and more with help. The gate sees the real level engine and tracing model (``skills.SkillTracker``), not the planted value.
* The stuck signal is the coach's real rule fallback (``heuristic_p`` of the time since the last progress event), or, as a secondary sweep,
  an emulated model signal with a stated discriminability (``signal="emulated"``).
* Candidates are the real ``NextStepModel`` fitted on experts sampled with a seed the workers do not share. Grounding is ``FakeGrounding``.
* Reactions: a correct cue to a stalled worker is followed with probability ``accept x tier boost x (1 - 0.5 mastery)`` (0.95 once the worker
  asked for help by accepting an offer or answering a question), ending the stall after a lognormal reaction time; a wrong cue adds
  confusion seconds; a question whose options hold the needed step is answered and then the cue follows; any intervention shown to a worker
  who is not stalled is a FALSE NUDGE that costs lost-focus seconds and is mostly dismissed.
* The same random plan (every duration and every decision uniform) runs with no Cue and with Cue, so the stall effect is paired.

Voice is never allowed in the simulation (``voice_ok`` False): visual by default.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..coach.signals import heuristic_p
from ..skills import SkillTracker
from ..skills import levels as LV
from ..skills import tracing as TR
from . import expert_data as XD
from . import ledger as L
from .candidates import NextStepModel
from .gate import CueState, apply_event, decide, episode_id
from .params import DEFAULT, CueParams
from .ports import FakeGrounding, GroundingPort
from .types import Candidate, CueInput, Grounding
from .vocab import StepVocab, get_vocab

DT = 2.5
T_BASE = 1_800_000_000.0 - (1_800_000_000.0 % 86400.0) + 9 * 3600.0         # 09:00 UTC on a fixed day
GROUND_TTL_S = 20.0

ASSUME: dict[str, Any] = {
    "stall_median_s": 80.0, "stall_sigma": 0.7,                       # heavy-tailed stall when stuck
    "pause_median_s": 25.0, "pause_sigma": 0.8,                       # thinking pause: NOT stuck
    "work_sigma": 0.25, "stuck_exponent": 1.2,
    "typing_prob_in_work": 0.8, "move_prob_stall": 0.10, "move_prob_pause": 0.03,
    "react_median_s": 6.0, "react_sigma": 0.4,
    "tier_boost": {1: 0.70, 2: 0.90, 3: 1.00, 4: 0.90},
    "follow_mastery_discount": 0.5, "follow_when_help_wanted": 0.95,
    "wrong_cue_confusion_s": 8.0, "wrong_cue_dismiss": 0.8,
    "false_nudge_cost_s": {"ring": 3.0, "chip": 5.0, "ghost": 8.0, "voice": 6.0, "ask": 10.0, "offer": 3.0},
    "false_nudge_dismiss": 0.85, "answer_prob": 0.85, "answer_s": 4.0, "answer_cost_when_stuck_s": 4.0,
    "offer_accept_stuck": (0.10, 0.40), "offer_accept_not_stuck": 0.05,
    "practice_gain": {"clean": 0.03, "assisted": 0.08, "struggled": 0.05},
    "error_prob": 0.03, "error_prob_after_confusion": 0.15,
    "stuck_base_beta": (2.0, 12.0), "pause_beta": (2.0, 6.0), "accept_beta": (6.0, 2.5), "batch_beta": (1.2, 4.0),
    "speed_sigma": 0.20, "emulated_dprime": 1.5,
}


# ------------------------------------------------------------------------------------------------ population
@dataclass(frozen=True)
class Worker:
    id: str
    persona: str
    speed: float
    base_stuck: float
    m0: float
    pause_p: float
    accept: float
    batch_p: float


def make_population(seed: int, n: int = 40) -> list[Worker]:
    """``n`` workers, a quarter around each v1 persona (its ``speed`` and starting skill ``s0``), with person-level effects. When a
    ``personas_v2`` module exposing ``worker_params(seed, n)`` exists it is used instead (try-import; ``None`` today)."""
    try:                                                          # the REALISM track's generator, when it lands with this hook
        from .. import personas_v2                                # type: ignore[attr-defined]

        fn = getattr(personas_v2, "worker_params", None)
        if callable(fn):
            return [Worker(**w) for w in fn(seed, n)]
    except ImportError:
        pass
    from ..personas import PERSONAS

    rng = np.random.default_rng(seed)
    a = ASSUME
    out = []
    for i in range(n):
        spec = PERSONAS[i % len(PERSONAS)]
        out.append(Worker(
            id=f"w{seed}_{i:02d}", persona=spec.slug, speed=float(spec.speed * rng.lognormal(0.0, a["speed_sigma"])),
            base_stuck=float(rng.beta(*a["stuck_base_beta"])), m0=float(np.clip(spec.s0 + rng.normal(0.0, 0.08), 0.05, 0.8)),
            pause_p=float(rng.beta(*a["pause_beta"])), accept=float(rng.beta(*a["accept_beta"])), batch_p=float(rng.beta(*a["batch_beta"]))))
    return out


# ------------------------------------------------------------------------------------------------ plans (standard randoms only)
@dataclass(frozen=True)
class StepPlan:
    step: str
    z_work: float
    z_pause: float
    z_stall: float
    z_react: float
    u_pause: float
    u_stuck: float
    u_follow: float
    u_dismiss: float
    u_answer: float
    u_offer: float


def plan_case(vocab: StepVocab, w: Worker, rep_seed: int, w_idx: int, case_idx: int) -> list[StepPlan]:
    rng = np.random.default_rng(np.random.SeedSequence([rep_seed, w_idx, case_idx, 1]))
    steps = XD.sample_steps(vocab, rng, batch_p=w.batch_p)
    out = []
    for s in steps:
        z = rng.standard_normal(4)
        u = rng.random(6)
        out.append(StepPlan(s, float(z[0]), float(z[1]), float(z[2]), float(z[3]), float(u[0]), float(u[1]), float(u[2]), float(u[3]), float(u[4]), float(u[5])))
    return out


# ------------------------------------------------------------------------------------------------ state and results
@dataclass
class WorkerState:
    accept: float
    m: dict[str, float] = field(default_factory=dict)
    tracker: SkillTracker = field(default_factory=SkillTracker)
    cue_state: CueState = field(default_factory=CueState)
    ground_cache: dict = field(default_factory=dict)
    first_show: dict[str, float] = field(default_factory=dict)       # skill -> time of the first show of the latest unrequested episode


@dataclass
class Intervention:
    t: float
    kind: str
    tier: int | None
    label: str
    stuck_now: bool
    correct: bool
    wrong_target: bool
    skill: str
    step: str
    asked: bool
    outcome: str = "ignored"          # accepted | dismissed | ignored
    cost_s: float = 0.0
    tau: float | None = None          # seconds since the stall began (stuck only)


@dataclass
class EpisodeRecord:
    worker: str
    step: str
    skill: str
    stall_s: float                    # the no-cue stall (from the plan)
    realised_s: float = 0.0           # the stall as it was
    first_cue_tau: float | None = None
    correct_appeared: bool = False
    any_cue: bool = False
    accepted: bool = False


@dataclass
class WorkerResult:
    worker: str
    seconds: float = 0.0
    interventions: list[Intervention] = field(default_factory=list)
    episodes: list[EpisodeRecord] = field(default_factory=list)
    ticks: int = 0
    stuck_ticks: int = 0
    silent_ticks: int = 0
    silent_stuck_ticks: int = 0
    questions_by_episode: dict[str, int] = field(default_factory=dict)
    gate_episodes: int = 0
    violations: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    choices: list[dict] = field(default_factory=list)
    cases: int = 0


class _Step:
    """The mutable state of one step while it is being simulated."""

    def __init__(self, plan: StepPlan, w: Worker, vocab: StepVocab, m: float, t0: float) -> None:
        A = ASSUME
        self.plan, self.step, self.t0 = plan, plan.step, t0
        pol = vocab.policy.steps[plan.step]
        self.skill = vocab.skill(plan.step)
        self.cogs = vocab.cogs(plan.step)
        self.group = vocab.group(plan.step)
        self.m = m
        self.stuck = bool(pol.skill is not None and plan.u_stuck < w.base_stuck * (1.0 - m) ** A["stuck_exponent"])
        self.stall = float(math.exp(math.log(A["stall_median_s"]) + A["stall_sigma"] * plan.z_stall)) if self.stuck else 0.0
        pause = 0.0 if self.stuck or plan.u_pause >= w.pause_p else float(math.exp(math.log(A["pause_median_s"]) + A["pause_sigma"] * plan.z_pause))
        med = pol.median_s or 40.0
        self.work = max(5.0, float(math.exp(math.log(med * w.speed) + A["work_sigma"] * plan.z_work)))
        self.lead_end = t0 + (self.stall if self.stuck else pause)
        self.extra = 0.0
        self.react = max(2.0, float(math.exp(math.log(A["react_median_s"]) + A["react_sigma"] * plan.z_react)))
        self.accepted = False
        self.confusion = False
        self.rec = EpisodeRecord("", plan.step, self.skill, self.stall) if self.stuck else None
        self.pending: list[Intervention] = []

    @property
    def end(self) -> float:
        return self.lead_end + self.work + self.extra


# ------------------------------------------------------------------------------------------------ the simulator
class Simulator:
    def __init__(self, *, params: CueParams = DEFAULT, ground_accuracy: float = 0.9, signal: str = "rule", model: NextStepModel | None = None,
                 vocab: StepVocab | None = None, ledger: bool = False, chooser=None, port: GroundingPort | None = None, model_seed: int = 9001,
                 expert_batch_beta: tuple[float, float] = (1.2, 4.0)) -> None:
        self.vocab = vocab or get_vocab("benefits-processor")
        assert self.vocab is not None
        self.params = params
        self.signal = signal
        self.ground_accuracy = ground_accuracy
        self.ledger = ledger
        self.chooser = chooser
        self._port = port
        if model is None:
            paths = XD.sample_paths(self.vocab, n_people=30, cases=3, seed=model_seed, batch_beta=expert_batch_beta)
            model = NextStepModel(self.vocab).fit(s for cs in paths.values() for s in cs)
        self.model = model
        self._cands: dict[tuple[str, ...], list[Candidate]] = {}

    def _candidates(self, hist: tuple[str, ...]) -> list[Candidate]:
        c = self._cands.get(hist)
        if c is None:
            c = self._cands[hist] = self.model.candidates(hist)[0]
        return c

    def _lm(self, ws: WorkerState, cogs: tuple[str, ...], now: float) -> tuple[int, float]:
        lv, ms = [], []
        for c in cogs:
            cs = ws.tracker.cogs.get(c)
            if cs is None:
                lv.append(1)
                ms.append(TR.DEFAULT.p_init)
                continue
            m = TR.decayed(cs.mastery, now)
            lv.append(LV.apply_decay(cs.level, m)[0].level)
            ms.append(m)
        return (min(lv) if lv else 1), (min(ms) if ms else TR.DEFAULT.p_init)

    def _signal_p(self, tsp: float, stuck_now: bool, rng) -> float:
        if self.signal == "emulated":
            score = ASSUME["emulated_dprime"] * (1.0 if stuck_now else 0.0) + float(rng.standard_normal())
            return float(1.0 / (1.0 + math.exp(-(1.6 * score - 1.2))))
        return heuristic_p(tsp)

    # ---- one run over a population
    def run(self, pop: list[Worker], rep_seed: int, *, arm: str = "cue", sessions: int = 3, cases_per_session: int = 4) -> list[WorkerResult]:
        if arm not in ("cue", "none"):
            raise ValueError("arm must be 'cue' or 'none'")
        results = []
        for w_idx, w in enumerate(pop):
            port = self._port or FakeGrounding(self.ground_accuracy, seed=int(np.random.SeedSequence([rep_seed, w_idx, 7]).generate_state(1)[0]))
            res = WorkerResult(w.id)
            ws = WorkerState(accept=w.accept)
            for sess in range(sessions):
                t = T_BASE + sess * 86400.0
                for c in range(cases_per_session):
                    k = sess * cases_per_session + c
                    plan = plan_case(self.vocab, w, rep_seed, w_idx, k)
                    rng = np.random.default_rng(np.random.SeedSequence([rep_seed, w_idx, k, 2]))
                    t0 = t
                    t = self._run_case(w, ws, plan, t, arm, port, rng, res)
                    res.seconds += t - t0
                    res.cases += 1
                    t += 180.0                                 # a break between cases; the progress clock restarts with the next case
            results.append(res)
        return results

    # ---- one case
    def _run_case(self, w: Worker, ws: WorkerState, plan: list[StepPlan], t: float, arm: str, port: GroundingPort, rng, res: WorkerResult) -> float:
        A, v, p = ASSUME, self.vocab, self.params
        hist: list[str] = []
        last_progress = t
        quiet_acc = 10.0
        for sp in plan:
            sx = _Step(sp, w, v, ws.m.setdefault(v.skill(sp.step), w.m0), t)
            if sx.rec is not None:
                sx.rec.worker = w.id
            hist_t, hist_work = tuple(hist), tuple(hist + [sx.cogs[0]])
            now = t
            while True:
                in_work = now >= sx.lead_end
                if in_work and now >= sx.end:
                    break
                stuck_now = sx.stuck and not in_work
                pr = self._signal_p(now - last_progress, stuck_now, rng)
                if in_work:
                    typing = bool(rng.random() < A["typing_prob_in_work"])
                    quiet_acc = 0.0 if typing else float(rng.exponential(1.2))
                else:
                    typing = False
                    quiet_acc = 0.0 if rng.random() < (A["move_prob_stall"] if sx.stuck else A["move_prob_pause"]) else quiet_acc + DT
                res.ticks += 1
                res.stuck_ticks += stuck_now
                kind = "none"
                if arm == "cue":
                    st = ws.cue_state
                    helped = bool(st.episode and st.episode.help_wanted)
                    flow = (typing or quiet_acc < p.quiet_required_s) and not helped and (st.gate.consecutive == 0 or st.episode is not None)
                    idle = pr < p.p_signal and st.episode is None and st.gate.consecutive == 0 and not helped
                    if not (flow or idle):
                        hk = hist_work if in_work else hist_t
                        cands = self._candidates(hk)
                        top = cands[0] if cands else None
                        if top is not None:
                            level, mastery = self._lm(ws, top.cogs, now)
                            ground = self._ground(ws, port, cands, top, sx.step, now, hk)
                            inp = CueInput(now=now, person=w.id, role=v.role, p_stuck=pr, p_source="rule" if self.signal == "rule" else "model",
                                           last_progress_t=last_progress, candidates=tuple(cands), level=level, mastery=mastery, grounding=ground,
                                           quiet_s=quiet_acc, typing_burst=typing, voice_ok=False)
                            r = decide(inp, st, p, chooser=self.chooser)
                            ws.cue_state = r.state
                            kind = r.decision.kind
                            res.gate_episodes += bool(r.opened)
                            if r.choice is not None:
                                res.choices.append({"t": now, "stuck_now": stuck_now, "choice": r.choice, "p": pr, "margin": r.decision.why["margin"], "level": level,
                                                    "mastery": mastery, "n_before": len(res.interventions) + len(sx.pending)})
                            if r.shown:
                                self._invariants(r, helped, typing, quiet_acc, level, now, res, ws, sx.skill)
                                self._react(w, ws, sx, r, ground, stuck_now, now, helped)
                    silent = kind in ("none", "confirm")
                    res.silent_ticks += silent
                    res.silent_stuck_ticks += silent and stuck_now
                now += DT
            t = sx.end
            last_progress = t
            hist.extend(sx.cogs)
            self._finish_step(w, ws, sx, t, res)
        return t

    def _ground(self, ws: WorkerState, port: GroundingPort, cands: list[Candidate], top: Candidate, step: str, now: float, hk: tuple[str, ...]) -> Grounding:
        key = (top.id, len(hk))
        hit = ws.ground_cache.get(key)
        if hit is not None and now - hit.t <= GROUND_TTL_S:
            return hit
        truth = next((c.id for c in cands if c.group == self.vocab.group(step)), None)
        g = port.ground(menu=[(c.id, c.label) for c in cands[:4]], truth=truth, for_step=top.id, t=now)
        ws.ground_cache = {k: x for k, x in ws.ground_cache.items() if now - x.t <= GROUND_TTL_S}
        ws.ground_cache[key] = g
        return g

    # ---- the worker's reaction to a shown intervention
    def _react(self, w: Worker, ws: WorkerState, sx: _Step, r, ground: Grounding | None, stuck_now: bool, now: float, helped: bool) -> None:
        A, v, p = ASSUME, self.vocab, self.params
        d = r.decision
        kind, tier = d.kind, d.tier
        label = {"cue": {1: "ring", 2: "chip", 3: "ghost", 4: "voice"}.get(tier or 2, "chip"), "ask": "ask", "offer": "offer"}[kind]
        correct = wrong_target = False
        if kind == "cue":
            correct = v.group(d.step["id"]) == sx.group
            if d.target and d.target.get("box_2d") is not None and ground is not None and ground.chosen is not None:
                wrong_target = v.group(ground.chosen) != sx.group
        elif kind == "ask":
            correct = any(v.group(o["id"]) == sx.group for o in (d.options or []) if o["id"] != "other")
        iv = Intervention(t=now, kind=kind, tier=tier, label=label, stuck_now=stuck_now, correct=correct, wrong_target=wrong_target, skill=sx.skill,
                          step=sx.step, asked=helped, tau=(now - sx.t0) if stuck_now else None)
        sx.pending.append(iv)
        rec, sp, st = sx.rec, sx.plan, ws.cue_state
        if rec is not None and stuck_now:
            rec.any_cue = True
            if rec.first_cue_tau is None:
                rec.first_cue_tau = iv.tau

        def cost(c: float) -> None:
            iv.cost_s = c
            if now < sx.lead_end:
                sx.lead_end += c
            else:
                sx.extra += c

        def dismiss(prob: float) -> None:
            if sp.u_dismiss < prob:
                iv.outcome = "dismissed"
                ws.cue_state = apply_event(ws.cue_state, "dismissed", now + 2.0, p)

        if kind == "cue":
            if stuck_now and correct and not wrong_target:
                thr = A["follow_when_help_wanted"] if helped else ws.accept * A["tier_boost"][tier or 2] * (1.0 - A["follow_mastery_discount"] * sx.m)
                if rec is not None:
                    rec.correct_appeared = True
                if sp.u_follow < thr:
                    iv.outcome = "accepted"
                    sx.lead_end = min(sx.lead_end, now + sx.react)
                    sx.accepted = True
                    ws.cue_state = apply_event(st, "accepted", now, p)
                    if rec is not None:
                        rec.accepted = True
                else:
                    dismiss(0.5)
            elif stuck_now:                                                    # a wrong cue to a stalled worker: confusion
                sx.lead_end += A["wrong_cue_confusion_s"]
                iv.cost_s = A["wrong_cue_confusion_s"]
                sx.confusion = True
                dismiss(A["wrong_cue_dismiss"])
            else:                                                              # a false nudge
                cost(A["false_nudge_cost_s"][label])
                dismiss(A["false_nudge_dismiss"])
        elif kind == "ask":
            if stuck_now:
                if sp.u_answer < A["answer_prob"]:
                    opts = [o for o in (st.episode.options if st.episode else ()) if o != "other"]
                    needed_opt = next((o for o in opts if v.group(o) == sx.group), None)
                    iv.outcome = "accepted"
                    iv.cost_s = A["answer_cost_when_stuck_s"]
                    if rec is not None and correct:
                        rec.correct_appeared = True
                    ws.cue_state = apply_event(st, "answered", now + A["answer_s"], p, answer_id=needed_opt or "other")
            else:
                cost(A["false_nudge_cost_s"]["ask"])
                dismiss(A["false_nudge_dismiss"])
        else:                                                                  # offer
            if stuck_now:
                lo, hi = A["offer_accept_stuck"]
                if sp.u_offer < lo + hi * ws.accept:
                    iv.outcome = "accepted"
                    ws.cue_state = apply_event(st, "accepted", now, p)
            else:
                cost(A["false_nudge_cost_s"]["offer"])
                if sp.u_offer < A["offer_accept_not_stuck"]:
                    iv.outcome = "accepted"
                    ws.cue_state = apply_event(st, "accepted", now, p)
                else:
                    dismiss(A["false_nudge_dismiss"])

    def _finish_step(self, w: Worker, ws: WorkerState, sx: _Step, t: float, res: WorkerResult) -> None:
        A = ASSUME
        res.interventions.extend(sx.pending)
        if sx.rec is not None:
            sx.rec.realised_s = max(0.0, sx.lead_end - sx.t0)
            res.episodes.append(sx.rec)
        gain = A["practice_gain"]["assisted" if sx.accepted else ("struggled" if sx.stuck else "clean")]
        ws.m[sx.skill] = sx.m + gain * (1.0 - sx.m)
        err_p = A["error_prob_after_confusion"] if sx.confusion else A["error_prob"]
        outcome = "assisted" if sx.accepted else ("error" if (sx.plan.u_answer < err_p and not sx.stuck) else "clean")
        for c in sx.cogs:
            ws.tracker.observe(c, outcome, t)                                    # type: ignore[arg-type]
        # choice logs: resolve rewards for decisions made in this step
        for ch in res.choices:
            if "reward" in ch or ch.get("step_end") is not None:
                continue
            ch["step_end"] = t
            ch["resumed_at"] = sx.lead_end
        if self.ledger:
            pid = "p_" + w.id.replace("_", "")[:28]
            res.rows.append(L.make_row(person=pid, role=self.vocab.role, skill=sx.skill, step=sx.step, t=t, outcome=outcome, origin="synthetic",
                                       trigger="auto" if sx.accepted else "none", tier=2 if sx.accepted else 0, accepted=sx.accepted,
                                       origin_detail="synthetic_learner", serial=len(res.rows),
                                       lost_s=(t - sx.t0) - (self.vocab.policy.steps[sx.step].median_s or 40.0)))

    def _invariants(self, r, helped: bool, typing: bool, quiet_s: float, level: int, now: float, res: WorkerResult, ws: WorkerState, skill: str) -> None:
        d, p = r.decision, self.params
        ep = r.state.episode
        if not helped:
            if len([x for x in r.state.shown_ts if now - x < p.cap_window_s]) > p.max_cues_window:
                res.violations.append("cap_10min")
            if typing or quiet_s < p.quiet_required_s:
                res.violations.append("flow")
            if level >= 4:
                res.violations.append("level_4")
        if d.kind == "ask" and ep is not None:
            res.questions_by_episode[ep.id] = res.questions_by_episode.get(ep.id, 0) + 1
            if res.questions_by_episode[ep.id] > p.max_questions:
                res.violations.append("questions_per_episode")
        if (d.say or {}).get("whisper"):
            res.violations.append("whisper_without_voice_ok")
        if (d.say or {}).get("chip") and len(d.say["chip"]) > 40:
            res.violations.append("chip_length")
        if r.opened and not helped:
            last = ws.first_show.get(skill)
            if last is not None and now - last < p.skill_gap_s - 1e-6:
                res.violations.append("skill_gap")
        if r.opened:
            ws.first_show[skill] = now
