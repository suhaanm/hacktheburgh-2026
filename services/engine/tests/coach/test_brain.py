from __future__ import annotations

import pytest

from understudy_engine.coach import CoachBrain, CoachError, StuckScorer
from understudy_engine.policy.gate import GateParams
from understudy_engine.store import EventStore

from .helpers import T0, calc, cliff, copy_to_note, ev, expert_task, read, reconcile, signature_events


@pytest.fixture()
def store(tmp_path):
    return EventStore(tmp_path / "data")


@pytest.fixture()
def brain(store):
    return CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")


def run(brain, events, person="p_hand", **kw):
    """Feed events one at a time and ask for a decision after each. Returns [(event, decision)]."""
    out = []
    for i, e in enumerate(events):
        out.append((e, brain.next_step(person, e.t, events=events[: i + 1], **kw)))
    return out


def acts(trace):
    return [(e, d) for e, d in trace if d.action != "silent"]


def test_signature_case_ring_lands_on_the_cliff_button(brain):
    trace = run(brain, signature_events())
    fired = acts(trace)
    assert len(fired) == 1
    e, d = fired[0]
    assert d.action == "annotate" and d.trigger == "expert_policy" and d.level == "L1" and d.chip == "full"
    assert d.target == {"zone": "cliff_button", "label_hint": "Check cliff edges", "role_hint": "button", "site": "calc1"}
    assert d.message == "Check cliff edges before you copy this result."
    assert d.missed[0] == "cliff_a" and "reconcile" in d.missed and d.confidence >= 0.9
    assert d.why.startswith("Experts:") and "nudged near a limit" in d.why
    assert {"policy_violation", "critical_step_missed", "gate_act"} <= set(d.reason_codes)
    # it waited for a second consecutive signal: the first event of the copy was silent, the second acted
    copy_events = [x for x in trace if x[0].meta.get("zone") in ("calc_result",) and x[0].type == "copy"]
    assert copy_events[0][1].action == "silent" and "gate_wait_signals" in copy_events[0][1].reason_codes
    assert e.type == "tab" and d.decision_id.startswith("d_")


def test_clean_expert_case_is_silent_all_the_way(brain):
    trace = run(brain, expert_task("t_h1", 0))
    assert not acts(trace)
    assert any("on_track" in d.reason_codes for _, d in trace)


def test_no_active_task_and_no_events(brain):
    d = brain.next_step("p_nobody", T0)
    assert d.action == "silent" and d.reason_codes == ["no_events"]
    done = expert_task("t_h1", 0)
    d = brain.next_step("p_hand", done[-1].t, events=done)
    assert d.action == "silent" and d.reason_codes == ["no_active_task"] and d.task_id is None


def test_unknown_role_has_no_pack_and_stays_silent(store):
    b = CoachBrain(store, scorer=StuckScorer(fit=False))
    evs = [ev(0, "task_start", role="sales-rep"), ev(2, "focus", "doc", role="sales-rep")]
    assert run(b, evs)[-1][1].reason_codes == ["no_pack"]


def test_silent_when_the_worker_is_away(brain):
    evs = signature_events()
    for e in evs:
        brain.feed("p_hand", [e])
    last = evs[-1].t.timestamp()
    d = brain.next_step("p_hand", last + 300)                      # five minutes later, nothing happened
    assert d.action == "silent" and ("gate_unsure" in d.reason_codes or "unsure_away" in d.reason_codes)
    assert d.gate["reason"] in ("unsure",)


