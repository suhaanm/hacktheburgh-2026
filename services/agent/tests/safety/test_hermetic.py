"""The safety tests must never touch shared state: a stale data/KILL would make the demo services refuse to run."""
from __future__ import annotations

import os
import pathlib

from understudy_agent.audit import AuditLog
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security import paths
from understudy_agent.security.killflag import clear_kill, is_killed, set_kill
from understudy_agent.security.settings import Origin

REAL_DATA = paths.repo_root() / "data"


def test_every_shared_path_resolves_inside_the_per_test_tmp_dir(tmp_path):
    for p in (paths.data_dir(), paths.queue_dir(), paths.audit_path(), paths.kill_path(), paths.runs_dir()):
        assert str(p).startswith(str(tmp_path.resolve())) or str(p).startswith(str(tmp_path)), p
        assert REAL_DATA.resolve() not in p.resolve().parents and p.resolve() != REAL_DATA.resolve()
    assert os.environ["UNDERSTUDY_HOME"].startswith(str(tmp_path))


def test_kill_flag_round_trip_never_touches_the_real_one():
    real = REAL_DATA / "KILL"
    before = real.exists()
    set_kill("hermetic test")
    assert is_killed() and real.exists() == before
    clear_kill()
    assert not is_killed() and real.exists() == before


def test_queue_and_audit_defaults_write_only_under_tmp(tmp_path):
    q = ApprovalQueue(audit=AuditLog())
    item = q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible")
    q.approve(item["id"], origin=Origin.HUMAN_UI)
    assert (tmp_path / "data" / "queue" / f"{item['id']}.json").exists() and (tmp_path / "data" / "audit.jsonl").exists()
    assert not (REAL_DATA / "queue" / f"{item['id']}.json").exists()


def test_voice_status_does_not_create_directories_even_in_tmp(tmp_path):
    from understudy_agent.voice import status

    status()
    assert not (tmp_path / "data" / "voice_cache").exists()


def test_environment_changes_do_not_leak_between_tests_a():
    os.environ["SAFETY_TEST_LEAK_CHECK"] = "1"  # set directly, not through monkeypatch


def test_environment_changes_do_not_leak_between_tests_b():
    assert "SAFETY_TEST_LEAK_CHECK" not in os.environ


def test_dotenv_cannot_load_a_real_env_file_into_a_test(tmp_path):
    import dotenv

    f = pathlib.Path(tmp_path) / ".env"
    f.write_text("SAFETY_DOTENV_LEAK=1\n")
    dotenv.load_dotenv(f)
    assert "SAFETY_DOTENV_LEAK" not in os.environ
