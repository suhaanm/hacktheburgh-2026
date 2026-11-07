"""Permission leases (BGA-1 reference): scope, expiry, revocation, narrowing, and hostile inputs."""
from __future__ import annotations

import json
import re
import threading

import pytest
from clicky_lift import Lease, LeaseBook, LeaseError, LeaseLimits, StopReason

AUDIT_TOKEN = re.compile(r"^[a-z0-9_.:\-]{1,40}$")   # what AuditLog.redact_meta keeps readable


def make(clock, **kw):
    base = {"lease_id": "ls_a", "holder": "child_1", "tools": {"read_file", "git_log"}, "ttl_s": 60, "max_steps": 5,
            "clock": clock}
    base.update(kw)
    return Lease(**base)


# ---------------------------------------------------------------- the happy path and the budgets
def test_in_scope_tool_is_allowed_and_counts_a_step(clock):
    ls = make(clock)
    d = ls.check("read_file")
    assert d.allowed and d.code == "ok" and d.step == 1 and d.remaining_steps == 4 and d.remaining_s == pytest.approx(60)
    assert ls.poll() == "active"


def test_step_cap_stops_the_lease_after_the_last_step(clock):
    ls = make(clock, max_steps=2)
    assert ls.check("read_file").allowed and ls.check("git_log").allowed
    assert ls.poll() == "stopped"                      # exhausted as soon as the last step is used
    d = ls.check("read_file")
    assert not d.allowed and d.code == StopReason.MAX_STEPS and d.remaining_steps == 0


def test_expiry_is_exact_and_permanent(clock):
    ls = make(clock, ttl_s=10)
    clock.advance(9)
    assert ls.check("read_file").allowed
    clock.advance(1)                                    # now == deadline: expired (the lease is open at the far end)
    d = ls.check("read_file")
    assert not d.allowed and d.code == StopReason.EXPIRED
    clock.t = 0.0                                       # even a clock that goes back does not revive it
    assert ls.check("read_file").code == StopReason.EXPIRED and ls.poll() == "stopped"


def test_revoke_is_immediate_idempotent_and_first_reason_wins(clock):
    ls = make(clock)
    assert ls.revoke("operator_stop") is True
    assert ls.revoke("something_else") is False
    d = ls.check("read_file")
    assert not d.allowed and d.code == "operator_stop"
    assert ls.snapshot()["state"] == "revoked" and ls.snapshot()["stop_reason"] == "operator_stop"


def test_revoke_reason_that_is_not_a_token_falls_back(clock):
    ls = make(clock)
    ls.revoke("Not A Token!\n")
    assert ls.snapshot()["stop_reason"] == StopReason.REVOKED


def test_scope_violation_stops_by_default_and_names_only_safe_tools(clock):
    events = []
    ls = make(clock, on_event=events.append)
    d = ls.check("delete_file")                          # a well-formed name, just not in scope
    assert not d.allowed and d.code == StopReason.SCOPE_VIOLATION
    assert not ls.check("read_file").allowed             # stopped: later in-scope calls are refused too
    assert [e["kind"] for e in events] == ["lease_denied", "lease_stopped"]
    assert events[0]["tool"] == "delete_file"


def test_max_violations_lets_a_lease_survive_a_few_slips(clock):
    ls = make(clock, max_violations=3)
    assert not ls.check("nope").allowed and not ls.check("nope").allowed
    assert ls.check("read_file").allowed                 # still alive after two violations
    assert not ls.check("nope").allowed                  # the third stops it
    assert not ls.check("read_file").allowed and ls.snapshot()["stop_reason"] == StopReason.SCOPE_VIOLATION


def test_denied_tools_override_the_scope_and_cannot_empty_it(clock):
    ls = make(clock, denied_tools={"git_log"})
    assert not ls.check("git_log").allowed
    with pytest.raises(LeaseError):
        make(clock, tools={"git_log"}, denied_tools={"git_log"})


# ---------------------------------------------------------------- kill switch and clock faults
def test_kill_flag_stops_the_lease_and_it_stays_stopped(clock):
    flag = {"on": False}
    ls = make(clock, killed=lambda: flag["on"])
    assert ls.check("read_file").allowed
    flag["on"] = True
    assert ls.check("read_file").code == StopReason.KILL_FLAG
    flag["on"] = False                                   # clearing the flag does not resurrect: a new lease is needed
    assert not ls.check("read_file").allowed


def test_unreadable_kill_flag_counts_as_set(clock):
    def boom() -> bool:
        raise OSError("disk gone")

    assert make(clock, killed=boom).check("read_file").code == StopReason.KILL_FLAG


