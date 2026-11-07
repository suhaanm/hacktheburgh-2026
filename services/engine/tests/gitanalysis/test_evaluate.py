from __future__ import annotations

import json
import os
import re

import pytest

from understudy_engine.gitanalysis.evaluate import evaluate_git
from understudy_engine.gitanalysis.features import HABIT_IDS


@pytest.fixture(scope="module")
def result():
    return evaluate_git(fast=True)


def test_shape_meta_and_statement(result):
    m = result["meta"]
    assert m["origin"] == "synthetic" and m["n_unit"] == "personas" and m["n"] == 36 and m["interval_level"] == 0.95 and m["split"] and m["note"]
    assert "No real people" in result["statement"] and result["status"] == "ok"
    assert {"habit_recovery", "placebo", "digest_accuracy", "digest_agreement", "genome", "leak_canary", "real_world", "limitations"} <= set(result)


def test_planted_habit_recovery_with_intervals(result):
    r = result["habit_recovery"]
    assert r["design"]["replicates"] == [100, 101, 102] and r["design"]["pairs"] == 72
    o = r["overall"]
    assert o["precision"]["value"] >= 0.85 and o["recall"]["value"] >= 0.8
    assert o["precision"]["ci"][0] <= o["precision"]["value"] <= o["precision"]["ci"][1]
    assert set(r["by_habit"]) == set(HABIT_IDS)
    assert r["dose_response"] and r["dose_response"][0]["recall"]["value"] <= o["recall"]["value"] + 0.05   # weaker plants are found less often


def test_stress_arm_is_reported(result):
    st = result["habit_recovery"]["stress_double_between_person_variation"]
    assert st["replicates"] == [100, 101, 102] and st["precision"]["n"] >= 1 and st["placebo_false_flags"]["n"] >= 100
    for k in ("precision", "recall", "specificity"):
        assert st[k]["ci"][0] <= st[k]["value"] <= st[k]["ci"][1]


def test_digest_agreement_with_a_model_present(monkeypatch, cohort):
    """With a (fake) model that agrees on size and tests but not on categories, the agreement section reports it."""
    import types

    from understudy_engine.gitanalysis import digest as dg
    from understudy_engine.gitanalysis import evaluate as ev
    from understudy_engine.gitanalysis import service

    def fake_ex(items, *, force_rules=False, client=None):
        from understudy_engine.localmodel.digest import commit_digest_ex as real
        b = real(items, force_rules=True)
        digs = [dict(d, category="feature" if i % 2 else d["category"]) for i, d in enumerate(b.digests)]
        return types.SimpleNamespace(digests=digs, per_item_source=["model"] * len(digs), fallbacks={})

    monkeypatch.setattr(dg, "_localmodel", lambda: types.SimpleNamespace(commit_digest_ex=lambda items, force_rules=False: (
        fake_ex(items) if not force_rules else __import__("understudy_engine.localmodel.digest", fromlist=["x"]).commit_digest_ex(items, force_rules=True))))
    monkeypatch.setattr(service, "model_available", lambda: True)
    out = ev._digest_agreement(cohort, 40)
    assert out["status"] == "ok" and out["n_commits"] == 40 and out["model_share"] == 1.0
    assert out["agreement"]["size_bucket"]["value"] == 1.0 and out["agreement"]["touches_tests"]["value"] == 1.0
    assert out["agreement"]["category"]["value"] < 1.0 and "not accuracy" in out["note"]


def test_placebo_near_zero(result):
    p = result["placebo"]
    assert p["pairs"] >= 100 and p["false_flags"]["value"] <= 0.08
    assert max(v for v in p["mean_abs_delta_by_habit"].values() if v is not None) < 0.12


def test_digest_accuracy_is_reported_not_flattered(result):
    d = result["digest_accuracy"]
    assert d["accuracy"]["size_bucket"]["value"] == 1.0 and d["accuracy"]["touches_tests"]["value"] == 1.0
    assert 0.5 < d["accuracy"]["category"]["value"] < 0.97              # the paraphrased messages cost something
    assert "same agent" in d["caveat"]


def test_model_agreement_is_not_run_without_a_model(result):
    assert result["digest_agreement"]["status"] == "not_run" and "rules" in result["digest_agreement"]["reason"]


def test_leak_canary_result(result):
    c = result["leak_canary"]
    assert c["status"] == "ok" and c["leaked_tokens"] == 0 and c["planted_tokens"] >= 100 and c["requests"] >= c["runs"]
    assert c["ledger_complete_runs"] == c["runs"] and c["errors"] == 0


def test_real_world_is_aggregates_only(result):
    rw = result["real_world"]
    assert rw["status"] in ("ok", "not_run")
    if rw["status"] == "ok":
        assert rw["n_commits"] >= 1 and "aggregates only" in rw["what"]
        assert set(rw["habit_shares"]) == set(HABIT_IDS)
        assert not (set(rw) & {"commits", "messages", "authors", "paths", "shas"})


def test_limitations_register(result):
    ids = [l["id"] for l in result["limitations"]]
    assert len(ids) == len(set(ids)) >= 8
    assert all(l["severity"] in ("low", "medium", "high") and len(l["text"]) > 30 for l in result["limitations"])
    assert {"git-synthetic", "git-circularity", "git-no-outcome", "git-genome-modelled"} <= set(ids)


def test_no_text_or_ids_in_the_result(result):
    text = json.dumps(result)
    assert not re.search(r"\b[0-9a-f]{40}\b", text) and "@" not in text
    assert "src/" not in text and "tests/" not in text and ".py" not in text and "/Users/" not in text and "/private/" not in text


def test_evaluation_runs_in_a_private_data_dir_and_restores_the_environment(monkeypatch, tmp_path):
    from understudy_engine.gitanalysis.evaluate import _isolated_data_dir
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "mine"))
    with _isolated_data_dir() as d:
        assert os.environ["UNDERSTUDY_DATA_DIR"] == str(d) != str(tmp_path / "mine")
    assert os.environ["UNDERSTUDY_DATA_DIR"] == str(tmp_path / "mine") and not d.exists()
    monkeypatch.delenv("UNDERSTUDY_DATA_DIR")
    with _isolated_data_dir():
        pass
    assert "UNDERSTUDY_DATA_DIR" not in os.environ
