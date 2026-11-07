"""M9: the retention sweep deletes old run screenshots, the voice cache and the debug replay folder, and never the ledger or the audit log."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from understudy_engine.privacy import ledger, retention
from understudy_engine.privacy.retention import sweep

DAY = 86400.0
NOW = 1_800_000_000.0


def touch(p: Path, age_days: float, size: int = 100) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    t = NOW - age_days * DAY
    os.utime(p, (t, t))
    return p


@pytest.fixture()
def tree(data_dir, tmp_path):
    t = {}
    t["old_shot"] = touch(data_dir / "runs/r_1/s1.png", 60)
    t["old_shot2"] = touch(data_dir / "runs/r_2/s3.png", 45, 500)
    t["new_shot"] = touch(data_dir / "runs/r_3/s1.png", 2)
    t["run_json"] = touch(data_dir / "runs/r_1/run.json", 90)             # an old run's own record stays
    t["artifact"] = touch(data_dir / "runs/r_1/artifacts/out.csv", 90)
    t["other_png"] = touch(data_dir / "runs/r_1/logo.png", 90)            # not a step screenshot (does not match s<N>.png)
    t["old_voice"] = touch(data_dir / "voice_cache/abc123.mp3", 40, 2000)
    t["old_voice_sub"] = touch(data_dir / "voice_cache/sub/def.wav", 100)
    t["new_voice"] = touch(data_dir / "voice_cache/new.mp3", 1)
    t["choice"] = touch(data_dir / "voice_cache/voice_choice.json", 400)  # a setting, never swept
    replay = tmp_path / "userData" / "replay"
    t["old_replay"] = touch(replay / "grounder-1.json", 50, 300)
    t["new_replay"] = touch(replay / "grounder-2.json", 3)
    t["replay_dir"] = replay
    # things that must never be touched however old
    t["ledger"] = touch(data_dir / "egress_ledger.jsonl", 900)
    t["blocked"] = touch(data_dir / "egress_blocked.jsonl", 900)
    t["meta"] = touch(data_dir / "egress_ledger_meta.json", 900)
    t["canary"] = touch(data_dir / "privacy_canary.json", 900)
    t["audit"] = touch(data_dir / "audit.jsonl", 900)
    t["queue"] = touch(data_dir / "queue/q_1.json", 900)
    t["kill"] = touch(data_dir / "KILL", 900)
    t["token"] = touch(data_dir / ".token", 900)
    t["golden"] = touch(data_dir / "golden/screenshots/s1.png", 900)
    t["synthetic"] = touch(data_dir / "synthetic/p/events.jsonl", 900)
    return t


NEVER = ("ledger", "blocked", "meta", "canary", "audit", "queue", "kill", "token", "golden", "synthetic", "choice", "run_json", "artifact", "other_png")


def test_dry_run_is_the_default_and_deletes_nothing_but_lists_exactly_the_old_files(data_dir, tree):
    before = {p for p in data_dir.rglob("*") if p.is_file()} | {p for p in tree["replay_dir"].rglob("*") if p.is_file()}
    rep = sweep(data_dir, 30, now=NOW, replay_dir=tree["replay_dir"])
    assert rep["dry_run"] is True and rep["deleted"] == [] and rep["bytes_freed"] == 0 and "Dry run" in rep["note"]
    assert {p for p in data_dir.rglob("*") if p.is_file()} | {p for p in tree["replay_dir"].rglob("*") if p.is_file()} == before
    got = {(c["category"], c["path"]) for c in rep["candidates"]}
    assert got == {("run_screenshot", "r_1/s1.png"), ("run_screenshot", "r_2/s3.png"), ("voice_cache", "abc123.mp3"), ("voice_cache", "sub/def.wav"),
                   ("debug_replay", "grounder-1.json")}
    assert rep["by_category"] == {"run_screenshot": {"files": 2, "bytes": 600}, "voice_cache": {"files": 2, "bytes": 2100}, "debug_replay": {"files": 1, "bytes": 300}}
    assert rep["bytes_candidates"] == 3000 and rep["max_age_days"] == 30.0
    ages = {c["path"]: c["age_days"] for c in rep["candidates"]}
    assert ages["r_1/s1.png"] == 60.0 and ages["abc123.mp3"] == 40.0


def test_apply_deletes_only_the_old_candidates_and_reports_the_bytes(data_dir, tree):
    rep = sweep(data_dir, 30, dry_run=False, now=NOW, replay_dir=tree["replay_dir"])
    assert rep["dry_run"] is False and len(rep["deleted"]) == 5 and rep["bytes_freed"] == 3000 and rep["errors"] == []
    for k in ("old_shot", "old_shot2", "old_voice", "old_voice_sub", "old_replay"):
        assert not tree[k].exists(), k
    for k in ("new_shot", "new_voice", "new_replay") + NEVER:
        assert tree[k].exists(), f"{k} must survive"
    again = sweep(data_dir, 30, dry_run=False, now=NOW, replay_dir=tree["replay_dir"])
    assert again["candidates"] == [] and again["deleted"] == []


def test_the_ledger_and_the_audit_log_survive_even_a_zero_day_sweep_of_everything(data_dir, tree):
    ledger.append({"purpose": "t.a", "payload": {}})
    rep = sweep(data_dir, 0, dry_run=False, now=NOW + DAY, replay_dir=tree["replay_dir"])
    for k in NEVER:
        assert tree[k].exists(), f"{k} was deleted by a zero-day sweep"
    assert (data_dir / "egress_ledger.jsonl").read_bytes().startswith(b"x") and (data_dir / "audit.jsonl").exists()
    assert not any(c["path"].endswith(("egress_ledger.jsonl", "audit.jsonl")) for c in rep["candidates"])
    assert tree["choice"].exists() and not tree["new_voice"].exists()


def test_a_symlink_is_never_followed_or_deleted(data_dir, tmp_path):
    target = touch(data_dir / "egress_ledger.jsonl", 900)
    (data_dir / "voice_cache").mkdir()
    os.symlink(target, data_dir / "voice_cache" / "link.mp3")
    shared = tmp_path / "shared_voice"
    touch(shared / "old.mp3", 500)
    demo = tmp_path / "demo-data"
    demo.mkdir()
    os.symlink(shared, demo / "voice_cache")                       # the demo data dir links voice_cache to the shared one
    rep = sweep(data_dir, 30, dry_run=False, now=NOW)
    assert target.exists() and (data_dir / "voice_cache" / "link.mp3").is_symlink()
    rep2 = sweep(demo, 30, dry_run=False, now=NOW)
    assert (shared / "old.mp3").exists() and rep2["candidates"] == [] and rep["deleted"] == []
    (data_dir / "runs").mkdir()
    os.symlink(shared, data_dir / "runs" / "r_9")
    touch(shared / "s1.png", 500)
    assert sweep(data_dir, 30, dry_run=False, now=NOW)["deleted"] == [] and (shared / "s1.png").exists()


def test_protected_directories_inside_the_voice_cache_and_replay_folders_are_not_entered(data_dir, tmp_path):
    keep = touch(data_dir / "voice_cache/queue/q_9.json", 900)
    keep2 = touch(data_dir / "voice_cache/golden/g.png", 900)
    replay = tmp_path / "replay"
    keep3 = touch(replay / "audit.jsonl", 900)
    keep4 = touch(replay / "synthetic" / "x.json", 900)
    gone = touch(replay / "ok.json", 900)
    sweep(data_dir, 1, dry_run=False, now=NOW, replay_dir=replay)
    assert keep.exists() and keep2.exists() and keep3.exists() and keep4.exists() and not gone.exists()


def test_files_in_run_folders_that_are_not_step_screenshots_stay(data_dir):
    keep = [touch(data_dir / "runs/r_1/run.json", 900), touch(data_dir / "runs/r_1/s1.json", 900), touch(data_dir / "runs/r_1/children/s2.png", 900),
            touch(data_dir / "runs/loose.png", 900), touch(data_dir / "runs/r_1/screenshot.png", 900)]
    gone = touch(data_dir / "runs/r_1/s12.png", 900)
    sweep(data_dir, 1, dry_run=False, now=NOW)
    assert all(k.exists() for k in keep) and not gone.exists()


def test_the_replay_folder_must_look_like_one_and_defaults_to_the_environment(data_dir, tmp_path, monkeypatch):
    home = tmp_path / "home_folder"
    f = touch(home / "important.txt", 900)
    with pytest.raises(ValueError, match="replay"):
        sweep(data_dir, 1, dry_run=False, now=NOW, replay_dir=home)
    assert f.exists()
    rp = tmp_path / "Replay-Files"
    old = touch(rp / "a.json", 900)
    monkeypatch.setenv("ALONGSIDE_REPLAY_DIR", str(rp))
    assert [c["category"] for c in sweep(data_dir, 1, now=NOW)["candidates"]] == ["debug_replay"]
    sweep(data_dir, 1, dry_run=False, now=NOW)
    assert not old.exists()
    monkeypatch.delenv("ALONGSIDE_REPLAY_DIR")
    assert sweep(data_dir, 1, now=NOW)["candidates"] == []


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "30", None])
def test_max_age_days_must_be_a_real_non_negative_number(data_dir, bad):
    with pytest.raises(ValueError, match="max_age_days"):
        sweep(data_dir, bad)       # type: ignore[arg-type]


def test_a_missing_data_dir_or_empty_one_is_fine(tmp_path):
    rep = sweep(tmp_path / "nowhere", 30)
    assert rep["candidates"] == [] and rep["scanned"] == 0 and rep["errors"] == []


def test_the_age_boundary_is_by_modification_time_and_exact(data_dir):
    on = touch(data_dir / "voice_cache/on.mp3", 30.0001)
    off = touch(data_dir / "voice_cache/off.mp3", 29.9)
    got = {c["path"] for c in sweep(data_dir, 30, now=NOW)["candidates"]}
    assert got == {"on.mp3"} and on.exists() and off.exists()


def test_it_defaults_to_the_current_data_dir_and_the_wall_clock(data_dir):
    p = touch(data_dir / "voice_cache/ancient.mp3", 0)
    os.utime(p, (time.time() - 100 * DAY, time.time() - 100 * DAY))
    rep = sweep(max_age_days=30)
    assert rep["dry_run"] is True and [c["path"] for c in rep["candidates"]] == ["ancient.mp3"] and p.exists()


def test_a_file_that_cannot_be_removed_is_reported_not_fatal(data_dir, monkeypatch):
    a = touch(data_dir / "voice_cache/a.mp3", 99)
    b = touch(data_dir / "voice_cache/b.mp3", 99)
    real = Path.unlink

    def flaky(self, *args, **kw):
        if self.name == "a.mp3":
            raise PermissionError("nope")
        return real(self, *args, **kw)

    monkeypatch.setattr(Path, "unlink", flaky)
    rep = sweep(data_dir, 30, dry_run=False, now=NOW)
    assert a.exists() and not b.exists() and len(rep["deleted"]) == 1 and len(rep["errors"]) == 1 and "PermissionError" in rep["errors"][0]


def test_the_cli_is_a_dry_run_unless_told_otherwise(data_dir, capsys, monkeypatch):
    p = touch(data_dir / "voice_cache/old.mp3", 0)
    os.utime(p, (time.time() - 100 * DAY, time.time() - 100 * DAY))
    monkeypatch.delenv("ALONGSIDE_REPLAY_DIR", raising=False)
    assert retention.main(["--days", "30"]) == 0 and p.exists() and "1 candidate" in capsys.readouterr().out
    assert retention.main(["--days", "30", "--apply"]) == 0 and not p.exists()


def test_the_module_never_touches_the_network_or_a_model():
    from understudy_engine.privacy import guard

    src = Path(retention.__file__).read_text()
    assert guard.scan_source(src, "privacy/retention.py", kind="layer")[0] == []
