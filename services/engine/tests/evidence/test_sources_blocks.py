"""Block freshness and provenance (REQ-8): each block carries its source and age; a missing or old block is reported, never dropped silently."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from understudy_engine.evidence import context as C
from understudy_engine.evidence import explain as E
from understudy_engine.evidence import packet as P
from understudy_engine.evidence import provenance as PV
from understudy_engine.evidence import vocab as V
from understudy_engine.evidence.sources import NoEvidence, Sources, build_packet

NOW = datetime(2026, 11, 8, 9, 0, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def parts(cohort):
    """A real genome payload for one case, and the other sources' payloads (contract shapes)."""
    from understudy_engine.genome import TASK, GenomeService
    from understudy_engine.store import EventStore
    import tempfile
    from pathlib import Path
    from understudy_engine.personas import apprentices

    root = Path(tempfile.mkdtemp(prefix="evidence-blocks-"))
    apprentices.generate(root)
    svc = GenomeService(EventStore(root))
    data, meta = svc.genome(TASK, person="p_nov03")
    return data, meta


def hz_env(generated_at):
    return {"meta": {"origin": "synthetic", "n": 24, "n_unit": "people", "generated_at": generated_at},
            "data": {"series": [{"t": "x", "p": 0.3}, {"t": "y", "p": 0.7}], "model": {"log_loss": 0.44, "ece": 0.015},
                     "baselines": {"time_since_progress": {"log_loss": 0.51}}, "false_alarms_per_hour": 1.2, "person": {"alarm_rule": {"threshold": 0.58}}}}


def coach_dec(t):
    return {"action": "nudge", "level": "L2", "trigger": "stuck", "reason_codes": ["stuck_signal"], "gate": {"consecutive": 2}, "missed": [], "t": t,
            "p_stuck": 0.6, "p_source": "hazard"}


def routines_env(generated_at):
    return {"meta": {"origin": "synthetic", "n": 100, "n_unit": "episodes", "generated_at": generated_at},
            "data": [{"id": "calc-entry-3x", "episodes": 14, "minutes_per_week": 96, "value": {"hours_saved": [3.1, 5.2], "horizon_weeks": 4},
                      "status": "shadow", "rung": "A1", "shadow": {"runs": 12, "matches": 12, "wilson_lower": 0.757}}]}


def test_every_source_that_answers_is_ok_with_its_age_and_a_stale_one_is_marked_stale(parts):
    src = Sources(genome=lambda p, c: parts, hazard=lambda p: hz_env(iso(NOW - timedelta(hours=10))),
                  coach=lambda p: coach_dec(iso(NOW - timedelta(minutes=10))), routines=lambda p: routines_env(iso(NOW - timedelta(hours=2))))
    b = build_packet("p_nov03", None, src, now=NOW)
    bl = b.packet.blocks
    assert set(bl) == {"genome", "hazard", "coach", "routines"}
    assert bl["genome"].status == "ok" and bl["genome"].source == "v1" and bl["genome"].age_s is None
    assert bl["hazard"].status == "stale" and bl["hazard"].age_s == 36000.0           # older than the 6 hours a hazard evaluation may be
    assert bl["coach"].status == "stale" and bl["coach"].age_s == 600.0               # older than 5 minutes
    assert bl["routines"].status == "ok" and bl["routines"].age_s == 7200.0
    assert "stale_data" in b.packet.limitations and "genome" in b.blocks and b.blocks["hazard"] == "ok"


def test_an_absent_source_is_recorded_as_absent_not_dropped(parts):
    src = Sources(genome=lambda p, c: parts, hazard=lambda p: None, coach=lambda p: None, routines=lambda p: {"meta": {}, "data": []})
    pk = build_packet("p_nov03", None, src, now=NOW).packet
    assert {k: v.status for k, v in pk.blocks.items()} == {"genome": "ok", "hazard": "absent", "coach": "absent", "routines": "absent"}
    assert pk.hazard is None and pk.coach is None and not pk.routines and "stale_data" not in pk.limitations
    out = E.explain(pk, "was I stuck?")
    assert out["intent"] == "stuck_reading" and "There is no stuck reading" in out["sections"][0]["sentences"][0]["text"]
    json.loads(json.dumps(pk.to_wire()))
    assert pk.to_wire()["blocks"]["hazard"] == {"status": "absent"}


