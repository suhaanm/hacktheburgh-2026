"""Isolated infrastructure for one participant: its own engine (ephemeral port, temp home and data dir) and a headless Chromium
with the REAL extension loaded. Never the engine on :7700 or the agent on :7710 (AGENT_PORT is pointed at a dead port so the
engine can never reach the owner's agent, and no model key is passed to the engine: the coach is rule based).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from .design import EVALS

REPO = EVALS.parent
EXT_DIST = REPO / "extension" / "dist"
DESKTOP_DEAD_URL = "http://127.0.0.1:1"
SHARED_PORTS = {"a": 7801, "b": 7802, "c": 7803}
BATCH_FLUSH_S = 4.5          # the extension batches events every 2 s


SNAPSHOT: dict = {"path": None}


def snapshot_pipeline() -> dict:
    """Freeze the code under test for the whole run: copy services/engine, services/agent and packages (packs, schema) to a temp folder and run every engine
    and sandbox process from that copy (PYTHONPATH first, cwd there), so commits and edits made by others while the run is going cannot change the coach, the
    sandbox sites or the packs mid-run. Returns {path, git_head, dirty_files, fingerprint}; the extension is frozen by its one build per world."""
    import hashlib

    snap = Path(tempfile.mkdtemp(prefix="study-sim-snapshot-"))
    ignore = shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", "tests", "*.log", "dist", "*.pyc")
    h = hashlib.sha256()
    for rel in ("services/engine", "services/agent", "packages"):
        shutil.copytree(REPO / rel, snap / rel, ignore=ignore)
    for f in sorted(p for p in snap.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(snap)).encode())
        h.update(f.read_bytes())

    def git(*a: str) -> str:
        try:
            return subprocess.run(["git", *a], cwd=str(REPO), capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    dirty = [ln[3:] for ln in git("status", "--porcelain").splitlines() if ln[3:].startswith(("services/", "packages/"))]
    info = {"path": str(snap), "git_head": git("rev-parse", "HEAD"), "uncommitted_files_in_snapshot_dirs": len(dirty), "fingerprint": h.hexdigest()[:16],
            "taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    SNAPSHOT.update(info)
    (snap / "SNAPSHOT.json").write_text(json.dumps(info, indent=1))
    return info


def snapshot_env(env: dict) -> tuple[dict, str]:
    """env and cwd for a child process: the frozen copy if a snapshot was taken, else the live repo."""
    p = SNAPSHOT.get("path")
    if not p:
        return env, str(REPO)
    env = dict(env)
    env["PYTHONPATH"] = os.pathsep.join([f"{p}/services/engine", f"{p}/services/agent"] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env, p


def drop_snapshot() -> None:
    p = SNAPSHOT.get("path")
    if p and not SNAPSHOT.get("frozen"):
        shutil.rmtree(p, ignore_errors=True)
        SNAPSHOT["path"] = None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def clean_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("OPENAI", "GEMINI", "ANTHROPIC", "UNDERSTUDY", "AGENT_PORT", "ENGINE_PORT"))}
    env.update(extra)
    return env


class EngineProc:
    """One isolated engine. ``UNDERSTUDY_MOCK=1`` only selects the engine's offline data loading: the coach, study mode and event
    store do not use a model."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="study-sim-engine-"))
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.port = 0
        self.proc: subprocess.Popen | None = None
        self.log_path = self.root / "engine.log"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: float = 150.0) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.data.mkdir(parents=True, exist_ok=True)
        src = REPO / "data" / "synthetic"                       # data, not code: read once per participant
        if src.is_dir() and not (self.data / "synthetic").exists():
            r = subprocess.run(["cp", "-cR", str(src), str(self.data / "synthetic")], capture_output=True)   # APFS clone, instant
            if r.returncode != 0:
                shutil.copytree(src, self.data / "synthetic")
        self.port = free_port()
        env = clean_env({"UNDERSTUDY_HOME": str(self.home), "UNDERSTUDY_DATA_DIR": str(self.data), "UNDERSTUDY_MOCK": "1",
                         "AGENT_PORT": "1", "PYTHONUNBUFFERED": "1"})
        code = f"from understudy_engine.cli import main; raise SystemExit(main(['serve', '--port', '{self.port}']))"
        log = open(self.log_path, "ab")
        env, cwd = snapshot_env(env)
        self.proc = subprocess.Popen([sys.executable, "-c", code], cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"engine exited early (code {self.proc.returncode}); see {self.log_path}")
            try:
                r = httpx.get(self.url + "/health", timeout=2)
                if r.status_code == 200 and "seconds" in (r.json().get("warm") or {}):
                    return                                                # all warm-ups finished: hazard model fitted
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        raise RuntimeError("engine did not become healthy in time")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def cleanup(self) -> None:
        self.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def log_issues(self) -> dict:
        """Errors in the engine's own log: tracebacks, ERROR lines and 4xx/5xx answers to the extension's POST /events."""
        txt = self.log_path.read_text(errors="replace") if self.log_path.exists() else ""
        lines = txt.splitlines()
        bad_events = [ln for ln in lines if "POST /events" in ln and any(f'" {c}' in ln for c in ("400", "401", "403", "404", "413", "422", "500", "503"))]
        return {"tracebacks": sum(1 for ln in lines if ln.startswith("Traceback")), "error_lines": sum(1 for ln in lines if " ERROR" in ln),
                "events_post_failures": len(bad_events)}


