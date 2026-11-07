"""Worker candidates and their edge cases (REQ-9): every case in docs/INSIGHTS_DESIGN.md section 3 that concerns one person."""
from __future__ import annotations

from understudy_engine.insights import select as SEL
from understudy_engine.insights import worker as W
from understudy_engine.insights.params import DEFAULT
from understudy_engine.insights.worker import WorkerCtx

from .helpers import DAY, NOW, SKILL, habit_rows, person, row

P = "p_w1"


def run(rows, **kw):
    pr = person(P, rows, **kw)
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    return out, sel


def kinds(sel):
    return [s.cand.kind for s in sel.selected]


def reasons(sel):
    return {(s.kind, s.subject): s.reason for s in sel.suppressed}


def test_a_persistent_time_loss_is_selected_and_carries_its_numbers():
    out, sel = run(habit_rows(P, lost=30.0))
    assert out.status == "ok"
    assert kinds(sel) == ["time_loss_habit"]
    c = sel.selected[0].cand
    assert 25 < c.value < 35 and c.lo > 0 and c.p < 0.001 and c.n == 12 and c.unit == "seconds"
    assert c.slots["seconds"] == 30 and c.slots["skill"] == SKILL and c.action_id == "open_growth"


def test_no_gap_means_nothing_stands_out_and_the_reason_is_recorded():
    out, sel = run(habit_rows(P, lost=0.0))
    assert sel.selected == []
    assert reasons(sel)[("time_loss_habit", SKILL)] in ("below_effect_floor", "interval_spans_zero")


def test_a_gap_below_the_floor_is_suppressed_never_shown_weakly():
    out, sel = run(habit_rows(P, lost=6.0, jitter=1.0))
    assert sel.selected == [] and reasons(sel)[("time_loss_habit", SKILL)] == "below_effect_floor"


def test_one_extreme_week_cannot_make_a_habit_regression_to_the_mean():
    rows = habit_rows(P, weeks=1, per_week=6, lost=90.0)                   # all the loss is in the newest week
    rows += habit_rows(P, weeks=2, per_week=4, lost=0.0, start_days=8.0, serial0=100)
    out, sel = run(rows)
    assert "time_loss_habit" not in kinds(sel)
    assert reasons(sel)[("time_loss_habit", SKILL)] in ("not_persistent", "interval_spans_zero", "below_effect_floor")


def test_outliers_are_clipped_not_trusted():
    rows = habit_rows(P, lost=0.0, jitter=2.0)
    rows[3] = row(P, 3.0, SKILL, "clean", 3600.0, serial=999)              # a single hour-long outlier
    out, sel = run(rows)
    assert "time_loss_habit" not in kinds(sel)


def test_no_expert_reference_gives_no_time_comparison_and_says_why():
    rows = [row(P, 1 + i * 1.5, SKILL, "clean", None, serial=i) for i in range(12)]
    out, sel = run(rows)
    assert reasons(sel)[("time_loss_habit", SKILL)] == "no_expert_reference"


def test_a_new_user_gets_an_onboarding_pointer_and_no_comparison():
    out, sel = run([row(P, 1 + i, SKILL, "clean", 50.0, serial=i) for i in range(5)])
    assert out.status == "onboarding" and kinds(sel) == ["onboarding"]
    assert out.candidates[0].slots == {"seen": 5, "needed": 10, "reason": "new"}


def test_no_rows_at_all_is_no_data_with_no_pointers():
    out, sel = run([])
    assert out.status == "no_data" and out.candidates == [] and sel.selected == []


def test_stale_data_gives_a_stale_marker_not_silence_and_not_old_insights():
    rows = habit_rows(P, lost=40.0, start_days=40.0)                       # the newest row is 40 days old
    out, sel = run(rows)
    assert out.status == "stale" and out.stale_sources == ["ledger"] and kinds(sel) == ["stale_data"]
    assert sel.selected[0].cand.slots["days"] >= 39


def test_a_role_change_resets_baselines_and_flags_the_discontinuity():
    old = habit_rows(P, lost=60.0, skill="profile-before-querying", serial0=500)
    for r in old:
        r["role"] = "data-analyst"
    new = [row(P, 1 + i * 0.5, SKILL, "clean", 0.0, serial=i) for i in range(4)]
    out, sel = run(old + new, role_since=NOW - 3 * DAY)
    assert out.status == "role_changed" and kinds(sel) == ["onboarding"]        # only 4 rows in the new role
    assert out.candidates[0].subject == "role_changed"
    # with enough new-role rows the old role's rows still never count, and the discontinuity is flagged once
    new = [row(P, 0.1 + i * 0.2, SKILL, "clean", 0.0, serial=700 + i) for i in range(14)]
    out, sel = run(old + new, role_since=NOW - 3 * DAY)
    assert out.status == "ok" and "time_loss_habit" not in kinds(sel)
    assert any(c.kind == "onboarding" and c.subject == "role_changed" for c in out.candidates)


