import json

import pytest

from understudy_engine.mlv2 import evaluate as EV


def test_fast_mode_section_shape_and_it_never_touches_held_out_or_sim(monkeypatch, tmp_path):
    from understudy_engine.mlv2 import apprentice_pool as AP
    from understudy_engine.mlv2 import splits, transfer

    monkeypatch.setenv("UNDERSTUDY_MLV2_CACHE", str(tmp_path))
    monkeypatch.delenv("UNDERSTUDY_MLV2_HELDOUT", raising=False)
    seen = []
    real_load = splits.load_pool
    real_app = AP.load_pool
    monkeypatch.setattr(splits, "load_pool", lambda pool, **kw: (seen.append(pool), real_load(pool, **kw))[1])
    monkeypatch.setattr(AP, "load_pool", lambda pool, **kw: (seen.append(pool), real_app(pool, **kw))[1])
    monkeypatch.setattr(transfer, "load_sim", lambda *a, **k: pytest.fail("fast mode must not read simulated-participant traces"))
    sec = EV.evaluate_mlv2(fast=True)
    assert set(seen) <= {"D0", "APP-D0"}
    assert sec["mode"] == "fast" and sec["meta"]["origin"] == "synthetic" and sec["meta"]["n_unit"] == "people"
    assert sec["variants_tried"]["total"] == 15 and sec["plan"].endswith("PLAN.md")
    hz = sec["dev"]["hazard_d0"]
    ids = {r["id"] for r in hz["family_a"]}
    assert {"A0", "A1", "A3", "A6", "TSP", "BASE"} <= ids
    assert {r["id"] for r in hz["family_c_on_A0"]} == {"C0", "C1", "C2"}
    gn = sec["dev"]["genome_apprentice_d0"]
    assert {r["id"] for r in gn["family_e"]} == {"E0", "E1", "E2", "E3", "E4"} and {r["id"] for r in gn["family_q"]} == {"Q0", "Q1", "Q1b"}
    assert "heldout" not in sec and any(x["id"] == "mlv2-synthetic" for x in sec["limitations"])
    sc = sec["scorecard"]
    assert sc["accepted"] is False and sc["verdict"] == "not_run" and sc["model_version_shown_as_default"] == "v1"
    assert set(sc["baselines"]) == {"base_rate", "time_since_progress", "v1"} and sc["budget_per_hour"] == 1.0
    for blk in (sc["model"], *sc["baselines"].values()):
        assert set(blk) >= {"log_loss", "brier", "ece", "false_alarms_per_hour", "detection_rate"} and set(blk["log_loss"]) == {"value", "ci"}
    assert sc["tte"] is not None and "c_index" in sc["tte"] and sc["meta"]["pool"].startswith("D0")
    assert any("gap" in c.lower() for c in sec["caveats"])
    json.dumps(sec, default=str)
    # every limitation is a register entry the eval harness accepts
    assert all({"id", "text", "severity"} <= set(x) for x in sec["limitations"])


def test_verdict_table_handles_missing_parts():
    assert EV.verdict_table(None, None, None) == []
