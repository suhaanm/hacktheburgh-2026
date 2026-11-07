"""Boot check for both providers, `models_status()`, the meter and prices."""
from __future__ import annotations

import json

import pytest

from understudy_agent.models import boot_check, gemini_boot_check
from understudy_agent.models.boot import LAST_BOOT, main
from understudy_agent.models.meter import CallRecord, Meter
from understudy_agent.models.prices import assumptions, cost_estimate, price_for
from understudy_agent.models.redact import contains_secret
from understudy_agent.models.routing import ModelRouter
from understudy_agent.models.status import models_status

from .conftest import FAKE_GEMINI_KEY
from .helpers import Clock, FakeBackend

USABLE = {
    "test-fast": ["generateContent"], "test-accurate": ["generateContent"], "test-live": ["bidiGenerateContent"],
    "gemini-other-flash": ["generateContent"], "gemini-other-live": ["bidiGenerateContent"], "text-embedding": ["embedContent"],
}


class ListClient:
    def __init__(self, models=USABLE, exc=None):
        self.models, self.exc, self.calls = models, exc, 0

    def list_models(self):
        self.calls += 1
        if self.exc:
            raise self.exc
        return dict(self.models)


def test_gemini_boot_ok(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_LIVE", "test-live")
    lines = []
    rep = gemini_boot_check(client=ListClient(), out=lines.append)
    assert rep.ok and rep.provider == "gemini" and rep.configured == {"fast": "test-fast", "accurate": "test-accurate", "live": "test-live"}
    assert LAST_BOOT["gemini"]["ok"] is True


def test_gemini_boot_wrong_id_fails_loudly_with_the_usable_list():
    monkeypatch_models = dict(USABLE)
    del monkeypatch_models["test-accurate"]
    lines = []
    with pytest.raises(SystemExit) as e:
        gemini_boot_check(client=ListClient(monkeypatch_models), out=lines.append)
    msg = str(e.value)
    assert "GEMINI_MODEL_ACCURATE=test-accurate" in msg and "gemini-other-flash" in msg and "gemini-other-live" in msg
    assert "never guessed" in msg and "text-embedding" not in msg and not contains_secret(msg)
    assert lines and lines[0].startswith("The key cannot use")


def test_gemini_boot_not_raising_returns_report(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_LIVE", "not-there")
    rep = gemini_boot_check(client=ListClient(), raise_on_fail=False, out=lambda s: None)
    assert not rep.ok and rep.missing == {"live": "not-there"} and "GEMINI_MODEL_LIVE=not-there" in rep.message


def test_gemini_boot_checks_the_method_each_role_needs(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_LIVE", "test-fast")        # a flash id is not a live model
    rep = gemini_boot_check(client=ListClient(), raise_on_fail=False, out=lambda s: None)
    assert not rep.ok and "needs bidiGenerateContent" in rep.message


def test_gemini_boot_missing_config_and_key(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL_FAST")
    rep = gemini_boot_check(client=ListClient(), raise_on_fail=False, out=lambda s: None)
    assert not rep.ok and "GEMINI_MODEL_FAST" in rep.message
    monkeypatch.setenv("GEMINI_MODEL_FAST", "test-fast")
    monkeypatch.delenv("GEMINI_API_KEY")
    rep = gemini_boot_check(raise_on_fail=False, out=lambda s: None)      # real client path: no key
    assert not rep.ok and "GEMINI_API_KEY" in rep.message


def test_gemini_boot_listing_failure_never_leaks_the_key():
    from understudy_agent.models.gemini_http import GeminiHTTPError

    rep = gemini_boot_check(client=ListClient(exc=GeminiHTTPError("auth", f"gemini auth (HTTP 403): bad key {FAKE_GEMINI_KEY}")),
                            raise_on_fail=False, out=lambda s: None)
    assert not rep.ok and "Could not list Gemini models" in rep.message and not contains_secret(rep.message)


def test_boot_check_mock_makes_no_gemini_call(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X_GEMINI", "1")
    c = ListClient()
    assert boot_check(client=object(), gemini_client=c).mock and c.calls == 0


class OpenAIList:
    def __init__(self):
        self.models = type("M", (), {"list": lambda s: type("R", (), {"data": [type("D", (), {"id": i})() for i in
                                                                               ("test-planner", "test-openai-fast", "test-computer")]})()})()


def test_boot_check_runs_gemini_only_when_the_flag_is_on(monkeypatch):
    c = ListClient()
    boot_check(client=OpenAIList(), gemini_client=c, out=lambda s: None)
    assert c.calls == 0                                           # flag off: nothing about Gemini runs
    monkeypatch.setenv("UNDERSTUDY_X_GEMINI", "1")
    boot_check(client=OpenAIList(), gemini_client=c, out=lambda s: None)
    assert c.calls == 1
    bad = dict(USABLE)
    del bad["test-fast"]
    with pytest.raises(SystemExit):
        boot_check(client=OpenAIList(), gemini_client=ListClient(bad), out=lambda s: None)


def test_cli_main_reports_both_providers(monkeypatch, capsys):
    import understudy_agent.models.boot as boot

    monkeypatch.setattr(boot, "_openai_boot_check", lambda **kw: boot.BootReport(ok=True, mock=False, configured={"fast": "x"}, usable=["gpt-x"]))
    monkeypatch.setattr(boot, "gemini_boot_check", lambda **kw: boot.BootReport(ok=False, mock=False, provider="gemini", message="no"))
    assert main(["--list"]) == 1
    out = capsys.readouterr().out
    assert "openai:" in out and "gemini:" in out and FAKE_GEMINI_KEY not in out


# ------------------------------------------------------------------------------------------------ status, meter, prices
def test_models_status_shape_and_no_secrets(monkeypatch):
    m = Meter()
    g = FakeBackend("gemini", {"fast": [], "accurate": []})
    r = ModelRouter(backends={"gemini": g}, meter=m, clock=Clock())
    m.record(CallRecord(role="point", provider="gemini", model="test-fast", tier="fast", method="point", ok=True, latency_ms=900,
                        input_tokens=1200, output_tokens=40, cost_usd=0.0005))
    st = models_status(r)
    text = json.dumps(st)
    assert not contains_secret(text) and FAKE_GEMINI_KEY not in text and "sk-test" not in text
    assert set(st["roles"]) == {"point", "glance", "verify"}
    assert st["roles"]["point"]["steps"][0] == {"provider": "gemini", "tier": "fast", "when": "primary", "model": "test-fast"}
    assert st["providers"]["gemini"]["models"]["accurate"] == "test-accurate" and st["providers"]["gemini"]["configured"] is True
    assert st["providers"]["gemini"]["health"] == "ok" and st["providers"]["openai"]["health"] == "unknown"
    assert st["providers"]["gemini"]["breaker"]["state"] == "closed"
    assert st["last_latencies_ms"] == {"gemini:test-fast": [900]} and st["prices_assumed"]["gemini.fast"]["source"] == "assumed_default"


def test_status_health_follows_breaker_and_failures():
    m = Meter()
    r = ModelRouter(backends={}, meter=m, clock=Clock())
    for _ in range(6):
        m.record(CallRecord(role="point", provider="gemini", model="x", tier="fast", method="point", ok=False, latency_ms=10,
                            error_kind="api"))
    assert models_status(r)["providers"]["gemini"]["health"] == "degraded"
    for _ in range(3):
        r.breakers["gemini"].record(False)
    assert models_status(r)["providers"]["gemini"]["health"] == "down"


def test_status_without_a_router_makes_no_network_call_and_reports_config_error(tmp_path, monkeypatch):
    f = tmp_path / "bad.yaml"
    f.write_text("- nope\n")
    monkeypatch.setenv("UNDERSTUDY_MODELS_YAML", str(f))
    from understudy_agent.models import routing

    routing.reset_router()
    st = models_status()
    assert st["config_error"] and "mapping" in st["config_error"]


def test_prices_env_override_and_labels(monkeypatch):
    assert price_for("gemini", "fast").source == "assumed_default"
    monkeypatch.setenv("UNDERSTUDY_PRICE_GEMINI_FAST_IN", "0.1")
    monkeypatch.setenv("UNDERSTUDY_PRICE_GEMINI_FAST_OUT", "0.4")
    p = price_for("gemini", "fast")
    assert (p.in_per_m, p.out_per_m, p.source) == (0.1, 0.4, "env")
    assert cost_estimate("gemini", "fast", 1_000_000, 1_000_000) == pytest.approx(0.5)
    assert cost_estimate("gemini", "fast", None, 5) is None
    assert "openai.fast" in assumptions()


def test_meter_percentiles_and_totals():
    m = Meter()
    for ms in (100, 200, 300, 400, 1000):
        m.record(CallRecord(role="point", provider="gemini", model="a", tier="fast", method="point", ok=True, latency_ms=ms,
                            input_tokens=10, output_tokens=2, thought_tokens=3, cost_usd=0.001))
    m.record(CallRecord(role="point", provider="gemini", model="a", tier="fast", method="point", ok=False, latency_ms=5000))
    row = m.summary()[0]
    assert row["n"] == 6 and row["ok"] == 5 and row["failed"] == 1 and row["p50_ms"] == 300 and row["p95_ms"] == 1000
    assert row["output_tokens"] == 25 and m.total_cost_usd() == pytest.approx(0.005)
