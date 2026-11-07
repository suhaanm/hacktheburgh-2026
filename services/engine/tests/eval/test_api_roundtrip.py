"""The engine's GET /eval/report serves exactly what the harness wrote (in-process client, no port)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient
from understudy_engine.api.app import create_app
from understudy_engine.eval import build_report, dumps, schema_errors
from understudy_engine.eval.__main__ import main


def test_report_written_by_the_cli_is_served_unchanged_and_every_section_has_meta(tmp_path, monkeypatch):
    out = tmp_path / "report.json"
    assert main(["--fast", "--no-generate", "--no-md", "--sections", "ski_rental,study,redteam", "--out", str(out)]) in (0, 2)
    monkeypatch.setenv("UNDERSTUDY_EVAL_REPORT", str(out))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    client = TestClient(create_app(tmp_path))
    r = client.get("/eval/report")
    assert r.status_code == 200
    body = r.json()
    assert body == json.loads(out.read_text())
    assert schema_errors(body) == []
    for name, sec in body["sections"].items():
        if name != "limitations":
            assert sec["meta"]["origin"] in ("real", "synthetic", "mixed", "unknown") and sec["meta"]["interval_level"] == 0.95, name


def test_missing_report_is_a_plain_404_with_the_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_EVAL_REPORT", str(tmp_path / "nope.json"))
    r = TestClient(create_app(tmp_path)).get("/eval/report")
    assert r.status_code == 404 and "make eval" in r.json()["error"]["message"]


def test_dumps_is_strict_json():
    rep = build_report(sections=["study"], regenerate=False, log=lambda m: None)
    json.loads(dumps(rep))
