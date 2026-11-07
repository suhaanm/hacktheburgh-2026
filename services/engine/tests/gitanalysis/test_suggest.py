from __future__ import annotations

import pytest

from understudy_engine.gitanalysis import suggest
from understudy_engine.gitanalysis.compare import habit_rows
from understudy_engine.gitanalysis.features import HABIT_IDS, HABITS, build_table
from understudy_engine.gitanalysis.records import load_records


def row(hid, learner, expert, flagged=True, n_num=10, n_den=40, delta=None):
    h = HABITS[hid]
    d = learner - expert if delta is None else delta
    return {"id": hid, "label": h.label, "learner": learner, "expert": expert, "delta": d, "ci": [d - 0.05, d + 0.05], "bad": h.bad,
            "min_delta": h.min_delta, "n_den": n_den, "n_num": n_num, "flagged": flagged, "reason": "flagged" if flagged else "below_min_delta"}


def test_catalogue_covers_every_habit_exactly_once_and_has_five_entries():
    assert len(suggest.CATALOGUE) == 5
    assert set(suggest.HABIT_TO_ENTRY) == set(HABIT_IDS) == set(HABITS)
    assert set(suggest.PRIVACY_HABIT) == set(HABIT_IDS)


@pytest.mark.parametrize("hid,eid", [("big_commits", "GIT_SMALLER_COMMITS"), ("tests_with_changes", "GIT_TESTS_WITH_CHANGES"),
                                     ("fix_after_fix", "GIT_RUN_TESTS_BEFORE_COMMIT"), ("reverts", "GIT_RUN_TESTS_BEFORE_COMMIT"),
                                     ("vague_messages", "GIT_CLEARER_MESSAGES"), ("late_night", "GIT_PROTECT_LATE_NIGHT")])
def test_each_habit_selects_its_entry_with_numbers_and_the_expert_reference(hid, eid):
    bad = HABITS[hid].bad
    learner, expert = (0.5, 0.1) if bad > 0 else (0.1, 0.7)
    out = suggest.select([row(hid, learner, expert)], n_experts=8)
    assert [s["id"] for s in out] == [eid]
    s = out[0]
    assert f"{round(100 * learner)}%" in s["text"] and f"{round(100 * expert)}%" in s["text"] and "10 of 40" in s["text"]
    assert s["expert_ref"]["n_experts"] == 8 and s["expert_ref"]["values"][hid] == expert and s["expert_ref"]["origin"] == "synthetic"
    assert s["numbers"][hid]["n_den"] == 40 and s["risk"] == "low" and s["wording"] == "template" and s["can_draft"] is False


def test_unflagged_habits_select_nothing_and_selection_is_deterministic():
    rows = [row(h, 0.1, 0.1, flagged=False, delta=0.0) for h in HABIT_IDS]
    assert suggest.select(rows) == []
    rows2 = [row("big_commits", 0.4, 0.03), row("late_night", 0.2, 0.03), row("vague_messages", 0.5, 0.04)]
    assert suggest.select(rows2) == suggest.select(list(reversed(rows2)))


def test_strongest_first_and_limit():
    rows = [row("big_commits", 0.15, 0.03, delta=0.12), row("vague_messages", 0.6, 0.04, delta=0.56), row("late_night", 0.2, 0.02, delta=0.18)]
    out = suggest.select(rows)
    assert out[0]["id"] == "GIT_CLEARER_MESSAGES" and len(suggest.select(rows, limit=2)) == 2


def test_combined_entry_cites_both_habits():
    out = suggest.select([row("fix_after_fix", 0.5, 0.1), row("reverts", 0.1, 0.01)])
    assert len(out) == 1 and out[0]["habits"] == ["fix_after_fix", "reverts"]
    assert "followed by another fix" in out[0]["text"] and "reverts" in out[0]["text"]


def test_attach_marks_only_flagged_habits():
    rows = [row("big_commits", 0.4, 0.03), row("late_night", 0.03, 0.03, flagged=False, delta=0.0)]
    got = suggest.attach(rows, suggest.select(rows))
    assert got[0]["suggestion"]["id"] == "GIT_SMALLER_COMMITS" and "suggestion" not in got[1]


def test_text_has_no_free_text_beyond_templates(learner_repo, cohort):
    experts = {p: build_table(load_records(r)[0]) for p, r in cohort["experts"].items()}
    rows = habit_rows(build_table(load_records(learner_repo)[0]), experts, B=200, seed=1)
    for s in suggest.select(rows, n_experts=8):
        assert "\n" not in s["text"] and len(s["text"]) < 400


# ---- rewording only through the privacy spine
def test_reword_default_off_and_in_mock_mode():
    rows = [row("big_commits", 0.4, 0.03)]
    s = suggest.select(rows)
    assert suggest.reword(s, rows) == s                                     # mock mode, no flag: templated
    assert suggest.reword(s, rows, enabled=False) == s


def test_reword_goes_through_egress_and_sends_only_bucketed_numbers():
    from understudy_engine.privacy.testing import CapturingPort, assert_ledger_complete
    rows = [row("tests_with_changes", 0.1371, 0.7423, n_den=168, n_num=23), row("vague_messages", 0.3756, 0.0384, n_den=205, n_num=77)]
    s = suggest.select(rows)
    port = CapturingPort().script("plan", {"text": "Pair each change with a test so reviews stay quick."})
    out = suggest.reword(s, rows, port=port)
    assert len(port) == 2
    assert any(o["wording"] == "model" and o["text"].startswith("Pair each") for o in out)
    assert all(o["text_templated"] for o in out)
    assert_ledger_complete(port)                                            # one ledger line per request, nothing bypassed
    body = " ".join(port.texts())
    assert "0.1371" not in body and "0.7423" not in body and "0.3756" not in body    # ratios go in 10% steps (the privacy track's rule)
    from understudy_engine.privacy.testing import ledger_extension_rows
    sent = [r["payload"] for r in ledger_extension_rows()]
    assert {p["habit"] for p in sent} == {"no_tests", "vague_messages"}
    assert all(set(p) == {"habit", "learner_ratio", "expert_ratio", "n_commits"} for p in sent)       # nothing else leaves
    assert sent[0]["learner_ratio"] == pytest.approx(0.1) and sent[0]["expert_ratio"] == pytest.approx(0.7)
    for o in out:                                                             # nothing from the habit rows' text reaches the model
        assert o["text_templated"] not in body


def test_reword_falls_back_to_the_template_on_any_failure():
    from understudy_engine.privacy.testing import CapturingPort
    rows = [row("big_commits", 0.4, 0.03)]
    s = suggest.select(rows)
    for bad in ({"text": "line one\nline two"}, {"text": "x" * 400}, {"nope": 1}):
        out = suggest.reword(s, rows, port=CapturingPort().script("plan", bad))
        assert out[0]["text"] == s[0]["text"] and out[0]["wording"] == "template"
    boom = CapturingPort().fail_with(RuntimeError("down"))
    assert suggest.reword(s, rows, port=boom)[0]["wording"] == "template"


def test_no_model_client_imports_in_this_package():
    import pathlib
    import re
    root = pathlib.Path(suggest.__file__).parent
    pat = re.compile(r"\b(import openai|from openai|ModelPort|get_model_port|\.plan\(|\.check\()")
    offenders = [p.name for p in root.glob("*.py") if pat.search(p.read_text())]
    assert offenders == [], offenders
