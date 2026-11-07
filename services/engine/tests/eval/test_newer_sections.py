"""The newer owner sections (git, proactive, calendar, localmodel, runtime, mlv2, evidence, cue, realism, modelbench, study_roles, agentic)
and the Evidence map. Landed owners run for real once (fast); the rest are tested with fixture files and stand-in modules so they light up as tracks land."""
from __future__ import annotations

import ast
import inspect
import json
import os
import sys
import types
from pathlib import Path

import pytest
from understudy_engine.eval import (
    adapters,
    build_report,
    deterministic_view,
    schema_errors,
)
from understudy_engine.eval import limitations as lim
from understudy_engine.eval.adapters import Ctx
from understudy_engine.eval.render_md import render

NOW = "2026-11-07T15:00:00Z"
META = {"origin": "synthetic", "n": 7, "n_unit": "items", "split": "x", "interval_level": 0.95, "note": "n", "generated_at": "x"}


def build(sections, root=None, **kw):
    return build_report(sections=sections, root=root, now=NOW, regenerate=False, log=lambda m: None, **kw)


@pytest.fixture()
def evals(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    (tmp_path / "evals").mkdir()
    return tmp_path / "evals"


def fake_module(monkeypatch, dotted, attr, fn):
    mod = types.ModuleType(dotted)
    setattr(mod, attr, fn)
    monkeypatch.setitem(sys.modules, dotted, mod)
    parent = dotted.rsplit(".", 1)[0]
    if parent not in sys.modules or sys.modules[parent] is None:
        monkeypatch.setitem(sys.modules, parent, types.ModuleType(parent))
    return mod


# --------------------------------------------------------------------------------------------- landed owners, run for real
@pytest.fixture(scope="module")
def landed():
    return build_report(sections=["git", "proactive", "calendar", "localmodel"], fast=True, now=NOW, regenerate=False, log=lambda m: None)


def test_landed_owner_sections_validate_and_carry_meta(landed):
    assert schema_errors(landed) == []
    for name in ("git", "proactive", "calendar", "localmodel"):
        s = landed["sections"][name]
        assert "status" not in s, (name, s.get("reason"))
        assert s["meta"]["origin"] == "synthetic" and s["meta"]["n"] > 0 and s["meta"]["generated_at"] == NOW and s["meta"]["split"]


def test_owner_status_ok_is_not_mistaken_for_a_stub_and_timing_is_dropped(landed):
    for name in ("git", "localmodel"):
        s = landed["sections"][name]
        assert s.get("owner_status") == "ok" and "elapsed_s" not in s and "wall_s" not in s


def test_owner_limitations_are_merged_into_the_register_with_their_source(landed):
    reg = {e["id"]: e for e in landed["sections"]["limitations"]}
    for name, owner_id in (("git", "git-synthetic"), ("proactive", "pro-iterated-on-eval"), ("calendar", "cal-synthetic-only"), ("localmodel", "loc_synthetic")):
        assert owner_id in reg, owner_id
        assert name in reg[owner_id]["source"]
    assert reg["pro-iterated-on-eval"]["severity"] == "high"


def test_the_local_model_is_never_started_by_the_harness(landed):
    m = landed["sections"]["localmodel"]["model"]
    assert m["source"] != "live" and not m.get("shipped_arm_run_now")


def test_landed_markdown_shows_the_headline_numbers(landed):
    md = render(landed)
    assert "Planted habit (synthetic developers)" in md and "Precision [95%]" in md
    assert "Planted problems found, eight types" in md
    assert "Cards worth surfacing" in md and "What surfaces cards" in md
    assert "Local model accuracy [95%]" in md and "Held-out n" in md


def test_calendar_and_localmodel_are_deterministic():
    a = build(["calendar", "localmodel"], fast=True)
    b = build(["calendar", "localmodel"], fast=True)
    assert deterministic_view(a) == deterministic_view(b)


# ------------------------------------------------------------------------------------------ the shape rules, on stand-ins
def test_a_stub_status_from_an_owner_becomes_a_stub_with_its_reason(monkeypatch):
    fake_module(monkeypatch, "understudy_engine.mlv2.evaluate", "evaluate_mlv2", lambda fast=False: {"status": "not_run", "reason": "no GPU here", "meta": META})
    s = build(["mlv2"])["sections"]["mlv2"]
    assert s["status"] == "not_run" and s["reason"] == "no GPU here"


def test_a_stub_status_without_a_reason_gets_one_from_the_meta_note(monkeypatch):
    fake_module(monkeypatch, "understudy_engine.cue.evaluate", "evaluate_cue", lambda fast=False, **kw: {"status": "pending", "meta": dict(META, note="waiting for data")})
    s = build(["cue"])["sections"]["cue"]
    assert s["status"] == "pending" and s["reason"] == "waiting for data"


def test_any_other_owner_status_is_kept_as_owner_status_on_a_section_with_numbers(monkeypatch):
    fake_module(monkeypatch, "understudy_engine.evidence.evaluate", "evaluate_evidence",
                lambda fast=False, **kw: {"status": "model_not_run", "meta": META, "rows": [{"a": 1}], "limitations": [{"id": "ev-1", "text": "Small n.", "severity": "high"}, "A plain sentence limit."]})
    rep = build(["evidence"])
    s = rep["sections"]["evidence"]
    assert "status" not in s and s["owner_status"] == "model_not_run" and s["rows"] == [{"a": 1}] and schema_errors(rep) == []
    reg = {e["id"]: e for e in rep["sections"]["limitations"]}
    assert reg["ev-1"]["severity"] == "high" and reg["evidence-limit-2"]["text"] == "A plain sentence limit." and reg["evidence-limit-2"]["severity"] == "medium"


def test_the_owners_own_timing_fields_are_dropped_so_two_runs_match(monkeypatch):
    counter = iter(range(100))
    fake_module(monkeypatch, "understudy_engine.personas_v2.evaluate", "evaluate_realism", lambda fast=False: {"meta": META, "elapsed_s": next(counter), "wall_s": 9.9, "rows": [1]})
    a, b = build(["realism"]), build(["realism"])
    assert deterministic_view(a) == deterministic_view(b) and "elapsed_s" not in a["sections"]["realism"]


def test_oversized_keys_are_listed_not_copied(monkeypatch):
    fake_module(monkeypatch, "understudy_engine.mlv2.evaluate", "evaluate_mlv2", lambda fast=False: {"meta": META, "small": [1], "huge": ["x" * 100] * 1000})
    s = build(["mlv2"])["sections"]["mlv2"]
    assert s["small"] == [1] and s["huge"] is None and s["trimmed"][0]["key"] == "huge" and s["trimmed"][0]["bytes"] > adapters.COMPACT_BYTES


def test_owner_calls_run_offline_whatever_the_callers_environment_says(monkeypatch):
    seen = []
    fake_module(monkeypatch, "understudy_engine.cue.evaluate", "evaluate_cue", lambda fast=False, **kw: (seen.append(os.environ.get("UNDERSTUDY_MOCK")), {"meta": META})[1])
    for before in (None, "0", "1"):
        if before is None:
            monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
        else:
            monkeypatch.setenv("UNDERSTUDY_MOCK", before)
        build(["cue"])
        assert os.environ.get("UNDERSTUDY_MOCK") == before          # restored
    assert seen == ["1", "1", "1"]


def test_fast_is_passed_only_to_owners_that_take_it(monkeypatch):
    got = {}
    fake_module(monkeypatch, "understudy_engine.mlv2.evaluate", "evaluate_mlv2", lambda fast=False: (got.update(a=fast), {"meta": META})[1])
    fake_module(monkeypatch, "understudy_engine.cue.evaluate", "evaluate_cue", lambda **kw: {"meta": META})
    build(["mlv2", "cue"], fast=True)
    assert got["a"] is True
    assert "status" not in build(["cue"])["sections"]["cue"]


def test_missing_modules_are_pending_with_the_owner_named(monkeypatch):
    for dotted in ("understudy_engine.mlv2.evaluate", "understudy_engine.evidence.evaluate", "understudy_engine.cue.evaluate", "understudy_engine.personas_v2.evaluate"):
        monkeypatch.setitem(sys.modules, dotted, None)
    rep = build(["mlv2", "evidence", "cue", "realism"])
    for name, owner in (("mlv2", "mlv2"), ("evidence", "evidence"), ("cue", "cue"), ("realism", "personas-v2")):
        s = rep["sections"][name]
        assert s["status"] == "pending" and s["reason"].startswith(f"{owner} not landed"), s
    assert schema_errors(rep) == []


def test_an_owner_that_raises_is_failed_and_visible(monkeypatch):
    def boom(fast=False, **kw):
        raise RuntimeError("model call failed")

    fake_module(monkeypatch, "understudy_engine.cue.evaluate", "evaluate_cue", boom)
    s = build(["cue"])["sections"]["cue"]
    assert s["status"] == "failed" and "model call failed" in s["reason"]


# ---------------------------------------------------------------------------------------- files the other tracks write
def put(root: Path, rel: str, data: dict) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


@pytest.mark.parametrize("section,rel,owner", [("runtime", "eval/runtime_eval.json", "agent-runtime"), ("modelbench", "eval/modelbench.json", "modelbench")])
def test_result_files_are_read_not_run(tmp_path, section, rel, owner):
    s = build([section], root=tmp_path)["sections"][section]
    assert s["status"] == "pending" and s["reason"].startswith(f"{owner} not landed") and f"data/{rel}" in s["reason"] and "never runs models" in s["reason"]
    put(tmp_path, rel, {"meta": META, "rows": [{"k": 1}], "limitations": [{"id": f"{section}-1", "text": "Small.", "severity": "medium"}]})
    rep = build([section], root=tmp_path)
    assert "status" not in rep["sections"][section] and rep["sections"][section]["rows"] == [{"k": 1}] and schema_errors(rep) == []
    assert f"{section}-1" in {e["id"] for e in rep["sections"]["limitations"]}


def test_a_result_file_that_is_not_an_object_is_failed(tmp_path):
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "modelbench.json").write_text("[1, 2]")
    assert build(["modelbench"], root=tmp_path)["sections"]["modelbench"]["status"] == "failed"


