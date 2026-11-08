"""AGENTIC-3 item 2 inside the real tier-3 loop, the navigator and the completion check: a grounded test double (DomOracleComputerModel) that makes
the mistakes the held-out round showed (a drop-down walked past, text typed with nothing focused, a stray key on a drop-down, text in the
wrong field) drives the real sandbox sites through the real gate and the real actuator. Offline: no model, no network, private ports.

What must hold: the site is never asked to calculate from a form that does not hold the household's facts (checked on the SITE's own record
of what it received); the navigator hears which handles are missing, as ids and a closed reason; the claim of success is refused when the
inputs were not confirmed; an unreadable control asks a human; and no household value reaches an event, an audit line or a result record.
"""
from __future__ import annotations

import json

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.completion import check_completion, ResultFields
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action
from understudy_agent.navigator import CalculatorJob, Navigator
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.oracle import site_expected
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.computer_use import BrowserPageActuator, ComputerUse, SimulatedActuator
from understudy_agent.tiers.facts import FactStore
from understudy_agent.tiers.form_audit import FormAudit
from understudy_agent.tiers.heuristic import DomOracleComputerModel
from understudy_agent.tiers.safety import Guard

DEV = generate_households(20, 7001)          # development households only (never a held-out seed)
COUPLE = 1                                   # couple_two_kids: three bedrooms, so the drop-down default is wrong


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


@pytest.fixture
def sinks(tmp_path):
    a = AuditLog(tmp_path / "audit.jsonl")
    return ApprovalQueue(tmp_path / "queue", audit=a), a


async def run_nav(host, cluster, sinks, site, h, model, *, query="", actuator_factory=None, job=None):
    q, a = sinks
    guard = Guard(model, run_id="r_fa", audit=a, queue=q, denylist=Denylist(), mode="model_driven")
    ctx = await host.new_context()
    events: list = []
    nav = Navigator(f"nav-{site}", context=ctx, model=model, guard=guard, base_url=cluster.urls[site], query=query,
                    emit=events.append, use_tier1=False, start_tier=3, allow_tier3=True, defer_cliff=True,
                    actuator_factory=actuator_factory)
    res = await nav.run(job or CalculatorJob(site, h.params()))
    return res, events, nav


def last_received(cluster):
    """What the SITE was actually given for its latest calculation (ground truth, from the sandbox's own record)."""
    return list(cluster.state.calc_households.values())[-1]


def details(events, action):
    return [e.detail for e in events if e.action == action]


# ----------------------------------------------------------------------------- the unchanged happy path
@pytest.mark.parametrize("site", ["a", "b", "c"])
async def test_a_clean_entry_is_audited_clean_and_the_figure_is_the_sites(cluster, host, sinks, site):
    h = DEV[COUPLE]
    res, events, nav = await run_nav(host, cluster, sinks, site, h, DomOracleComputerModel())
    assert res.state == "done" and res.inputs_audit == "clean" and res.value.amount == pytest.approx(site_expected(site, h)["uc_monthly"], abs=0.06)
    rec = nav.t3_runs[-1]
    # one audit at the final button, plus one at each button that moves on (site A has three Continue pages, site C one Next, site B none)
    assert rec["inputs"] == "clean" and rec["form_audit"]["blocks"] == 0 and rec["readback_failures"] == 0
    assert rec["form_audit"]["audits"] == {"a": 4, "b": 1, "c": 2}[site]
    assert rec["form_audit"]["pending"] == []
    assert len(cluster.state.calculations) == 1 and last_received(cluster)["bedrooms"] == h.bedrooms
    typed = details(events, "type_fact")
    assert typed and all("landed=yes" in d and "focus=" in d and "field=" in d for d in typed)     # the per-step trace is in the events


