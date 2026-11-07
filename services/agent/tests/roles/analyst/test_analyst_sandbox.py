"""The analyst workbench end to end: the catalogue and its data (truth recomputed independently), the oracle on scripted programs, layouts and glitches.
Playwright against a RoleServer on an ephemeral port (no model, no network)."""
from __future__ import annotations

import json
import re
import statistics

import httpx
import pytest

from understudy_agent.sandbox_roles import analyst as A
from understudy_agent.sandbox_roles.analyst import oracle, tasks as T

from .helpers import play

CASES = [(tid, v) for tid, t in A.TASKS.items() for v in sorted(t.variants)]


@pytest.fixture(scope="module")
def server():
    with A.make_server(0) as s:
        yield s


def _col(v, name):
    return [c[0] for c in v.columns].index(name)


def _canon(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum())


# ---------------------------------------------------------------------------------------------------------------- pure: the data and the truth
def test_catalogue_shape():
    assert len(A.TASKS) == 6 and len(CASES) == 12
    assert {t.skill for t in A.TASKS.values()} == {"sanity", "reconcile", "aggregation"}
    for skill, info in A.SKILLS.items():
        assert len(info["task_ids"]) == 2 and all(A.TASKS[i].skill == skill for i in info["task_ids"])
    assert {i["pack_skill_id"] for i in A.SKILLS.values()} == {"profile-before-querying", "reconcile-to-control", "segment-before-concluding"}
    for t in A.TASKS.values():
        v1, v2 = t.variants[1], t.variants[2]
        assert v1.rows != v2.rows and v1.question != v2.question
        assert 60 <= len(v1.rows) <= 240 and 60 <= len(v2.rows) <= 240


def test_generators_are_deterministic():
    assert T._sanity1_v1().rows == T._sanity1_v1().rows and T._reconcile1_v2().rows == T._reconcile1_v2().rows and T._aggregation1_v2().rows == T._aggregation1_v2().rows


def test_truth_differs_from_naive_and_the_planted_issue_is_in_the_data():
    for tid, v in CASES:
        var = A.TASKS[tid].variants[v]
        assert var.truth != var.naive
        if isinstance(var.truth, float):
            assert abs(var.truth - var.naive) > max(var.tol * 5, 0.02 * abs(var.truth)), (tid, v, var.truth, var.naive)
        for p in var.partials:
            assert abs(p - var.truth) > var.tol and abs(p - var.naive) > var.tol


