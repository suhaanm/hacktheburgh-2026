"""The runner: what it launches (pinned, no shell, minimal environment), and how it behaves with a hostile, slow, crashing or flooding server."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from understudy_agent.connections import runner as R
from understudy_agent.connections.runner import RunnerError, build_launch
from understudy_agent.connections.service import Refused
from understudy_engine.connections import registry, state

from .helpers import HOSTILE, PY, free_port, preset, register

READS = ["get_things", "get_deleted", "get_pid", "get_env_names", "get_big", "get_note", "get_crash", "slow", "get_sampling"]


def _on(monkeypatch, pid="hostile", **kw):
    p = preset(pid, classes={"read": READS}, **kw)
    register(monkeypatch, p)
    state.connect(p, mode="example", confirm=True)
    return p


# ---------------------------------------------------------------------------------------------------- what is launched
@pytest.mark.parametrize("pid", sorted(p for p, pr in registry.all_presets().items() if pr.real["transport"] == "stdio"))
def test_every_real_launch_is_pinned_without_a_shell_with_install_scripts_off_and_a_minimal_env(pid):
    p = registry.get(pid)
    params = {x["name"]: ("/Users/example/work" if x["kind"] == "path" else "https://example.org" if x["kind"] == "url" else "example") for x in p.params}
    secrets = {e: "tok-" + "x" * 12 for e in p.credential_envs}
    ln = build_launch(p, "real", params, secrets, which=lambda c: "/usr/bin/" + c)
    assert ln.kind == "stdio" and ln.command in ("npx", "uvx", "docker") and "sh" != ln.command
    assert any(p.real["version"] in a for a in ln.args), "the exact pinned version is in the launch"
    assert not any("latest" in a for a in ln.args) and not any(c in a for a in ln.args for c in ";&|`$")
    allowed = set(p.credential_envs) | set(p.real.get("env_fixed", {})) | {x["env"] for x in p.params if x.get("env")}
    allowed |= {"npm_config_ignore_scripts", "npm_config_audit", "npm_config_fund", "npm_config_update_notifier", "UV_NO_BUILD", "UV_NO_PROGRESS"}
    assert set(ln.env) <= allowed, "nothing but the named variables is added"
    assert set(secrets) <= set(ln.env) and not any(v in " ".join(ln.args) for v in secrets.values()), "a token is an environment value, never an argument"
    if ln.command == "npx":
        assert ln.env["npm_config_ignore_scripts"] == "true"
    if ln.command == "uvx":
        assert ln.env["UV_NO_BUILD"] == "1"


def test_a_launch_never_carries_the_agents_own_secrets():
    p = registry.get("slack")
    ln = build_launch(p, "real", {}, {"SLACK_MCP_XOXP_TOKEN": "xoxp-1-2-3-abcdef"}, which=lambda c: "/usr/bin/" + c)
    assert "OPENAI_API_KEY" not in ln.env and not any(k.startswith("UNDERSTUDY") for k in ln.env)
    assert set(ln.env) == {"SLACK_MCP_ENABLED_TOOLS", "SLACK_MCP_XOXP_TOKEN", "npm_config_ignore_scripts", "npm_config_audit", "npm_config_fund", "npm_config_update_notifier"}


def test_a_missing_launcher_a_bad_value_or_a_foreign_token_is_refused_with_a_plain_message():
    p = registry.get("filesystem")
    with pytest.raises(RunnerError) as e:
        build_launch(p, "real", {"folder": "/x"}, {}, which=lambda c: None)
    assert e.value.code == "launcher_missing" and "Node" in str(e.value)
    with pytest.raises(RunnerError) as e:
        build_launch(p, "real", {"folder": "--evil-flag"}, {}, which=lambda c: "/usr/bin/npx")
    assert e.value.code == "bad_param"
    with pytest.raises(RunnerError) as e:
        build_launch(registry.get("slack"), "real", {}, {"OTHER_TOKEN": "abcdefgh"}, which=lambda c: "/usr/bin/npx")
    assert e.value.code == "unknown_secret"
    with pytest.raises(RunnerError) as e:
        build_launch(p, "real", {}, {}, which=lambda c: "/usr/bin/npx")
    assert e.value.code == "missing_param"


def test_an_http_launch_builds_the_header_in_code_and_only_allows_https_or_this_machine():
    real = {"verified": True, "transport": "streamable-http", "url": "https://mcp.example.org/mcp", "hosts": ["mcp.example.org"],
            "credentials": [{"env": "EXAMPLE_TOKEN", "label": "t", "header": "Authorization"}]}
    ln = build_launch(preset("h", real=real), "real", {}, {"EXAMPLE_TOKEN": "abcdefgh1234"})
    assert ln.kind == "http" and ln.headers == {"Authorization": "Bearer abcdefgh1234"} and "abcdefgh1234" not in repr(ln)
    for bad in ("http://mcp.example.org/mcp", "ftp://x/mcp"):
        with pytest.raises(RunnerError) as e:
            build_launch(preset("h", real={**real, "url": bad}), "real", {}, {"EXAMPLE_TOKEN": "abcdefgh1234"})
        assert e.value.code == "bad_url"
    assert build_launch(preset("h", real={**real, "url": "http://127.0.0.1:9/mcp"}), "real", {}, {"EXAMPLE_TOKEN": "abcdefgh1234"}).kind == "http"


def test_a_stand_in_gets_only_its_own_passthrough_variables(monkeypatch):
    monkeypatch.setenv("KNACK_STANDIN_POISON", "1")
    monkeypatch.setenv("CANARY_SECRET_TOKEN", "zzz")
    ln = build_launch(registry.get("github"), "example", {}, {})
    assert ln.env == {"KNACK_STANDIN_POISON": "1"} and ln.command == sys.executable


# ---------------------------------------------------------------------------------------------------- the process
def test_the_server_process_sees_only_home_and_path_and_what_we_named(service, monkeypatch):
    monkeypatch.setenv("CANARY_SECRET_TOKEN", "zzz-canary")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setenv("USER", "someone")
    _on(monkeypatch)
    names = set(service.call("hostile", "get_env_names", {}).text.split(","))
    assert not names & {"CANARY_SECRET_TOKEN", "OPENAI_API_KEY", "SHELL", "USER", "LOGNAME", "TERM", "UNDERSTUDY_DATA_DIR", "UNDERSTUDY_HOME", "UNDERSTUDY_SECRET_BACKEND"}
    assert {"PATH", "HOME"} <= names
    assert names <= {"PATH", "HOME", "LC_CTYPE", "__CF_USER_TEXT_ENCODING", "PYTHONCOERCECLOCALE", "PYTHONUTF8"}, names


def test_stopping_ends_the_process_tree_and_forgets_the_session(service, monkeypatch):
    _on(monkeypatch)
    pid = int(service.call("hostile", "get_pid", {}).text)
    os.kill(pid, 0)
    assert service.stop("hostile")["stopped"] is True and not service.runner.is_running("hostile")
    for _ in range(60):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the server process was still alive after stop")
    assert service.stop("hostile")["stopped"] is False


def test_a_slow_server_is_stopped_by_the_timeout_not_waited_for(service, monkeypatch):
    _on(monkeypatch)
    t0 = time.monotonic()
    with pytest.raises(Refused) as e:
        service.call("hostile", "slow", {"seconds": 8}, timeout=1.0)
    assert e.value.code == "timeout" and time.monotonic() - t0 < 4
    from understudy_engine.connections import ledger as cl

    assert cl.rows("hostile")[-1]["outcome"] == "timeout"


def test_a_crashing_server_is_restarted_a_few_times_then_left_off(service, monkeypatch):
    _on(monkeypatch)
    assert service.call("hostile", "get_things", {}).text.startswith("alpha")
    for _ in range(R.RESTARTS_PER_WINDOW):
        with pytest.raises(Refused) as e:
            service.call("hostile", "get_crash", {})
        assert e.value.code == "server_gone"
        assert service.call("hostile", "get_things", {}).text.startswith("alpha"), "restarted once, supervised"
    with pytest.raises(Refused):
        service.call("hostile", "get_crash", {})
    with pytest.raises(Refused) as e:
        service.call("hostile", "get_things", {})
    assert e.value.code == "keeps_stopping", "the restart budget is spent: it stays off until the worker acts"
    assert service.start("hostile")["ok"] and service.call("hostile", "get_things", {}).text.startswith("alpha"), "the worker's own start begins the budget afresh"


def test_a_flood_is_capped_and_marked_truncated(service, monkeypatch):
    _on(monkeypatch)
    out = service.call("hostile", "get_big", {})
    assert out.truncated and out.bytes_result == R.MAX_RESULT_BYTES and len(out.text) == R.MAX_RESULT_BYTES


def test_a_server_that_does_not_start_is_reported_not_hung(monkeypatch, service):
    p = preset("hostile", classes={"read": READS}, script="/nonexistent/server.py")
    register(monkeypatch, p)
    state.connect(p, mode="example", confirm=True)
    t0 = time.monotonic()
    r = service.start("hostile")
    assert r["ok"] is False and r["code"] in ("start_failed", "server_error", "timeout") and time.monotonic() - t0 < 30


def test_we_never_offer_sampling_elicitation_or_roots_to_a_server():
    import inspect

    src = inspect.getsource(R._Conn.serve)
    for forbidden in ("sampling_callback", "elicitation_callback", "list_roots_callback", "logging_callback", "message_handler", "extensions="):
        assert forbidden not in src, forbidden
    assert "cache=None" in src


def test_streamable_http_works_through_the_same_client(monkeypatch):
    port = free_port()
    proc = subprocess.Popen([PY, HOSTILE, "http", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]})
    runner = R.ConnectionRunner()
    try:
        import socket

        for _ in range(100):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        real = {"verified": True, "transport": "streamable-http", "url": f"http://127.0.0.1:{port}/mcp", "hosts": [],
                "credentials": [{"env": "EXAMPLE_TOKEN", "label": "t", "header": "Authorization"}]}
        ln = build_launch(preset("hostile_http", real=real), "real", {}, {"EXAMPLE_TOKEN": "abcdefgh1234"})
        tools = runner.start("hostile_http", ln)
        assert "get_things" in {t.name for t in tools}
        assert runner.call("hostile_http", "get_things", {}).text.startswith("alpha")
    finally:
        runner.stop_all()
        proc.terminate()
        proc.wait(timeout=10)
