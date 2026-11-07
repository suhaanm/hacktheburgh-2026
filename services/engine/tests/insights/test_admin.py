"""Admin candidates and views on the synthetic firm (REQ-9, D41): comparisons within skill and standardised, k-anonymity for tables, per-user rows
as numbers and enums only, planted situations recovered."""
from __future__ import annotations

import json
import re

import pytest
from understudy_engine.insights import admin as A
from understudy_engine.insights import firm as F
from understudy_engine.insights import select as SEL
from understudy_engine.insights import views as VW
from understudy_engine.insights import vocab as V
from understudy_engine.insights.summary import AdminView, merge_small

LEDGER_KEYS = {"t_hour", "answer_id", "stuck_bucket", "options_shown", "seconds_to_progress", "level_before", "level_after", "retrieval", "tier", "step", "trigger"}


@pytest.fixture(scope="module")
def firm():
    return F.build_firm(0)


@pytest.fixture(scope="module")
def view(firm):
    return AdminView(firm.snapshot)


@pytest.fixture(scope="module")
def cands(view):
    return A.admin_run(view)


@pytest.fixture(scope="module")
def sel(view, cands):
    return SEL.select(cands, audience="admin", scope="firm", now=view.now)


def by(cands, kind, subject=None):
    return [c for c in cands if c.kind == kind and (subject is None or c.subject == subject)]


# ---------------------------------------------------------------------------------------------------- k-anonymity
def test_a_comparison_group_below_five_is_refused_in_one_place(view):
    assert view.cohort(role="programmer", level="expert") is None            # 3 experts
    assert view.cohort(role="benefits-processor", level="junior") is not None
    assert view.cohort(role="programmer", unit="prog_infra") is None         # the 4-person team
    assert len(view.cohort(role="benefits-processor", level="expert")) == 7


def test_merge_small_pools_small_cells_into_other_and_never_shows_a_group_below_k():
    cells = {"a": list("abcdef"), "b": list("gh"), "c": list("i"), "d": list("jk")}
    m = dict(merge_small(cells, 5))
    assert set(m) == {"a", "Other"} and len(m["Other"]) == 5 and all(len(v) >= 5 for v in m.values())
    assert merge_small({"a": list("ab"), "b": list("c")}, 5) == []                                     # nothing reaches 5: nothing shown
    pooled = merge_small({"a": list("abcdef"), "b": list("g"), "c": list("h")}, 5)
    assert dict(pooled)["a"] == list("abcdefgh")                                                       # a pool of 2 joins the smallest cell that has 5


def test_the_roles_table_gives_no_comparison_for_a_small_group_and_says_why(view):
    p = VW.roles_payload(view)
    prog = next(r for r in p["roles"] if r["role"] == "programmer")
    assert prog["enough"] is False and prog["reason"] == "no_expert_reference" and prog["habits"] == [] and prog["measures"] == []
    ben = next(r for r in p["roles"] if r["role"] == "benefits-processor")
    assert ben["enough"] and {m["key"] for m in ben["measures"]} == {"independence", "assisted_share", "time_vs_expert"}
    for t in ben["tenure"]:
        assert t["n"] >= 5


def test_the_firm_view_keeps_tiny_units_out_of_unit_tables_but_lists_per_user_rows(view):
    p = VW.firm_payload(view)
    prog = next(g for g in p["roles"] if g["role"] == "programmer")
    assert all(u["n"] >= 5 or u["unit"] == "Other" for u in prog["units"])
    assert all(u["unit"] != "prog infra" for u in prog["units"])                                      # the 4-person team is not a cell of its own
    assert len(prog["users"]) == 12                                                                 # per-user rows are allowed (D41)


# ---------------------------------------------------------------------------------------------------- planted truth
def test_the_role_gap_is_recovered_within_skill_and_names_the_planted_habits(view, cands):
    d = A.role_gap_detail(view, "benefits-processor")
    assert d["gap"]["lo"] > 5 and d["gap"]["value"] > 10 and d["gap"]["hi"] > d["gap"]["value"] > d["gap"]["lo"]
    top = sorted((h for h in d["habits"] if h["explains"]), key=lambda h: -h["explains"]["value"])[:2]
    assert {h["skill"] for h in top} == {"check-the-cliff", "reconcile-before-noting"}
    c = by(cands, "role_gap", "benefits-processor")[0]
    assert set(c.split["top_habits"]) == {"check-the-cliff", "reconcile-before-noting"} and c.lo > 0
    easy = next(h for h in d["habits"] if h["skill"] == "enter-household-once")
    assert easy["gap"].value < 8                                                                    # no planted gap on the easy skill