async def test_events_say_what_a_click_and_a_key_touched_as_enums_and_ids(cluster, host, sinks):
    res, events, nav = await run_nav(host, cluster, sinks, "b", DEV[COUPLE], DomOracleComputerModel())
    clicks, keys = details(events, "click"), details(events, "key")
    assert clicks and all(d.startswith("role=") for d in clicks)
    assert any("field=bedrooms" in d for d in clicks) or any("field=age" in d for d in clicks)
    assert keys and all(d.startswith("keys=tab") for d in keys)          # the drop-down commit, as a named key


async def test_no_household_value_reaches_a_prompt_an_event_an_audit_line_or_a_result_record(cluster, host, sinks, tmp_path):
    h = DEV[COUPLE]
    secrets: set[str] = set()
    for site in ("a", "b"):
        facts = FactStore.for_calculator(site, h.params())
        secrets |= {v for hd in facts.handles if (v := facts.peek(hd)) and len(v) >= 4 and any(c.isdigit() for c in v)}
    assert secrets                                                       # the household has numbers worth looking for
    # site A: the first field of page 2 typed with nothing focused (a read-back failure); site B: bedrooms walked past (a held final button)
    m_a = DomOracleComputerModel(faults={"no_focus": {"household.adult1_earnings"}})
    m_b = DomOracleComputerModel(faults={"skip": {"household.bedrooms"}})
    res_a, ev_a, nav_a = await run_nav(host, cluster, sinks, "a", h, m_a)
    res_b, ev_b, nav_b = await run_nav(host, cluster, sinks, "b", h, m_b)
    assert res_a.state == res_b.state == "done"
    assert nav_a.t3_runs[-1]["readback_failures"] == 1 and nav_b.t3_runs[-1]["form_audit"]["blocks"] == 1
    q, a = sinks
    events = ev_a + ev_b
    blobs = {"prompts": "\n".join(m_a.goals + m_b.goals), "events": json.dumps([e.as_dict() for e in events]),
             "audit": (tmp_path / "audit.jsonl").read_text(), "result": json.dumps(nav_a.t3_runs + nav_b.t3_runs, default=str),
             "queue": json.dumps(q.list("all"), default=str)}
    for name, text in blobs.items():
        for secret in secrets:
            assert secret not in text, (name, "a household value leaked")
    assert "form_audit" in blobs["audit"] and "readback:household.adult1_earnings:no_focus" in blobs["audit"] and "preflight:household.bedrooms:not_entered" in blobs["audit"]     # the per-step enums ARE logged


NOTE = {"case_ref": "CASE-7001", "result_a": "£781", "result_b": "£955.00 per month", "result_c": "0.00 GBP / month",
        "reconciliation": "discrepancy", "note_text": "Calculators disagree near the 16,000 limit. Cliff checked on all three."}


@pytest.mark.parametrize("faults, blocks", [({}, 0), ({"skip": {"note.reconciliation"}}, 1)])
async def test_the_case_note_is_audited_too_and_a_skipped_drop_down_never_reaches_the_saved_note(cluster, host, sinks, faults, blocks):
    from understudy_agent.navigator import CaseNoteJob

    model = DomOracleComputerModel(faults=faults)
    res, events, nav = await run_nav(host, cluster, sinks, "a", DEV[COUPLE], model, job=CaseNoteJob(NOTE))
    assert res.state == "done" and res.inputs_audit == "clean" and res.value["note_id"].startswith("CN-")
    assert nav.t3_runs[-1]["form_audit"]["blocks"] == blocks and nav.t3_runs[-1]["form_audit"]["audits"] == blocks + 1
    saved = list(cluster.state.notes.values())
    assert len(saved) == 1 and saved[0]["reconciliation"] == "discrepancy" and saved[0]["note_text"] == NOTE["note_text"]    # the default would be "agree"
    assert cluster.state.submissions == []