def test_a_clock_that_runs_backwards_never_extends_the_lease(clock):
    ls = make(clock, ttl_s=10)
    clock.advance(6)
    assert ls.check("read_file").allowed
    clock.t = 0.0                                        # clock rewound by an hour
    d = ls.check("read_file")
    assert d.allowed and d.remaining_s == pytest.approx(4)   # time did not go back
    clock.t = 1011.0
    assert ls.check("read_file").code == StopReason.EXPIRED


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "soon", None, True])
def test_a_bad_clock_reading_stops_the_lease(clock, bad):
    ls = make(clock)
    clock.t = bad                                        # type: ignore[assignment]
    assert ls.check("read_file").code == StopReason.CLOCK_ERROR


def test_a_clock_that_raises_stops_the_lease(clock):
    ls = make(clock)
    ls._clock = lambda: (_ for _ in ()).throw(RuntimeError("no clock"))
    assert ls.check("read_file").code == StopReason.CLOCK_ERROR


# ---------------------------------------------------------------- hostile input
class _EvilStr(str):
    def __eq__(self, other):          # claims to equal anything
        return True

    def __hash__(self):
        return hash("read_file")


class _Boom:
    def __eq__(self, other):
        raise AssertionError("must never be compared")

    def __hash__(self):
        raise AssertionError("must never be hashed")

    def __str__(self):
        raise AssertionError("must never be stringified")


HOSTILE_TOOLS = [
    "READ_FILE",                       # case is not folded
    "read_file ",                      # trailing space
    "read_file\n",                     # trailing newline slips past a naive `$`
    "read_file\x00",
    "read_fi\u200ble",                 # zero-width space inside
    "r\u0435ad_file",                  # Cyrillic e
    "read\uff3ffile",                  # full-width underscore
    "../../etc/passwd",
    "read_file; rm -rf /",
    "a" * 5000,
    "",
    None, 7, 7.5, True, b"read_file", ["read_file"], {"read_file"}, ("read_file",),
    _EvilStr("read_file"),             # a str subclass that lies about equality
    _Boom(),
]


@pytest.mark.parametrize("tool", HOSTILE_TOOLS, ids=lambda t: type(t).__name__ + ":" + repr(t)[:20])
def test_hostile_tool_names_are_refused_without_raising_and_never_echoed(clock, tool):
    events = []
    ls = make(clock, on_event=events.append)
    d = ls.check(tool)
    assert d.allowed is False and d.code == StopReason.SCOPE_VIOLATION
    assert ls.poll() == "stopped"
    for e in events:
        assert e.get("tool", "invalid") == "invalid"       # raw text never reaches the audit stream
        assert all(isinstance(v, (int, float)) or AUDIT_TOKEN.match(v) for v in e.values())


def test_construction_rejects_hostile_parameters(clock):
    bad_tools = [[], "read_file", b"read_file", ["Read File"], ["ok", 5], [_EvilStr("read_file")], ["x" * 41],
                 [f"t{i}" for i in range(40)]]
    for tools in bad_tools:
        with pytest.raises(LeaseError):
            make(clock, tools=tools)
    for ttl in (0, -1, float("nan"), float("inf"), True, "60", None, 10**9):
        with pytest.raises(LeaseError):
            make(clock, ttl_s=ttl)
    for steps in (0, -3, 2.5, True, "5", None, 10**6):
        with pytest.raises(LeaseError):
            make(clock, max_steps=steps)
    for ident in ("", "UPPER", "has space", "x" * 41, "a/b", "a\n", None, 5):
        with pytest.raises(LeaseError):
            make(clock, lease_id=ident)
        with pytest.raises(LeaseError):
            make(clock, holder=ident)
    with pytest.raises(LeaseError):
        make(lambda: float("nan"))                       # the clock must be sane at issue time


def test_record_fails_closed_on_unknown_or_hostile_verdicts(clock):
    class Verdicty:
        verdict = _EvilStr("success")

    class Angry:
        @property
        def verdict(self):
            raise RuntimeError("no")

    for v in ("SUCCESS", "ok", "", None, 7, Verdicty(), Angry(), _EvilStr("success"), "success\n"):
        ls = make(clock)
        assert ls.record(v) is False, repr(v)
        assert ls.snapshot()["stop_reason"] == StopReason.VERIFICATION


def test_record_continues_on_success_and_skipped_and_stops_on_the_rest(clock):
    class Post:
        def __init__(self, verdict):
            self.verdict = verdict

    for verdict, still_active in (("success", True), ("skipped", True), ("failed", False), ("uncertain", False),
                                  ("blocked_by_prompt", False)):
        ls = make(clock)
        assert ls.record(Post(verdict)) is still_active
        assert ls.record(verdict) is still_active
    # a stricter lease: uncertain may continue only if the caller chose so
    lenient = make(clock, stop_on_verdicts={"failed", "blocked_by_prompt"})
    assert lenient.record("uncertain") is True