def test_cooldown_blocks_a_second_prompt_and_expires(store):
    b = CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")
    evs = []
    # case 1 violates at 60 s; case 2 starts 20 s later and violates again inside the 120 s cooldown
    evs += [ev(0, "task_start", task="t_a", source="desk")] + read("t_a", 1) + calc("t_a", 12) + copy_to_note("t_a", 50) + [ev(70, "task_end", task="t_a", source="desk")]
    evs += [ev(80, "task_start", task="t_b", source="desk")] + read("t_b", 81) + calc("t_b", 92) + copy_to_note("t_b", 130)
    evs += [ev(200, "scroll", "doc", task="t_b"), ev(215, "scroll", "doc", task="t_b"), ev(228, "scroll", "doc", task="t_b")]
    trace = run(b, evs)
    fired = acts(trace)
    assert len(fired) == 2
    (e1, d1), (e2, d2) = fired
    assert d1.task_id == "t_a" and d2.task_id == "t_b"
    assert (e2.t - e1.t).total_seconds() >= 120
    blocked = [d for e, d in trace if d.task_id == "t_b" and "gate_cooldown" in d.reason_codes]
    assert blocked, "the violation in case 2 was seen while cooling down"


def test_levels_shape_the_help(store):
    """L2 one line, L3 a dot, L4 silent unless asked. Levels come from finished cases judged against the expert policy."""
    expectations = {3: ("nudge", "L2"), 6: ("silent", "L3"), 9: ("silent", "L4")}
    for n_clean, (action, level) in expectations.items():
        st = EventStore(store.root.parent / f"d{n_clean}")
        b = CoachBrain(st, scorer=StuckScorer(fit=False), tone="short")
        hist = []
        for k in range(n_clean):
            hist += expert_task(f"t_c{k}", 1000 * k)
        for e in hist:
            b.feed("p_hand", [e])
        bad = [ev(1000 * n_clean + x.t.timestamp() - T0.timestamp(), x.type, x.meta.get("zone"), task="t_new", **{k: v for k, v in x.meta.items() if k != "zone"})
               for x in signature_events("t_new")]
        trace = run(b, hist + bad)[len(hist):]
        last = trace[-1][1]
        assert last.level == level, (n_clean, last.level)
        fired = acts(trace)
        if action == "nudge":
            assert len(fired) == 1 and fired[0][1].action == "nudge" and fired[0][1].target is None
            assert fired[0][1].message == "Is any figure close to a limit? What changes if it moves a little?"
        else:
            assert not fired and last.action == "silent" and f"level_{level[1]}" in last.reason_codes
            assert last.chip == ("dot" if level == "L3" else "gone")
            assert (last.message == "Probe the edge.") if level == "L3" else (last.message == "")
        if level == "L4":                                   # the worker asks: a nudge at any level
            asked = b.next_step("p_hand", bad[-1].t, ask=True)
            assert asked.action == "nudge" and "worker_asked" in asked.reason_codes


def test_stuck_signal_gives_a_question_not_a_ring(store):
    b = CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")
    task = "t_s"
    evs = [ev(0, "task_start", task=task, source="desk")] + read(task, 1) + [ev(12, "nav", "calc_site", task=task, site="calc1")]
    # a long stretch on the first calculator with no progress: reading and searching around
    for k in range(14):
        evs.append(ev(20 + 12 * k, "scroll", "doc", task=task))
    trace = run(b, evs)
    fired = acts(trace)
    assert fired and fired[0][1].trigger == "stuck" and fired[0][1].action == "nudge" and fired[0][1].target is None
    assert fired[0][1].p_source == "heuristic" and fired[0][1].p_stuck >= 0.6
    assert fired[0][1].message.endswith("?")
    assert len(fired) == 1                                   # one prompt for this step in this task


def test_detailed_tone_adds_the_hint(store):
    b = CoachBrain(store, scorer=StuckScorer(fit=False), tone="detailed")
    d = acts(run(b, signature_events()))[0][1]
    assert d.message.startswith("Check cliff edges before you copy this result.") and "Press Check cliff edges under the result" in d.message


