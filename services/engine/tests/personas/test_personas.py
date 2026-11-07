from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime

import pytest

from understudy_engine.personas import CHANGE_DAY, N_DAYS, PERSONA_BY_SLUG, PERSONAS, simulate_persona, write_persona
from understudy_engine.store import EventStore, validate_row


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def runs():
    return {spec.slug: simulate_persona(spec, with_mc=False) for spec in PERSONAS}


def test_four_personas_21_days():
    assert [p.slug for p in PERSONAS] == ["nine-to-five", "night-owl", "shift-worker", "irregular"]
    assert N_DAYS == 21 and CHANGE_DAY == 15


def test_deterministic():
    spec = PERSONA_BY_SLUG["shift-worker"]
    a = simulate_persona(spec, with_mc=False)
    b = simulate_persona(spec, with_mc=False)
    assert a.rows == b.rows and a.truth == b.truth


def test_files_tagged_synthetic_and_valid(tmp_path):
    info = write_persona(PERSONA_BY_SLUG["irregular"], tmp_path, with_mc=False)
    out = tmp_path / "synthetic" / "irregular"
    assert (out / "events.jsonl").exists() and (out / "truth.json").exists()
    store = EventStore(tmp_path)
    evs = store.read("synthetic", person="p_irregular")
    assert len(evs) == info["events"] > 5000
    assert {e.origin for e in evs} == {"synthetic"} and {e.person for e in evs} == {"p_irregular"}
    assert store.read("real") == []
    truth = json.loads((out / "truth.json").read_text())
    assert truth["origin"] == "synthetic" and truth["person"] == "p_irregular" and truth["n_days"] == 21


