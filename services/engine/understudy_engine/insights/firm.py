"""A deterministic SYNTHETIC firm for the insights layer (REQ-9, owner decision D43). Badge: ``synthetic firm``. Nobody here is a person.

``build_firm(seed)`` returns about 60 users across three role packs (benefits-processor, deep; data-analyst and programmer, thin) with
tenure bands, experts and juniors, units, ledger-shaped rows (assist, delegated and automation streams), routines, an approval queue and a
risk feed. Every number the dashboard shows is computed from these rows by the insights code; nothing is typed in.

The learner dynamics follow ``cue.simlearn`` (latent mastery per skill, practice gains, forgetting between occurrences, the probability of
finishing unaided ``GUESS + (1 - GUESS) * m``), and use its constants and presets when that module imports (try-import; v1 values are the
fallback). It is a light, unvalidated generator of the same dynamics at firm scale, with planted situations the simulator has no place for.

Planted situations (``Firm.truth`` lists them, for the EVALUATION only: no product code reads it):
* benefits unit A juniors improve; unit B plateaus (and needs more help than the rest of the role: ``unit_attention``);
* a real expert-junior gap concentrated in two habits (check-the-cliff, reconcile-before-noting); a bottleneck skill;
* a Simpson trap (data-analyst juniors: every skill improves while the task mix shifts to the harder skills, so the raw pooled share falls);
* programmer has fewer than 5 experts (no expert reference) and a 4-person team (below the privacy threshold for comparison);
* an approved routine that hands work over with measured shadow matches, and pending proposals;
* a user with no data, a stale user, a new joiner, a user back from a 3-week holiday, a user who changed role 3 weeks ago;
* a risk feed: one approval 3 days old, two injection pauses, one kill event, no false claims.

``scenario="null"`` builds the same people with no planted effect: experts and juniors identical, no trend, no gap, no absence, no automation,
no risk. The evaluation measures the false-insight rate on it.
"""
from __future__ import annotations

import calendar
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import vocab as V
from .params import DAY
from .stats import seed_from
from .types import FirmSnapshot, PersonRecord

NOW0 = float(calendar.timegm((2026, 11, 9, 9, 0, 0)))      # Monday 9 Nov 2026, 09:00 UTC (a fixed "now" for the demo)
SKILLS: dict[str, tuple[str, ...]] = {
    "benefits-processor": ("reads-error-first", "enter-household-once", "check-the-cliff", "reconcile-before-noting"),
    "data-analyst": ("profile-before-querying", "inspect-before-trusting", "compare-to-last-period", "reconcile-to-control"),
    "programmer": ("read-the-trace-first", "smallest-change", "confirm-the-fix", "inspect-the-inputs"),
}
LOST0: dict[str, tuple[float, ...]] = {          # seconds lost per occurrence at zero mastery, against the expert's median
    "benefits-processor": (8.0, 6.0, 90.0, 60.0),
    "data-analyst": (30.0, 70.0, 30.0, 60.0),
    "programmer": (28.0, 22.0, 40.0, 18.0),
}
M0 = {"benefits-processor": (0.55, 0.60, 0.12, 0.2), "data-analyst": (0.8, 0.7, 0.1, 0.1), "programmer": (0.3, 0.3, 0.2, 0.25)}
SKILL_LR = {"benefits-processor": (1.0, 1.0, 0.45, 0.8), "data-analyst": (1.0, 1.0, 1.0, 0.5), "programmer": (1.0, 1.0, 0.6, 1.0)}      # the hard skill is slow to learn, so it stays the bottleneck
ROUTINE = {"benefits-processor": "case-note-draft", "data-analyst": "weekly-extract", "programmer": "test-rerun-loop"}
M_EXPERT = 0.95
STABILITY_JUNIOR, STABILITY_EXPERT = 200.0, 400.0

try:                                              # the CUE-ENGINE's simulated learners: constants and presets when importable
    from ..cue.simlearn import GUESS
    from ..cue.simlearn import preset as _preset

    _P = _preset("improving")
    LR_SELF, LR_HELP = float(_P.lr_self), float(_P.lr_help)
    SIMLEARN = True
except Exception:  # pragma: no cover - the v1 fallback
    GUESS, LR_SELF, LR_HELP, SIMLEARN = 0.10, 0.06, 0.14, False

