"""``generate_cohort``: many people, a few cases each, in the shapes v1 produces (events and a truth file like the apprentices').

    cohort = generate_cohort("process_trace", "benefits-processor", n_people=40, cases_per_person=8, seed=7)
    cohort.rows         schema-valid event dicts, sorted by time, origin "synthetic"
    cohort.truth        the v1 apprentices truth.json shape (people, traces[].deficits[], deficit_types, expert_reference,
                        stuck_episodes) plus a "realism" block
    cohort.levels       person -> "expert" | "novice" (a noisy function of tenure)
    cohort.events()     validated ``core.Event`` objects
    cohort.episodes()   episodes through the role pack's cog mapping (what the analytics see)
    cohort.planted_spells()   hidden stuck episodes by person as (t0, t1) unix seconds, for ``hazard`` validation
    cohort.genome_cohort(max_cases_per_person=None)   a ``genome.Cohort``
    cohort.write(root, slug)  events.jsonl and truth.json like the v1 generators

Everything is a pure function of the arguments: the same call gives byte-identical rows.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..core import Episode, Event
from .core import Clock, choose, lognormal, poisson, seeded
from .ctx import Ctx
from .emit import Emitter, emit_case, finalize, iso
from .families import FAMILY_ORDER, get_family
from .params import draw_hyper, params_sha256
from .people import Person, draw_people
from .roles import BENEFITS, RoleSpec, get_role

START = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)      # a Monday
LABEL = "generated, realism-calibrated"
NO_NOISE = {"drop_p": 0.0, "drop_burst_p": 0.0, "jitter_sd_s": 0.0, "double_p": 0.0, "zone_err_p": 0.0, "label_missing_p": 0.0,
            "coarse_ts_p": 0.0, "task_end_missing_p": 0.0, "os_skew_s": 0.0}


def expert_median_s(role: RoleSpec, complexity: float, strategy: dict | None = None) -> float:
    st = strategy or {d: o[0] for d, o in role.strategy_dims.items()}
    steps = role.nominal(st, seeded(0))
    return sum(role.dwell.get(s.cog, (10.0, 0))[0] * (complexity if s.cog == role.complexity_cog else 1.0) for s in steps)


def reference_sequences(role: RoleSpec) -> dict[str, list[str]]:
    rnd = seeded(0)
    dims = role.strategy_dims
    a = {d: o[0] for d, o in dims.items()}
    b = dict(a)
    if "cliff_mode" in b:
        b["cliff_mode"] = "batched"
    return {"sequence_A": [s.cog for s in role.nominal(a, rnd)], "sequence_B": [s.cog for s in role.nominal(b, rnd)]}


def rows_to_events(rows: list[dict]) -> list[Event]:
    """Build ``core.Event`` objects without per-row validation (the rows are valid by construction and tested against the schema)."""
    from ..core import Target

    out = []
    for r in rows:
        tg = r.get("target")
        out.append(Event.model_construct(
            schema_version=1, id=r["id"], t=datetime.fromisoformat(r["t"].replace("Z", "+00:00")), origin=r["origin"], actor=r["actor"],
            person=r["person"], role=r["role"], source=r["source"], type=r["type"], target=Target.model_construct(**tg) if tg else None,
            task_id=r.get("task_id"), meta=r.get("meta") or {},
        ))
    return out


@dataclass
class V2Cohort:
    family: str
    role: str
    seed: int
    n_people: int
    cases_per_person: int
    hyper: dict
    people: list[Person]
    rows: list[dict]
    truth: dict
    levels: dict[str, str]
    _cache: dict = field(default_factory=dict, repr=False)

    def events(self) -> list[Event]:
        if "events" not in self._cache:
            self._cache["events"] = rows_to_events(self.rows)
        return self._cache["events"]

    def episodes(self, mapping=None) -> list[Episode]:
        from ..cogs import segment_episodes
        from ..routines.sources import pack_mapping

        key = ("episodes", id(mapping))
        if key not in self._cache:
            self._cache[key] = segment_episodes(self.events(), mapping if mapping is not None else pack_mapping(self.role))
        return self._cache[key]

    def planted_spells(self) -> dict[str, list[tuple[float, float]]]:
        out: dict[str, list[tuple[float, float]]] = {}
        for s in self.truth["stuck_episodes"]:
            out.setdefault(s["person"], []).append((_ts(s["t0"]), _ts(s["t1"])))
        return out

    def genome_cohort(self, max_cases_per_person: int | None = None):
        from ..genome import Cohort

        eps = self.episodes()
        if max_cases_per_person is not None:
            case_of = {t["task_id"]: t["case"] for t in self.truth["traces"]}
            eps = [e for e in eps if case_of.get(e.task_id, 10 ** 9) <= max_cases_per_person]
        return Cohort(eps, dict(self.levels))

    def write(self, root: Path | str, slug: str | None = None) -> Path:
        from ..store.jsonl import EventStore

        out = Path(root) / "synthetic" / (slug or f"v2-{self.family}-{self.role}-{self.seed}")
        EventStore(Path(root)).write_file(out / "events.jsonl", self.rows)
        (out / "truth.json").write_text(json.dumps(self.truth, indent=1, sort_keys=True))
        return out


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _strategy_label(st: dict) -> str:
    return "-".join(f"{k[:3]}{v}" for k, v in sorted(st.items()))[:40].lower().replace("_", "")


def generate_cohort(family: str, role: str, n_people: int = 40, cases_per_person: int = 8, seed: int = 0, *,
                    hyper_overrides: dict[str, float] | None = None, noise: bool = True, start: datetime | None = None) -> V2Cohort:
    fam = get_family(family)
    rs = get_role(role)
    over = dict(hyper_overrides or {})
    if not noise:
        over = {**NO_NOISE, **over}
    h = draw_hyper(np.random.default_rng([seed, FAMILY_ORDER.index(family)]), over)
    rnd = seeded(seed, FAMILY_ORDER.index(family), 1)
    people = draw_people(h, rs, n_people, fam.code, seed, rnd)
    for p in people:
        fam.prepare_person(p, rs, h, seeded(seed, FAMILY_ORDER.index(family), 2, p.idx))
    t_start = (start or START).timestamp()

    all_rows: list[dict] = []
    traces: list[dict] = []
    stuck_eps: list[dict] = []
    people_truth: list[dict] = []
    for p in people:
        prnd = seeded(seed, FAMILY_ORDER.index(family), 3, p.idx)
        em = Emitter(p, rs, h, seeded(seed, FAMILY_ORDER.index(family), 4, p.idx), f"{p.id[2:]}")
        case_no, day, done_eff = 0, int(prnd.random() * 3), 0.0
        while case_no < cases_per_person:
            while day % 7 >= 5:
                day += 1
            n_sess = max(1, min(cases_per_person - case_no, 1 + poisson(prnd, h["cases_per_session_mean"] - 1.0)))
            hour = min(20.0, max(6.0, prnd.gauss(h["start_hour_mean"], h["start_hour_sd"])))
            t_cursor = t_start + day * 86400.0 + hour * 3600.0
            work_s, since = 0.0, 0.0
            for _ in range(n_sess):
                case_no += 1
                complexity = choose(prnd, (1.0, 1.2, 1.45), (0.5, 0.25, 0.25))
                clock = Clock(hour=(t_cursor - t_start) % 86400.0 / 3600.0, work_s=work_s, since_start_s=since)
                ctx = Ctx(prnd, rs, p, h, p.tenure + done_eff, clock, complexity, fam.dur_fn)
                fam.case(ctx)
                plan = ctx.plan
                tid = f"t_{p.id[2:]}c{case_no:02d}"
                t_end, spans = emit_case(em, plan, t_cursor, tid)
                dur = t_end - t_cursor
                ded = []
                for did, b in plan.deficits.items():
                    if b["instances"] > 0:
                        price = b["added_s"] - b["saved_s"]
                        ded.append({"type": did, "instances": b["instances"], "added_s": round(b["added_s"], 2), "saved_s": round(b["saved_s"], 2),
                                    "price_s": round(price, 2), "material": bool(price >= h["material_s"])})
                traces.append({
                    "task_id": tid, "person": p.id, "level": p.level, "case": case_no, "complexity": complexity,
                    "order_variant": _strategy_label(plan.strategy) or "free", "strategy": plan.strategy,
                    "t0": iso(t_cursor), "t1": iso(t_end), "duration_s": round(dur, 2),
                    "expert_median_s": round(expert_median_s(rs, complexity), 2),
                    "deficits": ded, "price_total_s": round(sum(d["price_s"] for d in ded), 2),
                    "severity": {d.skill: round(ctx.sev(d.skill), 4) for d in rs.deficits},
                    "n_eff": round(p.tenure + done_eff, 2), "interruptions": len(plan.interrupts),
                    "cogs": [[s.cog, round(s.dur, 2), s.tag] for s in plan.segs if s.kind != "interrupt"],
                })
                for s in plan.stuck:
                    stuck_eps.append({
                        "task_id": tid, "person": p.id, "t0": iso(spans[s.i0][0]), "t1": iso(spans[s.i1 - 1][1]),
                        "duration_s": round(s.seconds, 2), "deficit": s.tag, "labelled": s.reported, "suppression": round(s.supp, 3),
                        "silent": s.silent,
                    })
                gap = lognormal(prnd, h["between_case_gap_median_s"], 0.8)
                since += dur + gap
                work_s = work_s + dur if gap < 1200 else (work_s + dur) * 0.5
                t_cursor = t_end + gap
                done_eff += 1.0
            gap_days = max(1, int(round(prnd.expovariate(1.0 / h["session_gap_days_mean"]) + 0.5)))
            day += gap_days
            done_eff *= math.exp(-gap_days / h["forget_tau_days"])
        people_truth.append({
            "person": p.id, "level": p.level, "order_variant": "free", "speed_factor": round(math.exp(p.log_speed), 3), "tenure_cases": round(p.tenure, 1),
            "g": round(p.g, 3), "learn_form": p.learn_form, "learn_alpha": round(p.learn_alpha, 3),
            "theta_inf": {k: round(v, 3) for k, v in p.theta_inf.items()}, "p_slip": round(p.p_slip, 4), "p_pause": round(p.p_pause, 4),
            "interrupt_per_h": round(p.interrupt_per_h, 3), "k_s": round(p.k_s, 3),
        })
        all_rows.extend(em.rows)

    rows = finalize(all_rows)
    totals = {}
    for d in rs.deficits:
        present = [x for t in traces for x in t["deficits"] if x["type"] == d.id]
        totals[d.id] = {"traces_with": len(present), "material": sum(1 for x in present if x["material"]),
                        "mean_price_s_when_present": round(sum(x["price_s"] for x in present) / max(1, len(present)), 2),
                        "total_price_s": round(sum(x["price_s"] for x in present), 2)}
    from .cited import status_counts

    truth = {
        "schema": 1, "kind": "cohort_v2", "origin": "synthetic", "realism": {
            "label": LABEL, "family": family, "params_sha256": params_sha256(), "hyper": {k: round(v, 5) for k, v in h.items()},
            "cited_status_counts": status_counts(),
            "note": "Generated. Marginals sit inside published ranges where a constant was found; this is not real data.",
        },
        "task": "benefits-household-entry" if rs.id == BENEFITS else rs.units[0].id, "role": rs.id, "seed": seed, "family": family,
        "description": f"{n_people} people x {cases_per_person} cases from the {family} generator ({LABEL}). price_s = seconds added minus seconds saved by the deficit's own segments (exact by construction).",
        "n_experts": sum(1 for p in people if p.level == "expert"), "n_novices": sum(1 for p in people if p.level == "novice"),
        "cases_per_person": cases_per_person, "deficit_types": rs.deficit_types, "people": people_truth, "traces": traces,
        "stuck_episodes": stuck_eps, "deficit_totals": totals,
        "expert_reference": {**reference_sequences(rs),
                             "median_s_by_complexity": {str(c): round(expert_median_s(rs, c), 2) for c in (1.0, 1.2, 1.45)},
                             "note": "Canonical sequences only: v2 experts take many valid paths."},
        "counts": {"events": len(rows), "traces": len(traces), "stuck_episodes": len(stuck_eps)},
    }
    return V2Cohort(family, rs.id, seed, n_people, cases_per_person, h, people, rows, truth, {p.id: p.level for p in people})


__all__ = ["V2Cohort", "generate_cohort", "FAMILY_ORDER", "expert_median_s"]
