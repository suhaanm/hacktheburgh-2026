"""Analytics routes owned by engine-analytics. `api/app.py` includes `router` when importable.

  GET /hazard/{person}   stuck prediction for one person, from leave-one-person-out predictions
                         -> {meta: AnalyticMeta, data: {series, model, baselines, calibration, false_alarms_per_hour, split}}

Nothing here calls a model. The first request computes the evaluation (about 5 to 20 s for the persona data) and
caches it in-process, keyed on the synthetic files' modification times, so a regenerated dataset is picked up.

`analytics_sections()` assembles the section dicts the eval harness writes into evals/report.json (hazard, ope,
routing, agent_claims, plus policy_gate, skills and the limitations register); each has its own `meta`.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(tags=["analytics"])

_lock = threading.Lock()
_cache: dict[tuple, dict | None] = {}


def _data_signature() -> tuple:
    from understudy_engine.store import data_dir
    base = data_dir() / "synthetic"
    sig = []
    for d in ("nine-to-five", "night-owl", "shift-worker", "irregular", "apprentices"):
        p = base / d / "events.jsonl"
        sig.append((d, p.stat().st_mtime_ns if p.exists() else None))
    return tuple(sig)


def _hazard_eval(secondary: bool) -> dict | None:
    """Persona evaluation (primary) or apprentice evaluation (secondary), each computed once per data version."""
    key = (_data_signature(), "apprentices" if secondary else "personas")
    with _lock:
        if key not in _cache:
            from understudy_engine.hazard import evaluate_apprentice_hazard, evaluate_hazard_data
            for k in [k for k in _cache if k[0] != key[0]]:
                del _cache[k]          # a regenerated dataset invalidates everything
            _cache[key] = (evaluate_apprentice_hazard(n_boot=100) if secondary
                           else evaluate_hazard_data(n_boot=100, include_series=True, include_secondary=False))
        return _cache[key]


def warm(background: bool = True) -> threading.Thread | None:
    """Compute the persona hazard evaluation now so the first GET /hazard/{person} is instant (about 6 to 10 s of work).
    The app may call this at startup; it is safe to call more than once."""
    if not background:
        _hazard_eval(secondary=False)
        return None
    t = threading.Thread(target=lambda: _hazard_eval(secondary=False), name="hazard-warm", daemon=True)
    t.start()
    return t


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@router.get("/hazard/{person}")
def get_hazard(person: str, limit: int | None = Query(None, ge=1, le=100000, description="keep the first N series points")):
    is_apprentice = person.startswith(("p_exp", "p_nov"))
    src = _hazard_eval(secondary=is_apprentice)
    if src is None or person not in src.get("series_by_person", {}):
        known = sorted((src or {}).get("series_by_person", {}))
        return _error(404, "unknown_person", f"No hazard series for {person!r}. Known people: {', '.join(known) or 'none (is data/synthetic generated?)'}.")
    series = src["series_by_person"][person]
    if limit:
        series = series[:limit]
    pp = src["per_person"][person]
    note = (f"Held-out predictions for {person}: the model that scored them never saw this person. "
            f"{src['data_source']}. Label: no progress in the next 60 s.")
    if is_apprentice:
        note += " Scripted task sequences: part of the gain over the baselines is the script."
    meta = dict(src["meta"], note=note, n_unit="people")
    data = {
        "series": series,
        "model": src["model"] and {k: src["model"][k] for k in ("log_loss", "brier", "ece", "ci_log_loss")},
        "baselines": {k: {m: v[m] for m in ("log_loss", "brier", "ece")} for k, v in src["baselines"].items()},
        "calibration": src["calibration"],
        "false_alarms_per_hour": src["false_alarms_per_hour"],
        "false_alarms_within_budget": src["false_alarms_within_budget"],
        "split": src["split"],
        # extras for the page: this person's own held-out scores and the pooled event-level result
        "person": {"id": person, "n_bins": pp["n_bins"], "stuck_rate": pp["stuck_rate"],
                   "model": pp["model"], "time_since_progress": pp["time_since_progress"], "base_rate": pp["base_rate"],
                   "alarm_rule": pp["alarm_rule"], "events": pp["events"]},
        "events": src["model"]["events"],
        "budget_fa_per_hour": src["budget_fa_per_hour"],
        "caveats": src["caveats"],
    }
    return {"meta": meta, "data": data}


def analytics_sections(*, seed: int = 0, n_boot: int = 300) -> dict:
    """Section dicts for evals/report.json. Heavy (tens of seconds); the eval harness calls it, the API does not."""
    from understudy_engine.hazard import evaluate_hazard_data
    from understudy_engine.policy.evaluate import evaluate_gate, evaluate_ope
    from understudy_engine.routing.evaluate import evaluate_routing
    from understudy_engine.skills.evaluate import evaluate_skills
    from understudy_engine.trust.claims import evaluate_claims
    from understudy_engine.trust.limitations import analytics_limitations

    out: dict = {}
    haz = evaluate_hazard_data(n_boot=n_boot, seed=seed, include_series=True)
    out["hazard"] = haz
    out["ope"] = evaluate_ope(seed=seed)
    out["routing"] = evaluate_routing(seed=seed)
    out["agent_claims"] = evaluate_claims(seed=seed, n_boot=n_boot)
    try:
        from understudy_engine.hazard.data import load_persona_episodes
        eps, _, _ = load_persona_episodes()
        out["policy_gate"] = evaluate_gate(eps)
        out["skills"] = evaluate_skills()
    except FileNotFoundError:
        pass
    out["limitations"] = analytics_limitations()
    return out
