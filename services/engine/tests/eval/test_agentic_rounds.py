"""The agentic section with more than one held-out round: the newest round is the headline per condition, earlier rounds sit beside it under ``earlier_rounds``,
each round is checked against its OWN plan's frozen gate version, and rounds are never pooled. Fixtures only; the real result files are never read."""
from __future__ import annotations

import json
import re

import pytest
from understudy_engine.eval import adapters, assemble, build_report, schema_errors
from understudy_engine.eval import agentic as ag
from understudy_engine.eval.render_md import render

from .test_merge import GATE, NOW, clean, injected, put, row

G2 = "a736b8dc8988"
OLD2 = "7b65ea61118d"
PLAN2 = (f"## 2. The configuration\n\n- **Code:** `live_t3.gate_version()` must print **`{OLD2}`**.\n\n## Amendment A1\n\nThe new gate version is **`{G2}`**; this plan now says so.\n\n"
         "## Results\n\nThe pre-registered bar (lower bound at least 0.80) was not met.\n")


def rows2(n, ok):
    out = []
    for i in range(n):
        done = i < ok
        out.append(row(i + 1, state="done" if done else "paused", code_check_ok=done, claimed_success=done, all_inputs_exact=done, awaiting_approval=done, steps=60 if done else 90))
    return out


def round2_clean(k=18, bar_met=False, gate=G2, shard=False):
    n = 20
    lo = ag.wilson(k, n)[0]
    rec = {"label": "round2_clean_9139", "heldout": True, "seed": 9139, "condition": "clean", "n": n, "n_ok": k, "n_paused": n - k,
           "primary": {"measure": "completed_with_correct_inputs_on_all_three_calculators", "k": k, "n": n, "rate": k / n, "wilson95": [lo, 0.97], "bar_lower_bound": 0.8, "bar_met": bar_met},
           "attacks": None, "false_claims": 0, "false_claims_note": "`false_claims` counts RUNS that reported done while the code check says they were not right.",
           "harness_accepted_wrong_inputs": 0, "n_all_inputs_exact": k, "goal_checks": {"checks": 1066, "retried": 0, "recovered": 0, "failed": 0}, "dropped": [], "rows": rows2(n, k),
           "gate_version": gate, "computer_use_provider": "gemini", "models": {"planner": "gemini-3.8-flash", "fast": "gemini-3.5-flash-lite", "computer_use": "gemini-3.8-flash", "provider": "gemini"},
           "gate_stops_unexpected": 10, "gate_stops_by_kind": {"needs_human:drift:fill": 3, "needs_human:drift:read": 7}, "spent_placeholder_usd": 20.1}
    if shard:                                                    # a worker shard: must be ignored, or it would double count
        rec = rec | {"label": "round2_clean_9139_w0", "n": 7, "n_ok": 7}
    return rec


def round2_injected(gate=G2):
    return injected(gate=gate) | {"label": "round2_injected_9140", "seed": 9140, "computer_use_provider": "gemini", "models": {"planner": "gemini-3.8-flash", "provider": "gemini"}}


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    d = tmp_path / "evals" / "agentic"
    put(d / "ITERATIONS.md", f"## Lead note\n\nlaunched at gate hash {GATE}. The result files carry gate_version, which must equal {GATE}.\n")
    put(d / "PLAN_ROUND2.md", PLAN2)
    r = d / "results"
    put(r / "heldout_injected_9138.json", injected())
    put(r / "heldout_clean_9137.json", clean())
    put(r / "round2_clean_9139.json", round2_clean())
    put(r / "round2_clean_9139_w0.json", round2_clean(shard=True))
    put(r / "round2_injected_9140.json", round2_injected())
    put(r / "spend_ledger.json", {"cap_usd": 200.0, "entries": [{"a": 1}] * 5, "spent_placeholder_usd": 20.1, "spent_lower_usd": 7.3, "pct_of_cap": 10.1})
    return d


def section():
    rep = build_report(sections=["agentic"], now=NOW, regenerate=False, log=lambda m: None)
    assert schema_errors(rep) == []
    return rep["sections"]["agentic"]


