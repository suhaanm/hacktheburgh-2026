from __future__ import annotations

from understudy_engine.cue.gate import CueState, decide
from understudy_engine.cue.params import DEFAULT, CueParams
from understudy_engine.cue.types import Candidate, CueInput, Grounding

T0 = 1_800_000_000.0     # a fixed unix time (a Tuesday in 2027); only differences matter


def cand(step: str, p: float, *, label: str | None = None, skill: str | None = None, group: str | None = None, in_progress: bool = False) -> Candidate:
    return Candidate(id=step, group=group or step, label=label or step.replace("_", " ").title(), p=p, skill=skill or step,
                     reason_id="why.generic", cogs=(), in_progress=in_progress)


CLIFF = (cand("cliff_a", 0.85, label="Check cliff edges (A)", skill="check-the-cliff", group="cliff_a"), cand("calc_b", 0.15, group="calc_a"))
CLOSE = (cand("cliff_a", 0.52, label="Check cliff edges (A)", skill="check-the-cliff", group="cliff_a"), cand("calc_b", 0.48, group="calc_a"),
         cand("reconcile", 0.0))


def grounded(step: str = "cliff_a", conf: float = 0.9, source: str = "dom") -> Grounding:
    return Grounding(found=True, chosen=step, available=(step,), box_2d=(100, 200, 160, 420), confidence=conf, source=source, for_step=step)


def inp(t: float, *, stall: float = 100.0, p: float = 0.85, cands=CLIFF, level: int = 2, mastery: float = 0.1, **kw) -> CueInput:
    base = dict(now=T0 + t, person="p_test", role="benefits-processor", p_stuck=p, p_source="rule", last_progress_t=T0 + t - stall,
                candidates=tuple(cands), level=level, mastery=mastery, grounding=grounded(), quiet_s=10.0)
    base.update(kw)
    return CueInput(**base)


class Run:
    """Poll the gate at chosen times, keeping the state; the progress clock keeps its own anchor so stalls grow with time."""

    def __init__(self, params: CueParams = DEFAULT, start_stall: float = 100.0, **fixed) -> None:
        self.st = CueState()
        self.p = params
        self.fixed = fixed
        self.progress_t = T0 - start_stall
        self.log: list = []
        self.decide_kw: dict = {}          # extra keyword arguments for decide(), for example reason_text and step_target

    def poll(self, t: float, **kw):
        k = dict(self.fixed)
        k.update(kw)
        stall = k.pop("stall", None)
        i = inp(t, stall=(T0 + t - self.progress_t) if stall is None else stall, **k)
        if stall is not None:
            self.progress_t = T0 + t - stall
        r = decide(i, self.st, self.p, **self.decide_kw)
        self.st = r.state
        self.log.append((t, r))
        return r

    def progress(self, t: float) -> None:
        self.progress_t = T0 + t
