"""Hermetic fixtures for the local model tests: a private data dir and home, no real model, no real server.

The real model is never started here. ``stub`` installs a fake ``llama-server`` (``localmodel/stub_server.py``) behind a wrapper
script, so the real start/stop/health code paths run against a process that speaks the same protocol.
"""
from __future__ import annotations

import os
import socket
import stat
import sys
from pathlib import Path

import pytest


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith(("UNDERSTUDY_X", "UNDERSTUDY_LOCAL", "UNDERSTUDY_STUB", "UNDERSTUDY_LLAMA")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_LOCAL_MODEL", str(tmp_path / "nope" / "missing.gguf"))
    monkeypatch.setenv("UNDERSTUDY_LOCAL_MODEL_BACKOFF_S", "0")
    monkeypatch.setenv("UNDERSTUDY_LOCAL_MODEL_PORT", str(free_port()))
    from understudy_engine.localmodel import digest, server

    server._server = None
    digest.reset_stats()
    yield
    try:
        server.get_server().stop()
    finally:
        server._server = None


@pytest.fixture()
def stub(tmp_path, monkeypatch):
    """The model path enabled against the stub server: flag on, mock off, a tiny 'model' file, a wrapper binary."""
    model = tmp_path / "model" / "tiny.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not a real model, only a file that exists")
    wrapper = tmp_path / "bin" / "llama-server"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m understudy_engine.localmodel.stub_server "$@"\n')
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("UNDERSTUDY_LOCAL_MODEL", str(model))
    monkeypatch.setenv("UNDERSTUDY_LLAMA_SERVER", str(wrapper))
    monkeypatch.setenv("UNDERSTUDY_X_LOCALMODEL", "1")
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)

    class Handle:
        model_path: Path = model
        wrapper_path: Path = wrapper

        @staticmethod
        def behaviour(name: str) -> None:
            f = tmp_path / "data" / "localmodel" / "stub_behaviour"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(name)

    return Handle
