"""Where a connection's token lives (CONNECTIONS). Entered by the worker only; never in the repository, a log, a prompt, the dashboard or the
ledger. Two backends, no new dependency:

* ``keychain``: the macOS Keychain through the ``security`` command. The token goes in through ``security -i`` on STDIN, so it never appears
  in a process argument list. Reading uses ``find-generic-password -w`` (the token comes back on stdout only).
* ``file``: a mode-600 JSON file under ``UNDERSTUDY_HOME`` (never inside the repository), in a mode-700 folder. Used when the Keychain is not
  the backend: tests, other platforms, and mock mode.

``UNDERSTUDY_SECRET_BACKEND`` picks one (``keychain`` or ``file``). Unset: the Keychain on macOS in a real run, the file otherwise. A test
never reaches the real Keychain, because under pytest or in mock mode the default is the file.

A secret is stored under ``<connection id>.<ENV NAME>``. ``names(id)`` says which names have a value (never the value).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from .paths import secrets_path

SERVICE = "knack.connections"
#: printable ASCII without space, double quote or backslash: what the Keychain command line accepts without escaping
_TOKEN = re.compile(r"^[\x21\x23-\x5b\x5d-\x7e]{4,4096}$")
_ACCOUNT = re.compile(r"^[a-z][a-z0-9_]{1,40}\.[A-Z][A-Z0-9_]{2,60}$")


class SecretError(Exception):
    """A secret could not be stored or read. The message never contains the secret."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def check_token(value: str) -> str:
    if not isinstance(value, str) or not _TOKEN.match(value):
        raise SecretError("token_characters")        # spaces, quotes, backslashes, control characters, or too short or long
    return value


def _account(conn_id: str, env: str) -> str:
    acct = f"{conn_id}.{env}"
    if not _ACCOUNT.match(acct):
        raise SecretError("bad_name")
    return acct


class SecretStore(Protocol):
    name: str

    def get(self, conn_id: str, env: str) -> str | None: ...
    def set(self, conn_id: str, env: str, value: str) -> None: ...
    def delete(self, conn_id: str, env: str) -> bool: ...


class FileStore:
    """A mode-600 JSON file in a mode-700 folder, written atomically."""

    name = "file"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or secrets_path()

    def _read(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(raw, dict) else {}

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".sec-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                os.fchmod(fh.fileno(), 0o600)
                json.dump(data, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise SecretError("write_failed") from None

    def get(self, conn_id: str, env: str) -> str | None:
        return self._read().get(_account(conn_id, env))

    def set(self, conn_id: str, env: str, value: str) -> None:
        data = self._read()
        data[_account(conn_id, env)] = check_token(value)
        self._write(data)

    def delete(self, conn_id: str, env: str) -> bool:
        data = self._read()
        had = data.pop(_account(conn_id, env), None) is not None
        if had:
            self._write(data)
        return had


class KeychainStore:
    """The macOS Keychain through ``security``. The token is written through ``security -i`` (stdin), never as an argument."""

    name = "keychain"

    def _run(self, argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(["/usr/bin/security", *argv], input=stdin, capture_output=True, text=True, timeout=15, check=False)  # noqa: S603
        except (OSError, subprocess.SubprocessError):
            raise SecretError("keychain_unavailable") from None

    def get(self, conn_id: str, env: str) -> str | None:
        r = self._run(["find-generic-password", "-a", _account(conn_id, env), "-s", SERVICE, "-w"])
        return r.stdout.rstrip("\n") if r.returncode == 0 and r.stdout else None

    def set(self, conn_id: str, env: str, value: str) -> None:
        line = f'add-generic-password -a "{_account(conn_id, env)}" -s "{SERVICE}" -w "{check_token(value)}" -U\n'
        r = self._run(["-i"], stdin=line)
        if r.returncode != 0:
            raise SecretError("keychain_write_failed")

    def delete(self, conn_id: str, env: str) -> bool:
        r = self._run(["delete-generic-password", "-a", _account(conn_id, env), "-s", SERVICE])
        return r.returncode == 0


def backend_name() -> str:
    env = os.environ.get("UNDERSTUDY_SECRET_BACKEND", "").strip().lower()
    if env in ("keychain", "file"):
        return env
    mock = os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes")
    if sys.platform == "darwin" and not mock and "PYTEST_CURRENT_TEST" not in os.environ:
        return "keychain"
    return "file"


def backend() -> SecretStore:
    return KeychainStore() if backend_name() == "keychain" else FileStore()


def store_all(conn_id: str, values: dict[str, str], store: SecretStore | None = None) -> list[str]:
    """Store every value (all or none: a failure removes what this call wrote). Returns the variable names stored."""
    st = store or backend()
    for v in values.values():
        check_token(v)
    done: list[str] = []
    try:
        for env, value in values.items():
            st.set(conn_id, env, value)
            done.append(env)
    except SecretError:
        for env in done:
            st.delete(conn_id, env)
        raise
    return done


def forget(conn_id: str, envs: list[str], store: SecretStore | None = None) -> int:
    """Delete every named secret of a connection. Returns how many existed."""
    st = store or backend()
    n = 0
    for env in envs:
        try:
            n += 1 if st.delete(conn_id, env) else 0
        except SecretError:
            pass
    return n


def load_env(conn_id: str, envs: list[str], store: SecretStore | None = None) -> dict[str, str]:
    """The stored values for the named variables (for the agent's runner, which puts them in ONE child's environment). A missing one is
    simply absent from the result."""
    st = store or backend()
    out: dict[str, str] = {}
    for env in envs:
        v = st.get(conn_id, env)
        if v:
            out[env] = v
    return out
