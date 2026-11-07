"""Rewording only through the egress guard, and the canary flow over the whole judge, verify, prepare and fire path (PRV-1, PRV-4)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("understudy_engine.privacy")

from understudy_engine.privacy import ledger  # noqa: E402
from understudy_engine.privacy.egress import EgressError  # noqa: E402
from understudy_engine.privacy.testing import CapturingPort, canary_flow, hermetic  # noqa: E402

from understudy_engine.proactive import briefing as B  # noqa: E402
from understudy_engine.proactive import fire as F  # noqa: E402
from understudy_engine.proactive import reword as RW  # noqa: E402
from understudy_engine.proactive.candidates import Ctx, collect  # noqa: E402
from understudy_engine.proactive.store import BriefingStore  # noqa: E402

from .conftest import NOW, P, FakeQueue, FakeSpawner, cal_row, git_row, make_readers, routine_row, run_row, skill_row  # noqa: E402

PKG = Path(RW.__file__).parent


def _cand(kind: str, **readers):
    return next(c for c in collect(Ctx(P, NOW), make_readers(**readers)).candidates if c.kind == kind)


# ----------------------------------------------------------------------------------------------- reword
def test_the_wording_payload_has_only_kind_risk_sources_and_numbers(env):
    c = _cand("automate", routines=[routine_row(title="ZEPHYR secret routine")])
    payload = RW.payload_for(c, RW.ensure_features())
    assert set(payload) == {"kind", "risk", "sources", "numbers"}
    assert payload["kind"] == "automate" and payload["sources"] == ["routine"] and "episodes" in payload["numbers"]
    assert "ZEPHYR" not in json.dumps(payload) and not any(isinstance(v, (str, bool)) for v in payload["numbers"].values())


def test_a_reworded_reason_goes_through_one_egress_call_and_is_ledgered(env):
    c = _cand("automate", routines=[routine_row()])
    port = CapturingPort().script("plan", {"text": "It came up 14 times and could save a few hours."}).script("check", {"text": "It came up 14 times and could save a few hours."})
    out = RW.reword_why(c, port=port)
    assert out == "It came up 14 times and could save a few hours."
    assert len(port.requests) == 1
    rows = ledger.read_all()
    assert len(rows) == 1 and rows[0]["purpose"] == "briefing.card_wording"
    sent = json.dumps(rows[0]["payload"])
    assert "calc-entry" not in sent and "Enter the household" not in sent


def test_every_failure_falls_back_to_the_template(env):
    c = _cand("automate", routines=[routine_row()])
    assert RW.reword_why(c, port=CapturingPort().fail_with(RuntimeError("model down"))) is None
    wordy = {"text": "It saved 97 hours for you."}                       # a number that is in neither the template nor the payload
    assert RW.reword_why(c, port=CapturingPort().script("plan", wordy).script("check", wordy)) is None
    assert RW.reword_why(c, port=CapturingPort().script("plan", {"text": ""}).script("check", {"text": ""})) is None


def test_the_card_always_renders_without_a_model(env):
    readers = make_readers(routines=[routine_row()])
    b = B.build(P, store=env.store, readers=readers, now=NOW, reword_why=lambda c: (_ for _ in ()).throw(EgressError("blocked")))
    assert b.cards and b.cards[0].wording == "template" and b.cards[0].why.startswith("It came up 14 times")
    c = B.build("p_b", store=env.store, readers=readers, now=NOW, reword_why=lambda c: "A plain sentence with 14 in it.").cards[0]
    assert c.wording == "model" and c.why == "A plain sentence with 14 in it." and c.prepared["text"].startswith("What this does")


def test_the_model_never_writes_what_fires(env):
    readers = make_readers(routines=[routine_row()])
    plain = B.build("p_a", store=env.store, readers=readers, now=NOW).cards[0]
    worded = B.build("p_b", store=env.store, readers=readers, now=NOW, reword_why=lambda c: "Reworded.").cards[0]
    assert plain.prepared == worded.prepared


def test_the_default_hook_is_off_in_mock_mode_and_without_the_privacy_flag(monkeypatch):
    for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_PRIVACY", "UNDERSTUDY_MOCK"):
        monkeypatch.delenv(k, raising=False)
    assert RW.default_reword_why() is None
    monkeypatch.setenv("UNDERSTUDY_X_PRIVACY", "1")
    assert RW.default_reword_why() is RW.reword_why
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    assert RW.default_reword_why() is None


def test_nothing_under_proactive_reaches_a_model_except_through_egress():
    import ast

    files = list(PKG.glob("*.py")) + [PKG.parent / "routes_proactive.py"]
    assert len(files) >= 12
    for f in files:
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""] + [a.name for a in node.names]
            else:
                mods = []
            for m in mods:
                assert "openai" not in m.lower() and "understudy_agent.models" not in m and m not in ("ModelPort", "get_model_port"), f"{f.name} imports {m}"
            if isinstance(node, ast.Attribute) and node.attr in ("plan", "check", "vision", "read", "computer_step") and isinstance(node.value, ast.Name) \
                    and node.value.id in ("port", "model", "client", "model_port"):
                pytest.fail(f"{f.name} calls a model port method .{node.attr}")
            if isinstance(node, ast.Name) and node.id in ("ModelPort", "get_model_port"):
                pytest.fail(f"{f.name} uses {node.id}")
    assert "egress.send(" in (PKG / "reword.py").read_text()


# ----------------------------------------------------------------------------------------------- the canary flow (PRV-1, PRV-4)
SOURCE_KEYS = ("title", "organizer", "attendees", "location", "description", "message", "path", "author", "owner", "summary")


def _planted_strings(node, out):
    """Every string a planting pass put under a source key (calendar titles, attendees, commit messages, paths, authors ...)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in SOURCE_KEYS:
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, str):
                        out.append(x)
            else:
                _planted_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _planted_strings(v, out)
    return out


