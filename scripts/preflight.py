#!/usr/bin/env python
"""Demo-day preflight: a plain green / amber / red checklist. Exits non-zero on any red. Never prints a secret.

    uv run --package understudy-agent python scripts/preflight.py [--fix-hints] [--mode demo|dev] [--deep]

Read-only: it connects to the running services, reads files and lists models. It does not start, stop, reset or
write anything except an optional cache of the desktop typecheck (data/preflight/). It never calls a model to
generate, never reads a key into the output (names are shown, values never), and redacts any secret value it has
seen in .env from everything it prints.

GREEN: ready. AMBER: works, but read the note (or the check was skipped). RED: fix before judging.
--mode demo (default) expects what `make demo` produces: the isolated demo home, mock mode, the seeded identity.
--mode dev only reports those facts (a real home or live models is then amber at most).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

GREEN, AMBER, RED, SKIP = "green", "amber", "red", "skip"
DEMO_PERSON = "p_learn01"
DEMO_ROUTINE = "calc-entry-3x"
SECRET_NAME = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD)", re.I)
PUBLIC_VALUE_KEYS = {"UNDERSTUDY_MOCK", "UNDERSTUDY_VOICE", "ENGINE_PORT", "AGENT_PORT", "DASHBOARD_PORT", "SANDBOX_PORT_BASE"}
GROUPS = ("Environment", "Services", "Demo state", "Build", "Offline")


@dataclass
class Result:
    id: str
    group: str
    status: str
    title: str
    detail: str = ""
    hint: str = ""


@dataclass
class Ctx:
    repo: Path
    mode: str = "demo"
    deep: bool = False
    timeout: float = 2.0
    engine_port: int = 7700
    agent_port: int = 7710
    dashboard_port: int = 5173
    desktop_port: int = 7720
    site_ports: tuple[int, int, int] = (7801, 7802, 7803)
    env: dict[str, str] = field(default_factory=dict)       # process environment overlaid on .env (process wins)
    dotenv: dict[str, str] = field(default_factory=dict)    # .env only (names and values, never printed)
    skip: set[str] = field(default_factory=set)
    now: float = field(default_factory=time.time)
    _cache: dict[str, tuple[int | None, Any, str | None]] = field(default_factory=dict)

    @property
    def engine(self) -> str:
        return f"http://127.0.0.1:{self.engine_port}"

    @property
    def agent(self) -> str:
        return f"http://127.0.0.1:{self.agent_port}"

    def site(self, i: int) -> str:
        return f"http://127.0.0.1:{self.site_ports[i]}"

    def get(self, base: str, path: str) -> tuple[int | None, Any, str | None]:
        key = base + path
        if key not in self._cache:
            self._cache[key] = http_json(base + path, self.timeout)
        return self._cache[key]

    @property
    def demo(self) -> bool:
        return self.mode == "demo"


# ------------------------------------------------------------------------------------------------ helpers
def http_json(url: str, timeout: float = 2.0) -> tuple[int | None, Any, str | None]:
    """(status, parsed JSON or text or None, error). Never raises."""
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (loopback URLs only)
            raw = r.read(2_000_000)
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(200_000), e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, None, type(getattr(e, "reason", e)).__name__
    try:
        return status, json.loads(raw.decode("utf-8", "replace")), None
    except ValueError:
        return status, raw.decode("utf-8", "replace")[:300], None


def port_open(port: int, timeout: float = 0.4) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def who_listens(port: int) -> str:
    """'pid 123 (python3)' for whatever listens on the port, or ''. Reads no environment."""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True, timeout=3).stdout.split()
        if not out:
            return ""
        comm = subprocess.run(["ps", "-o", "comm=", "-p", out[0]], capture_output=True, text=True, timeout=3).stdout.strip()
        return f"pid {out[0]} ({Path(comm).name or 'unknown'})"
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def age_text(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m} min" if m < 120 else f"{m / 60:.1f} h" if m < 2880 else f"{m / 1440:.1f} days"


def R(ctx_group: str, id_: str, status: str, title: str, detail: str = "", hint: str = "") -> Result:
    return Result(id_, ctx_group, status, title, detail, hint)


# ------------------------------------------------------------------------------------------------ checks: environment
def check_python(ctx: Ctx) -> list[Result]:
    v = sys.version_info
    ok = (3, 12) <= (v.major, v.minor) < (3, 14)
    return [R("Environment", "python", GREEN if ok else RED, "Python", f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (the workspace needs 3.12 or 3.13)"),
              "" if ok else "uv python install 3.12, then make setup")]


def check_node(ctx: Ctx) -> list[Result]:
    try:
        out = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return [R("Environment", "node", RED, "Node", "not found", "install Node 20 or newer")]
    m = re.match(r"v(\d+)", out)
    major = int(m.group(1)) if m else 0
    return [R("Environment", "node", GREEN if major >= 20 else RED, "Node", out + ("" if major >= 20 else " (needs 20 or newer)"), "" if major >= 20 else "install Node 20 or newer")]


def check_env_file(ctx: Ctx) -> list[Result]:
    p = ctx.repo / ".env"
    live = not truthy(ctx.env.get("UNDERSTUDY_MOCK"))
    if not p.is_file():
        return [R("Environment", "env_file", AMBER if not live else RED, ".env", "missing", "cp .env.example .env, then fill it in (never commit it)")]
    names = ["OPENAI_API_KEY", "OPENAI_MODEL_PLANNER", "OPENAI_MODEL_FAST", "OPENAI_MODEL_COMPUTER_USE"]
    missing = [n for n in names if not ctx.dotenv.get(n)]
    res = []
    detail = "present; " + ", ".join(f"{n} {'set' if ctx.dotenv.get(n) else 'NOT set'}" for n in names)
    status = GREEN if not missing else (RED if live else AMBER)
    res.append(R("Environment", "env_file", status, ".env", detail, "" if not missing else f"set {', '.join(missing)} in .env (names only are checked here)" + ("" if live else "; not needed in mock mode")))
    mode = stat.S_IMODE(p.stat().st_mode)
    if mode & 0o077:
        res.append(R("Environment", "env_perms", AMBER, ".env permissions", f"mode {mode:o}: readable by other users", "chmod 600 .env"))
    try:
        ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ctx.repo, capture_output=True, timeout=5).returncode == 0
        res.append(R("Environment", "env_ignored", GREEN if ignored else RED, ".env is git-ignored", "yes" if ignored else "NO: it could be committed", "" if ignored else "add .env to .gitignore now"))
    except (OSError, subprocess.SubprocessError):
        res.append(R("Environment", "env_ignored", AMBER, ".env is git-ignored", "git not available to check"))
    return res


def check_mock(ctx: Ctx) -> list[Result]:
    """The engine's own report wins: `make demo` sets UNDERSTUDY_MOCK=1 for the services only, not in this shell or .env."""
    shell = ctx.env.get("UNDERSTUDY_MOCK")
    seen = f"this shell and .env say {shell or 'unset'}"
    if port_open(ctx.engine_port):
        st, body, _ = ctx.get(ctx.engine, "/health")
        if st == 200 and isinstance(body, dict) and "mock" in body:
            mock = bool(body["mock"])
            if ctx.demo and not mock:
                return [R("Environment", "mock", AMBER, "Mock mode", f"the engine is NOT in mock mode ({seen}): the demo would make model calls and need the network", "make stop && make demo")]
            return [R("Environment", "mock", GREEN, "Mock mode", f"the engine reports mock {mock} ({seen})")]
    mock = truthy(shell)
    if ctx.demo:
        return [R("Environment", "mock", GREEN if mock else AMBER, "Mock mode", f"engine not reachable; {seen}" + ("" if mock else ": make demo sets UNDERSTUDY_MOCK=1 for the services"),
                  "" if mock else "start with make demo")]
    return [R("Environment", "mock", GREEN, "Mock mode", f"{seen} (dev mode: informational)")]


