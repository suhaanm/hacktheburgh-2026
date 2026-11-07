"""run_python: a subprocess in an isolated workspace with no network (BGA-1, BGA-5).

On macOS the process runs under `sandbox-exec` with a profile built here:

    (allow default) then
    (deny network*)                         no sockets of any kind
    (deny file-write*)                      then writes are allowed ONLY in the workspace's WORK directory
    (deny file-read*) for HOME, the repository, the data directory and the temp area,
        then reads are allowed again for this workspace, the Python installation and its site-packages
    (deny process-fork) (deny process-exec*), then only the Python binary may be exec'd (no shells, no git, no curl)

Plus a cleared environment (nothing from the parent: no keys, no HOME), `python -I`, a new session and process group,
rlimits for CPU time, file size, open files and core dumps set inside the process (macOS refuses RLIMIT_AS and
RLIMIT_DATA, so memory is bounded by an RSS watchdog in the parent), a 30 s wall-clock timeout, and cancellation
polling every 50 ms so a stop kills the whole group well inside a second. Where `sandbox-exec` is missing the tool
FAILS CLOSED: it does not run the code unsandboxed.
"""
from __future__ import annotations

import os
import shutil
import signal
import site
import subprocess
import sys
import sysconfig
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..security.paths import data_dir, repo_root
from . import policy
from .workspace import Workspace, WorkspaceError, workspace_base

_PROBE: bool | None = None
_BOOT = r"""
import os, sys, resource, runpy
def _lim(name, value):
    try:
        resource.setrlimit(getattr(resource, name), (value, value))
    except Exception:
        pass
_lim("RLIMIT_CPU", int(os.environ["UDY_CPU"]))
_lim("RLIMIT_FSIZE", int(os.environ["UDY_FSIZE"]))
_lim("RLIMIT_NOFILE", int(os.environ["UDY_NOFILE"]))
_lim("RLIMIT_CORE", 0)
_lim("RLIMIT_AS", int(os.environ["UDY_RSS_MB"]) * 1024 * 1024 * 4)
script = sys.argv[1]
sys.argv = [script]
sys.path.insert(0, os.getcwd())
runpy.run_path(script, run_name="__main__")
"""


def sandbox_available() -> bool:
    """True when `sandbox-exec` exists and a trivial sandboxed command runs. Cached."""
    global _PROBE
    if _PROBE is None:
        exe = shutil.which("sandbox-exec") if sys.platform == "darwin" else None
        ok = False
        if exe:
            try:
                r = subprocess.run([exe, "-p", "(version 1)(allow default)(deny network*)", "/usr/bin/true"],
                                   capture_output=True, timeout=10)
                ok = r.returncode == 0
            except Exception:  # noqa: BLE001
                ok = False
        _PROBE = ok
    return _PROBE


def _q(path: Path | str) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ancestors(p: Path) -> list[Path]:
    return [a for a in reversed(p.parents) if str(a) not in ("/", "")]


def _exe_chain(exe: Path) -> list[Path]:
    """The interpreter path and every symlink hop to its real binary (uv and venvs go through aliases)."""
    chain, cur = [exe], exe
    for _ in range(8):
        if not cur.is_symlink():
            break
        nxt = Path(os.readlink(cur))
        cur = nxt if nxt.is_absolute() else cur.parent / nxt
        chain.append(Path(os.path.normpath(cur)))
    real = Path(os.path.realpath(exe))
    if real not in chain:
        chain.append(real)
    return chain


def python_paths() -> tuple[list[Path], list[Path]]:
    """(every path the interpreter may be exec'd as, directories the interpreter must be able to read)."""
    chain = _exe_chain(Path(sys.executable))
    reads: set[Path] = set()
    cands = [sys.prefix, sys.base_prefix, *site.getsitepackages(), sysconfig.get_path("stdlib"),
             sysconfig.get_path("platstdlib"), sysconfig.get_path("purelib"), sysconfig.get_path("platlib"),
             *[p for p in sys.path if p and os.path.isdir(p)], *[str(h.parent.parent) for h in chain]]
    for c in cands:
        if c:
            reads.add(Path(c))
            reads.add(Path(os.path.realpath(c)))
    return chain, sorted(reads)


