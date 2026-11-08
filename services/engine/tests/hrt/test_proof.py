"""The one-command live proof for the video: forecast before outcome, outcome after the horizon, a verified chain, an edit refused."""
from __future__ import annotations

import importlib.util

from understudy_engine.store.paths import repo_root


def _load():
    spec = importlib.util.spec_from_file_location("hrt_ledger_proof", repo_root() / "scripts" / "hrt_ledger_proof.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_proof_prints_the_four_facts_and_the_forgery_is_refused():
    t = {"now": 1_800_000_000.0}
    lines = _load().run(3.0, clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s))
    kinds = [x.split()[0] for x in lines]
    assert kinds == ["BEFORE", "AFTER", "SCORE", "CHAIN", "REWRITE"], lines
    assert "outcome: not yet known" in lines[0] and "written after the horizon" in lines[1]
    assert "refused" in lines[3] and "edited" in lines[3] and "NOT CAUGHT" not in " ".join(lines)
    assert "already has an outcome" in lines[4]
    assert "2027-" in lines[1] or "2026-" in lines[1] or "2025-" in lines[1]            # a timestamp is printed


def test_the_bin_is_picked_by_position_never_by_outcome_so_both_outcomes_occur_and_both_print_correctly():
    seen = set()
    for seed in range(9001, 9013):
        t = {"now": 1_800_000_000.0}
        lines = _load().run(1.0, seed=seed, clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s))
        assert [x.split()[0] for x in lines] == ["BEFORE", "AFTER", "SCORE", "CHAIN", "REWRITE"]
        seen.add("no progress" if "(no progress)" in lines[1] else "progress")
    assert seen == {"progress", "no progress"}, seen                                    # a forecast that turns out wrong is printed as plainly as one that turns out right