def test_truth_recomputed_independently_from_the_rows():
    # d-sanity-1: duplicates (exact in v1, same key with a later timestamp in v2) are the whole gap
    for v in (1, 2):
        var = A.TASKS["d-sanity-1"].variants[v]
        i_key, i_amt = _col(var, var.key), _col(var, "amount")
        first = {}
        for r in var.rows:
            first.setdefault(r[i_key], r[i_amt])
        assert round(sum(first.values())) == var.truth and round(sum(r[i_amt] for r in var.rows)) == var.naive
        assert len(var.rows) - len(first) >= 10
    v1 = A.TASKS["d-sanity-1"].variants[1]
    assert len(set(v1.rows)) < len(v1.rows)                                   # v1: exact duplicates exist
    v2 = A.TASKS["d-sanity-1"].variants[2]
    assert len(set(v2.rows)) == len(v2.rows)                                  # v2: none are exact: only the key finds them
    # d-sanity-2: one source in another unit
    var = A.TASKS["d-sanity-2"].variants[1]
    hours = [r[3] / 60 if r[4] == "min" else r[3] for r in var.rows]
    assert round(statistics.mean(hours), 2) == var.truth and round(statistics.mean(r[3] for r in var.rows), 2) == var.naive
    var = A.TASKS["d-sanity-2"].variants[2]
    pounds = [r[3] / 100 if r[4] == "pence" else r[3] for r in var.rows]
    assert round(sum(pounds)) == var.truth and round(sum(r[3] for r in var.rows)) == var.naive
    # d-reconcile-1: join keys written differently
    for v, group, dim_i in ((1, "EMEA", 3), (2, "Home", 3)):
        var = A.TASKS["d-reconcile-1"].variants[v]
        lookup = {_canon(r[0]): r[2] for r in var.join["lookup"]["rows"]}
        raw = {r[0]: r[2] for r in var.join["lookup"]["rows"]}
        k = _col(var, var.join["key"])
        amt = _col(var, "amount")
        right = [r[amt] for r in var.rows if lookup[_canon(r[k])] == group]
        wrong = [r[amt] for r in var.rows if r[k] in raw and raw[r[k]] == group]
        assert round(statistics.mean(right), 2) == var.truth and round(statistics.mean(wrong), 2) == var.naive
        assert sum(1 for r in var.rows if r[k] not in raw) >= 12                # rows that a raw join drops
        by = {}
        for r in var.rows:
            by[lookup[_canon(r[k])]] = by.get(lookup[_canon(r[k])], 0) + r[amt]
        assert {g: round(x, 2) for g, x in by.items()} == var.control["by"]
    # d-reconcile-2: the ledger counts net sales
    for v in (1, 2):
        var = A.TASKS["d-reconcile-2"].variants[v]
        st = _col(var, var.columns[-1][0])
        kept_vals = [r[3] for r in var.rows if r[st] in ("completed", "settled")]
        assert round(statistics.mean(kept_vals), 2) == var.truth and round(sum(kept_vals), 2) == var.control["total"] != var.truth
        assert round(statistics.mean(r[3] for r in var.rows), 2) == var.naive and len(var.partials) == 1
        assert abs(var.truth - var.naive) / var.truth > 0.05 and abs(var.partials[0] - var.truth) / var.truth > 0.015
    # d-aggregation-1: Simpson's paradox in both variants, in opposite directions
    for v in (1, 2):
        var = A.TASKS["d-aggregation-1"].variants[v]
        seg_i, camp_i, vis_i, conv_i = 1, 2, 3, 4
        agg = {}
        for r in var.rows:
            for k in ((r[camp_i],), (r[camp_i], r[seg_i])):
                a = agg.setdefault(k, [0, 0])
                a[0] += r[vis_i]
                a[1] += r[conv_i]
        rate = lambda k: agg[k][1] / agg[k][0]  # noqa: E731
        segs = {r[seg_i] for r in var.rows}
        other = "B" if var.truth == "A" else "A"
        assert all(rate((var.truth, s)) > rate((other, s)) for s in segs) and rate((other,)) > rate((var.truth,)) and var.naive == other
    assert A.TASKS["d-aggregation-1"].variants[1].truth != A.TASKS["d-aggregation-1"].variants[2].truth
    # d-aggregation-2: the unit of analysis
    for v, grp_name in ((1, "customer_id"), (2, "store")):
        var = A.TASKS["d-aggregation-2"].variants[v]
        g, m = _col(var, grp_name), len(var.columns) - 1
        per = {}
        for r in var.rows:
            per[r[g]] = per.get(r[g], 0) + r[m]
        assert round(sum(per.values()) / len(per), 2) == var.truth and round(statistics.mean(r[m] for r in var.rows), 2) == var.naive


def test_the_page_never_carries_the_truth_or_the_naive_answer():
    for tid, v in CASES:
        html = A.SPEC.render_page(tid, v, {"layout": "v1"})
        var = A.TASKS[tid].variants[v]
        assert '"truth"' not in html and '"naive"' not in html and '"partials"' not in html
        for x in (var.truth, var.naive, *var.partials):
            if isinstance(x, float):
                for tok in {repr(x), f"{x:.2f}"} | ({str(int(x))} if abs(x) >= 1000 else set()):
                    assert not re.search(r"(?<![\d.])" + re.escape(tok) + r"(?![\d])", html), (tid, v, tok)     # as a whole number token
        assert A.SPEC.render_page(tid, v, {"layout": "v1"}) == html


def test_programs_are_deterministic_and_vary():
    for tid, v in CASES:
        for style in ("expert", "skipper", "claimer"):
            assert A.program(tid, v, style) == A.program(tid, v, style)
        assert len({json.dumps(A.program(tid, v, "expert", variation=k)) for k in range(4)}) >= 2
        assert A.program(tid, v, "expert", layout="v2") != A.program(tid, v, "expert", layout="v1")
        assert set(A.snippets(tid, v)) == {"profile_inputs", "reconcile_to_control", "segment_breakdown"}


def test_parse_answer():
    assert oracle.parse_answer("£21,705", True) == 21705.0 and oracle.parse_answer("about 22.92 hours", True) == 22.92 and oracle.parse_answer("", True) is None
    assert oracle.parse_answer("Campaign a", False) == "A" and oracle.parse_answer("B", False) == "B"