# ---------------------------------------------------------------- narrowing and cascade
def test_a_child_can_only_narrow_its_parent(clock):
    book = LeaseBook(clock=clock)
    parent = book.issue(holder="parent", tools={"read_file", "git_log", "run_python"}, ttl_s=100, max_steps=20,
                        denied_tools={"run_python"})
    child = book.issue(holder="child_1", tools={"read_file"}, ttl_s=50, max_steps=10, parent=parent)
    assert child.tools == {"read_file"} and child.denied_tools == {"run_python"}
    with pytest.raises(LeaseError):
        book.issue(holder="c2", tools={"read_file", "write_workspace"}, ttl_s=50, max_steps=5, parent=parent)  # extra tool
    with pytest.raises(LeaseError):
        book.issue(holder="c3", tools={"run_python"}, ttl_s=50, max_steps=5, parent=parent)                    # denied above
    with pytest.raises(LeaseError):
        book.issue(holder="c4", tools={"read_file"}, ttl_s=101, max_steps=5, parent=parent)                    # outlives parent
    with pytest.raises(LeaseError):
        book.issue(holder="c5", tools={"read_file"}, ttl_s=50, max_steps=21, parent=parent)                    # more steps
    clock.advance(60)
    with pytest.raises(LeaseError):
        book.issue(holder="c6", tools={"read_file"}, ttl_s=50, max_steps=5, parent=parent)                     # 40 s left


def test_a_child_cannot_be_issued_from_a_stopped_or_unknown_parent(clock):
    book = LeaseBook(clock=clock)
    parent = book.issue(holder="parent", tools={"read_file"}, ttl_s=100, max_steps=5)
    parent.revoke()
    with pytest.raises(LeaseError):
        book.issue(holder="c", tools={"read_file"}, ttl_s=10, max_steps=1, parent=parent)
    with pytest.raises(LeaseError):
        book.issue(holder="c", tools={"read_file"}, ttl_s=10, max_steps=1, parent="ls_nope")


def test_revoking_the_parent_stops_children_on_their_next_check(clock):
    book = LeaseBook(clock=clock)
    parent = book.issue(holder="parent", tools={"read_file", "git_log"}, ttl_s=100, max_steps=20)
    kids = [book.issue(holder=f"child_{i}", tools={"read_file"}, ttl_s=50, max_steps=5, parent=parent) for i in range(3)]
    grandkid = book.issue(holder="grandchild", tools={"read_file"}, ttl_s=10, max_steps=2, parent=kids[0])
    assert all(k.check("read_file").allowed for k in kids)
    parent.revoke()                                      # no book call needed: children notice at once
    for k in (*kids, grandkid):
        d = k.check("read_file")
        assert not d.allowed and d.code == StopReason.PARENT_STOPPED


def test_book_revoke_cascades_and_revoke_all_counts(clock):
    book = LeaseBook(clock=clock)
    parent = book.issue(holder="parent", tools={"read_file"}, ttl_s=100, max_steps=20)
    kid = book.issue(holder="kid", tools={"read_file"}, ttl_s=50, max_steps=5, parent=parent)
    other = book.issue(holder="other", tools={"git_log"}, ttl_s=50, max_steps=5)
    assert book.revoke(parent.lease_id) is True
    assert kid.snapshot()["stop_reason"] == StopReason.PARENT_STOPPED and other.is_active()
    assert book.revoke("ls_unknown") is False and book.revoke(None) is False  # type: ignore[arg-type]
    assert book.revoke_all("kill_switch") == 1 and not other.is_active()
    assert book.active() == []


def test_book_caps_active_leases_and_rejects_duplicate_ids(clock):
    book = LeaseBook(clock=clock, max_active=2)
    book.issue(holder="a", tools={"read_file"}, ttl_s=10, max_steps=1, lease_id="ls_1")
    book.issue(holder="b", tools={"read_file"}, ttl_s=10, max_steps=1)
    with pytest.raises(LeaseError):
        book.issue(holder="c", tools={"read_file"}, ttl_s=10, max_steps=1)
    clock.advance(11)                                    # both expired: room again
    book.issue(holder="d", tools={"read_file"}, ttl_s=10, max_steps=1, lease_id="ls_2")
    with pytest.raises(LeaseError):
        book.issue(holder="e", tools={"read_file"}, ttl_s=10, max_steps=1, lease_id="ls_2")


def test_limits_cap_ttl_and_steps(clock):
    book = LeaseBook(clock=clock, limits=LeaseLimits(max_ttl_s=100, max_steps=10, max_tools=2))
    with pytest.raises(LeaseError):
        book.issue(holder="a", tools={"read_file"}, ttl_s=101, max_steps=1)
    with pytest.raises(LeaseError):
        book.issue(holder="a", tools={"read_file"}, ttl_s=10, max_steps=11)
    with pytest.raises(LeaseError):
        book.issue(holder="a", tools={"read_file", "git_log", "list_dir"}, ttl_s=10, max_steps=1)