def test_delegated_and_automation_rows_never_reach_an_independence_insight():
    rows = [row(P, 1 + i, SKILL, "clean", 0.0, stream="delegated" if i % 2 else "automation", serial=i) for i in range(40)]
    out, sel = run(rows)
    assert out.status == "no_data" and out.candidates == [] and sel.selected == []


def mastered_then(pid, recent_outcomes, *, gap_days=0.0):
    """15 independent occurrences, 10 more independent ones, then ``recent_outcomes`` after an optional gap."""
    rows = [row(pid, 80 - i * 1.0, SKILL, "clean", 0.0, serial=i) for i in range(25)]     # days 80 .. 56 ago
    for j, o in enumerate(recent_outcomes):
        rows.append(row(pid, 12 - j * 1.0 - gap_days * 0, SKILL, o, 0.0, serial=100 + j))
    return rows


def test_relapse_fires_when_a_mastered_skill_needs_help_again():
    rows = [row(P, 80 - i * 1.0, SKILL, "clean", 0.0, serial=i) for i in range(25)]
    rows += [row(P, 12 - j * 1.0, SKILL, "assisted", 0.0, serial=100 + j) for j in range(10)]
    out, sel = run(rows)
    assert "relapse" in kinds(sel), reasons(sel)
    c = next(s.cand for s in sel.selected if s.cand.kind == "relapse")
    assert c.value >= 0.25 and c.lo > 0


def test_a_short_absence_is_not_read_as_a_relapse_and_gives_retention_not_decay_claims():
    rows = [row(P, 90 - i * 1.0, SKILL, "clean", 0.0, serial=i) for i in range(25)]        # mastered, days 90 .. 66 ago
    # a 40-day break, then 5 occurrences back, all needing help
    rows += [row(P, 10 - j * 1.5, SKILL, "assisted", 0.0, serial=100 + j) for j in range(5)]
    out, sel = run(rows)
    assert "relapse" not in kinds(sel)
    rel = [c for c in out.candidates if c.kind == "relapse"]
    assert not rel or all(c.reason_pre in ("short_absence", "not_enough_data") for c in rel)


def test_retention_due_for_a_mastered_skill_not_practised_for_a_month():
    rows = [row(P, 60 - i * 1.5, SKILL, "clean", 0.0, serial=i) for i in range(12)]        # last done 42 days ago
    rows += habit_rows(P, lost=0.0, weeks=2, per_week=3, skill="enter-household-once", serial0=300, start_days=1.0)
    out, sel = run(rows)
    assert out.status == "ok"
    c = next(c for c in out.candidates if c.kind == "retention_due")
    assert c.subject == SKILL and 14 <= c.value <= 120
    assert "retention_due" in kinds(sel) and not any(k == "relapse" for k in kinds(sel))


def test_a_milestone_is_a_new_crossing_with_the_family_adjusted_bound():
    rows = [row(P, 60 - i * 1.5, SKILL, "assisted" if i % 2 else "clean", 0.0, serial=i) for i in range(20)]          # half unaided
    rows += [row(P, 29 - i * 1.0, SKILL, "clean", 0.0, serial=100 + i) for i in range(20)]                            # then 20 unaided
    out, sel = run(rows)
    assert "independence_milestone" in kinds(sel), reasons(sel)
    c = next(s.cand for s in sel.selected if s.cand.kind == "independence_milestone")
    assert c.slots["level"] >= 0.65 and c.slots["k"] == 20 and c.slots["n"] == 20


def test_a_milestone_needs_forty_occurrences_two_blocks_that_can_be_compared():
    out, sel = run([row(P, 1 + i, SKILL, "assisted" if i < 10 else "clean", 0.0, serial=i) for i in range(30)] + habit_rows(P, lost=0.0, serial0=200, skill="enter-household-once"))
    assert "independence_milestone" not in [c.kind for c in out.candidates]


def test_habit_improved_is_shown_when_quality_holds():
    rows = []
    k = 0
    for w in range(3):                                   # the earlier window: weeks 4 to 6 ago, 40 s lost
        for i in range(4):
            rows.append(row(P, 28 + w * 7 + i * 1.5 + 0.5, SKILL, "clean", 40.0 + (k % 3), serial=k)); k += 1
    for w in range(3):                                   # now: 5 s lost
        for i in range(4):
            rows.append(row(P, 1 + w * 7 + i * 1.5, SKILL, "clean", 5.0 + (k % 3), serial=k)); k += 1
    out, sel = run(rows)
    assert "habit_improved" in kinds(sel), reasons(sel)
    c = next(s.cand for s in sel.selected if s.cand.kind == "habit_improved")
    assert c.value > 25 and c.polarity == "positive" and not any(g.worse for g in c.guards)


