"""scripts/preflight.py against ephemeral stand-ins for the stack: stopped, healthy, and each way of being broken."""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preflight", REPO / "scripts" / "preflight.py")
P = importlib.util.module_from_spec(spec)
sys.modules["preflight"] = P
spec.loader.exec_module(P)

SECRET = "sk-test-DO-NOT-PRINT-9f3a7c21"
MACHINE = {"node", "chromium", "models", "extension_zones", "desktop", "disk"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """A stand-in service: routes maps path -> (status, body); body dicts and lists are sent as JSON."""

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                status, body = outer.routes.get(path, (404, {"error": {"code": "not_found"}}))
                raw = (json.dumps(body) if isinstance(body, (dict, list)) else str(body)).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json" if isinstance(body, (dict, list)) else "text/html")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


@pytest.fixture
def repo(tmp_path):
    """A tiny repo: git-ignored .env with a fake secret, golden run, synthetic data, a built extension, a dashboard."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / ".env").write_text(f"OPENAI_API_KEY={SECRET}\nOPENAI_MODEL_PLANNER=m1\nOPENAI_MODEL_FAST=m2\nOPENAI_MODEL_COMPUTER_USE=m3\nUNDERSTUDY_MOCK=1\nELEVENLABS_API_KEY={SECRET}-voice\n")
    (tmp_path / ".env").chmod(0o600)
    g = tmp_path / "data" / "golden"
    (g / "screenshots").mkdir(parents=True)
    (g / "benefits_golden.json").write_text("{}")
    (g / "screenshots" / "s1.png").write_bytes(b"x")
    for n in "abcd":
        (tmp_path / "data" / "synthetic" / n).mkdir(parents=True)
        (tmp_path / "data" / "synthetic" / n / "events.jsonl").write_text("")
    (tmp_path / "data" / "demo-home").mkdir(parents=True)
    ext = tmp_path / "extension"
    (ext / "src" / "generated").mkdir(parents=True)
    (ext / "src" / "a.ts").write_text("x")
    (ext / "manifest.json").write_text("{}")
    (ext / "popup.html").write_text("<html>")
    time.sleep(0.02)
    (ext / "dist").mkdir()
    for f in ("manifest.json", "content.js", "worker.js", "popup.js", "popup.html"):
        (ext / "dist" / f).write_text("x")
    dash = tmp_path / "apps" / "dashboard"
    (dash / "src").mkdir(parents=True)
    (dash / "node_modules" / "@fontsource-variable").mkdir(parents=True)
    (dash / "index.html").write_text('<html><script type="module" src="/src/main.tsx"></script></html>')
    return tmp_path


def healthy_engine(repo: Path, **over) -> dict:
    r = {
        "/health": (200, {"ok": True, "version": "0.1.0", "mock": True, "routers": {"data": True, "analytics": True, "handoff": True, "coach": True},
                           "warm": {"genome": True, "coach": True, "analytics": True}}),
        "/memory": (200, {"path": str(repo / "data" / "demo-home" / "memory.md"), "revision": 3}),
        "/identity": (200, {"person": "p_learn01", "role": "benefits-processor"}),
        "/memory/proposals": (200, [{"id": "r1", "status": "proposed"}]),
        "/routines": (200, [{"id": "calc-entry-3x", "status": "proposed", "rung": "A0"}]),
        "/coach/next": (200, {"meta": {}, "data": {"action": "silent", "level": "L1", "reason_codes": ["no_active_task"]}}),
        "/eval/report": (200, {"generated_at": iso(5), "mock": True, "sections": {}}),
        "/kill": (200, {"killed": False, "at": None}),
    }
    r.update(over)
    return r


class Stack:
    def __init__(self, repo: Path, engine: dict | None = None, agent: dict | None = None, sites: dict | None = None):
        self.repo = repo
        self.engine = Server(engine if engine is not None else healthy_engine(repo))
        self.agent = Server(agent if agent is not None else {"/health": (200, {"ok": True, "mock": True, "supervisor": {"generation": 0, "state": "idle"}})})
        clean = {"notes": {}, "submissions": [], "exfil_hits": [], "calculations": [], "cliff_opens": [], "pages_served": 0}
        site_routes = sites if sites is not None else {"/healthz": (200, {"ok": True, "site": "a"}), "/__state": (200, clean)}
        self.sites = [Server(site_routes) for _ in range(3)]
        self.dash = Server({"/": (200, "<html>Understudy</html>")})
        self.desk = Server({})
        self.servers = [self.engine, self.agent, *self.sites, self.dash, self.desk]

    def ctx(self, **kw) -> "P.Ctx":
        env = P.parse_dotenv(self.repo / ".env")
        base = dict(repo=self.repo, engine_port=self.engine.port, agent_port=self.agent.port, dashboard_port=self.dash.port, desktop_port=self.desk.port,
                    site_ports=tuple(s.port for s in self.sites), env=env, dotenv=P.parse_dotenv(self.repo / ".env"), skip=set(MACHINE))
        base.update(kw)
        return P.Ctx(**base)

    def close(self):
        for s in self.servers:
            s.close()


@pytest.fixture
def stack(repo):
    s = Stack(repo)
    yield s
    s.close()


def by_id(results, id_):
    rs = [r for r in results if r.id == id_]
    assert rs, f"no result with id {id_}: {[r.id for r in results]}"
    return rs[0]


def stopped_ctx(repo, **kw):
    ports = [free_port() for _ in range(7)]
    env = P.parse_dotenv(repo / ".env")
    base = dict(repo=repo, engine_port=ports[0], agent_port=ports[1], dashboard_port=ports[2], desktop_port=ports[3], site_ports=tuple(ports[4:7]),
                env=env, dotenv=env, skip=set(MACHINE))
    base.update(kw)
    return P.Ctx(**base)


# ------------------------------------------------------------------------------------------------ stopped and running
def test_a_stopped_stack_is_red_and_the_exit_code_says_so(repo, capsys):
    ctx = stopped_ctx(repo)
    results = P.run(ctx)
    for id_ in (f"port_{ctx.engine_port}", f"port_{ctx.agent_port}", f"port_{ctx.site_ports[0]}", f"port_{ctx.dashboard_port}"):
        assert by_id(results, id_).status == P.RED
    assert by_id(results, f"port_{ctx.desktop_port}").status == P.AMBER            # the desktop app is optional for the rest
    assert by_id(results, "engine_health").status == P.RED and by_id(results, "agent_health").status == P.RED
    assert by_id(results, "sandbox_a").status == P.RED
    # downstream checks say "not checked" instead of piling more reds on one cause
    assert by_id(results, "demo_identity").status == P.AMBER and "engine is down" in by_id(results, "demo_identity").detail
    assert by_id(results, "coach").status == P.AMBER
    code = P.main(["--repo", str(repo), "--engine-port", str(ctx.engine_port), "--agent-port", str(ctx.agent_port), "--dashboard-port", str(ctx.dashboard_port),
                   "--desktop-port", str(ctx.desktop_port), "--site-ports", ",".join(map(str, ctx.site_ports)), "--skip", ",".join(sorted(MACHINE))])
    out = capsys.readouterr().out
    assert code == 1 and "NOT READY" in out


def test_a_healthy_stack_has_no_red_and_exits_zero(repo, stack, capsys):
    results = P.run(stack.ctx())
    reds = [(r.id, r.detail) for r in results if r.status == P.RED]
    assert reds == []
    for id_ in ("engine_health", "agent_health", "sandbox_a", "sandbox_b", "sandbox_c", "sandbox_state", "engine_home", "kill_file", "demo_identity",
                "demo_proposal", "demo_routine", "coach", "eval_report", "mock", "extension_build", "offline_dashboard", "offline_golden", "offline_engine"):
        assert by_id(results, id_).status == P.GREEN, (id_, by_id(results, id_).detail)
    c = stack.ctx()
    code = P.main(["--repo", str(repo), "--engine-port", str(c.engine_port), "--agent-port", str(c.agent_port), "--dashboard-port", str(c.dashboard_port),
                   "--desktop-port", str(c.desktop_port), "--site-ports", ",".join(map(str, c.site_ports)), "--skip", ",".join(sorted(MACHINE))])
    assert code == 0 and "READY" in capsys.readouterr().out


def test_the_cli_runs_as_a_script_and_returns_the_exit_code(repo):
    ports = [free_port() for _ in range(7)]
    cmd = [sys.executable, str(REPO / "scripts" / "preflight.py"), "--repo", str(repo), "--engine-port", str(ports[0]), "--agent-port", str(ports[1]),
           "--dashboard-port", str(ports[2]), "--desktop-port", str(ports[3]), "--site-ports", ",".join(map(str, ports[4:])), "--skip", ",".join(sorted(MACHINE)), "--fix-hints"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert p.returncode == 1
    assert "RED" in p.stdout and "fix: make dev" in p.stdout
    assert SECRET not in p.stdout + p.stderr


# ------------------------------------------------------------------------------------------------ the owner's real home
def test_the_owners_real_home_is_red_in_demo_mode_and_amber_in_dev_mode(repo):
    real = Path.home() / ".understudy" / "memory.md"
    eng = healthy_engine(repo, **{"/memory": (200, {"path": str(real), "revision": 1})})
    s = Stack(repo, engine=eng)
    try:
        demo = by_id(P.run(s.ctx(mode="demo")), "engine_home")
        assert demo.status == P.RED and "REAL" in demo.detail and "make demo" in demo.hint
        dev = by_id(P.run(s.ctx(mode="dev")), "engine_home")
        assert dev.status == P.AMBER
    finally:
        s.close()


def test_a_custom_home_is_amber_in_demo_mode_and_the_demo_home_is_green(repo, stack, tmp_path):
    assert by_id(P.run(stack.ctx()), "engine_home").status == P.GREEN
    stack.engine.routes["/memory"] = (200, {"path": str(tmp_path / "elsewhere" / "memory.md")})
    r = by_id(P.run(stack.ctx()), "engine_home")
    assert r.status == P.AMBER and "not the demo home" in r.detail


# ------------------------------------------------------------------------------------------------ kill flag
def test_a_stale_kill_flag_file_is_red(repo, stack):
    (repo / "data" / "KILL").write_text("")
    r = by_id(P.run(stack.ctx()), "kill_file")
    assert r.status == P.RED and "rm" in r.hint


def test_an_engine_that_reports_killed_is_red(repo):
    s = Stack(repo, engine=healthy_engine(repo, **{"/kill": (200, {"killed": True, "at": "now"})}))
    try:
        assert by_id(P.run(s.ctx()), "kill_state").status == P.RED
    finally:
        s.close()


# ------------------------------------------------------------------------------------------------ engine health variants
def test_engine_routers_warmth_and_mock_mode(repo):
    h = healthy_engine(repo)["/health"][1]
    cases = [
        ({**h, "routers": {**h["routers"], "coach": False}}, P.RED, "routers not loaded: coach"),
        ({**h, "warm": {"genome": True, "coach": False, "analytics": True}}, P.AMBER, "still warming: coach"),
        ({**h, "mock": False}, P.AMBER, "NOT in mock mode"),
        ({"ok": False}, P.RED, "not as the engine"),
    ]
    for body, status, text in cases:
        s = Stack(repo, engine=healthy_engine(repo, **{"/health": (200, body)}))
        try:
            r = by_id(P.run(s.ctx()), "engine_health")
            assert r.status == status and text in r.detail, (body, r)
        finally:
            s.close()


def test_something_else_on_the_engine_port_is_red(repo):
    s = Stack(repo, engine={"/health": (404, "Not Found")})
    try:
        r = by_id(P.run(s.ctx()), "engine_health")
        assert r.status == P.RED and "not as the engine" in r.detail
    finally:
        s.close()


def test_agent_busy_and_disagreeing_about_mock_are_amber(repo):
    s = Stack(repo, agent={"/health": (200, {"ok": True, "mock": False, "supervisor": {"generation": 4, "state": "running"}})})
    try:
        r = by_id(P.run(s.ctx()), "agent_health")
        assert r.status == P.AMBER and "in progress" in r.detail and "disagree about mock" in r.detail
    finally:
        s.close()


# ------------------------------------------------------------------------------------------------ sandbox
def test_dirty_sandbox_state_is_amber_with_the_reset_command(repo):
    dirty = {"/healthz": (200, {"ok": True}), "/__state": (200, {"notes": {"CN-1": {}}, "calculations": [{}], "cliff_opens": [{}], "submissions": [], "exfil_hits": []})}
    s = Stack(repo, sites=dirty)
    try:
        r = by_id(P.run(s.ctx()), "sandbox_state")
        assert r.status == P.AMBER and "__reset" in r.hint and "1 notes" in r.detail
    finally:
        s.close()


def test_a_sandbox_site_that_is_down_is_red_and_one_that_answers_wrongly_too(repo):
    s = Stack(repo, sites={"/healthz": (500, {"x": 1})})
    try:
        assert by_id(P.run(s.ctx()), "sandbox_a").status == P.RED
    finally:
        s.close()
    ctx = stopped_ctx(repo)
    assert by_id(P.run(ctx), "sandbox_b").status == P.RED


# ------------------------------------------------------------------------------------------------ the demo seed
def test_missing_seed_is_red_in_demo_mode_and_amber_in_dev_mode(repo):
    bare = healthy_engine(repo, **{"/identity": (404, {"error": {"code": "not_onboarded"}}), "/memory/proposals": (200, []), "/routines": (200, [])})
    s = Stack(repo, engine=bare)
    try:
        res = P.run(s.ctx())
        assert [by_id(res, i).status for i in ("demo_identity", "demo_proposal", "demo_routine")] == [P.RED] * 3
        assert "make demo" in by_id(res, "demo_identity").hint
        dev = P.run(s.ctx(mode="dev"))
        assert [by_id(dev, i).status for i in ("demo_identity", "demo_proposal", "demo_routine")] == [P.AMBER] * 3
    finally:
        s.close()


def test_a_routine_already_consented_is_amber_and_another_person_is_red(repo):
    eng = healthy_engine(repo, **{"/routines": (200, [{"id": "calc-entry-3x", "status": "approval"}]), "/identity": (200, {"person": "p_someone", "role": "x"})})
    s = Stack(repo, engine=eng)
    try:
        res = P.run(s.ctx())
        assert by_id(res, "demo_routine").status == P.AMBER and "reseed" in by_id(res, "demo_routine").hint
        assert by_id(res, "demo_identity").status == P.RED
    finally:
        s.close()


def test_coach_failure_is_red_in_demo_mode(repo):
    s = Stack(repo, engine=healthy_engine(repo, **{"/coach/next": (404, {"error": {"code": "unknown_person"}})}))
    try:
        r = by_id(P.run(s.ctx()), "coach")
        assert r.status == P.RED and "unknown_person" in r.detail
    finally:
        s.close()


# ------------------------------------------------------------------------------------------------ evidence report
def test_eval_report_freshness_and_absence(repo):
    cases = [(healthy_engine(repo)["/eval/report"], P.GREEN), ((200, {"generated_at": iso(300), "mock": True}), P.AMBER), ((404, {"error": {}}), P.RED)]
    for resp, status in cases:
        s = Stack(repo, engine=healthy_engine(repo, **{"/eval/report": resp}))
        try:
            r = by_id(P.run(s.ctx()), "eval_report")
            assert r.status == status, (resp, r)
            if status != P.GREEN:
                assert "make eval" in r.hint
        finally:
            s.close()


def test_eval_report_file_is_used_when_the_engine_is_down(repo):
    (repo / "evals").mkdir()
    (repo / "evals" / "report.json").write_text("{}")
    assert by_id(P.run(stopped_ctx(repo)), "eval_report").status == P.AMBER
    (repo / "evals" / "report.json").unlink()
    assert by_id(P.run(stopped_ctx(repo)), "eval_report").status == P.RED


# ------------------------------------------------------------------------------------------------ .env and secrets
def test_secrets_are_never_printed_in_any_output_format(repo, stack, capsys):
    ctx = stack.ctx()
    results = P.run(ctx)
    text = P.render(results, ctx, hints=True, color=False)
    assert SECRET not in text and "OPENAI_API_KEY set" in text
    # even a check that tries to leak is redacted at the last step
    leaky = results + [P.Result("leak", "Environment", P.AMBER, "leaky", f"value {SECRET} and {SECRET}-voice", f"echo {SECRET}")]
    assert SECRET not in P.render(leaky, ctx, hints=True, color=False)
    P.main(["--repo", str(repo), "--json", "--skip", ",".join(sorted(MACHINE)), "--engine-port", str(ctx.engine_port)])
    assert SECRET not in capsys.readouterr().out


def test_a_crashing_check_is_red_and_does_not_leak(repo, stack, monkeypatch):
    def boom(ctx):
        raise RuntimeError(f"secret in message {SECRET}")
    monkeypatch.setattr(P, "CHECKS", [("boom", boom)])
    res = P.run(stack.ctx())
    assert res[0].status == P.RED and res[0].detail == "RuntimeError" and SECRET not in P.render(res, stack.ctx(), True, False)


def test_env_file_states(repo, stack):
    ctx = stack.ctx()
    ok = P.check_env_file(ctx)
    assert {r.id: r.status for r in ok} == {"env_file": P.GREEN, "env_ignored": P.GREEN}
    (repo / ".env").chmod(0o644)
    assert any(r.id == "env_perms" and r.status == P.AMBER for r in P.check_env_file(ctx))
    (repo / ".env").chmod(0o600)
    (repo / ".gitignore").write_text("")
    assert any(r.id == "env_ignored" and r.status == P.RED for r in P.check_env_file(ctx))
    # missing keys: amber in mock mode, red when live
    (repo / ".env").write_text("OPENAI_MODEL_FAST=m2\n")
    mock_ctx = stack.ctx(dotenv=P.parse_dotenv(repo / ".env"), env={"UNDERSTUDY_MOCK": "1"})
    r = P.check_env_file(mock_ctx)[0]
    assert r.status == P.AMBER and "OPENAI_API_KEY NOT set" in r.detail
    live_ctx = stack.ctx(dotenv=P.parse_dotenv(repo / ".env"), env={})
    assert P.check_env_file(live_ctx)[0].status == P.RED
    (repo / ".env").unlink()
    assert P.check_env_file(live_ctx)[0].status == P.RED and P.check_env_file(mock_ctx)[0].status == P.AMBER


def test_dotenv_parsing_handles_quotes_comments_and_export(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# c\nexport A=1\nB=\"two words\"\nC='x'\n\nD=\nbad line\n")
    assert P.parse_dotenv(f) == {"A": "1", "B": "two words", "C": "x", "D": ""}


def test_mock_state_prefers_the_engines_report(repo, stack):
    ctx = stack.ctx(env={"UNDERSTUDY_MOCK": "0"})
    r = by_id(P.run(ctx), "mock")
    assert r.status == P.GREEN and "engine reports mock True" in r.detail and "say 0" in r.detail
    s = Stack(repo, engine=healthy_engine(repo, **{"/health": (200, {**healthy_engine(repo)["/health"][1], "mock": False})}))
    try:
        assert by_id(P.run(s.ctx()), "mock").status == P.AMBER
    finally:
        s.close()
    down = by_id(P.run(stopped_ctx(repo, env={"UNDERSTUDY_MOCK": "0"})), "mock")
    assert down.status == P.AMBER and "make demo" in down.detail


# ------------------------------------------------------------------------------------------------ machine checks
def test_python_node_and_disk(repo, monkeypatch):
    ctx = stopped_ctx(repo)
    assert P.check_python(ctx)[0].status == P.GREEN
    assert P.check_node(ctx)[0].status in (P.GREEN, P.RED)
    monkeypatch.setattr(P.shutil, "disk_usage", lambda p: type("U", (), {"free": 0.5e9})())
    assert P.check_disk(ctx)[0].status == P.RED
    monkeypatch.setattr(P.shutil, "disk_usage", lambda p: type("U", (), {"free": 3e9})())
    assert P.check_disk(ctx)[0].status == P.AMBER
    monkeypatch.setattr(P.shutil, "disk_usage", lambda p: type("U", (), {"free": 90e9})())
    assert P.check_disk(ctx)[0].status == P.GREEN


def test_chromium_detection(repo, tmp_path, monkeypatch):
    ctx = stopped_ctx(repo)
    empty = tmp_path / "pw-empty"
    empty.mkdir()
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(empty))
    monkeypatch.setattr(P.Path, "home", classmethod(lambda cls: tmp_path / "nohome"))
    assert P.check_chromium(ctx)[0].status == P.RED
    (empty / "chromium-9999").mkdir()
    assert P.check_chromium(ctx)[0].status == P.RED                     # not marked complete
    (empty / "chromium-9999" / "INSTALLATION_COMPLETE").write_text("")
    assert P.check_chromium(ctx)[0].status == P.GREEN


def test_voice_flag_states(repo):
    base = P.parse_dotenv(repo / ".env")
    def state(env, cache=0):
        d = repo / "data" / "voice_cache"
        d.mkdir(parents=True, exist_ok=True)
        for p in d.glob("*"):
            p.unlink()
        for i in range(cache):
            (d / f"{i}.mp3").write_bytes(b"x")
        return P.check_voice(stopped_ctx(repo, env={**base, **env}))[0]
    assert state({"UNDERSTUDY_VOICE": "0"}).status == P.GREEN
    assert state({"UNDERSTUDY_VOICE": "1", "UNDERSTUDY_MOCK": "1"}).status == P.AMBER            # flag on, mock, no cache: silence
    assert state({"UNDERSTUDY_VOICE": "1", "UNDERSTUDY_MOCK": "1"}, cache=3).status == P.GREEN
    assert state({"UNDERSTUDY_VOICE": "1", "UNDERSTUDY_MOCK": "0"}).status == P.AMBER            # live, uncached: needs the network
    assert "ELEVENLABS" not in state({"UNDERSTUDY_VOICE": "1"}).detail or SECRET not in state({"UNDERSTUDY_VOICE": "1"}).detail


def test_model_boot_check_makes_no_network_call_in_mock_mode(repo, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("network call in mock mode")
    monkeypatch.setattr(P.urllib.request, "urlopen", forbidden)
    r = P.check_models(stopped_ctx(repo, env={"UNDERSTUDY_MOCK": "1"}))[0]
    assert r.status == P.GREEN and "no network call" in r.detail


def test_model_boot_check_reports_unusable_ids_without_the_key(repo, monkeypatch):
    boot = pytest.importorskip("understudy_agent.models.boot")
    rep = boot.BootReport(ok=False, mock=False, configured={"planner": "gpt-x"}, missing={"planner": "gpt-x"}, usable=["gpt-a"], message="m")
    monkeypatch.setattr(boot, "boot_check", lambda **k: rep)
    ctx = stopped_ctx(repo, env={"UNDERSTUDY_MOCK": "0"})
    r = P.check_models(ctx)[0]
    assert r.status == P.RED and "planner=gpt-x" in r.detail
    rep.ok, rep.missing, rep.usable = True, {}, ["gpt-a", "gpt-b"]
    assert P.check_models(ctx)[0].status == P.GREEN


# ------------------------------------------------------------------------------------------------ build checks
def test_extension_build_missing_stale_and_current(repo):
    ctx = stopped_ctx(repo)
    assert by_id(P.check_extension_build(ctx), "extension_build").status == P.GREEN
    (repo / "extension" / "src" / "generated" / "bundled.json").write_text("{}")      # rewritten by npm test: must not look stale
    assert P.check_extension_build(ctx)[0].status == P.GREEN
    src = repo / "extension" / "src" / "a.ts"
    src.write_text("changed")
    import os
    os.utime(src, (time.time() + 30, time.time() + 30))                   # a source edit after the build
    r = P.check_extension_build(ctx)[0]
    assert r.status == P.AMBER and "stale" in r.detail and "npm run build" in r.hint
    (repo / "extension" / "dist" / "worker.js").unlink()
    assert P.check_extension_build(ctx)[0].status == P.RED


def test_extension_zones_against_the_real_packs():
    """Static, read-only: the committed bundle must equal what the packs generate, and dist must carry the zones."""
    ctx = P.Ctx(repo=REPO)
    r = P.check_extension_zones(ctx)[0]
    assert r.status in (P.GREEN, P.AMBER), r.detail           # amber only if node_modules or dist is absent on this machine
    if (REPO / "extension" / "node_modules" / "yaml").is_dir():
        assert r.status == P.GREEN or "dist lacks zones" in r.detail


def test_extension_zones_detects_drift(tmp_path):
    ext = tmp_path / "extension"
    (ext / "node_modules" / "yaml").mkdir(parents=True)
    (ext / "src" / "generated").mkdir(parents=True)
    (ext / "src" / "generated" / "bundled.json").write_text("{}")
    r = P.check_extension_zones(P.Ctx(repo=tmp_path))[0]
    assert r.id == "extension_zones" and r.status in (P.AMBER, P.RED)       # cannot generate: never a green
    assert P.check_extension_zones(P.Ctx(repo=tmp_path / "nowhere"))[0].status == P.RED


def test_desktop_checks_use_the_cached_typecheck(repo):
    d = repo / "apps" / "desktop"
    assert P.check_desktop(stopped_ctx(repo))[0].status == P.RED          # no node_modules
    (d / "node_modules").mkdir(parents=True)
    (d / "out").mkdir()
    (d / "out" / "main.js").write_text("x")
    cache = repo / "data" / "preflight" / "desktop_typecheck.json"
    cache.parent.mkdir(parents=True)
    def status():
        return {r.id: r.status for r in P.check_desktop(stopped_ctx(repo))}
    assert status() == {"desktop_build": P.GREEN, "desktop_typecheck": P.AMBER}          # nothing cached: skipped, amber
    cache.write_text(json.dumps({"ok": True, "at": time.time()}))
    assert status()["desktop_typecheck"] == P.GREEN
    cache.write_text(json.dumps({"ok": True, "at": time.time() - 90000}))
    assert status()["desktop_typecheck"] == P.AMBER
    cache.write_text(json.dumps({"ok": False, "at": time.time()}))
    assert status()["desktop_typecheck"] == P.RED


# ------------------------------------------------------------------------------------------------ offline readiness
def test_offline_readiness_detects_remote_loads_and_missing_golden(repo):
    ctx = stopped_ctx(repo)
    res = P.check_offline(ctx)
    assert by_id(res, "offline_dashboard").status == P.GREEN and by_id(res, "offline_golden").status == P.GREEN and by_id(res, "offline_synthetic").status == P.GREEN
    (repo / "apps" / "dashboard" / "index.html").write_text('<link rel="stylesheet" href="https://fonts.example.com/css?family=X">')
    r = by_id(P.check_offline(ctx), "offline_dashboard")
    assert r.status == P.RED and "fonts.example.com" in r.detail
    (repo / "apps" / "dashboard" / "index.html").write_text("<html></html>")
    (repo / "apps" / "dashboard" / "src" / "x.ts").write_text('const r = await fetch("https://api.example.org/x"); const ok = fetch("http://127.0.0.1:7700/health");')
    assert by_id(P.check_offline(ctx), "offline_dashboard").status == P.RED
    (repo / "apps" / "dashboard" / "src" / "x.ts").write_text('// docs: https://auth0.com/docs and <a href="#/x">x</a> ; const u = "http://localhost:5173"')
    assert by_id(P.check_offline(ctx), "offline_dashboard").status == P.GREEN     # a mention in text is not a load
    (repo / "data" / "golden" / "benefits_golden.json").write_text("not json")
    assert by_id(P.check_offline(ctx), "offline_golden").status == P.RED
    (repo / "data" / "golden" / "benefits_golden.json").write_text("{}")
    for p in (repo / "data" / "golden" / "screenshots").glob("*"):
        p.unlink()
    assert by_id(P.check_offline(ctx), "offline_golden").status == P.AMBER
    (repo / "apps" / "dashboard" / ".env.local").write_text("VITE_AUTH0_DOMAIN=x\n")
    assert by_id(P.check_offline(ctx), "offline_auth").status == P.AMBER


def test_the_real_repos_dashboard_and_golden_run_pass_the_offline_checks():
    """Read-only against the real tree: the demo's offline promise holds on this checkout."""
    ctx = P.Ctx(repo=REPO, engine_port=free_port(), env={})
    res = {r.id: r for r in P.check_offline(ctx)}
    assert res["offline_dashboard"].status in (P.GREEN, P.AMBER), res["offline_dashboard"].detail
    assert res["offline_golden"].status in (P.GREEN, P.AMBER)


# ------------------------------------------------------------------------------------------------ output
def test_fix_hints_only_with_the_flag_and_only_for_amber_and_red(repo, stack):
    ctx = stopped_ctx(repo)
    res = P.run(ctx)
    plain = P.render(res, ctx, hints=False, color=False)
    hinted = P.render(res, ctx, hints=True, color=False)
    assert "fix:" not in plain and "--fix-hints" in plain
    assert "fix: make dev" in hinted
    greens = [r for r in res if r.status == P.GREEN]
    for g in greens:
        assert f"{g.title}" in hinted
    ok_ctx = stack.ctx()
    assert "fix:" not in P.render([r for r in P.run(ok_ctx) if r.status == P.GREEN], ok_ctx, hints=True, color=False)


def test_json_output_is_parseable_and_summary_counts_add_up(repo, stack, capsys):
    c = stack.ctx()
    code = P.main(["--repo", str(repo), "--json", "--engine-port", str(c.engine_port), "--agent-port", str(c.agent_port), "--dashboard-port", str(c.dashboard_port),
                   "--desktop-port", str(c.desktop_port), "--site-ports", ",".join(map(str, c.site_ports)), "--skip", ",".join(sorted(MACHINE))])
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and all(set(d) >= {"id", "group", "status", "title"} for d in data)
    text = P.render(P.run(c), c, False, False)
    counts = [int(x.split()[0]) for x in text.splitlines()[-1].split(".")[0].split(", ")]
    assert sum(counts) == len(P.run(c))


def test_color_is_off_when_not_a_terminal(repo, stack):
    c = stack.ctx()
    text = P.render(P.run(c), c, False, color=False)
    assert "\033[" not in text


def test_skip_marks_checks_as_skipped_and_never_as_red(repo):
    c = stopped_ctx(repo, skip={"engine", "ports"})
    res = {r.id: r for r in P.run(c)}
    assert res["engine"].status == P.SKIP and res["ports"].status == P.SKIP


def test_nothing_in_the_repo_is_written_by_a_normal_run(repo, stack):
    before = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if ".git" not in p.parts)
    P.run(stack.ctx())
    after = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if ".git" not in p.parts)
    assert before == after
