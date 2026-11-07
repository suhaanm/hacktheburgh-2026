"""Supervisor tests (AGT-2): stop within 1 s without a model, stale results dropped, kill flag, yield."""
from __future__ import annotations

import threading
import time

import pytest

from understudy_agent.supervisor import (
    Cancelled, HumanInputSignal, KillSwitchActive, Supervisor,
)


@pytest.fixture
def sup(tmp_path):
    s = Supervisor(kill_flag=tmp_path / "KILL", abandon_grace_s=0.2, kill_poll_interval_s=0.0)
    yield s
    s.close()


def test_generation_is_monotonic(sup):
    g0 = sup.generation
    h1 = sup.submit(lambda ctx: 1)
    assert h1.wait(2) and h1.state == "done" and h1.result == 1
    g1 = sup.generation
    sup.stop()
    g2 = sup.generation
    h2 = sup.submit(lambda ctx: 2)
    assert h2.wait(2)
    assert g0 < g1 < g2 < sup.generation
    assert h1.generation < h2.generation


def test_new_submit_supersedes_running_and_drops_its_stale_result(sup):
    started = threading.Event()

    def slow_uncooperative(ctx):
        started.set()
        time.sleep(0.6)  # ignores cancellation, like a blocking model call
        return "OLD"

    old = sup.submit(slow_uncooperative, name="old")
    assert started.wait(2)
    new = sup.submit(lambda ctx: "NEW", name="new")
    assert old.wait(1) and old.state == "superseded" and old.result is None
    assert new.wait(3) and new.state == "done" and new.result == "NEW"
    time.sleep(0.8)  # let the old thread finish; its result must never surface
    assert old.result is None and old.state == "superseded"
    assert sup.stale_results_dropped >= 1


def test_pending_request_is_replaceable(sup):
    gate = threading.Event()
    first = sup.submit(lambda ctx: gate.wait(2) and "first", name="first")
    time.sleep(0.1)
    mid = sup.submit(lambda ctx: "mid", name="mid")
    last = sup.submit(lambda ctx: "last", name="last")
    assert mid.wait(1) and mid.state == "superseded"
    gate.set()
    assert last.wait(3) and last.state == "done" and last.result == "last"
    assert first.state == "superseded"


def test_stop_wins_within_one_second_even_if_task_ignores_cancel(sup):
    """The task is stuck in a 3 s 'model call' that never checks cancellation."""
    model_calls = []

    def fake_model_call():
        model_calls.append(1)
        time.sleep(3.0)

    started = threading.Event()

    def task(ctx):
        started.set()
        fake_model_call()
        return "late result"

    h = sup.submit(task)
    assert started.wait(2)
    n_before = len(model_calls)
    t0 = time.monotonic()
    out = sup.stop("user pressed stop")
    elapsed = time.monotonic() - t0
    assert out["stopped"] is True
    assert elapsed < 0.1, f"stop() took {elapsed:.3f}s"
    assert h.wait(1.0 - elapsed) and h.state == "stopped"
    assert len(model_calls) == n_before  # stop never triggered another model call
    assert sup.snapshot()["state"] == "stopped"


def test_next_task_not_blocked_by_stuck_worker(sup):
    started = threading.Event()

    def stuck(ctx):
        started.set()
        time.sleep(1.5)
        return "stuck-result"

    old = sup.submit(stuck)
    assert started.wait(2)
    sup.stop()
    t0 = time.monotonic()
    new = sup.submit(lambda ctx: "fresh")
    assert new.wait(2.5) and new.result == "fresh"
    assert time.monotonic() - t0 < 1.5  # picked up by a replacement worker after the grace period
    assert old.state == "stopped"
    time.sleep(1.4)
    assert old.result is None


def test_cooperative_task_sees_cancel_quickly(sup):
    seen = {}
    started = threading.Event()

    def task(ctx):
        started.set()
        seen["slept_full"] = ctx.sleep(5.0)
        seen["current"] = ctx.is_current()
        ctx.check()  # raises Cancelled
        return "unreachable"

    h = sup.submit(task)
    assert started.wait(2)
    t0 = time.monotonic()
    sup.stop()
    assert h.wait(1) and h.state == "stopped"
    deadline = time.monotonic() + 1
    while "current" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    assert seen == {"slept_full": False, "current": False}
    assert time.monotonic() - t0 < 1.0


