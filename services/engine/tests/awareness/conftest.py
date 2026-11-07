from __future__ import annotations

import json
import socket
import struct
import zlib
from pathlib import Path

import pytest

FLAGS = ("UNDERSTUDY_X", "UNDERSTUDY_X_AWARENESS", "UNDERSTUDY_X_PRIVACY")


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path, monkeypatch):
    """No test here may touch the shared data/ directory or the real ~/.understudy, and none may reach the network."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("UNDERSTUDY_REPO_ROOT", raising=False)
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    for flag in FLAGS:
        monkeypatch.delenv(flag, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real_connect, real_create = socket.socket.connect, socket.create_connection

    def ok(addr) -> bool:
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        return host in ("127.0.0.1", "::1", "localhost") or str(host).startswith("/")

    def connect(self, addr, *a, **k):
        if not ok(addr):
            raise AssertionError(f"a test tried to open a network connection to {addr!r}")
        return real_connect(self, addr, *a, **k)

    def create(addr, *a, **k):
        if not ok(addr):
            raise AssertionError(f"a test tried to open a network connection to {addr!r}")
        return real_create(addr, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create)


@pytest.fixture()
def data_dir(tmp_path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def flag_on(monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_X_AWARENESS", "1")


# ------------------------------------------------------------------------------------------------ helpers shared by the tests
def window_event(i: int = 1, *, person: str = "p_demo01", origin: str = "real", t: str = "2026-11-07T10:00:00.000Z", **over):
    e = {
        "schema": 1, "id": f"evt-win-{i:05d}", "t": t, "origin": origin, "person": person, "role": "benefits-processor", "type": "window",
        "window_s": 2.0, "app_kind": "browser", "sys_idle_s": 0.4,
        "cursor": {"dwell_s": 1.9, "dwell_zone": "cliff_button", "wander": 1.0, "back_forth": 0, "zone_a": None, "zone_b": None,
                   "speed_bursts": 0, "idle_gap_s": 1.9, "clicks": None},
    }
    e.update(over)
    return e


def glance_event(i: int = 1, *, person: str = "p_demo01", origin: str = "real", t: str = "2026-11-07T10:00:01.000Z", **over):
    e = {
        "schema": 1, "id": f"evt-gl-{i:05d}", "t": t, "origin": origin, "person": person, "role": "benefits-processor", "type": "glance",
        "trigger": "stuck", "glance": {"app_kind": "spreadsheet", "task_phase": "entering", "blocker": "cannot_find_control", "confidence": 0.8},
    }
    e.update(over)
    return e


def _chunk(tag: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)


def png(w: int = 64, h: int = 48) -> bytes:
    raw = b"".join(b"\x00" + bytes((x * 7 + y * 13) % 256 for x in range(w * 3)) for y in range(h))
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def jpeg(w: int, h: int, pad: int = 200) -> bytes:
    """A JPEG header with the real size, as the desktop's JPEG carries (a baseline SOF0), plus some bytes."""
    return (b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xc0"
            + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01" + bytes(range(256))[:pad] + b"\xff\xd9")


def tiny_persona(root: Path, slug: str = "nine-to-five", *, n_tasks: int = 12, spells=((60.0, 110.0), (260.0, 300.0), (500.0, 560.0))) -> Path:
    """A hand-made persona directory (events.jsonl + truth.json) so the synth tests do not depend on the repo's generated data."""
    from datetime import datetime, timedelta, timezone

    base = root / "synthetic" / slug
    base.mkdir(parents=True)
    t0 = datetime(2026, 10, 12, 9, 0, 0, tzinfo=timezone.utc)

    def iso(sec: float) -> str:
        return (t0 + timedelta(seconds=sec)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    ev = []
    for k in range(n_tasks):
        a, b = k * 120.0, k * 120.0 + 100.0
        ev.append({"schema": 1, "id": f"x-{k}a", "t": iso(a), "origin": "synthetic", "actor": "human", "person": "p_ninetofive", "role": "benefits-processor",
                   "source": "browser", "type": "task_start", "task_id": f"t_{k:03d}"})
        ev.append({"schema": 1, "id": f"x-{k}b", "t": iso(b), "origin": "synthetic", "actor": "human", "person": "p_ninetofive", "role": "benefits-processor",
                   "source": "browser", "type": "task_end", "task_id": f"t_{k:03d}"})
    (base / "events.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    truth = {"person": "p_ninetofive", "role": "benefits-processor", "seed": 1101, "persona": slug,
             "stuck_episodes": [{"t0": iso(a), "t1": iso(b), "duration_s": b - a, "task_id": "t_x", "person": "p_ninetofive"} for a, b in spells]}
    (base / "truth.json").write_text(json.dumps(truth))
    return root
