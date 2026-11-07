"""The independence score and the growth numbers (CUE-7, GRO-1 data). Pure functions of ledger rows and a clock.

"Needs less help", never "became an expert". The unit is a skill occurrence in the ``assist`` stream. Delegated and automation rows
are filtered out before any number is computed (``assist_only``): offloaded work is listed, never scored.

Components (each with n and an interval; every ``None`` is "cannot be computed yet", never 0):

* **independence**: share of the last ``WINDOW`` (20) occurrences completed with no accepted cue; reported with its Wilson interval and
  the Wilson LOWER bound (the number the composite uses). Errors and unfinished steps count as not independent (a dismissed cue
  without finishing the step is not independence); an occurrence that did not happen has no row and is not counted.
* **trend**: the Theil-Sen slope of the assisted share over blocks of ``BLOCK`` (5) consecutive occurrences, per 10 occurrences
  (negative = needs less help), with a bootstrap interval that resamples the occurrences inside each block.
* **gap closure**: seconds lost against the pack's expert median per occurrence (the unit of the genome price), the first 5 occurrences
  against the latest 5, as a share closed (0 to 1), with a bootstrap interval. Needs 10 occurrences and an initial gap above zero.
* **retention**: the first occurrence at least 3 days after the skill was last taught was unaided and clean (Wilson interval); None until
  such an occurrence exists.
* **mastery**: the ledger replayed through the tracing model (clean and error are evidence, assisted and abandoned are none, forgetting
  between occurrences), decayed to now.

Composite 0 to 100 = 0.4 independence lower bound + 0.3 mastery + 0.2 gap closure + 0.1 retention. The weights are stated assumptions,
not fitted. When a component is None the composite is renormalised over the available weights and flagged ``composite_partial``; the
components always come with it and the headline is the trend with n and an interval, never the composite alone.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

from ..skills import tracing as T
from ..trust.stats import wilson_interval
from . import teach
from .teach import DAY_S, assist_rows, replay_mastery, row_time

WINDOW = 20
BLOCK = 5
BASELINE_N = 5
NEEDED = 10
RETENTION_DAYS = 3.0
WEIGHTS = {"independence_lb": 0.4, "mastery": 0.3, "gap_closure": 0.2, "retention": 0.1}
WEIGHTS_NOTE = "stated assumptions, not fitted"
CLAIM_TAIL = "This is not a measure of expertise."


def assist_only(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The only rows any score number may read: the assist stream, oldest first (file order within an hour)."""
    rs = [r for r in rows if r.get("stream") == "assist"]
    return sorted(rs, key=lambda r: r["t_hour"])


def is_independent(r: dict[str, Any]) -> bool:
    return r["outcome"] == "clean" and not r.get("accepted")


def is_assisted(r: dict[str, Any]) -> bool:
    return r["outcome"] == "assisted"


def _rnd(x, nd: int = 4):
    return None if x is None else round(float(x), nd)


def _iv(lo, hi, nd: int = 4):
    return None if lo is None or hi is None else [round(float(lo), nd), round(float(hi), nd)]


def _seed(rows: Sequence[dict[str, Any]], salt: str = "") -> int:
    h = hashlib.sha1((salt + "|" + ",".join(str(r.get("id")) for r in rows[-50:]) + f"|{len(rows)}").encode()).hexdigest()
    return int(h[:8], 16)


# ------------------------------------------------------------------------------------------------ independence
def independence(occ: Sequence[dict[str, Any]], window: int = WINDOW) -> dict[str, Any]:
    w = list(occ)[-window:]
    n = len(w)
    k = sum(1 for r in w if is_independent(r))
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "share": _rnd(k / n) if n else None, "wilson": _iv(lo, hi) if n else None, "lower": _rnd(lo) if n else None}


def baseline(occ: Sequence[dict[str, Any]], n0: int = BASELINE_N) -> dict[str, Any] | None:
    w = list(occ)[:n0]
    if len(w) < n0:
        return None
    k = sum(1 for r in w if is_independent(r))
    lo, hi = wilson_interval(k, len(w))
    return {"k": k, "n": len(w), "share": _rnd(k / len(w)), "wilson": _iv(lo, hi)}


