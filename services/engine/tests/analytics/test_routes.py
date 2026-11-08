import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.routes_analytics import router
from understudy_engine.store import data_dir

pytestmark = pytest.mark.skipif(not (data_dir() / "synthetic" / "nine-to-five" / "events.jsonl").exists(),
                                reason="generated personas not generated")

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_hazard_route_shape_for_a_persona():
    r = client.get("/hazard/p_ninetofive", params={"limit": 50})
    assert r.status_code == 200
    body = r.json()
    meta, data = body["meta"], body["data"]
    assert meta["origin"] == "synthetic" and meta["n"] == 4 and meta["split"] == "leave-one-person-out"
    assert meta["interval_level"] == 0.95 and meta["generated_at"] and meta["note"]
    assert len(data["series"]) == 50 and set(data["series"][0]) == {"t", "p"} and data["series"][0]["t"].endswith("Z")
    assert all(0.0 <= pt["p"] <= 1.0 for pt in data["series"])
    assert set(data["model"]) == {"log_loss", "brier", "ece", "ci_log_loss"}
    assert set(data["baselines"]) == {"base_rate", "time_since_progress"}
    assert data["calibration"] and set(data["calibration"][0]) >= {"p_mean", "freq", "n"}
    assert isinstance(data["false_alarms_per_hour"], float) and data["split"] == "leave-one-person-out"
    assert data["person"]["id"] == "p_ninetofive"


def test_hazard_route_apprentice_and_unknown_person():
    r = client.get("/hazard/p_nov01")
    assert r.status_code == 200 and r.json()["meta"]["n"] == 24
    assert "script" in r.json()["meta"]["note"]
    bad = client.get("/hazard/p_nobody")
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "unknown_person"
    assert "p_ninetofive" in bad.json()["error"]["message"]


def test_analytics_sections_fast_is_quick_complete_and_contract_shaped():
    import json
    import time
    from understudy_engine.routes_analytics import analytics_sections
    t = time.time()
    s = analytics_sections(fast=True)
    assert time.time() - t < 60
    assert {"hazard", "ope", "routing", "agent_claims", "policy_gate", "skills", "limitations"} <= set(s)
    h = s["hazard"]
    assert set(h["model"]) >= {"log_loss", "brier", "ece", "ci_log_loss"} and set(h["baselines"]) == {"base_rate", "time_since_progress"}
    assert h["calibration"] and "false_alarms_per_hour" in h and h["split"] == "leave-one-person-out"
    assert [e["name"] for e in s["ope"]["estimators"]] == ["naive", "ips", "snips", "dr"] and "true_value" in s["ope"]
    r = s["routing"]
    assert all(k in r for k in ("alpha", "curve", "held_out_error", "held_out_ci", "bound_held", "expert_minutes_per_case"))
    c = s["agent_claims"]
    assert c["reliability"] and "brier" in c and "base_rate" in c
    for k in ("hazard", "ope", "routing", "agent_claims", "policy_gate", "skills"):
        assert s[k]["meta"]["origin"] == "synthetic" and s[k]["limitations"], k
        assert all(set(x) == {"id", "text", "severity"} for x in s[k]["limitations"])
    json.dumps(s, default=str)
