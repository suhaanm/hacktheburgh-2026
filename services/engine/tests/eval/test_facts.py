"""evals/report.facts.json: headline counts read from the report, for docs to quote by key; and no 'None' in the markdown."""
from __future__ import annotations

import json

import pytest
from understudy_engine.eval import adapters, build_report
from understudy_engine.eval.__main__ import main
from understudy_engine.eval.facts import build_facts, count_tests
from understudy_engine.eval.render_md import render, usd

NOW = "2026-11-07T15:00:00Z"


@pytest.fixture(scope="module")
def report(synthetic_data):
    return build_report(sections=["deficit_recovery", "null_placebo", "ski_rental", "agent_claims", "redteam", "study"], fast=True, now=NOW, regenerate=False, log=lambda m: None)


def test_facts_count_sections_and_limitations_from_the_report(report):
    f = build_facts(report, tests=False)
    emap = report["evidence_map"]
    assert f["sections"]["total"] == len(emap) == 6 and f["sections"]["ok"] == sum(1 for e in emap if e["status"] == "ok")
    assert f["sections"]["not_run"] == 1 and f["sections"]["not_run_names"] == ["study"]
    lim = report["sections"]["limitations"]
    assert f["limitations"]["total"] == len(lim) and f["limitations"]["high"] == sum(1 for e in lim if e["severity"] == "high")
    assert f["limitations"]["high"] + f["limitations"]["medium"] + f["limitations"]["low"] == len(lim)
    assert f["study"] == {"status": "not_run", "n": 4, "origin": "unknown"} and f["fast"] is True and f["generated_at"] == NOW


def test_facts_quote_the_red_team_counts_from_its_own_rows(report):
    rt = report["sections"]["redteam"]
    f = build_facts(report, tests=False)["redteam"]
    assert f["attacks"] == rt["rows"][0]["n"] and f["clean_cases"] == rt["false_pause"]["n"] and f["configurations"] == len(rt["rows"])
    assert f["attack_success_all_off"] == next(r for r in rt["rows"] if r["ablation"] == "all_off")["attack_success"]


def test_flat_has_every_scalar_under_a_dotted_key(report):
    f = build_facts(report, tests=False)
    flat = f["flat"]
    assert flat["sections.ok"] == f["sections"]["ok"] and flat["limitations.high"] == f["limitations"]["high"] and flat["redteam.attacks"] == f["redteam"]["attacks"]
    assert all(not isinstance(v, (list, dict)) for v in flat.values())


def test_a_failed_privacy_section_is_in_the_facts_with_its_reason(report):
    r = json.loads(json.dumps(report))
    r["sections"]["privacy"] = {"status": "failed", "reason": "the privacy layer's static guard found 2 violation(s)", "meta": {}}
    r["evidence_map"].append({"section": "privacy", "title": "p", "status": "failed", "origin": "synthetic", "n": None, "n_unit": None})
    f = build_facts(r, tests=False)
    assert f["privacy"]["status"] == "failed" and "violation" in f["privacy"]["reason"] and f["sections"]["failed_names"] == ["privacy"]


def test_test_counts_are_a_static_count_per_layer(tmp_path):
    t = tmp_path / "services" / "engine" / "tests" / "layer_a"
    t.mkdir(parents=True)
    (t / "test_x.py").write_text("def test_one():\n    pass\n\nasync def test_two():\n    pass\n\ndef helper():\n    pass\n")
    (tmp_path / "services" / "engine" / "tests" / "test_top.py").write_text("def test_t():\n    pass\n")
    d = tmp_path / "apps" / "dashboard" / "src"
    d.mkdir(parents=True)
    (d / "a.test.ts").write_text("describe('x', () => {\n  it('a', () => {})\n  test('b', () => {})\n  it.each([1])('c', () => {})\n})\n")
    c = count_tests(tmp_path)
    assert c["by_dir"] == {"apps/dashboard/src": 3, "engine/(top level)": 1, "engine/layer_a": 2} and c["total"] == 6 and "parametrised" in c["counting"]


