"""``study_sim_section()``: the simulated-study section for engine-eval's report. Reads results/summary.json (written by ``python -m
evals.study_sim analyze``); without it, a not_run stub. Always labelled as simulated participants, never the live study."""
from __future__ import annotations

import json
from pathlib import Path

from . import LABEL

RESULTS = Path(__file__).resolve().parent / "results"


def study_sim_section() -> dict:
    p = RESULTS / "summary.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            d["label"] = LABEL
            return d
        except (OSError, ValueError):
            pass
    from .report import LIMITATIONS

    return {"status": "not_run", "label": LABEL, "n": 0, "n_aa": 0, "headline": None, "per_skill": None, "aa": None, "effort": None, "nudges": None,
            "pipeline_checks": None, "cost": {"usd_est": 0.0, "calls": 0, "tokens": {"in": 0, "out": 0}}, "limitations": LIMITATIONS,
            "meta": {"origin": "simulated_llm", "n": 0, "n_unit": "silicon participants", "label": LABEL, "interval_level": 0.95,
                     "note": "The language-model study has not been run. It never stands in for the live study with people."}}
