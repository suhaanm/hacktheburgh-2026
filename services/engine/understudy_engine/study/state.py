"""Study mode (EVL-2): a per-skill coach switch so the live study tests the system, not a printed card.

``data/study/state.json`` holds the current setting for one person: ``{person, block, skill_on, level}``.

  block "train"      the coach acts only for ``skill_on``, at ``level``, under the normal gate rules; silent for every
                     other skill
  block "post_test"  always silent, chip gone
  block "off"        always silent, chip gone
  no file            normal behaviour

Every change is also appended to ``data/study/log.jsonl`` (who, what, when) so the export can rebuild the block windows.
The study case uses two calculators, so ``steps_off`` (default calc_c and cliff_c) tells the coach not to wait for a third.
Writes are atomic. Only the worker's own UI or the facilitator's CLI writes this file; nothing from a page or a model does.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..store.paths import data_dir

BLOCKS = ("train", "post_test", "off")
LEVELS = ("L1", "L2", "L3", "L4")
DEFAULT_STEPS_OFF = ("calc_c", "cliff_c")
# the protocol's short names and the planted deficits both point at the pack's skill ids
SKILL_ALIASES = {
    "cliff": "check-the-cliff", "skipped_check_cliff": "check-the-cliff",
    "reconcile": "reconcile-before-noting",
    "copy_error": "note-with-evidence", "note": "note-with-evidence",
}
_TOKEN = re.compile(r"^[a-z0-9_\-]{1,40}$")
_PERSON = re.compile(r"^p_[a-z0-9]{2,16}$")
_lock = threading.Lock()


class StudyError(ValueError):
    pass


@dataclass(frozen=True)
class StudyMode:
    person: str
    block: str
    skill_on: str | None
    level: str = "L1"
    steps_off: tuple[str, ...] = DEFAULT_STEPS_OFF
    t: str = ""

    @property
    def skill_id(self) -> str | None:
        return SKILL_ALIASES.get(self.skill_on or "", self.skill_on)

    @property
    def level_n(self) -> int:
        return int(self.level[1:])

    @property
    def coaching(self) -> bool:
        """The coach may act at all: a train block with a skill switched on."""
        return self.block == "train" and bool(self.skill_on)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["steps_off"] = list(self.steps_off)
        return d


def study_dir() -> Path:
    return data_dir() / "study"


def state_path() -> Path:
    return study_dir() / "state.json"


def log_path() -> Path:
    return study_dir() / "log.jsonl"


def sessions_path() -> Path:
    return study_dir() / "sessions.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def validate(person: str, block: str, skill_on: str | None, level: str, steps_off=None) -> StudyMode:
    if not _PERSON.match(person or ""):
        raise StudyError("person must look like p_ab12 (lowercase letters and digits after p_).")
    if block not in BLOCKS:
        raise StudyError(f"block must be one of {', '.join(BLOCKS)}.")
    if level not in LEVELS:
        raise StudyError(f"level must be one of {', '.join(LEVELS)}.")
    if skill_on is not None and not _TOKEN.match(skill_on):
        raise StudyError("skill_on must be a skill id such as check-the-cliff, or null.")
    if block == "train" and not skill_on:
        raise StudyError("a train block needs skill_on (the one skill the coach may act on).")
    off = tuple(steps_off) if steps_off is not None else DEFAULT_STEPS_OFF
    for s in off:
        if not _TOKEN.match(s):
            raise StudyError(f"bad step id {s!r} in steps_off.")
    return StudyMode(person, block, skill_on if block == "train" else (skill_on or None), level, off, _now())


def write_state(person: str, block: str, skill_on: str | None = None, level: str = "L1", *, steps_off=None,
                participant: str | None = None, block_no: int | None = None) -> StudyMode:
    mode = validate(person, block, skill_on, level, steps_off)
    entry = {**mode.to_dict(), "participant": participant, "block_no": block_no}
    with _lock:
        atomic_write(state_path(), json.dumps(mode.to_dict(), indent=2) + "\n")
        log_path().parent.mkdir(parents=True, exist_ok=True)
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    _cache.clear()
    return mode


def clear_state() -> bool:
    with _lock:
        try:
            state_path().unlink()
            gone = True
        except FileNotFoundError:
            gone = False
        if gone:
            with open(log_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"t": _now(), "cleared": True}) + "\n")
    _cache.clear()
    return gone


_cache: dict = {}


def read_state() -> StudyMode | None:
    """The current setting, or None when there is no file (normal behaviour). A broken file counts as no file."""
    p = state_path()
    try:
        st = p.stat()
    except FileNotFoundError:
        return None
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _cache:
        return _cache[key]
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        mode = validate(d["person"], d["block"], d.get("skill_on"), d.get("level", "L1"), d.get("steps_off"))
        mode = StudyMode(mode.person, mode.block, mode.skill_on, mode.level, mode.steps_off, d.get("t", ""))
    except (OSError, ValueError, KeyError, TypeError):
        mode = None
    _cache.clear()
    _cache[key] = mode
    return mode


def read_log() -> list[dict]:
    p = log_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
