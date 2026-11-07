"""The three findings the Evidence page leads with (REALISM matrix, simulated study at the floor, ML v2 M5 transfer), the adapters that feed them, and the
other recorded results wired in this round (evidence live copy, cue held-out, attention, insights, mlv2 recorded files). Numbers come from fixtures here,
never from the real files."""
from __future__ import annotations

import json
import os
import sys
import types

import pytest
from understudy_engine.eval import adapters, build_report, schema_errors
from understudy_engine.eval import limitations as lim
from understudy_engine.eval.findings import SIM, build_findings, m5_text
from understudy_engine.eval.render_md import render

NOW = "2026-11-07T15:00:00Z"
META = {"origin": "synthetic", "n": 7, "n_unit": "items", "split": "x", "interval_level": 0.95, "note": "n", "generated_at": "x"}


def est(v, lo=None, hi=None):
    return {"est": v, "ci": [v - 0.005 if lo is None else lo, v + 0.005 if hi is None else hi]}


def cell(h1, fa, fa_over, no_skill=False, n_people=120):
    return {"n_people": n_people, "metrics": {"h1": est(h1), "fa_per_h": est(fa), "detection": est(0.4)}, "fa_over_budget": fa_over, "no_skill": no_skill,
            "delta_vs_diagonal": {"h1": {"verdict": "worse"}}}


def hazard_block():
    fams = ("markov", "latent_skill", "process_trace")
    cells = {"v1->v1": cell(0.071, 0.5, False, n_people=4)}
    for i, f in enumerate(fams):
        cells[f"{f}->{f}"] = cell((0.008, 0.012, 0.015)[i], 1.2 if i == 0 else 0.6, i == 0)
        cells[f"v1->{f}"] = cell((-0.43, -0.48, -0.53)[i], 2.0, True, no_skill=True)
        cells[f"{f}->v1"] = cell(0.03, 0.4, False)
        for g in fams:
            if g != f:
                cells[f"{f}->{g}"] = cell(0.002, 1.5 if (f, g) in (("markov", "latent_skill"), ("markov", "process_trace"), ("latent_skill", "markov")) else 0.5,
                                          (f, g) in (("markov", "latent_skill"), ("markov", "process_trace"), ("latent_skill", "markov")), no_skill=(f, g) == ("latent_skill", "markov"))
    return {"origin": "synthetic", "block": "hazard", "role": "benefits-processor", "partial": False, "result": {"cells": cells, "alarm_rules": {}}}


def put(root, rel, d):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))


# ------------------------------------------------------------------------------------------------- realism blocks
def test_hazard_block_summary_classifies_cells_and_counts_from_the_flags(tmp_path):
    put(tmp_path, "eval/realism_blocks/hazard_benefits-processor.json", hazard_block())
    put(tmp_path, "eval/realism_blocks/fast_hazard_benefits-processor.json", {"result": {"cells": {}}})           # the track's smoke run: skipped
    blocks = adapters._realism_blocks(tmp_path)
    b = blocks["hazard"]["benefits-processor"]
    assert list(blocks) == ["hazard"] and list(blocks["hazard"]) == ["benefits-processor"]
    assert b["v1_own"]["h1"]["est"] == 0.071 and set(b["v2_diagonals"]) == {"markov", "latent_skill", "process_trace"}
    assert [c["est"] for c in b["v1_trained_on_v2"].values()] == [-0.43, -0.48, -0.53]
    assert b["false_alarm_over_budget"] == {"v2_off_diagonal": {"n": 6, "over": 3}, "v2_diagonal": {"n": 3, "over": 1}, "v1_to_v2": {"n": 3, "over": 3},
                                            "v2_to_v1": {"n": 3, "over": 0}, "budget_per_hour": 1.0}
    assert b["no_skill_cells"] == ["latent_skill->markov", "v1->latent_skill", "v1->markov", "v1->process_trace"]
    assert b["n_people_v1_cell"] == 4 and b["n_people_v2_cell"] == 120


def genome_cell(p, r, fa, n=91):
    return {"n_people": n, "metrics": {"precision": est(p), "recall": est(r), "gap_s": est(500.0), "false_attr_s": est(fa), "recall:search_loop": est(1.0)},
            "delta_vs_diagonal": {"precision": {"verdict": "degrades"}, "recall": {"verdict": "inconclusive"}}}


