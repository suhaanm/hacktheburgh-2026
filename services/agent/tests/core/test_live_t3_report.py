"""AGENTIC-3 item 3: what the live harness reports. Offline (no model): input-level correctness per calculator from the sandbox's own record
and from the cliff panel, model failures that exclude the other navigators' cancellations, the form-audit summary, the A/B switch for the
audit, and the gate-version definition. Development households only."""
from __future__ import annotations

import html
import re

import httpx
import pytest

from understudy_agent import live_t3
from understudy_agent.audit import AuditLog
from understudy_agent.live_eval import cliff_panel_matches, inputs_received, inputs_report
from understudy_agent.navigator import CalculatorJob, Navigator, form_audit_mode
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.bundles import CANONICAL_PARAMS
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.specs import SITES
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.heuristic import DomOracleComputerModel
from understudy_agent.tiers.safety import Guard

DEV = generate_households(20, 7001)
COUPLE = DEV[1]
REF = re.compile(r"\b(?:GOV|T2U|ET)-[A-Z0-9]{6}\b")


def calculate_b(cluster, h, **override):
    """Ask site B for an estimate straight from the household's canonical parameters (what a perfectly entered form sends)."""
    spec = SITES["b"]
    p = {**h.params(), **override}
    form = {spec.fields("v1")[c]: p[c] for c in CANONICAL_PARAMS}
    r = httpx.post(cluster.urls["b"] + "/calculate", data=form, timeout=10)
    return REF.search(r.text).group(0)


def cliff_text(cluster, ref):
    body = httpx.get(cluster.urls["b"] + f"/cliff?site=b&ref={ref}", timeout=10).text
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


# ----------------------------------------------------------------------------- input-level correctness
def test_a_form_that_held_the_household_is_exact(cluster):
    ref = calculate_b(cluster, COUPLE)
    ok, differs = inputs_received(COUPLE, cluster.state.calc_households[ref])
    assert ok is True and differs == []
    rep = inputs_report(COUPLE, {"results": {"b": {"ref": ref, "cliff": ""}}}, cluster.state)
    assert rep["exact"] == {"a": None, "b": True, "c": None} and rep["all_exact"] is False       # a and c have no result here


def test_a_drop_down_left_on_its_default_is_named_by_field_not_by_value(cluster):
    ref = calculate_b(cluster, COUPLE, bedrooms="1")                       # the held-out hh_0002 calculator B mechanism
    ok, differs = inputs_received(COUPLE, cluster.state.calc_households[ref])
    assert ok is False and differs == ["bedrooms"]
    assert inputs_received(COUPLE, None) == (None, [])


@pytest.mark.parametrize("override, field", [({"savings": "100"}, "savings"), ({"rent_monthly": "1"}, "rent"), ({"adult1_age": "99"}, "adult1_age"),
                                             ({"children_ages": ""}, "children_ages"), ({"tenure": "own"}, "tenure")])
def test_other_wrong_inputs_are_named(cluster, override, field):
    ref = calculate_b(cluster, COUPLE, **override)
    ok, differs = inputs_received(COUPLE, cluster.state.calc_households[ref])
    assert ok is False and field in differs


def test_the_report_over_a_whole_household_says_all_exact_only_when_every_calculator_is():
    class State:
        calc_households = {"R-a": COUPLE.to_dict(), "R-b": COUPLE.to_dict(), "R-c": {**COUPLE.to_dict(), "bedrooms": 1}}

    res = {"results": {s: {"ref": f"R-{s}", "cliff": ""} for s in "abc"}}
    rep = inputs_report(COUPLE, res, State())
    assert rep["exact"] == {"a": True, "b": True, "c": False} and rep["differs"]["c"] == ["bedrooms"] and rep["all_exact"] is False
    State.calc_households["R-c"] = COUPLE.to_dict()
    assert inputs_report(COUPLE, res, State())["all_exact"] is True


def test_the_cliff_panel_check_says_true_false_or_not_enough_text(cluster):
    ref = calculate_b(cluster, COUPLE)
    text = cliff_text(cluster, ref)
    assert "Cliff edges for this household" in " ".join(text.split())
    assert cliff_panel_matches(COUPLE, text) is True
    assert cliff_panel_matches(COUPLE, text[:400]) is True                 # cut at the length the run stores: a prefix still decides
    other = generate_households(20, 7001)[2]
    assert cliff_panel_matches(other, text) is False                       # the panel of another household
    assert cliff_panel_matches(COUPLE, "Cliff edges for this household") is None and cliff_panel_matches(COUPLE, "") is None
    wrong = cliff_text(cluster, calculate_b(cluster, COUPLE, savings="9000"))
    assert cliff_panel_matches(COUPLE, wrong) is False                     # a panel rendered from different savings