def test_faster_but_more_errors_is_shown_as_a_trade_off_never_as_a_celebration():
    rows = []
    k = 0
    for w in range(3):
        for i in range(4):
            rows.append(row(P, 28 + w * 7 + i * 1.5 + 0.5, SKILL, "clean", 40.0 + (k % 3), serial=k)); k += 1
    for w in range(3):
        for i in range(4):
            rows.append(row(P, 1 + w * 7 + i * 1.5, SKILL, "error" if i < 2 else "clean", 5.0 + (k % 3), serial=k)); k += 1
    out, sel = run(rows)
    assert "habit_improved" not in kinds(sel)
    assert "trade_off" in kinds(sel)
    c = next(s.cand for s in sel.selected if s.cand.kind == "trade_off")
    assert c.polarity == "tradeoff" and c.slots["guard"] == "error_share" and c.slots["k_after"] > c.slots["k_before"]


def test_automation_opportunity_needs_support_value_and_fresh_evidence():
    routine = {"person": P, "id": "rt_a", "status": "proposed", "support": 6, "hours_lo": 1.2, "hours_hi": 3.0, "horizon_weeks": 4, "t": NOW - 2 * DAY}
    pr = person(P, habit_rows(P, lost=0.0))
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(routines=[routine], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    assert "automation_opportunity" in kinds(sel)
    weak = dict(routine, hours_lo=0.1)
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(routines=[weak], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    assert "automation_opportunity" not in kinds(sel) and reasons(sel)[("automation_opportunity", "rt_a")] == "below_effect_floor"
    old = dict(routine, t=NOW - 60 * DAY)
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(routines=[old], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    assert reasons(sel)[("automation_opportunity", "rt_a")] == "stale"


def test_a_hit_list_row_is_a_pointer_only_when_fresh():
    hit = {"id": "calc-entry-3x", "count": 5, "window_days": 7, "hours_lo": 0.9, "hours_hi": 2.0, "horizon_weeks": 4, "origin": "synthetic", "t": NOW - DAY, "what": "the step run calculator A"}
    pr = person(P, habit_rows(P, lost=0.0))
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(hitlist=[hit], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    c = next(s.cand for s in sel.selected if s.cand.kind == "automation_opportunity")
    assert c.action_id == "open_repeats"
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(hitlist=[dict(hit, t=NOW - 30 * DAY)], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    assert "automation_opportunity" not in kinds(sel)


def test_calendar_and_git_pointers_come_only_from_the_layers_flagged_suggestions():
    pr = person(P, habit_rows(P, lost=0.0))
    q = {"source": "git", "id": "GIT_SMALLER_COMMITS", "delta": 0.30, "ci": [0.10, 0.50], "floor": 0.15, "n": 20, "t": NOW - 3 * DAY, "n_unit": "commits"}
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(pointers=[q], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    assert "git_pointer" in kinds(sel)
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(badge="synthetic firm"))
    assert not any(c.kind in ("git_pointer", "calendar_pointer") for c in out.candidates)         # the layers are off: nothing
    bad = dict(q, ci=[-0.1, 0.7])
    out = W.worker_run(pr, NOW, DEFAULT, WorkerCtx(pointers=[bad], badge="synthetic firm"))
    sel = SEL.select(out.candidates, audience="worker", scope=P, now=NOW)
    assert "git_pointer" not in kinds(sel)


def test_origin_and_badge_are_on_every_candidate():
    out, sel = run(habit_rows(P, lost=30.0))
    for c in out.candidates:
        assert c.badge == "synthetic firm" and c.origin in ("real", "synthetic", "mixed")


def test_stable_independence_is_not_a_milestone_so_an_expert_is_not_congratulated():
    rows = [row(P, 80 - i * 1.5, SKILL, "clean", 0.0, serial=i) for i in range(45)]               # 45 unaided occurrences in a row
    out, sel = run(rows)
    assert not any(c.kind == "independence_milestone" for c in out.candidates)
    steady = [row(P, 80 - i * 1.5, SKILL, "clean" if i % 4 else "assisted", 0.0, serial=i) for i in range(45)]    # a steady 75%
    out, sel = run(steady)
    assert not any(c.kind == "independence_milestone" for c in out.candidates)
