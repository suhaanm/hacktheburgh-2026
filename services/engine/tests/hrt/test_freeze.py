"""Freeze and the held-out gate: no token, no freeze, an edit after the freeze, or a second run are all refused (PLAN.md section 7)."""
from __future__ import annotations

import json

import pytest

from understudy_engine.hrt import freeze as fz
from understudy_engine.hrt import run as run_mod


@pytest.fixture()
def evals(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_EVALS_DIR", str(tmp_path))
    (tmp_path / "hrt").mkdir()
    (tmp_path / "hrt" / "PLAN.md").write_text("plan v1")
    monkeypatch.delenv("UNDERSTUDY_HRT_HELDOUT", raising=False)
    return tmp_path


def test_refuses_without_the_token_then_without_a_freeze(evals, monkeypatch):
    with pytest.raises(fz.Refused, match="UNDERSTUDY_HRT_HELDOUT=1"):
        fz.check_can_run_heldout("ledger")
    monkeypatch.setenv("UNDERSTUDY_HRT_HELDOUT", "1")
    with pytest.raises(fz.Refused, match="no freeze"):
        fz.check_can_run_heldout("ledger")
    with pytest.raises(fz.Refused, match="unknown part"):
        fz.check_can_run_heldout("everything")


def test_runs_after_a_freeze_and_refuses_after_the_plan_or_the_code_changes(evals, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_HRT_HELDOUT", "1")
    fz.freeze(("ledger",))
    hs = fz.check_can_run_heldout("ledger")
    assert "PLAN.md" in hs and "prospective.py" in hs and "run.py" in hs and "scoreboard.py" not in hs
    (evals / "hrt" / "PLAN.md").write_text("plan v2: edited after the freeze")
    with pytest.raises(fz.Refused, match="changed since the freeze.*PLAN.md"):
        fz.check_can_run_heldout("ledger")
    fz.freeze(("ledger",))                                        # a re-freeze (a dated amendment) makes it runnable again
    assert fz.check_can_run_heldout("ledger")
    # a part that was not frozen is still refused
    with pytest.raises(fz.Refused, match="no freeze for this part"):
        fz.check_can_run_heldout("decisions")


def test_a_started_part_is_refused_a_second_time_unless_amended(evals, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_HRT_HELDOUT", "1")
    fz.freeze()
    assert not fz.part_started("decisions")
    fz.append_log({"event": "start", "part": "decisions", "t": fz.now()})
    assert fz.part_started("decisions") and not fz.part_started("ledger")
    with pytest.raises(fz.Refused, match="already has a start line"):
        fz.check_can_run_heldout("decisions")
    assert fz.check_can_run_heldout("decisions", amended=True)
    assert fz.check_can_run_heldout("ledger")


def test_the_cli_refuses_with_exit_code_3_and_writes_no_log_line(evals, monkeypatch, capsys):
    assert run_mod.main(["heldout", "--part", "ledger"]) == 3
    assert "refused" in capsys.readouterr().err
    assert not fz.log_path().exists()
    monkeypatch.setenv("UNDERSTUDY_HRT_HELDOUT", "1")
    assert run_mod.main(["heldout", "--part", "decisions"]) == 3          # token set, but no freeze
    assert not fz.log_path().exists()


def test_every_frozen_part_of_the_repository_is_unchanged_since_its_freeze():
    """The held-out runs were made with the code and plan the freeze recorded. A later edit to any fingerprinted file or to a plan is allowed only as a dated
    amendment with a re-freeze; until then this fails and names the file, so a silent change to what a held-out result came from cannot happen."""
    from understudy_engine.store.paths import repo_root

    path = repo_root() / "evals" / "hrt" / "results" / "frozen.json"
    if not path.exists():
        pytest.skip("no freeze recorded")
    frozen = json.loads(path.read_text(encoding="utf-8"))
    for part, rec in frozen["parts"].items():
        now = fz.code_hashes(part)
        if fz.fingerprint(now) != rec["fingerprint"]:
            changed = sorted(k for k in set(now) | set(rec["hashes"]) if now.get(k) != rec["hashes"].get(k))
            pytest.fail(f"part {part} changed since its freeze: {', '.join(changed)}. If this is a declared amendment, re-freeze and say so in the plan's amendment log.")


def test_results_json_is_nan_safe(evals):
    import numpy as np

    p = evals / "hrt" / "results" / "x.json"
    fz.write_json(p, {"a": float("nan"), "b": np.float64(1.5), "c": np.arange(3), "d": [float("inf")]})
    assert json.loads(p.read_text()) == {"a": None, "b": 1.5, "c": [0, 1, 2], "d": [None]}