def onboard(engine_url: str, person: str, role: str = "benefits-processor") -> dict:
    q = httpx.get(f"{engine_url}/onboarding/questions", params={"role": role}, timeout=15).json()
    answers: dict = {}
    for qu in q["questions"]:
        if qu["kind"] == "multi":
            answers[qu["id"]] = [o["value"] for o in qu["options"] if o.get("default")]
        elif qu["kind"] == "single":
            answers[qu["id"]] = (next((o for o in qu["options"] if o.get("default")), qu["options"][0]))["value"]
        else:
            answers[qu["id"]] = qu.get("default_hours") or {"start": "09:00", "end": "17:30", "days": ["mon", "tue", "wed", "thu", "fri"]}
    r = httpx.post(f"{engine_url}/onboarding", json={"person": person, "role": role, "answers": answers}, timeout=30)
    r.raise_for_status()
    return r.json()


def set_study_mode(engine_url: str, person: str, block: str, skill_on: str | None, participant: str, block_no: int, level: str = "L1") -> dict:
    body = {"person": person, "block": block, "skill_on": skill_on, "level": level, "participant": participant, "block_no": block_no}
    r = httpx.post(f"{engine_url}/study/mode", json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def read_events(engine_url: str, person: str) -> list[dict]:
    r = httpx.get(f"{engine_url}/events", params={"partition": "real", "person": person, "limit": 20000}, timeout=30)
    r.raise_for_status()
    return r.json().get("events", [])


# ----------------------------------------------------------------------------------------------- the extension in Chromium
class ExtBrowser:
    """Headless Chromium (new headless, ``channel='chromium'``) with the unpacked extension; config is written through the extension's
    own service worker, like the popup does."""

    def __init__(self, pw, engine_url: str, person: str, ext_dist: Path = EXT_DIST, role: str = "benefits-processor") -> None:
        self.pw = pw
        self.ext_dist = Path(ext_dist)
        self.engine_url = engine_url
        self.person = person
        self.role = role
        self.context = None
        self.sw = None
        self.user_data = Path(tempfile.mkdtemp(prefix="study-sim-browser-"))
        self.errors: list[str] = []

    async def open(self) -> None:
        if not (self.ext_dist / "manifest.json").exists():
            raise RuntimeError(f"the extension is not built at {self.ext_dist} (cd extension && npm run build)")
        self.context = await self.pw.chromium.launch_persistent_context(
            str(self.user_data), headless=True, channel="chromium", viewport={"width": 1200, "height": 800},
            args=[f"--disable-extensions-except={self.ext_dist}", f"--load-extension={self.ext_dist}", "--no-first-run", "--no-default-browser-check"])
        self.context.on("weberror", lambda e: self.errors.append(f"weberror: {str(getattr(e, 'error', e))[:120]}"))
        sw = self.context.service_workers[0] if self.context.service_workers else await self.context.wait_for_event("serviceworker", timeout=20000)
        self.sw = sw
        for _ in range(60):
            if await sw.evaluate("async () => Boolean((await chrome.storage.local.get('salt')).salt)"):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("extension worker did not initialise")
        await self.set_config({"person": self.person, "role": self.role, "engine_url": self.engine_url, "desktop_url": DESKTOP_DEAD_URL,
                               "identity_adopted": False, "capturing": False})

    async def set_config(self, patch: dict) -> None:
        await self.sw.evaluate("async (p) => { const cur = (await chrome.storage.local.get('config')).config ?? {}; await chrome.storage.local.set({ config: { ...cur, ...p } }); }", patch)

    async def get_config(self) -> dict:
        return await self.sw.evaluate("async () => (await chrome.storage.local.get('config')).config")

    async def capture(self, on: bool) -> None:
        await self.set_config({"capturing": on})
        await asyncio.sleep(0.8)

    async def close(self) -> None:
        try:
            if self.context:
                await self.context.close()
        finally:
            shutil.rmtree(self.user_data, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- a world: sandbox sites + extension build
class World:
    """One participant worker's private world: its own sandbox sites (own port triple and process, so nobody else can touch their state),
    and the extension build whose capture config is bound to exactly those ports. ``shared=True`` is the fallback onto the shared sites on
    7801-7803 (then the caller must hold ``sandbox_lock``) with the stock extension build."""

    def __init__(self, name: str, ports: dict[str, int], ext_dist: Path, shared: bool = False) -> None:
        self.name, self.ports, self.ext_dist, self.shared = name, dict(ports), Path(ext_dist), shared
        self.proc: subprocess.Popen | None = None
        self.log_path = Path(tempfile.gettempdir()) / f"study-sim-sites-{name}.log"

    @property
    def base(self) -> dict[str, str]:
        return {s: f"http://127.0.0.1:{p}" for s, p in self.ports.items()}

    @property
    def site_a(self) -> str:
        return self.base["a"]

    @property
    def url_gov(self) -> str:
        return f"{self.base['a']}/step/1"

    @property
    def url_quick(self) -> str:
        return f"{self.base['b']}/"

    @property
    def url_note(self) -> str:
        return f"{self.base['a']}/casenote"

    def site_of(self, port: int | None) -> str | None:
        return next((s for s, p in self.ports.items() if p == port), None)

    def allowed_ports(self) -> set[int]:
        return set(self.ports.values())

    def start_sites(self, timeout: float = 30.0) -> None:
        if self.shared or self.proc:
            return
        code = ("import time\nfrom understudy_agent.sandbox_sites.runner import SandboxCluster\n"
                f"c = SandboxCluster(ports={self.ports!r}).start()\nprint('up', flush=True)\ntime.sleep(10**7)\n")
        log = open(self.log_path, "ab")
        env, cwd = snapshot_env(clean_env({}))
        self.proc = subprocess.Popen([sys.executable, "-c", code], cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"sandbox sites for world {self.name} exited early; see {self.log_path}")
            if self.up():
                return
            time.sleep(0.3)
        raise RuntimeError(f"sandbox sites for world {self.name} did not come up")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.proc = None

    def up(self) -> bool:
        try:
            return all(httpx.get(f"{u}/healthz", timeout=2).status_code == 200 for u in self.base.values())
        except Exception:  # noqa: BLE001
            return False

    def reset(self) -> None:
        httpx.post(f"{self.site_a}/__reset", timeout=5).raise_for_status()

    def state(self) -> dict:
        r = httpx.get(f"{self.site_a}/__state", timeout=5)
        r.raise_for_status()
        return r.json()


def shared_world() -> World:
    return World("shared", SHARED_PORTS, EXT_DIST, shared=True)


def load_events_json(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def build_extension(name: str, ports: dict[str, int]) -> Path:
    """The real extension, built so its capture config is bound to this world's ports: ``node scripts/build.mjs --out dist-<name>`` with
    SANDBOX_PORT_A/B/C set (the build refuses any output outside the extension folder). The result is copied to a private temp folder and the
    in-tree build is removed at once, so nothing else working in ``extension/`` can delete or change what the browser loads."""
    ext = REPO / "extension"
    out = f"dist-{name}"
    env = clean_env({"SANDBOX_PORT_A": str(ports["a"]), "SANDBOX_PORT_B": str(ports["b"]), "SANDBOX_PORT_C": str(ports["c"])})
    env["PATH"] = os.environ.get("PATH", "")
    r = subprocess.run(["node", "scripts/build.mjs", "--out", out], cwd=str(ext), env=env, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"extension build failed for {name}: {r.stderr[-300:]}")
    dest = Path(tempfile.mkdtemp(prefix=f"study-sim-ext-{name}-")) / "ext"
    shutil.copytree(ext / out, dest)
    shutil.rmtree(ext / out, ignore_errors=True)
    return dest


def remove_extension_builds(paths: list) -> None:
    for p in paths:
        shutil.rmtree(Path(p).parent, ignore_errors=True)
    for q in (REPO / "extension").glob("dist-ssim*"):
        shutil.rmtree(q, ignore_errors=True)


def fingerprint_dir(root: Path, skip_names: tuple[str, ...] = ("SNAPSHOT.json",)) -> str:
    """Content fingerprint of a folder (relative paths and bytes, ignoring __pycache__, .pyc and the named files): the same algorithm snapshot_pipeline uses,
    so a frozen copy can be re-checked before it is reused."""
    import hashlib

    root = Path(root)
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name not in skip_names):
        h.update(str(f.relative_to(root)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]
