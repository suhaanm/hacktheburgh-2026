"""The three generator families. They share the person hierarchy, the interruption process, the deficit-block content
and the event emitter; they differ in how sequences, durations and deficit occurrences are produced.

``markov``        a plan-guided variable-order Markov process. The task is a walk over the pack's partial order (a random
                  linear extension steered by the person's unit preferences); between steps, detour chains follow
                  person-specific transition rows and are self-exciting; deficit behaviours are context-conditional
                  tendencies that cluster (geometric counts). Durations are top-down lognormals.
``latent_skill``  a hidden flow, hesitate, stuck process driven by the person's per-skill mastery (which learns).
                  A deficit occurs when the hidden state is stuck at a step that needs the skill, and its size is the
                  heavy-tailed length of the stuck episode. Durations are top-down lognormals scaled by the state.
``process_trace`` task-grammar sampling: an explicit Dirichlet mixture over valid methods per person, durations
                  built bottom-up from KLM operators (keystrokes, Fitts pointing, homing, mental units, Hick-Hyman
                  choice, system response), retries when a step fails, deficits as independent grammar mistakes.
"""
from __future__ import annotations

import math
import random

from .core import Step, choose, dirichlet, expit, logit, lognormal, lomax, poisson
from .ctx import REWORK_AT, Ctx
from .people import Person
from .roles import BENEFITS, RoleSpec


# ------------------------------------------------------------------------------------------ duration functions
def dur_td(ctx: Ctx, cog: str) -> float:
    """Top-down: a lognormal around the role's expert median, scaled by everything that scales time."""
    med, sig = ctx.role.dwell.get(cog, (10.0, 0.4))
    sigma = sig * (ctx.h["sd_within"] / 0.4) * ctx.p.within_mult
    cm = ctx.complexity if cog == ctx.role.complexity_cog else 1.0
    return max(1.0, lognormal(ctx.rnd, med * cm * ctx.base_mult() * getattr(ctx, "state_mult", 1.0), sigma))


def dur_klm(ctx: Ctx, cog: str) -> float:
    """Bottom-up: a sum of keystroke-level operators with a Fitts pointing term and a Hick-Hyman choice term."""
    spec = ctx.role.klm.get(cog) or {"M": 3}
    r, h, p = ctx.rnd, ctx.h, ctx.p
    cm = ctx.complexity if cog == ctx.role.complexity_cog else 1.0
    t = 0.0
    nM = poisson(r, spec.get("M", 0.0))
    t += nM * h["pt_mental_s"] * math.exp(0.5 * p.log_speed)
    nP = poisson(r, spec.get("P", 0.0) * cm)
    if nP:
        a, b = h["pt_pointing_a_s"], h["pt_pointing_b_s"]
        for _ in range(min(nP, 12)):
            t += a + b * math.log2(r.uniform(2.0, 12.0) + 1.0)
        if nP > 12:
            t += (nP - 12) * (a + b * 2.7)
    t += poisson(r, spec.get("K", 0.0) * cm) * p.k_s
    t += spec.get("H", 0.0) * h["pt_homing_s"]
    if spec.get("choices"):
        t += h["pt_hick_b_s"] * math.log2(spec["choices"])
    if spec.get("R"):
        t += lognormal(r, spec["R"], 0.5)
    t *= math.exp(0.12 * r.gauss(0.0, 1.0)) * (ctx.base_mult() / math.exp(p.log_speed))
    return max(1.0, t)


def _applies(spec, st: Step) -> bool:
    if spec.kind == "omit" and spec.cog == "READ_TRACE":
        return st.unit == "read_trace_first"
    return st.cog == spec.cog


def _read_cog(role: RoleSpec) -> str:
    return "READ" if "READ" in role.cogs else role.detour_cogs[0]


