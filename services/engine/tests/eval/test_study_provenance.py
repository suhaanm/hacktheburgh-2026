"""H5 (REVIEW-PRIVACY): the live `study` section must never show simulated participants as people.

It needs a hand-written results/MANIFEST.json (origin "human", consent_ref, collected_by, n_participants, date); no manifest means not_run, never ok. It refuses
symlinks, anything whose columns or ids look simulated, and a manifest whose n disagrees with the file. Its origin is "unknown" until all of that holds.
The same rule covers any other section that claims its data are people."""
from __future__ import annotations

import json
import os
import shutil

import pytest
from understudy_engine.eval import adapters, build_report, schema_errors
from understudy_engine.eval.render_md import render

from .helpers import GOOD_DONE, MANIFEST_OK, REPO, study_dir

NOW = "2026-11-07T15:00:00Z"
SIM_EXTRA = {"arm": "coached", "persona": "careful", "model": "m", "effort_unit": "actions"}


@pytest.fixture(autouse=True)
def _tmp_evals(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    (tmp_path / "evals").mkdir(exist_ok=True)


def study_section(tmp_path):
    rep = build_report(sections=["study"], now=NOW, regenerate=False, log=lambda m: None)
    return rep, rep["sections"]["study"]


# -------------------------------------------------------------------------------------------------------------- the valid case
def test_a_valid_manifest_and_human_looking_results_are_shown_as_real(tmp_path):
    study_dir(tmp_path, GOOD_DONE)
    rep, s = study_section(tmp_path)
    assert "status" not in s and s["meta"]["origin"] == "real" and s["n"] == 4
    assert s["provenance"] == MANIFEST_OK and schema_errors(rep) == []
    assert rep["evidence_map"][0]["origin"] == "real" and rep["evidence_map"][0]["status"] == "ok"


def test_the_manifest_n_must_match_the_file(tmp_path):
    study_dir(tmp_path, GOOD_DONE, manifest=dict(MANIFEST_OK, n_participants=9))
    rep, s = study_section(tmp_path)
    assert s["status"] == "invalid_provenance" and "manifest says 9 participants but the results file has 4" in s["reason"] and s["meta"]["origin"] == "unknown"
    assert schema_errors(rep) == []


# ---------------------------------------------------------------------------------------------------- the cp case (no manifest)
def test_a_copied_simulated_csv_with_no_manifest_is_not_run(tmp_path):
    sim_csv = REPO / "evals" / "study_sim" / "results" / "participants.csv"
    d = study_dir(tmp_path, GOOD_DONE, manifest=None, ids={"P1": "p_sim01", "P2": "p_sim02", "P3": "p_sim03", "P4": "p_sim04"}, extra_columns=SIM_EXTRA)
    if sim_csv.is_file():                              # the real thing, if the simulation has produced one on this machine
        shutil.copy(sim_csv, d / "results" / "participants.csv")
    rep, s = study_section(tmp_path)
    assert s["status"] == "not_run" and s["reason"].startswith("no human-study manifest") and s["rows"] == [] and s["meta"]["origin"] == "unknown"
    assert "p_sim" not in json.dumps(rep["sections"]["study"])
    assert rep["evidence_map"][0]["status"] == "not_run" and rep["evidence_map"][0]["origin"] == "unknown"


def test_a_copied_simulated_csv_even_with_a_manifest_saying_human_is_invalid(tmp_path):
    study_dir(tmp_path, GOOD_DONE, manifest=True, ids={"P1": "p_sim01", "P2": "p_sim02", "P3": "p_sim03", "P4": "p_sim04"}, extra_columns=SIM_EXTRA)
    rep, s = study_section(tmp_path)
    assert s["status"] == "invalid_provenance" and "look simulated" in s["reason"] and "p_sim01" in s["reason"] and "arm" in s["reason"] and "persona" in s["reason"]
    assert s["rows"] == [] and s["meta"]["origin"] == "unknown" and schema_errors(rep) == []
    assert "eval-study-invalid_provenance" in {e["id"] for e in rep["sections"]["limitations"]}


@pytest.mark.parametrize("ids,extra,needle", [
    ({"P1": "p_sim01"}, None, "participant ids p_sim01"),
    ({"P2": "sim02"}, None, "sim02"),
    ({"P3": "silicon_3"}, None, "silicon_3"),
    (None, {"arm": "coached"}, "columns arm"),
    (None, {"persona": "x"}, "persona"),
    (None, {"model": "x"}, "model"),
    (None, {"effort_unit": "actions"}, "effort_unit"),
    (None, {"sim_seed": "7"}, "sim_seed"),
])
def test_each_sign_of_a_simulation_is_enough_with_a_manifest_that_says_human(tmp_path, ids, extra, needle):
    study_dir(tmp_path, GOOD_DONE, manifest=True, ids=ids, extra_columns=extra)
    _, s = study_section(tmp_path)
    assert s["status"] == "invalid_provenance" and needle in s["reason"]


# ------------------------------------------------------------------------------------------------------------ the symlink case
def test_a_symlinked_participants_file_is_refused_even_with_a_valid_manifest(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    d = study_dir(tmp_path / "src", GOOD_DONE, manifest=True)
    elsewhere.mkdir()
    shutil.copy(d / "results" / "participants.csv", elsewhere / "participants.csv")
    live = study_dir(tmp_path, GOOD_DONE, manifest=True)
    (live / "results" / "participants.csv").unlink()
    os.symlink(elsewhere / "participants.csv", live / "results" / "participants.csv")
    rep, s = study_section(tmp_path)
    assert s["status"] == "invalid_provenance" and "symlink" in s["reason"] and "participants.csv" in s["reason"] and s["rows"] == []
    assert schema_errors(rep) == []


def test_a_symlinked_results_directory_is_refused(tmp_path):
    src = study_dir(tmp_path / "src", GOOD_DONE, manifest=True)
    live = study_dir(tmp_path, {}, manifest=None)
    shutil.rmtree(live / "results")
    os.symlink(src / "results", live / "results")
    s = study_section(tmp_path)[1]
    assert s["status"] == "invalid_provenance" and "symlink" in s["reason"]


def test_a_symlinked_manifest_is_refused(tmp_path):
    src = tmp_path / "other_manifest.json"
    src.write_text(json.dumps(MANIFEST_OK))
    live = study_dir(tmp_path, GOOD_DONE, manifest=None)
    os.symlink(src, live / "results" / "MANIFEST.json")
    s = study_section(tmp_path)[1]
    assert s["status"] == "invalid_provenance" and "MANIFEST.json is a symlink" in s["reason"]


def test_a_symlinked_study_directory_is_refused(tmp_path):
    real = study_dir(tmp_path / "src", GOOD_DONE, manifest=True)
    link = tmp_path / "evals" / "study"
    os.symlink(real, link)
    s = study_section(tmp_path)[1]
    assert s["status"] == "invalid_provenance" and "symlink" in s["reason"]


# ------------------------------------------------------------------------------------------------------------ bad manifests
@pytest.mark.parametrize("manifest,needle", [
    (dict(MANIFEST_OK, origin="synthetic"), "not 'human'"),
    (dict(MANIFEST_OK, origin="simulated"), "not 'human'"),
    ({k: v for k, v in MANIFEST_OK.items() if k != "consent_ref"}, "missing consent_ref"),
    (dict(MANIFEST_OK, collected_by=""), "missing collected_by"),
    (dict(MANIFEST_OK, n_participants="four"), "positive integer"),
    (dict(MANIFEST_OK, n_participants=0), "positive integer"),
    ([1, 2], "not a JSON object"),
])
def test_a_manifest_that_does_not_vouch_for_people_is_invalid(tmp_path, manifest, needle):
    study_dir(tmp_path, GOOD_DONE, manifest=manifest)
    _, s = study_section(tmp_path)
    assert s["status"] == "invalid_provenance" and needle in s["reason"]


def test_an_unreadable_manifest_is_invalid(tmp_path):
    d = study_dir(tmp_path, GOOD_DONE, manifest=None)
    (d / "results" / "MANIFEST.json").write_text("{not json")
    assert study_section(tmp_path)[1]["status"] == "invalid_provenance"


# ------------------------------------------------------------------------------------------------------------- summary.json
def test_a_summary_json_needs_the_manifest_too_and_must_be_marked_real(tmp_path):
    blocks = [{"participant": "P1", "condition": c, "skill": s_, "post_score": 1.0, "post_seconds": 10, "practice_seconds": 10, "post_capped": False, "practice_capped": False}
              for c, s_ in (("coached", "cliff"), ("uncoached", "reconcile"))]
    summary = {"meta": {"origin": "real", "n": 1}, "headline_unassisted": {"blocks": blocks, "ci95": [None, None]}, "unassisted_speed": {}}
    d = tmp_path / "evals" / "study" / "results"
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps(summary))
    assert study_section(tmp_path)[1]["status"] == "not_run"                         # no manifest
    (d / "MANIFEST.json").write_text(json.dumps(dict(MANIFEST_OK, n_participants=1)))
    s = study_section(tmp_path)[1]
    assert "status" not in s and s["meta"]["origin"] == "real" and s["n"] == 1
    (d / "summary.json").write_text(json.dumps(dict(summary, meta={"origin": "synthetic", "n": 1})))
    s = study_section(tmp_path)[1]
    assert s["status"] == "invalid_provenance" and "not marked as people's data" in s["reason"]
    blocks[0]["participant"] = "p_sim01"
    (d / "summary.json").write_text(json.dumps(summary))
    assert study_section(tmp_path)[1]["status"] == "invalid_provenance"


def test_no_results_at_all_is_a_plain_not_run_with_origin_unknown(tmp_path):
    s = study_section(tmp_path)[1]
    assert s["status"] == "not_run" and "no data" in s["reason"] and s["meta"]["origin"] == "unknown"


# ---------------------------------------------------------------- the other sections that could carry the same flaw
def put_dir_section(tmp_path, name, origin, rows=None):
    d = tmp_path / "evals" / name
    d.mkdir()
    (d / "summary.json").write_text(json.dumps({"meta": {"origin": origin, "n": 6, "n_unit": "people", "split": "x", "interval_level": 0.95, "note": None, "generated_at": None},
                                                 "rows": rows or [{"participant": "P1", "v": 1}]}))
    return d


def test_study_roles_cannot_call_itself_real_without_a_manifest(tmp_path):
    put_dir_section(tmp_path, "study_roles", "real")
    s = build_report(sections=["study_roles"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study_roles"]
    assert s["status"] == "invalid_provenance" and "no hand-written study_roles/MANIFEST.json" in s["reason"] and s["meta"]["origin"] == "unknown"


def test_study_roles_real_with_a_manifest_is_accepted_and_with_simulated_ids_is_not(tmp_path):
    d = put_dir_section(tmp_path, "study_roles", "real")
    (d / "MANIFEST.json").write_text(json.dumps(MANIFEST_OK))
    s = build_report(sections=["study_roles"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study_roles"]
    assert "status" not in s and s["meta"]["origin"] == "real"
    put_dir_section_rows = [{"participant": "p_sim01", "v": 1}]
    (d / "summary.json").write_text(json.dumps({"meta": {"origin": "real", "n": 1, "n_unit": "people"}, "rows": put_dir_section_rows}))
    s = build_report(sections=["study_roles"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study_roles"]
    assert s["status"] == "invalid_provenance" and "looks simulated" in s["reason"]


def test_a_synthetic_study_roles_needs_no_manifest(tmp_path):
    put_dir_section(tmp_path, "study_roles", "synthetic")
    s = build_report(sections=["study_roles"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study_roles"]
    assert "status" not in s and s["meta"]["origin"] == "synthetic"


@pytest.mark.parametrize("section,rel", [("runtime", "eval/runtime_eval.json"), ("modelbench", "eval/modelbench.json")])
def test_result_files_claiming_real_data_need_a_manifest_beside_them(tmp_path, section, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"meta": {"origin": "real", "n": 3, "n_unit": "runs", "split": "x", "interval_level": 0.95, "note": None, "generated_at": None}, "rows": []}))
    s = build_report(sections=[section], root=tmp_path, now=NOW, regenerate=False, log=lambda m: None)["sections"][section]
    assert s["status"] == "invalid_provenance" and "MANIFEST.json" in s["reason"]


def test_study_power_is_always_synthetic_whatever_the_owner_says(monkeypatch):
    import sys
    import types

    mod = types.ModuleType("understudy_engine.study_power")
    mod.evaluate_study_power = lambda fast=False: {"rows": [], "meta": {"origin": "real", "n": 4, "n_unit": "people", "split": "x", "interval_level": 0.95, "note": None, "generated_at": None}}
    monkeypatch.setitem(sys.modules, "understudy_engine.study_power", mod)
    s = build_report(sections=["study_power"], now=NOW, regenerate=False, log=lambda m: None)["sections"]["study_power"]
    assert s["meta"]["origin"] == "synthetic"


def test_study_sim_is_always_synthetic_and_never_feeds_the_live_study(tmp_path):
    d = tmp_path / "evals" / "study_sim"
    d.mkdir()
    (d / "__init__.py").write_text("def study_sim_section():\n    return {'meta': {'origin': 'real', 'n': 8, 'n_unit': 'runs', 'split': 's', 'interval_level': 0.95, 'note': None, 'generated_at': None}}\n")
    rep = build_report(sections=["study", "study_sim"], now=NOW, regenerate=False, log=lambda m: None)
    assert rep["sections"]["study_sim"]["meta"]["origin"] == "synthetic" and rep["sections"]["study"]["status"] == "not_run"


# ---------------------------------------------------------------------------------------------------- how it shows up
def test_markdown_says_invalid_provenance_and_shows_no_numbers(tmp_path):
    study_dir(tmp_path, GOOD_DONE, manifest=True, extra_columns=SIM_EXTRA)
    rep, _ = study_section(tmp_path)
    md = render(rep)
    sec = md[md.index("## Live study"):md.index("## Limitations register")]
    assert "INVALID PROVENANCE" in sec and "look simulated" in sec and "score_difference" not in sec
    first = md[md.index("## Evidence map"):md.index("## Live study")]
    assert "n/a" in first and "invalid provenance" in first.lower()


def test_schema_accepts_unknown_origin_and_the_new_status_but_not_a_real_study_without_it():
    meta = {"origin": "unknown", "n": 4, "n_unit": "people", "split": "x", "interval_level": 0.95, "note": None, "generated_at": NOW}
    ok = {"generated_at": NOW, "mock": True, "sections": {"study": {"status": "invalid_provenance", "reason": "r", "meta": meta, "rows": [], "n": 4}}}
    assert schema_errors(ok) == []
    row = {"participant": "P1", "unassisted_before_s": 1.0, "unassisted_after_s": 2.0}
    bad = {"generated_at": NOW, "mock": True, "sections": {"study": {"meta": meta, "rows": [row], "mean_change_s": 1.0, "mean_change_ci": [0.0, 2.0], "n": 1}}}
    assert any("real" in e for e in schema_errors(bad))
