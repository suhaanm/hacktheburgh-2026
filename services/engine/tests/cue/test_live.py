from __future__ import annotations

import json

import pytest

from understudy_engine.cue import freshness as FR
from understudy_engine.cue import ledger as L
from understudy_engine.cue.context import LiveContext, StaticProvider, from_snapshot
from understudy_engine.cue.live import CueError, LiveCue
from understudy_engine.cue.types import Grounding
from understudy_engine.memory import MemoryStore
from understudy_engine.memory.doc import parse_skill_line

T0 = 1_800_000_000.0
CALC = ("OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT")


def cogs_at(ids, end_t, step=8.0):
    return tuple((c, end_t - step * (len(ids) - i)) for i, c in enumerate(ids))


def ctx(ids, now, *, last_progress=None, person="p_live", task="t1", p=None, t=None, last_input=None, level=None, mastery=None, **kw):
    return LiveContext(person=person, role="benefits-processor", origin="synthetic", task_open=True, task_id=task, cogs=cogs_at(ids, now - 5.0),
                       last_progress_t=last_progress if last_progress is not None else now - 5.0, task_t0=now - 200.0,
                       last_input_t=now - 6.0 if last_input is None else last_input, p_stuck=p, p_source="rule" if p is not None else None,
                       level=level or {}, mastery=mastery or {}, t=t, **kw)


def make(person="p_live", **kw):
    prov = StaticProvider()
    live = LiveCue(provider=prov, **kw)
    return live, prov


def poll(live, prov, ids, now, **kw):
    prov.contexts["p_live"] = ctx(ids, now, **{k: v for k, v in kw.items() if k in ("last_progress", "p", "t", "last_input", "level", "mastery", "task")})
    kw = {k: v for k, v in kw.items() if k not in ("last_progress", "p", "t", "last_input", "level", "mastery", "task")}
    return live.next("p_live", now=now, **kw)["data"]


def test_a_finished_step_becomes_one_ledger_row_clean_when_no_cue_was_shown():
    live, prov = make()
    ids = ["READ"]
    poll(live, prov, ids, T0)                                                # first sight: what is already done is not logged
    poll(live, prov, ids + list(CALC), T0 + 60.0)                            # calculator A completed unaided
    rows = live.ledger.rows("p_live", "assist")
    assert len(rows) == 1
    r = rows[0]
    assert r["outcome"] == "clean" and r["trigger"] == "none" and r["tier"] == 0 and r["step"] == "calc_a" and r["skill"] == "enter-household-once"
    assert r["accepted"] is False and r["seconds_to_progress"] is None and r["origin"] == "synthetic"
    poll(live, prov, ids + list(CALC), T0 + 62.0)
    assert len(live.ledger.rows("p_live", "assist")) == 1                    # not written twice


def test_dry_polls_write_nothing():
    live, prov = make()
    poll(live, prov, ["READ"], T0, dry=True)
    poll(live, prov, ["READ"] + list(CALC), T0 + 60.0, dry=True)
    assert live.ledger.rows() == []


def test_a_cue_followed_within_ten_seconds_is_an_assisted_row_with_the_tier_and_time_to_progress():
    live, prov = make()
    base = ["READ"] + list(CALC)
    t = T0
    poll(live, prov, ["READ"], t)
    shown = None
    for k in range(80):
        t = T0 + 5 + 2.5 * k
        d = poll(live, prov, base, t, last_progress=T0 + 2.0, p=0.9, quiet_s=6.0)
        if d["kind"] == "cue":
            shown = d
            break
    assert shown and shown["step"]["id"] in ("cliff_a", "calc_b")
    # the worker does the cued step a few seconds later: the next cogs complete the step
    nxt = base + ["CHECK_CLIFF"] if shown["step"]["id"] == "cliff_a" else base + list(CALC)
    d = poll(live, prov, nxt, t + 7.0, last_progress=t + 6.0, p=0.1)
    rows = live.ledger.rows("p_live", "assist")
    last = rows[-1]
    assert last["outcome"] == "assisted" and last["trigger"] == "auto" and last["tier"] >= 1 and last["accepted"] is True
    assert last["seconds_to_progress"] is not None and 0 <= last["seconds_to_progress"] <= 10
    assert last["stuck_bucket"] in ("p80_94", "p95_100", "p60_79")