# ------------------------------------------------------------------------------------------------ trend
def theil_sen(y: Sequence[float]) -> float | None:
    """Median of the pairwise slopes of y against 0, 1, 2, ..."""
    y = np.asarray(y, float)
    n = y.size
    if n < 2:
        return None
    i, j = np.triu_indices(n, k=1)
    return float(np.median((y[j] - y[i]) / (j - i)))


def _block_flags(occ: Sequence[dict[str, Any]], size: int = BLOCK) -> list[np.ndarray]:
    flags = np.array([1.0 if is_assisted(r) else 0.0 for r in occ])
    nb = len(flags) // size
    return [flags[b * size:(b + 1) * size] for b in range(nb)]


def trend(occ: Sequence[dict[str, Any]], n_boot: int = 300, seed: int = 0, size: int = BLOCK) -> dict[str, Any]:
    blocks = _block_flags(occ, size)
    out: dict[str, Any] = {"slope_per_10": None, "ci": None, "direction": "too_early", "blocks": [], "n_blocks": len(blocks)}
    out["blocks"] = [{"i": b, "n": int(x.size), "assisted_share": _rnd(x.mean())} for b, x in enumerate(blocks)]
    if len(blocks) < 3:
        return out
    shares = np.array([b.mean() for b in blocks])
    per_block = theil_sen(shares)
    scale = 10.0 / size
    out["slope_per_10"] = _rnd(per_block * scale)
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        nb = len(blocks)
        draws = np.empty((n_boot, nb))
        for b, x in enumerate(blocks):
            draws[:, b] = rng.binomial(x.size, x.mean(), n_boot) / x.size      # resampling the occurrences inside block b
        i, j = np.triu_indices(nb, k=1)
        slopes = np.median((draws[:, j] - draws[:, i]) / (j - i), axis=1) * scale
        lo, hi = np.quantile(slopes, [0.025, 0.975])
        out["ci"] = _iv(lo, hi)
        out["direction"] = "less_help" if hi < 0 else ("more_help" if lo > 0 else "steady")
    else:
        out["direction"] = "less_help" if per_block < 0 else ("more_help" if per_block > 0 else "steady")
    return out


# ------------------------------------------------------------------------------------------------ gap closure
def gap_closure(occ: Sequence[dict[str, Any]], n_boot: int = 300, seed: int = 0, n0: int = BASELINE_N) -> dict[str, Any]:
    out: dict[str, Any] = {"value": None, "first5_lost_s": None, "last5_lost_s": None, "ci": None, "n_first": 0, "n_last": 0}
    if len(occ) < 2 * n0:
        return out
    first = np.array([r["lost_s"] for r in occ[:n0] if r.get("lost_s") is not None], float)
    last = np.array([r["lost_s"] for r in occ[-n0:] if r.get("lost_s") is not None], float)
    out["n_first"], out["n_last"] = int(first.size), int(last.size)
    if first.size < 3 or last.size < 3:
        return out
    g0, g1 = float(first.mean()), float(last.mean())
    out["first5_lost_s"], out["last5_lost_s"] = _rnd(g0, 2), _rnd(g1, 2)
    if g0 <= 0:
        return out                     # no initial gap: nothing to close, the component is not applicable
    out["value"] = _rnd(min(1.0, max(0.0, (g0 - g1) / g0)))
    if n_boot > 0:
        rng = np.random.default_rng(seed + 1)
        a = rng.choice(first, size=(n_boot, first.size)).mean(1)
        b = rng.choice(last, size=(n_boot, last.size)).mean(1)
        ok = a > 0
        if ok.sum() >= 20:
            v = np.clip((a[ok] - b[ok]) / a[ok], 0.0, 1.0)
            out["ci"] = _iv(*np.quantile(v, [0.025, 0.975]))
    return out


