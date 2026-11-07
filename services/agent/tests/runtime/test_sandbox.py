"""run_python (BGA-1, BGA-5): no network, nothing written outside the workspace, a cleared environment, limits, and a stop
that kills the process group within a second. These run real sandboxed processes (macOS sandbox-exec)."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time

import pytest

from understudy_agent.runtime import policy, sandbox
from understudy_agent.runtime.workspace import Workspace, WorkspaceError

pytestmark = pytest.mark.skipif(not sandbox.sandbox_available(), reason="needs macOS sandbox-exec")


@pytest.fixture
def ws():
    w = Workspace.create("tmp", run_id="r_test0001", child_id="c1")
    yield w
    w.cleanup()


def run(ws, code, **kw):
    ws.write_text("t.py", code)
    return sandbox.run_python(ws, "t.py", **kw)


def test_escape_attempts_fail_and_the_canary_is_untouched(ws, tmp_path):
    canary = tmp_path / "canary.txt"
    canary.write_text("untouched")
    code = f'''
import json, os, socket, subprocess
res = {{}}
def attempt(name, fn):
    try:
        fn(); res[name] = "OPEN"
    except Exception as e:
        res[name] = type(e).__name__
attempt("net", lambda: socket.create_connection(("1.1.1.1", 53), timeout=2))
attempt("dns", lambda: socket.getaddrinfo("example.org", 80))
attempt("write_canary", lambda: open({str(canary)!r}, "w").write("pwned"))
attempt("write_repo", lambda: open({str(policy.__file__)!r}, "a").write("x"))
attempt("read_repo", lambda: open({str(os.path.join(os.path.dirname(policy.__file__), "spec.py"))!r}).read(5))
attempt("exec", lambda: subprocess.run(["/bin/echo", "x"]))
attempt("fork", lambda: os.fork())
attempt("hardlink", lambda: os.link({str(canary)!r}, "out/h"))
res["env_keys"] = sorted(k for k in os.environ if "KEY" in k or "OPENAI" in k or "TOKEN" in k)
open("out/res.json", "w").write(json.dumps(res))
'''
    r = run(ws, code)
    assert r.exit_code == 0, (ws.work / ".run" / "stderr.txt").read_text()
    res = json.loads((ws.work / "out" / "res.json").read_text())
    for k in ("net", "dns", "write_canary", "write_repo", "read_repo", "exec", "fork", "hardlink"):
        assert res[k] != "OPEN", f"{k} was allowed: {res[k]}"
    assert res["env_keys"] == []                      # the parent's OPENAI_API_KEY is not in the child's environment
    assert canary.read_text() == "untouched"


def test_a_symlink_made_inside_is_removed_after_the_run(ws, tmp_path):
    canary = tmp_path / "canary.txt"
    canary.write_text("untouched")
    r = run(ws, f'import os\nos.symlink({str(canary)!r}, "out/link")\n')
    assert r.integrity["symlinks"] == 1 and not os.path.lexists(ws.work / "out" / "link")
    assert canary.read_text() == "untouched"


def test_pandas_and_matplotlib_work_inside_the_sandbox(ws):
    r = run(ws, "import pandas, matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
                "plt.plot([1, 2]); plt.savefig('out/c.png')\nprint(pandas.__version__)\n")
    assert r.ok and (ws.work / "out" / "c.png").stat().st_size > 1000


def test_timeout_kills_the_script(ws):
    t0 = time.monotonic()
    r = run(ws, "import time\ntime.sleep(30)\n", timeout_s=1.5)
    assert r.timed_out and r.killed_reason == "timeout" and time.monotonic() - t0 < 4


def test_cancel_kills_the_process_group_inside_a_second(ws):
    flag = threading.Event()
    threading.Timer(0.4, flag.set).start()
    t0 = time.monotonic()
    r = run(ws, "import time\ntime.sleep(30)\n", is_cancelled=flag.is_set)
    took = time.monotonic() - t0
    assert r.cancelled and took < 1.0, took
    time.sleep(0.2)
    assert subprocess.run(["pgrep", "-f", str(ws.root)], capture_output=True).stdout == b""


def test_memory_watchdog_kills_a_greedy_script(ws):
    r = run(ws, "x = bytearray(1400 * 1024 * 1024)\nimport time\ntime.sleep(10)\n")
    assert r.killed_reason == "memory" and r.rss_peak_mb > policy.PY_RSS_MB


def test_cpu_limit_stops_a_spin_loop_before_the_wall_clock_does(ws, monkeypatch):
    monkeypatch.setattr(policy, "PY_CPU_S", 2)
    r = run(ws, "while True:\n    pass\n", timeout_s=policy.PY_TIMEOUT_S)
    assert r.exit_code not in (0, None) and not r.timed_out and r.duration_s < 12, r


def test_stdout_is_capped_and_saved_by_the_parent(ws):
    r = run(ws, "print('x' * 500000)\n")
    assert r.ok and r.stdout_bytes == policy.PY_OUT_CAP
    assert len((ws.work / ".run" / "stdout.txt").read_bytes()) == policy.PY_OUT_CAP


def test_a_script_outside_the_workspace_or_not_python_is_refused(ws):
    with pytest.raises(WorkspaceError):
        sandbox.run_python(ws, "../x.py")
    ws.write_text("t.txt", "print(1)")
    with pytest.raises(WorkspaceError) as e:
        sandbox.run_python(ws, "t.txt")
    assert e.value.code == "not_a_script"


def test_it_fails_closed_without_a_sandbox(ws, monkeypatch):
    monkeypatch.setattr(sandbox, "_PROBE", False)
    ws.write_text("t.py", "print(1)")
    with pytest.raises(WorkspaceError) as e:
        sandbox.run_python(ws, "t.py")
    assert e.value.code == "sandbox_unavailable"