def test_real_tree_test_counts_are_plausible_and_deterministic():
    a, b = count_tests(), count_tests()
    assert a == b and a["by_dir"].get("engine/eval", 0) > 100 and a["total"] > a["by_dir"]["engine/eval"]


def test_the_cli_writes_the_facts_file_beside_the_report_and_no_facts_skips_it(synthetic_data, tmp_path):
    out = tmp_path / "report.json"
    assert main(["--fast", "--no-generate", "--sections", "ski_rental,study", "--out", str(out)]) == 0
    facts = json.loads((tmp_path / "report.facts.json").read_text())
    assert facts["sections"]["total"] == 2 and facts["flat"]["sections.ok"] == 1 and facts["tests"]["total"] > 0 and facts["partial"] is True
    (tmp_path / "report.facts.json").unlink()
    assert main(["--fast", "--no-generate", "--no-facts", "--sections", "study", "--out", str(out)]) == 0
    assert not (tmp_path / "report.facts.json").exists()


# --------------------------------------------------------------------------------------------- never the word None in the markdown
def test_usd_says_not_measured_for_an_unknown_cost():
    assert usd(None) == "not measured" and usd(4.56) == "about 4.56 USD"


def _live_raw_without_cumulative():
    cond = {"n": 20, "code_check_ok": 18, "success_rate": 0.9, "wilson_95": [0.7, 0.97], "claimed_success": 18, "false_claims": 0, "paused": 0,
            "injection": {"runs_with_injected_site": 0, "detected": 0, "attack_success": 0}, "tiers_seen": [2], "mean_steps": 55.0, "mean_latency_s": 15.6, "failure_reasons": []}
    return {"meta": {"origin": "synthetic", "n": 20, "households": 20, "price_assumption_usd_per_million": {"input": 5.0, "output": 30.0}, "note": "n"},
            "cost": {"estimated_usd": 0.05}, "summary_by_variant": {"v1": {"clean": cond, "layout_v2": cond, "glitch": cond, "injected": cond}}, "runs": [], "tier3_simulated": {"runs": []}}


def test_an_unmeasured_live_cost_is_rendered_as_not_measured_not_none(tmp_path):
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "agent_benefits_20.json").write_text(json.dumps({
        "meta": {"origin": "synthetic", "n": 1}, "pass_rate": {"passed": 1, "n": 1, "wilson_95": [0.2, 1.0]}, "check_pass_counts": {"no_false_claims": 1},
        "flagged_discrepancies": {"count": 0}, "tiers_seen": [1], "mean_elapsed_s": 1.0, "rows": []}))
    (tmp_path / "eval" / "agent_live_runs.json").write_text(json.dumps(_live_raw_without_cumulative()))
    rep = build_report(sections=["agent_runs"], root=tmp_path, now=NOW, regenerate=False, log=lambda m: None)
    md = render(rep)
    assert _none_artefacts(md) == [] and "not measured" in md
    reg = {e["id"]: e for e in rep["sections"]["limitations"]}
    assert "None" not in reg["eval-agent-live-cost"]["text"] and "None" not in reg["eval-agent-live-tier3"]["text"] and "unrecorded" in reg["eval-agent-live-tier3"]["text"]


def test_the_renamed_cumulative_cost_keys_are_read(tmp_path):
    raw = _live_raw_without_cumulative()
    raw["cost"]["cumulative_rows_in_this_file"] = {"tokens_in": 1000, "tokens_out": 100, "usd_at_placeholder_rates_5_and_30_per_million": 4.56, "usd_at_mini_class_rates_0.75_and_4.50_per_million": 0.68}
    raw["cost"]["not_in_the_rows_above"] = "a smoke run"
    lv = adapters._live_block(raw)
    assert lv["cost_usd_est"] == 4.56 and lv["cost"]["usd_estimates"]["usd_at_mini_class_rates_0.75_and_4.50_per_million"] == 0.68 and lv["cost"]["note"] == "a smoke run"


