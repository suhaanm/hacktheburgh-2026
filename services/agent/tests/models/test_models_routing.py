"""Role routing by code: escalation, fallback, deadline, breaker, meter, config. Everything runs on fake backends and a fake clock."""
from __future__ import annotations

import json

import pytest
from understudy_engine.privacy import egress, ledger
from understudy_engine.privacy.image import ImageGate

from understudy_agent.models.config import ConfigError
from understudy_agent.models.errors import SchemaViolation
from understudy_agent.models.gemini_http import GeminiHTTPError
from understudy_agent.models.meter import Meter
from understudy_agent.models.routing import ModelRouter, RoleRoute, RoutingConfig, Step

from .helpers import POINT_NONE, POINT_OK, Clock, FakeBackend, make_image, sandbox_gate

GLANCE = {"app_kind": "browser", "task_phase": "entering", "blocker": "none", "confidence": 0.9}


def router(gem=None, oa=None, *, clock=None, config=None, meter=None) -> ModelRouter:
    backends = {}
    if gem is not None:
        backends["gemini"] = gem
    if oa is not None:
        backends["openai"] = oa
    return ModelRouter(config=config, backends=backends, meter=meter or Meter(), clock=clock or Clock())


def gem(script, **kw) -> FakeBackend:
    return FakeBackend("gemini", script, **kw)


def oai(script, **kw) -> FakeBackend:
    return FakeBackend("openai", script, models={"fast": "openai-fast", "accurate": "openai-fast"}, **kw)


def test_confident_find_uses_only_the_fast_model():
    g = gem({"fast": [POINT_OK], "accurate": []})
    r = router(g).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "answered" and r.value.found and not r.escalated and not r.weak
    assert [c["tier"] for c in g.calls] == ["fast"]
    assert len([x for x in ledger.read_all() if x.get("kind") == "image"]) == 1


def test_not_found_escalates_to_the_accurate_model_with_the_same_frame():
    g = gem({"fast": [POINT_NONE], "accurate": [POINT_OK]})
    img = make_image("point")
    r = router(g).point(img, "submit", gate=sandbox_gate())
    assert r.outcome == "answered" and r.value.found and r.escalated
    assert [c["tier"] for c in g.calls] == ["fast", "accurate"]
    assert g.calls[0]["n_bytes"] == g.calls[1]["n_bytes"] > 0
    assert img.released
    assert len([x for x in ledger.read_all() if x.get("kind") == "image"]) == 2          # one ledger row per send


def test_low_confidence_escalates_and_final_weakness_is_reported():
    g = gem({"fast": [{"found": True, "confidence": 0.5, "box_2d": [10, 10, 60, 90]}],
             "accurate": [{"found": True, "confidence": 0.6, "box_2d": [10, 10, 60, 90]}]})
    r = router(g).point(make_image("point"), "next", gate=sandbox_gate())
    assert r.escalated and r.value.found and r.weak           # best available answer, flagged as under the bar


def test_confidence_bar_is_exactly_at_the_configured_value():
    ok = {"found": True, "confidence": 0.7, "box_2d": [10, 10, 60, 90]}
    g = gem({"fast": [ok], "accurate": []})
    r = router(g).point(make_image("point"), "next", gate=sandbox_gate())
    assert not r.escalated and not r.weak                    # 0.7 is not under 0.7


def test_schema_failure_and_timeout_escalate():
    g = gem({"fast": [SchemaViolation("bad")], "accurate": [POINT_OK]})
    r = router(g).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.escalated and r.value.found and r.attempts[0].error_kind == "schema"
    g = gem({"fast": [GeminiHTTPError("timeout", "slow")], "accurate": [POINT_OK]})
    r = router(g).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.escalated and r.value.found and r.attempts[0].error_kind == "timeout"


def test_hard_error_skips_the_sibling_model_and_falls_back_to_openai():
    g = gem({"fast": [GeminiHTTPError("auth", "no")], "accurate": []})
    o = oai({"fast": [POINT_OK]})
    r = router(g, o).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "answered" and r.value.found
    assert [c["tier"] for c in g.calls] == ["fast"] and len(o.calls) == 1
    assert [(a.provider, a.status) for a in r.attempts] == [("gemini", "failed"), ("openai", "ok")]   # the sibling is never tried


def test_not_found_does_not_trigger_the_openai_fallback():
    g = gem({"fast": [POINT_NONE], "accurate": [POINT_NONE]})
    o = oai({"fast": []})
    r = router(g, o).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "answered" and not r.value.found and r.value.reason == "model_not_found" and o.calls == []


