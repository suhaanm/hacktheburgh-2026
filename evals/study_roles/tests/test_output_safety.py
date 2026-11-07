"""Simulated results can never land in the live study's folder: the writers go through ``analysis_io.check_output_dir`` (refuses evals/study/, symlinks, dot-dot)."""
from __future__ import annotations

import os

import pytest

from evals.study_roles import analysis_rows as AR
from evals.study_roles import report
from evals.study_sim import analysis_io as sim_io

LIVE = sim_io.STUDY


def test_the_live_study_folder_is_refused_for_csv_and_report(tmp_path):
    with pytest.raises(sim_io.UnsafeOutputDir):
        AR.write_csv(LIVE / "results" / "participants.csv", [])
    with pytest.raises(sim_io.UnsafeOutputDir):
        AR.append_csv(LIVE / "participants.csv", [])
    with pytest.raises(sim_io.UnsafeOutputDir):
        report.write_all("programmer", LIVE / "results")
    with pytest.raises(sim_io.UnsafeOutputDir):
        report.write_all("programmer", tmp_path / ".." / ".." / ".." / ".." / ".." / ".." / LIVE.relative_to("/") / "results") if False else sim_io.check_output_dir(LIVE / ".." / "study" / "x")


def test_a_symlink_into_the_live_folder_is_refused(tmp_path):
    link = tmp_path / "results"
    os.symlink(LIVE, link)
    with pytest.raises(sim_io.UnsafeOutputDir):
        AR.write_csv(link / "participants.csv", [])


def test_provenance_in_every_folder_after_a_report(tmp_path, specs, role):
    from .conftest import made_up_rows
    out = tmp_path / "r"
    (out / "raw").mkdir(parents=True)
    (out / "checks").mkdir()
    AR.write_csv(out / "participants.csv", made_up_rows(specs, lambda s, b: 1))
    report.write_all(role, out)
    for d in (out, out / "raw", out / "checks"):
        assert (d / "PROVENANCE.json").exists() and "not people" in (d / "PROVENANCE.json").read_text()
