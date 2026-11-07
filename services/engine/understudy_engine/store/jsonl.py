"""Append-only JSONL event store, partitioned by origin.

Layout under the data dir::

    real/<person>/<YYYY-MM-DD>.jsonl        (live capture, one file per UTC day)
    synthetic/<group>/events.jsonl          (generators; <group> is a persona or "apprentices")
    synthetic/<person>/<YYYY-MM-DD>.jsonl   (synthetic events posted through the API)

Rules enforced here (CAP-2, CAP-3):
- every row is validated against event.schema.json and core.Event before it is written;
- a file never mixes origins (checked against the partition and against the file's first row);
- files are only ever opened for append (or replaced whole, atomically, by ``write_file``);
- duplicate event ids within a file are rejected, so re-posting a batch is harmless.
"""
from __future__ import annotations

import fcntl
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import orjson

from ..core import Event
from .paths import data_dir
from .validate import InvalidEvent, dumps_row, to_row, validate_row

PARTITIONS = ("real", "synthetic")


class StoreError(Exception):
    pass


class OriginMixError(StoreError):
    """Raised when an event would put two origins into one file or partition."""


@dataclass
class AppendResult:
    accepted: int = 0
    rejected: list[dict] = field(default_factory=list)  # {index, reason}


@dataclass
class _FileInfo:
    size: int
    origin: str | None
    ids: set[str]


_lock = threading.RLock()


def _scan_file(path: Path) -> _FileInfo:
    origin = None
    ids: set[str] = set()
    data = path.read_bytes() if path.exists() else b""
    for line in data.splitlines():
        if not line.strip():
            continue
        row = orjson.loads(line)
        origin = origin or row.get("origin")
        ids.add(row["id"])
    return _FileInfo(size=len(data), origin=origin, ids=ids)


class EventStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else data_dir()
        self._info: dict[str, _FileInfo] = {}
        self._cache: OrderedDict[tuple, list[Event]] = OrderedDict()

    # ------------------------------------------------------------------ paths
    def partition_dir(self, partition: str) -> Path:
        if partition not in PARTITIONS:
            raise StoreError(f"unknown partition {partition!r}; use real or synthetic")
        return self.root / partition

    def path_for(self, ev: Event) -> Path:
        day = ev.t.astimezone(timezone.utc).strftime("%Y-%m-%d")
        return self.partition_dir(ev.origin) / ev.person / f"{day}.jsonl"

    def files(self, partition: str, person: str | None = None) -> list[Path]:
        base = self.partition_dir(partition)
        if not base.exists():
            return []
        out = sorted(base.glob("*/*.jsonl"))
        if partition == "real" and person:
            out = [p for p in out if p.parent.name == person]
        return out

    # ----------------------------------------------------------------- append
    def _file_info(self, path: Path) -> _FileInfo:
        key = str(path)
        size = path.stat().st_size if path.exists() else 0
        info = self._info.get(key)
        if info is None or info.size != size:  # unknown, or changed behind our back
            info = _scan_file(path)
            self._info[key] = info
        return info

    def _check_partition(self, path: Path, origin: str) -> None:
        for part in PARTITIONS:
            base = self.partition_dir(part)
            try:
                path.resolve().relative_to(base.resolve())
            except ValueError:
                continue
            if part != origin:
                raise OriginMixError(f"{origin} event cannot be written under {part}/")

    def append(self, event: Event | dict, path: Path | None = None) -> Event:
        """Validate and append one event. Raises InvalidEvent, OriginMixError or StoreError."""
        ev = validate_row(event)
        self._append_validated([ev], path)
        return ev

    def append_many(self, events: Iterable[Event | dict]) -> AppendResult:
        """Append what is valid, report the rest as ``{index, reason}``. Never raises per row."""
        with _lock:                       # one writer at a time: the duplicate check and the write are one step
            return self._append_many(events)

    def _append_many(self, events: Iterable[Event | dict]) -> AppendResult:
        res = AppendResult()
        by_path: dict[Path, list[Event]] = {}
        seen: dict[Path, set[str]] = {}
        for i, raw in enumerate(events):
            try:
                ev = validate_row(raw)
                path = self.path_for(ev)
                info = self._file_info(path)
                ids = seen.setdefault(path, set())
                if ev.id in info.ids or ev.id in ids:
                    raise InvalidEvent("duplicate id")
                if info.origin and info.origin != ev.origin:
                    raise OriginMixError(f"file holds {info.origin} events; refusing {ev.origin}")
            except (InvalidEvent, OriginMixError, StoreError) as exc:
                res.rejected.append({"index": i, "reason": str(exc)})
                continue
            ids.add(ev.id)
            by_path.setdefault(path, []).append(ev)
        for path, evs in by_path.items():
            self._write_append(path, evs)
            res.accepted += len(evs)
        return res

    def _append_validated(self, evs: list[Event], path: Path | None) -> None:
        with _lock:
            self._append_validated_locked(evs, path)

    def _append_validated_locked(self, evs: list[Event], path: Path | None) -> None:
        by_path: dict[Path, list[Event]] = {}
        for ev in evs:
            p = path or self.path_for(ev)
            self._check_partition(p, ev.origin)
            by_path.setdefault(p, []).append(ev)
        for p, group in by_path.items():
            info = self._file_info(p)
            ids = set()
            for ev in group:
                if info.origin and info.origin != ev.origin:
                    raise OriginMixError(f"{p.name} holds {info.origin} events; refusing {ev.origin}")
                if len({e.origin for e in group}) > 1:
                    raise OriginMixError("one write mixes real and synthetic events")
                if ev.id in info.ids or ev.id in ids:
                    raise InvalidEvent(f"duplicate id {ev.id}")
                ids.add(ev.id)
            self._write_append(p, group)

    def _write_append(self, path: Path, evs: list[Event]) -> None:
        payload = b"".join(dumps_row(e) for e in evs)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, payload)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            info = self._info.get(str(path))
            if info is None:
                info = self._info[str(path)] = _FileInfo(0, None, set())
            info.size = path.stat().st_size
            info.origin = info.origin or evs[0].origin
            info.ids.update(e.id for e in evs)
            self._cache = OrderedDict((k, v) for k, v in self._cache.items() if k[0] != str(path))

    # ------------------------------------------------------------ whole files
    def write_file(self, path: Path | str, events: Iterable[Event | dict], *, overwrite: bool = True) -> int:
        """Validate every event, then atomically replace ``path`` with them (used by generators).

        The file must hold one origin only, and must sit in the matching partition if it is under the data dir.
        """
        path = Path(path)
        evs = [validate_row(e) for e in events]
        origins = {e.origin for e in evs}
        if len(origins) > 1:
            raise OriginMixError("refusing to write real and synthetic events into one file")
        if evs:
            self._check_partition(path, evs[0].origin)
        ids = [e.id for e in evs]
        if len(set(ids)) != len(ids):
            raise InvalidEvent("duplicate ids in batch")
        if path.exists() and not overwrite:
            raise StoreError(f"{path} exists")
        evs.sort(key=lambda e: (e.t, e.id))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        with _lock:
            tmp.write_bytes(b"".join(dumps_row(e) for e in evs))
            os.replace(tmp, path)
            self._info.pop(str(path), None)
        return len(evs)

    # ------------------------------------------------------------------- read
    def read_file(self, path: Path | str) -> list[Event]:
        """Parse one JSONL file into Events (cached per path, mtime and size)."""
        path = Path(path)
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
        with _lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        out = [
            Event.model_validate(orjson.loads(line))
            for line in path.read_bytes().splitlines()
            if line.strip()
        ]
        with _lock:
            self._cache[key] = out
            while len(self._cache) > 24:
                self._cache.popitem(last=False)
        return out

    def read(
        self,
        partition: str,
        person: str | None = None,
        since: datetime | str | None = None,
        until: datetime | str | None = None,
        task: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """Events of one partition, oldest first, optionally filtered. ``limit`` keeps the oldest rows."""
        since_dt = _as_dt(since)
        until_dt = _as_dt(until)
        out: list[Event] = []
        for path in self.files(partition, person):
            if person and person not in self._persons_of(path):
                continue
            for ev in self.read_file(path):
                if person and ev.person != person:
                    continue
                if task and ev.task_id != task:
                    continue
                if since_dt and ev.t < since_dt:
                    continue
                if until_dt and ev.t >= until_dt:
                    continue
                out.append(ev)
        out.sort(key=lambda e: (e.t, e.id))
        return out[:limit] if limit else out

    def _persons_of(self, path: Path) -> frozenset[str]:
        """Who is in a file (cached per path, mtime and size), so a person's read skips the other files."""
        st = path.stat()
        key = ("persons", str(path), st.st_mtime_ns, st.st_size)
        with _lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit  # type: ignore[return-value]
        found = frozenset(e.person for e in self.read_file(path))
        with _lock:
            self._cache[key] = found  # type: ignore[assignment]
            while len(self._cache) > 48:
                self._cache.popitem(last=False)
        return found

    def persons(self, partition: str) -> list[str]:
        seen: dict[str, None] = {}
        for path in self.files(partition):
            for ev in self.read_file(path):
                seen.setdefault(ev.person)
        return sorted(seen)

    def iter_rows(self, path: Path | str) -> Iterator[dict]:
        for line in Path(path).read_bytes().splitlines():
            if line.strip():
                yield orjson.loads(line)


def _as_dt(v: datetime | str | None) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def rows_of(events: Iterable[Event]) -> list[dict]:
    return [to_row(e) for e in events]