@pytest.mark.parametrize("section,dirname,fn_name", [("study_roles", "study_roles", "study_roles_section")])       # agentic reads recorded files (test_merge.py)
def test_directory_sections_pending_then_from_a_function_then_from_a_file(evals, section, dirname, fn_name):
    s = build([section])["sections"][section]
    assert s["status"] == "pending" and "does not exist yet" in s["reason"]
    d = evals / dirname
    d.mkdir()
    s = build([section])["sections"][section]
    assert s["status"] == "pending" and "has none of" in s["reason"]
    (d / "summary.json").write_text(json.dumps({"meta": META, "rows": [1]}))
    s = build([section])["sections"][section]
    assert "status" not in s and s["rows"] == [1]
    (d / "__init__.py").write_text(f"def {fn_name}():\n    return {{'meta': {json.dumps(META)}, 'rows': [2]}}\n")
    s = build([section])["sections"][section]
    assert s["rows"] == [2]                                                    # the function wins over the file


def test_a_directory_package_whose_lazy_module_is_missing_is_pending(evals):
    d = evals / "study_roles"
    d.mkdir()
    (d / "__init__.py").write_text("def study_roles_section():\n    from .section import study_roles_section as f\n    return f()\n")
    s = build(["study_roles"])["sections"]["study_roles"]
    assert s["status"] == "pending" and "section.py does not exist yet" in s["reason"]


