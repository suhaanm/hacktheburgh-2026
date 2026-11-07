"""``evaluate_study_roles()``: the role-studies section for engine-eval's report. Reads results/<role>/summary.json for each role; without results it returns status ``not_run``
with a reason. Always labelled as simulated participants; it NEVER feeds the live ``study`` section (that stays not_run until people do the live study)."""
from __future__ import annotations

import json
from pathlib import Path

from . import LABEL, ROLES

RESULTS = Path(__file__).resolve().parent / "results"
NOT_RUN_REASON = ("The simulated role studies have not been run. They need the lead's GO and a budget, and a feasibility pilot that shows a usable participant option. "
                  "They never stand in for the live study with people.")


def evaluate_study_roles(results_dir: Path | None = None) -> dict:
    root = Path(results_dir) if results_dir else RESULTS
    roles: dict[str, dict] = {}
    for role in ROLES:
        p = root / role / "summary.json"
        if p.exists():
            try:
                d = json.loads(p.read_text())
                d["label"] = LABEL
                roles[role] = d
            except (OSError, ValueError):
                continue
    pilots: dict[str, dict] = {}
    for role in ROLES:
        for pf in sorted((root / role).glob("PILOT_*.json")) if (root / role).is_dir() else []:
            try:
                pilots[f"{role}/{pf.stem}"] = json.loads(pf.read_text())
            except (OSError, ValueError):
                continue
    if not roles:
        return {"status": "not_run", "reason": NOT_RUN_REASON, "label": LABEL, "roles": {}, "pilots": pilots,
                "meta": {"origin": "simulated_llm", "n": 0, "n_unit": "silicon participants", "label": LABEL, "interval_level": 0.95,
                         "note": "Never feeds the live `study` section; not people."}}
    status = "ok" if all(r.get("status") == "ok" for r in roles.values()) else "partial"
    return {"status": status, "reason": "" if status == "ok" else "some roles ended in harness_failure or were not run", "label": LABEL, "roles": roles, "pilots": pilots,
            "meta": {"origin": "simulated_llm", "n": sum(r.get("n", 0) for r in roles.values()), "n_unit": "silicon participants", "label": LABEL, "interval_level": 0.95,
                     "note": "Never feeds the live `study` section; not people."}}
