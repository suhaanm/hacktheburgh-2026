"""Fire: only the worker's press creates anything; one thing per press; the prepared content fires verbatim; irreversible stays gated."""
from __future__ import annotations

import json

import httpx
import pytest

from understudy_engine.proactive import briefing as B
from understudy_engine.proactive import fire as F
from understudy_engine.proactive.cards import Card

from .conftest import NOW, P, FakeQueue, FakeSpawner, cal_row, git_row, make_readers, routine_row, run_row, skill_row


def _ready(env, **readers_kw):
    readers = make_readers(**readers_kw)
    b = B.build(P, store=env.store, readers=readers, now=NOW)
    return b, readers


def _press(env, card_id, readers, **kw):
    return F.fire(card_id, actor="worker", store=env.store, readers=readers, now=NOW, **kw)


def test_a_press_enqueues_one_pending_item_and_nothing_else(env):
    b, readers = _ready(env, routines=[routine_row()])
    q, sp = FakeQueue(), FakeSpawner()
    out = _press(env, b.cards[0].id, readers, queue=q, spawn=sp)
    assert set(out) >= {"queue_id", "status", "card"} and "run_id" not in out and out["status"] == "fired"
    assert len(q.calls) == 1 and sp.calls == []
    kw = q.calls[0]
    assert kw["dedupe_key"] == f"briefing:{b.cards[0].id}" and kw["risk_class"] == "normal" and kw["routine_id"] == "calc-entry-3x"
    assert env.store.find(b.cards[0].id).status == "fired" and env.store.find(b.cards[0].id).fired["queue_id"] == out["queue_id"]


def test_the_edited_content_is_exactly_what_fires(env):
    b, readers = _ready(env, routines=[routine_row()])
    cid = b.cards[0].id
    edited = B.edit_prepared(cid, {"text": "Only the first two calculators, please.", "steps": ["Start in shadow mode.", "Then ask me."]},
                             actor="worker", store=env.store)
    assert edited["edited"] is True and edited["prepared"]["steps"] == ["Start in shadow mode.", "Then ask me."]
    q = FakeQueue()
    out = _press(env, cid, readers, queue=q)
    sent = q.calls[0]["evidence"]["extracted"]
    assert sent["prepared"] == edited["prepared"] and sent["prepared_hash"] == edited["prepared_hash"]
    assert out["card"]["prepared"] == edited["prepared"]


def test_an_agent_card_starts_one_run_and_enqueues_nothing(env):
    b, readers = _ready(env, git=[git_row()])
    card = b.cards[0]
    assert card.kind == "git_habit" and card.fire_type == "agent"
    q, sp = FakeQueue(), FakeSpawner()
    out = _press(env, card.id, readers, queue=q, spawn=sp)
    assert "run_id" in out and "queue_id" not in out and q.calls == [] and len(sp.calls) == 1
    kind, params, mode = sp.calls[0]
    assert kind == "programming.commit_analyst" and mode == "foreground"
    assert params["prepared"] == card.prepared and params["prepared_hash"] == card.prepared_hash and params["card_id"] == card.id


def test_a_press_never_makes_both(env):
    b, readers = _ready(env, routines=[routine_row()], skills=[skill_row()], calendar=[cal_row()], git=[git_row()], runs=[run_row()])
    q, sp = FakeQueue(), FakeSpawner()
    for c in b.cards:
        out = _press(env, c.id, readers, queue=q, spawn=sp)
        assert ("queue_id" in out) != ("run_id" in out), c.kind


def test_an_irreversible_card_can_only_enter_the_queue_and_is_marked_irreversible(env):
    b, readers = _ready(env, routines=[routine_row()])
    cid = b.cards[0].id

    def make_irreversible(c: Card) -> None:
        c.risk_class = "irreversible"
        c.fire = {"type": "agent", "payload_ref": {"agent_kind": "programming.commit_analyst"}}

    env.store.update_card(cid, make_irreversible)
    q, sp = FakeQueue(), FakeSpawner()
    with pytest.raises(F.Refused):
        _press(env, cid, readers, queue=q, spawn=sp)
    assert q.calls == [] and sp.calls == [] and env.store.find(cid).status == "ready"
    env.store.update_card(cid, lambda c: setattr(c, "fire", {"type": "queue", "payload_ref": {"queue_kind": "batch_result", "action": "x"}}))
    _press(env, cid, readers, queue=q)
    assert q.calls[0]["risk_class"] == "irreversible" and q.calls[0]["kind"] == "irreversible_step"