def _calls(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn))
    node = tree.body[0]
    body = node.body[1:] if ast.get_docstring(node) else node.body
    seen: set[str] = set()
    for b in body:
        for n in ast.walk(b):
            if isinstance(n, ast.Name):
                seen.add(n.id)
            elif isinstance(n, ast.Attribute):
                seen.add(n.attr)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                seen.add(n.value)
    return seen


def test_the_live_study_adapter_never_reads_any_of_the_simulated_or_role_study_sections():
    for fn in (adapters.study, adapters._study_analysis, adapters._load_analyzer):
        names = _calls(fn)
        assert not any(w in x for x in names for w in ("study_sim", "study_roles", "agentic", "modelbench")), fn.__name__


def test_the_live_study_stays_not_run_even_if_every_other_study_section_has_numbers(evals):
    d = evals / "study_roles"
    d.mkdir()
    (d / "summary.json").write_text(json.dumps({"meta": dict(META, origin="synthetic", n=12, n_unit="runs"), "rows": [1]}))
    rep = build(["study", "study_roles"])
    assert rep["sections"]["study"]["status"] == "not_run" and rep["sections"]["study_roles"]["meta"]["n"] == 12


# ------------------------------------------------------------------------------------------------------------ evidence map
@pytest.fixture()
def mapped(evals, monkeypatch):
    fake_module(monkeypatch, "understudy_engine.cue.evaluate", "evaluate_cue", lambda fast=False, **kw: {"meta": dict(META, n=31, n_unit="people", origin="mixed")})
    monkeypatch.setitem(sys.modules, "understudy_engine.mlv2.evaluate", None)
    d = evals / "study_sim"
    d.mkdir()
    (d / "__init__.py").write_text("def study_sim_section():\n    return {'label': 'x', 'n': 8, 'meta': {'origin': 'synthetic', 'n': 8, 'n_unit': 'silicon participants', 'split': 's', "
                                   "'interval_level': 0.95, 'note': None, 'generated_at': None}}\n")
    return build(["study", "cue", "mlv2", "study_sim"])


