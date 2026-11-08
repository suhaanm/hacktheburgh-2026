"""Skills: instruction files the worker already has (Claude Code skills) or puts in `~/Knack/skills`.

INDEX (local, no network, bounded). A skill is a folder holding `SKILL.md` that starts with YAML front matter. Only the front
matter's `name` and `description` are read for the index. Sources, in this order:

* `claude`  `~/.claude/skills/*/SKILL.md`
* `plugin`  `~/.claude/plugins/**/skills/*/SKILL.md` (a depth-bounded walk that skips `node_modules`, `.git` and caches)
* `knack`   `~/Knack/skills/*/SKILL.md` (also `~/Knack/skills/*.md` with front matter)

Bounds: at most 500 skills, 64 KB read per file (a longer file is read up to 64 KB and used only if its front matter ends
inside that), symlinks that leave the folder are skipped, a time budget for the walk.

SELECTION is code: BM25 over the skill's name and description against the task words (stop words out). Nothing about a skill
is chosen by a model. For the `claude_agent` route the Claude CLI loads `~/.claude` skills itself (HOME is passed to it) and
we add the selected NAMES to the prompt as a hint. For the `answer`, `browser` and `desktop` routes the top two selected skills'
instructions are added to the planner context, size-capped, wrapped as UNTRUSTED guidance: a skill can never grant a
permission, change a gate or add a tool, because none of those is decided by prompt text.

SETTINGS (`<data dir>/task_settings.json`): `use_claude_skills` (default true), `off` (skill names switched off), and
`max_minutes` (default 30). Writing them is the worker's action.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..security.paths import data_dir

MAX_SKILLS = 500
MAX_FILE_BYTES = 64 * 1024
MAX_WALK_DEPTH = 7
WALK_BUDGET_S = 3.0
GUIDANCE_CAP_BYTES = 6000
SOURCES = ("claude", "plugin", "knack")
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".cache", "cache", ".trash", ".venv", "venv"}
_STOP = frozenset("""a an and are as at be but by can do for from has have how i if in into is it its me my of on or our please so
that the their them then there these they this to up us use want was we what when where which who will with you your
could would should about just also some any get make""".split())
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    source: str
    path: Path

    def public(self, enabled: bool) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "source": self.source, "enabled": enabled}


# ---------------------------------------------------------------------------------------------------------- settings
def settings_path() -> Path:
    return data_dir() / "task_settings.json"


_DEFAULTS: dict[str, Any] = {"use_claude_skills": True, "off": [], "max_minutes": 30}
_settings_lock = threading.Lock()


def load_settings() -> dict[str, Any]:
    out = dict(_DEFAULTS)
    try:
        d = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(d, dict):
        if isinstance(d.get("use_claude_skills"), bool):
            out["use_claude_skills"] = d["use_claude_skills"]
        if isinstance(d.get("off"), list):
            out["off"] = sorted({str(x)[:80] for x in d["off"] if isinstance(x, str)})[:MAX_SKILLS]
        mm = d.get("max_minutes")
        if isinstance(mm, int) and not isinstance(mm, bool) and 1 <= mm <= 120:
            out["max_minutes"] = mm
    return out


def save_settings(update: dict[str, Any]) -> dict[str, Any]:
    with _settings_lock:
        cur = load_settings()
        if isinstance(update.get("use_claude_skills"), bool):
            cur["use_claude_skills"] = update["use_claude_skills"]
        if isinstance(update.get("off"), list):
            cur["off"] = sorted({str(x)[:80] for x in update["off"] if isinstance(x, str)})[:MAX_SKILLS]
        mm = update.get("max_minutes")
        if isinstance(mm, int) and not isinstance(mm, bool) and 1 <= mm <= 120:
            cur["max_minutes"] = mm
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
        os.replace(tmp, p)
        return cur


# ------------------------------------------------------------------------------------------------------------ index
def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def read_front_matter(path: Path) -> tuple[dict[str, Any], int] | None:
    """(front matter mapping, byte offset where the body starts) from the first 64 KB of a file, or None."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_FILE_BYTES)
    except OSError:
        return None
    text = raw.decode("utf-8", "replace")
    if not text.startswith("---"):
        return None
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return None
    try:
        import yaml

        data = yaml.safe_load(m.group(1))
    except Exception:  # noqa: BLE001 - a broken skill file is skipped, never fatal
        return None
    if not isinstance(data, dict):
        return None
    return data, len(text[: m.end()].encode("utf-8", "replace"))


def _clean(v: Any, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _skill_from(path: Path, source: str, root: Path) -> SkillInfo | None:
    if path.is_symlink() and not _inside(path, root):
        return None
    if not path.is_file() or not _inside(path, root):
        return None
    fm = read_front_matter(path)
    if fm is None:
        return None
    data, _ = fm
    name = _clean(data.get("name") or path.parent.name, 80)
    desc = _clean(data.get("description"), 400)
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._:\-]{0,79}", name):
        return None
    return SkillInfo(name=name, description=desc, source=source, path=path)


def _walk_plugins(root: Path, found: list[SkillInfo], limit: int, deadline: float) -> None:
    if not root.is_dir():
        return
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if time.monotonic() > deadline or len(found) >= limit:
            return
        depth = len(Path(dirpath).parts) - base_depth
        dirnames[:] = [d for d in sorted(dirnames) if d not in _SKIP_DIRS and not d.startswith(".")] if depth < MAX_WALK_DEPTH else []
        if "SKILL.md" in filenames and Path(dirpath).parent.name == "skills":
            s = _skill_from(Path(dirpath) / "SKILL.md", "plugin", root)
            if s is not None:
                found.append(s)