def _fixtures():
    """Only the source rows are planted: routine and skill rows are pack text, not raw calendar or git content."""
    return {"sources": {
        "calendar": [cal_row(title="Quarterly planning", organizer="Ada Lovelace", attendees=["Grace Hopper"], location="Room 4",
                             description="redundancy talk", summary="Meeting with the customer")],
        "git": [git_row(message="fix rounding for Acme Holdings", path="/Users/me/secret/payroll.py", author="Linus T")],
        "runs": [run_row(owner="Barbara Liskov")],
    }}


def _pipeline(fx, port, store_path, person=P):
    """judge, verify, prepare, edit and fire for every card, over two mornings; returns everything we keep or hand on."""
    keep: dict = {}
    port.script("plan", {"text": "A short sentence about 14."}).script("check", {"text": "A short sentence about 14."})
    readers = make_readers(routines=[routine_row()], skills=[skill_row()], **fx["sources"])
    store = BriefingStore(store_path)
    b = B.build(person, store=store, readers=readers, now=NOW, reword_why=lambda c: RW.reword_why(c, port=port))
    keep["cards"] = [c.kind for c in b.cards]
    q, sp = FakeQueue(), FakeSpawner()
    for c in b.cards:
        B.edit_prepared(c.id, {"text": c.prepared.get("text", "x") + " Edited.", "steps": c.prepared.get("steps", [])}, actor="worker", store=store)
        F.fire(c.id, actor="worker", store=store, readers=readers, now=NOW, queue=q, spawn=sp)
    # a second person with every kind on offer, so the git and agent cards are judged, verified and prepared too
    wide = B.build(person + "_wide", store=store, readers=readers, now=NOW, reword_why=lambda c: RW.reword_why(c, port=port), cap=5)
    keep["wide"] = sorted({c.kind for c in wide.cards})
    for c in wide.cards:
        if c.status == "ready":
            F.fire(c.id, actor="worker", store=store, readers=readers, now=NOW, queue=q, spawn=sp)
    keep["queue"], keep["spawn"] = q.calls, sp.calls
    keep["text"] = B.briefing_text(person, store=store, readers=readers, now=NOW)
    keep["store"] = store.path.read_text()
    keep["planted"] = _planted_strings(fx, [])
    keep["blobs"] = {"store": keep["store"], "queue": json.dumps(q.calls, default=str), "spawn": json.dumps(sp.calls, default=str), "text": keep["text"]}
    return keep


def test_canary_flow_over_judge_verify_prepare_and_fire(env, monkeypatch):
    hermetic(monkeypatch, env.tmp)
    kept: dict = {}
    report = canary_flow("proactive.briefing", _fixtures, lambda fx, port: kept.update(_pipeline(fx, port, env.tmp / "data" / "briefing.json")), min_requests=2)
    assert report.ok, report.summary()
    assert report.planted >= 5 and len(kept["cards"]) >= 2 and kept["queue"] and kept["text"].startswith("Good morning.")
    assert {"git_habit", "focus_block", "agent_result"} <= set(kept["wide"])
    assert kept["spawn"], "the git habit card should have started a run through the (fake) spawner"
    # PRV-4: the planted source text never reached anything we keep or hand on: the briefing file, queue payloads, run params, spoken text.
    # A control run on the same fixtures without planting tells us which words are just ordinary words of ours ("review", "meeting").
    control = _pipeline(_fixtures(), CapturingPort(), env.tmp / "control" / "briefing.json", person="p_control")
    ordinary = " ".join(control["blobs"].values()).lower()
    needles = {w.lower() for s in kept["planted"] for w in re.split(r"[^A-Za-z0-9]+", s) if len(w) >= 4}
    needles = {n for n in needles if n not in ordinary}
    assert len(needles) >= 10, needles
    for name, blob in kept["blobs"].items():
        low = blob.lower()
        for n in needles:
            assert n not in low, f"{n!r} reached {name}"
    for s in kept["planted"]:
        assert all(s not in b for b in kept["blobs"].values())


def test_the_ledger_has_one_line_per_model_call_and_nothing_else_left(env, monkeypatch):
    hermetic(monkeypatch, env.tmp)
    port = CapturingPort()
    readers = make_readers(routines=[routine_row()], skills=[skill_row()], calendar=[cal_row()])
    b = B.build(P, store=BriefingStore(env.tmp / "data" / "briefing.json"), readers=readers, now=NOW, reword_why=lambda c: RW.reword_why(c, port=port))
    from understudy_engine.privacy.testing import assert_ledger_complete

    assert len(port.requests) == len(b.cards) >= 2
    assert_ledger_complete(port)