def test_a_role_with_fewer_than_five_experts_has_no_expert_comparison(cands, sel):
    c = by(cands, "role_gap", "programmer")[0]
    assert c.reason_pre == "no_expert_reference" and sel.reason_of(c.id) == ("suppressed", "no_expert_reference")


def test_the_improving_juniors_and_the_plateau_are_told_apart(view, cands):
    t = {r: A.trend_detail(view, r) for r in view.roles()}
    assert t["benefits-processor"]["class"] == "improving" and t["benefits-processor"]["est"].lo > 0
    ua, ub = by(cands, "unit_attention", "benefits-processor:unit_a")[0], by(cands, "unit_attention", "benefits-processor:unit_b")[0]
    assert ub.value > 0.08 and ub.lo > 0 and ua.lo is None or ua.lo < 0.05
    small = by(cands, "unit_attention", "programmer:prog_infra")
    assert not small or small[0].reason_pre == "group_too_small"


def test_simpsons_paradox_is_resolved_by_standardising_not_by_the_raw_rate(view):
    d = A.trend_detail(view, "data-analyst")
    assert d["std_late"] - d["std_early"] > 0.05                         # within skill, juniors improve
    assert d["raw_late"] - d["raw_early"] < d["std_late"] - d["std_early"] - 0.05          # the raw pooled change understates it, because the mix shifted
    assert d["class"] == "improving"
    drill = VW.drill_payload(view, by(A.admin_run(view), "cohort_trend", "data-analyst")[0], {}, "h")
    labels = [r["label"] for r in drill["rows"]]
    assert any("Standardised" in x for x in labels) and any("Raw pooled" in x for x in labels)


def test_the_bottleneck_skill_is_the_planted_one(cands):
    ben = [c for c in by(cands, "bottleneck_skill") if c.extras.get("role") == "benefits-processor" and c.value is not None]
    best = max(ben, key=lambda c: c.value)
    assert best.extras["skill"] == "check-the-cliff" and best.lo > 0.03


def test_automation_value_uses_measured_shadow_matches_and_pending_proposals_are_counted(cands, sel):
    c = by(cands, "automation_value")[0]
    assert c.value > 5 and c.split["shadow_lower"] >= 0.8 and c.n >= 20 and c.reason_pre is None
    assert sel.reason_of(c.id)[0] == "selected"
    pend = by(cands, "automation_pending")[0]
    assert pend.n >= 3 and pend.value >= 3


def test_risk_signals_are_counts_and_ages_and_hold_a_reserved_place(cands, sel):
    r = {c.subject: c for c in by(cands, "risk_signal")}
    assert r["approval_backlog"].value == 72.0 and r["approval_backlog"].n == 3
    assert r["injection_pauses"].value == 1.0                                       # two in 30 days, one inside the 7-day window
    assert "kill_events" not in r and "false_claims" not in r                          # the kill was 9 days ago; there were no false claims
    assert any(s.cand.kind == "risk_signal" for s in sel.selected)


def test_a_broken_risk_feed_is_reported_not_silenced(firm):
    from dataclasses import replace

    snap = replace(firm.snapshot, feed_t={"ledger": firm.snapshot.now, "risk_feed": firm.snapshot.now - 5 * 86400})
    cs = A.admin_run(AdminView(snap))
    assert any(c.kind == "data_stale" and c.slots["feed"] == "risk_feed" for c in cs)
    assert not any(c.kind == "risk_signal" for c in cs)
    s = SEL.select(cs, audience="admin", scope="firm", now=snap.now)
    assert any(x.cand.kind == "data_stale" for x in s.selected)


def test_a_false_claim_turns_the_automation_win_into_a_trade_off(firm):
    from dataclasses import replace

    snap = replace(firm.snapshot, risk_events=firm.snapshot.risk_events + ({"kind": "false_claim", "age_days": 6.0},))
    cs = A.admin_run(AdminView(snap))
    s = SEL.select(cs, audience="admin", scope="firm", now=snap.now)
    c = next(x.cand for x in s.selected if x.cand.kind == "automation_value")
    assert c.polarity == "tradeoff"


