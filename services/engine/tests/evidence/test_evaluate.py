"""evaluate_evidence: fast, offline, deterministic; the numbers the eval harness reads."""
from __future__ import annotations

import json
import time

from understudy_engine.evidence import evaluate_evidence
from understudy_engine.evidence import evaluate as EV
from understudy_engine.evidence import fakes as F


def test_fast_evaluation_shape_and_headline_numbers():
    t0 = time.time()
    r = evaluate_evidence(fast=True)
    assert time.time() - t0 < 120                    # about 10 s on an idle laptop; the bound only guards against a runaway under load
    assert r["elapsed_s"] < 120
    assert r["status"] == "ok" and r["meta"]["origin"] == "synthetic" and r["meta"]["n"] == 32 and r["meta"]["n_unit"] == "episodes"
    p = r["packets"]
    assert p["n"] == 32 and p["json_schema"]["rate"] == 1.0 and p["typed_roundtrip"]["rate"] == 1.0 and p["privacy_backstop"]["rate"] == 1.0
    assert p["request_bytes_max"] < 8192
    assert r["templates"]["pass"]["rate"] == 1.0
    f = r["faithful"]
    assert f["pass"]["n"] >= 300 and f["false_reject_rate"] < 0.01 and f["pass"]["ci"][0] > 0.95
    assert r["faithful_paraphrase"]["pass"]["n"] >= 90 and r["faithful_paraphrase"]["false_reject_rate"] < 0.05
    a = r["adversarial"]
    assert set(a["by_kind"]) == set(F.KINDS) and a["kinds_never_applicable"] == []
    assert a["overall"]["rejected"]["rate"] == 1.0 and a["overall"]["rejected"]["ci"][0] > 0.99
    assert a["overall"]["right_reason"]["rate"] > 0.98
    fb = r["fallback"]
    assert fb["faithful_fake"]["by_source"] == {"local": 8} and fb["no_model_mock"]["by_source"] == {"template": 8}
    assert fb["adversarial_fake"]["template_rate"]["rate"] == 1.0
    assert r["live"]["status"] == "not_run"
    assert {x["id"] for x in r["limitations"]} >= {"explainer_readability_not_accuracy", "faithful_fake_is_ours", "adversarial_set_is_ours"}
    json.dumps(r)                                                                  # JSON-ready


def test_the_evaluation_is_deterministic():
    a = evaluate_evidence(fast=True, seed=3, with_live=False)
    b = evaluate_evidence(fast=True, seed=3, with_live=False)
    for k in ("packets", "templates", "faithful", "faithful_paraphrase", "adversarial", "fallback"):
        assert a[k] == b[k], k


def test_live_is_off_unless_asked_and_cloud_is_never_in_the_default_run(monkeypatch):
    assert EV._live([], 0)["status"] == "not_run"
    monkeypatch.setenv("UNDERSTUDY_EVIDENCE_LIVE", "cloud")
    r = EV._live([], 0)
    assert r["status"] == "not_run" and "ask the owner" in r["reason"]
    monkeypatch.setenv("UNDERSTUDY_EVIDENCE_LIVE", "local")
    assert EV._live([], 0)["status"] == "not_run"                      # mock mode: the local model is not available


def test_live_cloud_has_a_hard_budget(packets):
    from understudy_engine.privacy.testing import CapturingPort

    cohort = [("p", "t", pk) for pk in packets]
    out = EV.live_cloud(CapturingPort(), cohort, max_calls=500, est_usd_per_call=0.002)
    assert out["n_replies"] <= 250 and out["est_cost_usd"] <= EV.LIVE_BUDGET_USD