# (role, unit, experts, juniors, scenario). 14 + 11 + 5 + 18 + 4 + 8 = 60.
PLAN: tuple[tuple[str, str, int, int, str], ...] = (
    ("benefits-processor", "unit_a", 4, 10, "improve"),
    ("benefits-processor", "unit_b", 2, 9, "plateau"),
    ("benefits-processor", "unit_c", 1, 4, "improve"),
    ("data-analyst", "unit_d", 5, 13, "simpson"),
    ("programmer", "prog_infra", 2, 2, "improve"),
    ("programmer", "prog_web", 1, 7, "improve"),
)
JOIN_WEEKS = (0, 0, 1, 1, 2, 2, 3, 3, 5, 7, 8, 9, 0)


@dataclass
class Firm:
    snapshot: FirmSnapshot
    truth: dict[str, Any] = field(default_factory=dict)


def _hour(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H", time.gmtime(t))


def _rid(person: str, i: int, stream: str = "a") -> str:
    import hashlib

    return "a_" + hashlib.sha1(f"{person}|{i}|{stream}".encode()).hexdigest()[:12]


def _mix(scenario: str, role: str, frac: float) -> np.ndarray:
    if scenario == "simpson":
        early, late = np.array([0.50, 0.35, 0.10, 0.05]), np.array([0.08, 0.07, 0.43, 0.42])
        w = (1 - frac) * early + frac * late
    else:
        w = np.full(4, 0.25)
    return w / w.sum()


def _gen_rows(*, person: str, role: str, level: str, scenario: str, now: float, weeks: int, rng: np.random.Generator, first_week: int,
              skip_weeks: frozenset[int] = frozenset(), last_week: int | None = None, rate: float = 12.0, null: bool = False,
              plateau_cap: float | None = None, lr_mult: float = 1.0, role_hint: str | None = None) -> tuple[list[dict[str, Any]], dict[str, float], list[tuple[float, str, float, float]]]:
    skills = SKILLS[role]
    lost0 = LOST0[role]
    expert = level == "expert"
    m = {s: (M_EXPERT + float(rng.normal(0, 0.015)) if expert else (0.9 if null else float(np.clip(M0[role][i] * (1 + rng.normal(0, 0.15)), 0.03, 0.9))))
         for i, s in enumerate(skills)}
    last_t: dict[str, float | None] = {s: None for s in skills}
    stability = STABILITY_EXPERT if expert else STABILITY_JUNIOR
    base0 = now - weeks * 7 * DAY - 9 * 3600.0
    rows: list[dict[str, Any]] = []
    latent: list[tuple[float, str, float, float]] = []       # (t, skill, true seconds lost without noise, true chance of finishing unaided): the truth, for the evaluation only
    taught_day: dict[tuple[str, int], bool] = {}
    serial = 0
    for w in range(first_week, (last_week if last_week is not None else weeks - 1) + 1):
        if w in skip_weeks:
            continue
        n = int(rng.poisson(rate))
        if n == 0:
            continue
        days = rng.integers(0, 5, n)
        hrs = rng.integers(8, 18, n)
        off = rng.uniform(0, 3600.0, n)
        ts = np.sort(base0 + w * 7 * DAY + days * DAY + hrs * 3600.0 + off)
        frac = w / max(1, weeks - 1)
        probs = _mix(scenario, role, frac)
        for t in ts:
            if t >= now:
                continue
            si = int(rng.choice(4, p=probs))
            s = skills[si]
            if last_t[s] is not None and not expert and not null:  # an expert's skill is stable, and so is everyone's in the null world; a junior forgets between occurrences
                m[s] = m[s] * float(np.exp(-((t - last_t[s]) / DAY) / stability))
            mm = m[s]
            q = GUESS + (1.0 - GUESS) * mm
            lost = 0.0 if null else lost0[si] * (M_EXPERT - mm)
            latent.append((float(t), s, float(lost), float(q)))
            lost += float(rng.normal(0, 7.0))
            if rng.random() < 0.04:
                lost += float(rng.uniform(100.0, 300.0))
            needs_nothing = bool(rng.random() < q)
            accepted = False
            tier, trig, stuck, ttp = 0, "none", None, None
            dismissed = False
            if needs_nothing:
                outcome, gain = "clean", LR_SELF
            else:
                shown = bool(rng.random() < 0.9)
                accepted = shown and bool(rng.random() < 0.8)
                if accepted:
                    outcome, gain = "assisted", LR_HELP
                    tier, trig, stuck = int(rng.integers(1, 3)), "auto", "p80_94"
                    ttp = float(rng.lognormal(np.log(9.0), 0.3))
                else:
                    u = float(rng.random())
                    dismissed = shown
                    if shown:
                        tier, trig, stuck = int(rng.integers(1, 3)), "auto", "p80_94"
                    outcome = "error" if u < 0.5 else ("abandoned" if u < 0.8 else "clean")
                    gain = LR_SELF * 0.5 if outcome == "error" else (0.0 if outcome == "abandoned" else LR_SELF)
            if not expert and not null:
                gl = gain * lr_mult * SKILL_LR[role][si]
                m[s] = min(plateau_cap if plateau_cap is not None else 0.999, mm + gl * (1.0 - mm))
            else:
                m[s] = mm
            last_t[s] = float(t)
            day = int(t // DAY)
            taught = bool(accepted and not taught_day.get((s, day)))
            if accepted:
                taught_day[(s, day)] = True
            lvl = int(1 + min(3, int(3 * m[s])))
            rows.append({
                "id": _rid(person, serial), "person": person, "origin": "synthetic", "origin_detail": "synthetic_learner", "t_hour": _hour(float(t)),
                "role": role, "skill": s, "step": s.replace("-", "_")[:40], "stream": "assist", "trigger": trig, "stuck_bucket": stuck, "tier": tier,
                "options_shown": 0, "answer_id": None, "accepted": bool(accepted), "dismissed": bool(dismissed),
                "seconds_to_progress": None if ttp is None else round(min(3600.0, ttp), 1), "lost_s": round(float(np.clip(lost, -600.0, 3600.0)), 1),
                "outcome": outcome, "level_before": lvl, "level_after": lvl, "taught": taught, "retrieval": False})
            serial += 1
    return rows, m, latent


def truth_effects(latent: list[tuple[float, str, float, float]], now: float) -> list[dict[str, Any]]:
    """The worker effects that are really there, from the latent truth: a time loss of at least 12 s over at least 8 occurrences in the last 3 weeks, an improvement of
    at least 12 s against the window ending 4 weeks ago, a rise in the chance of finishing unaided of at least 0.25 over the person's first 20 occurrences of the skill (the last 20 against the first 20). For the evaluation only."""
    out: list[dict[str, Any]] = []
    by: dict[str, list[tuple[float, float, float]]] = {}
    for t, sk, lost, q in latent:
        by.setdefault(sk, []).append((t, lost, q))
    for sk, occ in sorted(by.items()):
        rec = [x for x in occ if now - 21 * DAY < x[0] <= now]
        old = [x for x in occ if now - 49 * DAY < x[0] <= now - 28 * DAY]
        lr = sum(x[1] for x in rec) / len(rec) if rec else 0.0
        lo = sum(x[1] for x in old) / len(old) if old else 0.0
        if len(rec) >= 8 and lr >= 12.0:
            out.append({"kind": "time_loss_habit", "skill": sk, "size": round(lr, 1)})
        if len(rec) >= 6 and len(old) >= 6 and lo - lr >= 12.0:
            out.append({"kind": "habit_improved", "skill": sk, "size": round(lo - lr, 1)})
        if len(occ) >= 40:
            last = occ[-20:]
            ref = occ[:20]
            q1, q0 = sum(x[2] for x in last) / len(last), sum(x[2] for x in ref) / len(ref)
            if q1 - q0 >= 0.25 and q1 >= 0.65:
                out.append({"kind": "independence_milestone", "skill": sk, "size": round(q1 - q0, 3)})
    return out


def planted_from_latents(latents: dict[str, tuple[str, str, list[tuple[float, str, float, float]]]], now: float) -> tuple[dict[str, list[str]], dict[str, str]]:
    """What the generator really planted, read from its latent truth over the last 84 days (never named by hand): per role with at least 5 experts and 5 juniors with data, the two
    skills that explain most of the expert-junior gap (the juniors' true seconds lost minus the experts', weighted by the experts' occurrence mix); per role with at least 5
    juniors, the skill the juniors most often need help on (the highest mean of 1 minus the true chance of finishing unaided). For the evaluation only."""
    lo = now - 84 * DAY
    gaps: dict[str, list[str]] = {}
    bottle: dict[str, str] = {}
    for role in sorted({r for r, _l, _x in latents.values()}):
        exp = [x for r, lv, x in latents.values() if r == role and lv == "expert" and any(t > lo for t, *_ in x)]
        jun = [x for r, lv, x in latents.values() if r == role and lv == "junior" and any(t > lo for t, *_ in x)]
        skills = SKILLS[role]

        def mean_by(group: list[list[tuple[float, str, float, float]]], idx: int, skills: tuple[str, ...] = skills) -> dict[str, tuple[float, int]]:
            acc: dict[str, list[float]] = {sk: [] for sk in skills}
            for x in group:
                for t, sk, lost, q in x:
                    if t > lo:
                        acc[sk].append((lost, 1.0 - q)[idx])
            return {sk: ((sum(v) / len(v)) if v else 0.0, len(v)) for sk, v in acc.items()}

        if len(jun) >= 5:
            help_j = mean_by(jun, 1)
            top = max(skills, key=lambda sk: (round(help_j[sk][0], 6), sk))
            others = [help_j[sk][0] for sk in skills if sk != top]
            if help_j[top][0] - sum(others) / len(others) >= 0.12:       # only a margin the spec's own floor (0.10) could detect counts as planted
                bottle[role] = top
        if len(exp) >= 5 and len(jun) >= 5:
            le, lj = mean_by(exp, 0), mean_by(jun, 0)
            tot = sum(le[sk][1] for sk in skills) or 1
            expl = {sk: (le[sk][1] / tot) * (lj[sk][0] - le[sk][0]) for sk in skills}
            gaps[role] = sorted(skills, key=lambda sk: (-round(expl[sk], 6), sk))[:2]
    return gaps, bottle


def _offloaded(person: str, role: str, now: float, rng: np.random.Generator, stream: str, n: int, routine: str, serial0: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        t = now - float(rng.uniform(0.5, 27.5)) * DAY
        done = float(rng.random())
        out.append({
            "id": _rid(person, serial0 + i, stream[:1]), "person": person, "origin": "synthetic", "origin_detail": "synthetic_learner", "t_hour": _hour(t),
            "role": role, "skill": None, "step": None, "stream": stream, "trigger": "none", "stuck_bucket": None, "tier": 0, "options_shown": 0,
            "answer_id": None, "accepted": False, "dismissed": False, "seconds_to_progress": None, "lost_s": None, "outcome": "clean",
            "level_before": None, "level_after": None, "taught": False, "retrieval": False, "routine": routine,
            "minutes": round(float(rng.uniform(6.0, 14.0)), 1), "offload_outcome": "done" if done < 0.9 else ("queued" if done < 0.95 else "failed")})
    return out


def build_firm(seed: int = 0, *, scenario: str = "planted", weeks: int = 12, now: float = NOW0) -> Firm:
    """The synthetic firm. ``scenario``: ``planted`` (the demo) or ``null`` (the same people, nothing planted). Pure and deterministic."""
    null = scenario == "null"
    people: list[PersonRecord] = []
    routines: list[dict[str, Any]] = []
    truth: dict[str, Any] = {"scenario": scenario, "seed": seed, "weeks": weeks, "persons": {}, "planted": {}}
    counters: dict[str, int] = {}
    latents: dict[str, tuple[str, str, list[tuple[float, str, float, float]]]] = {}
    specials: dict[str, list[str]] = {"no_data": [], "stale": [], "new_joiner": [], "holiday": [], "role_change": []}
    for role, unit, n_exp, n_jun, scen in PLAN:
        code = V.role_code(role).lower()
        for k in range(n_exp + n_jun):
            level = "expert" if k < n_exp else "junior"
            j = k - n_exp
            counters[role] = counters.get(role, 0) + 1
            idx = counters[role]
            pid = f"p_f_{code}{idx:02d}"
            label = f"{V.role_code(role)}-{idx:02d}"
            rng = np.random.default_rng(seed_from("firm", seed, pid))
            use = "null" if null else scen
            kw: dict[str, Any] = dict(person=pid, role=role, level=level, scenario=use, now=now, weeks=weeks, rng=rng, null=null)
            first_week, skip, last_week, rate = 0, frozenset(), None, float(12.0 * np.exp(rng.normal(0, 0.2))) if level == "junior" else float(14.0 * np.exp(rng.normal(0, 0.15)))
            lr_mult = float(np.exp(rng.normal(0, 0.25))) * (0.3 if (scen == "simpson" and not null) else 1.0)
            cap = 0.55 if (scen == "plateau" and level == "junior" and not null) else None
            tenure = int(rng.integers(60, 300)) if level == "expert" else 0
            role_since = None
            if level == "junior":
                jw = JOIN_WEEKS[j % len(JOIN_WEEKS)] if scen in ("improve", "plateau") else 0
                if null:
                    jw = 0
                first_week = int(jw)
                tenure = int(weeks - jw)
            rows: list[dict[str, Any]] = []
            special = None
            if not null and level == "junior":
                if role == "data-analyst" and j == 12:
                    special = "no_data"
                elif role == "data-analyst" and j == 11:
                    special, last_week = "stale", weeks - 6
                elif role == "benefits-processor" and unit == "unit_c" and j == 3:
                    special, first_week, rate = "new_joiner", weeks - 1, 3.0
                    tenure = 1
                elif role == "benefits-processor" and unit == "unit_a" and j == 2:
                    special, skip = "holiday", frozenset({weeks - 5, weeks - 4, weeks - 3})
                elif role == "programmer" and unit == "prog_web" and j == 6:
                    special = "role_change"
            if special:
                specials[special].append(pid)
            m_end: dict[str, float] = {}
            latent: list[tuple[float, str, float, float]] = []
            if special == "no_data":
                pass
            elif special == "role_change":
                r1, m1, _l1 = _gen_rows(**{**kw, "role": "data-analyst", "scenario": "improve"}, first_week=0, last_week=weeks - 4, rate=rate, lr_mult=lr_mult)
                r2, m_end, latent = _gen_rows(**{**kw, "role": role, "rng": np.random.default_rng(seed_from("firm2", seed, pid))}, first_week=weeks - 3, rate=rate, lr_mult=lr_mult)
                rows = r1 + r2
                role_since = now - 3 * 7 * DAY
            else:
                rows, m_end, latent = _gen_rows(**kw, first_week=first_week, skip_weeks=skip, last_week=last_week, rate=rate, plateau_cap=cap, lr_mult=lr_mult)
            latents[pid] = (role, level, latent)
            # offloaded work: an approved routine with shadow matches (benefits units A and C), delegated work for a few people
            if not null and role == "benefits-processor" and unit in ("unit_a", "unit_c") and level == "junior" and special is None and j % 2 == 0:
                rows += _offloaded(pid, role, now, rng, "automation", int(rng.integers(8, 15)), ROUTINE[role], 5000)
                runs = int(rng.integers(24, 41))
                routines.append({"person": pid, "id": ROUTINE[role], "status": "approval" if j % 4 == 0 else "unattended", "support": 12, "hours_lo": 2.0, "hours_hi": 4.5,
                                 "horizon_weeks": 4, "shadow_runs": runs, "shadow_matches": runs - int(rng.integers(0, 2)), "t": now - 2 * DAY})
            if not null and role == "benefits-processor" and level == "junior" and special is None and j % 5 == 1:
                rows += _offloaded(pid, role, now, rng, "delegated", 3, "ad-hoc-lookup", 7000)
            if not null and level == "junior" and special is None and role in ("data-analyst", "programmer") and j % 2 == 0:
                lo = round(0.8 + 0.1 * (j % 4), 2)
                routines.append({"person": pid, "id": ROUTINE[role], "status": "proposed", "support": 5 + (j % 5), "hours_lo": lo, "hours_hi": round(lo + 1.5, 2),
                                 "horizon_weeks": 4, "shadow_runs": 0, "shadow_matches": 0, "t": now - 3 * DAY})
            rows.sort(key=lambda r: r["t_hour"])
            people.append(PersonRecord(id=pid, role=role, level=level, unit=unit, tenure_weeks=tenure, tz="UTC", role_since_t=role_since,
                                       joined_t=(now - tenure * 7 * DAY) if level == "junior" else None, label=label, origin="synthetic", rows=tuple(rows)))
            truth["persons"][pid] = {"role": role, "unit": unit, "level": level, "scenario": use, "special": special, "lr_mult": round(lr_mult, 3),
                                     "m_end": {s: round(v, 3) for s, v in m_end.items()}, "effects": [] if (null or level == "expert") else truth_effects(latent, now)}
    gap_truth, bottleneck_truth = ({}, {}) if null else planted_from_latents(latents, now)
    truth["planted"] = {
        "improving_units": [] if null else ["benefits-processor/unit_a", "benefits-processor/unit_c"],
        "plateau_units": [] if null else ["benefits-processor/unit_b"],
        "role_gap": gap_truth,
        "no_expert_reference": [] if null else ["programmer"], "small_team": [] if null else ["prog_infra"],
        "bottleneck": bottleneck_truth, "simpson": [] if null else ["data-analyst"],
        "specials": specials, "automation": {} if null else {"routine": ROUTINE["benefits-processor"], "approved": [r["person"] for r in routines if r["status"] != "proposed"]},
        "risk": {} if null else {"oldest_approval_h": 72.0, "injection_pauses": 2, "kill_events": 1, "false_claims": 0},
    }
    approvals = () if null else ({"age_h": 72.0}, {"age_h": 5.0}, {"age_h": 30.0})
    events = () if null else ({"kind": "injection_pause", "age_days": 3.0}, {"kind": "injection_pause", "age_days": 12.0}, {"kind": "kill", "age_days": 9.0})
    snap = FirmSnapshot(now=now, people=tuple(people), routines=tuple(routines), approvals=tuple(approvals), risk_events=tuple(events),
                        feed_t={"ledger": now, "risk_feed": now}, origin="synthetic", badge="synthetic firm", source="firm", truth=truth)
    return Firm(snap, truth)