def test_unconfigured_provider_is_skipped_and_all_unavailable_is_reported():
    r = router(gem({"fast": []}, available=False), oai({"fast": []}, available=False)).point(
        make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "unavailable" and not r.value.found and r.value.reason == "unavailable"
    assert {a.skipped_reason for a in r.attempts} == {"not_configured"}
    v = router(gem({"fast": []}, available=False)).verify(make_image("verify"), "page_shows_result", gate=sandbox_gate())
    assert v.value == {"verdict": "unsure", "confidence": 0.0}      # a missing answer is never a tick
    g = router(gem({"fast": []}, available=False)).glance(make_image("glance"), gate=sandbox_gate())
    assert g.value.app_kind == "unknown" and g.value.blocker == "unknown"


def test_hard_deadline_stops_escalation():
    clock = Clock()
    g = gem({"fast": [("clock", 5.9, POINT_NONE)], "accurate": [POINT_OK]}, clock=clock)
    r = router(g, clock=clock).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "answered" and not r.value.found and [c["tier"] for c in g.calls] == ["fast"]
    assert r.attempts[1].skipped_reason == "deadline"


def test_deadline_with_no_answer_is_a_timeout_outcome():
    clock = Clock()

    class Slow(FakeBackend):
        def vision(self, *a, **kw):
            clock.advance(6.0)
            raise GeminiHTTPError("timeout", "slow")

    g = Slow("gemini", {"fast": [], "accurate": []})
    r = router(g, clock=clock).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "timeout" and not r.value.found and r.value.reason == "timeout"


def test_per_call_timeout_is_capped_by_the_remaining_deadline():
    clock = Clock()
    g = gem({"fast": [("clock", 4.0, POINT_NONE)], "accurate": [POINT_OK]}, clock=clock)
    router(g, clock=clock).point(make_image("point"), "submit", gate=sandbox_gate())
    assert g.calls[0]["timeout_s"] == pytest.approx(6.0) and g.calls[1]["timeout_s"] == pytest.approx(2.0)


def test_circuit_breaker_opens_after_three_failures_then_half_opens():
    clock = Clock()
    err = GeminiHTTPError("api", "boom")
    g = gem({"fast": [err, err, err, POINT_OK], "accurate": []})
    o = oai({"fast": [POINT_OK, POINT_OK, POINT_OK, POINT_OK]})
    r = router(g, o, clock=clock)
    for _ in range(3):
        assert r.point(make_image("point"), "submit", gate=sandbox_gate()).value.found       # each falls back to OpenAI
    assert r.breakers["gemini"].state == "open"
    res = r.point(make_image("point"), "submit", gate=sandbox_gate())
    assert res.attempts[0].skipped_reason == "breaker_open" and len(g.calls) == 3             # gemini was not called at all
    clock.advance(61)
    assert r.breakers["gemini"].state == "half_open"
    res = r.point(make_image("point"), "submit", gate=sandbox_gate())                         # the single probe goes to gemini
    assert len(g.calls) == 4 and res.attempts[0].status == "ok"
    assert r.breakers["gemini"].state == "closed"


def test_failures_older_than_the_window_do_not_open_the_breaker():
    clock = Clock()
    err = GeminiHTTPError("api", "boom")
    g = gem({"fast": [err, err, err], "accurate": []})
    r = router(g, oai({"fast": [POINT_OK] * 3}), clock=clock)
    r.point(make_image("point"), "submit", gate=sandbox_gate())
    clock.advance(40)
    r.point(make_image("point"), "submit", gate=sandbox_gate())
    clock.advance(40)       # the first failure is now 80 s old
    r.point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.breakers["gemini"].state == "closed"


def test_closed_gate_propagates_and_sends_nothing():
    g = gem({"fast": []})
    r = router(g)
    gate = ImageGate(consent=False, denylisted_app=False, secure_input=False, unattended=False, source="real_screen")
    img = make_image("glance", source="real_screen")
    with pytest.raises(egress.ImageBlocked):
        r.glance(img, gate=gate)
    assert g.calls == [] and r.breakers["gemini"].snapshot()["recent_failures"] == 0 and img.released
    blocked = [x for x in ledger.read_all() if x.get("status") == "blocked"]
    assert len(blocked) == 1


def test_unattended_real_screen_never_sends():
    g = gem({"fast": []})
    gate = ImageGate(consent=True, denylisted_app=False, secure_input=False, unattended=True, source="real_screen")
    with pytest.raises(egress.ImageBlocked) as e:
        router(g).glance(make_image("glance", source="real_screen"), gate=gate)
    assert e.value.reason == "unattended" and g.calls == []


def test_ledger_failure_means_no_call(monkeypatch):
    def boom(entry):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "begin_image", boom)
    g = gem({"fast": [POINT_OK]})
    with pytest.raises(egress.EgressUnavailable):
        router(g).point(make_image("point"), "submit", gate=sandbox_gate())
    assert g.calls == []


def test_meter_records_every_call_without_pixels(tmp_path):
    path = tmp_path / "meter.jsonl"
    m = Meter(path=path)
    g = gem({"fast": [POINT_NONE], "accurate": [POINT_OK]})
    img = make_image("point")
    sha = img.sha8
    router(g, meter=m).point(img, "submit", gate=sandbox_gate())
    recs = m.records()
    assert [(x["role"], x["provider"], x["model"], x["tier"], x["ok"], x["step"]) for x in recs] == [
        ("point", "gemini", "gemini-fast", "fast", True, 0), ("point", "gemini", "gemini-accurate", "accurate", True, 1)]
    assert recs[0]["input_tokens"] == 1000 and recs[0]["output_tokens"] == 40 and recs[0]["cost_usd"] > 0
    assert recs[0]["latency_ms"] is not None and recs[0]["image_sha"] == sha
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert len(lines) == 2 and "/9j/" not in path.read_text() and "base64" not in path.read_text()
    rows = m.summary()
    assert rows[0]["n"] == 1 and rows[0]["p50_ms"] is not None and m.total_cost_usd() > 0


