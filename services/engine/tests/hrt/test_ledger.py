"""The prospective ledger: what it records, what it refuses, and that an edit is caught (PLAN.md section 3.1)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from understudy_engine.hrt.ledger import MIN_RESOLVED, Ledger, LedgerError, stream_key


def _filled(n: int = 300, kind: str = "stuck_hazard", seed: int = 0) -> Ledger:
    rng = np.random.default_rng(seed)
    led = Ledger()
    for i in range(n):
        s = f"s{i % 3}"
        led.predict(kind=kind, stream=s, made_at=float(i), horizon_s=60.0, forecasts={"model": float(rng.uniform(0.05, 0.95)), "base": 0.3}, primary="model", version="v1")
    for pid in range(n):
        led.resolve(pid, resolved_at=float(pid) + 60.0, outcome=int(rng.random() < 0.3))
    return led


def test_prediction_is_recorded_before_its_outcome_and_chain_verifies():
    led = Ledger()
    pid = led.predict(kind="stuck_hazard", stream="a", made_at=10.0, horizon_s=60.0, forecasts={"model": 0.4, "base": 0.3}, primary="model")
    assert led.pending("stuck_hazard") == 1 and led.n_predictions() == 1
    led.resolve(pid, resolved_at=70.0, outcome=1)
    assert led.pending("stuck_hazard") == 0
    assert [e["type"] for e in led.entries] == ["prediction", "outcome"]
    assert led.verify() is True


def test_outcome_before_the_horizon_is_refused():
    led = Ledger()
    pid = led.predict(kind="stuck_hazard", stream="a", made_at=10.0, horizon_s=60.0, forecasts={"model": 0.4}, primary="model")
    with pytest.raises(LedgerError, match="before its horizon"):
        led.resolve(pid, resolved_at=69.9, outcome=1)
    assert led.pending("stuck_hazard") == 1             # nothing was written
    assert len(led.entries) == 1


def test_an_outcome_is_written_once_and_only_for_a_known_prediction():
    led = Ledger()
    pid = led.predict(kind="stuck_hazard", stream="a", made_at=0.0, horizon_s=60.0, forecasts={"model": 0.4}, primary="model")
    led.resolve(pid, resolved_at=61.0, outcome=0)
    with pytest.raises(LedgerError, match="already has an outcome"):
        led.resolve(pid, resolved_at=90.0, outcome=1)
    with pytest.raises(LedgerError, match="no prediction"):
        led.resolve(99, resolved_at=90.0, outcome=1)
    with pytest.raises(LedgerError, match="0 or 1"):
        led.predict(kind="stuck_hazard", stream="a", made_at=1.0, horizon_s=60.0, forecasts={"model": 0.4}, primary="model")
        led.resolve(1, resolved_at=100.0, outcome=0.5)


def test_no_backdating_and_forecasts_must_be_probabilities():
    led = Ledger()
    led.predict(kind="stuck_hazard", stream="a", made_at=100.0, horizon_s=60.0, forecasts={"model": 0.4}, primary="model")
    with pytest.raises(LedgerError, match="no backdating"):
        led.predict(kind="stuck_hazard", stream="a", made_at=99.0, horizon_s=60.0, forecasts={"model": 0.4}, primary="model")
    with pytest.raises(LedgerError, match="not a probability"):
        led.predict(kind="stuck_hazard", stream="a", made_at=101.0, horizon_s=60.0, forecasts={"model": 1.2}, primary="model")
    with pytest.raises(LedgerError, match="primary"):
        led.predict(kind="stuck_hazard", stream="a", made_at=101.0, horizon_s=60.0, forecasts={"model": 0.2}, primary="other")
    with pytest.raises(LedgerError, match="unknown kind"):
        led.predict(kind="weather", stream="a", made_at=101.0, horizon_s=60.0, forecasts={"model": 0.2}, primary="model")


def test_editing_an_old_entry_or_removing_one_breaks_the_chain():
    led = _filled(60)
    assert led.verify()
    tampered = Ledger(entries=[dict(e) for e in led.entries])
    tampered.entries[10]["forecasts"] = {"model": 0.01, "base": 0.3}
    with pytest.raises(LedgerError, match="edited"):
        tampered.verify()
    dropped = Ledger(entries=[dict(e) for i, e in enumerate(led.entries) if i != 20])
    with pytest.raises(LedgerError, match="chain is broken"):
        dropped.verify()
    swapped = [dict(e) for e in led.entries]
    swapped[4], swapped[5] = swapped[5], swapped[4]
    with pytest.raises(LedgerError, match="chain is broken"):
        Ledger(entries=swapped).verify()


def test_scoring_refuses_when_too_few_are_resolved_or_a_stream_has_a_gap():
    led = _filled(MIN_RESOLVED - 1)
    with pytest.raises(LedgerError, match="scoring needs"):
        led.resolved("stuck_hazard")
    ok = _filled(300)
    arr = ok.resolved("stuck_hazard")
    assert arr["y"].size == 300 and set(arr["names"]) == {"model", "base"} and arr["n_pending"] == 0
    # a dropped prediction in one stream: rebuild a ledger whose stream s0 skips a sequence number
    gap = Ledger()
    for i in range(300):
        gap.predict(kind="stuck_hazard", stream=f"s{i % 3}", made_at=float(i), horizon_s=60.0, forecasts={"model": 0.3}, primary="model")
        gap.resolve(i, resolved_at=i + 60.0, outcome=0)
    gap.entries[0]["stream_seq"] = 5                   # as if sequence numbers 0..4 of stream s0 never reached the record
    assert gap.gaps("stuck_hazard") == [gap.entries[0]["stream"]]
    with pytest.raises(LedgerError, match="gap"):
        gap.resolved("stuck_hazard")


def test_pending_predictions_are_counted_and_not_scored():
    led = Ledger()
    for i in range(MIN_RESOLVED + 40):
        led.predict(kind="stuck_hazard", stream="a", made_at=float(i), horizon_s=60.0, forecasts={"model": 0.3, "base": 0.3}, primary="model")
    for pid in range(MIN_RESOLVED + 10):
        led.resolve(pid, resolved_at=pid + 61.0, outcome=0)
    r = led.resolved("stuck_hazard")
    assert r["y"].size == MIN_RESOLVED + 10 and r["n_pending"] == 30


def test_resolved_before_is_what_an_online_baseline_may_use():
    led = Ledger()
    ys = [1, 0, 1, 1, 0]
    for i, y in enumerate(ys):
        led.predict(kind="stuck_hazard", stream="a", made_at=float(i * 10), horizon_s=15.0, forecasts={"model": 0.5}, primary="model")
    # resolve out of order on purpose: the prefix sums must still be right
    for i in (2, 0, 1, 4, 3):
        led.resolve(i, resolved_at=i * 10 + 15.0, outcome=ys[i])
    assert led.resolved_before("stuck_hazard", 14.9) == (0, 0.0)
    assert led.resolved_before("stuck_hazard", 15.0) == (1, 1.0)
    assert led.resolved_before("stuck_hazard", 35.0) == (3, 2.0)
    assert led.resolved_before("stuck_hazard", 1e9) == (5, 3.0)


def test_jsonl_round_trip_reverifies_and_detects_edits(tmp_path):
    p = tmp_path / "ledger" / "predictions.jsonl"
    led = Ledger(path=p)
    for i in range(30):
        led.predict(kind="error_risk", stream=stream_key(f"case{i}", "salt"), made_at=float(i), horizon_s=5.0, forecasts={"model": 0.2, "base": 0.1}, primary="model")
    for i in range(0, 30, 2):
        led.resolve(i, resolved_at=i + 5.0, outcome=i % 4 == 0)
    led.close()
    again = Ledger.load(p)
    assert again.head() == led.head() and again.pending("error_risk") == 15 and again.n_predictions("error_risk") == 30
    lines = p.read_text().splitlines()
    row = json.loads(lines[3])
    row["forecasts"] = {"model": 0.9, "base": 0.1}
    lines[3] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerError, match="edited"):
        Ledger.load(p)


def test_the_record_holds_no_text_only_hashes_and_numbers():
    led = Ledger()
    led.predict(kind="stuck_hazard", stream=stream_key("alice@example.com", "salt"), made_at=1.0, horizon_s=60.0, forecasts={"model": 0.3}, primary="model", version="hazard-full-v1")
    blob = json.dumps(led.entries)
    assert "alice" not in blob and "example.com" not in blob
    assert led.summary()["kinds"]["stuck_hazard"] == {"predictions": 1, "resolved": 0, "pending": 1}


def test_time_to_progress_records_a_cdf_and_a_censored_outcome():
    led = Ledger()
    cdf = [0.1, 0.2, 0.35, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]
    for i in range(MIN_RESOLVED):
        pid = led.predict(kind="time_to_progress", stream="a", made_at=float(i), horizon_s=300.0, forecasts={"model": cdf, "km": cdf}, primary="model")
        led.resolve(pid, resolved_at=i + 300.0, outcome={"event_step": 3 if i % 2 else None, "steps_obs": 10 if i % 2 else 6})
    r = led.resolved("time_to_progress")
    assert r["forecasts"]["model"].shape == (MIN_RESOLVED, 10)
    assert set(r["event_step"].tolist()) == {-1, 3} and set(r["steps_obs"].tolist()) == {6, 10}
    with pytest.raises(LedgerError, match="steps_obs"):
        pid = led.predict(kind="time_to_progress", stream="a", made_at=1e6, horizon_s=300.0, forecasts={"model": cdf}, primary="model")
        led.resolve(pid, resolved_at=1e6 + 300, outcome=1)