def test_tone_follows_the_memory_preference(store, tmp_path, monkeypatch):
    from understudy_engine.memory import MemoryStore

    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    ms = MemoryStore()
    b = CoachBrain(store, scorer=StuckScorer(fit=False))
    assert b._tone() == "short"                                            # no memory file: short
    ms.write_markdown("---\nrole: benefits-processor\nrevision: 0\n---\n## Preferences\n- Summaries: short. Tone: plain.\n", 0, actor="worker")
    assert CoachBrain(store, scorer=StuckScorer(fit=False))._tone() == "short"
    rev = ms.revision()
    ms.write_markdown("---\nrole: benefits-processor\nrevision: 1\n---\n## Preferences\n- Summaries: detailed. Tone: plain.\n", rev, actor="worker")
    b2 = CoachBrain(store, scorer=StuckScorer(fit=False))                 # tone=None: read the worker's preference
    assert b2._tone() == "detailed"
    d = acts(run(b2, signature_events()))[0][1]
    assert "Press Check cliff edges under the result" in d.message           # the hint rides along for a worker who wants detail


# ---------------------------------------------------------------------------------- feedback
def fired_decision(brain):
    trace = run(brain, signature_events())
    return acts(trace)[0]


def test_feedback_followed_writes_a_schema_valid_event_and_is_neutral_for_the_level(brain, store):
    e, d = fired_decision(brain)
    now = e.t.timestamp() + 5
    res = brain.feedback(d.decision_id, "followed", now)
    assert res["recorded"] and res["outcome"] == "followed" and res["event_id"]
    assert res["skill"]["CHECK_CLIFF"]["level"] == "L1"                       # assisted is neutral: no streak, no demotion
    evs = store.read("synthetic", person="p_hand")
    types = [x.type for x in evs if x.source == "coach"]
    assert types == ["coach_shown", "coach_followed"]
    shown, followed = [x for x in evs if x.source == "coach"]
    assert shown.actor == "agent" and followed.actor == "human"
    assert shown.meta["decision"] == followed.meta["decision"] == d.decision_id and followed.meta["step"] == "cliff_a" and followed.meta["outcome"] == "followed"
    assert followed.task_id == "t_h1" and followed.origin == "synthetic"
    assert brain.feedback(d.decision_id, "followed", now)["recorded"] is False         # no double count


def test_feedback_dismissed_repeated_and_undone_are_dismissals_with_the_reason(store):
    for outcome in ("dismissed", "repeated", "undone"):
        st = EventStore(store.root.parent / f"fb_{outcome}")
        b = CoachBrain(st, scorer=StuckScorer(fit=False), tone="short")
        e, d = fired_decision(b)
        res = b.feedback(d.decision_id, outcome, e.t.timestamp() + 3)
        assert res["recorded"] and res["skill"] == {}
        coach = [x for x in st.read("synthetic", person="p_hand") if x.type == "coach_dismissed"]
        assert len(coach) == 1 and coach[0].meta["outcome"] == outcome and coach[0].actor == "human"


def test_a_dismissal_stops_the_nagging_and_a_repeat_earns_one_takeover_offer(store):
    # dismissed: the same missing check is not raised again in this case
    b = CoachBrain(EventStore(store.root.parent / "nag"), scorer=StuckScorer(fit=False), tone="short")
    evs = signature_events()
    trace = run(b, evs)
    e, d = acts(trace)[0]
    b.feedback(d.decision_id, "dismissed", e.t.timestamp() + 2)
    tail = [ev(60 + 15 * k, "scroll", "case_note", task="t_h1") for k in range(1, 20)]
    after = run(b, evs + tail)[len(evs):]
    assert not [1 for _, x in acts(after) if x.trigger == "expert_policy"]                 # (a long idle tail may still draw a stuck question)
    assert any("already_prompted" in x.reason_codes for _, x in after)
    # repeated: after the cooldown the coach offers to take over, once, as an offer
    b2 = CoachBrain(EventStore(store.root.parent / "rep"), scorer=StuckScorer(fit=False), tone="short")
    trace = run(b2, evs)
    e, d = acts(trace)[0]
    b2.feedback(d.decision_id, "repeated", e.t.timestamp() + 2)
    after = run(b2, evs + tail)[len(evs):]
    fired = [a for a in acts(after) if a[1].trigger == "expert_policy"]
    assert len(fired) == 1 and fired[0][1].action == "takeover_offer"
    assert fired[0][1].message.startswith("Want me to do this one for you") and "stop before anything is sent" in fired[0][1].message
    assert fired[0][1].target["zone"] == "cliff_button" and "issue_repeated" in fired[0][1].reason_codes


