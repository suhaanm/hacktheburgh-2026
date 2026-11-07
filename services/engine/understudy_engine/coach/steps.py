"""The expert policy as something a live trace can be checked against (COA-3, COA-4).

A pack's ``expert_steps.yaml`` is a partial order of checks. Each check names the cogs that make it up, what it
needs done first (``after``), and whether it is ``critical``. Calculators and cliff probes may be visited in any
order (``allowed_reorderings``); steps with the same cog pattern in one permutable set are interchangeable, and the
k-th time the worker does that pattern, the k-th step of the set is done.

``track`` walks the cog sequence of the current task once and says, for every step: done or not, when, and on which
site; whether a step was started before the things it needs were done (a violation); and which step is in progress.
Pure functions: no clock, no I/O, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..core import Cog


@dataclass(frozen=True)
class Step:
    id: str
    label: str
    cogs: tuple[str, ...]
    required: bool = True
    critical: bool = False
    after: tuple[str, ...] = ()
    skill: str | None = None
    median_s: float | None = None
    coach: dict = field(default_factory=dict)


@dataclass
class Occurrence:
    step: str
    start: int            # index of the first cog of this occurrence
    end: int              # index of the last cog matched so far
    t0: float
    t1: float
    complete: bool
    site: str | None = None


@dataclass
class Violation:
    step: str             # the step that was started too early
    at_cog: int
    t: float
    missing: tuple[str, ...]   # prerequisites not done when it started, policy order


@dataclass
class Progress:
    occurrences: dict[str, Occurrence] = field(default_factory=dict)
    done: set[str] = field(default_factory=set)
    violations: list[Violation] = field(default_factory=list)
    current: str | None = None            # a started step that is not finished, else the most recently started one
    n_cogs: int = 0

    def unresolved(self) -> list[Violation]:
        """Violations whose missing prerequisites are still not done."""
        out = []
        for v in self.violations:
            still = tuple(m for m in v.missing if m not in self.done)
            if still:
                out.append(Violation(v.step, v.at_cog, v.t, still))
        return out


class StepPolicy:
    def __init__(self, steps: Sequence[Step], permutable: Sequence[Sequence[str]] = (), task: str = "", coverage: str = "full"):
        self.steps = {s.id: s for s in steps}
        self.order = [s.id for s in steps]
        self._permutable = [list(g) for g in permutable]
        self.task = task
        self.coverage = coverage
        # groups of interchangeable steps: same cog pattern and listed together in a permutable set
        self.groups: dict[tuple[str, ...], list[str]] = {}
        in_perm = {sid for grp in permutable for sid in grp}
        for s in steps:
            key = s.cogs
            if s.id in in_perm:
                self.groups.setdefault(key, []).append(s.id)
            else:
                self.groups.setdefault(key + ("#" + s.id,), []).append(s.id)   # unique key: a lone step
        self.patterns = {key: [self.steps[i] for i in ids] for key, ids in self.groups.items()}

    @classmethod
    def from_doc(cls, doc: dict) -> "StepPolicy":
        steps = [
            Step(id=c["id"], label=c.get("label", c["id"]), cogs=tuple(c["cogs"]), required=bool(c.get("required", True)),
                 critical=bool(c.get("critical", False)), after=tuple(c.get("after") or ()), skill=c.get("skill"),
                 median_s=c.get("expert_median_s"), coach=dict(c.get("coach") or {}))
            for c in doc.get("checks", [])
        ]
        permutable = [r.get("permutable", []) for r in doc.get("allowed_reorderings", []) or []]
        return cls(steps, permutable, task=str(doc.get("task", "")), coverage=str(doc.get("coverage", "full")))

    @classmethod
    def from_pack(cls, pack) -> "StepPolicy":
        return cls.from_doc(pack.nested("expert_policy", "steps"))

    def without(self, step_ids: Sequence[str]) -> "StepPolicy":
        """The same policy for a task that leaves some steps out (the study case uses two calculators, not three):
        the steps are dropped and nothing waits for them any more."""
        drop = set(step_ids) & set(self.steps)
        if not drop:
            return self
        from dataclasses import replace

        kept = [replace(s, after=tuple(a for a in s.after if a not in drop)) for s in self.steps.values() if s.id not in drop]
        perm = [[i for i in g if i not in drop] for g in self._permutable]
        return StepPolicy(kept, [g for g in perm if g], task=self.task, coverage=self.coverage)

    # ------------------------------------------------------------------ tracking
    def track(self, cogs: Sequence[Cog], sites: Sequence[str | None] | None = None) -> Progress:
        sites = sites or [None] * len(cogs)
        prog = Progress(n_cogs=len(cogs))
        # 1. occurrences of each pattern, in order of completion
        per_pattern: dict[tuple, list[Occurrence]] = {}
        for key, steps in self.patterns.items():
            pat = steps[0].cogs
            occs: list[Occurrence] = []
            pos, start = 0, -1
            for i, c in enumerate(cogs):
                if c.id == pat[pos]:
                    if pos == 0:
                        start = i
                    pos += 1
                    if pos == len(pat):
                        occs.append(Occurrence("", start, i, cogs[start].t0, cogs[i].t1, True, sites[start]))
                        pos = 0
                elif pos > 0 and c.id == pat[0]:       # the worker started again: abandon the half-done attempt
                    start, pos = i, 1
                    if pos == len(pat):
                        occs.append(Occurrence("", start, i, c.t0, c.t1, True, sites[start]))
                        pos = 0
            if pos > 0:
                occs.append(Occurrence("", start, len(cogs) - 1, cogs[start].t0, cogs[-1].t1, False, sites[start]))
            per_pattern[key] = occs
        # 2. the k-th occurrence completes the k-th interchangeable step; extras (repeats) are ignored
        for key, occs in per_pattern.items():
            for step, occ in zip(self.patterns[key], occs):
                occ.step = step.id
                prog.occurrences[step.id] = occ
                if occ.complete:
                    prog.done.add(step.id)
        # 3. a step started before what it needs was done is a violation
        started = sorted(prog.occurrences.values(), key=lambda o: o.start)
        for occ in started:
            step = self.steps[occ.step]
            missing = []
            for pre in step.after:
                po = prog.occurrences.get(pre)
                if po is None or not po.complete or po.end >= occ.start:
                    missing.append(pre)
            if missing:
                # everything still undone that this step rests on, directly or through another step
                stack, seen = list(missing), set(missing)
                while stack:
                    for pre in self.steps[stack.pop()].after:
                        po = prog.occurrences.get(pre)
                        if pre not in seen and (po is None or not po.complete or po.end >= occ.start):
                            seen.add(pre)
                            stack.append(pre)
                missing = sorted(seen, key=self.order.index)
                prog.violations.append(Violation(step.id, occ.start, occ.t0, tuple(missing)))
        # 4. the step in progress: a partial occurrence, else the most recently started one
        partial = [o for o in started if not o.complete]
        if partial:
            prog.current = partial[-1].step
        elif started:
            prog.current = started[-1].step
        return prog

    # ------------------------------------------------------------------ helpers for the coach
    def next_ready(self, prog: Progress) -> list[str]:
        """Steps not done whose prerequisites are all done, in policy order."""
        return [sid for sid in self.order if sid not in prog.done and all(a in prog.done for a in self.steps[sid].after)]

    def pattern_mates(self, step_id: str) -> list[str]:
        """Steps interchangeable with this one (same cogs, same permutable set): one prompt covers all of them."""
        for ids in self.groups.values():
            if step_id in ids:
                return list(ids)
        return [step_id]

    def pick_missed(self, missing: Sequence[str], prog: Progress, exclude: Sequence[str] = (), only_skill: str | None = None) -> str | None:
        """Which missing step to talk about: a critical one the worker can do right now (everything it needs is done).
        A prompt about something that cannot be done yet is noise. Steps in ``exclude`` (already prompted) are skipped.

        ``only_skill`` (study mode) restricts the choice to the steps of one skill and does not wait for the worker to
        have done the steps of other skills first: the coach for one skill is silent about every other."""
        for m in missing:
            if m in exclude:
                continue
            step = self.steps[m]
            if only_skill is not None:
                if step.skill == only_skill:
                    return m
                continue
            if step.critical and all(a in prog.done for a in step.after):
                return m
        return None

    def episode_outcomes(self, prog: Progress) -> dict[str, str]:
        """For skill tracing: ``{step_id: 'clean' | 'error'}`` for the required steps of a finished episode. A step that
        is not done, or was done only after something that needed it had already started, is an error."""
        late = {m for v in prog.violations for m in v.missing}
        out: dict[str, str] = {}
        for sid in self.order:
            s = self.steps[sid]
            if not s.required:
                continue
            out[sid] = "error" if (sid not in prog.done or sid in late) else "clean"
        return out
