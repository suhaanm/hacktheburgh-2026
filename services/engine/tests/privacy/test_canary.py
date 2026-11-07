from __future__ import annotations

import base64
import json
import urllib.parse

import pytest

from understudy_engine.privacy import canary, egress, ledger
from understudy_engine.privacy.canary import Planted, assert_no_canaries, plant, scan
from understudy_engine.privacy.purposes import CalendarSuggestionWording, GitHabitWording
from understudy_engine.privacy.testing import CapturingPort, canary_flow


def calendar_fixture():
    return {"owner": {"name": "Ada Lovelace", "email": "ada@corp.example"},
            "events": [
                {"title": "Quarterly planning", "start": "2026-11-02T09:00", "end": "2026-11-02T10:00",
                 "attendees": ["Bob Smith", "Carol Jones"], "organizer": "Dan Wu", "location": "Room 4", "customer": "Acme Ltd"},
                {"title": "1:1", "start": "2026-11-02T11:00", "end": "2026-11-02T11:30", "attendees": ["Bob Smith"]},
            ]}


def git_fixture():
    return {"repo": "/Users/ada/Projects/payroll",
            "commits": [{"author": "Ada Lovelace", "email": "ada@corp.example", "message": "fix Acme payroll rounding",
                         "files": [{"path": "src/payroll/round.py", "added": 3, "deleted": 1}], "time": "2026-11-02T09:00"}]}


# --------------------------------------------------------------------------- planting
def test_plant_replaces_every_name_email_title_path_message_and_customer_with_unique_tokens():
    fx = calendar_fixture()
    p = plant(fx, seed=1)
    flat = json.dumps(fx)
    for original in ("Ada Lovelace", "ada@corp.example", "Quarterly planning", "Bob Smith", "Carol Jones", "Dan Wu", "Room 4", "Acme Ltd"):
        assert original not in flat
    assert fx["events"][0]["start"] == "2026-11-02T09:00"          # numbers and times untouched
    kinds = p.by_kind()
    assert {"person_name", "email", "meeting_title", "customer_name"} <= set(kinds)
    values = [t.value for t in p.tokens]
    assert len(values) == len(set(values))                          # every token unique
    assert len(fx["events"][0]["attendees"]) == 2 and fx["events"][0]["attendees"][0] != fx["events"][0]["attendees"][1]


def test_plant_covers_git_paths_messages_and_repo_paths():
    fx = git_fixture()
    p = plant(fx, seed=2)
    kinds = p.by_kind()
    assert {"person_name", "email", "commit_message", "file_path"} <= set(kinds)
    assert fx["commits"][0]["files"][0]["added"] == 3
    assert fx["repo"].startswith("/Users/") and "payroll" not in fx["repo"]


def test_all_six_kinds_can_be_generated_by_hand():
    p = Planted(seed=3)
    vals = {k: p.make(k) for k in canary.KINDS}
    assert "@" in vals["email"] and vals["file_path"].startswith("/Users/") and " & " in vals["customer_name"]
    assert len(p) == 6 and set(p.by_kind()) == set(canary.KINDS)


def test_same_seed_same_tokens_different_seed_different_tokens():
    a, b, c = Planted(5), Planted(5), Planted(6)
    assert [a.person_name(), a.email()] == [b.person_name(), b.email()]
    assert a.meeting_title() != c.meeting_title()


def test_append_mode_keeps_the_original_text_for_code_that_reads_keywords():
    fx = {"events": [{"title": "Weekly standup", "attendees": ["Bob"], "path": "tests/test_x.py"}]}
    plant(fx, mode="append")
    assert fx["events"][0]["title"].startswith("Weekly standup ") and fx["events"][0]["title"] != "Weekly standup"
    assert fx["events"][0]["path"].startswith("tests/test_x.py/")


def test_plant_refuses_fixtures_with_nothing_plantable():
    with pytest.raises(AssertionError, match="found nothing"):
        plant({"minutes": [30, 60], "kind": "focus"})


def test_add_text_registers_an_existing_sensitive_string():
    p = Planted()
    p.add_text("Ada Lovelace", "person_name")
    assert scan(CapturingPort_with("hello lovelace here"), p).leaked == 1
    assert scan(CapturingPort_with("hello world"), p).leaked == 0


# --------------------------------------------------------------------------- scanning
def CapturingPort_with(*texts):
    port = CapturingPort()
    for t in texts:
        port.plan([{"role": "user", "content": t}], None)
    return port


def one_token(kind="meeting_title", seed=0):
    p = Planted(seed)
    return p, p.make(kind)


