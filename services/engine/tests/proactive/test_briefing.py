"""The morning cycle: cap, zero, stale replaced, edits carried, generations, mock clock, store, spoken summary, acceptance learning."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from understudy_engine.proactive import briefing as B
from understudy_engine.proactive import fire as F
from understudy_engine.proactive.acceptance import AcceptanceModel
from understudy_engine.proactive.judge import CAP

from .conftest import NOW, P, FakeQueue, cal_row, git_row, make_readers, routine_row, run_row, skill_row


def _all():
    return dict(routines=[routine_row(), routine_row(id="case-note-copy", title="Copy results to the note", episodes=40, minutes_per_week=60.0,
                                                  hours_lo=1.5, hours_hi=2.5)],
                skills=[skill_row()], calendar=[cal_row()], git=[git_row()], runs=[run_row()])


def test_the_cap_holds_whatever_is_on_offer(env):
    b = B.build(P, store=env.store, readers=make_readers(**_all()), now=NOW)
    assert 0 < len(b.cards) <= CAP == 3
    assert [c.score for c in b.cards] == sorted((c.score for c in b.cards), reverse=True)
    assert len({c.kind for c in b.cards}) == len(b.cards) or len(b.cards) <= 3


def test_nothing_worth_surfacing_gives_an_empty_briefing(env):
    b = B.build(P, store=env.store, readers=make_readers(), now=NOW)
    assert b.cards == [] and b.to_contract()["cards"] == []
    assert B.summary_text(b.cards) == "Good morning. Nothing needs your attention today."


def test_building_a_briefing_never_creates_a_queue_item_or_a_run(env):
    B.build(P, store=env.store, readers=make_readers(**_all()), now=NOW)
    B.build(P, store=env.store, readers=make_readers(**_all()), now=NOW + timedelta(hours=20))
    assert not (env.data / "queue").exists() or list((env.data / "queue").glob("*.json")) == []
    assert not (env.data / "briefing" / "drafts").exists()


def test_reading_twice_is_stable_and_does_not_reshuffle(env):
    readers = make_readers(**_all())
    a = B.build(P, store=env.store, readers=readers, now=NOW)
    b = B.build(P, store=env.store, readers=readers, now=NOW + timedelta(minutes=30))
    assert [c.id for c in a.cards] == [c.id for c in b.cards] and b.generated_at == a.generated_at and not b.regenerated


def test_a_card_that_goes_stale_is_dropped_and_its_slot_refilled(env):
    first = B.build(P, store=env.store, readers=make_readers(**_all()), now=NOW)
    assert any(c.kind == "automate" for c in first.cards)
    changed = _all()
    changed["routines"] = [routine_row(status="shadow"), routine_row(id="case-note-copy", status="approval", title="x")]   # both switched on
    later = B.build(P, store=env.store, readers=make_readers(**changed), now=NOW + timedelta(hours=1))
    assert not any(c.kind == "automate" for c in later.cards)
    assert {d["id"] for d in later.dropped} >= {c.id for c in first.cards if c.kind == "automate"}
    assert len(later.cards) <= CAP
    stale = [c for c in env.store.cards(P) if c.status == "stale"]
    assert stale and all(c.verify_note for c in stale)


def test_stale_cards_stay_in_the_store_for_audit_but_not_in_the_briefing(env):
    B.build(P, store=env.store, readers=make_readers(skills=[skill_row()]), now=NOW)
    b = B.build(P, store=env.store, readers=make_readers(skills=[skill_row(level=4)]), now=NOW + timedelta(hours=1))
    assert b.cards == [] and [c.status for c in env.store.cards(P)] == ["stale"]


def test_a_new_generation_archives_old_cards_but_keeps_the_workers_edits(env):
    readers = make_readers(**_all())
    first = B.build(P, store=env.store, readers=readers, now=NOW)
    keep, other = first.cards[0], first.cards[1]
    B.edit_prepared(keep.id, {"text": "My own wording.", "steps": ["One step."]}, actor="worker", store=env.store)
    nxt = B.build(P, store=env.store, readers=readers, now=NOW + timedelta(hours=30))
    assert nxt.regenerated and keep.id in {c.id for c in nxt.cards}
    kept = next(c for c in nxt.cards if c.id == keep.id)
    assert kept.prepared == {"text": "My own wording.", "steps": ["One step."]} and kept.edited
    assert other.id not in {c.id for c in nxt.cards if c.edited}
    assert any(h["id"] == other.id for h in env.store.person(P)["history"])
    assert len(nxt.cards) <= CAP


def test_an_edit_survives_a_numbers_update(env):
    first = B.build(P, store=env.store, readers=make_readers(routines=[routine_row()]), now=NOW)
    cid = first.cards[0].id
    B.edit_prepared(cid, {"text": "Mine."}, actor="worker", store=env.store)
    moved = make_readers(routines=[routine_row(episodes=30, minutes_per_week=190.0, hours_lo=6.0, hours_hi=9.0)])
    b = B.build(P, store=env.store, readers=moved, now=NOW + timedelta(hours=2))
    c = b.cards[0]
    assert c.verdict == "updated" and c.numbers["episodes"] == 30 and c.prepared == {"text": "Mine."} and "30 times" in c.why


def test_an_unedited_card_is_reprepared_when_the_numbers_move(env):
    B.build(P, store=env.store, readers=make_readers(routines=[routine_row()]), now=NOW)
    moved = make_readers(routines=[routine_row(episodes=30, minutes_per_week=190.0, hours_lo=6.0, hours_hi=9.0)])
    c = B.build(P, store=env.store, readers=moved, now=NOW + timedelta(hours=2)).cards[0]
    assert "30 times" in c.prepared["text"]


def test_a_decline_is_a_label_that_lowers_the_next_estimate(env):
    readers = make_readers(skills=[skill_row()])
    b = B.build(P, store=env.store, readers=readers, now=NOW)
    F.dismiss(b.cards[0].id, actor="worker", store=env.store, mode="not_now", now=NOW)
    labels = env.store.person(P)["labels"]
    assert [x["accepted"] for x in labels] == [False]
    assert AcceptanceModel.from_labels(labels).p("practice") < AcceptanceModel().p("practice")


def test_a_press_on_one_kind_raises_it_over_a_decline_on_another(env):
    labels = [{"kind": "practice", "accepted": False}] * 4 + [{"kind": "automate", "accepted": True}] * 4
    m = AcceptanceModel.from_labels(labels)
    assert m.p("automate") > m.p("practice") and m.summary()["accepted"] == 4


def test_mock_mode_uses_the_briefings_own_clock_and_never_expires(env, monkeypatch):
    readers = make_readers(**_all())
    first = B.build(P, store=env.store, readers=readers, now=NOW)
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    far = B.build(P, store=env.store, readers=readers)           # no 'now': mock mode reuses the generation time
    assert [c.id for c in far.cards] == [c.id for c in first.cards] and far.generated_at == first.generated_at and not far.regenerated
    assert all(c.status == "ready" for c in far.cards)


def test_the_store_file_holds_no_source_text_and_survives_a_reload(env):
    B.build(P, store=env.store, readers=make_readers(calendar=[cal_row(title="ZEPHYR PLANNING", organizer="Brann Quill")]), now=NOW)
    raw = env.store.path.read_text()
    assert "ZEPHYR" not in raw and "Brann" not in raw
    d = json.loads(raw)
    assert d["version"] == 1 and P in d["persons"] and d["persons"][P]["cards"]
    from understudy_engine.proactive.store import BriefingStore

    assert [c.id for c in BriefingStore(env.store.path).cards(P)] == [c["id"] for c in d["persons"][P]["cards"]]


# ----------------------------------------------------------------------------------------------- the spoken summary
def test_the_spoken_briefing_is_counts_and_kinds_only(env):
    readers = make_readers(routines=[routine_row(title="ZEPHYR_CUSTOMER routine")], skills=[skill_row(label="QUILLMOOR skill")],
                           calendar=[cal_row(title="BRANN meeting")])
    b = B.build(P, store=env.store, readers=readers, now=NOW)
    text = B.briefing_text(P, store=env.store, readers=readers, now=NOW)
    assert text.startswith("Good morning. You have three suggestions ready:") and "Nothing happens until you press go" in text
    for c in b.cards:
        assert c.title not in text and c.why not in text
    for needle in ("ZEPHYR", "QUILLMOOR", "BRANN", "Automate", "calc-entry"):
        assert needle.lower() not in text.lower()
    assert not any(ch.isdigit() for ch in text.replace("one", ""))


def test_the_summary_tracks_what_is_still_ready(env):
    readers = make_readers(routines=[routine_row()], skills=[skill_row()])
    b = B.build(P, store=env.store, readers=readers, now=NOW)
    F.fire(b.cards[0].id, actor="worker", store=env.store, readers=readers, now=NOW, queue=FakeQueue())
    t = B.briefing_text(P, store=env.store, readers=readers, now=NOW)
    assert "one suggestion ready" in t


def test_summary_mentions_approval_only_for_careful_cards(env):
    plain = B.build(P, store=env.store, readers=make_readers(skills=[skill_row()]), now=NOW)
    assert "approval" not in B.summary_text(plain.cards)
    careful = B.build("p_other", store=env.store, readers=make_readers(calendar=[cal_row()]), now=NOW)
    assert "approval" in B.summary_text(careful.cards)


def test_edit_validation(env):
    b = B.build(P, store=env.store, readers=make_readers(routines=[routine_row()]), now=NOW)
    cid = b.cards[0].id
    for bad in ({"text": 5}, {"steps": "no"}, {"steps": ["x"] * 13}, {"html": "<b>"}, {}, "text", {"artifact_ref": "../../etc/passwd"}):
        with pytest.raises(B.EditError) as e:
            B.edit_prepared(cid, bad, actor="worker", store=env.store)
        assert e.value.status == 422
    ok = B.edit_prepared(cid, {"text": "Fine <b>[x]</b> | `y`"}, actor="worker", store=env.store)
    assert not any(ch in ok["prepared"]["text"] for ch in "<>[]`|")
    with pytest.raises(B.EditError) as e:
        B.edit_prepared("c_nonexistent", {"text": "x"}, actor="worker", store=env.store)
    assert e.value.status == 404


def test_the_spoken_text_passes_the_voice_modules_personal_data_check(env):
    dataflow = pytest.importorskip("understudy_agent.security.dataflow")
    tts = pytest.importorskip("understudy_agent.voice.tts")
    for person, kw in (("p_a", _all()), ("p_b", dict(skills=[skill_row()])), ("p_c", {})):
        text = B.briefing_text(person, store=env.store, readers=make_readers(**kw), now=NOW)
        assert not dataflow.personal_kinds(text)
        assert tts._clean(text, "briefing") == text and len(text) < tts.MAX_CHARS["briefing"]
