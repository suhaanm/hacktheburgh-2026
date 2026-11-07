"""The awareness store: append-only JSONL per person and origin, on this machine, validated on the way in.

    <data dir>/awareness/<real|synthetic>/<person>.jsonl     one validated event per line

What is stored is exactly what ``packages/schema/awareness.schema.json`` allows: numbers and closed enums. No coordinates, no window
titles, no text, no pixels, no hashes of pixels. ``real`` and ``synthetic`` never mix in one file (the origin is the directory). Events
with an id already seen in the last part of the file are dropped as duplicates, so the desktop's retry after a lost response is safe.

Typed views: ``Window`` (a two-second window of cursor features with the glances that fell inside it) and ``Glance``.
"""
from __future__ import annotations

import bisect
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import schema
from .paths import store_dir

ORIGINS = ("real", "synthetic")
MAX_BATCH = 500
_TAIL_BYTES = 512 * 1024
_PERSON_RE = re.compile(r"^p_[a-z0-9]{2,16}$")
_lock = threading.RLock()


@dataclass(frozen=True)
class Glance:
    t: float
    trigger: str
    app_kind: str | None
    task_phase: str | None
    blocker: str | None
    confidence: float
    box_2d: tuple[int, int, int, int] | None = None


@dataclass
class Window:
    """One two-second window of on-device features, with the glances (if any) whose time falls inside it."""

    t0: float
    window_s: float
    app_kind: str
    sys_idle_s: float | None
    cursor: dict[str, Any]
    glances: list[Glance] = field(default_factory=list)

    @property
    def t1(self) -> float:
        return self.t0 + self.window_s


@dataclass
class AppendResult:
    accepted: int = 0
    duplicates: int = 0
    rejected: list[tuple[int, str]] = field(default_factory=list)


def _glance_of(e: dict[str, Any]) -> Glance:
    g = e["glance"]
    box = g.get("box_2d")
    return Glance(t=schema.parse_time(e["t"]), trigger=e["trigger"], app_kind=g["app_kind"], task_phase=g["task_phase"], blocker=g["blocker"],
                  confidence=float(g["confidence"]), box_2d=tuple(box) if box else None)  # type: ignore[arg-type]


def merge_windows(events: Iterable[dict[str, Any]]) -> tuple[list[Window], list[Glance]]:
    """Window events become ``Window``s in time order; each glance is attached to the window that contains its time. Glances that fall
    in no window (a periodic glance while the cursor sampler was off, say) come back in the second list. Invalid events are skipped."""
    windows: list[Window] = []
    glances: list[Glance] = []
    for e in events:
        try:
            if e["type"] == "window":
                windows.append(Window(t0=schema.parse_time(e["t"]), window_s=float(e["window_s"]), app_kind=e["app_kind"],
                                      sys_idle_s=e.get("sys_idle_s"), cursor=dict(e["cursor"])))
            elif e["type"] == "glance":
                glances.append(_glance_of(e))
        except (KeyError, TypeError, ValueError):
            continue
    windows.sort(key=lambda w: w.t0)
    starts = [w.t0 for w in windows]
    loose: list[Glance] = []
    for g in sorted(glances, key=lambda g: g.t):
        i = bisect.bisect_right(starts, g.t) - 1
        if i >= 0 and g.t < windows[i].t1:
            windows[i].glances.append(g)
        else:
            loose.append(g)
    return windows, loose


class AwarenessStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else store_dir()
        self._ids: dict[Path, set[str]] = {}

    # ---- paths
    def path(self, person: str, origin: str = "real") -> Path:
        if origin not in ORIGINS:
            raise ValueError(f"origin must be one of {', '.join(ORIGINS)}")
        if not _PERSON_RE.match(person):
            raise ValueError("bad person id")
        return self.root / origin / f"{person}.jsonl"

    def people(self, origin: str = "real") -> list[str]:
        d = self.root / origin
        return sorted(p.stem for p in d.glob("p_*.jsonl")) if d.is_dir() else []

    # ---- write
    def _recent_ids(self, path: Path) -> set[str]:
        ids = self._ids.get(path)
        if ids is not None:
            return ids
        ids = set()
        if path.exists():
            with path.open("rb") as fh:
                size = fh.seek(0, os.SEEK_END)
                fh.seek(max(0, size - _TAIL_BYTES))
                lines = fh.read().splitlines()
                if size > _TAIL_BYTES:
                    lines = lines[1:]                       # the first line of a tail may be cut in half
                for raw in lines:
                    try:
                        ids.add(json.loads(raw)["id"])
                    except (ValueError, KeyError, TypeError):
                        continue
        self._ids[path] = ids
        return ids

    def append(self, events: Iterable[Any]) -> AppendResult:
        """Validate and append. Each event goes to the file of its own person and origin. Never raises for a bad event: it is reported."""
        res = AppendResult()
        by_path: dict[Path, list[str]] = {}
        with _lock:
            for i, e in enumerate(events):
                if i >= MAX_BATCH:
                    res.rejected.append((i, "batch too large"))
                    continue
                why = schema.problem(e)
                if why:
                    res.rejected.append((i, why))
                    continue
                path = self.path(e["person"], e["origin"])
                ids = self._recent_ids(path)
                if e["id"] in ids:
                    res.duplicates += 1
                    continue
                ids.add(e["id"])
                by_path.setdefault(path, []).append(json.dumps(e, ensure_ascii=True, separators=(",", ":")))
                res.accepted += 1
            for path, lines in by_path.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, ("\n".join(lines) + "\n").encode("ascii"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
        return res

    # ---- read
    def iter_events(self, person: str, origin: str = "real") -> Iterator[dict[str, Any]]:
        path = self.path(person, origin)
        if not path.exists():
            return
        with path.open("r", encoding="ascii", errors="replace") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue

    def events(self, person: str, origin: str = "real", *, since: float | None = None, until: float | None = None,
               limit: int | None = None) -> list[dict[str, Any]]:
        """Events in ``[since, until)`` (unix seconds), oldest first; ``limit`` keeps the NEWEST that many."""
        out = []
        for e in self.iter_events(person, origin):
            try:
                t = schema.parse_time(e["t"])
            except (KeyError, ValueError, TypeError):
                continue
            if (since is None or t >= since) and (until is None or t < until):
                out.append(e)
        return out[-limit:] if limit else out

    def windows(self, person: str, origin: str = "real", *, since: float | None = None, until: float | None = None) -> tuple[list[Window], list[Glance]]:
        return merge_windows(self.events(person, origin, since=since, until=until))

    def summary(self, person: str, origin: str = "real", *, since: float | None = None, until: float | None = None) -> dict[str, Any]:
        """Counts and means only, for the Privacy screen: nothing here could identify what the worker was looking at."""
        wins, loose = self.windows(person, origin, since=since, until=until)
        glances = [g for w in wins for g in w.glances] + loose
        by = lambda xs: {k: xs.count(k) for k in sorted(set(xs))}  # noqa: E731
        n = len(wins)
        mean = lambda key: round(sum(float(w.cursor[key]) for w in wins) / n, 3) if n else None  # noqa: E731
        return {
            "person": person, "origin": origin, "windows": n, "window_seconds": round(sum(w.window_s for w in wins), 1), "glances": len(glances),
            "first_t": schema.iso(wins[0].t0) if wins else None, "last_t": schema.iso(wins[-1].t0) if wins else None,
            "by_app_kind": by([w.app_kind for w in wins]),
            "glances_by_trigger": by([g.trigger for g in glances]),
            "glances_by_blocker": by([g.blocker for g in glances if g.blocker]),
            "cursor_mean": {k: mean(k) for k in ("dwell_s", "wander", "back_forth", "speed_bursts", "idle_gap_s")},
            "clicks_known": any(w.cursor.get("clicks") is not None for w in wins),
        }

    # ---- delete
    def clear(self, person: str | None = None, origin: str | None = None) -> int:
        """Delete stored awareness data (the worker's own action). Returns the number of files removed."""
        n = 0
        with _lock:
            for o in ([origin] if origin else ORIGINS):
                targets = [self.path(person, o)] if person else sorted((self.root / o).glob("p_*.jsonl")) if (self.root / o).is_dir() else []
                for p in targets:
                    if p.exists():
                        p.unlink()
                        n += 1
                    self._ids.pop(p, None)
        return n


def default_store() -> AwarenessStore:
    return AwarenessStore()
