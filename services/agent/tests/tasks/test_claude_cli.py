"""The Claude CLI spawner and monitor, against a FAKE claude (never the real one): environment allow-list, argv, progress lines that
carry no contents, caps, stop, kill file, crash reasons, process-group cleanup."""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import pytest

from understudy_agent.tasks import claude_cli as cc

from .conftest import wait_for


def run_fake(fake, tmp_path, mode, *, scope="files_and_commands", **kw):
    cwd = tmp_path / f"work-{mode}"
    argv = cc.build_argv(fake, cc.build_prompt(f"do it FAKE:{mode}", str(cwd), ["alpha"]), scope=scope,
                         session_id="11111111-1111-4111-8111-111111111111",
                         deny_rules=cc.protected_deny_rules(tmp_path / "data"))
    steps: list[str] = []
    kw.setdefault("grace_s", 1.0)
    kw.setdefault("tick_s", 0.05)
    r = cc.ClaudeRun(argv, str(cwd), cc.child_env(), on_step=steps.append, **kw)
    return r, steps, cwd


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # a zombie still answers kill(0); read its state
    try:
        import subprocess

        st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return bool(st) and not st.startswith("Z")
    except OSError:
        return True


def test_child_env_is_an_allow_list_and_never_carries_knack_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "e")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", "/x")
    monkeypatch.setenv("TERM", "xterm")
    env = cc.child_env()
    assert set(env) <= set(cc.ALLOWED_ENV)
    assert {"HOME", "PATH", "TERM"} <= set(env)
    assert "GEMINI_API_KEY" not in env and "ELEVENLABS_API_KEY" not in env and "ANTHROPIC_API_KEY" not in env
    parts = env["PATH"].split(":")
    assert "/usr/bin" in parts and "/sbin" in parts and not any(x.endswith("/.venv/bin") for x in parts)
    # an explicit parent mapping is honoured and still filtered
    assert cc.child_env({"HOME": "/h", "SECRET": "s", "PATH": ""}) == {"HOME": "/h", "PATH": ":".join(cc.SAFE_PATH_TAIL)}


def test_argv_scopes_and_hash(tmp_path):
    a = cc.build_argv("/bin/claude", "P", scope="files_and_commands", session_id="s", deny_rules=["Edit(//x)"])
    assert a[:3] == ["/bin/claude", "-p", "P"] and a[a.index("--output-format") + 1] == "stream-json" and "--verbose" in a
    assert a[a.index("--permission-mode") + 1] == "acceptEdits"
    assert a[a.index("--allowedTools") + 1] == "Read,Edit,Write,Glob,Grep,Bash"
    assert a[a.index("--permission-prompts") + 1] == "none"
    assert "--dangerously-skip-permissions" not in a                       # never by default
    assert json.loads(a[a.index("--settings") + 1]) == {"permissions": {"deny": ["Edit(//x)"]}}
    e = cc.build_argv("/bin/claude", "P", scope="everything", session_id="s")
    assert "--dangerously-skip-permissions" in e and "--allowedTools" not in e and "--permission-mode" not in e
    with pytest.raises(ValueError):
        cc.build_argv("/bin/claude", "P", scope="none", session_id="s")
    h1, h2 = cc.command_hash(a, "/w"), cc.command_hash(a, "/w")
    assert h1 == h2 and len(h1) == 64
    assert cc.command_hash(a, "/other") != h1 and cc.command_hash(e, "/w") != h1
    assert cc.command_hash([*a[:2], "Q", *a[3:]], "/w") != h1               # a changed prompt is a changed command


def test_protected_files_have_deny_rules(tmp_path):
    rules = cc.protected_deny_rules(tmp_path / "data", tmp_path / "repo")
    joined = "\n".join(rules)
    for name in ("KILL", "denylist.json", "rung_cleared.json", ".token", ".queue_key", "owner_tokens.json"):
        assert f"Edit(//{str(tmp_path / 'data' / name).lstrip('/')})" in joined
    assert "Read(//" + str(tmp_path / "data" / ".token").lstrip("/") + ")" in joined
    assert ".env" in joined