# ----------------------------------------------------------------------------- the rows
def test_a_navigator_cancelled_by_another_navigators_stop_is_not_a_model_failure():
    t3 = [{"navigator": "nav-a", "outcome": "stopped:CancelledError"}, {"navigator": "nav-b", "outcome": "stopped:CancelledError"},
          {"navigator": "nav-c", "outcome": "stopped:GateStop"}, {"navigator": "scribe", "outcome": "done"},
          {"navigator": "nav-a", "outcome": "stalled"}, {"navigator": "nav-b", "outcome": "stopped:FormAuditStop"}]
    assert live_t3.model_failure_rows(t3) == [{"nav": "nav-a", "outcome": "stalled"}, {"nav": "nav-b", "outcome": "stopped:FormAuditStop"}]
    assert live_t3.cancelled_after_stop(t3) == ["nav-a", "nav-b"]


def test_the_audit_summary_counts_read_backs_holds_and_recoveries():
    rec = lambda k, h, m, r="ok": {"step": 1, "k": k, "handle": h, "role": "text", "match": m, "reason": r}  # noqa: E731
    t3 = [{"navigator": "nav-a", "outcome": "done", "inputs": "clean",
           "form_audit": {"blocks": 1, "readbacks": {"yes": 3, "no": 1, "unreadable": 0},
                          "records": [rec("readback", "household.rent", "no", "no_focus"), rec("readback", "household.rent", "yes"),
                                      rec("readback", "household.savings", "yes"), rec("preflight", "household.bedrooms", "no", "not_entered")]}},
          {"navigator": "nav-b", "outcome": "stopped:FormAuditStop", "inputs": "mismatch",
           "form_audit": {"blocks": 4, "readbacks": {"yes": 1, "no": 3, "unreadable": 0},
                          "records": [rec("readback", "household.rent", "no", "wrong_field")] * 3}},
          {"navigator": "scribe", "outcome": "done"}]
    s = live_t3.audit_summary(t3)
    assert s["readbacks"] == {"yes": 4, "no": 4, "unreadable": 0}
    assert s["readback_failures"] == 4 and s["readback_failures_recovered"] == 1
    assert s["blocks"] == 5 and s["navigators_blocked"] == 2 and s["navigators_blocked_then_clean"] == 1
    assert [x["inputs"] for x in s["inputs_by_attempt"]] == ["clean", "mismatch"]


def test_the_gate_version_covers_the_new_files_and_is_stable():
    assert "tiers/form_audit.py" in live_t3.GATE_FILES and "completion.py" in live_t3.GATE_FILES
    assert live_t3.gate_version() == live_t3.gate_version() and len(live_t3.gate_version()) == 12


# ----------------------------------------------------------------------------- the A/B switch
@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


def test_the_audit_arm_comes_from_the_environment_and_defaults_to_full(monkeypatch):
    assert form_audit_mode() == "full"
    for value, expected in (("full", "full"), ("READBACK", "readback"), (" off ", "off"), ("banana", "full"), ("", "full")):
        monkeypatch.setenv("UNDERSTUDY_FORM_AUDIT", value)
        assert form_audit_mode() == expected


async def run_site_b(host, cluster, tmp_path, faults):
    a = AuditLog(tmp_path / "audit.jsonl")
    q = ApprovalQueue(tmp_path / "queue", audit=a)
    model = DomOracleComputerModel(faults=faults)
    guard = Guard(model, run_id="r_ab", audit=a, queue=q, denylist=Denylist(), mode="model_driven")
    nav = Navigator("nav-b", context=await host.new_context(), model=model, guard=guard, base_url=cluster.urls["b"], use_tier1=False,
                    start_tier=3, allow_tier3=True, defer_cliff=True)
    res = await nav.run(CalculatorJob("b", COUPLE.params()))
    ref = res.value.ref if res.value is not None else None
    return res, nav, (inputs_received(COUPLE, cluster.state.calc_households.get(ref))[0] if ref else None)


async def test_the_three_arms_on_the_held_out_mistake(cluster, host, tmp_path, monkeypatch):
    """The same walked-past drop-down in each arm (offline, a scripted double: this shows what the code does, not what any model does)."""
    faults = {"skip": {"household.bedrooms"}}
    monkeypatch.setenv("UNDERSTUDY_FORM_AUDIT", "off")
    res, nav, exact = await run_site_b(host, cluster, tmp_path / "off", faults)
    assert res.state == "done" and res.inputs_audit == "n/a" and exact is False            # the held-out failure: a wrong form goes through
    assert "form_audit" not in nav.t3_runs[-1]
    monkeypatch.setenv("UNDERSTUDY_FORM_AUDIT", "readback")
    res, nav, exact = await run_site_b(host, cluster, tmp_path / "rb", faults)
    assert res.state == "done" and res.inputs_audit == "n/a" and exact is False            # notes and records only: nothing holds the button
    assert nav.t3_runs[-1]["form_audit"]["blocks"] == 0 and nav.t3_runs[-1]["form_audit"]["audits"] == 0
    monkeypatch.setenv("UNDERSTUDY_FORM_AUDIT", "full")
    res, nav, exact = await run_site_b(host, cluster, tmp_path / "full", faults)
    assert res.state == "done" and res.inputs_audit == "clean" and exact is True           # held, fixed, then calculated
    assert nav.t3_runs[-1]["form_audit"]["blocks"] == 1


