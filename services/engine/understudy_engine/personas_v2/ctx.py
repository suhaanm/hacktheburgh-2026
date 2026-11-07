"""The execution context of one case, and the behaviours (deficit blocks, stalls, interruptions) the families call.

``Ctx`` is shared by the three families: it holds the person, the clock, the plan being built, the interruption
process and the duration functions. What differs between families is *when* they call the behaviours and with what
count distribution; the content of a deficit block (which cogs, how long) is built here.
"""
from __future__ import annotations

import math
import random
from typing import Callable

from .core import CasePlan, Clock, Seg, Step, Stuck, draw_pause, expit, lognormal, lomax, poisson, practice_mult, severity
from .people import Person
from .roles import BENEFITS, RoleSpec

REWORK_AT = {BENEFITS: "RECONCILE"}        # other roles flush owed rework at the end of the task
PAUSE_SCALE_MAX = 3.0


class Ctx:
    def __init__(self, rnd: random.Random, role: RoleSpec, person: Person, h: dict, n_eff: float, clock: Clock, complexity: float,
                 dur_fn: Callable[["Ctx", str], float]):
        self.rnd, self.role, self.p, self.h = rnd, role, person, h
        self.n_eff, self.clock, self.complexity, self.dur_fn = n_eff, clock, complexity, dur_fn
        self.plan = CasePlan()
        self.resume_left = 0
        self.next_int = self._int_gap()
        self._sev_cache: dict[str, float] = {}
        self.allow_interrupt = True
        self.force_stuck: bool | None = None       # set by the latent_skill family while its hidden state is stuck

    # ------------------------------------------------------------------ person state
    def sev(self, skill: str) -> float:
        if skill not in self._sev_cache:
            self._sev_cache[skill] = severity(self.p, skill, self.n_eff, 1.0)
        return self._sev_cache[skill]

    def mean_sev(self) -> float:
        sk = list(self.p.theta_inf)
        return sum(self.sev(s) for s in sk) / max(1, len(sk))

    def base_mult(self) -> float:
        """Everything that scales a time: person speed, practice, warm-up, fatigue, time of day."""
        return math.exp(self.p.log_speed) * practice_mult(self.p, self.n_eff) * self.clock.mult(self.p, self.h)

    # ------------------------------------------------------------------ segments
    def add(self, cog: str, dur: float, **kw) -> Seg:
        seg = Seg(cog=cog, dur=max(0.3, dur), **kw)
        self.plan.segs.append(seg)
        self.clock.local_s += seg.dur
        return seg

    def resume_factor(self) -> float:
        if self.resume_left == 2:
            return self.h["resume_slow"]
        if self.resume_left == 1:
            return 0.93                   # people speed up after an interruption (Mark, Gudith & Klocke 2008) ...
        return 1.0

    def work(self, st: Step | str, *, scale: float = 1.0, tag: str | None = None, kind: str = "work", site: str | None = None,
             query_len: int | None = None) -> Seg:
        cog = st.cog if isinstance(st, Step) else st
        site = site if site is not None else (st.site if isinstance(st, Step) else None)
        unit = st.unit if isinstance(st, Step) else ""
        d = self.dur_fn(self, cog) * scale * self.resume_factor()
        seg = self.add(cog, d, site=site, tag=tag, kind=kind, unit=unit, query_len=query_len)
        if cog in ("SEARCH", "REFORMULATE") and query_len is None:
            seg.query_len = self.rnd.randint(8, 40)
        if self.resume_left > 0:
            self.resume_left -= 1
        return seg

    def pause(self, dur: float | None = None, tag: str | None = None) -> Seg:
        d = draw_pause(self.rnd, self.h) if dur is None else dur
        return self.add("IDLE", min(600.0, d), kind="pause", tag=tag)

    # ------------------------------------------------------------------ the shared interruption process
    def _int_gap(self) -> float:
        rate = max(1e-6, self.p.interrupt_per_h) / 3600.0
        return self.rnd.expovariate(rate)

    def maybe_interrupt(self) -> None:
        """Poisson interruptions in task time. Ordinary and long ones; a resumption slowdown follows."""
        if not self.allow_interrupt or self.clock.local_s < self.next_int:
            return
        h, rnd = self.h, self.rnd
        if rnd.random() < h["int_long_share"]:
            d = lognormal(rnd, h["int_long_median_s"], 0.8)
        else:
            d = lognormal(rnd, h["int_len_median_s"], h["int_len_sigma"])
        d = min(d, 3000.0)
        seg = self.add("_AWAY", d, kind="interrupt")
        seg.traced = rnd.random() < 0.5
        self.plan.interrupts.append({"idx": len(self.plan.segs) - 1, "dur": round(d, 2)})
        self.resume_left = 2
        self.next_int = self.clock.local_s + self._int_gap()
        if rnd.random() < h["resume_reread_p"]:
            prev = next((s.cog for s in reversed(self.plan.segs[:-1]) if s.kind in ("work", "detour") and self.role.act_class.get(s.cog) == "read"), None)
            self.work(prev or ("READ" if "READ" in self.role.cogs else self.role.cogs[0]), scale=0.5, kind="detour")

    # ------------------------------------------------------------------ hidden stuck episodes
    def close_episode(self, i0: int, tag: str | None = None, *, force: bool | None = None) -> bool:
        """Decide whether segments ``i0:`` form a hidden stuck episode, and how much it suppresses progress."""
        segs = self.plan.segs[i0:]
        if not segs:
            return False
        h, rnd = self.h, self.rnd
        if force is None:
            force = self.force_stuck
        stuck = (rnd.random() > h["benign_detour_share"]) if force is None else force
        if not stuck:
            return False
        supp = 0.0 if rnd.random() < h["stuck_suppress_full_p"] else h["stuck_suppress_partial"]
        sid = len(self.plan.stuck) + 1
        for s in segs:
            s.stuck_id = sid
        silent = all(s.kind == "pause" for s in segs)
        self.plan.stuck.append(Stuck(sid, i0, len(self.plan.segs), supp, silent, tag, sum(s.dur for s in segs)))
        return True

    def detour_seconds(self, total_s: float, tag: str | None = None, *, silent_ok: bool = True) -> int:
        """Fill about ``total_s`` seconds with detour cogs (or, for a quiet stall, one pause). Returns the first segment index."""
        i0 = len(self.plan.segs)
        if silent_ok and self.rnd.random() < self.h["silent_stuck_share"]:
            self.pause(total_s, tag=tag)
            return i0
        remaining = total_s
        pool = self.role.detour_cogs
        guard = 0
        while remaining > 2.0 and guard < 40:
            guard += 1
            cog = pool[self.rnd.randrange(len(pool))]
            d = min(remaining, max(2.0, self.dur_fn(self, cog) * 0.7))
            seg = self.add(cog, d, kind="detour", tag=tag)
            if cog in ("SEARCH", "REFORMULATE"):
                seg.query_len = self.rnd.randint(8, 40)
            remaining -= d
        return i0

    # ------------------------------------------------------------------ deficit blocks (content shared by every family)
    def omit(self, spec, st: Step, tag: str | None = None) -> None:
        """The step is skipped. Its would-be duration is drawn anyway: it is the seconds saved."""
        ghost = self.dur_fn(self, st.cog) * self.resume_factor()
        self.plan.note(spec.id, saved=ghost, instances=1)
        self.plan.skipped += 1
        self.plan.pending[spec.id] = self.plan.pending.get(spec.id, 0) + 1

    def flush_rework(self, found_p: float, only: str | None = None) -> None:
        """Skipped checks found later: the rework tail (revert, redo, re-check, re-read), priced as added seconds."""
        for did in list(self.plan.pending):
            if only is not None and did != only:
                continue
            k = self.plan.pending.pop(did)
            spec = self.role.deficit(did)
            if k <= 0 or self.rnd.random() >= found_p:
                continue
            i0 = len(self.plan.segs)
            t0 = self.clock.local_s
            for cog in spec.rework:
                reps = k if cog == spec.cog else 1
                for _ in range(reps):
                    self.work(cog, scale=0.7 if cog == "ENTER_HOUSEHOLD" else 1.0, tag=did, kind="detour")
            self.plan.note(did, added=self.clock.local_s - t0)

    def repeat_block(self, spec, cog: str, n: int, stuck_ok: bool = True) -> None:
        if n <= 0:
            return
        i0 = len(self.plan.segs)
        t0 = self.clock.local_s
        for _ in range(n):
            self.work(cog, scale=0.6, tag=spec.id, kind="detour")
        self.plan.note(spec.id, added=self.clock.local_s - t0, instances=1)
        if n >= 2 and stuck_ok:
            self.close_episode(i0, spec.id)

    def loop_block(self, spec, rounds: int, silent_ok: bool = True) -> None:
        """Search, read the hits, reformulate, read again: ``rounds`` rounds (or one quiet stall of the same expected length)."""
        if rounds <= 0:
            return
        i0 = len(self.plan.segs)
        t0 = self.clock.local_s
        if silent_ok and self.rnd.random() < self.h["silent_stuck_share"]:
            self.pause(sum(self.dur_fn(self, "SEARCH") + 0.6 * self.dur_fn(self, "READ" if "READ" in self.role.cogs else "NAVIGATE") for _ in range(rounds)), tag=spec.id)
        else:
            read = "READ" if "READ" in self.role.cogs else self.role.detour_cogs[0]
            for r in range(rounds):
                self.work("SEARCH" if r == 0 else "REFORMULATE", tag=spec.id, kind="detour")
                self.work(read, scale=0.6, tag=spec.id, kind="detour")
        self.plan.note(spec.id, added=self.clock.local_s - t0, instances=1)
        self.close_episode(i0, spec.id)

    def freeze_block(self, spec, dur: float | None = None) -> None:
        """A long hesitation before a step (heavy-tailed)."""
        h = self.h
        d = (h["idle_lomax_scale_s"] + lomax(self.rnd, h["idle_lomax_alpha"], h["idle_lomax_scale_s"])) if dur is None else dur
        i0 = len(self.plan.segs)
        seg = self.pause(min(d, 600.0), tag=spec.id)
        self.plan.note(spec.id, added=seg.dur, instances=1)
        self.close_episode(i0, spec.id)

    def copy_block(self, spec, found_p: float) -> None:
        """The wrong figure was copied. Found at a second reconcile with probability ``found_p``: then revert and copy again."""
        self.plan.note(spec.id, instances=1)
        if self.rnd.random() >= found_p:
            return
        t0 = self.clock.local_s
        for cog in spec.rework:
            self.work(cog, scale=0.8 if cog == "RECONCILE" else 1.0, tag=spec.id, kind="detour")
        self.plan.note(spec.id, added=self.clock.local_s - t0)

    # ------------------------------------------------------------------ generic slip
    def maybe_slip(self, st: Step, last: Seg) -> None:
        """A slip on a productive step: undo and redo it. Not a deficit (the same for everyone, scaled by the person's slip rate)."""
        p = self.p.p_slip * (self.h["resume_error_mult"] if self.resume_left > 0 else 1.0)
        if self.role.act_class.get(st.cog) != "commit" or self.rnd.random() >= p:
            return
        self.work("REVERT", kind="detour")
        self.work(st.cog, scale=0.6, kind="detour", site=st.site)

    def hesitate(self, scale: float = 1.0) -> None:
        """A benign hesitation pause (heavy-tailed). Whether it is a stuck episode is the family's business."""
        self.pause(draw_pause(self.rnd, self.h) * scale)


def total_added(plan: CasePlan, d: str) -> float:
    b = plan.deficits.get(d)
    return 0.0 if not b else b["added_s"] - b["saved_s"]