# ------------------------------------------------------------------------------------------------ retention
def retention(occ: Sequence[dict[str, Any]], days: float = RETENTION_DAYS) -> dict[str, Any]:
    """Probes: the first occurrence at least ``days`` after the skill was last taught. Per skill, then pooled."""
    k = n = 0
    by_skill: dict[str, list[dict[str, Any]]] = {}
    for r in occ:
        by_skill.setdefault(r.get("skill") or "", []).append(r)
    for _skill, rs in by_skill.items():
        taught_t: float | None = None
        for r in sorted(rs, key=row_time):
            t = row_time(r)
            if taught_t is not None and t >= taught_t + days * DAY_S:
                n += 1
                k += 1 if is_independent(r) else 0
                taught_t = None
            if r.get("taught"):
                taught_t = t
    lo, hi = wilson_interval(k, n) if n else (None, None)
    return {"value": _rnd(k / n) if n else None, "k": k, "n": n, "wilson": _iv(lo, hi) if n else None, "after_days": days}


# ------------------------------------------------------------------------------------------------ mastery
def mastery_by_skill(occ: Sequence[dict[str, Any]], now: float) -> dict[str, float]:
    by: dict[str, list[dict[str, Any]]] = {}
    for r in occ:
        by.setdefault(r.get("skill") or "", []).append(r)
    return {s: float(T.decayed(replay_mastery(rs), now)) for s, rs in by.items() if s}


def _mean(xs: Sequence[float]) -> float | None:
    return float(np.mean(xs)) if len(xs) else None


# ------------------------------------------------------------------------------------------------ composite
def composite(ind_lower: float | None, mastery: float | None, gap: float | None, ret: float | None) -> dict[str, Any]:
    comps = {"independence_lb": ind_lower, "mastery": mastery, "gap_closure": gap, "retention": ret}
    avail = {k: v for k, v in comps.items() if v is not None}
    w = sum(WEIGHTS[k] for k in avail)
    if not avail or w <= 0 or ind_lower is None:
        return {"value": None, "partial": True, "available_weight": round(w, 3), "used_weights": {}}
    val = 100.0 * sum(WEIGHTS[k] * v for k, v in avail.items()) / w
    return {"value": _rnd(val, 1), "partial": len(avail) < len(comps), "available_weight": round(w, 3),
            "used_weights": {k: round(WEIGHTS[k] / w, 4) for k in avail}}


def _point_composite(occ: Sequence[dict[str, Any]], now: float, window: int = WINDOW) -> float | None:
    ind = independence(occ, window)
    ms = list(mastery_by_skill(occ, now).values())
    gc = gap_closure(occ, n_boot=0)["value"]
    rt = retention(occ)["value"]
    return composite(ind["lower"], _mean(ms), gc, rt)["value"]


