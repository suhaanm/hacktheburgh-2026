"""ANA-10, ANA-11, HND-1, HND-7: finder (planted routines), scoring, forecast, value, gate, timing, proposal copy."""
from __future__ import annotations

import collections
from datetime import datetime, timezone

import numpy as np
import pytest

from understudy_engine.memory import MemoryStore, load_pack
from understudy_engine.routines.detect import DetectConfig, detect_routines
from understudy_engine.routines.finder import FinderConfig, edit_distance, find_routines, pairwise_distances, skeleton
from understudy_engine.routines.forecast import DAY, backtest_coverage, fit_forecast
from understudy_engine.routines.gate import MemorySkillSource, routine_skill_gate
from understudy_engine.routines.proposal import build_proposal, how_often, hours_text
from understudy_engine.routines.scoring import judgement_share, match_template, score_cluster
from understudy_engine.routines.timing import AcceptModel, Candidate, ProposalScheduler, boundaries
from understudy_engine.routines.value import ValueParams, value_model

from .gen import routine_episodes


def _precision_recall(clusters, labels, eps, min_support=3):
    idx = {id(e): i for i, e in enumerate(eps)}
    planted = {l for l in labels if l}
    truth_counts = collections.Counter(l for l in labels if l)
    tp = 0
    found = set()
    for c in clusters:
        cnt = collections.Counter(labels[idx[id(e)]] for e in c.episodes)
        top, n = cnt.most_common(1)[0]
        if top is not None and n / c.size >= 0.5:
            tp += 1
            found.add(top)
    detectable = {l for l, n in truth_counts.items() if n >= min_support}
    return tp / max(len(clusters), 1), len(found & detectable) / max(len(detectable), 1)


# ----------------------------------------------------------------------------- finder
def test_edit_distance_is_normalised_and_vectorised_matches_scalar():
    assert edit_distance("abc", "abc") == 0 and edit_distance("abc", "xyz") == 1.0
    assert edit_distance("abcd", "abxd") == pytest.approx(0.25)
    seqs = [tuple("ABCDE"), tuple("ABXDE"), tuple("ZZZ"), tuple("ABCDEF")]
    D = pairwise_distances(seqs)
    for i in range(4):
        for j in range(4):
            assert D[i, j] == pytest.approx(edit_distance(seqs[i], seqs[j]), abs=1e-6)


def test_skeleton_drops_wandering_and_collapses_repeats():
    eps, _ = routine_episodes(planted={"result-to-note": 1.0}, n_noise_per_day=0, seed=1)
    from understudy_engine.core import Cog, Episode

    ep = Episode("t", "p", "r", "synthetic", 0, 10, [Cog(0, 1, "READ"), Cog(1, 2, "IDLE"), Cog(2, 3, "READ"), Cog(3, 4, "REFORMULATE"), Cog(4, 5, "COPY")])
    assert skeleton(ep) == ("READ", "COPY")


def test_planted_routines_are_found_with_precision_and_recall():
    planted = {"calc-entry": 1.0, "result-to-note": 0.8, "weekly-refresh": 0.4}
    eps, labels = routine_episodes(seed=3, planted=planted, n_noise_per_day=4.0)
    clusters = find_routines(eps, FinderConfig())
    p, r = _precision_recall(clusters, labels, eps)
    assert r == 1.0, "every planted routine with 3 or more runs is found"
    assert p >= 0.9
    # the medoid of the biggest cluster is the planted sequence (up to slips)
    from .gen import BASE_PATTERNS

    for name in planted:
        assert min(edit_distance(c.medoid, tuple(BASE_PATTERNS[name])) for c in clusters) <= 0.15, name


def test_one_off_work_and_rare_routines_are_not_clusters():
    eps, labels = routine_episodes(seed=5, planted={"calc-entry": 1.0, "weekly-refresh": 0.05}, n_noise_per_day=6.0)
    runs = collections.Counter(l for l in labels if l)
    clusters = find_routines(eps, FinderConfig(min_support=3))
    from .gen import BASE_PATTERNS

    rare = tuple(BASE_PATTERNS["weekly-refresh"])
    has_rare_cluster = any(edit_distance(c.medoid, rare) <= 0.15 for c in clusters)
    assert has_rare_cluster == (runs["weekly-refresh"] >= 3)        # found exactly when it ran often enough
    assert all(c.size >= 3 for c in clusters)
    assert find_routines(eps[:2]) == []