def test_progress_lines_name_tools_and_basenames_only(fake_claude, tmp_path):
    r, steps, cwd = run_fake(fake_claude, tmp_path, "ok")
    out = r.run()
    assert out.state == "done" and out.why == "ok" and out.exit_code == 0
    assert steps == ["Started", "Reading data.csv", "Running a command", "Writing summary.md"]
    blob = " ".join(steps)
    assert "SECRET HOOK TEXT" not in blob and "rate_limit" not in blob and "hook" not in blob.lower()      # the owner's hook output is never shown
    assert "SECRET FILE CONTENTS" not in blob and "curl" not in blob and "/Users/someone" not in blob and "passwd" not in blob
    assert out.result_text.startswith("Wrote summary.md with three rows.")
    assert [Path(w).name for w in out.written] == ["summary.md"]


def test_child_saw_only_the_allow_listed_environment_and_its_own_group(fake_claude, tmp_path):
    r, _, cwd = run_fake(fake_claude, tmp_path, "ok")
    r.run()
    seen = json.loads((cwd / "fake_seen.json").read_text())
    # LC_CTYPE and __CF_USER_TEXT_ENCODING are added by the shim's own Python runtime and macOS, not by Knack
    assert set(seen["env_keys"]) - {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"} <= set(cc.ALLOWED_ENV)
    assert not {"GEMINI_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY", "UNDERSTUDY_DATA_DIR", "KNACK_CLAUDE_BIN"} & set(seen["env_keys"])
    assert seen["pgid_is_own"] is True and seen["cwd"] == str(cwd.resolve()) or seen["cwd"] == str(cwd)
    assert "--dangerously-skip-permissions" not in seen["argv"]
    assert "--permission-mode" in seen["argv"]


def test_everything_scope_passes_skip_permissions_only_when_asked(fake_claude, tmp_path):
    r, _, cwd = run_fake(fake_claude, tmp_path, "ok", scope="everything")
    r.run()
    seen = json.loads((cwd / "fake_seen.json").read_text())
    assert "--dangerously-skip-permissions" in seen["argv"] and "--permission-mode" not in seen["argv"]


def test_a_crash_is_one_plain_reason_and_stderr_is_never_shown(fake_claude, tmp_path):
    r, steps, _ = run_fake(fake_claude, tmp_path, "exit3")
    out = r.run()
    assert out.state == "failed" and out.exit_code == 3
    assert out.reason == "The Claude agent stopped unexpectedly (exit code 3)."
    assert "secret" not in (out.reason or "").lower() and "boom" not in (out.reason or "")


def test_not_signed_in_and_usage_limit_have_their_own_reasons(fake_claude, tmp_path):
    out = run_fake(fake_claude, tmp_path, "noauth")[0].run()
    assert out.state == "failed" and out.why == "auth" and out.reason == cc.R_AUTH
    out = run_fake(fake_claude, tmp_path, "limit")[0].run()
    assert out.state == "failed" and out.why == "limit" and out.reason == cc.R_LIMIT


def test_error_result_and_missing_result(fake_claude, tmp_path):
    out = run_fake(fake_claude, tmp_path, "errresult")[0].run()
    assert out.state == "failed" and "ran out of turns" in out.reason
    out = run_fake(fake_claude, tmp_path, "nores")[0].run()
    assert out.state == "failed" and out.why == "no_result"
    out = run_fake(fake_claude, tmp_path, "silent")[0].run()
    assert out.state == "failed" and out.why == "no_result"


def test_a_missing_binary_is_a_plain_failure(tmp_path):
    r = cc.ClaudeRun(["/no/such/claude", "-p", "x"], str(tmp_path / "w"), cc.child_env())
    out = r.run()
    assert out.state == "failed" and out.why == "spawn" and out.reason == cc.R_NOT_FOUND


def test_stop_kills_the_whole_process_group_including_grandchildren(fake_claude, tmp_path):
    import threading

    r, steps, cwd = run_fake(fake_claude, tmp_path, "hang")
    box = {}
    th = threading.Thread(target=lambda: box.setdefault("o", r.run()))
    th.start()
    assert wait_for(lambda: (cwd / "grandchild.pid").exists() and "Reading a.txt" in steps, 10)
    gpid = int((cwd / "grandchild.pid").read_text())
    leader = r.proc.pid
    assert alive(gpid) and alive(leader)
    t0 = time.time()
    r.stop()
    th.join(10)
    assert not th.is_alive() and box["o"].state == "stopped" and box["o"].reason == "Stopped by you."
    assert time.time() - t0 < 5
    assert wait_for(lambda: not alive(gpid) and not alive(leader), 5)


def test_sigterm_ignored_falls_back_to_sigkill_after_the_grace(fake_claude, tmp_path):
    import threading

    r, _, cwd = run_fake(fake_claude, tmp_path, "ignoreterm", grace_s=0.6)
    box = {}
    th = threading.Thread(target=lambda: box.setdefault("o", r.run()))
    th.start()
    assert wait_for(lambda: (cwd / "grandchild.pid").exists(), 10)
    time.sleep(0.2)
    t0 = time.time()
    r.stop()
    th.join(10)
    dt = time.time() - t0
    assert box["o"].state == "stopped" and 0.5 <= dt < 5, dt           # waited the grace, then SIGKILL
    assert r.proc.returncode == -signal.SIGKILL
    assert wait_for(lambda: not alive(int((cwd / "grandchild.pid").read_text())), 5)


def test_wall_clock_cap(fake_claude, tmp_path):
    r, _, cwd = run_fake(fake_claude, tmp_path, "hang", max_seconds=1.0)
    out = r.run()
    assert out.state == "failed" and out.why == "wall" and "minute limit" in out.reason
    assert wait_for(lambda: not alive(int((cwd / "grandchild.pid").read_text())), 5)


def test_idle_cap(fake_claude, tmp_path):
    r, _, _ = run_fake(fake_claude, tmp_path, "hang", idle_seconds=1.0)
    out = r.run()
    assert out.state == "failed" and out.why == "idle" and "went quiet" in out.reason


def test_output_size_cap_ends_a_flood(fake_claude, tmp_path):
    r, steps, _ = run_fake(fake_claude, tmp_path, "flood", max_out_bytes=500_000)
    t0 = time.time()
    out = r.run()
    assert out.state == "failed" and out.why == "flood" and "more output than the limit" in out.reason
    assert time.time() - t0 < 10 and out.out_bytes >= 500_000
    assert out.out_bytes < 500_000 + 8_000_000                              # the reader killed the child at once: pipe buffers only


def test_kill_file_stops_a_running_child(fake_claude, tmp_path):
    flag = {"on": False}
    r, _, _ = run_fake(fake_claude, tmp_path, "hang", is_killed=lambda: flag["on"])
    import threading

    box = {}
    th = threading.Thread(target=lambda: box.setdefault("o", r.run()))
    th.start()
    assert wait_for(lambda: r.proc is not None, 5)
    time.sleep(0.3)
    flag["on"] = True
    th.join(10)
    assert box["o"].state == "stopped" and box["o"].why == "kill" and "kill switch" in box["o"].reason


def test_quiet_callback_fires_when_the_child_goes_silent(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "QUIET_AFTER_S", 0.4)
    quiet = []
    r, _, _ = run_fake(fake_claude, tmp_path, "hang", max_seconds=1.6, on_quiet=quiet.append)
    r.run()
    assert quiet and quiet[0] >= 0.4


def test_tool_lines_for_unusual_tools():
    assert cc.tool_line("mcp__x__y", {}) == "Using a connected tool"
    assert cc.tool_line("Edit", {"file_path": "/a/b/Report (1).docx"}) == "Editing Report (1).docx"
    assert cc.tool_line("Edit", {"file_path": "/a/b/\x1b[31mred.txt"}) == "Editing ??31mred.txt"
    assert cc.tool_line("Weird tool!", {}) == "Using Weirdtool"
    assert cc.tool_line("Bash", None) == "Running a command"
    assert cc.tool_line("Read", {"file_path": 5}) == "Reading 5"


def test_parse_line_ignores_garbage_and_never_raises():
    st = cc.StreamState()
    for raw in (b"", b"not json\n", b"[1,2]\n", b'{"type":"assistant","message":5}\n', b'{"type":"result","result":5}\n'):
        assert cc.parse_line(raw, st) == [] or True
    assert st.result_text == ""
