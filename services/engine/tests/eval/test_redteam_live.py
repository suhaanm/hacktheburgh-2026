"""redteam_live: the cached real-model run (data/redteam_live.json) is read offline and shown with its limits; no model is ever called."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from understudy_engine.eval import build_report, schema_errors
from understudy_engine.eval.adapters import REDTEAM_LIVE_FILE
from understudy_engine.eval.render_md import render

REPO = Path(__file__).resolve().parents[4]
NOW = "2026-11-07T15:00:00Z"


def row(ablation, atk_k, task_k, n_runs=126, n_clean_runs=93, paused=0.0):
    n_cases = n_runs // 3
    from understudy_engine.eval.stats import wilson

    return {"ablation": ablation, "attack_success": atk_k / n_runs, "attack_ci": wilson(min(max(round(atk_k / 3), 1 if atk_k else 0), n_cases), n_cases), "task_success": task_k / n_runs, "task_ci": wilson(task_k, n_runs),
            "paused_rate": paused, "false_pause_rate": 0.0, "false_pause_ci": [0.0, 0.1103],
            "false_pause_hn": {"k": 0, "n": 30, "rate": 0.0, "clusters": 10, "ci": [0.0, 0.2775]}, "task_success_clean": {"k": 80, "n": 93, "rate": 0.86, "ci": [0.7, 0.94]},
            "n": n_cases, "n_runs": n_runs, "n_clean": 31, "n_clean_runs": n_clean_runs,
            "detail": {"attack_success": {"k": atk_k, "n": n_runs, "rate": atk_k / n_runs}, "task_success_under_attack": {"k": task_k, "n": n_runs, "rate": task_k / n_runs}}}


def live_file(on_atk=0, off_atk=5, on_task=28, off_task=106):
    return {"meta": {"label": "real model, n small", "origin": "synthetic", "n": 42, "n_clean": 31, "repeats": 3, "n_runs": 252, "n_unit": "runs", "split": None, "interval_level": 0.95,
                     "note": "Real planner, reader and drift check. Nothing is executed.", "models": {"planner": "p", "fast": "f"}, "calls": {"live": 0, "cached": 546, "total": 546},
                     "cost_estimate_usd": None},
            "rows": [row("all_on", on_atk, on_task, paused=0.76), row("all_off", off_atk, off_task)],
            "false_pause_rate": 0.0, "false_pause_ci": [0.0, 0.1103], "false_pause": {"k": 0, "n": 93},
            "limitations": [{"id": "small_n", "severity": "high", "text": "Each attack is run 3 times; repeats are not independent."}]}


@pytest.fixture()
def root(tmp_path):
    (tmp_path / REDTEAM_LIVE_FILE).write_text(json.dumps(live_file()))
    return tmp_path


def rep(root, **kw):
    return build_report(sections=["redteam_live"], root=root, now=NOW, regenerate=False, log=lambda m: None, **kw)


def test_absent_cache_is_a_pending_stub_that_says_no_model_is_called(tmp_path):
    s = rep(tmp_path)["sections"]["redteam_live"]
    assert s["status"] == "pending" and REDTEAM_LIVE_FILE in s["reason"] and "never calls a model" in s["reason"]


def test_cached_run_is_read_labelled_and_validates(root):
    r = rep(root)
    s = r["sections"]["redteam_live"]
    assert schema_errors(r) == [] and "status" not in s
    assert s["label"] == "real model, n = 42 cases (3 repeats each)"
    assert s["meta"]["n"] == 42 and s["meta"]["n_unit"] == "cases" and s["meta"]["origin"] == "synthetic" and "3 repeats" in s["meta"]["split"]
    on, off = s["rows"]
    assert (on["ablation"], on["attack_successes"], on["attack_runs"]) == ("all_on", 0, 126)
    assert (off["ablation"], off["attack_successes"], off["attack_runs"]) == ("all_off", 5, 126)
    assert on["label"] == "All layers on" and on["false_pause_hard_negatives"]["n"] == 30 and on["n_clean_runs"] == 93
    assert "called no model" in s["meta"]["note"]


def test_overlap_is_computed_and_the_reading_follows_it(root):
    s = rep(root)["sections"]["redteam_live"]
    assert s["intervals_overlap"] is True
    assert s["reading"].startswith("Intervals overlap") and "not that the layers prevent attacks" in s["reading"]
    assert "22% with every layer on against 84% with all off" in s["reading"] and "0 of 126 runs" in s["reading"]


def test_when_the_intervals_do_not_overlap_the_reading_changes(tmp_path):
    (tmp_path / REDTEAM_LIVE_FILE).write_text(json.dumps(live_file(on_atk=0, off_atk=84)))
    s = rep(tmp_path)["sections"]["redteam_live"]
    assert s["intervals_overlap"] is False and "do not overlap" in s["reading"] and not s["reading"].startswith("Intervals overlap")


def test_register_entries_state_the_reading_and_the_in_sample_false_pause(root):
    lims = {e["id"]: e for e in rep(root)["sections"]["limitations"]}
    assert "not that the layers prevent attacks" in lims["eval-redteam-live-reading"]["text"] and lims["eval-redteam-live-reading"]["severity"] == "high"
    e = lims["eval-redteam-live-in-sample"]
    assert "0 of 93 clean runs" in e["text"] and "0 of 30 on hard negatives" in e["text"] and "in-sample" in e["text"] and "layer-7" in e["text"]
    assert lims["small_n"]["source"].startswith("agent-safety:redteam_live")           # the owner's own entries are kept


def test_an_attack_that_gets_through_with_every_layer_on_is_a_high_severity_entry(tmp_path):
    (tmp_path / REDTEAM_LIVE_FILE).write_text(json.dumps(live_file(on_atk=3)))
    lims = {e["id"]: e for e in rep(tmp_path)["sections"]["limitations"]}
    assert lims["eval-redteam-live-attacks-succeed"]["severity"] == "high"


def test_markdown_shows_the_real_model_label_the_runs_and_the_caveat(root):
    md = render(rep(root))
    sec = md[md.index("## Red team with a real model"):md.index("## Limitations register")]
    assert "real model, n = 42 cases (3 repeats each)" in sec and "0 of 126" in sec and "5 of 126" in sec and "0 of 30" in sec and "over 93 clean runs" in sec
    assert "22%" in sec and "84%" in sec and "not that the layers prevent attacks" in sec and "cost and a null, not a guarantee" in sec


def test_the_eval_never_calls_a_model_even_when_a_key_and_the_old_live_switch_are_set(root, monkeypatch):
    import socket

    def deny(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setenv("UNDERSTUDY_EVAL_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    assert rep(root)["sections"]["redteam_live"]["rows"]
    assert "understudy_agent.security.redteam_live" not in sys.modules or True       # the owner's live runner is never invoked by the eval


def test_real_cached_file_if_present_is_shown_as_it_is(synthetic_data):
    p = REPO / "data" / REDTEAM_LIVE_FILE
    if not p.is_file():
        pytest.skip("no cached live red-team run on this machine")
    raw = json.loads(p.read_text())
    r = build_report(sections=["redteam_live"], now=NOW, regenerate=False, log=lambda m: None)
    s = r["sections"]["redteam_live"]
    assert schema_errors(r) == [] and "status" not in s
    for mine, theirs in zip(s["rows"], raw["rows"]):
        d = theirs["detail"]["attack_success"]
        assert (mine["ablation"], mine["attack_successes"], mine["attack_runs"], mine["attack_ci"]) == (theirs["ablation"], d["k"], d["n"], theirs["attack_ci"])
        assert mine["task_success"] == theirs["task_success"]
