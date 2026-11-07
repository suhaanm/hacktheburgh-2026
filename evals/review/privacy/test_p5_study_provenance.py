"""REVIEW-PRIVACY (honesty): the live-study section is fed from evals/study/results/participants.csv with NO provenance check. The
simulated-participants harness writes the same schema, so copying its CSV into the live study's results folder makes the report show
language-model participants as origin "real" (people). Only summary.json is checked for origin; participants.csv is not.
Hermetic: temp tree, nothing in the repo is changed. Run: .venv/bin/python -m pytest evals/review/privacy/test_p5_study_provenance.py -q -s
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_simulated_csv_in_the_live_results_folder_is_reported_as_real(tmp_path, monkeypatch):
    from understudy_engine.eval import adapters
    sim_csv = REPO / "evals" / "study_sim" / "results" / "participants.csv"
    assert sim_csv.is_file(), "no simulated participants file to test with"
    out = tmp_path / "evals"
    (out / "study" / "results").mkdir(parents=True)
    shutil.copy(REPO / "evals" / "study" / "analyze.py", out / "study" / "analyze.py")
    shutil.copy(REPO / "evals" / "study" / "assignments.json", out / "study" / "assignments.json")
    shutil.copy(sim_csv, out / "study" / "results" / "participants.csv")      # <- what a careless copy or a symlink does
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: out)
    sec = adapters.study(None)
    print("\nlive study section built from the SIMULATED csv: status=%s origin=%s n=%s rows=%d" % (
        sec.get("status"), (sec.get("meta") or {}).get("origin"), sec.get("n"), len(sec.get("rows", []))))
    # REGRESSION FORM: the live section must refuse a results folder without a human-study manifest (landed ~17:46)
    assert sec.get("status") == "not_run" and not sec.get("rows"), f"un-provenanced data was shown as the live study: {sec.get('status')}"