def test_the_onboarding_curve_is_a_kaplan_meier_with_censoring_and_a_design_target(view):
    p = VW.onboarding_payload(view)
    assert p["target"]["label"] == "design target" and p["x_unit"] == "occurrences"
    ben = next(r for r in p["roles"] if r["role"] == "benefits-processor")
    assert ben["n"] >= 15 and ben["censored"] >= 1 and ben["reached_share"]["ci"][0] <= ben["reached_share"]["value"] <= ben["reached_share"]["ci"][1]
    ys = [pt["y"] for pt in ben["km"]]
    assert ys == sorted(ys)                                                        # cumulative reached share never falls
    assert all(pt["n"] >= 5 for pt in ben["curve"])
    prog = next(r for r in p["roles"] if r["role"] == "programmer")
    assert prog["reason"] in (None, "group_too_small")


# ---------------------------------------------------------------------------------------------------- what an admin may see
def test_no_admin_insight_has_a_person_as_its_subject(cands):
    for c in cands:
        assert not re.match(r"^p_", c.subject) and not re.match(r"^p_", c.group), c


def test_per_user_rows_are_numbers_and_enums_in_label_order_with_no_rank_or_score(view):
    rows = view.person_rows()
    assert [r["label"] for r in rows] == sorted(r["label"] for r in rows)
    forbidden = {"rank", "score", "composite", "percentile", "position", "league"}
    for r in rows:
        assert not (set(r) & forbidden)
        assert set(r) == {"id", "label", "role", "level", "unit", "tenure_band", "tenure_weeks", "status", "trend", "trend_label", "independence", "assisted_share",
                          "time_to_independence", "automations_running", "automation", "n", "n_recent", "last_seen_days", "skills", "origin", "name"}
        assert r["trend"] in V.TREND_CLASSES and r["status"] in V.STATUSES_PERSON and r["tenure_band"] in V.TENURE_BANDS


def test_no_admin_payload_contains_a_ledger_field_a_row_id_or_an_hour_bucket(view, cands, sel):
    from understudy_engine.insights.service import InsightsService
    from understudy_engine.insights.store import InsightsStore

    svc = InsightsService(InsightsStore(), snapshot_provider=lambda s: view.snap)
    docs = [svc.overview("firm"), svc.roles("firm"), svc.firm("firm"), svc.onboarding("firm")]
    for s in sel.selected:
        docs.append(svc.drill("firm", s.cand.id))
    blob = json.dumps(docs)
    assert not re.search(r"a_[0-9a-f]{12}", blob)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}\b", blob)
    parsed = json.loads(blob)

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)

    assert not (set(keys(parsed)) & LEDGER_KEYS)

    def lost_paths(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "lost_s":
                    yield path, v
                yield from lost_paths(v, path + "/" + k)
        elif isinstance(o, list):
            for v in o:
                yield from lost_paths(v, path)

    for path, v in lost_paths(parsed):                       # the only place the name appears is a per-skill aggregate with an interval, never a row value
        assert path.endswith("/users/skills") and (v is None or (isinstance(v, dict) and set(v) == {"value", "ci"})), path


def test_a_deleted_ledger_disappears_from_every_comparison_at_once(firm):
    from dataclasses import replace

    snap = firm.snapshot
    before = AdminView(snap)
    victim = next(p for p in snap.people if p.role == "benefits-processor" and p.level == "junior" and p.rows)
    after_snap = replace(snap, people=tuple(replace(p, rows=()) if p.id == victim.id else p for p in snap.people))
    after = AdminView(after_snap)
    assert after.sums[victim.id].status == "no_data" and before.sums[victim.id].status != "no_data"
    assert victim.id not in {s.id for s in after.cohort(role="benefits-processor", level="junior")}
    assert after.coverage()["by_status"]["no_data"] == before.coverage()["by_status"]["no_data"] + 1


def test_the_role_change_user_counts_in_the_new_role_only_and_old_rows_do_not_leak(firm, view):
    pid = firm.truth["planted"]["specials"]["role_change"][0]
    s = view.sums[pid]
    assert s.role == "programmer" and s.status in ("ok", "onboarding")
    assert all(r["role"] == "programmer" for r in s._rows)


def test_family_control_ran_over_the_admissible_admin_tests(sel):
    assert sel.family["method"] == "benjamini_hochberg" and sel.family["m"] >= 8 and 0 < len(sel.selected) <= 7
