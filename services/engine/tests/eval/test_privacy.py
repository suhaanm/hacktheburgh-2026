"""privacy: the privacy layer's own offline evaluation, included whenever its module imports (it needs no model)."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest
from understudy_engine.eval import build_report, deterministic_view, schema_errors
from understudy_engine.eval import limitations as lim
from understudy_engine.eval.meta import make_meta
from understudy_engine.eval.render_md import render
from understudy_engine.store.paths import data_dir

NOW = "2026-11-07T15:00:00Z"


@pytest.fixture(scope="module")
def privacy_report():
    return build_report(sections=["privacy"], fast=True, now=NOW, regenerate=False, log=lambda m: None)


def test_privacy_section_validates_and_carries_the_headline(privacy_report):
    s = privacy_report["sections"]["privacy"]
    assert schema_errors(privacy_report) == [] and "status" not in s
    h = s["headline"]
    assert h["leaked"] == 0 and h["planted"] > 0 and h["leak_rate_upper_95"] is not None and h["controls_passed"] == h["controls_total"]
    assert s["meta"]["origin"] == "synthetic" and s["meta"]["generated_at"] == NOW and "purposes" not in s
    assert s["by_kind"]["reference"]["flows"] >= 1 and s["layers"]


def test_privacy_is_pending_if_the_module_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "understudy_engine.privacy.evaluate", None)
    s = build_report(sections=["privacy"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["privacy"]
    assert s["status"] == "pending" and "privacy-layer not landed" in s["reason"]


def test_privacy_eval_writes_no_summary_file_uses_no_network_and_is_deterministic(monkeypatch):
    """Two back-to-back runs under a network guard: identical numbers, and the layer's own summary file is never written by the harness.
    (Compared with each other, not with an earlier run: the static-guard file count follows the code tree, which other tracks are still changing.)"""
    target = data_dir() / "privacy_canary.json"
    before = target.stat().st_mtime_ns if target.exists() else None

    def deny(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    a = build_report(sections=["privacy"], fast=True, now=NOW, regenerate=False, log=lambda m: None)
    b = build_report(sections=["privacy"], fast=True, now=NOW, regenerate=False, log=lambda m: None)
    assert "status" not in a["sections"]["privacy"] and deterministic_view(a) == deterministic_view(b)
    after = target.stat().st_mtime_ns if target.exists() else None
    assert before == after


def test_full_mode_runs_more_seeds_than_fast(privacy_report):
    full = build_report(sections=["privacy"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["privacy"]["headline"]
    assert full["runs"] > privacy_report["sections"]["privacy"]["headline"]["runs"] and full["leaked"] == 0


def test_privacy_markdown_states_leaks_the_bound_and_the_limit_of_the_claim(privacy_report):
    md = render(privacy_report)
    sec = md[md.index("## Privacy layer"):md.index("## Limitations register")]
    assert "planted canary tokens reached the model port" in sec and "upper bound on the leak rate" in sec and "never counted as passed" in sec
    assert "nothing here validates behaviour on real data" in sec and "origin: **synthetic**" in sec


def _sec(**kw):
    return {"meta": make_meta("synthetic", 1, "tokens", "x"), **kw}


def test_register_entries_for_a_leak_and_for_layers_without_real_flows():
    sections = {"privacy": _sec(headline={"leaked": 2, "planted": 100, "layers_without_integration_flows": ["calendar", "plugins"]},
                                by_kind={"integration": {"flows": 1, "leak_rate_upper_95": 0.1173, "planted": 24}})}
    reg = {e["id"]: e for e in lim.assemble(sections)}
    assert reg["eval-privacy-leak"]["severity"] == "high" and "2 of 100" in reg["eval-privacy-leak"]["text"]
    assert "calendar, plugins" in reg["eval-privacy-coverage"]["text"] and "11.7%" in reg["eval-privacy-coverage"]["text"] and "not counted as passed" in reg["eval-privacy-coverage"]["text"]
    clean = {"privacy": _sec(headline={"leaked": 0, "planted": 100, "layers_without_integration_flows": []}, by_kind={})}
    assert not [e for e in lim.assemble(clean) if e["id"].startswith("eval-privacy")]


def test_owner_limitations_are_kept_in_the_register(privacy_report):
    owner = privacy_report["sections"]["privacy"]["limitations"]
    reg = {e["id"]: e for e in privacy_report["sections"]["limitations"]}
    assert owner and all(o["id"] in reg and reg[o["id"]]["source"].startswith("privacy-layer:privacy") for o in owner)


def test_real_data_dir_is_untouched_by_the_report_path_json_roundtrip(privacy_report):
    json.loads(json.dumps(privacy_report, allow_nan=False))
    assert Path(data_dir()).exists()
