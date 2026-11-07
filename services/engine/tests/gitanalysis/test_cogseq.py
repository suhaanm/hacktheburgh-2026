from __future__ import annotations

import pytest
import yaml

from understudy_engine.gitanalysis import cogseq
from understudy_engine.gitanalysis.records import CommitRecord, load_records
from understudy_engine.genome import align
from understudy_engine.packs import load_pack

MIN = 60.0


def rec(t, cat="feature", tests=False, bucket="small", parents=1):
    return CommitRecord(t=1_790_000_000 + t, tz_min=0, author_key="a_x", parents=parents, n_files=1, added=5, deleted=1, category=cat,
                        size_bucket=bucket, touches_tests=tests, risk="low", message_quality="ok")


def test_mapping_file_is_valid_and_names_exactly_the_five_cogs():
    mp = cogseq.load_mapping()
    assert mp["version"] == 1 and mp["cogs"] == ["CODE", "TEST", "REFACTOR", "COMMIT", "REVERT"]
    used = {c for r in mp["rules"] for c in r["cogs"]}
    assert used == set(mp["cogs"])
    for ex in mp["examples"]:
        d = ex["digest"]
        r = rec(0, d["category"], d["touches_tests"], d["size_bucket"])
        assert cogseq.commit_cogs(r) == ex["expect"], ex


def test_mapping_survives_the_pack_validator_and_the_pack_still_loads():
    import importlib.util
    root = cogseq.MAPPING_PATH.parent
    yaml.safe_load((root / "git_mapping.yaml").read_text())
    spec = importlib.util.spec_from_file_location("pack_validate", root.parent / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert load_pack("programmer").id == "programmer"


@pytest.mark.parametrize("cat,tests,expect", [
    ("feature", True, ["CODE", "TEST", "COMMIT"]), ("feature", False, ["CODE", "COMMIT"]), ("fix", False, ["CODE", "COMMIT"]),
    ("other", True, ["CODE", "TEST", "COMMIT"]), ("test", True, ["TEST", "COMMIT"]), ("refactor", False, ["REFACTOR", "COMMIT"]),
    ("revert", False, ["REVERT"]), ("docs", False, ["COMMIT"]), ("chore", True, ["COMMIT"])])
def test_commit_cogs(cat, tests, expect):
    assert cogseq.commit_cogs(rec(0, cat, tests)) == expect


def test_sessions_split_on_the_gap_and_skip_merges():
    rs = [rec(0), rec(30 * MIN), rec(60 * MIN, parents=2), rec(200 * MIN), rec(230 * MIN)]
    s = cogseq.sessions(rs, 90)
    assert [len(x) for x in s] == [2, 2]


def test_cog_segments_are_ordered_and_end_at_the_commit():
    sess = [rec(0, "feature", True, "large"), rec(40 * MIN, "fix"), rec(50 * MIN, "revert")]
    cogs = cogseq.session_cogs(sess, cogseq.load_mapping())
    assert [c.id for c in cogs] == ["CODE", "TEST", "COMMIT", "CODE", "COMMIT", "REVERT"]
    assert all(c.t1 >= c.t0 for c in cogs) and all(a.t1 <= b.t0 + 1e-6 for a, b in zip(cogs, cogs[1:]))
    assert cogs[2].t1 == sess[0].t and cogs[-1].t1 == sess[2].t
    # the first commit's work lasts lead_in_s for its size bucket (large: 3600 s), 70/30 between CODE and TEST
    assert cogs[0].dwell + cogs[1].dwell == pytest.approx(3600 - 30, abs=1)
    assert cogs[0].dwell == pytest.approx(0.7 * (3600 - 30), abs=1)


def test_episodes_feed_the_existing_alignment(learner_repo):
    recs, _ = load_records(learner_repo)
    eps = cogseq.to_episodes(recs, "p_x", seed=1)
    assert 1 <= len(eps) <= cogseq.load_mapping()["params"]["max_episodes_per_person"]
    assert all(e.cogs and e.role == "programmer" for e in eps)
    a = align(eps[0].cogs, eps[-1].cogs, cogseq.cost_model())
    assert a.columns and abs(sum(c.seconds for c in a.columns) - a.gap_s) < 1e-6          # columns account for the gap exactly


def test_code_and_refactor_are_a_family():
    cm = cogseq.cost_model()
    assert cm.mismatch("CODE", "REFACTOR") == 0.5 and cm.mismatch("CODE", "TEST") == 2.5 and cm.mismatch("CODE", "CODE") == 0.0


def test_genome_compare_runs_with_controls(cohort):
    L = {p: load_records(r)[0] for p, r in cohort["learners"].items()}
    E = {p: load_records(r)[0] for p, r in cohort["experts"].items()}
    out = cogseq.genome_compare(L, E, null_draws=40, boot=200)
    assert out["status"] == "ok" and out["shape"]["learner"]["n_people"] == 4 and out["shape"]["expert_placebo"]["n_people"] == 8
    assert set(out["cogs"]) <= {"CODE", "TEST", "REFACTOR", "COMMIT", "REVERT"}
    assert out["shape"]["null"]["draws"] == 40 and 0 < out["shape"]["null"]["p_value"] <= 1
    assert out["shape"]["learner"]["ci"][0] <= out["shape"]["learner"]["mean"] <= out["shape"]["learner"]["ci"][1]
    assert "gap_s" in out["seconds"]["real"] and "placebo" in out["seconds"]


def test_genome_compare_needs_enough_people(cohort):
    L = {p: load_records(r)[0] for p, r in list(cohort["learners"].items())[:1]}
    E = {p: load_records(r)[0] for p, r in list(cohort["experts"].items())[:2]}
    assert cogseq.genome_compare(L, E)["status"] == "not_run"