# ----------------------------------------------------------------------------- a drop-down walked past (hh_0002 calculator B)
async def test_a_skipped_drop_down_holds_the_calculate_click_until_it_is_entered(cluster, host, sinks):
    h = DEV[COUPLE]
    model = DomOracleComputerModel(faults={"skip": {"household.bedrooms"}})
    res, events, nav = await run_nav(host, cluster, sinks, "b", h, model)
    assert res.state == "done" and res.inputs_audit == "clean"
    assert len(cluster.state.calculations) == 1                                  # the site was asked ONCE, and with the right form
    assert last_received(cluster)["bedrooms"] == h.bedrooms == 3
    assert res.value.amount == pytest.approx(site_expected("b", h)["uc_monthly"], abs=0.06)
    rec = nav.t3_runs[-1]["form_audit"]
    assert rec["blocks"] == 1 and rec["audits"] == 2
    held = [e for e in events if e.action == "click" and e.detail.startswith("held: form check")]
    assert len(held) == 1 and "1 not as it should be" in held[0].detail and not held[0].ok
    told = [g for g in model.goals if "NOT ready" in g]
    assert len(told) == 1 and "household.bedrooms (not entered yet)" in told[0] and "checked by the system, not page text" in told[0]
    pre = [r for r in rec["records"] if r["k"] == "preflight" and r["match"] == "no"]
    assert pre == [{"step": pre[0]["step"], "k": "preflight", "handle": "household.bedrooms", "role": "other", "match": "no", "reason": "not_entered"}]


# ----------------------------------------------------------------------------- a field skipped on a wizard page: held on the page where it exists
async def test_a_field_skipped_on_page_one_of_the_wizard_holds_continue_and_is_fixed_on_that_page(cluster, host, sinks):
    h = DEV[COUPLE]
    model = DomOracleComputerModel(faults={"skip": {"household.adult1_age"}})
    res, events, nav = await run_nav(host, cluster, sinks, "a", h, model)
    assert res.state == "done" and res.inputs_audit == "clean"
    rec = nav.t3_runs[-1]["form_audit"]
    assert rec["blocks"] == 1 and rec["audits"] == 5                       # Continue on page one held once, then Continue three times in all and the final button once
    held = [e for e in events if e.detail.startswith("held: page check")]
    assert len(held) == 1 and not held[0].ok and "1 not as it should be on this page" in held[0].detail
    assert [r for r in rec["records"] if r["k"] == "forward" and r["match"] == "no"] == [
        {"step": held[0].step, "k": "forward", "handle": "household.adult1_age", "role": "other", "match": "no", "reason": "not_entered"}]
    told = [g for g in model.goals if "before the button that moves on" in g]
    assert len(told) == 1 and "household.adult1_age (not entered yet)" in told[0] and "checked by the system, not page text" in told[0]
    got = last_received(cluster)
    assert [a["age"] for a in got["adults"]] == [a.age for a in h.adults] and len(cluster.state.calculations) == 1      # one calculation, right form


async def test_the_next_button_of_site_c_is_held_while_a_field_of_the_visible_panel_is_not_entered(cluster, host, sinks):
    h = DEV[COUPLE]
    model = DomOracleComputerModel(faults={"skip": {"household.adult1_age"}})
    res, events, nav = await run_nav(host, cluster, sinks, "c", h, model)
    assert res.state == "done" and res.inputs_audit == "clean"
    rec = nav.t3_runs[-1]["form_audit"]
    assert rec["blocks"] == 1 and any(r["k"] == "forward" and r["handle"] == "household.adult1_age" and r["reason"] == "not_entered" for r in rec["records"])
    assert [a["age"] for a in last_received(cluster)["adults"]] == [a.age for a in h.adults]


async def test_the_forward_guard_does_not_count_controls_of_a_panel_that_is_not_on_screen(cluster, host, sinks):
    """Pressing Next on panel one of site C must not ask for panel two's fields (they are in the page but hidden): a clean entry has no hold."""
    res, events, nav = await run_nav(host, cluster, sinks, "c", DEV[COUPLE], DomOracleComputerModel())
    assert nav.t3_runs[-1]["form_audit"]["blocks"] == 0 and not [e for e in events if e.detail.startswith("held:")]