def test_finder_is_deterministic_and_handles_empty():
    eps, _ = routine_episodes(seed=7)
    a = [(c.size, c.medoid) for c in find_routines(eps)]
    b = [(c.size, c.medoid) for c in find_routines(list(reversed(eps)))]
    assert a == b
    assert find_routines([]) == []


# ----------------------------------------------------------------------------- scoring
def test_scoring_count_minutes_cv_and_judgement_share():
    eps, labels = routine_episodes(seed=3, planted={"calc-entry": 1.0}, n_noise_per_day=0.0)
    (cl,) = find_routines(eps)
    sc = score_cluster(cl, span_days=21)
    assert sc.count == cl.size == len(eps)
    assert sc.minutes_per_week == pytest.approx(sum(e.duration for e in eps) / 60 / 3, rel=1e-6)
    assert 0 < sc.cv < 1 and sc.judgement_share == 0.0 and sc.n_days >= 5
    assert judgement_share(["SEARCH", "READ", "DECIDE", "COPY"]) == 0.5
    assert judgement_share([], ["SEARCH"]) == 0.0


def test_template_match_uses_each_templates_own_distance():
    pack = load_pack("benefits-processor")
    medoid = ("OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT") * 3 + ("RECONCILE",)
    t, d = match_template(medoid, pack.templates)
    assert t["id"] == "calc-entry-3x" and d < 0.3
    none, _ = match_template(("NAVIGATE", "ASK", "PASTE", "SEARCH"), pack.templates)
    assert none is None


# ----------------------------------------------------------------------------- forecast
def _times(per_dow: dict[int, float], weeks: int, seed=3):
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 10, 12, tzinfo=timezone.utc).timestamp()  # a Monday
    out = []
    for w in range(weeks):
        for dow, lam in per_dow.items():
            for _ in range(rng.poisson(lam)):
                out.append(t0 + (w * 7 + dow) * DAY + rng.uniform(9, 17) * 3600)
    return out, (t0, t0 + weeks * 7 * DAY)


def test_forecast_has_weekly_seasonality_and_an_interval_that_covers():
    times, win = _times({0: 4, 1: 4, 2: 4, 3: 4, 4: 4}, 3)             # weekdays only, 4 a day
    f = fit_forecast(times, win, 28)
    assert 70 < f.mean_runs < 105                                       # ~20 a week x 4 weeks
    assert f.lo < f.mean_runs < f.hi and f.lo < 80 < f.hi
    assert f.runs_per_week == pytest.approx(f.mean_runs / 4)
    only_mon, win2 = _times({0: 6}, 3)
    g = fit_forecast(only_mon, win2, 28)
    assert 14 < g.mean_runs < 36                                        # about 4 Mondays x 6 runs
    # deterministic
    assert fit_forecast(times, win, 28).mean_runs == f.mean_runs