def check_disk(ctx: Ctx) -> list[Result]:
    free = shutil.disk_usage(ctx.repo).free / 1e9
    st = RED if free < 1 else AMBER if free < 5 else GREEN
    return [R("Environment", "disk", st, "Disk space", f"{free:.1f} GB free", "" if st == GREEN else "free some space: caches, data/runs, old node_modules")]


def check_chromium(ctx: Ctx) -> list[Result]:
    roots = [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []
    roots += [Path.home() / "Library/Caches/ms-playwright", Path.home() / ".cache/ms-playwright"]
    for root in roots:
        for d in sorted(root.glob("chromium-*")) if root.is_dir() else []:
            if (d / "INSTALLATION_COMPLETE").exists():
                return [R("Environment", "chromium", GREEN, "Chromium for Playwright", d.name)]
    return [R("Environment", "chromium", RED, "Chromium for Playwright", "not installed", "uv run --package understudy-agent playwright install chromium")]


def check_voice(ctx: Ctx) -> list[Result]:
    flag = truthy(ctx.env.get("UNDERSTUDY_VOICE"))
    key = bool(ctx.env.get("ELEVENLABS_API_KEY"))
    mock = truthy(ctx.env.get("UNDERSTUDY_MOCK"))
    cache = ctx.repo / "data" / "voice_cache"
    cached = len([p for p in cache.glob("*") if p.is_file()]) if cache.is_dir() else 0
    if not flag:
        return [R("Environment", "voice", GREEN, "ElevenLabs voice", "off (UNDERSTUDY_VOICE not 1): silent coach, never blocks the demo")]
    if mock or not key:
        why = "mock mode" if mock else "no ELEVENLABS_API_KEY"
        return [R("Environment", "voice", GREEN if cached else AMBER, "ElevenLabs voice", f"flag on but {why}: plays cached audio only ({cached} files)" if cached else f"flag on but {why} and the audio cache is empty: silence",
                  "" if cached else "warm data/voice_cache while online, or leave UNDERSTUDY_VOICE off")]
    return [R("Environment", "voice", AMBER if not cached else GREEN, "ElevenLabs voice", f"on, key set (name only checked), {cached} cached files" + ("; needs the network for anything uncached" if not cached else ""),
              "" if cached else "warm data/voice_cache while online before going offline")]


def check_models(ctx: Ctx) -> list[Result]:
    if truthy(ctx.env.get("UNDERSTUDY_MOCK")):
        return [R("Environment", "models", GREEN, "Model boot check", "mock mode: no models needed, no network call made")]
    try:
        from understudy_agent.models.boot import boot_check
    except ImportError:
        return [R("Environment", "models", AMBER, "Model boot check", "run this script with `uv run --package understudy-agent` to list models")]
    for k in ("OPENAI_API_KEY", "OPENAI_MODEL_PLANNER", "OPENAI_MODEL_FAST", "OPENAI_MODEL_COMPUTER_USE"):
        if ctx.dotenv.get(k) and not os.environ.get(k):
            os.environ[k] = ctx.dotenv[k]
    rep = boot_check(raise_on_fail=False, out=lambda s: None)
    if rep.ok:
        return [R("Environment", "models", GREEN, "Model boot check", f"read-only: the key lists {len(rep.usable)} models and all three configured IDs are usable")]
    miss = ", ".join(f"{r}={m}" for r, m in rep.missing.items()) if rep.missing else rep.message.splitlines()[0] if rep.message else "failed"
    return [R("Environment", "models", RED, "Model boot check", miss, "fix .env (ids are never guessed), or run in mock mode with the wifi off")]


# ------------------------------------------------------------------------------------------------ checks: services
def check_ports(ctx: Ctx) -> list[Result]:
    res = []
    spec = [("engine", ctx.engine_port, RED), ("agent", ctx.agent_port, RED), ("sandbox a", ctx.site_ports[0], RED), ("sandbox b", ctx.site_ports[1], RED),
            ("sandbox c", ctx.site_ports[2], RED), ("dashboard", ctx.dashboard_port, RED), ("desktop coach channel", ctx.desktop_port, AMBER)]
    for name, port, if_free in spec:
        up = port_open(port)
        hint = {"engine": "make dev", "agent": "make dev", "dashboard": "make dev", "desktop coach channel": "start the desktop app (the overlay needs it)"}.get(name, "make dev")
        res.append(R("Services", f"port_{port}", GREEN if up else if_free, f"port {port} ({name})",
                     "listening" if up else "free: nothing is running here", "" if up else hint))
    return res


def check_engine(ctx: Ctx) -> list[Result]:
    if not port_open(ctx.engine_port):
        return [R("Services", "engine_health", RED, "Engine /health", "not reachable", "make dev (or make demo)")]
    st, body, err = ctx.get(ctx.engine, "/health")
    if st != 200 or not isinstance(body, dict) or not body.get("ok"):
        who = who_listens(ctx.engine_port)
        return [R("Services", "engine_health", RED, "Engine /health", f"port {ctx.engine_port} answers but not as the engine (status {st}, {err or 'no ok'})" + (f"; held by {who}" if who else ""),
                  f"stop whatever holds the port, then make dev")]
    routers = body.get("routers") or {}
    warm = body.get("warm") or {}
    bad_r = [k for k in ("data", "analytics", "handoff", "coach") if not routers.get(k)]
    bad_w = [k for k in ("genome", "coach", "analytics") if not warm.get(k)]
    mock = bool(body.get("mock"))
    detail = f"ok, version {body.get('version')}, mock {mock}, routers {sum(1 for v in routers.values() if v)}/{len(routers) or 4}, warm: " + (", ".join(k for k in ("genome", "coach", "analytics") if warm.get(k)) or "nothing yet")
    st_ = GREEN
    notes = []
    if bad_r:
        st_ = RED
        notes.append(f"routers not loaded: {', '.join(bad_r)}")
    if bad_w and st_ != RED:
        st_ = AMBER
        notes.append(f"still warming: {', '.join(bad_w)} (wait 15 s and rerun)")
    if ctx.demo and not mock:
        st_ = AMBER if st_ == GREEN else st_
        notes.append("engine is NOT in mock mode: it will make model calls and need the network")
    return [R("Services", "engine_health", st_, "Engine /health", detail + ("; " + "; ".join(notes) if notes else ""),
              "" if st_ == GREEN else "check data/logs/engine.log; restart with make stop && make demo")]


def check_agent(ctx: Ctx) -> list[Result]:
    if not port_open(ctx.agent_port):
        return [R("Services", "agent_health", RED, "Agent /health", "not reachable", "make dev (or make demo)")]
    st, body, err = ctx.get(ctx.agent, "/health")
    if st != 200 or not isinstance(body, dict) or not body.get("ok"):
        return [R("Services", "agent_health", RED, "Agent /health", f"answers but not ok (status {st})", "check data/logs/agent.log; make stop && make demo")]
    sup = body.get("supervisor") or {}
    state = sup.get("state")
    detail = f"ok, mock {bool(body.get('mock'))}, supervisor {state} (generation {sup.get('generation')})"
    st_ = GREEN
    if state not in (None, "idle"):
        st_ = AMBER
        detail += ": a run is in progress or paused"
    est, ebody, _ = ctx.get(ctx.engine, "/health")
    if isinstance(ebody, dict) and "mock" in ebody and bool(ebody["mock"]) != bool(body.get("mock")):
        st_ = AMBER
        detail += "; engine and agent disagree about mock mode"
    return [R("Services", "agent_health", st_, "Agent /health", detail, "" if st_ == GREEN else "make stop && make demo for a clean start")]


def check_sandbox(ctx: Ctx) -> list[Result]:
    res = []
    all_up = True
    for i, name in enumerate("abc"):
        if not port_open(ctx.site_ports[i]):
            all_up = False
            res.append(R("Services", f"sandbox_{name}", RED, f"Sandbox site {name} /healthz", "not reachable", "make dev"))
            continue
        st, body, _ = ctx.get(ctx.site(i), "/healthz")
        ok = st == 200 and isinstance(body, dict) and body.get("ok")
        all_up = all_up and bool(ok)
        res.append(R("Services", f"sandbox_{name}", GREEN if ok else RED, f"Sandbox site {name} /healthz", "ok" if ok else f"answers but not ok (status {st})", "" if ok else "make stop && make dev"))
    if all_up:
        st, body, _ = ctx.get(ctx.site(0), "/__state")
        if st == 200 and isinstance(body, dict):
            notes, calcs, cliff = len(body.get("notes") or {}), len(body.get("calculations") or []), len(body.get("cliff_opens") or [])
            dirty = notes or calcs or cliff or body.get("submissions") or body.get("exfil_hits")
            res.append(R("Services", "sandbox_state", AMBER if dirty else GREEN, "Sandbox /__state",
                         f"{notes} notes, {calcs} calculations, {cliff} cliff opens, {len(body.get('submissions') or [])} submissions, {len(body.get('exfil_hits') or [])} exfil hits" + (": not clean (left over from a rehearsal)" if dirty else ": clean"),
                         f"curl -s -X POST {ctx.site(0)}/__reset" if dirty else ""))
        else:
            res.append(R("Services", "sandbox_state", RED, "Sandbox /__state", f"not reachable (status {st})", "make stop && make dev"))
    return res


def real_home() -> Path:
    return (Path.home() / ".understudy").resolve()


def _home_from_ps(port: int) -> str | None:
    """The one variable UNDERSTUDY_HOME of the process listening on the port; every other variable is dropped unread."""
    try:
        pid = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True, timeout=3).stdout.split()
        if not pid:
            return None
        txt = subprocess.run(["ps", "eww", "-o", "command=", "-p", pid[0]], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(?:^|\s)UNDERSTUDY_HOME=(\S+)", txt)
    return m.group(1) if m else None


def check_engine_home(ctx: Ctx) -> list[Result]:
    if not port_open(ctx.engine_port):
        return [R("Services", "engine_home", AMBER, "Which UNDERSTUDY_HOME the engine uses", "not checked: engine is down")]
    st, body, _ = ctx.get(ctx.engine, "/memory")
    home: Path | None = None
    how = "from GET /memory"
    if st == 200 and isinstance(body, dict) and isinstance(body.get("path"), str):
        home = Path(body["path"]).expanduser().parent
    else:
        h = _home_from_ps(ctx.engine_port)
        if h:
            home, how = Path(h).expanduser(), "from the engine process"
    if home is None:
        return [R("Services", "engine_home", AMBER, "Which UNDERSTUDY_HOME the engine uses", "could not tell (no /memory path, no process info)")]
    resolved = home.resolve()
    is_real = resolved == real_home()
    in_demo = resolved == (ctx.repo / "data" / "demo-home").resolve()
    detail = f"{resolved} ({how})"
    if ctx.demo and is_real:
        return [R("Services", "engine_home", RED, "Which UNDERSTUDY_HOME the engine uses", detail + ": this is the OWNER'S REAL memory, but a demo was expected", "make stop && make demo (it points the engine at data/demo-home)")]
    if ctx.demo and not in_demo:
        return [R("Services", "engine_home", AMBER, "Which UNDERSTUDY_HOME the engine uses", detail + ": not the demo home (data/demo-home)", "make stop && make demo")]
    if is_real:
        return [R("Services", "engine_home", AMBER, "Which UNDERSTUDY_HOME the engine uses", detail + ": the real home (dev mode: onboarding or the demo seed would overwrite your memory)")]
    return [R("Services", "engine_home", GREEN, "Which UNDERSTUDY_HOME the engine uses", detail)]


def check_kill(ctx: Ctx) -> list[Result]:
    res = []
    flag = ctx.repo / "data" / "KILL"
    if flag.exists():
        res.append(R("Services", "kill_file", RED, "Kill flag file data/KILL", "present: everything is stopped", f"rm {flag}  (or POST {ctx.engine}/kill/clear, or the Resume button)"))
    else:
        res.append(R("Services", "kill_file", GREEN, "Kill flag file data/KILL", "absent"))
    if port_open(ctx.engine_port):
        st, body, _ = ctx.get(ctx.engine, "/kill")
        if st == 200 and isinstance(body, dict) and body.get("killed"):
            res.append(R("Services", "kill_state", RED, "Engine kill state", "killed: true", f"curl -s -X POST {ctx.engine}/kill/clear"))
    return res


# ------------------------------------------------------------------------------------------------ checks: demo state
def _engine_down(id_: str, title: str) -> list[Result]:
    return [R("Demo state", id_, AMBER, title, "not checked: engine is down")]


def _items(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("data", "items", "proposals", "routines"):
            if isinstance(body.get(k), list):
                return body[k]
    return []


def check_demo_seed(ctx: Ctx) -> list[Result]:
    if not port_open(ctx.engine_port):
        return _engine_down("demo_identity", "Demo seed")
    miss = RED if ctx.demo else AMBER
    seed_hint = "make stop && make demo (seeds data/demo-home)"
    res = []
    st, body, _ = ctx.get(ctx.engine, "/identity")
    person = body.get("person") if st == 200 and isinstance(body, dict) else None
    if person == DEMO_PERSON:
        res.append(R("Demo state", "demo_identity", GREEN, "Identity", f"{DEMO_PERSON} ({(body or {}).get('role')})"))
    elif person:
        res.append(R("Demo state", "demo_identity", AMBER if not ctx.demo else RED, "Identity", f"{person}, not the demo person {DEMO_PERSON}", seed_hint))
    else:
        res.append(R("Demo state", "demo_identity", miss, "Identity", f"none (status {st}): not onboarded", seed_hint))
    st, body, _ = ctx.get(ctx.engine, "/memory/proposals")
    props = _items(body)
    pending = [p for p in props if isinstance(p, dict) and p.get("status") == "proposed"]
    res.append(R("Demo state", "demo_proposal", GREEN if pending else miss, "A rule proposal waiting for approval",
                 f"{len(pending)} pending" if pending else f"none pending ({len(props)} listed)", "" if pending else seed_hint))
    st, body, _ = ctx.get(ctx.engine, "/routines")
    routines = [r for r in _items(body) if isinstance(r, dict)]
    mine = next((r for r in routines if r.get("id") == DEMO_ROUTINE), None)
    if mine and mine.get("status") == "proposed":
        res.append(R("Demo state", "demo_routine", GREEN, f"Routine {DEMO_ROUTINE}", "proposed, rung " + str(mine.get("rung"))))
    elif mine:
        res.append(R("Demo state", "demo_routine", AMBER, f"Routine {DEMO_ROUTINE}", f"already {mine.get('status')}: the proposal card will not show", "make stop && make demo to reseed"))
    else:
        res.append(R("Demo state", "demo_routine", miss, f"Routine {DEMO_ROUTINE}", f"not found among {len(routines)} routines", seed_hint))
    return res


def check_coach(ctx: Ctx) -> list[Result]:
    if not port_open(ctx.engine_port):
        return _engine_down("coach", "Coach /coach/next")
    st, body, err = http_json(f"{ctx.engine}/coach/next?person={DEMO_PERSON}&dry=1", ctx.timeout + 3)
    if st == 200 and isinstance(body, dict):
        d = body.get("data") or {}
        return [R("Demo state", "coach", GREEN, "Coach /coach/next (dry)", f"answers: action {d.get('action')}, level {d.get('level')}, reason {','.join(d.get('reason_codes') or [])}")]
    code = (body or {}).get("error", {}).get("code") if isinstance(body, dict) else None
    return [R("Demo state", "coach", RED if ctx.demo else AMBER, "Coach /coach/next (dry)", f"status {st} {code or err or ''}".strip(), "needs the demo person: make stop && make demo")]


def check_eval_report(ctx: Ctx) -> list[Result]:
    res = []
    file = ctx.repo / "evals" / "report.json"
    if port_open(ctx.engine_port):
        st, body, _ = ctx.get(ctx.engine, "/eval/report")
        if st == 200 and isinstance(body, dict) and body.get("generated_at"):
            try:
                at = datetime.fromisoformat(str(body["generated_at"]).replace("Z", "+00:00")).timestamp()
                age = ctx.now - at
                st_ = GREEN if age <= 7200 else AMBER
                res.append(R("Demo state", "eval_report", st_, "Evidence report /eval/report", f"present, generated {age_text(age)} ago, mock {body.get('mock')}",
                             "" if st_ == GREEN else "make eval FAST=1 (or make eval) to refresh before judging"))
            except ValueError:
                res.append(R("Demo state", "eval_report", AMBER, "Evidence report /eval/report", "present but generated_at is not a time"))
        else:
            res.append(R("Demo state", "eval_report", RED, "Evidence report /eval/report", f"missing (status {st})", "make eval FAST=1"))
        return res
    if file.is_file():
        return [R("Demo state", "eval_report", AMBER, "Evidence report", f"engine is down; evals/report.json exists, {age_text(ctx.now - file.stat().st_mtime)} old")]
    return [R("Demo state", "eval_report", RED, "Evidence report", "engine is down and evals/report.json is missing", "make eval FAST=1")]


# ------------------------------------------------------------------------------------------------ checks: build
def check_extension_build(ctx: Ctx) -> list[Result]:
    ext = ctx.repo / "extension"
    dist = ext / "dist"
    need = ["manifest.json", "content.js", "worker.js", "popup.js", "popup.html"]
    missing = [n for n in need if not (dist / n).is_file()]
    if missing:
        return [R("Build", "extension_build", RED, "Extension build (extension/dist)", f"missing {', '.join(missing)}", "cd extension && npm install && npm run build")]
    built = min((dist / "content.js").stat().st_mtime, (dist / "worker.js").stat().st_mtime)
    # src/generated is rewritten (same content) by every `npm test`; the zones check below compares its content instead
    src = [p.stat().st_mtime for p in (ext / "src").rglob("*") if p.is_file() and "generated" not in p.parts] + [(ext / "manifest.json").stat().st_mtime, (ext / "popup.html").stat().st_mtime]
    newest = max(src) if src else 0
    if newest > built + 1:
        return [R("Build", "extension_build", AMBER, "Extension build (extension/dist)", f"stale: sources are {age_text(newest - built)} newer than the build", "cd extension && npm run build, then reload it in chrome://extensions")]
    return [R("Build", "extension_build", GREEN, "Extension build (extension/dist)", f"present, built {age_text(ctx.now - built)} ago")]


def check_extension_zones(ctx: Ctx) -> list[Result]:
    ext = ctx.repo / "extension"
    bundled = ext / "src" / "generated" / "bundled.json"
    if not bundled.is_file():
        return [R("Build", "extension_zones", RED, "Extension zones match the packs", "src/generated/bundled.json missing", "cd extension && npm run gen")]
    if not (ext / "node_modules" / "yaml").is_dir():
        return [R("Build", "extension_zones", AMBER, "Extension zones match the packs", "not checked: extension/node_modules missing", "cd extension && npm install")]
    try:
        out = subprocess.run(["node", "-e", "import('./scripts/gen.mjs').then(m=>process.stdout.write(JSON.stringify(m.generate())))"],
                             cwd=ext, capture_output=True, text=True, timeout=30)
        fresh = json.loads(out.stdout)
        have = json.loads(bundled.read_text())
    except (OSError, subprocess.SubprocessError, ValueError):
        return [R("Build", "extension_zones", AMBER, "Extension zones match the packs", "could not run the generator", "cd extension && npm run gen")]
    if fresh != have:
        return [R("Build", "extension_zones", RED, "Extension zones match the packs", "bundled.json differs from what the packs generate", "cd extension && npm run gen && npm run build")]
    content = ext / "dist" / "content.js"
    if content.is_file():
        text = content.read_text(errors="replace")
        absent = [z for z in have["zones"]["vocabulary"] if f'"{z}"' not in text and z not in text]
        if absent:
            return [R("Build", "extension_zones", AMBER, "Extension zones match the packs", f"bundled.json is current but extension/dist lacks zones: {', '.join(absent[:4])}", "cd extension && npm run build")]
    return [R("Build", "extension_zones", GREEN, "Extension zones match the packs", f"{len(have['zones']['vocabulary'])} zones, {len(have['zones']['sites'])} site configs, npm run gen is clean")]


def check_desktop(ctx: Ctx) -> list[Result]:
    d = ctx.repo / "apps" / "desktop"
    if not (d / "node_modules").is_dir():
        return [R("Build", "desktop", RED, "Desktop app", "node_modules missing", "cd apps/desktop && npm install")]
    res = []
    out_dir = d / "out"
    res.append(R("Build", "desktop_build", GREEN if out_dir.is_dir() and any(out_dir.iterdir()) else AMBER, "Desktop app build output (apps/desktop/out)",
                 "present" if out_dir.is_dir() and any(out_dir.iterdir()) else "absent: npm run dev builds on start; npm run build for a packaged run", "" if out_dir.is_dir() else "cd apps/desktop && npm run build"))
    cache = ctx.repo / "data" / "preflight" / "desktop_typecheck.json"
    if ctx.deep:
        t0 = time.time()
        try:
            p = subprocess.run(["npm", "run", "typecheck", "--silent"], cwd=d, capture_output=True, text=True, timeout=600)
            ok = p.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"ok": ok, "at": time.time(), "seconds": round(time.time() - t0, 1)}))
        res.append(R("Build", "desktop_typecheck", GREEN if ok else RED, "Desktop typecheck", f"{'passes' if ok else 'FAILS'} ({time.time() - t0:.0f} s, run now)", "" if ok else "cd apps/desktop && npm run typecheck"))
    elif cache.is_file():
        try:
            c = json.loads(cache.read_text())
            age = ctx.now - float(c["at"])
            st = (GREEN if age < 43200 else AMBER) if c.get("ok") else RED
            res.append(R("Build", "desktop_typecheck", st, "Desktop typecheck (cached)", f"{'passed' if c.get('ok') else 'FAILED'} {age_text(age)} ago" + ("" if age < 43200 else ": stale"), "" if st == GREEN else "rerun with --deep"))
        except (ValueError, KeyError):
            res.append(R("Build", "desktop_typecheck", AMBER, "Desktop typecheck", "cache unreadable; skipped", "rerun with --deep"))
    else:
        res.append(R("Build", "desktop_typecheck", AMBER, "Desktop typecheck", "skipped (no cached result; takes about a minute)", "rerun with --deep"))
    return res


