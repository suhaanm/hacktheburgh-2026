import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine.routes_analytics import router
from understudy_engine.store import data_dir

pytestmark = pytest.mark.skipif(not (data_dir() / "synthetic" / "nine-to-five" / "events.jsonl").exists(),
                                reason="synthetic personas not generated")

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
