"""Words and enums: stop classes, families, labels and keys. Fixed by code, checked against every pack we ship."""
from __future__ import annotations

import pytest

from understudy_engine.hitlist import vocab as V
from understudy_engine.memory import load_pack
from understudy_engine.memory.packinfo import list_pack_ids


@pytest.mark.parametrize("text,want", [
    ("submit", "submit"), ("submit to claimant record", "submit"), ("close case", "submit"), ("approve payment", "payment"),
    ("issue payment", "payment"), ("pay", "payment"), ("send decision", "message"), ("send letter", "message"), ("notify claimant", "message"),
    ("delete", "delete"), ("overwrite", "delete"), ("post", "share"), ("export", "share"), ("publish", "share"), ("share dashboard", "share"),
    ("merge pull request", "release"), ("deploy", "release"), ("force push", "release"), ("read the page", None), ("", None),
])
def test_classify_phrase(text, want):
    assert V.classify_phrase(text) == want


def test_worst_orders_by_severity_and_defaults_to_none():
    assert V.worst(["share", "submit", None]) == "submit"
    assert V.worst(["message", "payment"]) == "payment"
    assert V.worst([None, None]) == "none" and V.worst([]) == "none"
    assert V.stops_for_never(["submit", "submit to claimant record", "send letter"]) == "submit"
    assert V.stops_for_never(["merge pull request", "deploy"]) == "release"


def test_every_stop_is_in_the_enum():
    for p in ("submit", "pay", "send letter", "delete", "export", "deploy", "read"):
        assert (V.classify_phrase(p) or "none") in V.STOPS


@pytest.mark.parametrize("cog,fam", [
    ("OPEN_CALCULATOR", "open"), ("NAVIGATE", "open"), ("ENTER_HOUSEHOLD", "enter"), ("ENTER", "enter"), ("READ_RESULT", "read"),
    ("COPY_TO_NOTE", "copy"), ("PASTE", "copy"), ("CHECK_CLIFF", "check"), ("DECIDE", "check"), ("RUN_QUERY", "run"), ("RUN_TESTS", "run"),
    ("WRITE_QUERY", "enter"), ("INSPECT_RESULT", "read"), ("SEARCH", "search"), ("ASK", "step"), ("EXPORT_RESULT", "copy"),
])
def test_family_of(cog, fam):
    assert V.family_of(cog) == fam and fam in V.FAMILIES


def test_family_signature_collapses_repeats_and_ignores_the_tool():
    a = V.family_signature(["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"])
    b = V.family_signature(["NAVIGATE", "ENTER", "READ", "READ"])
    assert a == b == ("open", "enter", "read")


def test_dominant_family_is_deterministic_on_ties_and_ignores_unknown_steps():
    assert V.dominant_family(["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"]) == "open"        # three-way tie: fixed order
    assert V.dominant_family(["ASK", "ASK", "COPY"]) == "copy"
    assert V.dominant_family(["ASK"]) == "step" and V.dominant_family([]) == "step"


def test_unmatched_label_is_spelled_from_the_steps():
    label, key, fam = V.label_for(None, ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"])
    assert label == "Open calculator, enter household and read result" and key == "Open calculator" and fam == "open"
    label, _, _ = V.label_for(None, ["READ", "COPY", "PASTE", "CHECK", "READ"])
    assert label == "Read, copy, paste and more"
    assert V.label_for(None, ["READ", "READ", "READ"])[0] == "Read"


def test_every_shipped_template_has_a_label_whose_key_is_part_of_it():
    seen = 0
    for pid in list_pack_ids():
        for t in load_pack(pid).templates:
            label, key, fam = V.label_for(t, list(t["cogs"]))
            assert label == t["title"] and fam in V.FAMILIES
            assert key and key.lower() in label.lower(), (t["id"], key)
            seen += 1
    assert seen >= 7


def test_derive_key_falls_back_to_the_first_noun_words():
    assert V.derive_key("Refresh the weekly metrics sheet") == "weekly metrics"
    assert V.derive_key("Sweep") is None


def test_fixed_sentences_are_plain_and_name_the_window():
    assert "three times" in V.sentence_new_user()
    assert "5 cases" in V.sentence_too_little(5, 7) and "30 day view" in V.sentence_too_little(5, 7) and "day view" not in V.sentence_too_little(5, 30)
    assert "1 case " in V.sentence_too_little(1, 7)
    assert "30 days" in V.sentence_nothing(30)
    assert V.sentence_counting_again("2026-11-07").startswith("Counting again since 7 November.")
    assert V.human_date("2026-01-31") == "31 January" and V.human_date("soon") == "soon"
    for s in (V.sentence_new_user(), V.sentence_all_handled(), V.sentence_capture_off(), V.note_meta("real"), V.note_meta("synthetic")):
        assert s and "  " not in s and not any(ord(c) > 127 for c in s)
    assert "synthetic" in V.note_meta("synthetic") and "synthetic" not in V.note_meta("real")
