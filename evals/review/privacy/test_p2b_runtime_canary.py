"""REVIEW-PRIVACY: plant canaries in a CSV's header and cells and run the agent runtime (data.profile) in menu mode (nightly: no raw text
may reach a model) and in raw mode (foreground + raw_ok: raw text reaches the reader by design). Scan the port's captured calls and every
file under the data dir. The runtime has no privacy canary flow of its own (privacy eval 'gaps': ['agent_runtime']), so this is the first one.
Run: UNDERSTUDY_MOCK=1 .venv/bin/python -m pytest evals/review/privacy/test_p2b_runtime_canary.py -q -s -p no:cacheprovider
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

HDR = "Zebulon_Quillfeather_salary"
CELL = "Hollowbrook merger redundancy QZ7731"


def _scan(texts: list[str]) -> list[str]:
    low = "\n".join(texts).lower()
    return [n for n in ("zebulon", "quillfeather", "hollowbrook", "qz7731", "redundancy") if n in low]


def _csv(tmp: Path) -> Path:
    p = tmp / "sales.csv"
    p.write_text(f"region,{HDR},units\nnorth,{CELL},10\nsouth,{CELL},12\neast,{CELL},9\n")
    return p


def _run(tmp_path, monkeypatch, mode, raw_ok):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    from understudy_agent.models.mock_provider import MockProvider
    from understudy_agent.runtime.evaluate import _run as run
    from understudy_agent.runtime.mockscripts import mock_plan
    port = MockProvider("benefits_clean")
    port.script_plan("agent_plan", mock_plan("data.profile"))
    port.script_plan("child_step_c1", {"tool": "read_file", "reason": "look", "path": "input/data.csv"},
                     {"tool": "emit_result", "reason": "x", "result_file": "result.json"})
    r = run("data.profile", {"csv_path": str(_csv(tmp_path))}, mode=mode, raw_ok=raw_ok, port=port, auto_script=False, timeout=120)
    calls = [json.dumps(c, default=str) for c in port.calls]
    files = [p.read_bytes().decode("utf-8", "ignore") for p in (tmp_path / "data").rglob("*") if p.is_file()]
    return r, calls, files


def test_menu_mode_sends_no_file_text_to_the_model_and_persists_none_outside_the_workspace(tmp_path, monkeypatch):
    r, calls, files = _run(tmp_path, monkeypatch, "nightly", False)
    print("\nmenu/nightly: model calls =", len(calls), "| status =", {k: v.status for k, v in r.results.items()})
    assert calls, "no model call was captured; the test is not exercising the planner"
    assert _scan(calls) == [], f"file text reached the model in menu mode: {_scan(calls)}"
    survivors = [n for n in _scan(files)]
    print("canaries found in data-dir files (workspace copies are expected):", survivors)


def test_raw_mode_sends_file_text_to_the_model_by_design_and_ledgers_bytes_only(tmp_path, monkeypatch):
    r, calls, files = _run(tmp_path, monkeypatch, "foreground", True)
    seen = _scan(calls)
    led = tmp_path / "data" / "egress_ledger.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines()] if led.exists() else []
    direct = [x for x in rows if x.get("kind") == "direct"]
    print("\nraw/foreground: canaries in model calls =", seen, "| direct ledger rows =", len(direct),
          "| ledger rows mention a canary:", bool(_scan([json.dumps(rows)])))
    assert not _scan([json.dumps(rows)]), "the ledger must hold metadata only"
    assert seen, "expected the raw path to carry file text (documented); if empty the raw path changed"