def test_deadline_cancels_overdue_task(sup):
    def task(ctx):
        while ctx.sleep(0.05):
            pass
        return "x"

    h = sup.submit(task, deadline_s=0.25)
    assert h.wait(2) and h.state == "timeout" and "deadline" in h.reason
    assert sup.snapshot()["state"] == "timeout"


def test_task_exception_is_recorded_not_raised(sup):
    def boom(ctx):
        raise ValueError("bad page")

    h = sup.submit(boom)
    assert h.wait(2) and h.state == "failed" and isinstance(h.error, ValueError)
    ok = sup.submit(lambda ctx: "still works")
    assert ok.wait(2) and ok.state == "done"


def test_kill_flag_stops_running_task_and_blocks_new_ones(sup, tmp_path):
    flag = tmp_path / "KILL"
    started = threading.Event()

    def task(ctx):
        started.set()
        while ctx.sleep(0.05):
            pass

    h = sup.submit(task)
    assert started.wait(2)
    t0 = time.monotonic()
    flag.write_text("1")
    assert h.wait(1.0) and h.state == "killed"
    assert time.monotonic() - t0 < 1.0
    with pytest.raises(KillSwitchActive):
        sup.submit(lambda ctx: 1)
    assert sup.state == "killed"
    flag.unlink()
    h2 = sup.submit(lambda ctx: "back")
    assert h2.wait(2) and h2.result == "back"


def test_stop_hooks_run_without_blocking(sup):
    ran = threading.Event()

    def slow_hook():
        time.sleep(0.3)
        ran.set()

    sup.add_stop_hook(slow_hook)
    t0 = time.monotonic()
    sup.stop()
    assert time.monotonic() - t0 < 0.1  # hooks do not delay stop
    assert ran.wait(2)


def test_human_input_yields_background_task_within_one_second(tmp_path):
    human = HumanInputSignal()
    s = Supervisor(kill_flag=tmp_path / "KILL", human_input=human)
    try:
        started = threading.Event()

        def bg(ctx):
            started.set()
            while ctx.sleep(0.05):
                pass

        h = s.submit(bg, yield_on_human=True)
        assert started.wait(2)
        t0 = time.monotonic()
        human.signal()
        assert h.wait(1.0)
        assert h.state == "yielded" and time.monotonic() - t0 < 1.0
        assert s.snapshot()["state"] == "yielded"
        assert not human.quiet_for(5.0) and human.quiet_for(0.0)
    finally:
        s.close()


def test_human_input_does_not_touch_foreground_task(tmp_path):
    human = HumanInputSignal()
    s = Supervisor(kill_flag=tmp_path / "KILL", human_input=human)
    try:
        h = s.submit(lambda ctx: (ctx.sleep(0.4), "fg")[1], yield_on_human=False)
        time.sleep(0.1)
        human.signal()
        assert h.wait(2) and h.state == "done" and h.result == "fg"
    finally:
        s.close()


def test_many_rapid_submits_only_last_completes(sup):
    handles = [sup.submit(lambda ctx, i=i: (ctx.sleep(0.05), i)[1]) for i in range(40)]
    last = handles[-1]
    assert last.wait(5) and last.state == "done" and last.result == 39
    time.sleep(0.2)
    done = [h for h in handles if h.state == "done"]
    assert done == [last]
    gens = [h.generation for h in handles]
    assert gens == sorted(gens) and len(set(gens)) == len(gens)


def test_cancelled_exception_inside_task_is_not_a_failure(sup):
    started = threading.Event()

    def task(ctx):
        started.set()
        ctx.sleep(5)
        ctx.check()

    h = sup.submit(task)
    assert started.wait(2)
    sup.stop()
    assert h.wait(1) and h.state == "stopped" and h.error is None