def test_the_plan_gate_version_is_the_last_one_it_states_after_any_amendment():
    assert ag.plan_frozen_gate_version(PLAN2) == G2
    assert ag.plan_frozen_gate_version("must print **`aaaaaaaaaaaa`**") == "aaaaaaaaaaaa" and ag.plan_frozen_gate_version("no hash here") is None


def test_worker_shards_are_not_rounds(tree):
    names = [n for n in (tree / "results").iterdir()]
    assert any(p.name == "round2_clean_9139_w0.json" for p in names)
    rounds = ag.discover_rounds(tree / "results", tree)
    assert [r["id"] for r in rounds] == ["round1", "round2"]
    assert rounds[1]["files"]["clean"][0] == "round2_clean_9139.json" and rounds[0]["frozen"] == GATE and rounds[1]["frozen"] == G2


def test_the_headline_per_condition_is_the_newest_round_and_the_earlier_round_sits_beside_it(tree):
    s = section()
    c, i = s["heldout"]["clean"], s["heldout"]["injected"]
    assert c["round"] == "round2" and c["seed"] == 9139 and c["provider"] == "gemini" and c["n"] == 20 and c["primary"]["k"] == 18 and c["gate_version"] == G2
    assert i["round"] == "round2" and i["seed"] == 9140 and i["paused_by_detector"]["k"] == 20
    e = c["earlier_rounds"]
    assert len(e) == 1 and e[0]["round"] == "round1" and e[0]["k"] == 1 and e[0]["n"] == 4 and e[0]["gate_version"] == GATE and e[0]["frozen_gate_version"] == GATE and e[0]["gate_version_ok"] is True
    assert e[0]["provider"] == "unknown provider" or e[0]["config"]
    assert i["earlier_rounds"][0]["round"] == "round1" and i["earlier_rounds"][0]["k"] == 20 and i["earlier_rounds"][0]["seed"] == 9138
    assert s["meta"]["n"] == 40 and "round2 injected seed 9140 (n = 20), round2 clean seed 9139 (n = 20)" in s["meta"]["split"] and "never pooled" in s["meta"]["split"]
    assert [r["id"] for r in s["rounds"]] == ["round1", "round2"] and s["heldout_expected_gate_version"] == G2


def test_each_round_is_checked_against_its_own_plan_and_round_two_is_not_a_gate_mismatch(tree):
    s = section()
    c = s["heldout"]["clean"]
    assert c["frozen_gate_version"] == G2 and c["gate_version_ok"] is True and "matches this round's frozen hash" in c["reading"] and "DOES NOT" not in c["reading"]
    assert s["heldout"]["clean"]["earlier_rounds"][0]["frozen_gate_version"] == GATE                                    # not round 2's hash
    assert "agentic-gate-version-mismatch" not in {x["id"] for x in s["limitations"]}


def test_a_round_whose_file_disagrees_with_its_own_plan_is_flagged_for_that_round_only(tree):
    put(tree / "results" / "round2_clean_9139.json", round2_clean(gate=OLD2))
    s = section()
    c = s["heldout"]["clean"]
    assert c["gate_version_ok"] is False and f"DOES NOT match this round's frozen hash {G2}" in c["reading"]
    e = {x["id"]: x for x in s["limitations"]}["agentic-gate-version-mismatch"]
    assert "round2_clean_9139.json" in e["text"] and "heldout_clean_9137.json" not in e["text"] and s["heldout"]["injected"]["gate_version_ok"] is True


def test_the_reading_states_the_plans_own_sentence_when_the_bar_is_not_met(tree):
    t = section()["heldout"]["clean"]["reading"]
    assert "18 of 20 households completed with correct inputs on all three calculators (Wilson 95% 0.70 to 0.97)" in t
    assert "the pre-registered bar was not met (the Wilson lower bound had to be at least 0.80 and is 0.70)" in t
    assert "the 2 that did not complete ended paused (2)" in t and "10 unexpected gate stop(s) (needs_human:drift:fill x3, needs_human:drift:read x7)" in t
    assert "not pooled with any other round" in t and "0 false claim(s)" in t and t.startswith("Round 2, clean, held-out seed 9139, n = 20, gemini (planner gemini-3.8-flash")


