"""Cue over the REAL coach brain: events in the store, ``CoachBrain.snapshot`` read through the adapter, the decision and the ledger out."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from understudy_engine.coach import CoachBrain, StuckScorer
from understudy_engine.cue.context import BrainProvider
from understudy_engine.cue.live import LiveCue
from understudy_engine.store import EventStore, validate_row

T0 = datetime(2026, 11, 9, 9, 0, 0, tzinfo=timezone.utc)
N = [0]


def ev(dt, typ, zone=None, task="t_i1", person="p_int", **meta):
    N[0] += 1
    row = {"schema": 1, "id": f"int{N[0]:07d}", "t": (T0 + timedelta(seconds=dt)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "origin": "synthetic", "actor": "human",
           "person": person, "role": "benefits-processor", "source": "browser", "type": typ, "task_id": task}
    m = dict(meta)
    if zone:
        m["zone"] = zone
    if m:
        row["meta"] = m
    return validate_row(row)


def first_calculator(t=12):
    return [ev(0, "task_start"), ev(1, "focus", "doc"), ev(8, "scroll", "doc"),
            ev(t, "nav", "calc_site", site="calc1"), ev(t + 6, "click", "household_form"), ev(t + 14, "click", "household_form"),
            ev(t + 24, "focus", "calc_result"), ev(t + 30, "scroll", "calc_result"), ev(t + 31, "progress", kind="result_read")]


def test_cue_reads_the_real_brain_snapshot_and_ends_up_with_a_grounded_cue_and_a_ledger_row(tmp_path):
    store = EventStore(tmp_path / "data")
    for e in first_calculator():
        store.append(e)
    brain = CoachBrain(store, scorer=StuckScorer(tmp_path, fit=False))
    t_prog = (T0 + timedelta(seconds=43)).timestamp()
    live = LiveCue(provider=BrainProvider(brain))
    # the coach's own snapshot is read-only and carries cogs, last progress and the stuck reading
    snap = brain.snapshot("p_int", t_prog + 100)
    assert snap.person == "p_int" and snap.role == "benefits-processor" and [c.id for c in snap.cogs][:2] == ["READ", "OPEN_CALCULATOR"] and snap.p_source == "rule"
    seen = []
    for k in range(60):
        now = t_prog + 20 + 2.5 * k
        d = live.next("p_int", now=now, quiet_s=6.0)["data"]
        seen.append((d["kind"], d["why"]["reasons"][0]))
        if d["kind"] == "cue":
            break
    assert d["kind"] == "cue", seen[-5:]
    assert d["step"]["id"] in ("cliff_a", "calc_b") and d["why"]["p_stuck"] >= 0.4 and d["source"] == "rule"
    assert d["manifest"]["inputs_read"][:2] == ["snapshot", "p_stuck"] and "snapshot" not in (d["stale"] or [])
    # nothing was written to the event store or moved in the brain by reading
    assert brain.snapshot("p_int", t_prog + 100).last_progress_t == snap.last_progress_t
    # the cued step is done a few seconds later: one assisted ledger row
    store.append(ev(80, "click", "cliff_button"))
    store.append(ev(84, "scroll", "cliff_panel"))
    store.append(ev(85, "progress", kind="cliff_checked"))
    now2 = (T0 + timedelta(seconds=87)).timestamp()
    out = live.next("p_int", now=now2, quiet_s=6.0)["data"]
    rows = live.ledger.rows("p_int", "assist")
    assert out["kind"] == "none" and out["why"]["reasons"][0] in ("step_done", "progress")
    assert rows and rows[-1]["skill"] in ("check-the-cliff", "enter-household-once") and rows[-1]["origin"] == "synthetic"
    assert rows[-1]["outcome"] in ("assisted", "clean") and rows[-1]["role"] == "benefits-processor"