def test_an_agent_card_cannot_start_an_unlisted_run_kind(env):
    b, readers = _ready(env, git=[git_row()])
    cid = b.cards[0].id
    env.store.update_card(cid, lambda c: setattr(c, "fire", {"type": "agent", "payload_ref": {"agent_kind": "computer.click_anything"}}))
    sp = FakeSpawner()
    with pytest.raises(F.Refused):
        _press(env, cid, readers, spawn=sp)
    assert sp.calls == []


@pytest.mark.parametrize("actor", ["agent", "model", "page", "tool", "", "Worker"])
def test_only_the_worker_can_press(env, actor):
    b, readers = _ready(env, routines=[routine_row()])
    q = FakeQueue()
    with pytest.raises(F.Refused):
        F.fire(b.cards[0].id, actor=actor, store=env.store, readers=readers, now=NOW, queue=q)
    with pytest.raises(F.Refused):
        F.dismiss(b.cards[0].id, actor=actor, store=env.store)
    with pytest.raises(B.EditError):
        B.edit_prepared(b.cards[0].id, {"text": "x"}, actor=actor, store=env.store)
    assert q.calls == [] and env.store.find(b.cards[0].id).status == "ready"


def test_pressing_twice_changes_nothing_the_second_time(env):
    b, readers = _ready(env, routines=[routine_row()])
    q = FakeQueue()
    first = _press(env, b.cards[0].id, readers, queue=q)
    with pytest.raises(F.NotReady) as e:
        _press(env, b.cards[0].id, readers, queue=q)
    assert e.value.extra["queue_id"] == first["queue_id"] and len(q.calls) == 1


def test_a_card_that_went_stale_is_dropped_not_fired(env):
    b, _ = _ready(env, routines=[routine_row()])
    changed = make_readers(routines=[routine_row(status="shadow")])        # switched on from another screen
    q = FakeQueue()
    with pytest.raises(F.Stale) as e:
        _press(env, b.cards[0].id, changed, queue=q)
    assert "already switched" in e.value.message.lower() and q.calls == []
    assert env.store.find(b.cards[0].id).status == "stale"


def test_the_kill_switch_stops_a_press(env):
    b, readers = _ready(env, routines=[routine_row()])
    (env.data / "KILL").write_text("2026-11-08T08:00:00Z\n")
    q = FakeQueue()
    with pytest.raises(F.Killed):
        _press(env, b.cards[0].id, readers, queue=q)
    assert q.calls == [] and env.store.find(b.cards[0].id).status == "ready"


def test_an_unreachable_queue_leaves_the_card_ready_to_press_again(env):
    b, readers = _ready(env, routines=[routine_row()])

    def down(**kw):
        raise F.Unavailable("queue down")

    with pytest.raises(F.Unavailable):
        _press(env, b.cards[0].id, readers, queue=down)
    assert env.store.find(b.cards[0].id).status == "ready"
    _press(env, b.cards[0].id, readers, queue=FakeQueue())
    assert env.store.find(b.cards[0].id).status == "fired"


def test_a_press_is_an_accept_label_and_the_subject_is_not_raised_again(env):
    b, readers = _ready(env, routines=[routine_row()])
    _press(env, b.cards[0].id, readers, queue=FakeQueue())
    st = env.store.person(P)
    assert st["labels"][-1]["accepted"] is True and "routine:calc-entry-3x" in st["suppress"]
    again = B.build(P, store=env.store, readers=readers, now=NOW, force=True)
    assert all(c.status != "ready" for c in again.cards) and not [c for c in again.cards if c.status == "ready"]


# ----------------------------------------------------------------------------------------------- dismiss
def test_not_now_snoozes_and_is_a_decline_label(env):
    b, readers = _ready(env, routines=[routine_row()])
    out = F.dismiss(b.cards[0].id, actor="worker", store=env.store, mode="not_now", now=NOW)
    assert out["status"] == "dismissed" and out["card"]["status"] == "dismissed"
    st = env.store.person(P)
    assert st["labels"][-1] == {"t": NOW.timestamp(), "kind": "automate", "accepted": False, "card": b.cards[0].id}
    soon = B.build(P, store=env.store, readers=readers, now=NOW, force=True)
    assert [c for c in soon.cards if c.status == "ready"] == []
    later = B.build(P, store=env.store, readers=readers, now=NOW.replace(day=12), force=True)     # past the cooldown
    assert [c.kind for c in later.cards if c.status == "ready"] == ["automate"]