def composite_interval(occ: Sequence[dict[str, Any]], now: float, n_boot: int, seed: int) -> list[float] | None:
    """Percentile interval of the composite over an occurrence bootstrap that keeps time order (resampled indices are sorted)."""
    n = len(occ)
    if n_boot <= 0 or n < NEEDED:
        return None
    rng = np.random.default_rng(seed + 2)
    vals = []
    for _ in range(n_boot):
        idx = np.sort(rng.integers(0, n, n))
        v = _point_composite([occ[i] for i in idx], now)
        if v is not None:
            vals.append(v)
    if len(vals) < max(20, n_boot // 4):
        return None
    return _iv(*np.quantile(vals, [0.025, 0.975]), nd=1)


# ------------------------------------------------------------------------------------------------ time to progress
def time_to_progress(occ: Sequence[dict[str, Any]], n_boot: int = 300, seed: int = 0) -> dict[str, Any] | None:
    v = np.array([r["seconds_to_progress"] for r in occ if r.get("seconds_to_progress") is not None], float)
    if v.size == 0:
        return None
    ci = None
    if v.size >= 5 and n_boot > 0:
        rng = np.random.default_rng(seed + 3)
        ci = _iv(*np.quantile(np.median(rng.choice(v, size=(n_boot, v.size)), axis=1), [0.025, 0.975]), nd=1)
    return {"after_cue": {"median_s": _rnd(np.median(v), 1), "ci": ci, "n": int(v.size)}, "no_cue": None,
            "note": "Seconds from the first cue to the next progress event. Live data has no no-cue counterfactual; the simulator pairs them."}


# ------------------------------------------------------------------------------------------------ the whole picture
def compute(occ_rows: Sequence[dict[str, Any]], now: float, *, n_boot: int = 200, seed: int = 0, window: int = WINDOW) -> dict[str, Any]:
    """Every number for one focus (a skill, or everything). ``occ_rows`` may contain any streams; only assist rows are read."""
    occ = assist_only(occ_rows)
    n = len(occ)
    ind = independence(occ, window)
    bl = baseline(occ)
    tr = trend(occ, n_boot, seed) if n >= NEEDED else {"slope_per_10": None, "ci": None, "direction": "too_early", "blocks": [], "n_blocks": n // BLOCK}
    gc = gap_closure(occ, n_boot, seed)
    rt = retention(occ)
    ms = mastery_by_skill(occ, now)
    m = _mean(list(ms.values()))
    ready = n >= NEEDED
    comp = composite(ind["lower"], m, gc["value"], rt["value"]) if ready else {"value": None, "partial": True, "available_weight": 0.0, "used_weights": {}}
    ci = composite_interval(occ, now, n_boot, seed) if ready and comp["value"] is not None else None
    counts = Counter(r["outcome"] for r in occ)
    return {
        "n": n, "ready": ready, "independence": ind, "baseline": bl, "trend": tr, "gap_closure": gc, "retention": rt,
        "mastery": {"value": _rnd(m), "by_skill": {s: _rnd(v) for s, v in sorted(ms.items())}},
        "composite": comp, "composite_ci": ci,
        "occurrences": {"total": n, "unaided": counts.get("clean", 0), "assisted": counts.get("assisted", 0), "errors": counts.get("error", 0),
                        "abandoned": counts.get("abandoned", 0)},
    }


def curve(occ_rows: Sequence[dict[str, Any]], window: int = WINDOW, start: int = NEEDED, max_points: int = 200) -> list[dict[str, Any]]:
    """Independence over a sliding window ending at each occurrence from ``start`` on, with the Wilson interval, the cue tiers seen
    in the window (``tiers[t]`` = occurrences whose highest tier was t) and the help level at the window's end."""
    occ = assist_only(occ_rows)
    pts = []
    for i in range(start, len(occ) + 1):
        w = occ[max(0, i - window):i]
        k = sum(1 for r in w if is_independent(r))
        lo, hi = wilson_interval(k, len(w))
        tiers = [0] * 5
        for r in w:
            tiers[int(r.get("tier") or 0)] += 1
        pts.append({"i": i, "t_hour": occ[i - 1]["t_hour"], "independence": _rnd(k / len(w)), "lo": _rnd(lo), "hi": _rnd(hi), "n": len(w),
                    "level": occ[i - 1].get("level_after"), "tiers": tiers})
    return pts[-max_points:]


def _origin_detail(occ: Sequence[dict[str, Any]]) -> str:
    c = Counter(r.get("origin_detail") for r in occ if r.get("origin_detail"))
    if c:
        return c.most_common(1)[0][0]
    return "live_worker" if any(r.get("origin") == "real" for r in occ) else "synthetic_learner"


def growth(rows: Sequence[dict[str, Any]], *, person: str | None = None, skill: str | None = None, now: float | None = None,
           n_boot: int = 200, window: int = WINDOW) -> dict[str, Any]:
    """The payload of ``GET /growth``. Keys starting with an underscore are for the route's meta, not the data."""
    from .vocab import skill_info

    rows = [r for r in rows if person is None or r.get("person") == person]
    occ_all = assist_only(rows)
    now = now if now is not None else (row_time(occ_all[-1]) + 1800.0 if occ_all else 0.0)
    seed = _seed(occ_all, person or "")
    focus = [r for r in occ_all if skill is None or r.get("skill") == skill]
    role = (focus[-1] if focus else (occ_all[-1] if occ_all else {})).get("role", "")
    g = compute(focus, now, n_boot=n_boot, seed=seed, window=window)
    skills_present = sorted({r["skill"] for r in occ_all if r.get("skill")})
    by_skill = []
    less = 0
    for s in skills_present:
        srows = [r for r in occ_all if r.get("skill") == s]
        sg = compute(srows, now, n_boot=min(n_boot, 150), seed=seed + 7, window=window)
        info = skill_info(role, s) if role else {"label": s, "name": s}
        first10 = last10 = None
        if len(srows) >= 20:
            first10 = {"n": 10, "assisted": sum(1 for r in srows[:10] if is_assisted(r))}
            last10 = {"n": 10, "assisted": sum(1 for r in srows[-10:] if is_assisted(r))}
        ret = sg["retention"]
        mem = teach.skill_memory(srows, now)
        direction = sg["trend"]["direction"]
        less += direction == "less_help"
        by_skill.append({
            "skill": s, "label": info["label"], "name": info["name"], "n": sg["n"], "independent": sg["occurrences"]["unaided"], "assisted": sg["occurrences"]["assisted"],
            "independence_lower": sg["independence"]["lower"], "mastery": sg["mastery"]["value"], "level": srows[-1].get("level_after"), "direction": direction,
            "first10": first10, "last10": last10, "time_to_progress": time_to_progress(srows, min(n_boot, 200), seed),
            "retention": {"value": ret["value"], "k": ret["k"], "n": ret["n"], "wilson": ret["wilson"]},
            "retrieval_due": teach.retrieval_due(mem, now),
        })
    off = [r for r in rows if r.get("stream") in ("delegated", "automation")]
    offloaded = {"delegated": sum(1 for r in off if r["stream"] == "delegated"), "automation": sum(1 for r in off if r["stream"] == "automation"),
                 "minutes": {s: round(sum((r.get("minutes") or 0.0) for r in off if r["stream"] == s), 1) for s in ("delegated", "automation")},
                 "by_skill": dict(Counter(r.get("skill") or "none" for r in off)),
                 "note": "Work the agent did for you. It never changes the score."}
    n_sk = len(by_skill)
    if g["n"] < NEEDED:
        claim = f"Too early to say: {g['n']} occurrences so far, {NEEDED} needed. {CLAIM_TAIL}"
    else:
        claim = f"Needs less help on {less} of {n_sk} skills. {CLAIM_TAIL}"
    ready = g["ready"]
    data = {
        "person": person, "role": role or None, "skill": skill, "window": window, "as_of": None if not occ_all else row_time(occ_all[-1]) and _asof(now),
        "origin_detail": _origin_detail(focus or occ_all),
        "readiness": {"occurrences": g["n"], "needed": NEEDED, "ready": ready},
        "score": {"composite": g["composite"]["value"], "composite_ci": g["composite_ci"], "composite_partial": g["composite"]["partial"],
                  "available_weight": g["composite"]["available_weight"], "weights": dict(WEIGHTS), "used_weights": g["composite"]["used_weights"],
                  "weights_note": WEIGHTS_NOTE},
        "baseline": g["baseline"],
        "components": {"independence": g["independence"], "mastery": g["mastery"], "gap_closure": g["gap_closure"], "retention": g["retention"]},
        "trend": g["trend"],
        "curve": curve(focus, window) if ready else [],
        "occurrences": g["occurrences"],
        "time_to_progress": time_to_progress(focus, n_boot, seed),
        "by_skill": by_skill,
        "offloaded": offloaded,
        "counts": dict(Counter(r.get("stream") for r in rows)),
        "claim": claim,
    }
    origin = "mixed" if len({r.get("origin") for r in focus or occ_all}) > 1 else ((focus or occ_all)[0]["origin"] if (focus or occ_all) else "synthetic")
    data["_origin"] = origin
    data["_n"] = g["n"]
    data["_split"] = None
    data["_note"] = (f"Independence is the share of the last {window} occurrences finished with no accepted cue, with its Wilson interval. "
                     "The composite uses stated, unfitted weights; read the components. Delegated and automation work is not counted.")
    return data


def _asof(t: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summary_line(rows: Sequence[dict[str, Any]]) -> str:
    """The one line written into the worker's memory file: counts only, derived from the ledger, safe to read aloud."""
    occ = assist_only(rows)
    w = occ[-WINDOW:]
    needed = sum(1 for r in w if is_assisted(r))
    skills = len({r.get("skill") for r in occ if r.get("skill")})
    tag = " (synthetic data)" if any(r.get("origin") == "synthetic" for r in occ) else ""
    return f"Cue assist ledger{tag}: help was needed on {needed} of the last {len(w)} steps across {skills} skills."
