"""study_sim (language-model participants) and study_power (what the n = 4 design could detect): both optional, both pending until their owners land.

HARD RULES under test: `study` stays the live humans only and is never fed from `study_sim`; every study_sim text says
"simulated participants (language model), not people"; the study_sim origin is always synthetic.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
import types

import pytest
from understudy_engine.eval import adapters, build_report, schema_errors
from understudy_engine.eval.render_md import render

PHRASE = "simulated participants (language model), not people"
NOW = "2026-11-07T15:00:00Z"

SIM_SRC = '''
def study_sim_section():
    return {
        "label": "Simulated participants (LLM)",
        "n": 8, "n_aa": 4,
        "headline": {"mean_difference": 0.25, "ci95": [-0.1, 0.6]},
        "per_skill": [{"skill": "cliff", "coached": 0.9, "uncoached": 0.5}, {"skill": "reconcile", "coached": 0.8, "uncoached": 0.6}],
        "aa": {"mean_difference": 0.02}, "effort": {"turns": 12.5}, "nudges": {"shown": 6},
        "pipeline_checks": {"all_passed": True}, "cost": {"usd": 1.25},
        "limitations": [{"id": "sim-owner-note", "text": "The prompts are ours.", "severity": "medium"}],
        "caveats": ["Participants share one model."],
        "meta": {"origin": "real", "n": 8, "n_unit": "runs", "split": "2 skills x 2 orders x 2 repeats", "interval_level": 0.95, "note": "owner note", "generated_at": "x"},
    }
'''


@pytest.fixture()
def evals(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "evals_out_dir", lambda: tmp_path / "evals")
    (tmp_path / "evals").mkdir()
    return tmp_path / "evals"


def put_sim(evals, src=SIM_SRC):
    d = evals / "study_sim"
    d.mkdir(exist_ok=True)
    (d / "__init__.py").write_text(src)


def fake_rows():
    rows = []
    power = {(4, "none"): 0.017, (4, "small"): 0.024, (4, "medium"): 0.044, (4, "large"): 0.116, (16, "none"): 0.049, (16, "small"): 0.102, (16, "medium"): 0.273, (16, "large"): 0.748}
    eff = {"none": 0.0, "small": 10.2, "medium": 20.6, "large": 38.8}
    for n in (4, 16):
        for e in ("none", "small", "medium", "large"):
            for carry, order in ((0.0, 0.0), (0.0, -0.7), (1.0, 0.0), (1.0, -0.7)):
                p = power[(n, e)] * (0.5 if carry else 1.0)
                rows.append({"n": n, "effect_label": e, "true_effect_pp": eff[e], "carryover": carry, "order_effect": order, "power_ci": p, "power_p05": 0.0 if n == 4 else p / 2,
                             "bias_pp": -10.4 if carry else 0.1, "bias": -0.1, "coverage": 0.94, "false_positive": 0.04 if e == "none" else None})
    return rows


def fake_power(monkeypatch, record):
    mod = types.ModuleType("understudy_engine.study_power")

    def evaluate_study_power(fast=False):
        record.append(fast)
        return {"rows": fake_rows(), "min_p_by_n": {"4": 0.125, "16": 3.0517578125e-05}, "needed_difference_n4": {"reading": "Only a very large effect, seen in every participant, can show."},
                "note": "Design properties under our assumptions.", "caveats": ["Every number depends on invented assumptions."],
                "limitations": [{"id": "power-assumed-sd", "text": "The noise level is assumed.", "severity": "medium"}],
                "meta": {"origin": "synthetic", "n": 2000, "n_unit": "replications", "split": "simulated studies", "interval_level": 0.95, "note": None, "generated_at": "x"}}

    mod.evaluate_study_power = evaluate_study_power
    monkeypatch.setitem(sys.modules, "understudy_engine.study_power", mod)


def build(sections):
    return build_report(sections=sections, now=NOW, regenerate=False, log=lambda m: None)


# ------------------------------------------------------------------------------------------------------- pending stubs
def test_both_are_pending_stubs_until_their_owners_land(evals, monkeypatch):
    monkeypatch.setitem(sys.modules, "understudy_engine.study_power", None)           # as if the module did not exist yet
    rep = build(["study_sim", "study_power"])
    assert rep["sections"]["study_sim"]["status"] == "pending" and "study-sim not landed" in rep["sections"]["study_sim"]["reason"]
    assert rep["sections"]["study_power"]["status"] == "pending" and "engine-analytics not landed" in rep["sections"]["study_power"]["reason"]
    assert schema_errors(rep) == []


def test_a_study_power_package_without_the_entry_point_is_still_pending(evals, monkeypatch):
    monkeypatch.setitem(sys.modules, "understudy_engine.study_power", types.ModuleType("understudy_engine.study_power"))
    s = build(["study_power"])["sections"]["study_power"]
    assert s["status"] == "pending" and "evaluate_study_power missing" in s["reason"]


def test_study_sim_missing_directory_or_function_is_pending(evals):
    s = build(["study_sim"])["sections"]["study_sim"]
    assert s["status"] == "pending" and "does not exist yet" in s["reason"]
    put_sim(evals, "x = 1\n")
    s = build(["study_sim"])["sections"]["study_sim"]
    assert s["status"] == "pending" and "no study_sim_section()" in s["reason"]


def test_a_study_sim_that_raises_is_failed_not_hidden(evals):
    put_sim(evals, "def study_sim_section():\n    raise RuntimeError('model call failed')\n")
    s = build(["study_sim"])["sections"]["study_sim"]
    assert s["status"] == "failed" and "model call failed" in s["reason"]


# -------------------------------------------------------------------------------------------------------- study_sim
@pytest.fixture()
def sim_report(evals):
    put_sim(evals)
    return build(["study_sim"])


def test_study_sim_is_labelled_forced_synthetic_and_validates(sim_report):
    s = sim_report["sections"]["study_sim"]
    assert "status" not in s and s["label"] == PHRASE and s["owner_label"] == "Simulated participants (LLM)"
    assert s["meta"]["origin"] == "synthetic"                      # the owner said "real"; it is never allowed to be
    assert PHRASE in s["meta"]["note"].lower() and "owner note" in s["meta"]["note"]
    assert s["n"] == 8 and s["n_aa"] == 4
    assert schema_errors(sim_report) == []


def test_every_study_sim_text_in_the_register_says_what_it_is(sim_report):
    lims = sim_report["sections"]["limitations"]
    sim = [e for e in lims if e["source"].startswith(("engine-eval:study_sim", "study-sim"))]
    ids = {e["id"] for e in sim}
    assert {"eval-study-sim-not-human", "eval-study-sim-planted-by-us", "eval-study-sim-learning-proxy", "eval-study-sim-timing", "sim-owner-note"} <= ids
    for e in sim:
        assert PHRASE in e["text"].lower(), e["id"]
    for i in ("eval-study-sim-not-human", "eval-study-sim-planted-by-us", "eval-study-sim-learning-proxy", "eval-study-sim-timing"):
        assert next(e for e in lims if e["id"] == i)["severity"] == "high"
    assert "language model plays each participant" in next(e for e in lims if e["id"] == "eval-study-sim-not-human")["text"]
    assert "proxy" in next(e for e in lims if e["id"] == "eval-study-sim-learning-proxy")["text"]
    assert "not human" in next(e for e in lims if e["id"] == "eval-study-sim-timing")["text"]


def test_no_study_sim_register_entries_when_the_section_has_no_numbers(evals):
    rep = build(["study_sim"])
    assert not [e for e in rep["sections"]["limitations"] if "study-sim" in e["id"]]


def test_every_study_sim_paragraph_and_table_in_the_markdown_says_what_it_is(sim_report):
    md = render(sim_report)
    sec = md[md.index("## Simulated participants (language model), not people"):md.index("## Limitations register")]
    assert PHRASE in sec.split("\n\n")[0].lower() or PHRASE in sec.lower()
    blocks = [b for b in sec.split("\n\n") if b.strip()]
    for b in blocks:
        if b.startswith("|"):
            continue                                            # a table is captioned by the block above it
        assert PHRASE in b.lower(), b
    # each table is preceded by a caption that says it
    parts = sec.split("\n\n")
    for k, b in enumerate(parts):
        if b.startswith("| "):
            assert PHRASE in parts[k - 1].lower(), parts[k - 1]
    assert "not the live study" in sec and "never combined" in sec
    assert "Participants share one model" in sec and sec.lower().count(PHRASE) >= 4


def test_study_sim_pending_text_in_markdown_still_says_it_is_not_people(evals):
    md = render(build(["study_sim"]))
    sec = md[md.index("## Simulated participants (language model), not people"):md.index("## Limitations register")]
    assert PHRASE in sec.lower() and "PENDING" in sec


# ----------------------------------------------------------------------------------------- study is live humans only
def _names_and_strings(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn))
    fn_node = tree.body[0]
    body = fn_node.body[1:] if ast.get_docstring(fn_node) else fn_node.body        # skip the docstring itself
    seen: set[str] = set()
    for node in body:
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                seen.add(n.id)
            elif isinstance(n, ast.Attribute):
                seen.add(n.attr)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                seen.add(n.value)
    return seen


def test_the_study_adapter_never_touches_study_sim_even_when_it_exists(evals):
    for fn in (adapters.study, adapters._study_analysis, adapters._load_analyzer):
        assert not any("study_sim" in x for x in _names_and_strings(fn)), fn.__name__
    put_sim(evals)
    rep = build(["study", "study_sim"])
    assert rep["sections"]["study"]["status"] == "not_run" and rep["sections"]["study"]["rows"] == [] and rep["sections"]["study"]["n"] == 4
    assert rep["sections"]["study"]["meta"]["origin"] == "real"
    assert rep["sections"]["study_sim"]["meta"]["origin"] == "synthetic"


def test_results_not_marked_real_are_never_shown_as_the_live_study(evals):
    d = evals / "study" / "results"
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps({"meta": {"origin": "synthetic", "n": 8, "n_unit": "runs"}, "headline_unassisted": {"blocks": [
        {"participant": "S1", "condition": "coached", "skill": "cliff", "post_score": 1.0, "post_seconds": 10, "practice_seconds": 10, "post_capped": False, "practice_capped": False},
        {"participant": "S1", "condition": "uncoached", "skill": "reconcile", "post_score": 0.0, "post_seconds": 10, "practice_seconds": 10, "post_capped": False, "practice_capped": False}]}}))
    s = build(["study"])["sections"]["study"]
    assert s["status"] == "not_run"


def test_schema_refuses_a_synthetic_or_simulated_origin_as_the_live_study():
    meta = {"origin": "synthetic", "n": 4, "n_unit": "people", "split": "x", "interval_level": 0.95, "note": None, "generated_at": NOW}
    row = {"participant": "P1", "unassisted_before_s": 1.0, "unassisted_after_s": 2.0}
    rep = {"generated_at": NOW, "mock": True, "sections": {"study": {"meta": meta, "rows": [row], "mean_change_s": 1.0, "mean_change_ci": [0.0, 2.0], "n": 1}}}
    assert any("real" in e for e in schema_errors(rep))
    rep["sections"]["study"]["meta"] = dict(meta, origin="real")
    assert schema_errors(rep) == []


def test_schema_guards_study_sim_label_and_origin_and_keeps_it_optional():
    meta = {"origin": "synthetic", "n": 8, "n_unit": "runs", "split": "x", "interval_level": 0.95, "note": PHRASE, "generated_at": NOW}
    ok = {"generated_at": NOW, "mock": True, "sections": {"study_sim": {"meta": meta, "label": PHRASE}}}
    assert schema_errors(ok) == []
    assert schema_errors({"generated_at": NOW, "mock": True, "sections": {}}) == []                         # optional
    bad_label = {"generated_at": NOW, "mock": True, "sections": {"study_sim": {"meta": meta, "label": "participants"}}}
    assert any(PHRASE in e or "label" in e for e in schema_errors(bad_label))
    bad_origin = {"generated_at": NOW, "mock": True, "sections": {"study_sim": {"meta": dict(meta, origin="real"), "label": PHRASE}}}
    assert any("synthetic" in e for e in schema_errors(bad_origin))
    assert any("label" in e for e in schema_errors({"generated_at": NOW, "mock": True, "sections": {"study_sim": {"meta": meta}}}))


# ------------------------------------------------------------------------------------------------------- study_power
def test_study_power_is_wired_passes_fast_through_and_validates(evals, monkeypatch):
    calls: list[bool] = []
    fake_power(monkeypatch, calls)
    full = build(["study_power"])
    fast = build_report(sections=["study_power"], fast=True, now=NOW, regenerate=False, log=lambda m: None)
    assert calls == [False, True]
    s = full["sections"]["study_power"]
    assert "status" not in s and s["rows"][0]["n"] == 4 and s["min_p_by_n"]["4"] == 0.125 and s["meta"]["generated_at"] == NOW
    assert s["headline_power"]["4"]["p05_impossible"] is True and s["headline_power"]["16"]["p05_impossible"] is False
    assert schema_errors(full) == [] and schema_errors(fast) == []


def test_study_power_register_entry_says_it_is_about_the_design_only(evals, monkeypatch):
    fake_power(monkeypatch, [])
    lims = build(["study_power"])["sections"]["limitations"]
    e = next(e for e in lims if e["id"] == "eval-study-power-assumptions")
    assert e["severity"] == "high" and "could detect under our own assumptions" in e["text"] and "not a result about people" in e["text"]
    assert any(x["id"] == "power-assumed-sd" for x in lims)                    # the owner's own entry is kept
    assert not [x for x in lims if "study-sim" in x["id"]]


def test_study_power_markdown_is_a_design_table_not_a_result(evals, monkeypatch):
    fake_power(monkeypatch, [])
    md = render(build(["study_power"]))
    sec = md[md.index("## Study power"):md.index("## Limitations register")]
    assert "A property of the design, not a result about people" in sec and "origin: **synthetic**" in sec
    assert "smallest attainable two-sided sign-flip p is 0.125, so p < 0.05 is impossible" in sec
    assert "| none | 0.0 | 1.7% | 4.9% |" in sec and "| small | 10.2 | 2.4% | 10.2% |" in sec and "| medium | 20.6 | 4.4% | 27.3% |" in sec and "| large | 38.8 | 11.6% | 74.8% |" in sec
    assert "Spill-over of the coached gain onto the other skill is not protected by the design" in sec


def test_both_sections_are_in_the_section_list_and_optional():
    assert "study_sim" in adapters.SECTION_NAMES and "study_power" in adapters.SECTION_NAMES
    props = json.loads(adapters.__file__.replace("adapters.py", "report.schema.json") and open(adapters.__file__.replace("adapters.py", "report.schema.json")).read())
    assert "study_sim" in props["properties"]["sections"]["properties"] and "study_power" in props["properties"]["sections"]["properties"]
    assert "study_sim" not in props["properties"]["sections"].get("required", []) and "study_power" not in props["properties"]["sections"].get("required", [])


def test_a_study_sim_package_whose_section_module_is_not_written_yet_is_pending_not_failed(evals):
    put_sim(evals, "def study_sim_section():\n    from .section import study_sim_section as f\n    return f()\n")
    s = build(["study_sim"])["sections"]["study_sim"]
    assert s["status"] == "pending" and "section.py does not exist yet" in s["reason"]


def test_a_study_sim_package_that_imports_siblings_by_absolute_path_loads(evals):
    d = evals / "study_sim"
    d.mkdir()
    (d / "__init__.py").write_text("def study_sim_section():\n    from evals.study_sim.helper import value\n    return {'meta': {'origin': 'synthetic', 'n': value(), 'n_unit': 'runs', 'split': 'x', 'interval_level': 0.95, 'note': None, 'generated_at': 'x'}}\n")
    (d / "helper.py").write_text("def value():\n    return 3\n")
    # the repo's own `evals` namespace may already be cached; this run uses the temporary one through sys.path
    for k in [k for k in sys.modules if k == "evals" or k.startswith("evals.")]:
        monkeypatch_sys = sys.modules.pop(k)
        del monkeypatch_sys
    s = build(["study_sim"])["sections"]["study_sim"]
    assert s.get("status") is None and s["meta"]["n"] == 3 and s["label"] == PHRASE


def test_the_real_study_power_matches_the_plain_numbers_in_the_markdown():
    from understudy_engine.eval.adapters import Ctx, study_power

    s = study_power(Ctx(fast=True))
    rep = {"generated_at": NOW, "mock": True, "sections": {"study_power": json.loads(json.dumps(s))}}
    rep["sections"]["study_power"]["meta"]["generated_at"] = NOW
    assert schema_errors(rep) == []
    md = render(rep)
    sec = md[md.index("## Study power"):md.index("## Limitations register")]
    h = s["headline_power"]
    for e in ("none", "small", "medium", "large"):
        p4, p16 = h["4"]["power_ci"][e], h["16"]["power_ci"][e]
        assert f"{100 * p4:.1f}% | {100 * p16:.1f}%" in sec, e
    assert h["4"]["min_sign_flip_p"] == 0.125 and h["4"]["p05_impossible"] is True
    assert "p < 0.05 is impossible" in sec and "not protected by the design" in sec
    for row in s["rows"]:                                     # the headline cells are the grid's own cells, not retyped numbers
        if row["n"] == 4 and row["carryover"] == 0 and row["order_effect"] == 0:
            assert h["4"]["power_ci"][row["effect_label"]] == row["power_ci"]