class Family:
    name = "base"
    code = "xx"
    dur_fn = staticmethod(dur_td)

    def prepare_person(self, person: Person, role: RoleSpec, h: dict, rnd: random.Random) -> None:
        pass

    # the role's main task (the household entry for benefits)
    def case_steps(self, ctx: Ctx) -> list[Step]:
        raise NotImplementedError

    def run_steps(self, ctx: Ctx, steps: list[Step], *, deficits: bool = True) -> None:
        raise NotImplementedError

    def adhoc_steps(self, ctx: Ctx, n: int) -> list[Step]:
        raise NotImplementedError

    def case(self, ctx: Ctx) -> None:
        self.run_steps(ctx, self.case_steps(ctx), deficits=True)

    def finish(self, ctx: Ctx) -> None:
        ctx.flush_rework(ctx.h["rework_found_p"])


# ------------------------------------------------------------------------------------------ process_trace
class ProcessTrace(Family):
    name, code = "process_trace", "pt"
    dur_fn = staticmethod(dur_klm)

    def case_steps(self, ctx: Ctx) -> list[Step]:
        st = {}
        for dim, opts in ctx.role.strategy_dims.items():
            st[dim] = choose(ctx.rnd, opts, ctx.p.strategy[dim])
        ctx.plan.strategy = st
        return ctx.role.nominal(st, ctx.rnd)

    def adhoc_steps(self, ctx: Ctx, n: int) -> list[Step]:
        out: list[Step] = []
        units = list(ctx.role.units)
        while len(out) < n:
            u = units[ctx.rnd.randrange(len(units))]
            out.extend(Step(s.cog, s.site, u.id) for s in u.steps)
        return out[: max(n, 3)]

    def run_steps(self, ctx: Ctx, steps: list[Step], *, deficits: bool = True) -> None:
        r, h, p, role = ctx.rnd, ctx.h, ctx.p, ctx.role
        first_enter = True
        for st in steps:
            ctx.maybe_interrupt()
            if r.random() < p.p_pause * (1.0 + 0.25 * math.log2(1 + (role.klm.get(st.cog, {}).get("choices", 1) or 1))):
                i0 = len(ctx.plan.segs)
                ctx.hesitate()
                if ctx.plan.segs[-1].dur >= 30.0:
                    ctx.close_episode(i0)
            specs = role.deficit_for_cog(st.cog) if deficits else []
            omitted = False
            for spec in specs:
                if not _applies(spec, st):
                    continue
                sev, base = ctx.sev(spec.skill), h[spec.param]
                if spec.kind == "omit":
                    if r.random() < min(0.97, base * sev):
                        ctx.omit(spec, st)
                        omitted = True
                elif spec.kind == "freeze":
                    if r.random() < min(0.95, base * sev * (1.0 if first_enter else 0.5)):
                        ctx.freeze_block(spec)
                elif spec.kind == "loop":
                    if r.random() < min(0.9, 0.5 * sev):
                        ctx.loop_block(spec, 1 + poisson(r, base * sev))
            if st.cog == "ENTER_HOUSEHOLD":
                first_enter = False
            if omitted:
                continue
            seg = ctx.work(st)
            if role.act_class.get(st.cog) == "commit" and r.random() < h["pt_retry_p"]:      # a failed attempt: retry spell
                i0 = len(ctx.plan.segs) - 1
                ctx.work("REVERT", kind="detour")
                ctx.work(_read_cog(role), scale=0.6, kind="detour")
                ctx.work(st, scale=0.8, kind="detour")
                ctx.close_episode(i0)
            ctx.maybe_slip(st, seg)
            for spec in specs:
                if not _applies(spec, st):
                    continue
                sev, base = ctx.sev(spec.skill), h[spec.param]
                if spec.kind == "repeat":
                    ctx.repeat_block(spec, st.cog, poisson(r, base * sev))
                elif spec.kind == "copy" and r.random() < min(0.95, base * sev):
                    ctx.copy_block(spec, h["rework_found_p"])
            if st.cog == REWORK_AT.get(role.id):
                ctx.flush_rework(h["rework_found_p"])
        self.finish(ctx)