def test_never_is_honoured_for_the_subject_and_the_whole_kind(env):
    b, readers = _ready(env, routines=[routine_row(), routine_row(id="case-note-copy", title="Copy results to the note")])
    ids = [c for c in b.cards if c.kind == "automate"]
    F.dismiss(ids[0].id, actor="worker", store=env.store, mode="never", now=NOW)
    later = B.build(P, store=env.store, readers=readers, now=NOW.replace(day=20), force=True)
    assert [c for c in later.cards if c.status == "ready" and c.kind == "automate"] == []        # kind and source not proposed again


def test_dismiss_rejects_an_unknown_mode(env):
    b, _ = _ready(env, routines=[routine_row()])
    with pytest.raises(F.FireError):
        F.dismiss(b.cards[0].id, actor="worker", store=env.store, mode="forever")


def test_viewing_a_result_marks_the_run_as_seen(env):
    b, readers = _ready(env, runs=[run_row()])
    F.dismiss(b.cards[0].id, actor="worker", store=env.store, mode="not_now", now=NOW)
    assert "r_bg_001" in env.store.person(P)["viewed_runs"]


# ----------------------------------------------------------------------------------------------- real ports
def test_the_default_spawner_posts_to_the_agent_service():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"run_id": "r_abc123"})

    spawn = F.default_spawner(url="http://127.0.0.1:7710", transport=httpx.MockTransport(handler))
    assert spawn("programming.test_gap", {"a": 1}, "foreground") == {"run_id": "r_abc123"}
    assert seen["url"] == "http://127.0.0.1:7710/agents/spawn" and seen["body"] == {"kind": "programming.test_gap", "params": {"a": 1}, "mode": "foreground"}
    down = F.default_spawner(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused"))))
    with pytest.raises(F.Unavailable):
        down("data.profile", {}, "foreground")
    bad = F.default_spawner(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(F.Unavailable):
        bad("data.profile", {}, "foreground")
    empty = F.default_spawner(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(F.Unavailable):
        empty("data.profile", {}, "foreground")


def test_the_real_approval_queue_gets_a_pending_item_never_an_approved_one(env):
    pytest.importorskip("understudy_agent")
    b, readers = _ready(env, routines=[routine_row()], calendar=[cal_row()])
    for c in b.cards:
        edited = B.edit_prepared(c.id, {"text": c.prepared["text"] + " Edited by me.", "steps": c.prepared["steps"]}, actor="worker", store=env.store)
        out = _press(env, c.id, readers)
        item = json.loads((env.data / "queue" / f"{out['queue_id']}.json").read_text())
        assert item["status"] == "pending" and item["decided_by"] is None and item.get("consumed_at") is None
        assert item["evidence"]["extracted"]["prepared"] == edited["prepared"]          # the queue's own sanitiser changed nothing
        assert item["evidence"]["extracted"]["prepared_hash"] == edited["prepared_hash"]
        assert item["dedupe_key"] == f"briefing:{c.id}" and item["risk_class"] == c.risk_class
    drafts = list((env.data / "briefing" / "drafts").glob("*.json"))
    assert len(drafts) == 1 and json.loads(drafts[0].read_text())["note"].startswith("A local draft")
    audit = [json.loads(x) for x in (env.data / "audit.jsonl").read_text().splitlines()]
    assert {a["kind"] for a in audit} >= {"queue_enqueued", "briefing_fired"}


def test_the_queue_item_carries_no_source_text(env):
    pytest.importorskip("understudy_agent")
    b, readers = _ready(env, calendar=[cal_row(title="ZEPHYR_PLANNING_MEETING", attendees=["Quillmoor Brann"], text="ORSIN secret merger")])
    out = _press(env, b.cards[0].id, readers)
    blob = (env.data / "queue" / f"{out['queue_id']}.json").read_text() + (env.data / "audit.jsonl").read_text() + env.store.path.read_text()
    for needle in ("ZEPHYR", "Quillmoor", "ORSIN", "merger"):
        assert needle.lower() not in blob.lower(), needle