# ------------------------------------------------------------------------------------------------ checks: offline
EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)|url\(\s*["']?(https?://[^)"']+)|@import\s+["'](https?://[^"']+)|\bfetch\(\s*["'`](https?://[^"'`]+)""")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _external_urls(text: str) -> list[str]:
    out = []
    for m in EXTERNAL.finditer(text):
        url = next(g for g in m.groups() if g)
        host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0]
        if host not in LOCAL_HOSTS and "w3.org" not in host:
            out.append(url)
    return out


def check_offline(ctx: Ctx) -> list[Result]:
    res = []
    dash = ctx.repo / "apps" / "dashboard"
    found: dict[str, list[str]] = {}
    files = [dash / "index.html"] + [p for p in (dash / "src").rglob("*") if p.suffix in (".ts", ".tsx", ".css", ".html")] if (dash / "src").is_dir() else [dash / "index.html"]
    for f in files:
        if f.is_file():
            urls = _external_urls(f.read_text(errors="replace"))
            if urls:
                found[str(f.relative_to(ctx.repo))] = urls[:3]
    if found:
        first = next(iter(found.items()))
        res.append(R("Offline", "offline_dashboard", RED, "Dashboard needs no remote URL", f"{sum(len(v) for v in found.values())} remote loads, e.g. {first[0]}: {first[1][0]}", "serve it locally (@fontsource, bundled assets) or remove the load"))
    else:
        fonts = (dash / "node_modules" / "@fontsource-variable").is_dir()
        res.append(R("Offline", "offline_dashboard", GREEN if fonts else AMBER, "Dashboard needs no remote URL", "no remote script, style, font or fetch in index.html or src" + ("" if fonts else "; fonts package not installed (cd apps/dashboard && npm install)")))
    auth = ctx.env.get("VITE_AUTH0_DOMAIN") or (dash / ".env.local").is_file() and "AUTH0" in (dash / ".env.local").read_text(errors="replace")
    res.append(R("Offline", "offline_auth", AMBER if auth else GREEN, "Auth0 sign-in", "configured: sign-in needs the network (a local profile fallback exists)" if auth else "off (local profile only)",
                 "leave the Auth0 values unset for the offline demo" if auth else ""))
    golden = ctx.repo / "data" / "golden" / "benefits_golden.json"
    shots = ctx.repo / "data" / "golden" / "screenshots"
    ok_g = False
    if golden.is_file():
        try:
            json.loads(golden.read_text())
            ok_g = True
        except ValueError:
            ok_g = False
    nshots = len([p for p in shots.glob("*") if p.is_file()]) if shots.is_dir() else 0
    if ok_g and nshots:
        res.append(R("Offline", "offline_golden", GREEN, "Cached golden run", f"benefits_golden.json parses, {nshots} screenshots"))
    elif ok_g:
        res.append(R("Offline", "offline_golden", AMBER, "Cached golden run", "benefits_golden.json parses but data/golden/screenshots is empty", "record the golden run while online"))
    else:
        res.append(R("Offline", "offline_golden", RED, "Cached golden run", "data/golden/benefits_golden.json missing or not JSON", "record the golden run while online (the cached fallback needs it)"))
    synth = ctx.repo / "data" / "synthetic"
    n = len(list(synth.glob("*/events.jsonl"))) if synth.is_dir() else 0
    res.append(R("Offline", "offline_synthetic", GREEN if n >= 4 else RED, "Synthetic data (genome, presence, evidence)", f"{n} persona or apprentice files" if n else "missing", "" if n >= 4 else "uv run --package understudy-engine understudy synth --all"))
    st, body, _ = ctx.get(ctx.engine, "/health") if port_open(ctx.engine_port) else (None, None, None)
    if isinstance(body, dict):
        mock = bool(body.get("mock"))
        res.append(R("Offline", "offline_engine", GREEN if mock else AMBER, "Engine works with the network off", "mock mode: no model call is made" if mock else "NOT in mock mode: model calls need the network", "" if mock else "restart with make demo"))
    return res


CHECKS: list[tuple[str, Callable[[Ctx], list[Result]]]] = [
    ("python", check_python), ("node", check_node), ("env_file", check_env_file), ("mock", check_mock), ("disk", check_disk),
    ("chromium", check_chromium), ("voice", check_voice), ("models", check_models),
    ("ports", check_ports), ("engine", check_engine), ("agent", check_agent), ("sandbox", check_sandbox),
    ("engine_home", check_engine_home), ("kill", check_kill),
    ("demo_seed", check_demo_seed), ("coach", check_coach), ("eval_report", check_eval_report),
    ("extension_build", check_extension_build), ("extension_zones", check_extension_zones), ("desktop", check_desktop),
    ("offline", check_offline),
]


# ------------------------------------------------------------------------------------------------ run and print
def make_redactor(ctx: Ctx) -> Callable[[str], str]:
    secrets = sorted({v for k, v in {**ctx.dotenv, **ctx.env}.items() if v and len(v) >= 6 and SECRET_NAME.search(k)}, key=len, reverse=True)

    def redact(text: str) -> str:
        for s in secrets:
            text = text.replace(s, "[redacted]")
        return text
    return redact


def run(ctx: Ctx) -> list[Result]:
    results: list[Result] = []
    for name, fn in CHECKS:
        if name in ctx.skip:
            results.append(Result(name, "Environment", SKIP, name, "skipped by --skip"))
            continue
        try:
            results.extend(fn(ctx))
        except Exception as e:  # a crashing check is a red, never a silent pass
            results.append(Result(name, "Environment", RED, f"check '{name}' crashed", type(e).__name__))
    return results


def render(results: list[Result], ctx: Ctx, hints: bool, color: bool) -> str:
    redact = make_redactor(ctx)
    paint = {GREEN: "\033[32m", AMBER: "\033[33m", RED: "\033[31m", SKIP: "\033[2m"}
    label = {GREEN: "GREEN", AMBER: "AMBER", RED: "RED  ", SKIP: "SKIP "}
    lines = [f"Understudy preflight  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC  mode {ctx.mode}  repo {ctx.repo}"]
    for g in GROUPS:
        rs = [r for r in results if r.group == g]
        if not rs:
            continue
        lines.append("")
        lines.append(f"== {g}")
        for r in rs:
            tag = f"{paint[r.status]}{label[r.status]}\033[0m" if color else label[r.status]
            lines.append(f"{tag}  {r.title}" + (f": {r.detail}" if r.detail else ""))
            if hints and r.hint and r.status in (AMBER, RED):
                lines.append(f"       fix: {r.hint}")
    n = {s: sum(1 for r in results if r.status == s) for s in (GREEN, AMBER, RED, SKIP)}
    lines.append("")
    verdict = "NOT READY: fix the red items" if n[RED] else "READY, read the amber notes" if n[AMBER] else "READY"
    lines.append(f"{n[GREEN]} green, {n[AMBER]} amber, {n[RED]} red, {n[SKIP]} skipped.  {verdict}")
    if (n[RED] or n[AMBER]) and not hints:
        lines.append("Run again with --fix-hints for what to do about each.")
    return redact("\n".join(lines))


def build_ctx(args: argparse.Namespace) -> Ctx:
    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[1]
    dotenv = parse_dotenv(repo / ".env")
    env = {**dotenv, **{k: v for k, v in os.environ.items() if k in dotenv or k.startswith(("UNDERSTUDY_", "ELEVENLABS_", "OPENAI_", "VITE_AUTH0", "AUTH0", "ENGINE_", "AGENT_", "DASHBOARD_", "SANDBOX_"))}}

    def port(flag: int | None, name: str, default: int) -> int:
        return int(flag if flag is not None else env.get(name, default))

    base = int(env.get("SANDBOX_PORT_BASE", 7801))
    sites = tuple(int(x) for x in args.site_ports.split(",")) if args.site_ports else tuple(int(env.get(f"SANDBOX_PORT_{s}", base + i)) for i, s in enumerate("ABC"))
    if len(sites) != 3:
        raise SystemExit("--site-ports needs three ports, for example 7801,7802,7803")
    return Ctx(repo=repo, mode=args.mode, deep=args.deep, timeout=args.timeout, engine_port=port(args.engine_port, "ENGINE_PORT", 7700),
               agent_port=port(args.agent_port, "AGENT_PORT", 7710), dashboard_port=port(args.dashboard_port, "DASHBOARD_PORT", 5173),
               desktop_port=port(args.desktop_port, "DESKTOP_PORT", 7720), site_ports=sites, env=env, dotenv=dotenv,
               skip={s for s in (args.skip or "").split(",") if s})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Understudy demo-day preflight (read-only).")
    ap.add_argument("--fix-hints", action="store_true", help="print what to do about each amber and red item")
    ap.add_argument("--mode", choices=["demo", "dev"], default="demo", help="demo expects the isolated demo home, mock mode and the seed")
    ap.add_argument("--deep", action="store_true", help="also run the desktop typecheck (about a minute) and cache the result")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--repo")
    ap.add_argument("--engine-port", type=int)
    ap.add_argument("--agent-port", type=int)
    ap.add_argument("--dashboard-port", type=int)
    ap.add_argument("--desktop-port", type=int)
    ap.add_argument("--site-ports", help="three ports, e.g. 7801,7802,7803")
    ap.add_argument("--skip", help="comma list of checks to skip: " + ",".join(n for n, _ in CHECKS))
    args = ap.parse_args(argv)
    ctx = build_ctx(args)
    results = run(ctx)
    if args.json:
        redact = make_redactor(ctx)
        print(redact(json.dumps([r.__dict__ for r in results], indent=1)))
    else:
        print(render(results, ctx, args.fix_hints, sys.stdout.isatty() and not os.environ.get("NO_COLOR")))
    return 1 if any(r.status == RED for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