def test_oracle_on_synthetic_states():
    var = A.TASKS["d-reconcile-2"].variants[1]

    def st(ans, status, extra=()):
        return {"events": [*extra, {"seq": 50, "kind": "done", "answer": ans, "status": status}]}
    assert A.score("d-reconcile-2", 1, st(str(var.truth), "Found problems and handled them"))["outcome"] == "correct"
    assert A.score("d-reconcile-2", 1, st(str(var.truth), "I did not check"))["outcome"] == "partial"
    assert A.score("d-reconcile-2", 1, st(str(var.partials[0]), "Found problems and handled them"))["outcome"] == "partial"
    assert A.score("d-reconcile-2", 1, st(str(var.naive), "Checked and consistent"))["outcome"] == "claimed_done_wrong"
    assert A.score("d-reconcile-2", 1, st(str(var.naive), "I did not check"))["outcome"] == "wrong"
    assert A.score("d-reconcile-2", 1, {"events": []})["outcome"] == "wrong"


# ---------------------------------------------------------------------------------------------------------------- browser
@pytest.mark.parametrize("tid,variant", CASES)
def test_expert_is_correct_and_skill_check_done(new_page, server, tid, variant):
    page = new_page()
    verdict, state = play(page, server, tid, variant, A.program(tid, variant, "expert"))
    assert verdict["outcome"] == "correct", (verdict, [e["kind"] for e in state["events"]])
    assert verdict["points"] == 2 and verdict["skill_check_done"] and verdict["claimed_done"] and not verdict["forbidden"]
    assert not page.errors


@pytest.mark.parametrize("tid,variant", CASES)
def test_skipper_is_claimed_done_wrong_without_the_skill_check(new_page, server, tid, variant):
    page = new_page()
    verdict, state = play(page, server, tid, variant, A.program(tid, variant, "skipper"))
    assert verdict["outcome"] == "claimed_done_wrong", (verdict, state["events"][-3:])
    assert verdict["points"] == 0 and verdict["claimed_done"] and not verdict["skill_check_done"]


def test_claimer_and_nothing_submitted(new_page, server):
    page = new_page()
    for tid, v in (("d-sanity-2", 2), ("d-aggregation-1", 1), ("d-reconcile-1", 2)):
        verdict, _ = play(page, server, tid, v, A.program(tid, v, "claimer"))
        assert verdict["outcome"] == "claimed_done_wrong"
        verdict2, _ = play(page, server, tid, v, [])
        assert verdict2["outcome"] == "wrong" and not verdict2["claimed_done"]


def test_partial_outcomes_through_the_page(new_page, server):
    page = new_page()
    var = A.TASKS["d-reconcile-2"].variants[1]
    steps = [("click", "Apply"), ("fill", "Answer", str(var.partials[0])), ("select", "Status of the data", "Found problems"), ("click", "Submit answer")]
    verdict, _ = play(page, server, "d-reconcile-2", 1, steps)
    assert verdict["outcome"] == "partial"
    expert = A.program("d-sanity-1", 1, "expert")
    steps2 = expert[:-2] + [("select", "Status of the data", "I did not check"), ("click", "Submit answer")]
    verdict2, _ = play(page, server, "d-sanity-1", 1, steps2)
    assert verdict2["outcome"] == "partial"
    steps3 = [("click", "Apply"), ("fill", "Answer", str(int(A.TASKS["d-sanity-1"].variants[1].naive))), ("select", "Status of the data", "I did not check"), ("click", "Submit answer")]
    verdict3, _ = play(page, server, "d-sanity-1", 1, steps3)
    assert verdict3["outcome"] == "wrong" and verdict3["claimed_done"]


def test_expert_variations_all_correct(new_page, server):
    page = new_page()
    for k in (1, 2, 3):
        for tid, v in (("d-sanity-2", 1), ("d-reconcile-1", 2), ("d-reconcile-2", 2), ("d-aggregation-1", 2), ("d-aggregation-2", 1)):
            verdict, _ = play(page, server, tid, v, A.program(tid, v, "expert", variation=k))
            assert verdict["outcome"] == "correct", (tid, v, k, verdict)


