"""The pre-registered analysis and the report section, on made-up numbers (never on data)."""
from __future__ import annotations

import json

import pytest

from evals.study_sim import analysis, report
from evals.study_sim.design import SEED

from .conftest import made_up_rows, write_rows_csv


def coached_gain(gain):
    def f(s, b):
        base = 1 if b.skill == "cliff" else 0
        return min(base + (gain if b.nominal_condition == "coached" else 0), 2 if b.skill == "cliff" else 1)
    return f


def test_all_participants_gain_gives_a_positive_headline(specs):
    rows = made_up_rows(specs, lambda s, b: (2 if b.skill == "cliff" else 1) if b.nominal_condition == "coached" else 0)
    a = analysis.analyse_all(rows)
    h = a["headline"]
    assert h["n"] == 16 and h["mean_difference"] == 1.0 and h["ci_degenerate"] is True            # identical differences: zero-width interval is flagged
    assert h["sign_flip_p_two_sided"] == pytest.approx(2 / 2 ** 16, abs=1e-6) and h["smallest_possible_p"] == 2 / 2 ** 16
    assert a["design_problems"] == []
    assert a["per_skill"]["cliff"]["mean_coached"] == 1.0 and a["per_skill"]["cliff"]["mean_uncoached"] == 0.0
    assert a["nudges"]["shown"] == 32 and a["nudges"]["followed"] == 16


def test_no_effect_gives_zero_and_the_aa_arm_is_separate(specs):
    rows = made_up_rows(specs, lambda s, b: 1 if b.skill == "cliff" else 0, aa_score_fn=lambda s, b: 1)
    a = analysis.analyse_all(rows)
    assert a["headline"]["n"] == 16
    assert a["aa"]["n"] == 8 and a["aa"]["relabelling"]["n"] == 8
    coached_only = analysis.headline(analysis.split_arms(rows)[0])
    assert coached_only["n"] == 16
    assert a["effort"]["actions_coached"]["n"] == 16 and a["effort"]["actions_uncoached"]["n"] == 16
    assert a["effort_aa"]["actions_coached"]["n"] == 0 and a["effort_aa"]["actions_uncoached"]["n"] == 16     # A/A: nothing was actually coached
    assert a["nudges"]["coached_blocks"] == 16                                                             # A/A blocks never count as coached


def test_a_negative_effect_is_shown_as_negative(specs):
    rows = made_up_rows(specs, lambda s, b: 0 if b.nominal_condition == "coached" else (2 if b.skill == "cliff" else 1))
    a = analysis.analyse_all(rows)
    assert a["headline"]["mean_difference"] < 0 and a["headline"]["ci95"][1] < 0
    assert all(v < 0 for v in a["headline"]["per_participant_difference"].values())


def test_exclusion_removes_the_whole_participant(specs):
    rows = made_up_rows(specs, coached_gain(1))
    for r in rows:
        if r["participant"] == "p_sim01" and r["block"] == 2:
            r["exclusion"] = "harness error"
    a = analysis.analyse_all(rows)
    assert a["headline"]["n"] == 15 and "p_sim01" in a["excluded_participants"] and "p_sim01" not in a["headline"]["per_participant_difference"]


def test_aa_relabelling_is_exact_and_flags_a_biased_chain(specs):
    # a chain in which cliff always scores 2 and reconcile 0 has a big skill difference; balanced relabelling cancels it in the mean
    rows = made_up_rows(specs, lambda s, b: 0, aa_score_fn=lambda s, b: 2 if b.skill == "cliff" else 0)
    aa = analysis.split_arms(rows)[1]
    r = analysis.aa_relabelling(aa)
    assert r["relabellings"] == 70 and r["n"] == 8
    assert 0.0 <= r["share_sign_flip_p_below_05"] <= 1.0 and 0.0 <= r["share_ci_excludes_zero"] <= 1.0
    # with all scores equal there is nothing to flag
    same = analysis.split_arms(made_up_rows(specs, lambda s, b: 0, aa_score_fn=lambda s, b: 0))[1]
    assert analysis.aa_relabelling(same)["share_ci_excludes_zero"] == 0.0


def test_bootstrap_is_reproducible():
    a, b = [1.0, 2.0, 2.0, 1.0], [0.0, 1.0, 0.0, 1.0]
    assert analysis._boot_mean_diff(a, b) == analysis._boot_mean_diff(a, b)
    assert analysis._boot_mean_diff([1.0], b) == [None, None] and SEED == 20261107