def genome_block():
    fams = ("markov", "latent_skill", "process_trace")
    cells = {"v1->v1": genome_cell(0.92, 0.95, 1.1, n=16)}
    for i, f in enumerate(fams):
        cells[f"{f}->{f}"] = genome_cell((0.67, 0.48, 0.71)[i], (0.62, 0.68, 0.49)[i], (55.7, 58.6, 45.7)[i], n=(91, 92, 87)[i])
        cells[f"v1->{f}"] = genome_cell((0.47, 0.33, 0.56)[i], (0.95, 0.87, 0.90)[i], 70.0, n=(91, 92, 87)[i])
        cells[f"{f}->v1"] = genome_cell((0.79, 1.0, 1.0)[i], (0.10, 0.42, 0.33)[i], 1.0, n=16)
    return {"origin": "synthetic", "block": "genome", "role": "benefits-processor", "partial": False, "result": {"cells": cells, "placebo": {}, "thresholds_s": {}}}


def rcell(p, r, g, n=120):
    return {"n_people": n, "metrics": {"r1_precision": est(p), "r2_recall": est(r), "r3_proposal_precision": est(g), "clusters_per_person": est(4.0), "proposals_per_person": est(0.3)}}


def routines_block(thin=False):
    cells = {}
    shipped = {"v1": (0.22, 1.0, 1.0), "markov": (0.97, 0.45, 1.0), "latent_skill": (0.93, 0.66, 1.0), "process_trace": (0.44, 0.92, 0.74)}
    fams = ("markov", "latent_skill", "process_trace") if thin else tuple(shipped)
    for fit in fams:
        for test in fams:
            p, r, g = shipped[test]
            cells[f"shipped:{fit}->{test}"] = rcell(p, r, g, n=4 if test == "v1" else 120)
            cells[f"fitted:{fit}->{test}"] = rcell(0.9 if fit == test else 0.04 if test == "v1" else 0.6, 1.0 if fit == test else 0.16, 1.0, n=4 if test == "v1" else 120)
    return {"origin": "synthetic", "block": "routines", "partial": False, "result": {"cells": cells, "tuned_threshold": {"markov:0": 0.5}, "f1_by_threshold": {}}}


def test_genome_block_summary_keeps_the_four_metrics_the_verdicts_and_classifies_cells(tmp_path):
    assert adapters._realism_blocks(tmp_path) == {}
    put(tmp_path, "eval/realism_blocks/genome_benefits-processor.json", genome_block())
    g = adapters._realism_blocks(tmp_path)["genome"]["benefits-processor"]
    assert g["v1_own"]["precision"]["est"] == 0.92 and g["n_people_v1_cell"] == 16 and g["partial"] is False
    assert set(g["v2_diagonals"]) == set(g["v1_trained_on_v2"]) == set(g["v2_trained_on_v1"]) == {"markov", "latent_skill", "process_trace"}
    assert g["v2_diagonals"]["latent_skill"]["recall"]["est"] == 0.68 and g["v2_diagonals"]["latent_skill"]["n_people"] == 92
    assert set(g["cells"]["v1->v1"]) == {"precision", "recall", "gap_s", "false_attr_s", "n_people", "verdicts"} and g["cells"]["markov->v1"]["verdicts"] == {"precision": "degrades", "recall": "inconclusive"}


def test_routines_block_summary_splits_fitted_from_shipped_and_notes_that_shipped_cannot_depend_on_the_fit_family(tmp_path):
    put(tmp_path, "eval/realism_blocks/routines_benefits-processor.json", routines_block())
    r = adapters._realism_blocks(tmp_path)["routines"]["benefits-processor"]
    assert r["shipped_identical_across_fit_family"] is True and set(r["shipped_by_test_family"]) == {"v1", "markov", "latent_skill", "process_trace"}
    assert r["shipped_by_test_family"]["v1"]["r1_precision"]["est"] == 0.22 and r["shipped_by_test_family"]["process_trace"]["r3_proposal_precision"]["est"] == 0.74
    assert r["fitted"]["markov->v1"]["r1_precision"]["est"] == 0.04 and r["tuned_threshold"] == {"markov:0": 0.5}
    broken = routines_block()
    broken["result"]["cells"]["shipped:markov->latent_skill"] = rcell(0.5, 0.5, 0.5)                 # a shipped cell that depends on the fit family is flagged
    put(tmp_path, "eval/realism_blocks/routines_benefits-processor.json", broken)
    assert adapters._realism_blocks(tmp_path)["routines"]["benefits-processor"]["shipped_identical_across_fit_family"] is False