def build_index(home: Path | None = None) -> list[SkillInfo]:
    """Every skill found on this Mac, de-duplicated by name (the first source wins), at most 500."""
    h = home or Path.home()
    found: list[SkillInfo] = []
    deadline = time.monotonic() + WALK_BUDGET_S
    for source, root in (("claude", h / ".claude" / "skills"), ("knack", h / "Knack" / "skills")):
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for e in entries:
            if len(found) >= MAX_SKILLS:
                break
            if e.is_dir() or (e.is_symlink() and e.resolve().is_dir()):
                if e.is_symlink() and not _inside(e, root):
                    continue
                s = _skill_from(e / "SKILL.md", source, root)
            elif source == "knack" and e.suffix == ".md":
                s = _skill_from(e, source, root)
            else:
                s = None
            if s is not None:
                found.append(s)
    if len(found) < MAX_SKILLS:
        _walk_plugins(h / ".claude" / "plugins", found, MAX_SKILLS, deadline)
    seen: set[str] = set()
    out: list[SkillInfo] = []
    # claude first, then knack, then plugin: the worker's own folders win a name clash
    for s in sorted(found, key=lambda s: {"claude": 0, "knack": 1, "plugin": 2}[s.source]):
        key = s.name.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out[:MAX_SKILLS]


class SkillBook:
    """The index with a short cache (a re-scan at most every 30 s, or when asked) and the worker's switches applied."""

    def __init__(self, home: Path | None = None, ttl_s: float = 30.0) -> None:
        self._home, self._ttl = home, ttl_s
        self._at = 0.0
        self._items: list[SkillInfo] = []
        self._lock = threading.Lock()

    def items(self, *, fresh: bool = False) -> list[SkillInfo]:
        with self._lock:
            if fresh or self._at == 0.0 or time.monotonic() - self._at > self._ttl:
                self._items = build_index(self._home)
                self._at = time.monotonic()
            return list(self._items)

    def enabled(self, s: SkillInfo, settings: dict[str, Any] | None = None) -> bool:
        st = settings or load_settings()
        if s.source in ("claude", "plugin") and not st["use_claude_skills"]:
            return False
        return s.name not in set(st["off"])

    def listing(self, *, fresh: bool = False) -> dict[str, Any]:
        st = load_settings()
        return {"use_claude_skills": st["use_claude_skills"], "off": st["off"],
                "skills": [s.public(self.enabled(s, st)) for s in self.items(fresh=fresh)]}

    def select(self, task_text: str, k: int = 2, settings: dict[str, Any] | None = None) -> list[SkillInfo]:
        st = settings or load_settings()
        pool = [s for s in self.items() if self.enabled(s, st)]
        return bm25_select(task_text, pool, k)


# ------------------------------------------------------------------------------------------------------ selection
def tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall((text or "").lower()):
        if len(w) > 2 and w not in _STOP:
            out.append(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def bm25_select(query: str, pool: list[SkillInfo], k: int = 2, *, k1: float = 1.4, b: float = 0.75, min_score: float = 1.0) -> list[SkillInfo]:
    """BM25 over name (counted twice) and description. Returns at most k skills whose score reaches `min_score`; none if the
    task shares no words with any skill. Deterministic: ties break by name."""
    q = sorted(set(tokens(query)))
    if not q or not pool:
        return []
    docs = [tokens(s.name.replace("-", " ").replace("_", " ")) * 2 + tokens(s.description) for s in pool]
    n = len(docs)
    avg = (sum(len(d) for d in docs) / n) or 1.0
    df = {t: sum(1 for d in docs if t in d) for t in q}
    scored: list[tuple[float, str, SkillInfo]] = []
    for s, d in zip(pool, docs):
        score = 0.0
        for t in q:
            f = d.count(t)
            if not f:
                continue
            idf = math.log(1 + n / df[t])          # stays useful for a small pool (the classic form collapses to zero at n = 1)
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * len(d) / avg))
        if score >= min_score:
            scored.append((score, s.name, s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [s for _, _, s in scored[:k]]


def read_body(skill: SkillInfo, cap: int = GUIDANCE_CAP_BYTES) -> str:
    """The instructions after the front matter, cut to `cap` bytes. Untrusted text: callers wrap it."""
    fm = read_front_matter(skill.path)
    start = fm[1] if fm else 0
    try:
        with open(skill.path, "rb") as f:
            f.seek(start)
            raw = f.read(cap)
    except OSError:
        return ""
    return raw.decode("utf-8", "replace").strip()


def guidance_block(skills: list[SkillInfo], cap: int = GUIDANCE_CAP_BYTES) -> tuple[str, int]:
    """(text for the planner context, bytes of skill text in it). The text is wrapped as untrusted guidance; the second
    value is for the privacy ledger (a count and a size, never the text)."""
    from ..security.sanitize import wrap_untrusted

    parts: list[str] = []
    total = 0
    for s in skills[:2]:
        body = read_body(s, cap)
        if not body:
            continue
        total += len(body.encode("utf-8", "replace"))
        parts.append(wrap_untrusted(f"Skill: {s.name}\n{body}", source="skill", max_chars=cap))
    return "\n\n".join(parts), total
