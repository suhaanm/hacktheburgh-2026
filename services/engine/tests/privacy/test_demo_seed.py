from __future__ import annotations

from understudy_engine.privacy import ledger
from understudy_engine.privacy.demo import seed
from understudy_engine.privacy.testing import vocabulary_problems


def test_seed_writes_only_genuine_guard_lines_all_marked_mock():
    out = seed(rounds=2)
    rows = ledger.read_all()
    assert out["lines"] == len(rows) == 2 * (1 + 1 + 2 + 1)
    assert {r["purpose"] for r in rows} == {"calendar.suggestion_wording", "git.habit_wording", "briefing.card_wording", "digest.meta"}
    assert all(r["mock"] is True and r["kind"] == "extension" and r["model"] == "capturing" and r["payload"] and r["bytes"] > 0 for r in rows)
    s = ledger.summary()
    assert s["calls"] == len(rows) and s["mock_calls"] == len(rows)


def test_reset_removes_everything_without_a_trace_and_clear_keeps_a_note(data_dir):
    seed()
    ledger.clear()
    assert ledger.summary()["cleared"]["times"] == 1
    seed(reset=True)
    assert ledger.summary()["cleared"]["times"] == 0 and ledger.count() > 0


def test_seed_with_canary_fills_the_summary_block():
    seed(reset=True, canary=True)
    c = ledger.summary()["canary"]
    assert c["planted"] > 0 and c["leaked"] == 0 and c["runs"] >= 5


def test_no_vocabulary_or_field_problem_after_everything_the_layers_registered():
    assert vocabulary_problems() == []