@pytest.mark.parametrize("transform", [
    lambda s: s,
    lambda s: s.upper(),
    lambda s: s.lower(),
    lambda s: "".join(c if c.isalnum() else "_" for c in s),
    lambda s: "".join(c for c in s if c.isalnum()),
    lambda s: urllib.parse.quote(s),
    lambda s: base64.b64encode(s.encode()).decode(),
    lambda s: s.encode().hex(),
    lambda s: s[: len(s) // 2 + 6],          # truncated: still carries an invented word
])
@pytest.mark.parametrize("kind", canary.KINDS)
def test_scan_finds_a_token_through_common_rewrites(kind, transform):
    p, tok = one_token(kind)
    port = CapturingPort_with("context: " + transform(tok) + " end")
    r = scan(port, p)
    assert r.leaked == 1 and not r.ok, (kind, transform(tok))


def test_scan_is_clean_on_clean_bodies_and_counts_requests():
    p, _ = one_token()
    r = scan(CapturingPort_with("meeting_h 14", "focus_blocks_60 lt5", "a plain sentence"), p)
    assert r.ok and r.requests == 3 and r.planted == 1 and r.leaked == 0


def test_scan_accepts_ports_lists_strings_dicts_and_bytes():
    p, tok = one_token()
    for captured in (CapturingPort_with(tok), [CapturingPort_with(tok).requests[0]], tok, {"messages": [tok]}, tok.encode(), [tok, "x"]):
        assert scan(captured, p).leaked == 1


def test_assert_no_canaries_raises_naming_kind_and_request_number_not_a_vacuous_pass():
    p, tok = one_token("email")
    port = CapturingPort_with("fine", f"oops {tok}")
    with pytest.raises(AssertionError, match=r"email.*\[1\]"):
        assert_no_canaries(port, p)
    with pytest.raises(AssertionError, match="nothing was planted"):
        assert_no_canaries(port, Planted())
    clean = CapturingPort_with("fine")
    assert assert_no_canaries(clean, p, min_requests=1).ok
    with pytest.raises(AssertionError, match="at least 2"):
        assert_no_canaries(clean, p, min_requests=2)


def test_no_false_positive_on_ordinary_payload_text():
    p = Planted(9)
    for _ in range(30):
        p.make("person_name"), p.make("email"), p.make("meeting_title"), p.make("file_path"), p.make("commit_message"), p.make("customer_name")
    body = json.dumps({"template": "protect_focus_block", "role": "programmer", "learner": {"meeting_h": 14.08, "focus_blocks_60": "lt5"},
                       "text": "Try one 90 minute block of focus time on Tuesday and Thursday mornings."})
    assert scan(body, p).ok


# --------------------------------------------------------------------------- the kit on a real flow
def calendar_flow(fx, port):
    """A correct flow: events in, aggregates computed locally, only SafePayload numbers out through the guard."""
    ev = fx["events"]
    n = len(ev)
    long_ones = sum(1 for e in ev if e["end"][11:13] != e["start"][11:13])
    payload = CalendarSuggestionWording(template="protect_focus_block", role="programmer", risk="low",
                                        learner={"n_meetings": n, "focus_blocks_60": long_ones, "meeting_h": 1.5},
                                        expert={"focus_blocks_60": 9})
    return egress.send("calendar.suggestion_wording", payload, port=port).output


def leaky_flow(fx, port):
    """A buggy flow that bypasses the guard and sends a meeting title straight to the port."""
    port.plan([{"role": "user", "content": "Reword: " + fx["events"][0]["title"]}], None)


def leaky_via_attendees(fx, port):
    port.check("who is in " + ", ".join(fx["events"][0]["attendees"]), {"type": "object", "properties": {}})


def test_canary_flow_passes_a_flow_that_sends_only_through_the_guard_and_records_the_run():
    report = canary_flow("calendar.suggestions", calendar_fixture, calendar_flow, seed=11)
    assert report.ok and report.requests == 1 and report.planted >= 10
    s = ledger.canary_summary()
    assert s["runs"] == 1 and s["planted"] == report.planted and s["leaked"] == 0
    assert s["flows"][0]["flow"] == "calendar.suggestions" and s["last_run"]


def test_canary_flow_catches_a_flow_that_bypasses_the_guard_with_a_title():
    with pytest.raises(AssertionError) as ei:
        canary_flow("calendar.leaky", calendar_fixture, leaky_flow, seed=12)
    assert "bypass" in str(ei.value).lower() or "without going through egress" in str(ei.value)


def test_canary_flow_non_strict_reports_the_leak_instead_of_raising_for_the_eval_harness():
    report = canary_flow("calendar.leaky2", calendar_fixture, leaky_via_attendees, seed=13, strict=False)
    assert not report.ok and report.leaked >= 1 and {lk.kind for lk in report.leaks} == {"person_name"}
    assert ledger.canary_summary()["leaked"] >= 1


def test_canary_flow_needs_at_least_one_request_by_default():
    with pytest.raises(AssertionError, match="at least 1"):
        canary_flow("calendar.silent", calendar_fixture, lambda fx, port: None)
    assert canary_flow("calendar.silent2", calendar_fixture, lambda fx, port: None, min_requests=0).ok


def test_canary_flow_checks_the_ledger_one_line_per_call_and_flags_a_missing_line(monkeypatch):
    def flow(fx, port):
        calendar_flow(fx, port)
        calendar_flow(fx, port)

    assert canary_flow("calendar.twice", calendar_fixture, flow, min_requests=2).requests == 2
    real_append = ledger.append
    state = {"n": 0}

    def skip_second(entry):
        state["n"] += 1
        if state["n"] == 2:
            return {**entry, "id": "e_fake", "t": "x"}          # claims success but writes nothing
        return real_append(entry)

    monkeypatch.setattr(ledger, "append", skip_second)
    with pytest.raises(AssertionError, match="ledger line"):
        canary_flow("calendar.twice_broken", calendar_fixture, flow, min_requests=2)


def test_git_flow_through_the_guard_is_clean():
    def flow(fx, port):
        c = fx["commits"]
        egress.send("git.habit_wording", GitHabitWording(habit="no_tests", learner_ratio=len(c) / 3, expert_ratio=0.1, n_commits=len(c) + 10), port=port)

    assert canary_flow("git.habits", git_fixture, flow, seed=14).ok


# --------------------------------------------------------------------------- PRV-4: logs, audit, queue
def _fx():
    return {"events": [{"title": "Quarterly planning", "attendees": ["Bob Smith"]}]}


def _clean(fx, port):
    egress.send("calendar.suggestion_wording", dict(template="protect_focus_block", role="programmer", risk="low", learner={"n_meetings": 1}, expert={}), port=port)


def test_a_planted_token_in_the_audit_log_the_queue_or_a_log_file_is_found(data_dir):
    p = Planted(21)
    title = p.meeting_title()
    (data_dir / "queue").mkdir()
    (data_dir / "queue" / "q_01.json").write_text(json.dumps({"title": "Prepare " + title}))
    (data_dir / "audit.jsonl").write_text(json.dumps({"note": "clean"}) + "\n")
    (data_dir / "logs").mkdir()
    (data_dir / "logs" / "engine.log").write_text("started\n")
    r = canary.scan_artifacts(p, data_dir)
    assert r.leaked == 1 and r.requests == 3
    (data_dir / "queue" / "q_01.json").write_text(json.dumps({"title": "Prepare the weekly summary"}))
    assert canary.scan_artifacts(p, data_dir).ok


def test_missing_artifact_paths_are_skipped():
    assert canary.scan_artifacts(Planted(1), None).requests == 0


def test_log_capture_sees_every_logger_and_exception_text():
    import logging

    from understudy_engine.privacy.testing import LogCapture

    p, tok = one_token("file_path")
    with LogCapture() as logs:
        logging.getLogger("some.module").warning("opened %s", tok)
        try:
            raise ValueError("bad " + tok)
        except ValueError:
            logging.getLogger("other").exception("failed")
    assert scan(logs.texts, p).leaked == 1 and len(logs.records) == 2


def test_canary_flow_fails_when_a_flow_logs_a_planted_title():
    import logging

    def flow(fx, port):
        _clean(fx, port)
        logging.getLogger("calendar").info("handling %s", fx["events"][0]["title"])

    with pytest.raises(AssertionError, match="log records"):
        canary_flow("calendar.logs_title", _fx, flow)


def test_canary_flow_fails_when_a_flow_writes_a_title_into_the_audit_log_or_queue(data_dir):
    def flow(fx, port):
        _clean(fx, port)
        (data_dir / "queue").mkdir(exist_ok=True)
        (data_dir / "queue" / "q_x.json").write_text(json.dumps({"summary": fx["events"][0]["title"]}))

    with pytest.raises(AssertionError, match="PRV-4"):
        canary_flow("calendar.queue_title", _fx, flow)


def test_a_clean_flow_passes_the_artifact_checks_too():
    assert canary_flow("calendar.clean_artifacts", _fx, _clean).ok
