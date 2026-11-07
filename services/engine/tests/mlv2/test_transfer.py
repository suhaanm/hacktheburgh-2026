"""The M5 loader on a FAKE results directory built in a temp folder (never the real evals/study_sim)."""
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from understudy_engine.mlv2 import splits, transfer


def _write_fake(root: Path, n_people: int = 3, finished: int = 2) -> None:
    from understudy_engine.personas import PERSONAS, simulate_persona

    (root / "checks").mkdir(parents=True)
    (root / "raw").mkdir()
    spec = PERSONAS[0]
    rows_out = []
    for i in range(1, n_people + 1):
        pid = f"p_sim{i:02d}"
        import dataclasses
        run = simulate_persona(dataclasses.replace(spec, seed=900 + i), 2, with_mc=False)
        d = root / "raw" / pid
        d.mkdir()
        with (d / "engine_events.jsonl").open("w") as fh:
            for r in run.rows:
                r = dict(r)
                r["person"] = pid
                r["origin"] = "real"
                fh.write(json.dumps(r) + "\n")
        if i <= finished:
            (root / "checks" / f"{pid}.json").write_text(json.dumps({"participant": pid, "arm": "coached", "exclusion": ""}))
        elif i == finished + 1:
            (root / "checks" / f"{pid}.json").write_text(json.dumps({"participant": pid, "arm": "coached", "exclusion": "harness error"}))
        rows_out.append({"participant": pid, "arm": "coached" if i % 2 else "aa"})
    with (root / "participants.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["participant", "arm"])
        w.writeheader()
        w.writerows(rows_out)


def test_loader_uses_only_finished_participants_and_is_read_only(tmp_path):
    _write_fake(tmp_path, n_people=4, finished=2)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    ids, skipped = transfer.finished_participants(tmp_path)
    assert ids == ["p_sim01", "p_sim02"]
    assert skipped == {"p_sim03": "excluded: harness error"}               # p_sim04 has no checks file at all: still running
    sim = transfer.load_sim(tmp_path)
    assert sim.finished == ids and len(sim.episodes) > 0 and {e.person for e in sim.episodes} == set(ids)
    assert sim.n_progress > 0 and sim.arm["p_sim01"] == "coached" and sim.arm["p_sim02"] == "aa"
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before            # nothing written


def test_loader_tolerates_an_empty_or_missing_results_dir(tmp_path):
    sim = transfer.load_sim(tmp_path)                                          # no checks dir
    assert sim.finished == [] and sim.episodes == []
    from understudy_engine.hazard.features import build_bins
    train = build_bins(splits.load_pool("D0", limit_replicates=0))
    out = transfer.evaluate_transfer(train, sim)
    assert out["status"] == "no_finished_participants" and out["n_participants_finished"] == 0 and out["badge"].startswith("simulated participants")


def test_evaluate_transfer_labels_n_and_models(tmp_path):
    _write_fake(tmp_path, n_people=3, finished=3)
    sim = transfer.load_sim(tmp_path)
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.hazard.sim import simulate_people
    eps, _ = simulate_people(5, 30, seed=2)
    train = build_bins(eps)
    out = transfer.evaluate_transfer(train, sim, primary_spec_id="A1", n_boot=200, inner_folds=3)
    assert out["status"] == "ok" and out["n"] == 3 and out["n_unit"] == "participants" and out["test_only"]
    assert set(out["models"]) >= {"v1", "time_since_progress", "base_rate", "v2"}
    assert "v1_minus_base_rate" in out["paired_log_loss"] and len(out["caveats"]) >= 4
    assert out["genome_comparison"].startswith("not applicable")
    for r in out["alarm_rules"].values():
        assert r["false_alarms_per_hour"]["interval"][0] <= r["false_alarms_per_hour"]["interval"][1]