def sections_with(blocks=None, hazard=True):
    s = {"realism": {"meta": META, "blocks": {"hazard": {"benefits-processor": blocks}}} if blocks else {"meta": META}}
    if hazard:
        s["hazard"] = {"meta": META, "model": {"log_loss": 0.436}, "baselines": {"time_since_progress": {"log_loss": 0.509}, "base_rate": {"log_loss": 0.51}}}
    return s


def test_realism_finding_states_the_numbers_and_the_headline_sentence(tmp_path):
    put(tmp_path, "eval/realism_blocks/hazard_benefits-processor.json", hazard_block())
    f = build_findings(sections_with(adapters._realism_blocks(tmp_path)["hazard"]["benefits-processor"]))[0]
    t = f["text"]
    assert f["status"] == "ok" and f["origin"] == "synthetic" and f["id"] == "realism-generator-dependence" and f["severity"] == "high"
    assert "0.071 nats per bin on its own generator" in t and "0.008 to 0.015 on three harder generator families" in t
    assert "0.43 to 0.53 nats worse than the baseline" in t
    assert "3 of 6 v2-to-v2 off-diagonal cells, 1 of 3 v2 diagonals, 3 of 3 v1-to-v2 cells and 0 of 3 v2-to-v1 cells" in t
    assert "latent_skill->markov" in t and "v1->markov" in t
    assert "log loss 0.436 against 0.509" in t and "largely reflects the generator's emission table; it stays labelled synthetic" in t


def realism_section(tmp_path, thin=True):
    put(tmp_path, "eval/realism_blocks/genome_benefits-processor.json", genome_block())
    put(tmp_path, "eval/realism_blocks/routines_benefits-processor.json", routines_block())
    if thin:
        for role in ("data-analyst", "programmer"):
            put(tmp_path, f"eval/realism_blocks/routines_{role}.json", routines_block(thin=True))
    return {"realism": {"meta": META, "blocks": adapters._realism_blocks(tmp_path)}}


def test_genome_finding_states_the_ranges_read_from_the_block(tmp_path):
    f = {x["id"]: x for x in build_findings(realism_section(tmp_path))}["realism-genome-generator-dependence"]
    t = f["text"]
    assert f["status"] == "ok" and f["origin"] == "synthetic" and f["severity"] == "high"
    assert "precision 92% and recall 95% on the v1 generator fall to 48 to 71% precision and 49 to 68% recall on three harder generator families" in t
    assert "Thresholds fitted on v1 keep recall (87 to 95%) but lose precision (33 to 56%)" in t
    assert "high precision (79 to 100%) but recall of only 10 to 42%" in t
    assert "46 to 59 s on the v2 families against 1.1 s on v1" in t and "16 personas on the v1 generator, 87 to 92 synthetic people per v2 cell" in t
    assert f["numbers"]["v2_diagonals"]["markov"]["recall"]["est"] == 0.62


def test_routines_finding_states_the_raw_precision_the_gate_and_the_thin_roles(tmp_path):
    f = {x["id"]: x for x in build_findings(realism_section(tmp_path))}["realism-routines-generator-dependence"]
    t = f["text"]
    assert f["status"] == "ok"
    assert "raw cluster precision is 22% on the v1 generator (the published figure) and 44 to 97% on the three v2 families, with recall 45 to 92% (100% on v1)" in t
    assert "Proposal precision after the gate is 74 to 100% (100% on v1)" in t and "4 personas on the v1 generator, 120 synthetic people per v2 cell" in t
    assert "raw precision ranges from 4 to 60%" in t and "which do not depend on the fit family" in t
    assert "data-analyst, programmer" in t and "raw precision 44 to 97%" in t and "so the figures differ by role as well as by family" in t
    assert set(f["numbers"]["thin_roles"]) == {"data-analyst", "programmer"}


def test_routines_finding_without_thin_roles_says_nothing_about_them(tmp_path):
    f = {x["id"]: x for x in build_findings(realism_section(tmp_path, thin=False))}["realism-routines-generator-dependence"]
    assert "thin roles" not in f["text"] and f["numbers"]["thin_roles"] == {}


