"""Simulated results must never be written under the live study's folder, nor through a symlink; every results folder carries PROVENANCE.json."""
from __future__ import annotations

import json
import os

import pytest

from evals.study_sim import analysis_io
from evals.study_sim.analysis_io import UnsafeOutputDir, check_output_dir, write_provenance, write_provenance_tree


def test_refuses_the_live_study_folder_and_everything_under_it():
    live = analysis_io.LIVE_STUDY_DIR
    for p in (live, live / "results", live / "results" / "raw", live / "results" / "participants.csv"):
        with pytest.raises(UnsafeOutputDir):
            check_output_dir(p)
    with pytest.raises(UnsafeOutputDir):
        check_output_dir(live / "results" / ".." / "results")                         # dot-dot back into it
    with pytest.raises(UnsafeOutputDir):
        write_provenance(live / "results")
    assert not (live / "results" / "PROVENANCE.json").exists()


def test_refuses_a_relative_path_that_resolves_into_the_live_study(monkeypatch):
    monkeypatch.chdir(analysis_io.LIVE_STUDY_DIR.parent)
    with pytest.raises(UnsafeOutputDir):
        check_output_dir("study/results")
    with pytest.raises(UnsafeOutputDir):
        check_output_dir("study_sim/../study/results")


def test_refuses_symlinks_in_the_path_and_the_link_target_is_not_followed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(real, link)
    with pytest.raises(UnsafeOutputDir):
        check_output_dir(link)
    with pytest.raises(UnsafeOutputDir):
        check_output_dir(link / "sub")
    # a symlink that points INTO the live study is refused as a symlink before its target is even considered
    evil = tmp_path / "evil"
    os.symlink(analysis_io.LIVE_STUDY_DIR / "results", evil)
    with pytest.raises(UnsafeOutputDir):
        write_provenance(evil)
    assert not (analysis_io.LIVE_STUDY_DIR / "results" / "PROVENANCE.json").exists()


def test_provenance_is_written_in_every_folder(tmp_path):
    root = tmp_path / "results"
    write_provenance(root / "raw" / "p_sim01")
    (root / "checks").mkdir()
    n = write_provenance_tree(root)
    dirs = [root, root / "raw", root / "raw" / "p_sim01", root / "checks"]
    assert n == len(dirs)
    for d in dirs:
        prov = json.loads((d / "PROVENANCE.json").read_text())
        assert prov == {"origin": "simulated_participants_llm", "label": "simulated participants (language model), not people"}


def test_the_harness_entry_points_refuse_the_live_study(tmp_path):
    import asyncio

    from evals.study_sim import __main__ as m
    with pytest.raises(UnsafeOutputDir):
        asyncio.run(m._run_many([], lambda s: None, analysis_io.LIVE_STUDY_DIR / "results", "x", None, worlds=[], pace=0, cap=1, poll_s=1, skip_done=set()))
    from evals.study_sim import report
    with pytest.raises(UnsafeOutputDir):
        report.write_all(analysis_io.LIVE_STUDY_DIR / "results")
    ok = tmp_path / "results"
    ok.mkdir()
    s = report.write_all(ok)
    assert s["status"] == "not_run" and (ok / "PROVENANCE.json").exists() and (ok / "summary.json").exists()