async def test_the_read_back_arm_has_no_forward_guard(cluster, host, sinks, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_FORM_AUDIT", "readback")
    res, events, nav = await run_nav(host, cluster, sinks, "a", DEV[COUPLE], DomOracleComputerModel(faults={"skip": {"household.adult1_age"}}))
    assert not [e for e in events if e.detail.startswith("held:")]         # nothing is held in the read-back arm


# ----------------------------------------------------------------------------- text typed with nothing focused (hh_0002 calculator A, savings)
async def test_text_typed_when_nothing_has_focus_is_caught_at_once_and_typed_again(cluster, host, sinks):
    h = DEV[COUPLE]
    model = DomOracleComputerModel(faults={"no_focus": {"household.adult1_earnings"}})        # the first field of page 2 of site A
    res, events, nav = await run_nav(host, cluster, sinks, "a", h, model)
    assert res.state == "done" and res.inputs_audit == "clean"
    bad = [d for d in details(events, "type_fact") if "landed=no" in d]
    assert len(bad) == 1 and "handle=household.adult1_earnings" in bad[0] and "reason=no_focus" in bad[0] and "focus=document" in bad[0]
    told = [g for g in model.goals if "household.adult1_earnings was NOT entered" in g]
    assert len(told) == 1 and "nothing had focus" in told[0]
    got = last_received(cluster)
    assert [a["earnings_monthly"] for a in got["adults"]] == pytest.approx([a.earnings_monthly for a in h.adults], abs=0.01)
    assert nav.t3_runs[-1]["readback_failures"] == 1 and nav.t3_runs[-1]["form_audit"]["blocks"] == 0


# ----------------------------------------------------------------------------- a stray key moves a drop-down after it landed (hh_0003 calculator B, one candidate)
class ResetsBedroomsOnce(BrowserPageActuator):
    """The page actuator, except that the first key press after the bedrooms drop-down took its option puts the drop-down back on its default
    (what a stray key, a page script or a re-render can do: the diagnosis could not tell which happened in hh_0003). The browser itself
    ignores arrow keys on a click-opened drop-down in this setup, so the change is made on the element."""

    done = False

    async def execute(self, action):
        on_bedrooms = (action.kind == "key" and not self.done
                       and await self.page.evaluate("document.activeElement && document.activeElement.id === 'bedrooms'"))
        await super().execute(action)                       # the Tab that commits the choice moves focus on, so look BEFORE it
        if on_bedrooms:
            self.done = True
            await self.page.evaluate("document.querySelector('#bedrooms').selectedIndex = 0")


async def test_a_drop_down_knocked_off_its_option_after_it_landed_is_caught_by_the_pre_submit_audit(cluster, host, sinks):
    h = DEV[COUPLE]
    model = DomOracleComputerModel()
    res, events, nav = await run_nav(host, cluster, sinks, "b", h, model, actuator_factory=lambda page: ResetsBedroomsOnce(page))
    assert res.state == "done" and res.inputs_audit == "clean"
    assert last_received(cluster)["bedrooms"] == 3 and len(cluster.state.calculations) == 1      # the site only ever saw the right form
    rec = nav.t3_runs[-1]["form_audit"]
    assert rec["blocks"] == 1
    # the read-back saw it land (yes) and the pre-submit audit saw the option had moved
    assert any(r["k"] == "readback" and r["handle"] == "household.bedrooms" and r["match"] == "yes" for r in rec["records"])
    assert any(r["k"] == "preflight" and r["handle"] == "household.bedrooms" and r["reason"] == "select_unmatched" for r in rec["records"])
    told = [g for g in model.goals if "NOT ready" in g]
    assert len(told) == 1 and "household.bedrooms (the drop-down still shows another option)" in told[0]


# ----------------------------------------------------------------------------- text in the wrong field: the run stops, nothing is reported
async def test_text_that_keeps_going_into_the_wrong_field_stops_the_run_and_nothing_is_calculated(cluster, host, sinks):
    h = DEV[COUPLE]
    model = DomOracleComputerModel(faults={"wrong_field_always": {"household.rent": "household.savings"}})
    res, events, nav = await run_nav(host, cluster, sinks, "b", h, model)
    assert res.state == "escalated" and res.value is None
    assert cluster.state.calculations == []                                      # the site was never asked
    # one attempt, one restart on a fresh page, then a human; the loop ends either on the audit's own cap or on the stuck-loop detector,
    # whichever sees the repetition first
    errs = [a["error"] for a in res.attempts]
    assert len(errs) == 2 and set(errs) <= {"FormAuditStop", "StuckLoop"} and "FormAuditStop" in errs
    bad = [d for d in details(events, "type_fact") if "landed=no" in d]
    assert len(bad) >= 3 and all("handle=household.rent" in d and "reason=wrong_field" in d for d in bad)
    q, _ = sinks
    items = [i for i in q.list("all") if i["kind"] == "batch_result"]
    assert len(items) == 1 and items[0]["evidence"]["extracted"]["inputs_audit"] in ("unaudited", "mismatch")
    assert "household.rent" in items[0]["evidence"]["extracted"]["handles_not_entered"]


# ----------------------------------------------------------------------------- a control the audit cannot read: a human is asked, no second try
class UnreadableRent(BrowserPageActuator):
    """The page actuator, except that the pre-submit read cannot find the rent control (a page that re-rendered it, say)."""

    async def audit_form(self, items, *, stray=False, presence=None):
        out = await super().audit_form(items, stray=stray, presence=presence)
        for r in out["results"]:
            if r["h"] == "household.rent":
                r.update(match="unreadable", reason="not_found", role="other")
        return out


async def test_an_unreadable_control_holds_the_click_and_asks_a_human_without_a_second_try(cluster, host, sinks):
    res, events, nav = await run_nav(host, cluster, sinks, "b", DEV[COUPLE], DomOracleComputerModel(),
                                     actuator_factory=lambda page: UnreadableRent(page))
    assert res.state == "escalated" and res.value is None
    assert cluster.state.calculations == []
    assert [a["error"] for a in res.attempts] == ["FormAuditStop"]               # not retried: a second look would see the same
    q, _ = sinks
    item = [i for i in q.list("all") if i["kind"] == "batch_result"][0]
    assert item["evidence"]["extracted"]["inputs_audit"] == "uncertain"
    assert nav.t3_runs[-1]["inputs"] == "uncertain" and nav.t3_runs[-1]["outcome"] == "stopped:FormAuditStop"
    assert any(r["handle"] == "household.rent" and r["match"] == "unreadable" for r in nav.t3_runs[-1]["form_audit"]["records"])


# ----------------------------------------------------------------------------- the claim of success needs a clean audit
async def test_a_result_page_without_a_clean_audit_is_not_believed(cluster, host):
    """The final page is showing, but the guard never fired (the audit watches a label this page does not have): `Done` is refused."""
    h = DEV[COUPLE]
    facts = FactStore.for_calculator("b", h.params())
    ctx = await host.new_context()
    page = await ctx.new_page()
    await page.goto(cluster.urls["b"] + "/", wait_until="domcontentloaded")
    model = DomOracleComputerModel(faults={"skip": {"household.bedrooms"}})
    guard = Guard(model, run_id="r_fa2", audit=AuditLog(), queue=ApprovalQueue(), denylist=Denylist(), mode="model_driven")
    audit = FormAudit(facts, final_labels=("A label this page does not have",))
    cu = ComputerUse(model, BrowserPageActuator(page), guard, navigator="nav-b", facts=facts, form_audit=audit)
    job = CalculatorJob("b", h.params())

    async def verify():
        from understudy_agent.tiers.observe import observe
        return job.looks_final(await observe(page))

    res = await cu.run(job.goal, verify)
    assert res.claimed_done and res.outcome == "claimed_not_verified" and res.false_claim and res.inputs == "unaudited"
    assert len(cluster.state.calculations) == 1 and last_received(cluster)["bedrooms"] == 1      # the wrong form WAS sent: nothing held it
    assert res.audit["state"] == "unaudited" and res.audit["pending"] == ["household.bedrooms"]


async def test_without_a_page_actuator_the_loop_runs_exactly_as_before():
    facts = FactStore({"household.savings": "savings"}, {"household.savings": lambda: "5000"})
    audit = FormAudit(facts, final_labels=("Calculate",))

    class Script:
        name = "script"
        n = 0

        def computer_step(self, goal, shot, history, **kw):
            self.n += 1
            return Action("screenshot", {}) if self.n == 1 else __import__("understudy_agent.models.port", fromlist=["Done"]).Done("done", True)

    async def verify():
        return True

    guard = Guard(MockProvider(), run_id="r_fa3", audit=AuditLog(), queue=ApprovalQueue(), denylist=Denylist(), mode="model_driven")
    cu = ComputerUse(Script(), SimulatedActuator(), guard, navigator="n", facts=facts, form_audit=audit)
    res = await cu.run("g", verify)
    assert res.outcome == "done" and res.inputs == "n/a" and cu._audit_in_use() is None and audit.records == []


# ----------------------------------------------------------------------------- the completion check, in the product
def _fields(site="b", amount=1316.96):
    return ResultFields(site, f"£{amount:,.2f} per month", amount, "Likely to qualify", True, "T2U-ABC123")


def test_completion_refuses_a_calculator_whose_inputs_were_not_confirmed():
    results = {s: ResultFields(s, "£100.00 per month", 100.0, "Likely to qualify", True, ref) for s, ref in
               (("a", "GOV-AAAAAA"), ("b", "T2U-BBBBBB"), ("c", "ET-CCCCCC"))}
    text = "CN-1234 Draft £100.00 per month 100.00 Likely to qualify GOV-AAAAAA T2U-BBBBBB ET-CCCCCC"
    assert check_completion(text, results, "CN-1234").ok                                           # unchanged without audits
    assert check_completion(text, results, "CN-1234", input_audits={"a": "clean", "b": "clean", "c": "n/a"}).ok
    for bad in ("mismatch", "uncertain", "unaudited"):
        r = check_completion(text, results, "CN-1234", input_audits={"a": "clean", "b": bad, "c": "clean"})
        assert not r.ok and r.missing == (f"calculator b: inputs not verified ({bad})",)


async def test_the_orchestrator_does_not_report_a_well_formed_figure_whose_inputs_were_not_confirmed(tmp_path, monkeypatch):
    """The verifier re-reads the result page and finds the same figure, reference and flag: that alone used to be enough. With the form
    audit's verdict on the navigator's result, a figure whose inputs were not confirmed is not a verified result."""
    from understudy_agent.navigator import NavResult
    from understudy_agent.orchestrator import BenefitsRun, RunOptions

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    run = BenefitsRun("r_fa_verify", DEV[COUPLE], model=MockProvider(), base_urls={s: f"http://127.0.0.1:9/{s}" for s in "abc"},
                      options=RunOptions(denylist=Denylist(), use_tier1=False, allow_tier3=True, start_tier=3, screenshots=False))
    first = _fields()

    class SameFigure:
        async def _read_final(self, page, job, fresh=False):
            return {"amount_text": first.amount_text, "status_text": first.status_text, "ref": first.ref}

    for audit, expected in (("clean", (True, "")), ("n/a", (True, "")), ("mismatch", (False, "inputs not verified (mismatch)")),
                            ("uncertain", (False, "inputs not verified (uncertain)")), ("unaudited", (False, "inputs not verified (unaudited)"))):
        nr = NavResult("nav-b", "b", "done", first, object(), [3], inputs_audit=audit)
        assert await run._verify("b", nr, SameFigure()) == expected, audit