def test_findings_are_pending_with_a_reason_not_absent_when_their_source_has_no_numbers():
    fs = build_findings({"realism": {"status": "pending", "reason": "x", "meta": META}, "study_sim": {"status": "not_run", "reason": "no run", "meta": META}})
    assert [f["id"] for f in fs] == ["realism-generator-dependence", "study-sim-floor-null", "mlv2-m5-transfer-failure", "realism-genome-generator-dependence",
                                     "realism-routines-generator-dependence"]
    assert all(f["status"] == "pending" and f["text"] and f["reason"] for f in fs)
    assert SIM in fs[1]["text"].lower() and SIM in fs[2]["text"].lower()
    assert "genome block" in fs[3]["text"] and "routines block" in fs[4]["text"]


# ------------------------------------------------------------------------------------------------------ simulated study
def sim_section():
    return {"meta": dict(META, n=24), "n": 16, "n_aa": 8, "owner_status": "complete",
            "headline": {"mean_difference": 0.0938, "ci95": [-0.0512, 0.2387], "sign_flip_p_two_sided": 0.5},
            "floor": {"coached": {"post_tests": 32, "score_zero": 30, "hit_the_action_cap": 18}, "aa": {"post_tests": 16, "score_zero": 16}},
            "nudges": {"shown": 12}, "pipeline_checks": {"study_mode_enforcement": {"non_silent_polls_by_mode": {"train": 12, "post_test": 0, "off": 0}}},
            "limitations": [{"id": "sim-power", "severity": "high", "text": f"{SIM[0].upper() + SIM[1:]}: With 16 coached-arm participants the analysis has about 6% false positives and 12%, 29% and 76% power."}],
            "run5_pilot": {"pass": False, "post_tests": 6, "post_tests_above_zero": 0, "needed_above_zero": 3, "reasons_for_stopping": ["only 0 of 6 pilot post-tests scored above zero (needed 3)"]}}


def test_study_sim_finding_reads_the_floor_the_null_the_power_note_the_pilot_and_enforcement():
    f = build_findings({"study_sim": sim_section()})[1]
    t = f["text"]
    assert f["status"] == "ok" and f["badge"] == SIM and t.startswith(SIM[0].upper() + SIM[1:])
    assert "n = 24: 16 coached-arm and 8 A/A" in t and "30 of 32 coached post-tests scored 0" in t and "16 of 16 A/A post-tests" in t and "18 of 32" in t
    assert "+0.094 [-0.051, +0.239], sign-flip p = 0.5" in t and "a null shows nothing" in t
    assert "about 6% false positives and 12%, 29% and 76% power" in t and t.lower().count(SIM) == 1
    assert "Run 5 pilot: 0 of 6 post-tests scored above zero (needed 3); stopped, so there is no run 5 proper" in t
    assert "Study-mode enforcement held: 0 non-silent coach polls in post-test blocks and 0 in blocks with the coach off" in t and "12 nudges were shown, all in train blocks" in t


def test_a_violated_study_mode_is_said_plainly():
    s = sim_section()
    s["pipeline_checks"]["study_mode_enforcement"]["non_silent_polls_by_mode"]["post_test"] = 2
    assert "DID NOT HOLD" in build_findings({"study_sim": s})[1]["text"]


