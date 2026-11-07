"""The pack's capture config (task_start / progress / task_end markers and the nav zones) evaluated against the real sandbox pages. A marker that is already true at page load
would close the task at once (a bug the first fake study found: #case-done existed in the DOM, hidden), so each selector is checked before and after the action it stands for."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from understudy_agent.sandbox_roles import analyst as A
from understudy_agent.sandbox_roles import programmer as P
from understudy_agent.sandbox_roles.programs_util import run_program

PACKS = Path(__file__).resolve().parents[4] / "packages" / "packs"


def site(role: str) -> dict:
    m = yaml.safe_load((PACKS / role / "mapping.yaml").read_text())
    return next(s for s in m["capture_sites"] if s["id"] == "roles_sandbox")


def matches(page, selector: str) -> bool:
    """True when the selector matches now, allowing the page its own short moment to set a marker after the visible result (the log is posted first)."""
    try:
        page.wait_for_selector(selector, state="attached", timeout=3000)
        return True
    except Exception:  # noqa: BLE001
        return False


def absent(page, selector: str) -> bool:
    return page.query_selector(selector) is None


def test_programmer_markers_false_at_load_true_after_the_action(new_page):
    cfg = site("programmer")
    end = cfg["markers"]["task_end"]["when"]
    nav = {r["zone"]: r["when"] for r in cfg["nav"]}
    prog = {p["kind"]: p["when"] for p in cfg["markers"]["progress"]}
    with P.make_server(0) as s:
        page = new_page()
        httpx.post(s.url + "/__reset")
        page.goto(s.case_url("p-boundary-1", 1))
        page.wait_for_selector("#editor")
        assert absent(page, end) and all(absent(page, w) for w in nav.values()) and all(absent(page, w) for w in prog.values())
        page.locator("#run-tests").click()
        page.wait_for_selector("#tests-status:not([data-state=idle])")
        assert matches(page, nav["test_report"]) and matches(page, prog["tests_run"]) and absent(page, end)
        run_program(page, [("fill", "editor", P.reference("p-boundary-1", 1)["src/pagination.js"]), ("click", "Stage src/pagination.js"), ("fill", "Message", "Fix pageCount: round up"), ("click", "Commit")])
        page.wait_for_selector("#git-log li[data-commit]")
        assert matches(page, nav["commit_box"]) and matches(page, prog["committed"])
        page.locator("#done-btn").click()
        page.wait_for_selector("#case-done:not([hidden])")
        assert matches(page, end) and matches(page, nav["decision_btn"])


def test_analyst_markers_false_at_load_true_after_the_action(new_page):
    cfg = site("data-analyst")
    end = cfg["markers"]["task_end"]["when"]
    nav = {r["zone"]: r["when"] for r in cfg["nav"]}
    prog = {p["kind"]: p["when"] for p in cfg["markers"]["progress"]}
    with A.make_server(0) as s:
        page = new_page()
        httpx.post(s.url + "/__reset")
        page.goto(s.case_url("d-reconcile-1", 1))
        page.wait_for_selector("#data-table")
        assert absent(page, end) and all(absent(page, w) for w in nav.values())
        page.locator("#profile-btn").click()
        page.wait_for_selector("#profile-output:has-text('Rows:')")
        assert matches(page, nav["profile_panel"]) and matches(page, prog["profiled"])
        page.locator("#cl-join").click()
        page.wait_for_selector("#clean-output:has-text('no match')")
        assert matches(page, nav["clean_panel"])
        page.locator("#control-btn").click()
        page.wait_for_selector("#control-output:has-text('control')")
        assert matches(page, nav["control_panel"]) and matches(page, prog["reconciled"])
        page.locator("#pivot-btn").click()
        page.wait_for_selector("#pivot-output:has-text('Groups')")
        assert matches(page, nav["pivot_panel"]) and matches(page, prog["aggregated"])
        page.locator("#answer").fill("1")
        page.locator("#status").select_option(label="I did not check")
        page.locator("#answer-submit").click()
        page.wait_for_selector("#case-done:not([hidden])")
        assert matches(page, end) and matches(page, nav["decision_btn"])


@pytest.mark.parametrize("role", ["programmer", "data-analyst"])
def test_the_sites_hosts_cover_the_private_ports_and_the_zones_of_elements_exist(role):
    cfg = site(role)
    ports = range(7941, 7949) if role == "programmer" else range(7951, 7959)
    assert all(f"127.0.0.1:{p}" in cfg["hosts"] and f"localhost:{p}" in cfg["hosts"] for p in ports)
    assert cfg["markers"]["task_start"]["zone"] == cfg["nav_default"]
