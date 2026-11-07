"""The assembler: pending/failed/not_run sections, schema validity, determinism, no network, the limitations register, the CLI."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from understudy_engine.eval import (
    adapters,
    assemble,
    build_report,
    deterministic_view,
    dumps,
    schema_errors,
)
from understudy_engine.eval import limitations as lim
from understudy_engine.eval.__main__ import main
from understudy_engine.eval.adapters import NotLanded, SectionSpec, owner_attr
from understudy_engine.eval.meta import make_meta

REPO = Path(__file__).resolve().parents[4]
FAST_CORE = ["deficit_recovery", "null_placebo", "routing", "ski_rental", "agent_claims", "agent_runs", "redteam", "redteam_live", "study_power", "study"]
NOW = "2026-11-07T15:00:00Z"


@pytest.fixture(autouse=True)
def _empty_study_dir(tmp_path, monkeypatch):
    """No live study results unless a test puts some there."""
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")


# ------------------------------------------------------------------------------------------------ pending and failure
def test_owner_attr_tells_a_missing_module_from_a_broken_one(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "eval_probe_broken.py").write_text("import a_dependency_that_does_not_exist_zzz\n")
    (tmp_path / "eval_probe_ok.py").write_text("def present():\n    return 1\n")
    with pytest.raises(NotLanded) as e:
        owner_attr("someone", "eval_probe_not_there_zzz", "f")
    assert "someone not landed" in str(e.value)
    with pytest.raises(NotLanded):
        owner_attr("someone", "eval_probe_ok", "missing_function")
    assert owner_attr("someone", "eval_probe_ok", "present")() == 1
    with pytest.raises(ModuleNotFoundError):      # a bug inside a module that exists is a real error, not "not landed"
        owner_attr("someone", "eval_probe_broken", "f")


def test_sections_whose_owner_has_not_landed_are_pending_with_a_reason_and_meta(monkeypatch):
    def missing(owner, module, attr):
        raise NotLanded(owner, f"module {module} missing")

    monkeypatch.setattr(adapters, "owner_attr", missing)
    rep = build_report(sections=["hazard", "redteam", "ski_rental"], now=NOW, regenerate=False, log=lambda m: None)
    for name, owner in (("hazard", "engine-analytics"), ("redteam", "agent-safety"), ("ski_rental", "engine-handoff")):
        s = rep["sections"][name]
        assert s["status"] == "pending" and s["reason"].startswith(f"{owner} not landed"), s
        assert s["meta"]["generated_at"] == NOW and s["meta"]["origin"] in ("real", "synthetic", "mixed")
    assert schema_errors(rep) == []
    ids = {e["id"] for e in rep["sections"]["limitations"]}
    assert {"eval-hazard-pending", "eval-redteam-pending", "eval-ski_rental-pending"} <= ids       # a missing section is itself a limitation


def test_missing_synthetic_data_is_pending_not_a_crash(tmp_path):
    rep = build_report(sections=["deficit_recovery", "null_placebo"], root=tmp_path, regenerate=False, now=NOW, log=lambda m: None)
    for name in ("deficit_recovery", "null_placebo"):
        assert rep["sections"][name]["status"] == "pending" and "data missing" in rep["sections"][name]["reason"]
    assert schema_errors(rep) == []


def test_a_section_that_raises_is_failed_loudly_and_the_others_still_run(monkeypatch):
    seen: list[str] = []

    def boom(ctx):
        raise RuntimeError("owner bug")

    def fine(ctx):
        return {"meta": make_meta("synthetic", 1, "people", "x")}

    specs = (SectionSpec("hazard", "engine-analytics", boom, False), SectionSpec("ope", "engine-analytics", fine, False))
    monkeypatch.setattr(assemble, "SECTIONS", specs)
    monkeypatch.setattr(assemble, "SECTION_NAMES", ("hazard", "ope"))
    rep = build_report(now=NOW, regenerate=False, log=seen.append)
    assert rep["sections"]["hazard"]["status"] == "failed" and "RuntimeError: owner bug" in rep["sections"]["hazard"]["reason"]
    assert "meta" in rep["sections"]["ope"] and "status" not in rep["sections"]["ope"]
    assert any("FAILED" in m and "owner bug" in m for m in seen)
    assert "eval-hazard-failed" in {e["id"] for e in rep["sections"]["limitations"]}


def test_unknown_section_name_is_an_error():
    with pytest.raises(ValueError, match="unknown section"):
        build_report(sections=["nope"], regenerate=False)


# ---------------------------------------------------------------------------------------------------------- the study
def test_study_not_run_when_there_are_no_results():
    rep = build_report(sections=["study"], now=NOW, regenerate=False, log=lambda m: None)
    s = rep["sections"]["study"]
    assert s["status"] == "not_run" and s["n"] == 4 and s["rows"] == [] and s["meta"]["origin"] == "real" and s["meta"]["n"] == 4
    assert schema_errors(rep) == []
    assert "eval-study-not_run" in {e["id"] for e in rep["sections"]["limitations"]}


def _study_dir(tmp_path, done, post=None, practice=None, exclusion=None):
    """A private evals/study with the platform's analyze.py and assignments.json and a made-up participants.csv (numbers for the test only)."""
    import csv
    import shutil

    src = REPO / "evals" / "study"
    d = tmp_path / "evals" / "study"
    (d / "results").mkdir(parents=True)
    shutil.copy(src / "analyze.py", d / "analyze.py")
    shutil.copy(src / "assignments.json", d / "assignments.json")
    asg = json.loads((src / "assignments.json").read_text())
    possible = {"cliff": 2, "reconcile": 1}
    cols = ["participant", "sequence", "block", "skill", "condition", "practice_case", "post_case", "practice_seconds", "practice_capped", "post_seconds",
            "post_capped", "post_checks_done", "post_checks_possible", "nudges_shown", "nudges_followed", "nudges_dismissed", "exclusion", "notes"]
    with (d / "results" / "participants.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for p, plan in asg["participants"].items():
            for b in plan["blocks"]:
                key = (p, b["condition"])
                w.writerow({"participant": p, "sequence": plan["sequence"], "block": b["block"], "skill": b["skill"], "condition": b["condition"],
                            "practice_case": b["practice_case"], "post_case": b["post_case"], "practice_seconds": (practice or {}).get(key, 300),
                            "practice_capped": "no", "post_seconds": (post or {}).get(key, 200), "post_capped": "no",
                            "post_checks_done": min(done.get(key, 0), possible[b["skill"]]), "post_checks_possible": possible[b["skill"]],
                            "nudges_shown": 6 if b["condition"] == "coached" else 0, "nudges_followed": 4 if b["condition"] == "coached" else 0,
                            "nudges_dismissed": 1 if b["condition"] == "coached" else 0, "exclusion": (exclusion or {}).get(p, ""), "notes": ""})
    return d


def test_study_follows_the_analysis_plan_headline_is_unassisted_skill_score_and_speed_is_separate(tmp_path):
    done = {("P1", "coached"): 2, ("P1", "uncoached"): 0, ("P2", "coached"): 1, ("P2", "uncoached"): 0, ("P3", "coached"): 2, ("P3", "uncoached"): 1,
            ("P4", "coached"): 1, ("P4", "uncoached"): 0}
    post = {("P1", "coached"): 150, ("P1", "uncoached"): 210}
    _study_dir(tmp_path, done, post=post)
    s = build_report(sections=["study"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study"]
    assert "status" not in s and s["n"] == 4 and s["meta"]["origin"] == "real" and s["meta"]["n"] == 4
    rows = {r["participant"]: r for r in s["rows"]}
    assert len(rows) == 4
    p1 = rows["P1"]
    assert p1["score_difference"] == pytest.approx(p1["score_coached"] - p1["score_uncoached"]) and p1["score_coached"] > p1["score_uncoached"]
    h = s["headline"]
    mean = sum(r["score_difference"] for r in s["rows"]) / 4
    assert h["mean_difference"] == pytest.approx(mean, abs=1e-3) and h["ci95"][0] < h["mean_difference"] < h["ci95"][1]
    assert h["smallest_possible_p"] == 0.125 and "t interval" in h["ci_method"]
    assert s["assisted_speed"]["label"].startswith("ASSISTED") and s["unassisted_speed"]["label"].startswith("UNASSISTED")
    assert "mean_difference" not in s["assisted_speed"] or s["assisted_speed"]["mean_difference_s"] != h["mean_difference"]      # never combined
    # contract keys for the dashboard come from the secondary unassisted-time measure, labelled as such
    assert s["mean_change_s"] == s["unassisted_speed"]["mean_difference_s"] and "alias_note" in s
    assert schema_errors({"generated_at": NOW, "mock": True, "sections": {"study": s}}) == []


def test_study_a_negative_difference_and_a_wide_interval_reach_the_register(tmp_path):
    done = {("P1", "coached"): 0, ("P1", "uncoached"): 1, ("P2", "coached"): 1, ("P2", "uncoached"): 0, ("P3", "coached"): 0, ("P3", "uncoached"): 0,
            ("P4", "coached"): 1, ("P4", "uncoached"): 0}
    _study_dir(tmp_path, done)
    rep = build_report(sections=["study"], now=NOW, regenerate=False, log=lambda m: None)
    s = rep["sections"]["study"]
    ids = {e["id"] for e in s["limitations"]}
    assert {"study-interval-includes-zero", "study-negative-differences"} <= ids
    assert {"study-interval-includes-zero", "study-negative-differences"} <= {e["id"] for e in rep["sections"]["limitations"]}


def test_study_exclusions_reduce_n_and_are_listed(tmp_path):
    done = {(p, c): (1 if c == "coached" else 0) for p in ("P1", "P2", "P3", "P4") for c in ("coached", "uncoached")}
    _study_dir(tmp_path, done, exclusion={"P4": "stopped before finishing"})
    rep = build_report(sections=["study"], now=NOW, regenerate=False, log=lambda m: None)
    s = rep["sections"]["study"]
    assert s["n"] == 3 and s["meta"]["n"] == 3 and s["excluded_participants"] == ["P4"]
    assert "study-exclusions" in {e["id"] for e in s["limitations"]}
    n_entry = next(e for e in rep["sections"]["limitations"] if e["id"] == "eval-study-n4")
    assert "n = 3" in n_entry["text"] and "planned" not in n_entry["text"]       # the register states the n the study actually has


def test_study_without_the_analysis_script_is_pending_not_invented(tmp_path):
    d = _study_dir(tmp_path, {})
    (d / "analyze.py").unlink()
    s = build_report(sections=["study"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study"]
    assert s["status"] == "pending" and "platform not landed" in s["reason"]


# ---------------------------------------------------------------------------------------------------- the real sections
@pytest.fixture(scope="module")
def core_report(synthetic_data):
    return build_report(fast=True, sections=FAST_CORE + ["presence", "routines"], now=NOW, regenerate=False, log=lambda m: None)


def test_real_sections_validate_against_the_schema(core_report):
    assert schema_errors(core_report) == []
    json.loads(dumps(core_report))            # strict JSON: no NaN or inf


def test_no_section_failed(core_report):
    failed = {k: v["reason"] for k, v in core_report["sections"].items() if isinstance(v, dict) and v.get("status") == "failed"}
    assert not failed, failed


def test_every_section_carries_complete_meta_stamped_with_the_report_time(core_report):
    for name, s in core_report["sections"].items():
        if name == "limitations":
            continue
        m = s["meta"]
        assert set(m) >= {"origin", "n", "n_unit", "split", "interval_level", "note", "generated_at"}, name
        assert m["generated_at"] == NOW, name
        assert m["origin"] in ("real", "synthetic", "mixed")


def test_every_section_that_has_numbers_names_its_split(core_report):
    for name, s in core_report["sections"].items():
        if name != "limitations" and "status" not in s:
            assert isinstance(s["meta"]["split"], str) and len(s["meta"]["split"]) > 8, name


def test_meta_fallback_fills_gaps_but_never_loses_what_the_owner_gave():
    from understudy_engine.eval.meta import normalise_meta

    m = normalise_meta({"origin": "real", "n": 3, "split": None, "note": "kept"}, {"split": "from fallback", "n_unit": "people", "note": "ignored"})
    assert m["origin"] == "real" and m["n"] == 3 and m["split"] == "from fallback" and m["note"] == "kept" and m["n_unit"] == "people"


def test_synthetic_sections_say_so(core_report):
    for name in ("deficit_recovery", "null_placebo", "routing", "ski_rental", "agent_claims", "agent_runs", "presence", "routines"):
        s = core_report["sections"][name]
        if "status" not in s:
            assert s["meta"]["origin"] == "synthetic", name


def test_dashboard_compat_aliases_are_present_beside_the_contract_keys(core_report):
    s = core_report["sections"]
    if "status" not in s["agent_claims"]:
        a = s["agent_claims"]
        assert {"reliability", "brier", "base_rate", "claims", "false_claims", "false_claim_rate", "false_claim_ci", "caught_by_code_check"} <= set(a)
    if "status" not in s["redteam"]:
        assert all("label" in r for r in s["redteam"]["rows"])
    if "status" not in s["ski_rental"]:
        assert s["ski_rental"]["hindsight_regret"] == 1.0 and s["ski_rental"]["hindsight"] == 1


def test_limitations_register_has_static_and_section_entries(core_report):
    lims = core_report["sections"]["limitations"]
    ids = [e["id"] for e in lims]
    assert len(ids) == len(set(ids))
    assert {"eval-synthetic", "eval-study-n4", "eval-thin-real-data", "eval-oracle", "eval-sandbox-sites", "eval-claims-simulated", "eval-offhours-s2"} <= set(ids)
    for e in lims:
        assert e["severity"] in ("low", "medium", "high") and e["text"] and e["source"]
    sev = [lim.SEV_RANK[e["severity"]] for e in lims]
    assert sev == sorted(sev), "most serious first"
    assert any(e["source"].startswith("engine-handoff") for e in lims) and any(e["source"].startswith("engine-analytics") for e in lims)


# --------------------------------------------------------------------------------------------------------- limitations
def test_oracle_entry_reads_its_numbers_from_the_spike_record_not_from_code():
    text = lim._oracle_text()
    spikes = (REPO / "docs" / "SPIKES.md").read_text()
    import re
    m = re.search(r"agree within 1 pound on only (\d+) of (\d+)", spikes)
    if m:
        assert f"{m.group(1)} of {m.group(2)}" in text
    assert "not the law" in text


def _sec(**kw):
    return {"meta": make_meta("synthetic", 1, "people", "x"), **kw}


def test_weak_results_are_added_to_the_register_whatever_the_owner_wrote():
    sections = {
        "routing": _sec(bound_held=False),
        "hazard": _sec(model={"log_loss": 0.6}, baselines={"time_since_progress": {"log_loss": 0.5}, "base_rate": {"log_loss": 0.55}},
                       false_alarms_within_budget=False, false_alarms_per_hour=1.4, budget_false_alarms_per_hour=1.0),
        "ope": _sec(true_value=0.02, headline_target="t", estimators=[{"name": "dr", "value": 0.2, "ci": [0.15, 0.25]}],
                    replications={"n_replications": 10, "by_target": {"t": {"dr": {"ci_coverage": 0.5}, "ips": {"ci_coverage": 0.95}, "snips": {"ci_coverage": 0.95}}}}),
        "null_placebo": _sec(real={"gap_s": 100, "ci": [80, 120]}, placebo={"gap_s": 20, "ci": [10, 30]}, null={"gap_s": 40, "ci": [-30, 110]}),
        "deficit_recovery": _sec(rows=[{"deficit": "d", "precision": 0.5, "recall": 0.6, "bias_s": 30.0, "bias_ci": [10.0, 50.0]}],
                                 overall={"precision": 0.5, "recall": 0.6, "pairs": 10}),
        "redteam": _sec(rows=[{"ablation": "all_on", "attack_success": 0.1, "attack_ci": [0.0, 0.3]}]),
    }
    ids = {e["id"] for e in lim.assemble(sections)}
    assert {"eval-routing-bound-failed", "eval-hazard-not-better", "eval-hazard-alarm-budget", "eval-ope-coverage", "eval-placebo-nonzero",
            "eval-null-offset", "eval-deficit-weak", "eval-deficit-bias", "eval-redteam-attacks-succeed"} <= ids


def test_good_results_add_no_computed_entries():
    sections = {
        "routing": _sec(bound_held=True),
        "hazard": _sec(model={"log_loss": 0.4}, baselines={"time_since_progress": {"log_loss": 0.5}, "base_rate": {"log_loss": 0.55}}, false_alarms_within_budget=True),
        "redteam": _sec(rows=[{"ablation": "all_on", "attack_success": 0.0, "attack_ci": [0.0, 0.05]}]),
    }
    assert not [e for e in lim.assemble(sections) if e["id"].startswith("eval-") and e["source"].startswith("engine-eval:")]


def test_owner_entries_are_deduplicated_by_id_with_sources_joined_and_generic_synthetic_folded():
    entry = {"id": "ana-hazard-people", "text": "Four people.", "severity": "high"}
    generic = {"id": "ana-synthetic-origin", "text": "All synthetic.", "severity": "high"}
    sections = {"hazard": _sec(limitations=[entry, generic]), "policy_gate": _sec(limitations=[entry, generic])}
    out = lim.assemble(sections)
    people = [e for e in out if e["id"] == "ana-hazard-people"]
    assert len(people) == 1 and "hazard" in people[0]["source"] and "policy_gate" in people[0]["source"]
    assert not [e for e in out if e["id"] == "ana-synthetic-origin"]
    umbrella = next(e for e in out if e["id"] == "eval-synthetic")
    assert "engine-analytics:hazard" in umbrella["source"]


def test_only_all_caps_keyword_caveats_are_lifted_into_the_register():
    sections = {"routing": _sec(caveats=["CIRCULARITY: we planted the quirks.", "Expert review time is an assumption."])}
    out = lim.assemble(sections)
    assert any(e["id"] == "routing-circularity" and e["severity"] == "medium" for e in out)
    assert not any("Expert review time" in e["text"] for e in out)


# ----------------------------------------------------------------------------------------------- determinism and mock
def test_two_runs_give_identical_numbers(synthetic_data):
    a = build_report(fast=True, sections=FAST_CORE, now=NOW, regenerate=False, log=lambda m: None)
    b = build_report(fast=True, sections=FAST_CORE, now=NOW, regenerate=False, log=lambda m: None)
    assert deterministic_view(a) == deterministic_view(b)
    a["run"], b["run"] = {}, {}
    assert dumps(a) == dumps(b)          # even the bytes, once timing is set aside


def test_two_processes_with_different_hash_seeds_give_identical_numbers(synthetic_data, tmp_path):
    outs = []
    for k, hs in enumerate(("1", "4242")):
        out = tmp_path / f"r{k}.json"
        env = dict(os.environ, PYTHONHASHSEED=hs, UNDERSTUDY_MOCK="1")
        p = subprocess.run([sys.executable, "-m", "understudy_engine.eval", "--fast", "--no-generate", "--no-md", "--sections",
                            "deficit_recovery,null_placebo,ski_rental,routing,agent_claims,agent_runs,redteam,redteam_live,study_power,study", "--out", str(out)],
                           capture_output=True, text=True, env=env, cwd=str(REPO), timeout=300)
        assert p.returncode == 0, p.stderr[-2000:]
        outs.append(deterministic_view(json.loads(out.read_text())))
    assert outs[0] == outs[1]


def test_mock_flag_follows_the_environment(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    assert build_report(sections=["study"], regenerate=False, log=lambda m: None)["mock"] is True
    monkeypatch.delenv("UNDERSTUDY_MOCK")
    assert build_report(sections=["study"], regenerate=False, log=lambda m: None)["mock"] is False


def test_eval_needs_no_network_and_no_model(synthetic_data, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("the eval tried to use the network")

    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    rep = build_report(fast=True, sections=FAST_CORE + ["presence"], now=NOW, regenerate=False, log=lambda m: None)
    assert not [k for k, v in rep["sections"].items() if isinstance(v, dict) and v.get("status") == "failed"]


# --------------------------------------------------------------------------------------------------------------- the CLI
def test_cli_writes_report_json_and_markdown(synthetic_data, tmp_path, capsys):
    out = tmp_path / "report.json"
    rc = main(["--fast", "--no-generate", "--sections", "deficit_recovery,null_placebo,ski_rental,study", "--out", str(out)])
    assert rc == 0
    rep = json.loads(out.read_text())
    assert schema_errors(rep) == [] and set(rep["sections"]) == {"deficit_recovery", "null_placebo", "ski_rental", "study", "limitations"}
    md = out.with_suffix(".md").read_text()
    assert "# Understudy evaluation report" in md and "## Limitations register" in md
    assert "origin: **synthetic**" in md and "n = " in md and "95%" in md
    assert "NOT RUN" in md          # the study
    assert "wrote" in capsys.readouterr().out


def test_cli_refuses_to_write_an_invalid_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("understudy_engine.eval.__main__.errors", lambda r: ["sections/x: broken"])
    out = tmp_path / "r.json"
    assert main(["--fast", "--no-generate", "--sections", "study", "--out", str(out)]) == 3
    assert not out.exists()
    assert main(["--fast", "--no-generate", "--sections", "study", "--out", str(out), "--force"]) == 0 and out.exists()


def test_cli_exit_code_2_when_a_section_failed(tmp_path, monkeypatch):
    def boom(ctx):
        raise RuntimeError("x")

    monkeypatch.setattr(assemble, "SECTIONS", (SectionSpec("hazard", "engine-analytics", boom, False),))
    monkeypatch.setattr(assemble, "SECTION_NAMES", ("hazard",))
    monkeypatch.setattr("understudy_engine.eval.__main__.SECTION_NAMES", ("hazard",))
    assert main(["--no-generate", "--out", str(tmp_path / "r.json"), "--no-md"]) == 2


def test_cli_rejects_unknown_sections(capsys):
    assert main(["--sections", "nope", "--no-generate"]) == 2
    assert "unknown section" in capsys.readouterr().err


def test_clean_makes_everything_json_safe():
    import numpy as np

    out = assemble.clean({"a": float("nan"), "b": np.float64(1.5), "c": (np.int64(2), float("inf")), "d": np.array([1.0, float("nan")]), "e": {3, 1}})
    assert out == {"a": None, "b": 1.5, "c": [2, None], "d": [1.0, None], "e": [1, 3]}
    json.dumps(out, allow_nan=False)