def test_study_sim_adapter_keeps_the_owner_status_adds_the_total_n_and_reads_the_pilot(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    d = tmp_path / "evals" / "study_sim"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("def study_sim_section():\n    return {'status': 'complete', 'n': 16, 'n_aa': 8, 'headline': {'mean_difference': 0.1}, 'meta': {'origin': 'simulated_llm', 'n_unit': 'silicon participants', "
                                   "'split': 's', 'interval_level': 0.95, 'note': None, 'generated_at': None}, 'limitations': []}\n")
    put(tmp_path, "evals/study_sim/results_run5/pilot/PILOT_DECISION.json", {"pass": False, "post_tests": 6, "post_tests_above_zero": 0, "needed_above_zero": 3,
                                                                         "reasons_for_stopping": ["r"], "pilot_scores": [0.0] * 6})
    rep = build_report(sections=["study_sim"], now=NOW, regenerate=False, log=lambda m: None)
    s = rep["sections"]["study_sim"]
    assert "status" not in s and s["owner_status"] == "complete" and s["meta"]["n"] == 24 and s["meta"]["origin"] == "synthetic" and s["meta"]["origin_detail"] == "simulated_llm"
    assert s["run5_pilot"]["post_tests_above_zero"] == 0 and s["run5_pilot"]["source"].endswith("PILOT_DECISION.json")
    assert schema_errors(rep) == [] and "n = 16 coached-arm plus 8 A/A" in s["meta"]["split"]


# ------------------------------------------------------------------------------------------------------------ M5
def transfer():
    est_ = lambda v: {"value": v, "interval": [v - 0.1, v + 0.1]}  # noqa: E731
    return {"n": 24, "n_bins": 419, "label_rate": 0.647, "train_label_rate": 0.216,
            "models": {"v1": {"log_loss": est_(1.43), "ece": est_(0.51)}, "v2": {"log_loss": est_(1.46), "ece": est_(0.53)}, "base_rate": {"log_loss": est_(1.08)}},
            "paired_log_loss": {"v2_minus_v1": {"delta": 0.03, "interval": [-0.03, 0.085]}}}


def test_m5_text_and_finding_come_from_the_recorded_transfer_result():
    t = m5_text(transfer())
    assert SIM in t.lower() and "neither v1 nor v2 transfers" in t and "1.43 [1.33 to 1.53] for v1 and 1.46 [1.36 to 1.56] for v2 against 1.08" in t
    assert "65% of the test bins are 'stuck' against 22% in training" in t and "v2 minus v1 log loss is +0.030" in t and "no improvement" in t
    f = build_findings({"mlv2": {"meta": META, "transfer_simulated_participants": transfer()}})[2]
    assert f["status"] == "ok" and f["numbers"]["label_rate"] == 0.647 and f["numbers"]["log_loss"]["v1"]["value"] == 1.43


def test_the_register_carries_all_five_findings_as_high_entries_with_their_origin_wording(tmp_path):
    realism = realism_section(tmp_path)["realism"]
    secs = {**sections_with({"v1_own": {"h1": {"est": 0.071}}, "v2_diagonals": {"a": {"est": 0.01}}, "v1_trained_on_v2": {"a": {"est": -0.4}}, "no_skill_cells": [],
                             "false_alarm_over_budget": {k: {"n": 3, "over": 1} for k in ("v2_off_diagonal", "v2_diagonal", "v1_to_v2", "v2_to_v1")},
                             "n_people_v1_cell": 4, "n_people_v2_cell": 120}),
            "study_sim": sim_section(), "mlv2": {"meta": META, "transfer_simulated_participants": transfer()}}
    secs["realism"]["blocks"].update(realism["blocks"])                                    # the hazard block above plus the genome and routines blocks
    reg = {e["id"]: e for e in lim.assemble(secs)}
    for i in ("eval-realism-generator-dependence", "eval-study-sim-floor-null", "eval-mlv2-m5-transfer-failure", "eval-realism-genome-generator-dependence",
              "eval-realism-routines-generator-dependence"):
        assert reg[i]["severity"] == "high" and reg[i]["text"]
    assert "46 to 59 s on the v2 families" in reg["eval-realism-genome-generator-dependence"]["text"] and "44 to 97%" in reg["eval-realism-routines-generator-dependence"]["text"]
    assert reg["eval-realism-genome-generator-dependence"]["source"] == "engine-eval:realism"
    assert SIM in reg["eval-study-sim-floor-null"]["text"].lower() and SIM in reg["eval-mlv2-m5-transfer-failure"]["text"].lower()


def test_findings_are_in_the_report_the_markdown_the_facts_and_on_their_sections(tmp_path, monkeypatch):
    import understudy_engine.mlv2.evaluate as mev

    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    monkeypatch.setattr(mev, "evaluate_mlv2", lambda **kw: {"meta": dict(META)})
    monkeypatch.setattr(mev, "_load", lambda name: transfer() if name == "transfer_sim.json" else None)
    rep = build_report(sections=["mlv2"], now=NOW, regenerate=False, log=lambda m: None)
    f = {x["id"]: x for x in rep["findings"]}
    assert f["mlv2-m5-transfer-failure"]["status"] == "ok" and f["realism-generator-dependence"]["status"] == "pending" and f["study-sim-floor-null"]["status"] == "pending"
    assert rep["sections"]["mlv2"]["finding"]["id"] == "mlv2-m5-transfer-failure" and schema_errors(rep) == []
    md = render(rep)
    assert md.index("## Evidence map") < md.index("## Findings") < md.index("## ML v2" if "## ML v2" in md else "## Models v2")
    assert "### ML v2 does not transfer to the simulated participants" in md and "**PENDING**" in md and "origin: **synthetic**" in md
    from understudy_engine.eval.facts import build_facts

    facts = build_facts(rep, tests=False)
    assert facts["findings"]["total"] == 5 and facts["findings"]["ok"] == ["mlv2-m5-transfer-failure"] and facts["flat"]["findings.total"] == 5


def test_the_schema_requires_text_and_a_badge_on_every_finding():
    base = {"generated_at": NOW, "mock": True, "sections": {}, "findings": [{"id": "x", "title": "t", "text": "words", "status": "ok", "origin": "synthetic", "badge": "b"}]}
    assert schema_errors(base) == []
    bad = json.loads(json.dumps(base))
    del bad["findings"][0]["badge"]
    assert any("badge" in e for e in schema_errors(bad))
    bad = json.loads(json.dumps(base))
    bad["findings"][0]["text"] = ""
    assert schema_errors(bad)


# ------------------------------------------------------------------------- the other recorded results wired this round
def fake_module(monkeypatch, dotted, attr, fn):
    mod = types.ModuleType(dotted)
    setattr(mod, attr, fn)
    monkeypatch.setitem(sys.modules, dotted, mod)


@pytest.fixture()
def evals(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    (tmp_path / "evals").mkdir()
    return tmp_path / "evals"


def test_evidence_never_goes_live_and_reads_the_committed_copy_of_the_recorded_live_block(evals, monkeypatch):
    seen = {}

    def fake(fast=False, *, seed=0, with_live=True):
        seen.update(with_live=with_live, env={k: os.environ.get(k) for k in ("UNDERSTUDY_EVIDENCE_LIVE", "OPENAI_API_KEY", "UNDERSTUDY_MOCK")})
        return {"status": "ok", "meta": META, "live": {"status": "not_run", "recorded": {"stale": "from data/"}}, "limitations": []}

    fake_module(monkeypatch, "understudy_engine.evidence.evaluate", "evaluate_evidence", fake)
    monkeypatch.setenv("UNDERSTUDY_EVIDENCE_LIVE", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-key")
    (evals / "evidence").mkdir()
    (evals / "evidence" / "live_recorded.json").write_text(json.dumps({"local_qwen25_7b": {"reword_final": {"rate": 0.8, "pass": 24, "n": 30, "ci": [0.63, 0.9]},
                                                                                       "reword_n30_before_fix": {"rate": 0.4, "pass": 12, "n": 30}}}))
    rep = build_report(sections=["evidence"], now=NOW, regenerate=False, log=lambda m: None)
    assert seen["with_live"] is False and seen["env"] == {"UNDERSTUDY_EVIDENCE_LIVE": None, "OPENAI_API_KEY": None, "UNDERSTUDY_MOCK": "1"}
    assert os.environ["UNDERSTUDY_EVIDENCE_LIVE"] == "local" and os.environ["OPENAI_API_KEY"] == "not-a-key"          # restored for the caller
    live = rep["sections"]["evidence"]["live"]
    assert live["recorded"]["local_qwen25_7b"]["reword_final"]["rate"] == 0.8 and "evals/evidence/live_recorded.json" in live["recorded_source"] and "stale" not in live["recorded"]
    reg = {e["id"]: e for e in rep["sections"]["limitations"]}
    t = reg["eval-evidence-local-model-first-run"]["text"]
    assert "40% (12 of 30) on its first n = 30 run" in t and "80% (24 of 30" in t and "in-sample" in t and reg["eval-evidence-local-model-first-run"]["severity"] == "high"
    assert "readability, not accuracy" in reg["eval-evidence-readability-not-accuracy"]["text"] and "traceability, not truth" in reg["eval-evidence-traceability-not-truth"]["text"]


def test_without_the_committed_copy_the_evidence_live_block_says_so(evals, monkeypatch):
    fake_module(monkeypatch, "understudy_engine.evidence.evaluate", "evaluate_evidence",
                lambda fast=False, *, seed=0, with_live=True: {"status": "ok", "meta": META, "live": {"status": "not_run", "recorded": {"x": 1}}, "limitations": []})
    live = build_report(sections=["evidence"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["evidence"]["live"]
    assert "recorded" not in live and "absent" in live["recorded_missing"]


def test_the_owner_statements_already_present_are_not_duplicated(evals, monkeypatch):
    fake_module(monkeypatch, "understudy_engine.evidence.evaluate", "evaluate_evidence",
                lambda fast=False, *, seed=0, with_live=True: {"status": "ok", "meta": META, "live": {}, "limitations": [
                    {"id": "explainer_readability_not_accuracy", "severity": "high", "text": "The explainer improves readability, not accuracy; the check proves traceability, not truth."}]})
    ids = {e["id"] for e in build_report(sections=["evidence"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["limitations"]}
    assert "explainer_readability_not_accuracy" in ids and "eval-evidence-readability-not-accuracy" not in ids and "eval-evidence-traceability-not-truth" not in ids


def test_cue_attention_insights_never_run_held_out_and_attach_recorded_results(evals, monkeypatch):
    calls = {}
    fake_module(monkeypatch, "understudy_engine.cue.evaluate", "evaluate_cue", lambda fast=False, *, held_out=False, root=None: (calls.update(cue=held_out), {"meta": META, "limitations": [], "held_out": {"status": "not_run"}})[1])
    fake_module(monkeypatch, "understudy_engine.attention.evaluate", "evaluate_attention", lambda fast=False, *, held_out=False, **kw: (calls.update(att=held_out), {"meta": {"badge": "b", "n_workers": 8, "split": "dev", "seeds": [0]}})[1])
    fake_module(monkeypatch, "understudy_engine.insights.evaluate", "evaluate_insights", lambda fast=False, heldout=False, **kw: (calls.update(ins=heldout), {"meta": {"badge": "synthetic firm", "seed_list": [0, 1], "people_per_firm": 60}, "limitations": ["Sentence limit."]})[1])
    (evals / "cue").mkdir()
    (evals / "cue" / "held_out.json").write_text(json.dumps({"cue": {"m": 1}, "score_validation": {"v": 2}, "params": {}, "meta": {}, "code_hashes": {"x": "y"}}))
    (evals / "attention").mkdir()
    (evals / "attention" / "report_held_out.json").write_text(json.dumps({"verdict": "ok"}))
    (evals / "insights").mkdir()
    (evals / "insights" / "heldout.json").write_text(json.dumps({"m1": 0.0}))
    rep = build_report(sections=["cue", "attention", "insights"], now=NOW, regenerate=False, log=lambda m: None)
    assert calls == {"cue": False, "att": False, "ins": False}
    s = rep["sections"]
    assert s["cue"]["held_out"]["cue"] == {"m": 1} and "code_hashes" not in s["cue"]["held_out"] and "never run by the harness" in s["cue"]["held_out"]["source"]
    assert s["attention"]["held_out"]["verdict"] == "ok" and s["attention"]["meta"]["n"] == 8 and s["attention"]["meta"]["n_unit"] == "simulated workers"
    assert s["insights"]["held_out"]["m1"] == 0.0 and s["insights"]["meta"]["n"] == 120 and "synthetic people" in s["insights"]["meta"]["n_unit"]
    assert any(e["source"].startswith("insights:insights") for e in s["limitations"])          # a plain-sentence limit became a register entry
    assert schema_errors(rep) == []


def test_hitlist_is_pending_until_it_has_an_evaluator(monkeypatch):
    monkeypatch.setitem(sys.modules, "understudy_engine.hitlist.evaluate", None)
    s = build_report(sections=["hitlist"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["hitlist"]
    assert s["status"] == "pending" and "hitlist not landed" in s["reason"]


def test_mlv2_attaches_the_recorded_held_out_and_transfer_files_and_never_asks_for_the_slow_path(evals, monkeypatch):
    import understudy_engine.mlv2.evaluate as mev

    seen = {}
    monkeypatch.setattr(mev, "evaluate_mlv2", lambda **kw: (seen.update(kw), {"meta": dict(META)})[1])
    heldout = {"hazard": {"x": 1}}
    monkeypatch.setattr(mev, "_load", lambda name: {"heldout_hazard.json": heldout, "transfer_sim.json": transfer()}.get(name))
    monkeypatch.setattr(mev, "slim_hazard", lambda r: {"slim": r})
    monkeypatch.setattr(mev, "_fingerprint_note", lambda res, part: {"part": part})
    monkeypatch.setattr(mev, "verdict_table", lambda *a: {"rows": len([x for x in a if x])})
    s = build_report(sections=["mlv2"], fast=False, now=NOW, regenerate=False, log=lambda m: None)["sections"]["mlv2"]
    assert seen.get("fast") is True                                              # even in a full eval run: the full dev run is the track's own command
    assert s["recorded"]["files"] == {"heldout_hazard.json": True, "heldout_genome.json": False, "heldout_mismatch.json": False, "transfer_sim.json": True}
    assert s["heldout"]["hazard"]["result"] == {"slim": heldout} and s["verdicts"] == {"rows": 1} and s["transfer_simulated_participants"]["n"] == 24


def test_a_failure_in_the_recorded_part_does_not_hide_the_dev_numbers(evals, monkeypatch):
    import understudy_engine.mlv2.evaluate as mev

    monkeypatch.setattr(mev, "evaluate_mlv2", lambda **kw: {"meta": dict(META), "dev": {"a": 1}})

    def boom(name):
        raise RuntimeError("bad file")

    monkeypatch.setattr(mev, "_load", boom)
    s = build_report(sections=["mlv2"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["mlv2"]
    assert s["dev"] == {"a": 1} and "bad file" in s["recorded_error"] and "status" not in s


def test_realism_runs_in_its_own_process_so_a_forked_pool_cannot_kill_the_harness(evals, monkeypatch):
    calls = {}
    monkeypatch.setattr(adapters, "_call_isolated", lambda module, attr, kw, timeout_s=1800: (calls.update(module=module, attr=attr, kw=kw), {"meta": META, "rows": []})[1])
    fake_module(monkeypatch, "understudy_engine.personas_v2.evaluate", "evaluate_realism", lambda fast=True: {})
    s = build_report(sections=["realism"], root=evals.parent, now=NOW, regenerate=False, log=lambda m: None)["sections"]["realism"]
    assert calls == {"module": "understudy_engine.personas_v2.evaluate", "attr": "evaluate_realism", "kw": {"fast": True}} and "status" not in s
    assert "blocks" not in s                                                   # no blocks recorded under this tmp root


def test_isolated_call_returns_json_and_raises_with_the_stderr_tail():
    assert adapters._call_isolated("json", "dumps", {"obj": {"a": 1}}) == '{"a": 1}'
    with pytest.raises(RuntimeError, match="failed in its own process"):
        adapters._call_isolated("understudy_engine.eval.nope_not_a_module", "x", {})


def test_a_section_with_three_findings_carries_the_first_and_lists_the_rest_and_the_markdown_shows_all_five(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    monkeypatch.setattr(adapters, "_call_isolated", lambda module, attr, kw, timeout_s=1800: {"meta": META, "rows": []})
    fake_module(monkeypatch, "understudy_engine.personas_v2.evaluate", "evaluate_realism", lambda fast=True: {})
    put(tmp_path, "eval/realism_blocks/hazard_benefits-processor.json", hazard_block())
    realism_section(tmp_path)
    (tmp_path / "evals" / "realism").mkdir(parents=True)
    (tmp_path / "evals" / "realism" / "REPORT.md").write_text("# REALISM REPORT\n")
    rep = build_report(sections=["realism"], root=tmp_path, now=NOW, regenerate=False, log=lambda m: None)
    s = rep["sections"]["realism"]
    assert s["finding"]["id"] == "realism-generator-dependence" and [x["id"] for x in s["more_findings"]] == ["realism-genome-generator-dependence", "realism-routines-generator-dependence"]
    assert s["report_file"]["path"] == "evals/realism/REPORT.md" and len(s["report_file"]["sha256"]) == 64 and s["report_file"]["bytes"] == 17
    assert set(s["blocks"]) == {"hazard", "genome", "routines"} and set(s["blocks"]["routines"]) == {"benefits-processor", "data-analyst", "programmer"}
    assert [f["status"] for f in rep["findings"]] == ["ok", "pending", "pending", "ok", "ok"] and schema_errors(rep) == []
    md = render(rep)
    for title in ("The stuck model's advantage depends on the generator", "Deficit detection does not hold up on harder generators",
                  "The repeat finder's precision depends on the generator; the gate carries the proposals"):
        assert f"### {title}" in md