# ------------------------------------------------------------------------------------------ markov
class Markov(Family):
    name, code = "markov", "mk"

    def prepare_person(self, person: Person, role: RoleSpec, h: dict, rnd: random.Random) -> None:
        pool = list(role.detour_cogs)
        rows: dict[str, list[float]] = {}
        for ctx_cog in list(role.cogs) + ["_start"]:
            base = [1.0 + (2.0 if c == ctx_cog else 0.0) + (1.0 if c in ("SEARCH", "SEARCH_DOCS") else 0.0) for c in pool]
            tot = sum(base)
            rows[ctx_cog] = dirichlet(rnd, [max(1e-2, h["mk_dirichlet_conc"] * b / tot) for b in base])
        person.mk_rows = {"rows": rows, "pool": pool}
        w = {c: math.exp(0.7 * rnd.gauss(0.0, 1.0)) for c in role.pool}
        person.mk_rows["adhoc"] = {c: dirichlet(rnd, [w[d] * (3.0 if d == c else 1.0) for d in role.pool]) for c in role.pool}

    def case_steps(self, ctx: Ctx) -> list[Step]:
        prefs = {k: v * math.exp(0.3 * ctx.rnd.gauss(0.0, 1.0)) for k, v in ctx.p.unit_prefs.items()}
        ctx.plan.strategy = {"walk": "frontier"}
        return ctx.role.frontier_walk(ctx.rnd, prefs, p_optional=ctx.h["verify_reread_pop"])

    def adhoc_steps(self, ctx: Ctx, n: int) -> list[Step]:
        rows, pool = ctx.p.mk_rows["adhoc"], list(ctx.role.pool)
        cur = pool[ctx.rnd.randrange(len(pool))]
        out = [Step(cur)]
        while len(out) < n:
            cur = choose(ctx.rnd, pool, rows[cur])
            out.append(Step(cur, f"calc{ctx.rnd.randint(1, 3)}" if cur == "OPEN_CALCULATOR" else None))
        return out

    def _detour(self, ctx: Ctx, from_cog: str, burst: float) -> int:
        r, h = ctx.rnd, ctx.h
        rows, pool = ctx.p.mk_rows["rows"], ctx.p.mk_rows["pool"]
        i0 = len(ctx.plan.segs)
        cogs = [choose(r, pool, rows.get(from_cog, rows["_start"]))]
        cont = min(0.85, h["mk_selfexcite"] * (0.7 + 0.6 * ctx.mean_sev()) * burst)
        while r.random() < cont and len(cogs) < 8:
            cogs.append(choose(r, pool, rows.get(cogs[-1], rows["_start"])))
        if len(cogs) >= 2 and r.random() < h["silent_stuck_share"]:
            ctx.pause(sum(ctx.dur_fn(ctx, c) * 0.7 for c in cogs))
        else:
            for c in cogs:
                ctx.work(c, scale=0.7, kind="detour")
        if len(cogs) >= 2:
            ctx.close_episode(i0)
        return len(cogs)

    def run_steps(self, ctx: Ctx, steps: list[Step], *, deficits: bool = True) -> None:
        r, h, p, role = ctx.rnd, ctx.h, ctx.p, ctx.role
        tend: dict[str, float] = {d.id: 1.0 for d in role.deficits}
        burst = 1.0
        prev_cog = "_start"
        prev_step: Step | None = None
        first_enter = True
        i = 0
        crit = {u.id for u in role.units if u.critical}
        while i < len(steps):
            st = steps[i]
            ctx.maybe_interrupt()
            if i > 0 and r.random() < h["mk_skipahead_p"] and st.unit not in crit and role.act_class.get(st.cog) != "commit":
                ctx.plan.skipped += 1
                i += 1
                continue
            p_start = min(0.5, h["mk_detour_base"] * (1.0 + 2.0 * ctx.mean_sev()) * burst)
            if r.random() < p_start:
                n = self._detour(ctx, prev_cog, burst)
                burst = min(3.0, burst * (1.0 + 0.4 * (n >= 2)))
            else:
                burst = 1.0 + (burst - 1.0) * 0.5
            specs = role.deficit_for_cog(st.cog) if deficits else []
            omitted = False
            for spec in specs:
                if not _applies(spec, st):
                    continue
                sev, base = ctx.sev(spec.skill), h[spec.param]
                pe = min(0.97, base * sev * tend[spec.id]) if spec.kind in ("omit", "freeze", "copy") else 0.0
                if spec.kind == "omit":
                    hit = r.random() < pe
                    if hit:
                        ctx.omit(spec, st)
                        omitted = True
                elif spec.kind == "freeze":
                    hit = r.random() < min(0.95, pe * (1.0 if first_enter else 0.5))
                    if hit:
                        ctx.freeze_block(spec)
                elif spec.kind == "loop":
                    hit = r.random() < min(0.9, 0.5 * sev * tend[spec.id])
                    if hit:
                        rounds = 1
                        while r.random() < min(0.8, h["mk_selfexcite"] + 0.15) and rounds < 6:
                            rounds += 1
                        ctx.loop_block(spec, rounds)
                else:
                    hit = False
                if spec.kind in ("omit", "freeze", "loop"):
                    tend[spec.id] = tend[spec.id] * (1.0 + 2.0 * h["mk_selfexcite"]) if hit else 1.0 + (tend[spec.id] - 1.0) * 0.5
            if st.cog == "ENTER_HOUSEHOLD":
                first_enter = False
            if omitted:
                prev_cog, i = st.cog, i + 1
                continue
            seg = ctx.work(st)
            ctx.maybe_slip(st, seg)
            for spec in specs:
                if not _applies(spec, st):
                    continue
                sev, base = ctx.sev(spec.skill), h[spec.param]
                if spec.kind == "repeat":
                    m = base * sev * tend[spec.id]
                    q = m / (1.0 + m)
                    n = 0
                    while r.random() < q and n < 8:
                        n += 1
                    ctx.repeat_block(spec, st.cog, n)
                    tend[spec.id] = tend[spec.id] * (1.0 + 2.0 * h["mk_selfexcite"]) if n else 1.0 + (tend[spec.id] - 1.0) * 0.5
                elif spec.kind == "copy":
                    hit = r.random() < min(0.95, base * sev * tend[spec.id])
                    if hit:
                        ctx.copy_block(spec, h["rework_found_p"])
                    tend[spec.id] = tend[spec.id] * (1.0 + 2.0 * h["mk_selfexcite"]) if hit else 1.0 + (tend[spec.id] - 1.0) * 0.5
            if prev_step is not None and r.random() < h["mk_backtrack_p"]:
                ctx.work(prev_step, scale=0.6, kind="detour")
            if st.cog == REWORK_AT.get(role.id):
                ctx.flush_rework(h["rework_found_p"])
            prev_cog, prev_step = st.cog, st
            i += 1
        self.finish(ctx)