def build_profile(ws: Workspace) -> str:
    """The sandbox profile for one workspace. Later rules win in SBPL, so denies come first and allows after."""
    assert ws.root is not None and ws.work is not None
    chain, py_reads = python_paths()
    work, root = ws.work.resolve(), ws.root.resolve()
    deny_read = {Path.home().resolve(), repo_root().resolve(), data_dir().resolve(), workspace_base().resolve()}
    allow_read = [root, *py_reads]
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        f"(allow file-write* (subpath {_q(work)}) (literal \"/dev/null\") (literal \"/dev/dtracehelper\"))",
        "(deny file-read* " + " ".join(f"(subpath {_q(p)})" for p in sorted(deny_read)) + ")",
    ]
    # the allowed trees, plus the directories on the way to them (so the interpreter can stat its own path)
    reads = list(allow_read)
    lits: set[Path] = set()
    for p in reads:
        for a in _ancestors(p):
            if any(a == d or (d in a.parents) or (a in d.parents) for d in deny_read):
                lits.add(a)
    lines.append("(allow file-read* " + " ".join(f"(subpath {_q(p)})" for p in reads) + ")")
    if lits:
        lines.append("(allow file-read* " + " ".join(f"(literal {_q(p)})" for p in sorted(lits)) + ")")
    lines += [
        "(deny process-fork)",
        "(deny process-exec*)",
        "(allow process-exec " + " ".join(f"(literal {_q(p)})" for p in chain) + ")",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class PyResult:
    exit_code: int | None
    duration_s: float
    timed_out: bool = False
    cancelled: bool = False
    killed_reason: str = ""          # "", "timeout", "cancel", "memory"
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    rss_peak_mb: float = 0.0
    integrity: dict[str, int] | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.killed_reason


def _rss_mb(pid: int) -> float:
    try:
        out = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout
        return int(out.strip() or 0) / 1024.0
    except Exception:  # noqa: BLE001
        return 0.0


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _drain(stream: object, cap: int, sink: bytearray) -> None:
    try:
        while True:
            chunk = stream.read(8192)  # type: ignore[attr-defined]
            if not chunk:
                return
            room = cap - len(sink)
            if room > 0:
                sink.extend(chunk[:room])
    except Exception:  # noqa: BLE001
        return


def run_python(ws: Workspace, script_rel: str, *, timeout_s: float = policy.PY_TIMEOUT_S,
               is_cancelled: Callable[[], bool] = lambda: False) -> PyResult:
    """Run a script that is already inside the workspace. Never raises for the script's own failure; raises
    WorkspaceError for refusals (bad path, no sandbox)."""
    if not sandbox_available():
        raise WorkspaceError("sandbox_unavailable", "no sandbox on this machine; run_python fails closed")
    script = ws.resolve(script_rel, must_exist=True)
    if not script.is_file() or script.suffix != ".py":
        raise WorkspaceError("not_a_script")
    assert ws.root is not None and ws.work is not None
    timeout_s = max(1.0, min(float(timeout_s), policy.PY_TIMEOUT_S))
    profile = ws.root / ".sandbox.sb"                      # outside WORK: the script cannot rewrite it
    profile.write_text(build_profile(ws))
    exe = Path(sys.executable)
    work = ws.work
    env = {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "HOME": str(work), "TMPDIR": str(work / ".tmp"),
        "MPLCONFIGDIR": str(work / ".tmp" / "mpl"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "UDY_CPU": str(policy.PY_CPU_S), "UDY_FSIZE": str(policy.PY_FSIZE_BYTES), "UDY_NOFILE": str(policy.PY_NOFILE),
        "UDY_RSS_MB": str(policy.PY_RSS_MB),
    }
    cmd = ["/usr/bin/sandbox-exec", "-f", str(profile), str(exe), "-I", "-c", _BOOT, ws.relpath(script)]
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=str(work), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True, close_fds=True)
    out_b, err_b = bytearray(), bytearray()
    readers = [threading.Thread(target=_drain, args=(proc.stdout, policy.PY_OUT_CAP, out_b), daemon=True),
               threading.Thread(target=_drain, args=(proc.stderr, policy.PY_OUT_CAP, err_b), daemon=True)]
    for r in readers:
        r.start()
    reason, peak, last_rss = "", 0.0, 0.0
    try:
        while proc.poll() is None:
            now = time.monotonic()
            if is_cancelled():
                reason = "cancel"
                break
            if now - t0 >= timeout_s:
                reason = "timeout"
                break
            if now - last_rss >= 0.25:
                last_rss = now
                peak = max(peak, _rss_mb(proc.pid))
                if peak > policy.PY_RSS_MB:
                    reason = "memory"
                    break
            time.sleep(0.03)
    finally:
        if proc.poll() is None:
            _kill_group(proc)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
    for r in readers:
        r.join(timeout=1.0)
    run_dir = work / ".run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "stdout.txt").write_bytes(bytes(out_b))
    (run_dir / "stderr.txt").write_bytes(bytes(err_b))
    res = PyResult(exit_code=proc.returncode, duration_s=round(time.monotonic() - t0, 3), timed_out=reason == "timeout",
                   cancelled=reason == "cancel", killed_reason=reason, stdout_bytes=len(out_b), stderr_bytes=len(err_b),
                   rss_peak_mb=round(peak, 1))
    res.integrity = ws.integrity_scan()
    return res
