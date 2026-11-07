"""The memory file on disk: atomic writes, stale-revision rejection, worker-only writers (MEM-1, MEM-2, MEM-5).

Who may write (MEM-2, SEC-8): only the worker, acting directly (``"worker"``) or approving a proposal
(``"worker_approval"``). Every other actor, whatever it calls itself (a page, a tool result, a model, the
agent, a plugin), is refused with ``WriteRefused`` and the file is left untouched. The refusal is a hard
check in code; no text is ever interpreted as an instruction.

Concurrency: a process lock plus an ``flock`` on a lock file make "check the revision, then write" one step,
and the file is replaced with ``os.replace`` so a reader never sees half a file. A stale ``base_revision``
raises ``StaleRevision``; the worker's re-submit against the new revision wins.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import doc as D
from .paths import home_dir

#: Actors that may write. Named for what they are; nothing else is ever consulted.
WORKER_ACTORS = frozenset({"worker", "worker_approval"})


class WriteRefused(PermissionError):
    """A non-worker actor tried to write the memory file or its rule state."""

    def __init__(self, actor: str, what: str = "memory") -> None:
        super().__init__(f"{what} writes are refused for actor {actor!r}: only the worker may change memory")
        self.actor = actor
        self.what = what


class StaleRevision(RuntimeError):
    def __init__(self, base: int, current: int) -> None:
        super().__init__(f"memory is at revision {current}, your edit was based on {base}")
        self.base = base
        self.current = current


def require_worker(actor: str, what: str = "memory") -> None:
    if actor not in WORKER_ACTORS:
        raise WriteRefused(str(actor), what)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_GUARD = threading.Lock()


def _thread_lock(key: str) -> threading.RLock:
    with _THREAD_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


class MemoryStore:
    """One memory file (``memory.md``) plus a small JSON sidecar for rule state (precedents, proposals)."""

    def __init__(self, home: str | Path | None = None, *, on_refusal: Callable[[str, str], None] | None = None) -> None:
        self.home = Path(home).expanduser() if home else home_dir()
        self.path = self.home / "memory.md"
        self.state_path = self.home / "memory_state.json"
        self._lock_path = self.home / ".memory.lock"
        self._tlock = _thread_lock(str(self.path))
        self._depth = threading.local()
        self.on_refusal = on_refusal

    # ----- locking -----
    @contextmanager
    def _locked(self):
        self.home.mkdir(parents=True, exist_ok=True)
        with self._tlock:
            depth = getattr(self._depth, "n", 0)
            if depth:  # re-entered from inside a locked section of this thread
                self._depth.n = depth + 1
                try:
                    yield
                finally:
                    self._depth.n -= 1
                return
            with open(self._lock_path, "a+") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                self._depth.n = 1
                try:
                    yield
                finally:
                    self._depth.n = 0
                    fcntl.flock(lf, fcntl.LOCK_UN)

    def _refuse(self, actor: str, what: str) -> None:
        if self.on_refusal:
            try:
                self.on_refusal(str(actor), what)
            except Exception:  # an audit hook must never turn a refusal into a write
                pass
        raise WriteRefused(str(actor), what)

    def _check_actor(self, actor: str, what: str) -> None:
        if actor not in WORKER_ACTORS:
            self._refuse(actor, what)

    # ----- reads -----
    def exists(self) -> bool:
        return self.path.exists()

    def read_text(self) -> str:
        if not self.path.exists():
            return D.render(D.MemoryDoc(front={"role": "unknown", "revision": 0}))
        return self.path.read_text(encoding="utf-8")

    def read(self) -> D.MemoryDoc:
        if not self.path.exists():
            return D.parse(D.render(D.MemoryDoc(front={"role": "unknown", "revision": 0})))
        return D.parse(self.path.read_text(encoding="utf-8"))

    def revision(self) -> int:
        return self.read().revision

    def view(self) -> dict[str, Any]:
        doc = self.read()
        prof = self.load_state().get("profile") or {}
        return {
            "path": str(self.path),
            "revision": doc.revision,
            "markdown": D.render(doc),
            "sections": doc.by_section(),
            "role": doc.role,
            "person": prof.get("person"),
        }

    # ----- writes -----
    def _commit(self, actor: str, mutate: Callable[[D.MemoryDoc], Any], *, base_revision: int | None = None,
                what: str = "memory") -> tuple[D.MemoryDoc, Any]:
        self._check_actor(actor, what)
        with self._locked():
            doc = self.read()
            if base_revision is not None and base_revision != doc.revision:
                raise StaleRevision(base_revision, doc.revision)
            result = mutate(doc)
            doc.revision = doc.revision + 1
            atomic_write(self.path, D.render(doc))
            return doc, result

    def write_markdown(self, markdown: str, base_revision: int, *, actor: str) -> int:
        """Replace the whole file with the worker's edit. The worker's wording and unknown sections are kept.

        ``base_revision`` must be the revision the worker was looking at; otherwise ``StaleRevision``.
        """
        def mutate(doc: D.MemoryDoc) -> None:
            new = D.parse(markdown)
            doc.front = {**new.front, "role": new.front.get("role") or doc.front.get("role", "unknown")}
            doc.preamble = new.preamble
            doc.sections = new.sections

        doc, _ = self._commit(actor, mutate, base_revision=base_revision)
        return doc.revision

    def add_line(self, section: str, text: str, *, actor: str, note: str = "", line_id: str | None = None) -> D.Line:
        def mutate(doc: D.MemoryDoc) -> D.Line:
            sec = doc.section(section)
            assert sec is not None
            t = D.clean_text(text)
            # same text already in the section: the worker said it twice, keep one line
            for ln in sec.lines():
                if ln.text == t:
                    return ln
            return doc.add(section, text, note=note, line_id=line_id)

        _, line = self._commit(actor, mutate)
        return line

    def update_line(self, line_id: str, *, actor: str, text: str | None = None, note: str | None = None) -> D.Line:
        def mutate(doc: D.MemoryDoc) -> D.Line:
            hit = doc.find(line_id)
            if hit is None:
                raise KeyError(line_id)
            _, ln = hit
            if text is not None:
                t = D.clean_text(text)
                if not t:
                    raise ValueError("empty line")
                ln.text = t
            if note is not None:
                ln.note = D.clean_text(note, 200)
            return ln

        _, line = self._commit(actor, mutate)
        return line

    def forget(self, line_id: str, *, actor: str) -> int:
        """MEM-5: delete a line. Anything that behaves from that line stops, because behaviour reads the file."""
        def mutate(doc: D.MemoryDoc) -> D.Line:
            gone = doc.remove(line_id)
            if gone is None:
                raise KeyError(line_id)
            return gone

        doc, _ = self._commit(actor, mutate)
        return doc.revision

    def mutate(self, actor: str, fn: Callable[[D.MemoryDoc], Any]) -> tuple[D.MemoryDoc, Any]:
        """For modules inside this package that do several edits as one revision (onboarding, rules)."""
        return self._commit(actor, fn)

    def export_markdown(self) -> str:
        return self.read_text()

    # ----- sidecar state (rule bookkeeping; never read for behaviour without checking the file) -----
    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save_state(self, state: dict[str, Any], *, actor: str) -> None:
        self._check_actor(actor, "memory state")
        with self._locked():
            atomic_write(self.state_path, json.dumps(state, indent=1, sort_keys=True))

    def export_bundle(self) -> dict[str, Any]:
        """Everything the worker owns, in one JSON object (MEM-5 export). Local file contents only."""
        return {"markdown": self.export_markdown(), "state": self.load_state(), "exported_at": now_iso()}
