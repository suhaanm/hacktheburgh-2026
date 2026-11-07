"""Normalisation, buckets and the deterministic rules."""
from __future__ import annotations

import pytest

from understudy_engine.localmodel import rules
from understudy_engine.localmodel.schemas import (
    COMMIT_KEYS,
    EVENT_KEYS,
    attendee_bucket,
    duration_bucket,
    normalise_commit,
    normalise_event,
    parse_numstat,
    size_bucket,
)


def test_size_buckets_edges():
    assert [size_bucket(n) for n in (0, 10, 11, 50, 51, 250, 251, 1000, 1001)] == [
        "tiny", "tiny", "small", "small", "medium", "medium", "large", "large", "huge"]


def test_duration_and_attendee_buckets():
    assert [duration_bucket(m) for m in (5, 29.9, 30, 59, 60, 89, 90, 179, 180, 600)] == [
        "lt30", "lt30", "30to59", "30to59", "60to89", "60to89", "90to179", "90to179", "180plus", "180plus"]
    assert duration_bucket(None, all_day=True) == "allday" and duration_bucket(24 * 60) == "allday"
    assert [attendee_bucket(n) for n in (0, 1, 4, 5, 9, 10, 40)] == ["lt5", "lt5", "lt5", "5to9", "5to9", "10plus", "10plus"]


def test_numstat_parsing_handles_binary_and_renames():
    rows = parse_numstat("12\t3\tsrc/a.py\n-\t-\tlogo.png\n5\t0\tdocs/{old => new}/x.md\n")
    assert rows == [("src/a.py", 12, 3), ("logo.png", 0, 0), ("docs/new/x.md", 5, 0)]


def test_commit_normalisation_accepts_the_shapes_the_other_tracks_use():
    a = normalise_commit({"message": "Fix x", "files": [{"path": "a.py", "additions": 4, "deletions": 1}, {"path": "tests/test_a.py", "additions": 9}]})
    assert (a.additions, a.deletions, a.files_changed, a.touches_tests) == (13, 1, 2, True)
    b = normalise_commit({"subject": "Fix x", "body": "because y", "numstat": "3\t2\tsrc/q.py\n"})
    assert b.message.startswith("Fix x") and b.lines_changed == 5 and not b.touches_tests
    c = normalise_commit({"message": "m", "additions": 300, "deletions": 20, "files_changed": 7})
    assert c.facts() == {"size_bucket": "large", "touches_tests": False}
    assert normalise_commit("just a message").has_stat is False
    with pytest.raises(TypeError):
        normalise_commit(42)


def test_event_normalisation_accepts_iso_graph_and_counts():
    e = normalise_event({"subject": "Sync", "start": {"dateTime": "2026-11-02T10:00:00"}, "end": {"dateTime": "2026-11-02T11:30:00"},
                         "attendees": [1, 2, 3, 4, 5, 6], "recurrence": {"pattern": "weekly"}})
    assert e.duration_min == 90 and e.attendee_count == 6 and e.recurring
    assert e.facts() == {"recurring": True, "duration_bucket": "90to179", "attendee_bucket": "5to9"}
    assert normalise_event({"title": "x", "attendee_count": 12}).attendee_count == 12
    assert normalise_event({"title": "x", "all_day": True}).facts()["duration_bucket"] == "allday"


def test_rules_output_has_exactly_the_contract_keys_and_vocab():
    c = rules.digest_commit({"message": "Add retry to the uploader", "files": ["up.py"]})
    e = rules.digest_event({"title": "Team standup", "attendees": 8, "duration_min": 15})
    assert tuple(c) == COMMIT_KEYS and tuple(e) == EVENT_KEYS


@pytest.mark.parametrize("msg,files,want", [
    ("Revert \"Switch to async\"", ["a.py"], "revert"),
    ("feat(api): add pagination", ["api.py"], "feature"),
    ("fix: crash when list is empty", ["a.py"], "fix"),
    ("chore: bump deps", ["package.json"], "chore"),
    ("anything", ["tests/test_a.py", "tests/test_b.py"], "test"),
    ("update the guide", ["docs/guide.md"], "docs"),
    ("Rename Foo to Bar everywhere", ["a.py", "b.py"], "refactor"),
    ("wip", ["a.py"], "other"),
])
def test_commit_category_rules(msg, files, want):
    assert rules.digest_commit({"message": msg, "files": files})["category"] == want


def test_commit_risk_rules():
    big = {"message": "Rewrite the importer", "additions": 2000, "deletions": 900}
    assert rules.digest_commit(big)["risk"] == "high"
    assert rules.digest_commit({"message": "Fix typo", "files": ["README.md"], "additions": 1, "deletions": 1})["risk"] == "low"
    assert rules.digest_commit({"message": "Change session timeout", "files": ["auth/session.py"], "additions": 3, "deletions": 1})["risk"] == "high"
    assert rules.digest_commit({"message": "Add export button", "files": ["ui/export.py"], "additions": 80, "deletions": 4})["risk"] == "medium"


def test_message_quality_rules():
    q = lambda m: rules.digest_commit({"message": m})["message_quality"]  # noqa: E731
    assert q("wip") == "vague" and q("fixes") == "vague" and q("update stuff") == "vague"
    assert q("Add retry with backoff to the upload client") == "ok"
    assert q("Fix duplicate sends\n\nThe worker re-queued the job before the first attempt finished, so slow replies sent twice.") == "clear"


@pytest.mark.parametrize("title,att,mins,want", [
    ("1:1 with Sam", 2, 30, "one_to_one"), ("Daily standup", 8, 15, "team_meeting"), ("Design review: search", 5, 60, "review"),
    ("Focus time", 1, 120, "focus"), ("Team lunch", 12, 60, "social"), ("Submit expenses", 0, 30, "admin"),
    ("Call with Acme customer", 3, 45, "external"), ("Train to Glasgow", 0, 180, "travel"), ("Hold", 1, 60, "unknown"),
])
def test_event_category_rules(title, att, mins, want):
    assert rules.digest_event({"title": title, "attendees": att, "duration_min": mins})["category"] == want


def test_event_needs_prep_follows_category():
    assert rules.digest_event({"title": "Customer discovery call", "attendees": 3})["needs_prep"] is True
    assert rules.digest_event({"title": "Focus time", "attendees": 1})["needs_prep"] is False
    assert rules.digest_event({"title": "Daily standup", "attendees": 8})["needs_prep"] is False