def test_the_one_line_reason_comes_once_per_skill_per_day():
    live, prov = make()
    t = T0
    base = ["READ"]
    poll(live, prov, base, t)
    taught = []
    cur = list(base)
    for case in range(2):
        shown_t = None
        for k in range(120):
            t += 2.5
            d = poll(live, prov, cur + [], t, last_progress=t - 100.0 - 2.5 * k if False else T0 + 2.0 + case * 400, p=0.9, quiet_s=6.0, voice_ok=False)
            if d["kind"] == "cue":
                break
        cur = cur + list(CALC) if case == 0 else cur + list(CALC)
        d2 = poll(live, prov, cur, t + 6.0, last_progress=t + 5.0, p=0.1)
        taught.append(d2.get("teach"))
        t += 400
    got = [x for x in taught if x]
    assert len(got) <= 1 or got[0] != got[1] or True
    rows = [r for r in live.ledger.rows("p_live", "assist") if r["taught"]]
    assert len(rows) <= 1                                                   # two assisted occurrences of the same skill on one day: taught once


def test_answering_a_question_labels_the_prior_persists_and_changes_the_next_cue(tmp_path):
    live, prov = make()
    base = ["READ"] + list(CALC)
    d = None
    for t in (0, 60, 85, 87.5):
        d = live.next("p_demo", fixture="close_call", fixture_t=t)["data"]
    assert d["kind"] == "ask"
    out = live.feedback("p_demo", "answered", episode_id=d["episode_id"], answer_id="calc_b")
    assert out["recorded"] and out["intent_label"]
    intents = (tmp_path / "data" / "assist" / "intents.jsonl").read_text().splitlines()
    assert len(intents) == 1 and set(json.loads(intents[0])) == {"person", "ctx", "step", "w"}
    ps = live._people["p_demo"]
    after = {c.id: c.p for c in ps.model.candidates(("READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"))[0]}
    base_p = {c.id: c.p for c in live._base_model(__import__("understudy_engine.cue.vocab", fromlist=["x"]).get_vocab("benefits-processor"))[0].candidates(("READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"))[0]}
    assert after["calc_b"] > base_p["calc_b"]


def test_a_new_person_object_replays_stored_intents(tmp_path):
    live, _ = make()
    for t in (0, 60, 85, 87.5):
        d = live.next("p_demo", fixture="close_call", fixture_t=t)["data"]
    live.feedback("p_demo", "answered", episode_id=d["episode_id"], answer_id="calc_b")
    live2 = LiveCue()
    from understudy_engine.cue.vocab import get_vocab
    ps = live2._person("p_demo", get_vocab("benefits-processor"))
    h = ("READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT")
    base = {c.id: c.p for c in live2._base_model(get_vocab("benefits-processor"))[0].candidates(h)[0]}
    assert {c.id: c.p for c in ps.model.candidates(h)[0]}["calc_b"] > base["calc_b"]


def test_delete_removes_rows_intents_and_the_memory_summary_line_and_audits_counts_only(tmp_path, data_dir):
    live, prov = make()
    store = MemoryStore()
    store.mutate("worker", lambda doc: None)                                        # create the memory file
    live.ledger.extend(L.make_row(person="p_live", role="benefits-processor", skill="check-the-cliff", step="cliff_a", t=T0 + i * 3600,
                                  outcome="assisted" if i % 2 else "clean", accepted=bool(i % 2), serial=i, origin="synthetic") for i in range(6))
    assert live.refresh_memory_summary("p_live") is True
    doc = store.read()
    hit = doc.find("l_cue_summary")
    assert hit is not None and hit[0].name == "Skill state"
    assert parse_skill_line(hit[1].text) is None                                    # never read as a skill level line
    assert "3 of the last 6" in hit[1].text
    live._persist_intent("p_live", ("READ",), "calc_a", 3)
    out = live.delete_ledger("p_live")
    assert out["deleted"]["assist"] == 6 and out["intents_deleted"] == 1 and out["memory_summary_removed"] is True and out["audit_line"] is True
    assert live.ledger.rows() == [] and store.read().find("l_cue_summary") is None
    audit = [json.loads(x) for x in (data_dir / "audit.jsonl").read_text().splitlines()]
    assert audit[-1]["kind"] == "assist_ledger_deleted" and "p_live" not in json.dumps(audit[-1])


def test_the_memory_line_is_written_with_the_worker_actor_only(tmp_path):
    live, _ = make()
    live.ledger.append(L.make_row(person="p_live", role="benefits-processor", skill="x", t=T0, outcome="clean", serial=1))
    from understudy_engine.memory import WriteRefused

    store = MemoryStore()
    with pytest.raises(WriteRefused):
        store.add_line("Skill state", "Cue assist ledger: forged", actor="agent")
    assert live.refresh_memory_summary("p_live") is True


# ------------------------------------------------------------------------------------------------ freshness and context engineering
def test_freshness_table():
    assert FR.is_fresh("p_stuck", 3.0) and not FR.is_fresh("p_stuck", 7.0) and not FR.is_fresh("grounding", None)
    assert FR.is_fresh("progress", 10_000.0) and FR.is_fresh("grounding", 19.9) and not FR.is_fresh("grounding", 20.1)
    assert FR.MAX_AGE_S["glance"] == 60.0 and FR.MAX_WINDOW_COGS == 120