def test_a_lease_cannot_be_widened_after_issue(clock):
    ls = make(clock)
    for name in ("extend", "widen", "add_tool", "grant", "set_ttl"):
        assert not hasattr(ls, name)
    assert isinstance(ls.tools, frozenset)
    with pytest.raises(AttributeError):
        ls.tools.add("run_python")                       # type: ignore[attr-defined]


# ---------------------------------------------------------------- audit and reporting
def test_events_and_snapshots_are_audit_safe_and_json_ready(clock):
    events = []
    book = LeaseBook(clock=clock, on_event=events.append)
    parent = book.issue(holder="parent", tools={"read_file"}, ttl_s=60, max_steps=3)
    child = book.issue(holder="child_1", tools={"read_file"}, ttl_s=30, max_steps=2, parent=parent)
    child.check("read_file")
    child.check("evil\u202etool")
    parent.revoke("operator_stop")
    clock.advance(5)
    for e in events:
        for k, v in e.items():
            assert isinstance(v, (int, float)) or AUDIT_TOKEN.match(v), (k, v)
    json.dumps(book.snapshots())
    meta = child.audit_meta()
    assert set(meta) == {"state", "stop_reason", "steps", "remaining_s"}
    assert all(isinstance(v, (int, float)) or AUDIT_TOKEN.match(v) for v in meta.values())
    assert [e["kind"] for e in events].count("lease_issued") == 2


def test_snapshot_gives_a_countdown_for_the_agents_screen(clock):
    ls = make(clock, ttl_s=60)
    clock.advance(12.34)
    snap = ls.snapshot()
    assert snap["state"] == "active" and snap["remaining_s"] == pytest.approx(47.7, abs=0.05)
    assert snap["tools"] == ["git_log", "read_file"] and snap["steps_used"] == 0


def test_a_failing_event_sink_never_breaks_enforcement(clock):
    def sink(_):
        raise RuntimeError("sink down")

    ls = make(clock, on_event=sink)
    assert ls.check("nope").allowed is False             # still denies
    assert ls.event_errors >= 1 and ls.poll() == "stopped"


def test_event_sink_may_call_back_into_the_lease_and_book(clock):
    book = LeaseBook(clock=clock)
    seen = []
    book._on_event = lambda e: seen.append((book.active(), book.snapshots()))
    ls = book.issue(holder="a", tools={"read_file"}, ttl_s=5, max_steps=1)
    ls.check("nope")                                       # the sink re-enters the book while events fire
    assert seen


# ---------------------------------------------------------------- concurrency
def test_concurrent_checks_never_exceed_the_step_cap(clock):
    ls = make(clock, max_steps=100, ttl_s=60)
    allowed = []
    lock = threading.Lock()

    def worker():
        n = 0
        for _ in range(500):
            if ls.check("read_file").allowed:
                n += 1
        with lock:
            allowed.append(n)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(allowed) == 100
    assert ls.poll() == "stopped"


def test_revoke_during_a_busy_loop_wins_immediately(clock):
    ls = make(clock, max_steps=10**6, limits=LeaseLimits(max_steps=10**6))
    stop = threading.Event()
    revoked = threading.Event()
    late = []

    def worker():
        while not stop.is_set():
            revoke_already_returned = revoked.is_set()      # read BEFORE the call: a check that began after revoke()
            d = ls.check("read_file")                       # had returned must never be allowed
            if revoke_already_returned and d.allowed:
                late.append(1)

    t = threading.Thread(target=worker)
    t.start()
    ls.revoke("operator_stop")
    revoked.set()
    stop.set()
    t.join()
    assert late == []
    assert ls.snapshot()["stop_reason"] == "operator_stop"


def test_a_parent_can_be_named_by_id_and_stop_events_fire_once(clock):
    events = []
    book = LeaseBook(clock=clock, on_event=events.append)
    book.issue(holder="parent", tools={"read_file", "git_log"}, ttl_s=100, max_steps=20, lease_id="ls_root")
    child = book.issue(holder="child_1", tools={"read_file"}, ttl_s=10, max_steps=5, parent="ls_root")
    assert child.parent is book.get("ls_root")
    clock.advance(11)
    for _ in range(5):                                   # polling, checking and snapshotting a dead lease is quiet
        child.poll()
        child.check("read_file")
        child.snapshot()
    stops = [e for e in events if e["kind"] == "lease_stopped" and e["holder"] == "child_1"]
    assert len(stops) == 1 and stops[0]["code"] == StopReason.EXPIRED
