from __future__ import annotations

import json
import statistics
from collections import Counter

import pytest

from understudy_engine.cli import main
from understudy_engine.cogs import segment_episodes
from understudy_engine.personas import learners
from understudy_engine.store import EventStore


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    root = tmp_path_factory.mktemp("learners")
    info = learners.generate(root)
    truth = json.loads((root / "synthetic" / "learners" / "truth.json").read_text())
    return root, info, truth


def traces(truth, person):
    return sorted((t for t in truth["traces"] if t["person"] == person), key=lambda t: t["case"])


def test_shape_three_learners_thirty_cases_each(gen):
    root, info, truth = gen
    assert [p["person"] for p in truth["people"]] == ["p_learn01", "p_learn02", "p_learn03"]
    for p in truth["people"]:
        ts = traces(truth, p["person"])
        assert len(ts) == 30 and ts[0]["task_id"] == f"t_{p['person'][2:]}_01" and ts[-1]["task_id"].endswith("_30")
    evs = EventStore(root).read("synthetic")
    assert len(evs) == info["events"] and {e.origin for e in evs} == {"synthetic"} and {e.person for e in evs} == {"p_learn01", "p_learn02", "p_learn03"}
    types = Counter(e.type for e in evs)
    assert types["task_start"] == types["task_end"] == 90
    for t in ("coach_shown", "coach_followed", "coach_dismissed", "progress", "stuck", "idle", "undo"):
        assert types[t] > 0, t
    assert {e.source for e in evs if e.type.startswith("coach_")} == {"coach"}
    assert (root / "synthetic" / "learners" / "truth.json").exists()


def test_about_three_cases_a_day_over_ten_days(gen):
    _, _, truth = gen
    for person in ("p_learn01", "p_learn03"):
        by_day = Counter(t["day"] for t in traces(truth, person))
        assert set(by_day.values()) == {3} and max(by_day) == 10
    l2 = traces(truth, "p_learn02")
    assert Counter(t["day"] for t in l2).keys() >= {1, 5, 9, 13} and 6 not in {t["day"] for t in l2} and 7 not in {t["day"] for t in l2} and 8 not in {t["day"] for t in l2}
    assert l2[15]["day"] - l2[14]["day"] == 4                      # a three-day absence after case 15


def test_deficit_probability_decays_with_practice_per_the_planted_curve(gen):
    _, _, truth = gen
    mech = truth["mechanism"]["deficit_params"]
    for p in truth["people"]:
        ts = traces(truth, p["person"])
        first = statistics.fmean(sum(t["p_deficit"].values()) for t in ts[:5])
        last = statistics.fmean(sum(t["p_deficit"].values()) for t in ts[-5:])
        assert last < 0.5 * first, (p["person"], first, last)
        assert ts[-1]["skill"] > ts[0]["skill"] + 0.5 and ts[0]["skill"] == 0.0
        # the recorded probability is exactly the formula on the recorded effective practice
        for t in ts:
            for d, pr in t["p_deficit"].items():
                q = mech[d]
                assert pr == pytest.approx(q["p0"] * (1 + t["n_eff"][d] / q["n0"]) ** (-q["alpha"]), abs=1e-4)
    # the simulated occurrences follow the probabilities: more deficits early than late, pooled over learners
    early = sum(len([d for d in t["deficits"] if d["instances"]]) for p in truth["people"] for t in traces(truth, p["person"])[:10])
    late = sum(len([d for d in t["deficits"] if d["instances"]]) for p in truth["people"] for t in traces(truth, p["person"])[-10:])
    assert early > 1.6 * late
    # and the cases get faster
    for p in truth["people"]:
        ts = traces(truth, p["person"])
        assert statistics.fmean(t["duration_s"] for t in ts[-5:]) < 0.9 * statistics.fmean(t["duration_s"] for t in ts[:5])


def test_coach_help_speeds_the_decline(gen):
    """After a case where the deficit appeared and its prompt was shown and followed, n_eff jumps by the boost."""
    _, _, truth = gen
    boost = truth["mechanism"]["coach_boost"]
    helped = unhelped = 0
    for p in truth["people"]:
        ts = traces(truth, p["person"])
        for a, b in zip(ts, ts[1:]):
            if b["day"] - a["day"] > 1 and p["absence"]:
                continue
            for c in a["coach"]:
                step = b["n_eff"][c["deficit"]] - a["n_eff"][c["deficit"]]
                if c["helped"]:
                    helped += 1
                    assert step == pytest.approx(p["rate"] * (1 + boost), abs=2e-3)
                else:
                    assert step == pytest.approx(p["rate"], abs=2e-3)
                    unhelped += 1
    assert helped >= 15 and unhelped >= 15
    # the pair is in the events for every helped case
    ids = {(t["task_id"]) for p in truth["people"] for t in traces(truth, p["person"]) if any(c["helped"] for c in t["coach"])}
    assert len(ids) >= 15


def test_coach_events_come_in_shown_followed_pairs(gen):
    root, _, truth = gen
    evs = EventStore(root).read("synthetic")
    by_task: dict[str, list] = {}
    for e in evs:
        if e.type.startswith("coach_"):
            by_task.setdefault(e.task_id, []).append(e)
    for t in truth["traces"]:
        helped = sum(c["helped"] for c in t["coach"])
        followed_events = sum(1 for e in by_task.get(t["task_id"], []) if e.type == "coach_followed")
        shown_events = sum(1 for e in by_task.get(t["task_id"], []) if e.type == "coach_shown")
        assert followed_events == helped and shown_events == sum(c["shown"] for c in t["coach"])
        for e in by_task.get(t["task_id"], []):
            assert t["t0"] <= e.t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z" <= t["t1"] or e.type != "coach_shown"


def test_absence_partly_restores_the_deficit_probability(gen):
    _, _, truth = gen
    ts = traces(truth, "p_learn02")
    before, after = sum(ts[14]["p_deficit"].values()), sum(ts[15]["p_deficit"].values())
    assert after > before * 1.1                                            # forgetting: it gets worse over the break ...
    assert after < sum(ts[0]["p_deficit"].values()) * 0.6                  # ... but only part of the way back to the start
    assert truth["people"][1]["absence"] == {"after_case": 15, "days": 3}
    # the other learners show no such jump anywhere
    for person in ("p_learn01", "p_learn03"):
        t = traces(truth, person)
        assert all(sum(b["p_deficit"].values()) <= sum(a["p_deficit"].values()) + 1e-9 for a, b in zip(t, t[1:]))


def test_events_map_to_the_planted_cog_sequences(gen):
    root, _, truth = gen
    planted = {t["task_id"]: [c for c, _, _ in t["cogs"]] for t in truth["traces"]}
    eps = segment_episodes(EventStore(root).read("synthetic"))
    assert len(eps) == 90
    for ep in eps:
        assert [c.id for c in ep.cogs] == planted[ep.task_id], ep.task_id


def test_deterministic_and_part_of_synth_all(tmp_path, gen):
    root, _, _ = gen
    learners.generate(tmp_path)
    for name in ("events.jsonl", "truth.json"):
        assert (tmp_path / "synthetic" / "learners" / name).read_bytes() == (root / "synthetic" / "learners" / name).read_bytes()
    out = tmp_path / "cli"
    assert main(["synth", "--learners", "--out", str(out)]) == 0
    assert (out / "synthetic" / "learners" / "events.jsonl").read_bytes() == (root / "synthetic" / "learners" / "events.jsonl").read_bytes()
    assert not (out / "synthetic" / "apprentices").exists()
