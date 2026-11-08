"""The live ledger and its routes: the engine's clock stamps every entry, subjects are hashed, origins never mix, scoring refuses when it must."""
from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from understudy_engine.api.app import create_app
from understudy_engine.hrt.live import LiveLedgers


@pytest.fixture()
def live(tmp_path):
    t = {"now": 1_000.0}
    return LiveLedgers(tmp_path / "ledger", clock=lambda: t["now"]), t


def test_the_engine_clock_stamps_predictions_and_outcomes_and_subjects_are_hashed(live, tmp_path):
    led, t = live
    r = led.predict("real", kind="stuck_hazard", subject="alice@example.com", horizon_s=60.0, forecasts={"model": 0.3, "online_base": 0.2}, primary="model", version="v1")
    assert r["made_at"] == 1000.0 and r["pid"] == 0
    t["now"] = 1059.0
    from understudy_engine.hrt.ledger import LedgerError

    with pytest.raises(LedgerError, match="before its horizon"):
        led.resolve("real", 0, 1)
    t["now"] = 1061.0
    assert led.resolve("real", 0, 1)["resolved_at"] == 1061.0
    text = (tmp_path / "ledger" / "real" / "predictions.jsonl").read_text()
    assert "alice" not in text and "example.com" not in text
    again = LiveLedgers(tmp_path / "ledger")                          # a new process reads the same files and the same salt, and the chain verifies
    assert again.salt() == led.salt() and again.summary()["origins"]["real"]["verified"] is True


def test_origins_are_separate_chains_and_never_scored_together(live):
    led, t = live
    led.predict("real", kind="error_risk", subject="c1", horizon_s=5.0, forecasts={"model": 0.2}, primary="model")
    led.predict("synthetic", kind="error_risk", subject="c1", horizon_s=5.0, forecasts={"model": 0.9}, primary="model")
    s = led.summary()["origins"]
    assert s["real"]["kinds"]["error_risk"]["predictions"] == 1 and s["synthetic"]["kinds"]["error_risk"]["predictions"] == 1
    assert s["real"]["head"] != s["synthetic"]["head"]
    from understudy_engine.hrt.ledger import LedgerError

    with pytest.raises(LedgerError, match="origin"):
        led.predict("imaginary", kind="error_risk", subject="c1", horizon_s=5.0, forecasts={"model": 0.2}, primary="model")


def test_scoring_refuses_when_few_are_resolved_and_scores_from_the_record_when_enough_are(live):
    led, t = live
    refused = led.score("real", "stuck_hazard")
    assert refused["status"] == "refused" and "scoring needs" in refused["reason"]
    rng = np.random.default_rng(0)
    for i in range(400):
        t["now"] = 1000.0 + i * 10
        p = float(rng.uniform(0.05, 0.6))
        pid = led.predict("synthetic", kind="stuck_hazard", subject=f"p{i % 8}", horizon_s=5.0, forecasts={"model": p, "online_base": 0.25}, primary="model")["pid"]
        t["now"] += 6
        led.resolve("synthetic", pid, int(rng.random() < p))
    res = led.score("synthetic", "stuck_hazard", B=100)
    assert res["status"] == "ok" and res["n"] == 400 and set(res["predictors"]) == {"model", "online_base"} and res["n_pending"] == 0
    assert res["predictors"]["model"]["log_loss"]["est"] < res["predictors"]["online_base"]["log_loss"]["est"]
    assert "every forecast was written before its outcome" in res["split"]


def _client(tmp_path, monkeypatch, on: bool = True):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_HRT"):
        monkeypatch.delenv(k, raising=False)
    if on:
        monkeypatch.setenv("UNDERSTUDY_X_HRT", "1")
    app = create_app(tmp_path / "data", warm=False)
    return app, TestClient(app)


def test_the_routes_are_off_without_the_flag_and_on_with_it(tmp_path, monkeypatch):
    app, c = _client(tmp_path, monkeypatch, on=False)
    assert c.get("/hrt/ledger").status_code == 404
    assert app.state.extensions["hrt"] is False
    app, c = _client(tmp_path / "b", monkeypatch, on=True)
    assert app.state.extensions["hrt"] is True and app.state.router_status["hrt.routes"] == "included"
    body = c.get("/hrt/ledger").json()["data"]
    assert set(body["origins"]) == {"real", "synthetic"} and body["origins"]["real"]["verified"] is True


def test_post_prediction_then_outcome_through_the_routes_and_the_refusals(tmp_path, monkeypatch):
    app, c = _client(tmp_path, monkeypatch)
    pred = {"origin": "synthetic", "kind": "stuck_hazard", "subject": "someone", "horizon_s": 60, "forecasts": {"model": 0.4, "online_base": 0.2}, "primary": "model", "version": "t"}
    r = c.post("/hrt/ledger/predictions", json=pred)
    assert r.status_code == 200 and r.json()["pid"] == 0 and "made_at" in r.json()
    early = c.post("/hrt/ledger/outcomes", json={"origin": "synthetic", "pid": 0, "outcome": 1})
    assert early.status_code == 422 and early.json()["error"]["code"] == "ledger_refused" and "horizon" in early.json()["error"]["message"]
    assert c.post("/hrt/ledger/predictions", json={**pred, "forecasts": {"model": 1.5}}).status_code == 422
    assert c.post("/hrt/ledger/predictions", json={**pred, "origin": "dreamed"}).status_code == 422
    assert c.post("/hrt/ledger/predictions", json={**pred, "made_at": 5.0}).status_code == 200          # an unknown field is ignored: a caller cannot send a time
    led = json.loads((tmp_path / "data" / "ledger" / "synthetic" / "predictions.jsonl").read_text().splitlines()[1])
    assert led["made_at"] > 1e9
    s = c.get("/hrt/ledger/score", params={"origin": "synthetic", "kind": "stuck_hazard"}).json()["data"]
    assert s["status"] == "refused" and s["n_pending"] == 2
    assert c.get("/hrt/ledger/score", params={"origin": "nope"}).status_code == 422