def test_evidence_map_has_one_row_per_section_with_origin_n_and_status(mapped):
    em = {e["section"]: e for e in mapped["evidence_map"]}
    assert set(em) == {"cue", "mlv2", "study", "study_sim"}
    assert (em["cue"]["status"], em["cue"]["origin"], em["cue"]["n"], em["cue"]["n_unit"]) == ("ok", "mixed", 31, "people")
    assert em["mlv2"]["status"] == "pending" and "mlv2 not landed" in em["mlv2"]["reason"]
    assert (em["study"]["status"], em["study"]["origin"], em["study"]["n"]) == ("not_run", "unknown", 4)
    assert "limitations" not in em and schema_errors(mapped) == []


def test_evidence_map_is_the_first_table_in_the_markdown_and_badges_every_origin(mapped):
    md = render(mapped)
    first = md.index("## Evidence map")
    assert first < md.index("## Live study")
    sec = md[first:md.index("\n## ", first + 5)]
    assert "4 sections: 2 with numbers, 1 pending, 1 not run, 0 failed" in sec
    rows = {x.split("|")[1].strip(): [c.strip() for c in x.split("|")[2:-1]] for x in sec.splitlines() if x.startswith("| ") and not x.startswith("| Section")}
    assert rows["Cue analysis"][:2] == ["[mixed]", "31 people"] and rows["Live study (n = 4)"][0] == "[unknown]" and rows["Live study (n = 4)"][1] == "4 people"
    assert rows["Models v2"][:2] == ["n/a", "n/a"] and rows["Models v2"][2].startswith("pending: mlv2 not landed")       # a pending section shows no origin badge
    assert rows["Simulated participants (language model), not people"][0] == "[synthetic]"


def test_the_evidence_map_row_for_the_simulated_study_keeps_its_label(mapped):
    row = next(e for e in mapped["evidence_map"] if e["section"] == "study_sim")
    assert row["status"] == "ok" and row["label"] == "simulated participants (language model), not people" and row["origin"] == "synthetic"
    assert "simulated participants (language model), not people" in render(mapped)[render(mapped).index("## Evidence map"):]


def test_evidence_map_is_deterministic_and_in_every_full_report(landed):
    assert [e["section"] for e in landed["evidence_map"]] == ["git", "proactive", "calendar", "localmodel"]
    assert all(e["status"] == "ok" and e["n"] > 0 for e in landed["evidence_map"])


def test_register_does_not_get_pending_entries_for_the_optional_newer_sections(monkeypatch):
    monkeypatch.setitem(sys.modules, "understudy_engine.mlv2.evaluate", None)
    ids = {e["id"] for e in build(["mlv2"])["sections"]["limitations"]}
    assert not [i for i in ids if "mlv2" in i]


def test_ctx_has_no_state_leak_between_owner_calls():
    assert Ctx().cache == {} and Ctx().fast is False
    assert lim.OWNER.get("git") == "git-analysis" and lim.OWNER.get("runtime") == "agent-runtime"
