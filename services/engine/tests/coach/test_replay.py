"""The coach replayed on the synthetic traces, event by event, as if the worker were doing the work live."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime

import pytest

from understudy_engine.coach import CoachBrain, StuckScorer
from understudy_engine.store import EventStore

COOLDOWN = 120.0


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


@pytest.fixture(scope="module")
def scorer(synth_root):
    s = StuckScorer(synth_root)
    s.warm(background=False)
    assert s.state == "ready"            # the hazard model is fitted on the synthetic personas and apprentices
    return s


def replay_people(root, people, scorer, tmp, exclude_types=()):
    """{person: [(event, decision), ...]} for every person, one fresh brain each, committing as it goes."""
    src = EventStore(root)
    evs = [e for e in src.read("synthetic") if e.person in people and e.type not in exclude_types]
    by = defaultdict(list)
    for e in evs:
        by[e.person].append(e)
    out = {}
    for person, es in sorted(by.items()):
        brain = CoachBrain(EventStore(tmp / person), scorer=scorer, tone="short")
        out[person] = [(e, brain.next_step(person, e.t, events=es[: i + 1])) for i, e in enumerate(es)]
    return out


@pytest.fixture(scope="module")
def apprentice_run(synth_root, scorer, tmp_path_factory):
    truth = json.loads((synth_root / "synthetic" / "apprentices" / "truth.json").read_text())
    people = {p["person"] for p in truth["people"]}
    return truth, replay_people(synth_root, people, scorer, tmp_path_factory.mktemp("rep_app"))


def acting(trace):
    return [(e, d) for e, d in trace if d.action != "silent"]


def test_ring_lands_on_the_cliff_button_in_the_planted_skipped_check_traces(apprentice_run):
    truth, run = apprentice_run
    skip = {t["task_id"] for t in truth["traces"] if any(d["type"] == "skipped_check_cliff" and d["instances"] for d in d_list(t))}
    assert len(skip) >= 10
    hit, lag = set(), []
    for person, trace in run.items():
        for e, d in acting(trace):
            if d.trigger == "expert_policy":
                assert d.action == "annotate" and d.target["zone"] == "cliff_button" and d.missed and d.missed[0].startswith("cliff_")
                assert d.message == "Check cliff edges before you reconcile the results." or d.message.startswith("Check cliff edges before you")
                hit.add(d.task_id)
                first = next(x for x, _ in trace if x.task_id == d.task_id and x.type == "tab" and x.meta.get("zone") == "results_tabs")
                lag.append((e.t - first.t).total_seconds())
    precision = len(hit & skip) / len(hit)
    recall = len(hit & skip) / len(skip)
    assert precision == 1.0, "no ring on a case that did the cliff checks"
    assert recall >= 0.9, (recall, sorted(skip - hit))
    assert max(lag) < 20.0, "the ring arrives within seconds of starting to reconcile"
    print(f"\n[coach replay, apprentices] ring on skipped cliff: precision {precision:.2f}, recall {recall:.2f} over {len(skip)} planted cases; lag max {max(lag):.1f}s")


def d_list(t):
    return t["deficits"]


def test_silent_for_every_expert_trace(apprentice_run):
    truth, run = apprentice_run
    experts = [p["person"] for p in truth["people"] if p["level"] == "expert"]
    assert len(experts) == 8
    for person in experts:
        assert not acting(run[person]), (person, [(d.trigger, d.message) for _, d in acting(run[person])])
    n = sum(len(run[p]) for p in experts)
    assert n > 1000
    print(f"\n[coach replay, apprentices] experts: 0 acting decisions over {n} polls, 16 cases")


def test_at_most_one_prompt_per_cooldown(apprentice_run):
    _, run = apprentice_run
    for person, trace in run.items():
        times = [e.t.timestamp() for e, _ in acting(trace)]
        assert all(b - a >= COOLDOWN for a, b in zip(times, times[1:])), person
    assert sum(len(acting(t)) for t in run.values()) >= 10


def test_every_acting_decision_is_recorded_and_explained(apprentice_run):
    _, run = apprentice_run
    for person, trace in run.items():
        for e, d in acting(trace):
            assert d.decision_id and d.message and d.why and d.reason_codes and d.confidence >= 0.5
            assert d.level in ("L1", "L2", "L3", "L4") and d.chip in ("full", "small", "dot", "gone")
            if d.action == "annotate":
                assert d.target and d.target["zone"]


@pytest.fixture(scope="module")
def learner_run(synth_root, scorer, tmp_path_factory):
    truth = json.loads((synth_root / "synthetic" / "learners" / "truth.json").read_text())
    people = {p["person"] for p in truth["people"]}
    # the dataset's own coach events are kept: the brain must ignore events it did not write
    return truth, replay_people(synth_root, people, scorer, tmp_path_factory.mktemp("rep_learn"))


def test_false_nudges_per_hour_on_the_learners(learner_run):
    truth, run = learner_run
    traces = {t["task_id"]: t for t in truth["traces"]}
    blocks = defaultdict(list)
    for t in truth["traces"]:
        cur = _ts(t["t0"])
        for cog, dur, tag in t["cogs"]:
            if tag in ("search_loop", "repeated_read_result", "idle_before_enter"):
                blocks[t["task_id"]].append((cur, cur + dur))
            cur += dur
    stats = Counter()
    for person, trace in run.items():
        for e, d in acting(trace):
            tr = traces[d.task_id]
            if d.trigger == "expert_policy":
                ok = any(x["type"] == "skipped_check_cliff" and x["instances"] for x in tr["deficits"])
            else:
                ok = any(a - 5 <= e.t.timestamp() <= b + 30 for a, b in blocks.get(d.task_id, []))
            stats["true" if ok else "false"] += 1
    hours = sum(t["duration_s"] for t in truth["traces"]) / 3600
    n_cases = len(truth["traces"])
    n_acts = stats["true"] + stats["false"]
    per_hour = stats["false"] / hours
    print(f"\n[coach replay, learners] n = {n_cases} cases, 3 learners, {hours:.1f} working hours: {n_acts} acting decisions, "
          f"{stats['false']} false -> {per_hour:.2f} false nudges per hour (precision {stats['true'] / max(1, n_acts):.2f})")
    assert n_cases == 90 and n_acts >= 10
    assert per_hour <= 0.5
    assert stats["true"] / n_acts >= 0.85


def test_help_lightens_as_the_learners_improve(learner_run):
    _, run = learner_run
    levels = defaultdict(Counter)
    for trace in run.values():
        for e, d in acting(trace):
            if d.trigger == "expert_policy":
                levels["early" if int(d.task_id.split("_")[-1]) <= 10 else "later"][d.level] += 1
    assert levels["early"]["L1"] >= 1
    assert sum(levels["later"].values()) >= 1
    assert levels["early"]["L2"] + levels["later"]["L2"] >= 1                 # the level engine moved someone off full help


def strip_markers(events):
    return [e.model_copy(update={"task_id": None}) for e in events if e.type not in ("task_start", "task_end", "progress")]


def test_replay_without_task_markers_gives_the_same_rings_and_silent_experts(synth_root, scorer, tmp_path):
    """The zone fallback: the same traces with task_start, task_end, progress and task ids removed."""
    truth = json.loads((synth_root / "synthetic" / "apprentices" / "truth.json").read_text())
    skip = {t["task_id"] for t in truth["traces"] if any(d["type"] == "skipped_check_cliff" and d["instances"] for d in t["deficits"])}
    by_person = defaultdict(list)
    for e in EventStore(synth_root).read("synthetic"):
        if e.person.startswith(("p_exp", "p_nov")):
            by_person[e.person].append(e)
    rings, expert_acts, polls = 0, 0, 0
    for person, evs in sorted(by_person.items()):
        bare = strip_markers(evs)
        brain = CoachBrain(EventStore(tmp_path / person), scorer=scorer, tone="short")
        for i, e in enumerate(bare):
            d = brain.next_step(person, e.t, events=bare[: i + 1])
            polls += 1
            if d.action != "silent":
                if person.startswith("p_exp"):
                    expert_acts += 1
                elif d.trigger == "expert_policy":
                    rings += 1
                    assert d.action == "annotate" and d.target["zone"] == "cliff_button" and "implicit_task" in d.reason_codes
    assert expert_acts == 0
    # with markers the replay rang on 14 planted cases; without them the same cases (one ring each) are found
    assert rings >= int(0.9 * len(skip)) and rings <= len(skip)
    print(f"\n[coach replay, no task markers] {rings} rings over {len(skip)} planted skipped-cliff cases, {expert_acts} acting decisions on experts over {polls} polls")