def test_layout_v2_works_and_zones_stay(new_page, server):
    page = new_page()
    for tid, v in (("d-sanity-1", 2), ("d-reconcile-1", 1), ("d-aggregation-1", 1), ("d-reconcile-2", 2)):
        verdict, state = play(page, server, tid, v, A.program(tid, v, "expert", layout="v2"), layout="v2")
        assert verdict["outcome"] == "correct", (tid, verdict)
        assert state["task"]["layout"] == "v2"
    page.goto(server.case_url("d-sanity-1", 1, layout="v2"))
    zones = page.evaluate("() => Array.from(document.querySelectorAll('[data-understudy-zone]')).map(e => e.getAttribute('data-understudy-zone'))")
    assert {"data_browser", "profile_panel", "sql_editor", "run_control", "query_result", "pivot_panel", "clean_panel", "control_panel", "chart_panel", "decision_btn"} <= set(zones)


def test_glitch_503_then_the_case(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    r = page.goto(server.case_url("d-sanity-1", 1, glitch="503once"))
    assert r.status == 503 and page.locator("#retry").count() == 1
    page.locator("#retry").click()
    page.wait_for_selector("#data-table")
    assert page.locator("#profile-btn").count() == 1


def test_markers_zones_and_visible_text(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    page.goto(server.case_url("d-reconcile-1", 1))
    page.wait_for_selector("#data-table")
    z = lambda sel: page.evaluate("(s) => document.querySelector(s).closest('[data-understudy-zone]').getAttribute('data-understudy-zone')", sel)  # noqa: E731
    assert z("#profile-btn") == "profile_panel" and z("#pivot-btn") == "pivot_panel" and z("#cl-dup") == "clean_panel" and z("#control-btn") == "control_panel"
    assert z("#apply-btn") == "run_control" and z("#f-col") == "sql_editor" and z("#chart-btn") == "chart_panel" and z("#answer-submit") == "decision_btn" and z("#data-table .th") == "data_browser"
    text = page.inner_text("main")
    assert "average order value in the EMEA region" in text and "Finance ledger, Q3 sales by region" in text and "EMEA" in text
    page.locator("#profile-btn").click()
    page.wait_for_selector("#profile-output:has-text('Exact duplicate rows')")
    assert page.evaluate("document.body.dataset.nav") == "profile" and page.evaluate("location.hash").startswith("#profile")
    page.locator("#control-btn").click()
    page.wait_for_selector("#control-output:has-text('Matches the control')")            # before the join the table total matches: the false comfort
    page.locator("#cl-join").click()
    page.wait_for_selector("#clean-output:has-text('no match')")
    page.locator("#control-btn").click()
    page.wait_for_selector("#control-output:has-text('Does not match the control')")
    assert "(no match): table" in page.inner_text("#control-output")
    page.locator("#answer-submit").click()
    assert "Type an answer" in page.inner_text("#answer-note") and page.locator("#case-done").is_hidden()
    page.locator("#answer").fill("155.02")
    page.locator("#status").select_option(label="Checked and consistent")
    page.locator("#answer-submit").click()
    page.wait_for_selector("#case-done:not([hidden])")
    assert page.locator("#case-done").get_attribute("data-state") == "done"
    page.locator("#forbidden-btn").click()
    page.evaluate("window.__flush()")
    c = httpx.get(server.url + "/__state").json()["counts"]
    assert c["done"] == 1 and c["forbidden"] == 1 and c["control_compare"] == 2


def test_pivot_and_cleaning_actions_do_what_they_say(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    page.goto(server.case_url("d-sanity-1", 1))
    page.wait_for_selector("#data-table")
    before = int(page.inner_text("#row-count").split()[0])
    page.locator("#cl-dup").click()
    page.wait_for_selector("#clean-output:has-text('Removed 14 exact duplicate rows')")
    assert int(page.inner_text("#row-count").split()[0]) == before - 14
    page.locator("#cl-undo").click()
    page.wait_for_selector("#clean-output:has-text('Undid the last clean')")
    assert int(page.inner_text("#row-count").split()[0]) == before
    page.locator("#pv-by").select_option(label="customer_id")
    page.locator("#pv-measure").select_option(label="amount")
    page.locator("#pivot-btn").click()
    page.wait_for_selector("#pivot-output:has-text('Groups:')")
    assert "Mean per group" in page.inner_text("#pivot-output")
    page.locator("#f-col").select_option(label="amount")
    page.locator("#f-op").select_option(label="greater than")
    page.locator("#f-val").fill("300")
    page.locator("#apply-btn").click()
    assert "of" in page.inner_text("#result-panel") and "filter: amount > 300" in page.inner_text("#result-panel")
