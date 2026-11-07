"""Pure parts of the bake-off: statistics, budget guard, cache, runner (fake calls), case building, analysis, report. No network."""
from __future__ import annotations

import json
import math

import pytest

from evals.modelbench import analyze, cases as cm, report, stats
from evals.modelbench.budget import SAFETY_FACTOR, Budget
from evals.modelbench.cache import ResultCache, make_key
from evals.modelbench.contenders import Contender, Out
from evals.modelbench.runner import Job, Runner, key_for


# ------------------------------------------------------------------------------------------------ stats
def test_wilson_matches_the_engine_helper_and_edges():
    from understudy_engine.trust.stats import wilson_interval

    for k, n in [(0, 10), (10, 10), (7, 10), (59, 60), (1, 3)]:
        a, b = stats.wilson(k, n), wilson_interval(k, n)
        assert a[0] == pytest.approx(b[0]) and a[1] == pytest.approx(b[1])
    assert stats.wilson(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        stats.wilson(5, 3)
    r = stats.rate(6, 7)
    assert r["k"] == 6 and r["n"] == 7 and r["lo"] < 6 / 7 < r["hi"]


def test_percentile_bootstrap_is_seeded_and_ordered():
    vals = [float(x) for x in range(1, 101)]
    assert stats.percentile(vals, 50) == 50 and stats.percentile(vals, 95) == 95 and stats.percentile([], 50) is None
    s1, s2 = stats.summarize(vals), stats.summarize(vals)
    assert s1 == s2 and s1["p50_ci"][0] <= 50 <= s1["p50_ci"][1] and s1["n"] == 100
    assert stats.bootstrap_ci([1.0], lambda v: v[0]) is None


def test_iou_and_point_in_box():
    assert stats.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert stats.iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert stats.iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert stats.point_in_box(5, 5, [0, 0, 10, 10]) and not stats.point_in_box(11, 5, [0, 0, 10, 10])


def test_paired_diff_and_mcnemar():
    a = [1] * 20 + [0] * 5
    b = [1] * 10 + [0] * 15
    d = stats.paired_diff(a, b)
    assert d["only_a"] == 10 and d["only_b"] == 0 and d["diff"] == pytest.approx(0.4) and d["mcnemar_p"] < 0.01
    same = stats.paired_diff(a, a)
    assert same["diff"] == 0 and same["mcnemar_p"] == 1.0
    assert math.isclose(stats.paired_diff([1, 0], [0, 1])["mcnemar_p"], 1.0)


# ------------------------------------------------------------------------------------------------ budget and cache
def test_budget_guard_stops_and_resumes_across_runs(tmp_path):
    p = tmp_path / "spend.jsonl"
    b = Budget(1.0, p)
    assert b.allow(0.01)
    b.add(0.5, contender="x", kind="k")
    assert b.guarded_spent() == pytest.approx((0.06 + 0.5) * SAFETY_FACTOR)
    assert not b.allow(0.5)                                   # (0.56 + 0.5) * 1.25 > 1.0
    b.drop({"cell": "c1"})
    b2 = Budget(1.0, p)                                       # a new run reads the ledger
    assert b2.spent == pytest.approx(0.56) and b2.summary()["n_dropped"] == 0
    assert json.loads(p.read_text().splitlines()[0])["usd"] == 0.5


def test_cache_key_has_no_content_and_failures_retry_once(tmp_path):
    k = make_key(kind="point_desc", contender="gemini_fast", model="m", api="interactions", prompt="the secret button", image_sha="abc", schema_name="s")
    assert "secret" not in k and len(k) == 40
    c = ResultCache(tmp_path / "r.jsonl", max_attempts=2)
    c.put(k, {"ok": False, "error_kind": "timeout"})
    assert c.get(k) is None and c.attempts(k) == 1            # one failure: retried on the next run
    c.put(k, {"ok": False, "error_kind": "timeout"})
    assert c.get(k) is not None                               # two failures: stop retrying
    k2 = make_key(kind="a", contender="c", model="m", api="i", prompt="p", image_sha="s", schema_name="s")
    c.put(k2, {"ok": True})
    assert ResultCache(tmp_path / "r.jsonl").get(k2)["ok"] is True      # reloaded from disk


def test_cache_key_changes_with_model_prompt_image_and_repeat():
    base = dict(kind="point_desc", contender="c", model="m1", api="interactions", prompt="p", image_sha="i", schema_name="s")
    keys = {make_key(**base), make_key(**{**base, "model": "m2"}), make_key(**{**base, "prompt": "q"}),
            make_key(**{**base, "image_sha": "j"}), make_key(**{**base, "rep": 1}), make_key(**{**base, "api": "generate_content"})}
    assert len(keys) == 6


# ------------------------------------------------------------------------------------------------ runner
def fake_runner(tmp_path, cap=3.0, calls=None):
    shots = tmp_path / "shots"
    shots.mkdir(exist_ok=True)
    from understudy_agent.models.imaging import make_test_png

    (shots / "a.png").write_bytes(make_test_png(640, 400))
    seen = calls if calls is not None else []

    def fn(c, j, jpeg):
        seen.append((c.name, j.case_id))
        return Out(True, None, 100, 1000, 40, 0, 0.001, {"found": True, "confidence": 0.9, "box_2d": [10, 10, 60, 90]})

    return Runner(shots, ResultCache(tmp_path / "r.jsonl"), Budget(cap, tmp_path / "s.jsonl"), log=lambda s: None, call_fn=fn), seen


def test_runner_is_resumable_and_never_repeats_a_call(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_FAST", "m-fast")
    jobs = [Job("point_desc", f"c{i}", "a.png", "sha", desc=f"d{i}") for i in range(4)]
    r, seen = fake_runner(tmp_path)
    c = Contender("gemini_fast")
    r.run([c], jobs)
    assert len(seen) == 4 and r.counts["live"] == 4
    r2, seen2 = fake_runner(tmp_path)
    r2.run([c], jobs)
    assert seen2 == [] and r2.counts["cached"] == 4              # a rerun makes no calls


def test_runner_stops_at_the_budget_and_records_dropped_cells(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_FAST", "m-fast")
    r, seen = fake_runner(tmp_path, cap=0.12)                    # 0.06 probes already counted; the guard counts 1.25x
    jobs = [Job("point_desc", f"c{i}", "a.png", "sha", desc=f"d{i}") for i in range(200)]
    r.run([Contender("gemini_fast")], jobs)
    assert 0 < len(seen) < 200 and r.counts["dropped"] == 200 - len(seen)
    assert r.budget.guarded_spent() <= 0.12 + 1e-9 and len(r.budget.dropped) == r.counts["dropped"]
    assert r.budget.dropped[0]["reason"] == "budget"


def test_job_key_depends_on_the_contenders_model(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_FAST", "a")
    j = Job("point_desc", "c", "a.png", "sha", desc="d")
    k1 = key_for(Contender("gemini_fast"), j)
    monkeypatch.setenv("GEMINI_MODEL_FAST", "b")
    assert key_for(Contender("gemini_fast"), j) != k1


# ------------------------------------------------------------------------------------------------ cases
def test_describe_and_unique_by_desc():
    assert cm.describe({"tag": "input", "label": "Your age"}) == ('the text box labelled "Your age"', "control")
    assert cm.describe({"tag": "button", "label": "Continue"})[1] == "button"
    assert cm.describe({"tag": "a", "label": ""}) is None
    items = [("d1", "control", [0, 0, 1, 1]), ("d2", "button", [0, 0, 1, 1]), ("d1", "control", [2, 2, 3, 3])]
    assert [i[0] for i in cm.unique_by_desc(items)] == ["d2"]


def test_negatives_are_kept_only_when_absent_from_the_page():
    blob = "check your answers. this page has a search box and a continue button"
    out = cm.negatives_for("a_step1", blob, [('the button labelled "Continue"', ("continue",)), ('the button labelled "Calculate"', ("calculate",))], "base", n_pool=3)
    descs = [d for d, _ in out]
    assert 'the button labelled "Calculate"' in descs and 'the button labelled "Continue"' not in descs
    assert "the search box in the page header" not in descs                      # 'search' is on the page
    assert [r for _, r in out].count("near_miss") == 1 and len([1 for _, r in out if r == "absent"]) == 3
    assert out == cm.negatives_for("a_step1", blob, [('the button labelled "Continue"', ("continue",)), ('the button labelled "Calculate"', ("calculate",))], "base", n_pool=3)


def make_cases() -> list[cm.Case]:
    out = []
    for cond in ("base", "v2", "injected", "dark"):
        for i in range(40):
            out.append(cm.Case(f"{cond}::{i:03d}", f"{cond}__s", "positive", f"d{i}", [0, 0, 10, 10], "button" if i < 6 else "control", cond, "a", "s"))
        for i in range(10):
            out.append(cm.Case(f"{cond}::n{i:03d}", f"{cond}__s", "negative", f"n{i}", None, "absent", cond, "a", "s"))
    return out


def test_sampling_is_seeded_stratified_and_complete_for_base():
    cases = make_cases()
    s1, s2 = cm.sample_cases(cases), cm.sample_cases(cases)
    assert [c.case_id for c in s1["v2"]] == [c.case_id for c in s2["v2"]]
    assert len(s1["base"]) == 50 and all(c.cond == "base" for c in s1["base"])
    for cond in ("v2", "injected", "dark"):
        pos = [c for c in s1[cond] if c.kind == "positive"]
        assert len(pos) == 24 and len([c for c in s1[cond] if c.kind == "negative"]) == 5
    assert all(any(c.role == "button" and c.case_id == x.case_id for x in s1["v2"]) for c in cases if c.cond == "v2" and c.role == "button")
    assert cm.sample_cases(cases, seed=1)["dark"] != s1["dark"]


def test_step_cases_cover_present_and_absent_steps():
    shots = [cm.Shot("base__a_step1", "a_step1", "a", "base", "v1", "clean", "light", "f.png", 1280, 800, "x", {"next": [1, 2, 3, 4]}),
             cm.Shot("dark__a_step1", "a_step1", "a", "dark", "v1", "clean", "dark_filter", "g.png", 1280, 800, "y", {"next": [1, 2, 3, 4]})]
    sc = cm.step_cases(shots)
    assert [c["step"] for c in sc if c["kind"] == "positive"] == ["next"] and len([c for c in sc if c["kind"] == "negative"]) == 1
    assert all(c["cond"] == "base" for c in sc)                                  # the dark condition is not part of the step cells


@pytest.mark.skipif(not __import__("shutil").which("python3"), reason="needs a Python")
def test_renderer_builds_site_b_truth_from_the_real_dom(tmp_path):
    """One real headless render (private ports): site B's form has 12 fields and a button; every positive box is inside the viewport."""
    pw = pytest.importorskip("playwright.sync_api")
    from understudy_agent.sandbox_sites.runner import SandboxCluster
    from understudy_agent.sandbox_sites.specs import SITES

    with SandboxCluster(ephemeral=True) as cluster, pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:  # browser not installed on this machine
            pytest.skip(f"no chromium: {type(e).__name__}")
        r = cm.Renderer(tmp_path, cluster.urls)
        ctx = browser.new_context(viewport={"width": cm.VIEW_W, "height": cm.VIEW_H}, device_scale_factor=1)
        page = ctx.new_page()
        shot = r._site_b(page, "base", SITES["b"], "v1")
        browser.close()
    assert shot is not None and shot.screen == "b_result"
    home = [c for c in r.cases if c.screen == "b_home" and c.kind == "positive"]
    assert len(home) == 13 and all(0 <= c.box[0] < c.box[2] <= cm.VIEW_W and 0 <= c.box[1] < c.box[3] <= cm.VIEW_H for c in home)
    assert any('labelled "Calculate"' in c.desc and c.role == "button" for c in home)
    assert any(c.kind == "negative" for c in r.cases if c.screen == "b_home")
    png = (tmp_path / "base__b_home.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------------------------------------------------------ analysis
SHOT = {"shot_id": "s", "width": 1280, "height": 800}


def row(contender, cid, value, *, ok=True, lat=1000, cost=0.001, kind="point_desc", rep=0, err=None):
    return {"kind": kind, "contender": contender, "case_id": cid, "rep": rep, "group": "", "ok": ok, "error_kind": err, "latency_ms": lat,
            "input_tokens": 1000, "output_tokens": 40, "thought_tokens": 10, "cost_usd": cost, "value": value}


def test_point_record_hit_iou_and_negatives():
    pos = {"case_id": "p", "kind": "positive", "box": [320, 160, 640, 240], "cond": "base", "site": "a", "role": "button"}
    hit = analyze.point_record(pos, SHOT, row("c", "p", {"found": True, "confidence": 0.9, "box_2d": [210, 260, 300, 500]}))
    assert hit["hit"] and hit["iou"] is not None and 0 < hit["iou"] < 1
    miss = analyze.point_record(pos, SHOT, row("c", "p", {"found": True, "confidence": 0.9, "box_2d": [700, 700, 800, 800]}))
    assert miss["found"] and not miss["hit"]
    nf = analyze.point_record(pos, SHOT, row("c", "p", {"found": False, "confidence": 0.9}))
    assert not nf["found"] and not nf["hit"]
    fail = analyze.point_record(pos, SHOT, row("c", "p", None, ok=False, err="timeout"))
    assert not fail["ok"] and not fail["hit"] and fail["error_kind"] == "timeout"
    over = analyze.point_record(pos, SHOT, row("c", "p", {"found": True, "confidence": 0.9, "box_2d": [0, 0, 950, 950]}))
    assert not over["found"] and over["reason"] == "oversize_box"
    neg = {"case_id": "n", "kind": "negative", "box": None, "cond": "base", "site": "a", "role": "absent"}
    assert analyze.point_record(neg, SHOT, row("c", "n", {"found": False, "confidence": 0.9}))["correct_negative"]
    assert not analyze.point_record(neg, SHOT, row("c", "n", {"found": True, "confidence": 0.9, "box_2d": [10, 10, 60, 90]}))["correct_negative"]
    assert not analyze.point_record(neg, SHOT, row("c", "n", None, ok=False, err="api"))["correct_negative"]   # a failure is not a correct negative


def rec(cid, *, hit, found=True, conf=0.9, lat=1000, ok=True, kind="positive", cost=0.001):
    return {"case_id": cid, "kind": kind, "cond": "base", "site": "a", "role": "control", "present": True, "ok": ok, "error_kind": None,
            "latency_ms": lat, "cost_usd": cost, "input_tokens": 1, "output_tokens": 1, "found": found, "reason": None,
            "confidence": conf, "hit": hit, "iou": 0.5 if found else None, "correct_negative": kind == "negative" and not found}


def test_routed_simulation_escalates_only_when_weak_and_respects_the_deadline():
    lite = {"a": rec("a", hit=True), "b": rec("b", hit=False, found=False), "c": rec("c", hit=False, conf=0.4),
            "d": rec("d", hit=True, lat=7000)}
    flash = {k: rec(k, hit=True, lat=3000, cost=0.003) for k in lite}
    sim = {r["case_id"]: r for r in analyze.routed_simulation(lite, flash, deadline=False)}
    assert not sim["a"]["escalated"] and sim["a"]["hit"] and sim["a"]["latency_ms"] == 1000
    assert sim["b"]["escalated"] and sim["b"]["hit"] and sim["b"]["latency_ms"] == 4000 and sim["b"]["cost_usd"] == pytest.approx(0.004)
    assert sim["c"]["escalated"] and sim["c"]["hit"]
    sim6 = {r["case_id"]: r for r in analyze.routed_simulation(lite, flash, deadline=True)}
    assert sim6["b"]["escalated"] and sim6["b"]["latency_ms"] == 4000
    assert not sim6["d"]["ok"] and sim6["d"]["error_kind"] == "timeout" and not sim6["d"]["hit"]      # lite alone took over 6 s
    slow = {"x": rec("x", hit=False, found=False, lat=4000)}
    fl = {"x": rec("x", hit=True, lat=3000)}
    assert not analyze.routed_simulation(slow, fl, deadline=True)[0]["escalated"]                       # 4 s + 3 s > 6 s: lite's answer stands
    assert analyze.routed_simulation(slow, fl, deadline=False)[0]["escalated"]


def test_agg_point_counts_failures_as_misses_and_reports_intervals():
    recs = [rec("1", hit=True), rec("2", hit=False), rec("3", hit=False, found=False, ok=False)] + [
        rec("n1", hit=False, found=False, kind="negative"), rec("n2", hit=False, found=True, kind="negative")]
    a = analyze.agg_point(recs)
    assert a["positives"]["hit"]["k"] == 1 and a["positives"]["hit"]["n"] == 3 and a["negatives"]["correct"]["k"] == 1
    assert a["negatives"]["false_positives"] == 1 and a["n_failed"] == 1
    assert a["latency_ms"]["n"] == 4 and 0 <= a["positives"]["hit"]["lo"] <= a["positives"]["hit"]["hi"] <= 1


def test_pointing_section_pairs_models_and_never_counts_uncalled_cases():
    cases = [{"case_id": f"p{i}", "shot_id": "s", "kind": "positive", "box": [0, 0, 1280, 800], "cond": "base", "site": "a", "role": "button", "desc": "d"}
             for i in range(6)] + [{"case_id": "n0", "shot_id": "s", "kind": "negative", "box": None, "cond": "base", "site": "a", "role": "absent", "desc": "d"}]
    man = {"shots": [SHOT], "selected_cases": cases}
    ok = {"found": True, "confidence": 0.9, "box_2d": [100, 100, 200, 200]}
    rows = [row("gemini_fast", f"p{i}", ok) for i in range(6)] + [row("gemini_fast", "n0", {"found": False, "confidence": 0.9})]
    rows += [row("gemini_accurate", f"p{i}", ok, lat=3000) for i in range(4)]              # only 4 of 7 cases called for flash
    sec = analyze.pointing_section(man, rows, ["gemini_fast", "gemini_accurate"], kind="point_desc", id_key="selected_cases")
    assert sec["cells"]["gemini_fast"]["positives"]["hit"]["n"] == 6 and sec["cells"]["gemini_accurate"]["positives"]["hit"]["n"] == 4
    assert "routed_lite_then_flash_6s_deadline" in sec["cells"] and sec["origin"] == analyze.ORIGIN
    assert sec["baselines"]["click_viewport_centre"]["hit"]["k"] == 6


def test_verifier_section_false_accept_gate_and_groups():
    items = [{"id": f"s{i}", "group": "success", "truth_accept": True} for i in range(4)] + [
        {"id": f"e{i}", "group": "error_503", "truth_accept": False} for i in range(4)]
    man = {"verifier": items}
    rows = [row("m", f"s{i}", {"verdict": "yes", "confidence": 0.9}, kind="verify") for i in range(3)] + [row("m", "s3", {"verdict": "unsure", "confidence": 0.4}, kind="verify")]
    rows += [row("m", "e0", {"verdict": "no", "confidence": 0.9}, kind="verify"), row("m", "e1", {"verdict": "yes", "confidence": 0.6}, kind="verify"),
             row("m", "e2", {"verdict": "yes", "confidence": 0.95}, kind="verify"), row("m", "e3", {"verdict": "unsure", "confidence": 0.2}, kind="verify")]
    c = analyze.verifier_section(man, rows, ["m"])["cells"]["m"]
    y = c["verdict_yes_is_accept"]
    assert y["false_accept"]["k"] == 2 and y["false_accept"]["n"] == 4 and y["false_reject"]["k"] == 1 and y["accuracy"]["k"] == 5
    assert c["code_gate_yes_and_confidence_at_least_0.7"]["false_accept"]["k"] == 1       # the 0.6-confidence yes is gated out
    assert c["unsure"]["k"] == 2 and c["by_group"]["error_503"]["verdicts"] == {"no": 1, "yes": 2, "unsure": 1}
    assert analyze.verifier_section(man, rows, ["m"])["baselines"]["always_accept"]["false_accept"]["p"] == 1.0


def test_glance_stability_and_plausibility():
    man = {}
    same = {"app_kind": "browser", "task_phase": "entering", "blocker": "none", "confidence": 0.9}
    other = {**same, "task_phase": "reading"}
    rows = [row("m", "a_landing", same if i < 4 else other, kind="glance", rep=i) for i in range(5)]
    rows += [row("m", "a_503", {**same, "blocker": "error_message", "task_phase": "waiting"}, kind="glance", rep=i) for i in range(5)]
    c = analyze.glance_section(man, rows, ["m"])["cells"]["m"]
    assert c["modal_triple_agreement"]["k"] == 9 and c["modal_triple_agreement"]["n"] == 10
    assert c["field_agreement"]["app_kind"]["k"] == 10 and c["plausible"]["k"] == 10
    assert set(c["by_screen"]) == {"a_landing", "a_503"} and c["by_screen"]["a_landing"]["modal"] == ("browser", "entering", "none")


# ------------------------------------------------------------------------------------------------ report
def test_report_renders_from_synthetic_sections_and_recommendation_follows_intervals(tmp_path):
    cases = [{"case_id": f"p{i}", "shot_id": "s", "kind": "positive", "box": [0, 0, 1280, 800], "cond": "base", "site": "a", "role": "button", "desc": "d"}
             for i in range(30)]
    man = {"shots": [SHOT], "selected_cases": cases, "step_cases": [], "verifier": []}
    good = {"found": True, "confidence": 0.9, "box_2d": [100, 100, 200, 200]}
    rows = []
    for c, lat in (("gemini_fast", 900), ("gemini_accurate", 3300), ("openai_fast", 1500)):
        rows += [row(c, f"p{i}", good if i < 28 else {"found": False, "confidence": 0.9}, lat=lat) for i in range(30)]
    secs = {"pointing": analyze.pointing_section(man, rows, ["gemini_fast", "gemini_accurate", "openai_fast"], kind="point_desc", id_key="selected_cases"),
            "pointing_step_ids": analyze.pointing_section(man, [], ["gemini_fast"], kind="point_step", id_key="step_cases"),
            "verifier": analyze.verifier_section(man, [], ["gemini_fast"]), "glance": analyze.glance_section(man, [], ["gemini_fast"])}
    rec_ = report.recommend(secs)
    assert rec_["point_lite_primary"] is True and rec_["point_openai_primary"] is False          # intervals overlap: no reason to switch
    assert rec_["point_keep_escalation"] is False and rec_["significance"]["lite_vs_flash_hit"] == "not significant"
    j = report.build_json({**secs, "recommendation": rec_}, models={"gemini_fast": "m1"}, budget=Budget(3.0, None).summary(),
                          counts={"live": 1, "cached": 0, "failed": 0, "dropped": 0}, apis={"gemini_fast": "interactions"}, thinking={"gemini_fast": "low"})
    md = report.render_markdown(j)
    assert "synthetic sandbox ui, headless screenshots" in md.lower() and "Wilson 95%" in md and "Limitations" in md
    assert "OLD PROJECT" in md and md.count("|") > 50
    yml = report.routing_yaml(rec_)
    assert "gemini" in yml and "roles:" in yml
    report.write_all(j, out_json=tmp_path / "o.json", out_md=tmp_path / "o.md", out_yaml=tmp_path / "o.yaml")
    assert json.loads((tmp_path / "o.json").read_text())["meta"]["origin"] == analyze.ORIGIN


def test_recommendation_switches_to_openai_only_when_intervals_separate():
    def cell(k, n):
        r = stats.rate(k, n)
        return {"positives": {"hit": r}, "latency_ms": {"p95": 2000}, "n_cases": n}

    secs = {"pointing": {"cells": {"gemini_fast": cell(40, 100), "gemini_accurate": cell(45, 100), "openai_fast": cell(95, 100)}}}
    assert report.recommend(secs)["point_openai_primary"] is True
    secs = {"pointing": {"cells": {"gemini_fast": cell(90, 100), "gemini_accurate": cell(92, 100), "openai_fast": cell(95, 100)}}}
    assert report.recommend(secs)["point_openai_primary"] is False       # 95 vs 92: the intervals overlap, so no switch


# ------------------------------------------------------------------------------------------------ regression tests (found by looking at the first full run)
def test_collect_rows_finds_rows_by_cache_key_and_counts_identical_inputs_once(tmp_path, monkeypatch):
    """Identical inputs (same pixels and description) are one case; a re-render that renumbers case ids cannot misalign rows."""
    from evals.modelbench.__main__ import collect_rows

    monkeypatch.setenv("GEMINI_MODEL_FAST", "m-fast")
    c = Contender("gemini_fast")
    cache = ResultCache(tmp_path / "r.jsonl")
    j1 = Job("point_desc", "old-id-1", "a.png", "sha1", desc="the button")
    cache.put(key_for(c, j1), {"ok": True, "value": {"found": False, "confidence": 0.9}, "case_id": "old-id-1"})
    renumbered = Job("point_desc", "new-id-7", "a.png", "sha1", desc="the button")                 # same input, new case id
    same_input_other_condition = Job("point_desc", "v2-id-8", "a.png", "sha1", desc="the button")  # pixel-identical v2 case
    different = Job("point_desc", "new-id-9", "a.png", "sha2", desc="the button")                  # new pixels: not in the cache yet
    rows, dup = collect_rows(cache, [c], [renumbered, same_input_other_condition, different])
    assert [r["case_id"] for r in rows] == ["new-id-7"] and dup == 1


def test_select_cases_never_samples_a_secondary_case_that_repeats_a_base_input():
    from evals.modelbench.__main__ import select_cases

    shots = [{"shot_id": f"{c}__s", "screen": "s", "site": "c", "cond": c, "layout": "v1", "variant": "clean", "theme": "light",
              "file": f"{c}.png", "width": 1280, "height": 800, "sha": "same" if c in ("base", "v2") else f"sha-{c}",
              "step_truth": {}, "injection_visible": c == "injected"} for c in ("base", "v2", "injected", "dark")]
    cs = [c.__dict__ for c in make_cases()]
    sel = select_cases({"shots": shots, "cases": cs})
    assert not [c for c in sel if c["cond"] == "v2"]                  # every v2 case here is pixel-identical to a base case
    assert len([c for c in sel if c["cond"] == "dark" and c["kind"] == "positive"]) == 24
    assert len([c for c in sel if c["cond"] == "injected" and c["kind"] == "positive"]) == 24


def test_a_503_screens_are_real_error_pages_on_every_site(tmp_path):
    """The first full run rendered site A's 'a_503' without the glitch parameter, so it was a result page. All three must be error pages."""
    pw = pytest.importorskip("playwright.sync_api")
    from understudy_agent.sandbox_sites.runner import SandboxCluster

    with SandboxCluster(ephemeral=True) as cluster, pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"no chromium: {type(e).__name__}")
        r = cm.Renderer(tmp_path, cluster.urls)
        r.render_glitch_pages(browser, "base")
        browser.close()
    for site in ("a", "b", "c"):
        cs = [c for c in r.cases if c.screen == f"{site}_503" and c.kind == "positive"]
        assert any(c.role == "alert" for c in cs), f"{site}_503 has no error message box: it is not an error page"
        assert any("Go back" in c.desc for c in cs)


def test_verifier_images_are_all_distinct_and_cover_the_planned_groups(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from understudy_agent.sandbox_sites.runner import SandboxCluster

    with SandboxCluster(ephemeral=True) as cluster, pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"no chromium: {type(e).__name__}")
        items = cm.Renderer(tmp_path, cluster.urls).render_verifier(browser)
        browser.close()
    assert len({i["sha"] for i in items}) == len(items) == 30
    groups = {}
    for i in items:
        groups.setdefault(i["group"], []).append(i["truth_accept"])
    assert {g: (len(v), set(v)) for g, v in groups.items()} == {
        "success": (12, {True}), "error_503": (6, {False}), "invalid_total": (6, {False}), "injected_result": (3, {True}),
        "injected_false_success_503": (3, {False})}


def test_recommendation_keeps_escalation_only_when_the_paired_interval_is_above_zero():
    def cell(k, n):
        return {"positives": {"hit": stats.rate(k, n)}, "latency_ms": {"p95": 1500}, "n_cases": n}

    pairs_better = {"routed_6s_deadline_minus_gemini_fast": {"ci": (0.02, 0.1), "diff": 0.06},
                    "gemini_fast_minus_gemini_accurate": {"ci": (-0.2, -0.05), "diff": -0.12}}
    secs = {"pointing": {"cells": {"gemini_fast": cell(80, 100), "gemini_accurate": cell(92, 100)}, "paired_hit_differences": pairs_better}}
    r = report.recommend(secs)
    assert r["point_keep_escalation"] is True and r["point_lite_primary"] is False       # flash is significantly better: lite is not primary
    pairs_flat = {"routed_6s_deadline_minus_gemini_fast": {"ci": (-0.03, 0.04), "diff": 0.005}}
    r2 = report.recommend({"pointing": {"cells": {"gemini_fast": cell(80, 100), "gemini_accurate": cell(92, 100)}, "paired_hit_differences": pairs_flat}})
    assert r2["point_keep_escalation"] is False and r2["significance"]["routed_vs_lite_hit"] == "not significant"


def test_verifier_recommendation_follows_the_intervals():
    def v(k, n):
        return {"verdict_yes_is_accept": {"false_accept": stats.rate(k, n)}}

    same = {"verifier": {"cells": {"gemini_fast": v(1, 13), "gemini_accurate": v(1, 13), "openai_fast": v(1, 13)}}}
    assert report.recommend(same)["verify_gemini_ok"] is True
    worse = {"verifier": {"cells": {"gemini_fast": v(40, 50), "gemini_accurate": v(1, 50), "openai_fast": v(2, 50)}}}
    assert report.recommend(worse)["verify_gemini_ok"] is False


def test_runner_records_the_load_average_per_call_and_the_latency_section_uses_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_FAST", "m-fast")
    monkeypatch.setattr("os.getloadavg", lambda: (42.5, 50.0, 60.0))
    r, _ = fake_runner(tmp_path)
    c = Contender("gemini_fast")
    jobs = [Job("point_desc", "c0", "a.png", "sha", desc="d", rep=100 + i, group="latency") for i in range(4)]
    r.run([c], jobs)
    rows = [{**x, "kind": "point_desc"} for x in r.cache.rows()]
    assert all(x["load_avg_1m"] == 42.5 for x in rows)
    sec = analyze.latency_section(rows, ["gemini_fast"], {"gemini_fast": {"latency_ms": {"p50": 900.0, "n": 190}}})
    cell = sec["cells"]["gemini_fast"]
    assert cell["n_ok"] == 4 and cell["load_avg_1m"] == {"n_calls_with_load": 4, "mean": 42.5, "max": 42.5}
    assert cell["main_run_p50_ms"] == 900.0 and cell["latency_ms"]["p50"] == 100


def test_cells_without_recorded_load_say_so():
    rec_ = rec("x", hit=True)
    assert analyze.agg_point([rec_])["load_avg_1m"] == {"n_calls_with_load": 0, "mean": None, "max": None}