def test_section_shape_and_labels(specs, tmp_path):
    rows = made_up_rows(specs, coached_gain(1), aa_score_fn=lambda s, b: 1)
    write_rows_csv(tmp_path / "participants.csv", rows)
    (tmp_path / "checks").mkdir()
    for s in specs[:2]:
        (tmp_path / "checks" / f"{s.pid}.json").write_text(json.dumps({"participant": s.pid, "exclusion": "", "cases": [{"phase": "post", "capped": False}], "checks": {
            "events": {"total": 100, "from_extension": 98, "schema_invalid": 0, "types": {"click": 10}},
            "coach": {"shown": [{"action": "annotate", "zone": "cliff_button", "skill": "cliff", "ring_found": True, "ring_on_arrival": False, "outcome": "followed", "false": "", "delay_s": 9.0}],
                      "polls": 30, "decisions_non_silent": 1, "p_source": {"hazard": 5}, "polls_by_mode": {"train": 10, "post_test": 10, "off": 10},
                      "non_silent_by_mode": {"train": 1, "post_test": 0, "off": 0}},
            "coach_events": {"by_block_skill": {"train/check-the-cliff": 1}}, "study_mode_violations": [], "study_mode_enforcement_from_store": [],
            "engine_log": {"tracebacks": 0, "error_lines": 0, "events_post_failures": 0}, "errors": [], "consent_probe_events": 0, "consent_off_events_after": 0,
            "kill": {"engine_reports_killed": True, "coach_action_after_kill": "silent"}}}))
    (tmp_path / "cost.json").write_text(json.dumps({"usd_est": 1.5, "cap_usd": 8, "calls": 100, "cache_hits": 3, "tokens": {"in": 1000, "out": 100}}))
    sec = report.build_section(tmp_path)
    for k in ("status", "label", "n", "n_aa", "headline", "per_skill", "aa", "effort", "nudges", "pipeline_checks", "cost", "limitations", "meta"):
        assert k in sec
    assert sec["status"] == "complete" and sec["n"] == 16 and sec["n_aa"] == 8
    assert sec["label"] == "simulated participants (language model), not people"
    for k in ("mean_difference", "ci95", "per_participant_difference", "sign_flip_p_two_sided", "smallest_possible_p"):
        assert k in sec["headline"]
    assert set(sec["nudges"]) >= {"shown", "followed", "dismissed"} and set(sec["effort"]) >= {"actions_coached", "actions_uncoached"}
    assert "false_positive_note" in sec["aa"] and "mean_difference" in sec["aa"]
    pc = sec["pipeline_checks"]
    assert pc["ring_target"]["zone_equals_missing_step_zone"] == 2 and pc["study_mode_enforcement"]["verdict"].startswith("zero nudges")
    assert pc["consent"]["respected"] is True and pc["events"]["schema_valid_share"] == 1.0
    assert all({"id", "text", "severity"} <= set(x) for x in sec["limitations"])
    md = report.render_md(sec)
    assert "not people" in md and "What this does not show" in md and "Study mode enforcement" in md


def test_violations_are_called_out(specs, tmp_path):
    rows = made_up_rows(specs[:4], coached_gain(1))
    write_rows_csv(tmp_path / "participants.csv", rows)
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks" / "p_sim01.json").write_text(json.dumps({"participant": "p_sim01", "checks": {
        "events": {}, "coach": {"shown": [], "polls": 5, "non_silent_by_mode": {"train": 0, "post_test": 1, "off": 0}, "polls_by_mode": {"train": 1, "post_test": 3, "off": 1}},
        "study_mode_violations": ["p_sim01 block 1 post-test: coach acted (annotate) in a post_test block"], "errors": []}}))
    sec = report.build_section(tmp_path)
    assert sec["status"] == "harness_failure" and sec["pipeline_checks"]["study_mode_enforcement"]["verdict"].startswith("VIOLATION")


def test_not_run_stub_and_section_function(tmp_path, monkeypatch):
    from evals.study_sim import section
    monkeypatch.setattr(section, "RESULTS", tmp_path)
    s = section.study_sim_section()
    assert s["status"] == "not_run" and s["label"] == "simulated participants (language model), not people" and s["limitations"]
    assert report.build_section(tmp_path)["status"] == "not_run"


def test_run_refuses_without_go(monkeypatch, capsys):
    from evals.study_sim import __main__ as m
    monkeypatch.setattr(m, "GO_FILE", m.HERE / "no-such-go-file")
    class A:  # noqa: D401
        only = ""; pace = 0.1; cap = 1; poll = 1.0; workers = 1; shared = False
    assert m.cmd_run(A()) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_engine_event_export_is_time_ordered_and_scrubs_text(tmp_path):
    from evals.study_sim import analysis_io
    d = tmp_path / "real" / "p_sim01"
    d.mkdir(parents=True)
    rows = [{"id": "b", "t": "2026-11-07T10:00:02Z", "type": "click", "meta": {"zone": "cliff_button", "n": 3}, "target": {"role": "button", "label_hash": "h:abcdef012345"}},
            {"id": "a", "t": "2026-11-07T10:00:01Z", "type": "nav", "meta": {"zone": "calc_site"}},
            {"id": "c", "t": "2026-11-07T10:00:03Z", "type": "coach_shown", "meta": {"step": "cliff_a", "note": "Check cliff edges before you copy this result."}}]
    (d / "2026-11-07.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = tmp_path / "raw" / "p_sim01" / "engine_events.jsonl"
    r = analysis_io.export_engine_events(tmp_path, "p_sim01", out)
    got = [json.loads(x) for x in out.read_text().splitlines()]
    assert [g["id"] for g in got] == ["a", "b", "c"] and r == {"events": 3, "stripped_values": 1}
    assert got[2]["meta"]["note"] == "[removed]" and got[1]["target"]["label_hash"] == "h:abcdef012345" and got[1]["meta"]["n"] == 3
    assert analysis_io.export_engine_events(tmp_path, "p_none", tmp_path / "x" / "e.jsonl") == {"events": 0, "stripped_values": 0}