def test_forecast_interval_widens_with_week_to_week_variation():
    steady, w1 = _times({0: 5, 1: 5, 2: 5, 3: 5, 4: 5}, 4, seed=1)
    t0 = w1[0]
    bursty = [t0 + (w * 7 + d) * DAY + 3600 * 10 for w, n in enumerate([40, 2, 38, 1]) for d in range(n % 5 if n < 5 else 5) for _ in range(max(1, n // 5))]
    a, b = fit_forecast(steady, w1, 28), fit_forecast(bursty, w1, 28)
    assert b.dispersion > a.dispersion
    assert (b.hi - b.lo) / max(b.mean_runs, 1) > (a.hi - a.lo) / a.mean_runs


def test_forecast_backtest_returns_fields():
    times, win = _times({0: 3, 1: 3, 2: 3, 3: 3, 4: 3}, 4)
    bt = backtest_coverage(times, win[0], win[0] + 21 * DAY, win[1])
    assert set(bt) == {"predicted", "lo", "hi", "actual", "inside"}


# ----------------------------------------------------------------------------- value
def test_value_model_hours_net_and_confidence():
    draws = np.random.default_rng(1).poisson(60, 2000).astype(float)
    durs = [300.0, 280.0, 320.0, 310.0, 290.0]                          # about 5 minutes a run
    v = value_model(draws, durs, 0.0, ValueParams(wage_gbp_h=15.0, build_cost_runs=6))
    assert 4.0 < v["hours_saved_mean"] < 6.0                            # 60 runs x 5 min
    assert v["hours_saved"][0] < v["hours_saved_mean"] < v["hours_saved"][1]
    assert v["net_gbp"][0] > 0 and v["confidence"] == 1.0 and v["horizon_weeks"] == 4
    tiny = value_model(np.full(200, 2.0), durs, 0.0, ValueParams())
    assert tiny["net_gbp_mean"] < 0 and tiny["confidence"] == 0.0       # two runs never repay the build
    half = value_model(draws, durs, 0.5, ValueParams())                  # judgement stays with the worker
    assert half["hours_saved_mean"] == pytest.approx(v["hours_saved_mean"] / 2, rel=0.05)
    cheap = value_model(draws, durs, 0.0, ValueParams(wage_gbp_h=30.0))
    assert cheap["net_gbp_mean"] > v["net_gbp_mean"]                    # the wage is a parameter


# ----------------------------------------------------------------------------- skill gate
def test_skill_gate_requires_l4_or_not_learning_relevant(tmp_path):
    pack = load_pack("benefits-processor")
    store = MemoryStore(tmp_path)
    from understudy_engine.memory import onboard

    onboard(store, "benefits-processor", {})
    src = MemorySkillSource(store.read(), pack)
    g = routine_skill_gate(src, ["ENTER_HOUSEHOLD"], 0.0, learning_relevant=True)
    assert not g["eligible"] and "coach first" in g["reason"] and "ENTER_HOUSEHOLD at L1" in g["reason"]
    assert routine_skill_gate(src, ["COPY_TO_NOTE"], 0.0, learning_relevant=False)["eligible"]
    # the worker reaches L4 on the skill that holds ENTER_HOUSEHOLD
    doc = store.read()
    line = [l for l in doc.section("Skill state").lines() if l.text.startswith("enter-household-once")][0]
    store.update_line(line.id, actor="worker", text="enter-household-once: L4, streak 3, last seen 2026-11-07")
    g = routine_skill_gate(MemorySkillSource(store.read(), pack), ["ENTER_HOUSEHOLD"], 0.0)
    assert g["eligible"] and g["reason"] == "mastery L4 on ENTER_HOUSEHOLD"
    assert not routine_skill_gate(None, ["X"], 0.0)["eligible"]


# ----------------------------------------------------------------------------- proposal timing (HND-7)
def test_accept_model_learns_from_declines_and_accepts():
    m = AcceptModel.from_prior({"alpha": 2, "beta": 3})
    assert m.p_accept("p") == pytest.approx(0.4)
    for _ in range(6):
        m.observe("p", False, 15)
    assert m.p_accept("p") < 0.2 and m.p_accept("q") == pytest.approx(0.4)   # per person
    for _ in range(10):
        m.observe("q", True, 9)
    assert m.p_accept("q") > 0.7 and m.p_accept("q", 9) > m.p_accept("q", 15)   # morning accepts lift the morning estimate


def test_scheduler_only_at_boundaries_within_budget_with_cooldown():
    sch = ProposalScheduler(daily_budget=2, cooldown_days=2)
    now = datetime(2026, 11, 3, 10, tzinfo=timezone.utc).timestamp()
    cands = [Candidate("a", 3.0), Candidate("b", 1.0)]
    assert sch.offer("p", now, cands, at_boundary=False) is None
    assert sch.offer("p", now, cands, at_boundary=True).routine_id == "a"       # highest expected value first
    assert sch.offer("p", now + 600, cands, at_boundary=True).routine_id == "a"
    assert sch.offer("p", now + 1200, cands, at_boundary=True) is None            # budget of two used up today
    assert sch.offer("p", now + DAY, [Candidate("a", 3.0, declined_not_now_at=now + DAY - 3600)], at_boundary=True) is None   # cooldown
    assert sch.offer("p", now + 4 * DAY, [Candidate("a", 3.0, declined_not_now_at=now)], at_boundary=True).routine_id == "a"
    assert sch.offer("q", now, [Candidate("n", 3.0, status="never"), Candidate("z", 0.0), Candidate("m", 2.0, proposable=False)], at_boundary=True) is None


def test_a_decline_is_a_label_and_fewer_cards_follow():
    sch = ProposalScheduler(daily_budget=5, min_p_accept=0.25)
    now = datetime(2026, 11, 3, 10, tzinfo=timezone.utc).timestamp()
    assert sch.offer("p", now, [Candidate("a", 2.0)], at_boundary=True) is not None
    for _ in range(5):
        sch.decline_or_accept("p", now, accepted=False)
    assert sch.offer("p", now + 60, [Candidate("a", 2.0)], at_boundary=True) is None


def test_proposals_never_fire_mid_task_in_replay():
    import json
    from pathlib import Path

    from understudy_engine.memory.paths import data_dir

    p = Path(data_dir()) / "synthetic" / "nine-to-five" / "events.jsonl"
    if not p.exists():
        pytest.skip("persona data not generated")
    rows = [json.loads(l) for l in p.read_text().splitlines()][:6000]
    marks = boundaries(rows)
    assert len(marks) > 20
    # reconstruct task intervals; every boundary lies outside every [task_start, task_end]
    ev = sorted(((datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp(), r["type"]) for r in rows))
    open_t, spans = None, []
    for t, typ in ev:
        if typ == "task_start":
            open_t = t
        elif typ == "task_end" and open_t is not None:
            spans.append((open_t, t))
            open_t = None
    for m in marks:
        assert not any(a < m < b for a, b in spans), m


# ----------------------------------------------------------------------------- proposal copy (HND-1)
def test_proposal_copy_has_what_how_often_hours_touches_never():
    pack = load_pack("benefits-processor")
    tmpl = pack.template("calc-entry-3x")
    cp = build_proposal(title=tmpl["title"], template=tmpl, medoid=["OPEN_CALCULATOR"], count=14, span_days=21,
                        hours=[3.1, 5.2], horizon_weeks=4, risk_irreversible=pack.risk_irreversible)
    assert cp["what"].startswith("Enter the household") and cp["how_often"] == "about 14 times in 3 weeks"
    assert cp["hours_saved_text"] == "about 3.1 to 5.2 hours over the next 4 weeks"
    assert cp["touches"] == tmpl["touches"] and cp["never"] == tmpl["never"]
    auto = build_proposal(title="x", template=None, medoid=["READ", "COPY", "COPY"], count=3, span_days=7, hours=[0.0, 0.05],
                          horizon_weeks=4, risk_irreversible=["submit", "pay"])
    assert "read, then copy" in auto["what"] and auto["never"] == ["submit", "pay"] and "under 0.1" in auto["hours_saved_text"]
    assert how_often(1, 7) == "about 1 time in 1 week" or how_often(1, 7) == "about 1 times in 1 week"
    assert hours_text([1.0, 2.0], 2).endswith("2 weeks")


# ----------------------------------------------------------------------------- the pipeline
def test_detect_routines_builds_contract_ready_objects_from_planted_episodes():
    pack = load_pack("benefits-processor")
    eps, labels = routine_episodes(seed=3, planted={"calc-entry": 1.2, "result-to-note": 1.0}, n_noise_per_day=5.0)
    out = detect_routines(eps, pack, person="p_t", skills=None, cfg=DetectConfig())
    assert out, "something is reported"
    top = out[0]
    for k in ("id", "role", "title", "episodes", "minutes_per_week", "cv", "judgement_share", "value", "touches", "never",
              "build_timing", "skill_gate", "proposal", "irreversible_classes", "forecast"):
        assert k in top
    assert top["value"]["hours_saved"][0] <= top["value"]["hours_saved"][1] and top["value"]["horizon_weeks"] == 4
    assert top["build_timing"]["rule"] == "ski-rental" and top["build_timing"]["buy_after_runs"] >= 0
    assert not top["skill_gate"]["eligible"]                      # no skill record: coach first
    assert "not_proposable_because" in top and not top["proposable"]
    assert len({r["id"] for r in out}) == len(out)