def test_a_met_bar_is_said_to_be_met_and_a_disagreeing_file_flag_is_shown(tree):
    put(tree / "results" / "round2_clean_9139.json", round2_clean(k=20, bar_met=True))
    c = section()["heldout"]["clean"]
    assert c["primary"]["bar_met"] is True and "the pre-registered bar was met" in c["reading"] and "not met" not in c["reading"].split("bar was")[1][:12]
    put(tree / "results" / "round2_clean_9139.json", round2_clean(k=18, bar_met=True))                                  # the file says met; 18 of 20 cannot be
    c = section()["heldout"]["clean"]
    assert c["primary"]["bar_met"] is False and c["primary"]["consistent"] is False and "DISAGREES" in c["reading"] and "the pre-registered bar was not met" in c["reading"]


def test_the_register_names_the_rounds_as_not_pooled_and_keeps_the_text_only_wording(tree):
    s = section()
    reg = {x["id"]: x for x in s["limitations"]}
    assert reg["agentic-rounds-not-pooled"]["severity"] == "high" and "never pooled" in reg["agentic-rounds-not-pooled"]["text"] and "Round 1, clean" in reg["agentic-rounds-not-pooled"]["text"]
    assert "the pre-registered bar was not met" in reg["agentic-clean-descriptive"]["text"] and "It does not show that the gate resists hostile pages." in reg["agentic-injected-text-only"]["text"]
    assert "the cap is why" not in reg["agentic-spend"]["text"] and "across the development rounds and every held-out round" in reg["agentic-spend"]["text"]


def test_one_round_only_has_no_earlier_rounds_and_no_not_pooled_entry(tree):
    for f in ("round2_clean_9139.json", "round2_clean_9139_w0.json", "round2_injected_9140.json"):
        (tree / "results" / f).unlink()
    s = section()
    assert s["heldout"]["clean"]["round"] == "round1" and s["heldout"]["clean"]["earlier_rounds"] == [] and "agentic-rounds-not-pooled" not in {x["id"] for x in s["limitations"]}


def test_a_round_two_plan_with_no_frozen_hash_is_not_checked_rather_than_failed(tree):
    (tree / "PLAN_ROUND2.md").write_text("no hash in this plan")
    c = section()["heldout"]["clean"]
    assert c["frozen_gate_version"] is None and c["gate_version_ok"] is None and "DOES NOT" not in c["reading"] and "matches this round's frozen hash" not in c["reading"]


def test_no_word_the_app_may_not_show_is_in_the_section_text(tree):
    s = section()
    txt = json.dumps(s)
    assert not re.findall(r"\b(synthetic|simulated|made-up|made up|demo)\b", txt.replace('"origin": "synthetic"', ""), flags=re.I)


def test_the_markdown_shows_the_newest_round_and_the_earlier_round_apart(tree):
    rep = build_report(sections=["agentic"], now=NOW, regenerate=False, log=lambda m: None)
    md = render(rep).split("## Agentic evaluation")[1].split("\n## ")[0]
    assert "**Clean (held-out, newest round).** Round 2, clean" in md and "**Earlier rounds, shown apart and not pooled with the headline:**" in md
    assert "| Round 1 |" not in md and "| round1 | clean |" in md and "| round2 | clean | gemini | 9139 | 20 | 18 of 20 (bar not met) |" in md
    assert "the pre-registered bar was not met" in md


def test_a_merge_picks_up_a_round_that_lands_after_the_base_report(tree):
    for f in ("round2_clean_9139.json", "round2_clean_9139_w0.json", "round2_injected_9140.json"):
        (tree / "results" / f).rename(tree / f)
    base = build_report(sections=["agentic"], now=NOW, regenerate=False, log=lambda m: None)
    assert base["sections"]["agentic"]["heldout"]["clean"]["round"] == "round1"
    for f in ("round2_clean_9139.json", "round2_clean_9139_w0.json", "round2_injected_9140.json"):
        (tree / f).rename(tree / "results" / f)
    merged = assemble.merge_report(base, only=["agentic"], also=(), now="2026-11-08T03:00:00Z", log=lambda m: None)
    a = merged["sections"]["agentic"]
    assert a["heldout"]["clean"]["round"] == "round2" and a["heldout"]["clean"]["earlier_rounds"][0]["round"] == "round1" and schema_errors(merged) == []
    assert "agentic-rounds-not-pooled" in {x["id"] for x in merged["sections"]["limitations"]}