def test_meter_records_failures_with_the_error_kind():
    m = Meter()
    g = gem({"fast": [GeminiHTTPError("rate_limit", "429")], "accurate": []})
    router(g, oai({"fast": [POINT_OK]}), meter=m).point(make_image("point"), "submit", gate=sandbox_gate())
    assert [(x["provider"], x["ok"], x["error_kind"]) for x in m.records()] == [("gemini", False, "rate_limit"), ("openai", True, None)]


def test_verify_unsure_escalates_but_yes_does_not():
    g = gem({"fast": [{"verdict": "unsure", "confidence": 0.4}], "accurate": [{"verdict": "yes", "confidence": 0.9}]})
    r = router(g).verify(make_image("verify"), "page_shows_result", gate=sandbox_gate())
    assert r.escalated and r.value["verdict"] == "yes"
    g = gem({"fast": [{"verdict": "yes", "confidence": 0.95}], "accurate": []})
    assert not router(g).verify(make_image("verify"), "page_shows_result", gate=sandbox_gate()).escalated


def test_glance_does_not_escalate_on_confidence_by_default():
    g = gem({"fast": [{**GLANCE, "confidence": 0.1}], "accurate": []})
    r = router(g).glance(make_image("glance"), gate=sandbox_gate())
    assert not r.escalated and r.value.app_kind == "browser" and not r.weak       # the glance bar is off (0.0)


def test_prompt_carries_the_format_note_and_the_closed_schema():
    g = gem({"fast": [POINT_OK], "accurate": []})
    router(g).point(make_image("point"), "submit", gate=sandbox_gate())
    c = g.calls[0]
    assert "submit = the main button" in c["prompt"] and "[ymin, xmin, ymax, xmax]" in c["prompt"]
    assert '"step":"submit"' in c["prompt"].replace(" ", "")
    assert c["schema"]["additionalProperties"] is False


def test_mock_mode_never_reaches_a_backend(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    g = gem({"fast": [POINT_OK]})
    r = router(g).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.outcome == "unavailable" and g.calls == [] and {a.skipped_reason for a in r.attempts} == {"mock_mode"}


# ------------------------------------------------------------------------------------------------ config as data
def test_default_routing_table_is_the_plan():
    cfg = RoutingConfig()
    p = cfg.roles["point"]
    assert [(s.provider, s.tier, s.when) for s in p.steps] == [("gemini", "fast", "primary"), ("gemini", "accurate", "escalate"),
                                                              ("openai", "fast", "fallback")]
    assert p.confidence_below == 0.7 and p.deadline_s == 6.0 and p.call_timeout_s == 6.0
    assert (cfg.breaker_failures, cfg.breaker_window_s, cfg.breaker_open_s) == (3, 60.0, 60.0)


def test_yaml_roundtrip_and_override(tmp_path, monkeypatch):
    cfg = RoutingConfig()
    back = RoutingConfig.from_dict(__import__("yaml").safe_load(cfg.to_yaml()))
    assert back.to_dict() == cfg.to_dict()
    f = tmp_path / "models.yaml"
    f.write_text("roles:\n  point:\n    steps:\n      - {provider: openai, tier: fast, when: primary}\n"
                 "    escalate: {confidence_below: 0.9}\n    deadline_s: 3\nbreaker: {failures: 5}\n")
    monkeypatch.setenv("UNDERSTUDY_MODELS_YAML", str(f))
    c2 = RoutingConfig.from_env()
    assert [s.provider for s in c2.roles["point"].steps] == ["openai"] and c2.roles["point"].confidence_below == 0.9
    assert c2.roles["point"].deadline_s == 3.0 and c2.breaker_failures == 5
    assert c2.roles["glance"].steps == RoutingConfig().roles["glance"].steps      # roles not named keep their defaults


@pytest.mark.parametrize("text", [
    "roles:\n  nonsense:\n    steps: [{provider: gemini, tier: fast}]\n",
    "roles:\n  point:\n    steps: [{provider: gemini, tier: fast, when: escalate}]\n",
    "roles:\n  point:\n    steps: [{provider: acme, tier: fast}]\n",
    "- not a mapping\n",
])
def test_bad_routing_config_is_a_config_error(tmp_path, text):
    f = tmp_path / "bad.yaml"
    f.write_text(text)
    with pytest.raises(ConfigError):
        RoutingConfig.from_yaml(f)


def test_custom_route_can_make_openai_primary():
    cfg = RoutingConfig(roles={**RoutingConfig().roles, "point": RoleRoute("point", (Step("openai", "fast", "primary"),))})
    o = oai({"fast": [POINT_OK]})
    g = gem({"fast": []})
    r = router(g, o, config=cfg).point(make_image("point"), "submit", gate=sandbox_gate())
    assert r.value.found and g.calls == [] and len(o.calls) == 1