def test_doing_the_missed_step_soon_after_the_prompt_is_labelled_followed(brain, store):
    evs = signature_events()
    trace = run(brain, evs)
    e, d = acts(trace)[0]
    more = evs + cliff("t_h1", 70)
    for i in range(len(evs), len(more)):
        brain.next_step("p_hand", more[i].t, events=more[: i + 1])
    labelled = [x for x in store.read("synthetic", person="p_hand") if x.type == "coach_followed"]
    assert len(labelled) == 1 and labelled[0].meta.get("implicit") is True and labelled[0].meta["decision"] == d.decision_id


def test_feedback_errors(brain):
    with pytest.raises(CoachError) as ex:
        brain.feedback("d_nope", "followed")
    assert ex.value.code == "no_such_decision" and ex.value.status == 404
    e, d = fired_decision(brain)
    with pytest.raises(CoachError) as ex:
        brain.feedback(d.decision_id, "ignored")
    assert ex.value.code == "bad_outcome" and ex.value.status == 422


def test_dry_run_changes_nothing(store):
    b = CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")
    evs = signature_events()
    trace = run(b, evs, commit=False)
    assert not acts(trace)
    assert not [x for x in store.read("synthetic", person="p_hand") if x.source == "coach"]
    cand = [d.candidate for _, d in trace if d.candidate]
    assert cand and cand[-1]["action"] == "annotate" and cand[-1]["target"]["zone"] == "cliff_button"


def test_cooldown_and_what_was_said_survive_a_restart(store):
    evs = signature_events()
    b = CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")
    e, d = acts(run(b, evs))[0]
    for x in evs:                                   # the worker's events are in the store, as they would be live
        store.append(x)
    b2 = CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")
    d2 = b2.next_step("p_hand", e.t.timestamp() + 10)
    assert d2.action == "silent" and "already_prompted" in d2.reason_codes
    assert b2.feedback(d.decision_id, "followed", e.t.timestamp() + 12)["recorded"]       # the decision is found in the log


def test_repeated_calls_with_the_same_events_are_deterministic(store):
    evs = signature_events()
    a = [d.to_dict() for _, d in run(CoachBrain(EventStore(store.root.parent / "a"), scorer=StuckScorer(fit=False), tone="short"), evs, commit=False)]
    b = [d.to_dict() for _, d in run(CoachBrain(EventStore(store.root.parent / "b"), scorer=StuckScorer(fit=False), tone="short"), evs, commit=False)]
    assert a == b


def test_gate_parameters_are_the_dignity_gate_defaults():
    from understudy_engine.coach import GATE

    assert GATE == GateParams(need=2, cooldown_s=120.0, p_signal=0.6, min_confidence=0.5)