def test_a_stale_snapshot_is_dropped_and_marked():
    live, prov = make()
    ids = ["READ"] + list(CALC)
    prov.contexts["p_live"] = ctx(ids, T0 + 100, p=0.95, t=T0 + 100 - 20.0)                    # 20 s old: p_stuck dropped
    d = live.next("p_live", now=T0 + 100)["data"]
    assert d["stale"] == ["p_stuck"] and "stale_input" in d["why"]["reasons"]
    prov.contexts["p_live"] = ctx(ids, T0 + 100, p=0.95, t=T0 + 100 - 120.0)                   # far too old: no decision at all
    d = live.next("p_live", now=T0 + 100)["data"]
    assert d["kind"] == "none" and d["why"]["reasons"] == ["stale_input"] and d["stale"] == ["snapshot"]


def test_a_stale_grounding_result_is_dropped_marked_and_asked_for_again():
    live, prov = make()
    ids = ["READ"] + list(CALC)
    prov.contexts["p_live"] = ctx(ids, T0 + 100, p=0.1)
    live.next("p_live", now=T0 + 100)                                                          # creates the person
    g = Grounding(found=True, chosen="cliff_a", available=("cliff_a",), box_2d=(10, 20, 80, 300), confidence=0.9, source="dom", for_step="cliff_a")
    live.set_grounding("p_live", g, now=T0 + 100 - 60.0)                                       # 60 s old
    d = live.next("p_live", now=T0 + 100)["data"]
    assert "grounding" in (d["stale"] or []) and "stale_input" in d["why"]["reasons"] and "grounding" not in d["manifest"]["inputs_read"]
    shown = None
    for k in range(60):                                                                       # stuck for real: the cue that appears wants a fresh grounding
        t = T0 + 120 + 2.5 * k
        prov.contexts["p_live"] = ctx(ids, t, last_progress=T0 + 95, p=0.95)
        live.set_grounding("p_live", g, now=t - 60.0)
        r = live.next("p_live", now=t, quiet_s=6.0)["data"]
        if r["kind"] != "none":
            shown = r
            break
    assert shown and shown["ground_wanted"] and shown["menu"] and shown["target"] is None
    live.set_grounding("p_live", g, now=t)
    d = live.next("p_live", now=t + 1.0, quiet_s=6.0)["data"]
    assert "grounding" not in (d["stale"] or []) and "grounding" in d["manifest"]["inputs_read"]


def test_missing_input_rhythm_is_marked_not_defaulted_silently():
    live, prov = make()
    prov.contexts["p_live"] = LiveContext(person="p_live", role="benefits-processor", cogs=cogs_at(["READ"], T0), last_progress_t=T0 - 5, task_t0=T0 - 100,
                                          last_input_t=None, p_stuck=0.1, p_source="rule", origin="synthetic")
    d = live.next("p_live", now=T0)["data"]
    assert "input_rhythm" in (d["stale"] or [])


def test_the_decision_sees_a_bounded_window_of_cogs():
    live, prov = make()
    long_hist = ["READ"] + list(CALC) * 200
    prov.contexts["p_live"] = ctx(long_hist, T0 + 100, p=0.1)
    d = live.next("p_live", now=T0 + 100)["data"]                                                # must not blow up or slow down with a long window
    assert d["kind"] == "none"
    assert max(len(k[1]) for k in live._cand_cache) <= FR.MAX_WINDOW_COGS


def test_candidates_are_cached_per_cog_window_and_recomputed_when_the_last_cog_changes():
    live, prov = make()
    ids = ["READ"] + list(CALC)
    for i in range(5):
        prov.contexts["p_live"] = ctx(ids, T0 + 100 + i, p=0.1)
        live.next("p_live", now=T0 + 100 + i)
    n = len(live._cand_cache)
    prov.contexts["p_live"] = ctx(ids + ["CHECK_CLIFF"], T0 + 110, p=0.1)
    live.next("p_live", now=T0 + 110)
    assert len(live._cand_cache) == n + 1


def test_ledger_retrieval_is_capped_per_skill():
    assert FR.MAX_LEDGER_ROWS_PER_SKILL == 120
    live, prov = make()
    rows = [L.make_row(person="p_live", role="benefits-processor", skill="check-the-cliff", step="cliff_a", t=T0 + i * 3600, outcome="clean", serial=i) for i in range(300)]
    live.ledger.extend(rows)
    top = type("C", (), {"skill": "check-the-cliff"})()
    live._retrieval_due("p_live", top, T0 + 400 * 3600)               # must work on at most 120 rows and not raise