# ------------------------------------------------------------------------------------------ latent_skill
class LatentSkill(Family):
    name, code = "latent_skill", "ls"

    def prepare_person(self, person: Person, role: RoleSpec, h: dict, rnd: random.Random) -> None:
        prefs = {k: v for k, v in person.unit_prefs.items()}
        person.habit = role.frontier_walk(rnd, prefs, p_optional=h["verify_reread_pop"])

    def case_steps(self, ctx: Ctx) -> list[Step]:
        ctx.plan.strategy = {"habit": "own"}
        if ctx.rnd.random() < 0.2:
            return ctx.role.frontier_walk(ctx.rnd, {k: v * math.exp(0.4 * ctx.rnd.gauss(0.0, 1.0)) for k, v in ctx.p.unit_prefs.items()},
                                          p_optional=ctx.h["verify_reread_pop"])
        return list(ctx.p.habit)

    def adhoc_steps(self, ctx: Ctx, n: int) -> list[Step]:
        pool = list(ctx.role.pool)
        k = min(len(pool), 3 + ctx.rnd.randrange(2))
        ws = ctx.rnd.sample(pool, k)                         # a small working set the person cycles through
        out = []
        cur = ws[0]
        while len(out) < n:
            cur = cur if ctx.rnd.random() < 0.2 else ws[ctx.rnd.randrange(k)]
            out.append(Step(cur, f"calc{ctx.rnd.randint(1, 3)}" if cur == "OPEN_CALCULATOR" else None))
        return out

    def _stuck_len(self, ctx: Ctx, sev: float) -> float:
        h, r = ctx.h, ctx.rnd
        med = h["ls_stuck_median_s"] * (0.5 + sev)
        if r.random() < 0.3:
            d = med * (1.0 + lomax(r, h["ls_stuck_lomax_alpha"], 0.5))
        else:
            d = lognormal(r, med, 0.7)
        return min(900.0, max(8.0, d))

    def run_steps(self, ctx: Ctx, steps: list[Step], *, deficits: bool = True) -> None:
        r, h, p, role = ctx.rnd, ctx.h, ctx.p, ctx.role
        streak = 0
        first_enter = True
        shift = logit(p.p_pause) - logit(h["p_pause_med"])
        for st in steps:
            ctx.maybe_interrupt()
            specs = [s for s in (role.deficit_for_cog(st.cog) if deficits else []) if _applies(s, st)]
            if specs:
                spec = choose(r, specs, [ctx.sev(s.skill) + 0.05 for s in specs])
                sev = ctx.sev(spec.skill)
            else:
                spec, sev = None, ctx.mean_sev()
            th_eff = -logit(min(max(sev, 1e-4), 1 - 1e-4))            # the person's current log-odds mastery
            p_h = expit(h["ls_hesitate_a"] - h["ls_hesitate_b"] * (th_eff - 1.0) + shift + (0.8 if streak > 0 else 0.0))
            state = "flow"
            if r.random() < p_h:
                state = "hesitate"
                i0 = len(ctx.plan.segs)
                ctx.hesitate()
                if r.random() < h["ls_hes_to_stuck"] * (1.0 + (0.5 if streak > 0 else 0.0)):
                    state = "stuck"
                else:
                    ctx.close_episode(i0, force=False)
            omitted = False
            after: list = []
            if state == "stuck":
                d = self._stuck_len(ctx, sev)
                ctx.force_stuck = True
                if spec is None:
                    ctx.close_episode(ctx.detour_seconds(d, None, silent_ok=True), None)
                elif spec.kind == "omit":
                    ctx.omit(spec, st)
                    omitted = True
                    ctx.close_episode(ctx.detour_seconds(d * 0.5, None), None)
                elif spec.kind == "freeze":
                    ctx.freeze_block(spec, dur=d)
                elif spec.kind == "loop":
                    ctx.loop_block(spec, max(1, int(round(d / 20.0))))
                else:
                    after.append((spec, d))
                ctx.force_stuck = None
                streak = 2
            elif streak > 0:
                streak -= 1
            if st.cog == "ENTER_HOUSEHOLD":
                first_enter = False
            if omitted:
                continue
            ctx.state_mult = 1.3 if state == "stuck" else (0.92 if state == "flow" else 1.05)
            seg = ctx.work(st)
            ctx.state_mult = 1.0
            ctx.maybe_slip(st, seg)
            for spec2, d in after:
                ctx.force_stuck = True
                if spec2.kind == "repeat":
                    ctx.repeat_block(spec2, st.cog, min(10, max(2, int(round(d / max(4.0, 0.6 * ctx.dur_fn(ctx, st.cog)))))))
                elif spec2.kind == "copy":
                    ctx.copy_block(spec2, 1.0)
                    ctx.close_episode(ctx.detour_seconds(d * 0.5, spec2.id), spec2.id)
                ctx.force_stuck = None
            if st.cog == REWORK_AT.get(role.id):
                ctx.flush_rework(h["rework_found_p"])
        self.finish(ctx)


FAMILIES: dict[str, Family] = {"markov": Markov(), "latent_skill": LatentSkill(), "process_trace": ProcessTrace()}
FAMILY_ORDER = ("markov", "latent_skill", "process_trace")


def get_family(name: str) -> Family:
    if name not in FAMILIES:
        raise KeyError(f"unknown family {name!r}; known: {list(FAMILIES)}")
    return FAMILIES[name]
