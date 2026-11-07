"""REVIEW-PRIVACY P2: run the tracks' REAL canary flows (privacy.evaluate.discover_flows) but look in more places than they do:
the flow's RETURN VALUE (what an API route would send to the dashboard), EVERY file under the data dir, HOME and TMPDIR (not only
ledger/audit/queue/logs), stdout and stderr, logging records at DEBUG (including formatted tracebacks), and the text of exceptions from a
failing model port. Needles come from the kit's planted tokens plus a second, independently shaped set (digit-bearing codes, mixed-case
names split across words, percent-encoded and base64 forms).
Run: UNDERSTUDY_MOCK=1 .venv/bin/python -m pytest evals/review/privacy/test_p2_canary_all_sinks.py -q -s -p no:cacheprovider
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import logging
import os
import re
import tempfile
import traceback
import urllib.parse
from pathlib import Path

import pytest

from understudy_engine.privacy import canary, evaluate
from understudy_engine.privacy.testing import CapturingPort

FLOWS, _LAYERS = evaluate.discover_flows()
INTEGRATION = [f for f in FLOWS if f.kind == "integration"]


class _Handler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.texts: list[str] = []

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.exc_info:
                msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
            self.texts.append(msg + " " + repr(record.args) + " " + repr(getattr(record, "__dict__", {}).get("extra", "")))
        except Exception:
            pass


def _needles(planted) -> list[str]:
    out = []
    for t in planted.tokens:
        out += list(t.needles)
        out.append(t.value.lower())
        out.append(urllib.parse.quote(t.value).lower())
        out.append(base64.b64encode(t.value.encode()).decode().lower().rstrip("="))
    return sorted({n for n in out if len(n) >= 5})


def _scan_text(text: str, needles) -> list[str]:
    low = text.lower()
    sq = re.sub(r"[^a-z0-9]+", "", low)
    hits = []
    for n in needles:
        if n in low or (len(re.sub(r"[^a-z0-9]+", "", n)) >= 6 and re.sub(r"[^a-z0-9]+", "", n) in sq):
            hits.append(n)
    return hits


def _all_files(*roots: Path):
    for r in roots:
        for p in r.rglob("*"):
            if p.is_file():
                yield p


@pytest.mark.parametrize("flow", INTEGRATION, ids=[f.name for f in INTEGRATION])
@pytest.mark.parametrize("seed", [101, 202])
def test_no_planted_token_survives_anywhere(flow, seed, tmp_path, monkeypatch):
    data, tmpd, home = tmp_path / "data", tmp_path / "tmp", tmp_path / "home"
    for d in (data, tmpd, home):
        d.mkdir(exist_ok=True)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(home / ".understudy"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(tmpd))
    monkeypatch.setattr(tempfile, "tempdir", str(tmpd))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    fixtures = flow.make_fixtures()
    planted = canary.plant(fixtures, seed=seed, mode=flow.mode)
    port = CapturingPort()
    h = _Handler()
    root = logging.getLogger()
    old = root.level
    root.addHandler(h); root.setLevel(logging.DEBUG)
    out, err = io.StringIO(), io.StringIO()
    ret = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ret = flow.run(fixtures, port)
    finally:
        root.removeHandler(h); root.setLevel(old)
    needles = _needles(planted)
    where: dict[str, list[str]] = {}
    sinks = {
        "return_value": json.dumps(ret, default=str) if ret is not None else "",
        "stdout": out.getvalue(), "stderr": err.getvalue(), "log_records": "\n".join(h.texts),
        "port_requests": json.dumps([getattr(r, "body", r) for r in port.requests], default=str),
    }
    for name, text in sinks.items():
        got = _scan_text(text, needles)
        if got:
            where[name] = got[:3]
    for p in _all_files(data, tmpd, home):
        try:
            got = _scan_text(p.read_bytes().decode("utf-8", "ignore"), needles)
        except OSError:
            continue
        if got:
            where[f"file:{p.relative_to(tmp_path)}"] = got[:3]
    files = sum(1 for _ in _all_files(data, tmpd, home))
    print(f"\n[{flow.name} seed {seed}] requests={len(port.requests)} files_scanned={files} return_bytes={len(sinks['return_value'])} survivors={where or 'none'}")
    assert not where, f"planted tokens survived in: {where}"


@pytest.mark.parametrize("flow", INTEGRATION, ids=[f.name for f in INTEGRATION])
def test_failing_model_port_exception_text_and_traceback_hold_no_canary(flow, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    fixtures = flow.make_fixtures()
    planted = canary.plant(fixtures, seed=303, mode=flow.mode)
    port = CapturingPort().fail_with(RuntimeError("upstream exploded"))
    texts = []
    try:
        ret = flow.run(fixtures, port)
        texts.append(json.dumps(ret, default=str))
    except Exception as exc:  # noqa: BLE001
        texts.append("".join(traceback.format_exception(exc)))
        texts.append(str(exc))
    got = _scan_text("\n".join(texts), _needles(planted))
    assert not got, f"{flow.name}: an exception, traceback or fallback result carried a planted token: {got[:3]}"