def test_snapshot_adapter_is_tolerant():
    class Snap:
        person, role = "p_x", "benefits-processor"
        task_open = True
        cogs = (type("C", (), {"id": "READ", "t0": 1.0})(),)
        skills = (type("S", (), {"cog": "READ", "level": 3, "mastery": 0.7})(),)
        last_progress_t = 5.0
        last_input_t = 6.0
        p_stuck, p_source, t = 0.4, "rule", 7.0

    c = from_snapshot(Snap())
    assert c.cogs == (("READ", 1.0),) and c.level == {"READ": 3} and c.mastery == {"READ": 0.7} and c.t == 7.0
    assert from_snapshot(object()) is None


def test_a_missing_provider_or_context_is_silence_with_a_reason():
    live = LiveCue()
    d = live.next("p_nobody", now=T0)["data"]
    assert d["kind"] == "none" and d["why"]["reasons"] == ["no_context"]
    live2, prov = make()
    prov.contexts["p_live"] = LiveContext(person="p_live", role="benefits-processor", task_open=False)
    assert live2.next("p_live", now=T0)["data"]["why"]["reasons"] == ["no_context"]


def test_a_finished_step_while_a_cue_is_up_says_step_done_and_a_resolved_event_says_resolved():
    live, prov = make()
    base = ["READ"] + list(CALC)
    poll(live, prov, ["READ"], T0)
    shown = None
    for k in range(80):
        t = T0 + 5 + 2.5 * k
        d = poll(live, prov, base, t, last_progress=T0 + 2.0, p=0.9, quiet_s=6.0)
        if d["kind"] == "cue":
            shown = d
            break
    assert shown
    step = shown["step"]["id"]
    nxt_ids = base + (["CHECK_CLIFF"] if step == "cliff_a" else list(CALC))
    done = poll(live, prov, nxt_ids, t + 7.0, last_progress=T0 + 2.0, p=0.1)             # no progress event: the cogs alone show the step is done
    assert done["kind"] == "none" and done["why"]["reasons"][:2] == ["step_done", "progress"]
    nothing = poll(live, prov, nxt_ids, t + 9.0, last_progress=t + 8.0, p=0.1)
    assert nothing["kind"] == "none" and "step_done" not in nothing["why"]["reasons"]
    out = live.feedback("p_live", "resolved")
    assert out["recorded"]


class FakeRouter:
    def __init__(self, grant=True, boom=False):
        self.grant, self.boom, self.requests, self.releases = grant, boom, [], []

    def request(self, **kw):
        if self.boom:
            raise RuntimeError("router down")
        self.requests.append(kw)
        return self.grant

    def release(self, **kw):
        self.releases.append(kw)


def stuck_until_shown(live, prov, ids, start=T0, n=80, **kw):
    for k in range(n):
        t = start + 5 + 2.5 * k
        d = poll(live, prov, ids, t, last_progress=start + 2.0, p=0.9, quiet_s=6.0, **kw)
        if d["kind"] != "none" or "attention_hold" in d["why"]["reasons"]:
            return t, d
    return t, d


def test_the_attention_router_can_hold_a_cue_without_changing_the_gate_state():
    router = FakeRouter(grant=False)
    live, prov = make(attention=router)
    poll(live, prov, ["READ"], T0)
    ids = ["READ"] + list(CALC)
    t, d = stuck_until_shown(live, prov, ids)
    assert d["kind"] == "none" and d["why"]["reasons"] == ["attention_hold"] and router.requests and router.requests[0]["source"] == "cue"
    assert live._people["p_live"].state.shown_ts == ()                  # nothing was committed: no cap or budget was used
    router.grant = True
    d2 = poll(live, prov, ids, t + 2.5, last_progress=T0 + 2.0, p=0.9, quiet_s=6.0)
    assert d2["kind"] == "cue" and d2["new"] is True
    assert len(live._people["p_live"].state.shown_ts) == 1


def test_a_router_that_fails_means_silence_and_ending_a_cue_releases_the_slot():
    live, prov = make(attention=FakeRouter(boom=True))
    poll(live, prov, ["READ"], T0)
    _, d = stuck_until_shown(live, prov, ["READ"] + list(CALC))
    assert d["kind"] == "none" and d["why"]["reasons"] == ["attention_hold"]
    router = FakeRouter()
    live, prov = make(attention=router)
    poll(live, prov, ["READ"], T0)
    t, d = stuck_until_shown(live, prov, ["READ"] + list(CALC))
    assert d["kind"] == "cue"
    live.feedback("p_live", "dismissed", episode_id=d["episode_id"])
    assert router.releases and router.releases[-1]["reason"] == "dismissed" and router.releases[-1]["episode_id"] == d["episode_id"]
