"""The programmer workbench end to end: the catalogue, the oracle on scripted programs, safety of the runner, layouts and glitches.
Playwright against a RoleServer on an ephemeral port (no model, no network)."""
from __future__ import annotations

import json

import httpx
import pytest

from understudy_agent.sandbox_roles import programmer as P
from understudy_agent.sandbox_roles.programmer import oracle
from understudy_agent.sandbox_roles.programs_util import ControlNotFound, run_program

from .helpers import play

CASES = [(tid, v) for tid, t in P.TASKS.items() for v in sorted(t.variants)]


@pytest.fixture(scope="module")
def server():
    with P.make_server(0) as s:
        yield s


# ---------------------------------------------------------------------------------------------------------------- pure
def test_catalogue_shape():
    assert len(P.TASKS) == 6 and len(CASES) == 12
    assert {t.skill for t in P.TASKS.values()} == {"boundary", "missing", "discipline"}
    for skill, info in P.SKILLS.items():
        assert len(info["task_ids"]) == 2 and all(P.TASKS[i].skill == skill for i in info["task_ids"])
    assert {i["pack_skill_id"] for i in P.SKILLS.values()} == {"probe-the-boundary", "inspect-the-inputs", "test-first-clean-commits"}
    for t in P.TASKS.values():
        v1, v2 = t.variants[1], t.variants[2]
        assert v1.files != v2.files and v1.ticket != v2.ticket and v1.reference != v2.reference
        assert sum(h.tag == "edge" for h in v1.hidden) >= 3 and sum(h.tag == "core" for h in v1.hidden) >= 2
        assert abs(len(v1.hidden) - len(v2.hidden)) <= 2
        for v in (v1, v2):
            assert set(v.reference) == set(v.naive)
            assert all(len(c.splitlines()) <= 30 for c in v.files.values())


def test_hidden_tests_and_solutions_are_not_in_the_page():
    for tid, v in CASES:
        html = P.SPEC.render_page(tid, v, {"layout": "v1"})
        var = P.TASKS[tid].variants[v]
        for h in var.hidden:
            if h.tag == "edge":
                assert h.code not in html
        for content in list(var.reference.values()) + list(var.naive.values()):
            if content not in var.files.values():
                assert content not in html


def test_programs_are_deterministic_and_vary():
    for tid, v in CASES:
        for style in ("expert", "skipper", "claimer"):
            assert P.program(tid, v, style) == P.program(tid, v, style)
        orders = {json.dumps(P.program(tid, v, "expert", variation=k)) for k in range(4)}
        assert len(orders) >= 3
        assert P.program(tid, v, "expert", layout="v2") != P.program(tid, v, "expert", layout="v1")
        assert set(P.snippets(tid, v)) >= {"probe_edges", "inspect_inputs", "review_diff", "write_failing_test"}


def test_oracle_refuses_an_ungraded_state():
    with pytest.raises(ValueError):
        oracle.score("p-boundary-1", 1, {"events": [], "final": None})


def test_good_message_rules():
    kw = ("greeting", "noon")
    assert oracle.good_message("Fix greeting at noon: 12 is the afternoon", kw)
    assert not oracle.good_message("fix", kw) and not oracle.good_message("fix stuff", kw) and not oracle.good_message("update the thing today", kw)
    assert not oracle.good_message("Tidy the module quickly", kw)


# ---------------------------------------------------------------------------------------------------------------- browser
@pytest.mark.parametrize("tid,variant", CASES)
def test_expert_is_correct_and_skill_check_done(new_page, server, tid, variant):
    page = new_page()
    verdict, state = play(page, server, tid, variant, P.program(tid, variant, "expert"))
    assert verdict["outcome"] == "correct", (verdict, [e["kind"] for e in state["events"]])
    assert verdict["points"] == 2 and verdict["skill_check_done"] and verdict["claimed_done"]
    assert not page.errors


@pytest.mark.parametrize("tid,variant", CASES)
def test_skipper_is_partial_and_misses_the_edge(new_page, server, tid, variant):
    page = new_page()
    verdict, state = play(page, server, tid, variant, P.program(tid, variant, "skipper"))
    assert verdict["outcome"] == "partial", verdict
    assert verdict["points"] == 1 and verdict["claimed_done"]
    if P.TASKS[tid].kind != "commit_hygiene":
        assert verdict["edge_cases_missed"], verdict
    assert not verdict["skill_check_done"], verdict


@pytest.mark.parametrize("tid,variant", [("p-boundary-1", 1), ("p-missing-2", 2), ("p-discipline-1", 1), ("p-discipline-2", 2)])
def test_claimer_is_claimed_done_wrong_and_nothing_started_is_wrong(new_page, server, tid, variant):
    page = new_page()
    verdict, _ = play(page, server, tid, variant, P.program(tid, variant, "claimer"))
    assert verdict["outcome"] == "claimed_done_wrong" and verdict["points"] == 0 and verdict["claimed_done"]
    verdict2, _ = play(page, server, tid, variant, [])
    assert verdict2["outcome"] == "wrong" and not verdict2["claimed_done"]


def test_expert_variations_all_correct(new_page, server):
    page = new_page()
    for k in (1, 2, 3):
        for tid, v in (("p-boundary-2", 1), ("p-discipline-1", 2), ("p-discipline-2", 1), ("p-missing-1", 2)):
            verdict, _ = play(page, server, tid, v, P.program(tid, v, "expert", variation=k))
            assert verdict["outcome"] == "correct", (tid, v, k, verdict)


