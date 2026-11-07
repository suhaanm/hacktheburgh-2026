"""Marginal checks: is each generated dataset inside the published ranges? (``PLAN.md`` section 5, M1 to M13.)

The claim is only ever "within the cited range", never "matches real users". Each check says how well its constant was
verified (``cited.CITED[...]["status"]``); a range we assumed ourselves is not called published.
No analytic is run here: these are statistics of the generated events and truth.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np

from .cited import CITED


def _chk(cid: str, what: str, value, rng: tuple | None, cite: str, note: str = "", applies: bool = True) -> dict[str, Any]:
    c = CITED.get(cite) or {}
    inside = None
    if applies and rng is not None and value is not None and not (isinstance(value, float) and math.isnan(value)):
        inside = bool(rng[0] <= value <= rng[1])
    return {"id": cid, "what": what, "value": None if value is None else round(float(value), 4), "range": list(rng) if rng else None,
            "inside": inside, "applies": applies, "constant": cite, "constant_status": c.get("status", "assumption"), "note": note}


def _cv(x: np.ndarray) -> float:
    return float(x.std() / x.mean()) if x.size > 2 and x.mean() > 0 else float("nan")


def cohort_checks(c) -> list[dict[str, Any]]:
    """Checks on a ``V2Cohort`` (events and truth)."""
    h, tr, people = c.hyper, c.truth["traces"], c.truth["people"]
    out: list[dict[str, Any]] = []
    pt = c.family == "process_trace"
    ks = np.array([p["k_s"] for p in people])
    out.append(_chk("M1", "share of people whose effective KLM keystroke time K is inside 0.12 to 1.2 s", float(np.mean((ks >= 0.12) & (ks <= 1.2))), (0.99, 1.0),
                    "klm_keystroke_s", "K is only used by process_trace", applies=pt))
    mt = h["pt_pointing_a_s"] + h["pt_pointing_b_s"] * 2.89
    out.append(_chk("M2a", "mean pointing time P (Fitts, mean ID 2.89 bits), s", mt, CITED["klm_pointing_s"]["range"], "klm_pointing_s", applies=pt))
    out.append(_chk("M2b", "mean ISO throughput of the pointing times, bits/s", 2.89 / mt, CITED["fitts_mouse_throughput_bps"]["range"], "fitts_mouse_throughput_bps", applies=pt))
    out.append(_chk("M2c", "Fitts slope b, s per bit", h["pt_pointing_b_s"], CITED["fitts_mouse_slope_s_per_bit"]["range"], "fitts_mouse_slope_s_per_bit", applies=pt))
    out.append(_chk("M2d", "Hick-Hyman slope, s per bit (range is our assumption)", h["pt_hick_b_s"], CITED["hick_hyman_slope_s_per_bit"]["range"], "hick_hyman_slope_s_per_bit", applies=pt))
    # M3 pauses
    pauses = np.array([x[1] for t in tr for x in t["cogs"] if x[0] == "IDLE" and x[2] is None])
    out.append(_chk("M3", "pause durations: p99 over median (leptokurtic, mixture of lognormals)", float(np.quantile(pauses, 0.99) / np.median(pauses)) if pauses.size > 30 else None,
                    CITED["pause_lognormal_mixture"]["range"], "pause_lognormal_mixture", f"{pauses.size} untagged pauses"))
    # M4 dwell body lognormal: pooled residual of log dwell about each (person, cog) mean, untagged work of experts
    by: dict[tuple[str, str], list[float]] = defaultdict(list)
    for t in tr:
        if t["level"] != "expert":
            continue
        for cog, d, tag in t["cogs"]:
            if tag is None and cog not in ("IDLE", "REVERT") and d > 0.5:
                by[(t["person"], cog)].append(math.log(d))
    res = []
    for v in by.values():
        if len(v) >= 3:
            m = sum(v) / len(v)
            res.extend(x - m for x in v)
    ks_d = None
    if len(res) > 50:
        from scipy.stats import kstest
        r = np.array(res)
        ks_d = float(kstest((r - r.mean()) / r.std(), "norm").statistic)
    out.append(_chk("M4", "Kolmogorov-Smirnov distance of expert log dwell residuals to a normal (lognormal body)", ks_d, (0.0, 0.15), "pause_lognormal_mixture",
                    f"{len(res)} residuals; the bound 0.15 is ours"))
    # M5 practice: the exponent is a parameter (draw check) and learning must be visible in low-tenure novices
    alphas = np.array([p["learn_alpha"] for p in people])
    lo, hi = CITED["power_law_exponent"]["range"]
    out.append(_chk("M5a", "share of people whose learning exponent is inside 0.1 to 1.0 (power law or exponential curve)", float(np.mean((alphas >= lo) & (alphas <= hi))), (0.9, 1.0), "power_law_exponent",
                    "a parameter draw: a check that the range was respected, not an estimate"))
    ratios = []
    for pid in {t["person"] for t in tr}:
        ts = sorted((t for t in tr if t["person"] == pid and t["n_eff"] < 8), key=lambda t: t["case"])
        if len(ts) >= 5:
            a_ = np.median([t["duration_s"] for t in ts[:2]])
            b_ = np.median([t["duration_s"] for t in ts[-3:]])
            ratios.append(b_ / a_)
    out.append(_chk("M5b", "median over low-tenure people of (median of last 3 cases) / (median of first 2 cases): learning is visible", float(np.median(ratios)) if len(ratios) >= 3 else None,
                    (0.3, 0.98), "power_law_exponent", f"{len(ratios)} people with tenure under 8 cases and at least 5 cases; the bounds are ours"))
    slopes = []
    for pid in {t["person"] for t in tr}:
        ts = [t for t in tr if t["person"] == pid and t["level"] == "novice"]
        if len(ts) >= 5:
            x = np.log1p([t["n_eff"] for t in ts])
            y = np.log([t["duration_s"] for t in ts])
            if np.ptp(x) > 0.2:
                slopes.append(-float(np.polyfit(x, y, 1)[0]))
    out.append(_chk("M5c", "(informational) median fitted slope of log time on log practice among novices", float(np.median(slopes)) if len(slopes) >= 5 else None,
                    CITED["power_law_exponent"]["range"], "power_law_exponent",
                    "understates alpha: the fit includes the asymptote, and most novices have tenure above the 8 cases observed", applies=False))
    # M6 interruptions per hour
    hours = sum(t["duration_s"] for t in tr) / 3600.0
    out.append(_chk("M6", "interruptions per hour of task time", sum(t["interruptions"] for t in tr) / max(hours, 1e-9), CITED["interruptions_per_hour"]["range"], "interruptions_per_hour"))
    # M7 burstiness of inter-event times within a case
    times: dict[str, list[float]] = defaultdict(list)
    from .emit import iso  # noqa: F401
    from datetime import datetime
    for r in c.rows:
        if r.get("task_id") and r["type"] not in ("task_start", "task_end", "progress", "stuck"):
            times[r["task_id"]].append(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp())
    gaps = np.concatenate([np.diff(sorted(v)) for v in times.values() if len(v) > 3] or [np.zeros(0)])
    gaps = gaps[gaps > 0]
    out.append(_chk("M7", "coefficient of variation of inter-event times within a case", _cv(gaps) if gaps.size > 100 else None, CITED["burstiness_cv"]["range"], "burstiness_cv", f"{gaps.size} gaps"))
    # M8 to M11 person-level
    slips = np.array([p["p_slip"] for p in people])
    out.append(_chk("M8", "share of people whose slip probability per step is inside 0.04 to 6.5 percent (cited range across field types)", float(np.mean((slips >= 0.0004) & (slips <= 0.065))), (0.9, 1.0), "slip_rate_per_step",
                    "low confidence constant; not clipped, so the tail of the person distribution can fall outside"))
    ls = np.log([p["speed_factor"] for p in people])
    out.append(_chk("M9", "between-person SD of log speed", float(ls.std()), (0.10, 0.35), "klm_keystroke_s", "range from KLM typist tiers"))
    corr = float(np.corrcoef(ls, slips)[0, 1]) if len(people) > 5 else None
    out.append(_chk("M10", "correlation across people of slowness with slip probability (faster people slip less: positive)", corr, (0.0, 1.0), "typing_population", "sign only"))
    out.append(_chk("M11", "mean fatigue slope per hour", h["fatigue_per_h"], CITED["fatigue_slowdown_per_hour"]["range"], "fatigue_slowdown_per_hour"))
    # M12 capture noise realised
    dup = 0
    n = 0
    last: dict[str, tuple] = {}
    for r in c.rows:
        if r["type"] in ("task_start", "task_end", "progress", "stuck", "idle"):
            continue
        n += 1
        key = (r["person"], r["type"], (r.get("target") or {}).get("label_hash"))
        t = datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp()
        if key in last and 0 <= t - last[key][0] <= 0.41 and last[key][1] != r["id"]:
            dup += 1
        last[key] = (t, r["id"])
    out.append(_chk("M12a", "share of events that look like double fires (same person, type and label within 0.4 s)", dup / max(1, n), (0.0, 0.25), "burstiness_cv", "includes genuine fast repeats; the range is ours"))
    tasks = {t["task_id"] for t in tr}
    ends = {r["task_id"] for r in c.rows if r["type"] == "task_end"}
    out.append(_chk("M12b", "share of cases with no task_end marker", 1 - len(tasks & ends) / max(1, len(tasks)), (0.0, 0.12), "burstiness_cv", "range is ours"))
    return out


def structure_checks(c) -> list[dict[str, Any]]:
    """Structural plausibility targets (set before any analytic ran; ranges are our assumption, flagged as such)."""
    tr = c.truth["traces"]
    nov = [t for t in tr if t["level"] == "novice"]
    exp = [t for t in tr if t["level"] == "expert"]
    mat = lambda t: sum(1 for x in t["deficits"] if x["material"])  # noqa: E731
    out = []
    if nov:
        out.append(_chk("S1", "material deficit occurrences per novice case", float(np.mean([mat(t) for t in nov])), (0.1, 2.5), "assumption", "structural plausibility target"))
    if exp:
        out.append(_chk("S2", "material deficit occurrences per expert case (experts are not clean)", float(np.mean([mat(t) for t in exp])), (0.0, 0.8), "assumption", "structural plausibility target"))
    pp: dict[str, int] = defaultdict(int)
    for t in tr:
        pp[t["person"]] += mat(t)
    out.append(_chk("S3", "share of people with no material deficit in any case", float(np.mean([v == 0 for v in pp.values()])), (0.03, 0.9), "assumption", "some people have none, not everyone"))
    out.append(_chk("S4", "hidden stuck episodes per case", len(c.truth["stuck_episodes"]) / max(1, len(tr)), (0.1, 2.0), "assumption", "structural plausibility target"))
    if exp and nov:
        em = float(np.median([t["duration_s"] for t in exp]))
        nm = float(np.median([t["duration_s"] for t in nov]))
        out.append(_chk("S5", "share of novice cases faster than the expert median (the labels overlap)", float(np.mean([t["duration_s"] < em for t in nov])), (0.01, 0.45), "assumption"))
        deep = c.role == "benefits-processor"
        out.append(_chk("S6a", "median expert case duration, s", em, (300.0, 1000.0) if deep else (150.0, 800.0), "assumption",
                        "pack medians sum to about 565 s (benefits) or 250 s (thin roles) before interruptions"))
        out.append(_chk("S6b", "novice over expert median duration", nm / em, (1.1, 2.2), "assumption"))
    return out


def label_checks(c, episodes=None) -> list[dict[str, Any]]:
    """M13: how decoupled the hazard label is from the hidden stuck episodes. Uses only bin construction, no model."""
    from datetime import datetime

    from ..hazard.features import build_bins

    eps = episodes if episodes is not None else c.episodes()
    tab = build_bins(eps)
    if tab.n == 0:
        return []
    planted = c.planted_spells()
    lab = np.zeros(tab.n, dtype=int)
    for person, spells in planted.items():
        rows = tab.rows_of([person])
        if not rows.size:
            continue
        t = tab.t[rows]
        for t0, t1 in spells:
            lab[rows[(t + tab.horizon_s > t0) & (t < t1)]] = 1
    y = tab.y.astype(int)
    share_in = float(((y == 1) & (lab == 1)).sum() / max(1, (y == 1).sum()))
    cover = float(((y == 1) & (lab == 1)).sum() / max(1, (lab == 1).sum()))
    # hidden stuck episodes that still contain a progress event
    prog: dict[str, list[float]] = defaultdict(list)
    for r in c.rows:
        if r["type"] == "progress" and r.get("task_id"):
            prog[r["task_id"]].append(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp())
    stuck = c.truth["stuck_episodes"]
    with_prog = [any(_ts(s["t0"]) <= p <= _ts(s["t1"]) for p in prog.get(s["task_id"], [])) for s in stuck]
    return [
        _chk("M13a", "base rate of the hazard label (no progress in the next 60 s)", float(y.mean()), (0.02, 0.8), "burstiness_cv", "informational", applies=False),
        _chk("M13b", "share of label-1 bins that fall inside a hidden stuck episode (v1: 0.25)", share_in, (0.02, 0.98), "burstiness_cv", "neither 0 nor 1 means the label is not the hidden state"),
        _chk("M13c", "share of bins inside a hidden stuck episode that are label 1", cover, (0.02, 0.98), "burstiness_cv", "episodes that only partly suppress progress, and benign detours"),
        _chk("M13d", "share of hidden stuck episodes that still contain a progress event", float(np.mean(with_prog)) if with_prog else None, (0.02, 0.98), "burstiness_cv", f"{len(stuck)} episodes"),
    ]


def _ts(s: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def summarise(checks_by_dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Per check id: how many datasets were inside the range, and the status of the cited constant."""
    agg: dict[str, dict[str, Any]] = {}
    for name, checks in checks_by_dataset.items():
        for c in checks:
            a = agg.setdefault(c["id"], {"id": c["id"], "what": c["what"], "range": c["range"], "constant": c["constant"], "constant_status": c["constant_status"],
                                         "inside": 0, "outside": 0, "not_applicable": 0, "values": []})
            if not c["applies"] or c["inside"] is None:
                a["not_applicable"] += 1
            elif c["inside"]:
                a["inside"] += 1
            else:
                a["outside"] += 1
            if c["value"] is not None:
                a["values"].append(c["value"])
    for a in agg.values():
        v = a.pop("values")
        a["min"], a["median"], a["max"] = (round(min(v), 4), round(float(np.median(v)), 4), round(max(v), 4)) if v else (None, None, None)
    return agg