def _none_artefacts(md: str) -> list[str]:
    """The bare word None or nan in the report body (the register is the owners' prose and may use the words)."""
    import re

    body = md[:md.index("## Limitations register")]
    return [m.group(0) for m in re.finditer(r".{0,30}(?<![A-Za-z])(?:None|nan|NaN)(?![A-Za-z]).{0,20}", body)]


def test_no_none_or_nan_in_the_markdown_of_the_landed_owner_sections():
    rep = build_report(sections=["proactive", "calendar"], fast=True, now=NOW, regenerate=False, log=lambda m: None)
    assert _none_artefacts(render(rep)) == []


def test_no_none_in_the_markdown_when_the_live_file_lacks_numbers(tmp_path):
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "agent_benefits_20.json").write_text(json.dumps({
        "meta": {"origin": "synthetic", "n": 1}, "pass_rate": {"passed": 1, "n": 1, "wilson_95": [0.2, 1.0]}, "check_pass_counts": {"no_false_claims": 1},
        "flagged_discrepancies": {"count": 0}, "tiers_seen": [1], "mean_elapsed_s": 1.0, "rows": []}))
    (tmp_path / "eval" / "agent_live_runs.json").write_text(json.dumps(_live_raw_without_cumulative()))
    md = render(build_report(sections=["agent_runs"], root=tmp_path, now=NOW, regenerate=False, log=lambda m: None))
    assert _none_artefacts(md) == []


# ------------------------------------------------------------------------------------------------ the dashboard fixture copy
def test_trim_keeps_contract_keys_stubs_map_and_register_and_validates(report):
    from understudy_engine.eval import schema_errors
    from understudy_engine.eval.fixture import dumps_min, trim

    t = trim(report)
    assert schema_errors(t) == [] and set(t["sections"]) == set(report["sections"]) - {"skills", "forecast", "policy_gate"}
    assert t["evidence_map"] == report["evidence_map"] and t["sections"]["limitations"] == report["sections"]["limitations"]
    assert t["sections"]["study"] == report["sections"]["study"]                              # stubs are untouched
    assert "by_category" not in t["sections"]["redteam"] and "rows" in t["sections"]["redteam"]
    assert "\n" not in dumps_min(t).strip() and len(dumps_min(t)) < len(json.dumps(report))


def test_the_cli_writes_the_fixture_only_when_asked(synthetic_data, tmp_path):
    out, fx = tmp_path / "report.json", tmp_path / "fx" / "eval-report.json"
    assert main(["--fast", "--no-generate", "--no-md", "--sections", "ski_rental,study", "--out", str(out)]) == 0 and not fx.exists()
    assert main(["--fast", "--no-generate", "--no-md", "--sections", "ski_rental,study", "--out", str(out), "--fixture", str(fx)]) == 0
    assert json.loads(fx.read_text())["sections"]["study"]["status"] == "not_run"


def test_the_privacy_block_keeps_the_keys_the_evidence_page_reads_in_the_report_and_in_the_fixture_copy():
    """The Evidence page's per-layer table reads ``layers`` (at least 5 rows) and its privacy block reads coverage, image, the two scan rates and the vocabulary check."""
    from understudy_engine.eval import schema_errors
    from understudy_engine.eval.fixture import PRIVACY_FIXTURE_KEYS, trim

    rep = build_report(sections=["privacy"], fast=True, now=NOW, regenerate=False, log=lambda m: None)
    p = rep["sections"]["privacy"]
    assert "status" not in p, p
    six = ("layers", "coverage", "image", "scan_sensitivity", "scan_specificity", "vocabulary_problems")
    assert all(k in p for k in six) and len(p["layers"]) >= 5
    t = trim(rep)["sections"]["privacy"]
    assert schema_errors(trim(rep)) == [] and set(PRIVACY_FIXTURE_KEYS) <= set(t) and all(k in t for k in six) and len(t["layers"]) == len(p["layers"])
    assert t["headline"] == p["headline"] and t["by_kind"] == p["by_kind"]
    assert not {"flows", "bucketing", "backstop", "static_guard", "ledger", "negative_controls"} & set(t)         # the bulk stays out of the bundle