def test_layout_v2_works_and_zones_stay(new_page, server):
    page = new_page()
    for tid, v in (("p-boundary-1", 1), ("p-missing-2", 1), ("p-discipline-2", 2), ("p-discipline-1", 1)):
        verdict, state = play(page, server, tid, v, P.program(tid, v, "expert", layout="v2"), layout="v2")
        assert verdict["outcome"] == "correct", (tid, verdict)
        assert state["task"]["layout"] == "v2"
    page.goto(server.case_url("p-boundary-1", 1, layout="v2"))
    zones = page.evaluate("() => Array.from(document.querySelectorAll('[data-understudy-zone]')).map(e => e.getAttribute('data-understudy-zone'))")
    assert {"test_runner", "edge_probe", "input_data", "commit_box", "diff_view", "decision_btn", "code_view", "ci_log", "code_editor"} <= set(zones)


def test_glitch_503_then_the_case(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    r = page.goto(server.case_url("p-boundary-1", 1, glitch="503once"))
    assert r.status == 503 and page.locator("#retry").count() == 1
    page.locator("#retry").click()
    page.wait_for_selector("#editor")
    assert page.locator("#run-tests").count() == 1


def test_zones_and_markers_on_the_page(new_page, server):
    page = new_page()
    page.goto(server.case_url("p-discipline-2", 1))
    page.wait_for_selector("#editor")
    z = lambda sel: page.evaluate("(s) => document.querySelector(s).closest('[data-understudy-zone]').getAttribute('data-understudy-zone')", sel)  # noqa: E731
    assert z("#run-tests") == "test_runner" and z("#probe-run") == "edge_probe" and z("#commit-btn") == "commit_box" and z("#diff-btn") == "diff_view"
    assert z("#done-btn") == "decision_btn" and z("#file-tree button") == "code_view" and z("#test-output") == "ci_log" and z("#inputs-panel summary") == "input_data"
    assert page.locator("#editor").get_attribute("data-understudy-zone") == "code_editor"
    page.locator("#file-tree button", has_text="tests/greeting.test.js").click()
    assert page.locator("#editor").get_attribute("data-understudy-zone") == "test_editor"
    assert page.locator("#tests-status").get_attribute("data-state") == "idle"
    page.locator("#run-tests").click()
    page.wait_for_selector("#tests-status:not([data-state=idle])")
    assert page.locator("#tests-status").get_attribute("data-state") == "fail"
    assert "FAIL noon is already the afternoon" in page.inner_text("#test-output")
    assert page.evaluate("document.body.dataset.nav") == "run"
    assert page.evaluate("location.hash").startswith("#run")
    assert page.locator("#case-done").is_hidden()
    page.locator("#done-btn").click()
    page.wait_for_selector("#case-done:not([hidden])")
    assert page.locator("#case-done").get_attribute("data-state") == "done" and page.locator("#case-done").is_visible()


def test_the_runner_is_walled_in(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    page.goto(server.case_url("p-boundary-1", 1))
    page.wait_for_selector("#editor")
    page.locator("#file-tree button", has_text="src/pagination.js").click()      # an infinite loop is cut off and the page stays usable
    page.locator("#editor").fill("function pageCount(total, pageSize) { while (true) {} }\n")
    page.locator("#run-tests").click()
    page.wait_for_selector("#tests-status:not([data-state=idle])", timeout=8000)
    assert "timed out" in page.inner_text("#test-output")
    page.locator("#editor").fill("function pageCount(total, pageSize) { return Math.ceil(total / pageSize); }\n")
    page.locator("#run-tests").click()
    page.wait_for_selector("#tests-status[data-state=pass]", timeout=8000)
    # user code cannot reach the network from the worker (fetch is removed)
    page.locator("#probe-input").fill("fetch('/__state')")
    page.locator("#probe-run").click()
    page.wait_for_selector("#probe-output:has-text('Error')", timeout=5000)
    page.locator("#probe-input").fill("typeof XMLHttpRequest + ' ' + typeof WebSocket + ' ' + typeof importScripts")
    page.locator("#probe-run").click()
    page.wait_for_selector("#probe-output:has-text('= ')", timeout=5000)
    assert "undefined undefined undefined" in page.inner_text("#probe-output")
    assert page.evaluate("fetch('https://example.org/').then(() => 'reached', () => 'blocked')") == "blocked"   # the CSP forbids other origins


def test_a_reload_resets_the_repo_in_the_page_but_the_server_keeps_its_log(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    page.goto(server.case_url("p-boundary-1", 2))
    page.wait_for_selector("#editor")
    page.locator("#run-tests").click()
    page.wait_for_selector("#tests-status:not([data-state=idle])")
    page.evaluate("window.__flush()")
    page.reload()
    page.wait_for_selector("#editor")
    assert page.locator("#tests-status").get_attribute("data-state") == "idle"
    assert httpx.get(server.url + "/__state").json()["counts"]["run_tests"] == 1


def test_a_participant_cannot_commit_nothing_or_without_a_message(new_page, server):
    page = new_page()
    httpx.post(server.url + "/__reset")
    page.goto(server.case_url("p-boundary-2", 1))
    page.wait_for_selector("#editor")
    page.locator("#commit-btn").click()
    assert "Nothing is staged" in page.inner_text("#git-note")
    page.locator("#editor").fill(P.reference("p-boundary-2", 1)["src/range.js"])
    page.locator("#changes input[type=checkbox]").first.check()
    page.locator("#commit-btn").click()
    assert "needs a message" in page.inner_text("#git-note")
    page.locator("#commit-message").fill("Fix inRange: include both ends")
    page.locator("#commit-btn").click()
    page.wait_for_selector("#git-log li[data-commit]")
    assert "No changes" in page.inner_text("#changes")


def test_unknown_control_is_a_script_error_not_a_click(new_page, server):
    page = new_page()
    page.goto(server.case_url("p-boundary-1", 1))
    with pytest.raises(ControlNotFound):
        run_program(page, [("click", "No such button")])
