from __future__ import annotations

import json
from collections import Counter

import pytest

from understudy_engine.personas import apprentices
from understudy_engine.personas.apprentices import DEFICIT_ORDER, expert_median_s
from understudy_engine.store import EventStore


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    info = apprentices.generate(root)
    truth = json.loads((root / "synthetic" / "apprentices" / "truth.json").read_text())
    return root, info, truth


def test_counts_and_files(gen):
    root, info, truth = gen
    levels = Counter(t["level"] for t in truth["traces"])
    assert levels["expert"] >= 6 and levels["novice"] >= 12
    evs = EventStore(root).read("synthetic")
    assert len(evs) == info["events"] and {e.origin for e in evs} == {"synthetic"}
    types = Counter(e.type for e in evs)
    for t in ("task_start", "task_end", "progress", "stuck", "nav", "copy", "paste", "undo", "idle", "search"):
        assert types[t] > 0, t
    assert types["task_start"] == types["task_end"] == len(truth["traces"])


def test_each_deficit_present_and_absent_enough(gen):
    _, _, truth = gen
    novices = [p for p in truth["people"] if p["level"] == "novice"]
    for d in DEFICIT_ORDER:
        with_d = sum(d in p["deficits"] for p in novices)
        assert with_d >= 5 and len(novices) - with_d >= 5, (d, with_d)
        assert truth["deficit_totals"][d]["mean_price_s_when_present"] > 10
    assert all(p["deficits"] == [] for p in truth["people"] if p["level"] == "expert")


def test_price_accounting_is_exact(gen):
    """duration = baseline + sum(price) + the 0.2 s task_end tail: the truth is consistent by construction."""
    _, _, truth = gen
    for t in truth["traces"]:
        assert t["duration_s"] == pytest.approx(t["baseline_s"] + t["price_total_s"] + 0.2, abs=0.35), t["task_id"]
        seq_total = sum(d for _, d, _ in t["cogs"])
        assert seq_total == pytest.approx(t["duration_s"] - 0.2, abs=0.01 * len(t["cogs"]) + 0.5)
        for d in t["deficits"]:
            assert d["price_s"] == pytest.approx(d["added_s"] - d["saved_s"], abs=0.02)
        assert t["baseline_s"] - t["expert_median_s"] == pytest.approx(t["slowness_s"], abs=0.02)


def test_deficit_cog_signatures(gen):
    _, _, truth = gen
    for t in truth["traces"]:
        names = {d["type"] for d in t["deficits"]}
        cogs = [c for c, _, _ in t["cogs"]]
        assert ("REVERT" in cogs) == bool(names & {"skipped_check_cliff", "copy_error"}), t["task_id"]
        if "search_loop" in names:
            assert "SEARCH" in cogs and "REFORMULATE" in cogs
        else:
            assert "SEARCH" not in cogs
        if "idle_before_enter" in names:
            assert "IDLE" in cogs
        if "skipped_check_cliff" in names:
            assert cogs.count("CHECK_CLIFF") >= 3 or t["order_variant"] == "A"
        if t["level"] == "expert":
            assert cogs.count("CHECK_CLIFF") == 3 and cogs.count("READ_RESULT") == 3 and cogs.count("OPEN_CALCULATOR") == 3
            assert cogs[-1] == "COPY_TO_NOTE" and cogs[-2] == "RECONCILE"


def test_novices_slower_than_experts_by_more_than_deficits_alone(gen):
    _, _, truth = gen
    ex = [t["duration_s"] for t in truth["traces"] if t["level"] == "expert"]
    nv = [t["duration_s"] for t in truth["traces"] if t["level"] == "novice"]
    assert sum(nv) / len(nv) > 1.3 * sum(ex) / len(ex)
    assert expert_median_s(1.45) > expert_median_s(1.0)
    # experts: no deficit price; their only gap to the median is natural variation
    assert all(t["price_total_s"] == 0 for t in truth["traces"] if t["level"] == "expert")


def test_expert_reordering_variant_is_marked(gen):
    _, _, truth = gen
    variants = Counter(p["order_variant"] for p in truth["people"] if p["level"] == "expert")
    assert variants == {"A": 6, "B": 2}


def test_generation_is_deterministic(tmp_path, gen):
    root, _, _ = gen
    apprentices.generate(tmp_path)
    for name in ("events.jsonl", "truth.json"):
        assert (tmp_path / "synthetic" / "apprentices" / name).read_bytes() == (root / "synthetic" / "apprentices" / name).read_bytes()