def test_events_contain_no_text_and_use_expected_types(runs):
    for run in runs.values():
        ok = 0
        for row in run.rows[:: max(1, len(run.rows) // 400)]:
            validate_row(row)
            ok += 1
        assert ok > 100
        types = Counter(r["type"] for r in run.rows)
        for t in ("task_start", "task_end", "progress", "stuck", "scroll", "click", "nav", "search", "copy", "paste", "idle", "lock", "unlock", "sleep", "resume"):
            assert types[t] > 0, (run.spec.slug, t)
        ids = [r["id"] for r in run.rows]
        assert len(set(ids)) == len(ids)


def _first_active_by_day(truth):
    first = {}
    for s in truth["states"]:
        if s["state"] == "ACTIVE":
            d = s["t0"][:10]
            h = _dt(s["t0"]).hour + _dt(s["t0"]).minute / 60
            if d not in first:
                first[d] = h
    return first


def _day_kinds(truth):
    return {d["date"]: d for d in truth["daily"]}


def test_schedule_change_on_day_15(runs):
    t = runs["nine-to-five"].truth
    first, kinds = _first_active_by_day(t), _day_kinds(t)
    pre = [h for d, h in first.items() if kinds[d]["kind"] == "normal" and kinds[d]["phase"] == "pre"]
    post = [h for d, h in first.items() if kinds[d]["kind"] == "normal" and kinds[d]["phase"] == "post"]
    assert len(pre) >= 8 and len(post) >= 4
    assert statistics.mean(pre) - statistics.mean(post) == pytest.approx(1.0, abs=0.6)   # starts an hour earlier
    t = runs["night-owl"].truth
    first, kinds = _first_active_by_day(t), _day_kinds(t)
    pre = [h for d, h in first.items() if kinds[d]["kind"] == "normal" and kinds[d]["phase"] == "pre" and 11 <= h <= 17]
    post = [h for d, h in first.items() if kinds[d]["kind"] == "normal" and kinds[d]["phase"] == "post" and 8 <= h <= 14]
    assert statistics.mean(pre) - statistics.mean(post) > 2.0                             # the owl starts earlier


def test_truth_schedule_recoverable_from_events(runs):
    """CAP-9: the planted windows can be recovered from the events (first human event of a normal day)."""
    run = runs["nine-to-five"]
    by_day: dict[str, float] = {}
    for r in run.rows:
        if r["actor"] == "human" and r["source"] != "os":
            by_day.setdefault(r["t"][:10], _dt(r["t"]).hour + _dt(r["t"]).minute / 60)
    errs = []
    for d in run.truth["daily"]:
        if d["kind"] == "normal" and d["windows"] and d["date"] in by_day:
            errs.append(abs(by_day[d["date"]] - d["windows"][0][0]))
    assert len(errs) >= 12 and statistics.median(errs) < 1.0


def test_sick_day_and_holiday(runs):
    for slug, run in runs.items():
        truth = run.truth
        assert truth["sick_day"] and truth["holiday"] and truth["sick_day"]["day"] != truth["holiday"]["day"]
        per_day = Counter(r["t"][:10] for r in run.rows if r["source"] == "browser")
        normal = [per_day[d["date"]] for d in truth["daily"] if d["kind"] == "normal"]
        if not normal:
            continue
        med = statistics.median(normal)
        assert per_day[truth["sick_day"]["date"]] < 0.6 * med, slug
        assert per_day[truth["holiday"]["date"]] < 0.35 * med, slug


def test_stuck_hazard_depends_on_improving_skill(runs):
    for slug, run in runs.items():
        sk = run.truth["skill"]["by_day"]
        assert len(sk) == 21 and sk[-1] > sk[0] + 0.25 and all(b >= a - 1e-9 for a, b in zip(sk, sk[1:])), slug
    # pooled over personas: stuck episodes per task fall from week 1 to week 3
    tasks = defaultdict(int)
    stuck = defaultdict(int)
    for run in runs.values():
        daily = {d["date"]: d["day"] for d in run.truth["daily"]}
        for r in run.rows:
            if r["type"] == "task_start":
                tasks[min(2, (daily[r["t"][:10]] - 1) // 7)] += 1
        for e in run.truth["stuck_episodes"]:
            stuck[min(2, (daily[e["t0"][:10]] - 1) // 7)] += 1
    rate = {w: stuck[w] / tasks[w] for w in range(3)}
    assert rate[0] > 1.5 * rate[2], rate


def test_stuck_episodes_have_no_progress_inside(runs):
    run = runs["nine-to-five"]
    prog = sorted(_dt(r["t"]).timestamp() for r in run.rows if r["type"] == "progress")
    import bisect

    bad = 0
    for e in run.truth["stuck_episodes"]:
        a, b = _dt(e["t0"]).timestamp(), _dt(e["t1"]).timestamp()
        i = bisect.bisect_left(prog, a + 1.0)
        if i < len(prog) and prog[i] < b - 1.0:
            bad += 1
    assert bad == 0 and len(run.truth["stuck_episodes"]) > 20


def test_planted_routines_present_with_parameters(runs):
    for slug, run in runs.items():
        names = {r["name"] for r in run.truth["routines"]}
        assert len(names) == 3
        for r in run.truth["routines"]:
            assert r["rate_per_day"] > 0 and r["nominal_cogs"] and 0 <= r["judgement_share"] <= 1
        assert sum(r["n_instances"] for r in run.truth["routines"]) >= 40, slug
    # an instance of calc-entry-3x visits at least two calculator sites and reads results
    run = runs["nine-to-five"]
    inst = next(r for r in run.truth["routines"] if r["name"] == "calc-entry-3x")["instances"][0]
    rows = [r for r in run.rows if r.get("task_id") == inst["task_id"]]
    assert sum(1 for r in rows if r.get("meta", {}).get("zone") == "calc_site") >= 2
    assert any(r["type"] == "progress" and r["meta"]["kind"] == "result_read" for r in rows)


def test_presence_truth_present_with_mc():
    run = simulate_persona(PERSONA_BY_SLUG["nine-to-five"], with_mc=True)
    pre = run.truth["expected_active_prob"]["pre"]
    assert len(pre) == 7 and len(pre[0]) == 96
    # weekday 10:00 slot is likely active, 03:00 is not, Sunday 10:00 is not
    assert pre[1][40] > 0.6 and pre[1][12] < 0.05 and pre[6][40] < 0.1
    assert run.truth["state_hours_per_week"]["pre"]["ACTIVE"] > 20


def test_synthetic_salt_is_fixed_so_hashes_repeat(runs):
    hashes = {r["target"]["label_hash"] for r in runs["irregular"].rows if r.get("target", {}).get("label_hash")}
    assert 5 < len(hashes) < 80          # a small fixed vocabulary of hashed labels