def test_touching_the_reconciliation_control_satisfies_reconcile_and_resolves_the_prompt(store, monkeypatch):
    """With the default mapping (which knows the case note's reconciliation select), reconcile is done by touching it."""
    from understudy_engine.cogs import load_mapping
    from understudy_engine.packs.loader import Pack

    monkeypatch.setattr(Pack, "cog_mapping", lambda self: load_mapping(None))
    b = CoachBrain(store, scorer=StuckScorer(fit=False), tone="short")
    task = "t_h1"
    # two calculators with their cliff checks, then straight to the note without reconciling
    evs = ([ev(0, "task_start", task=task, source="desk")] + read(task, 1) + calc(task, 12, "calc1") + cliff(task, 46) + calc(task, 56, "calc2")
           + cliff(task, 90) + calc(task, 100, "calc3") + cliff(task, 134) + copy_to_note(task, 142))
    trace = run(b, evs)
    fired = acts(trace)
    assert len(fired) == 1
    d = fired[0][1]
    assert d.missed[0] == "reconcile" and d.target == {"zone": "reconcile_control", "label_hint": "How do they compare", "role_hint": "select",
                                                         "fallback_zones": ["results_tabs"]}
    assert d.message == "Reconcile the three results before writing anything."
    # the worker touches the select: the missed step is done, the signal is gone, and the prompt is labelled followed
    more = evs + [ev(160, "focus", "reconcile_control", task=task), ev(163, "click", "reconcile_control", task=task)]
    tail = run(b, more)[len(evs):]
    assert not acts(tail) and tail[-1][1].missed == [] and "policy_violation" not in tail[-1][1].reason_codes
    assert [x for x in b.store.read("synthetic", person="p_hand") if x.type == "coach_followed" and x.meta.get("implicit")]
    # and the same case, but the worker switched tabs between the calculators instead: also reconciled (the old rule)
    b2 = CoachBrain(EventStore(store.root.parent / "tabs"), scorer=StuckScorer(fit=False), tone="short")
    evs2 = ([ev(0, "task_start", task=task, source="desk")] + read(task, 1) + calc(task, 12, "calc1") + cliff(task, 46) + calc(task, 56, "calc2")
            + cliff(task, 90) + calc(task, 100, "calc3") + cliff(task, 134) + reconcile(task, 142) + copy_to_note(task, 158))
    assert not acts(run(b2, evs2))


def poll_run(brain, events, poll=3.0, batch=2.0, person="p_hand", offset=1.0):
    """What the live harness does: the extension batches events (they become visible `batch` s late) and the desktop polls every
    `poll` s. Returns [(poll time, decision)]."""
    t0 = events[0].t.timestamp()
    t, idx, fed, out = t0 + offset, 0, 0, []
    while t <= events[-1].t.timestamp() + 12:
        while idx < len(events) and events[idx].t.timestamp() <= t - batch:
            idx += 1
        out.append((t, brain.next_step(person, t, events=events[fed:idx])))
        fed = idx
        t += poll
    return out


def dense_signature_events(task="t_h1"):
    """The signature case, but the copy and the move to the note land inside one poll window (events 0.8 s apart)."""
    return ([ev(0, "task_start", task=task, source="desk")] + read(task, 1) + calc(task, 12)
            + [ev(50, "copy", "calc_result", task=task), ev(50.8, "tab", "case_note", task=task), ev(52, "paste", "case_note", task=task),
               ev(60, "click", "case_note", task=task)])


def test_event_clock_lets_the_first_poll_act_when_two_signals_are_already_in_the_window(tmp_path):
    evs = dense_signature_events()
    copy_t = next(e for e in evs if e.type == "copy").t.timestamp()
    lag = {}
    for clock in ("polls", "events"):
        b = CoachBrain(EventStore(tmp_path / clock), scorer=StuckScorer(fit=False), tone="short", gate_clock=clock)
        fired = [(t, d) for t, d in poll_run(b, evs, offset=0.0) if d.action != "silent"]
        assert len(fired) == 1 and fired[0][1].action == "annotate" and fired[0][1].target["zone"] == "cliff_button"
        lag[clock] = fired[0][0] - copy_t
    assert lag["polls"] == pytest.approx(7.0) and lag["events"] == pytest.approx(4.0)          # one poll interval (3 s) sooner


def test_the_event_clock_does_not_count_a_signal_twice_or_skip_the_cooldown(tmp_path):
    evs = signature_events()
    b = CoachBrain(EventStore(tmp_path / "e"), scorer=StuckScorer(fit=False), tone="short", gate_clock="events")
    run1 = poll_run(b, evs)
    assert len([1 for _, d in run1 if d.action != "silent"]) == 1                      # acted once; the repeats are the cooldown
    assert any("gate_cooldown" in d.reason_codes or "already_prompted" in d.reason_codes for _, d in run1)
    with pytest.raises(ValueError):
        CoachBrain(EventStore(tmp_path / "x"), gate_clock="sometimes")