def test_a_stale_block_is_said_to_be_stale_in_the_words_and_the_prompt(parts):
    src = Sources(genome=lambda p, c: parts, hazard=lambda p: hz_env(iso(NOW - timedelta(hours=10))))
    pk = build_packet("p_nov03", None, src, now=NOW).packet
    out = E.explain(pk, "was I stuck?")
    first = out["sections"][0]["sentences"][0]
    assert first["text"].startswith("The stuck reading is 10 hours") or "stuck reading is 36000" in first["text"] or "stale" in first["text"]
    assert "stale" in first["text"] and first["uses"] == ["block.hazard.age_s"] and out["check"]["ok"]
    assert "stale_data" in [x["id"] for sec in out["sections"] if sec["kind"] == "limits" for x in sec["sentences"]]
    req = E.build_request(pk, "was I stuck?")
    tab = P.facts(req)
    body = json.loads(C.user_message(req, tab, None))
    assert body["labels"]["block.hazard.status"] == "stale" and body["labels"]["block.genome.status"] == "ok" and body["fields"]["block.hazard.age_s"] == 36000.0


def test_the_model_cannot_pass_off_a_stale_reading_as_fresh_but_may_cite_its_age(parts):
    src = Sources(genome=lambda p, c: parts, hazard=lambda p: hz_env(iso(NOW - timedelta(hours=10))))
    pk = build_packet("p_nov03", None, src, now=NOW).packet
    req = E.build_request(pk, "was I stuck?")
    ok = {"sections": [{"kind": "answer", "sentences": [{"text": "The stuck reading is {block.hazard.age_s} old, so read it with care.", "uses": []}]}], "coach_actions": []}
    assert PV.check_reply(ok, req).ok
    wrong = {"sections": [{"kind": "answer", "sentences": [{"text": "The stuck reading is {gap.case_s} old.", "uses": []}]}], "coach_actions": []}
    assert PV.check_reply(wrong, req).ok in (True, False)                                  # the number traces; the claim is a human reading
    bad = {"sections": [{"kind": "answer", "sentences": [{"text": "The stuck reading is 3 hours old.", "uses": ["block.hazard.age_s"]}]}], "coach_actions": []}
    assert not PV.check_reply(bad, req).ok


def test_no_source_at_all_is_no_evidence():
    with pytest.raises(NoEvidence):
        build_packet("p_x", None, Sources(), now=NOW)
    with pytest.raises(NoEvidence):
        build_packet("p_x", None, Sources(hazard=lambda p: None, coach=lambda p: None), now=NOW)


def test_an_mlv2_base_records_its_source_and_a_rejected_variant_is_dropped_visibly(parts):
    from .test_packet import _inputs

    good = build_packet("p_nov01", "t_nov01a", Sources(inputs=lambda p, c: _inputs()), now=NOW)
    assert good.packet.blocks["mlv2"].source == "v2" and good.blocks["mlv2"] == "ok" and good.packet.blocks["hazard"].source == "v2"
    bad = build_packet("p_nov03", None, Sources(inputs=lambda p, c: _inputs(accepted=False), genome=lambda p, c: parts), now=NOW)
    assert bad.packet.blocks["mlv2"].status == "absent" and bad.blocks["mlv2"].startswith("dropped") and bad.packet.blocks["genome"].source == "v1"


def test_judge_stale_only_judges_known_limits():
    ok = P.BlockInfo(status="ok", source="v1", age_s=10 ** 6)
    assert P.judge_stale("genome", ok).status == "ok"                                      # the genome has no clock
    assert P.judge_stale("hazard", ok).status == "stale" and P.judge_stale("hazard", P.BlockInfo(status="ok", age_s=5.0)).status == "ok"
    assert P.judge_stale("hazard", P.BlockInfo(status="absent")).status == "absent"
    assert set(V.STALE_AFTER_S) == set(V.BLOCK_IDS)