# ----------------------------------------------------------------------------- the primary measure, sharded rounds, the ledger
def _row(i, ok=True, exact=True, **extra):
    return {"run_id": f"r_x_hh_{i:04d}", "index": i, "household": f"hh_{i:04d}", "code_check_ok": ok, "all_inputs_exact": exact, "false_claim": False,
            "harness_accepted_wrong_inputs": False, "paused": False, "gate_stops": [], "gate_stops_unexpected": 0, "exfil_hits": 0, "submissions": 0,
            "goal_checks": {"checks": 10, "retried": 1, "recovered": 1, "failed": 0, "by_class": {"timeout": 1}},
            "form_audit": {"readback_failures": 1, "readback_failures_recovered": 1, "blocks": 0, "navigators_blocked": 0, "navigators_blocked_then_clean": 0},
            **extra}


def _summarise(rows, condition="clean"):
    return live_t3.summarise(rows, label="x", heldout=True, seed=1, condition=condition, dropped=[], models={}, cu_provider="openai", by_provider=None)


def test_the_primary_measure_needs_the_code_check_and_correct_inputs_on_every_calculator():
    rows = [_row(i) for i in range(20)]
    d = _summarise(rows)
    assert d["primary"]["k"] == 20 and d["primary"]["n"] == 20 and d["primary"]["wilson95"][0] == pytest.approx(0.8389, abs=1e-3)
    assert d["primary"]["bar_met"] is True and d["primary"]["rate"] == 1.0
    rows[3] = _row(3, ok=True, exact=False)                                  # a figure that matched by luck on wrong inputs is not a pass
    rows[4] = _row(4, ok=False, exact=True)
    d = _summarise(rows)
    assert d["primary"]["k"] == 18 and d["primary"]["bar_met"] is False and d["n_ok"] == 19 and d["n_all_inputs_exact"] == 19
    assert _summarise([_row(i) for i in range(19)] + [_row(19, ok=False)])["primary"]["wilson95"][0] == pytest.approx(0.7639, abs=1e-3)   # 19 of 20
    assert _summarise(rows, condition="injected")["primary"] is None


def test_parse_shard():
    assert live_t3.parse_shard("0/1") == (0, 1) and live_t3.parse_shard(" 2/4 ") == (2, 4)
    for bad in ("1/1", "a/b", "3", "-1/2", "0/0", "2/2"):
        with pytest.raises(SystemExit):
            live_t3.parse_shard(bad)


def test_merging_workers_gives_the_round_and_refuses_what_is_not_one_round():
    def part(label, idxs, **kw):
        d = _summarise([_row(i) for i in idxs])
        d.update(label=label, gate_version="abc123abc123", **kw)
        return d

    a, b = part("w0", [0, 2, 4]), part("w1", [1, 3])
    m = live_t3.merge_parts([a, b], "whole")
    assert m["n"] == 5 and [r["index"] for r in m["rows"]] == [0, 1, 2, 3, 4] and m["merged_from"] == ["w0", "w1"]
    assert m["primary"]["k"] == 5 and m["gate_version"] == "abc123abc123"
    assert m["goal_checks"]["checks"] == 50 and m["goal_check_failures_by_class"] == {"timeout": 5}
    with pytest.raises(ValueError, match="seed"):
        live_t3.merge_parts([a, part("w2", [5], seed=2)], "x")
    with pytest.raises(ValueError, match="gate_version"):
        live_t3.merge_parts([a, {**part("w2", [5]), "gate_version": "other"}], "x")
    with pytest.raises(ValueError, match="overlap"):
        live_t3.merge_parts([a, part("w3", [2])], "x")


def test_workers_can_append_to_the_spend_ledger_at_the_same_time(tmp_path, monkeypatch):
    import json
    import threading

    monkeypatch.setattr(live_t3, "RESULTS", tmp_path)
    monkeypatch.setattr(live_t3, "LEDGER", tmp_path / "spend_ledger.json")
    monkeypatch.setattr(live_t3, "gate_version", lambda: "g")
    errors: list[BaseException] = []

    def work(k):
        try:
            for j in range(6):
                live_t3.record(f"w{k}", "dev_round", 10, 1, 0.01, household=f"hh_{j}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(k,)) for k in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    doc = json.loads((tmp_path / "spend_ledger.json").read_text())
    assert len(doc["entries"]) == 36 and doc["spent_placeholder_usd"] == pytest.approx(0.36)         # no entry lost to a race
    assert not list(tmp_path.glob("*.tmp"))
