"""Where the routes and the evaluation get a person's commit habits: repository registry, digest cache, analysis.

Repositories that can be analysed (a request names one by id; it can never name a path):

* the synthetic cohort, materialised once under ``<data>/synthetic/git/`` (4 learners ``p_git_learner_N`` with repos
  ``r_git_learner_N``, 8 experts ``p_git_expert_N``). These are the reference experts for every comparison;
* repositories the worker registers with ``UNDERSTUDY_GIT_REPOS="name=/abs/path,name2=/abs/path2"`` (their own, local,
  read-only). A registered repo is compared with the SYNTHETIC experts, so its origin is reported as ``mixed``.

Digests: ``rules`` (the local-model track's deterministic rules) unless the local model is available. Model digests are slow
(about a second a commit), so they are kept in a local cache keyed by commit id (``<data>/git/digest_cache.json``: enums
only). A comparison uses model digests only when EVERY commit it needs (the learner's and all experts') is cached, so the two
sides are always digested the same way; until then it answers with the rules and warms the cache in the background.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from ..store.paths import data_dir
from . import digest as dg
from . import suggest, synth
from .compare import habit_rows, placebo
from .features import HABITS, CommitTable, build_table, compute_features
from .records import CommitRecord, records_from_items
from .source import GitSource

log = logging.getLogger("understudy.gitanalysis")

DEFAULT_PERSON = "p_git_learner_1"
B_REQUEST = 500
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class GitServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class Target:
    person: str
    repo_id: str
    path: Path
    kind: str          # "synthetic" | "registered"


def flag_on() -> bool:
    return any(os.environ.get(k, "").strip().lower() in ("1", "true", "yes", "on") for k in ("UNDERSTUDY_X", "UNDERSTUDY_X_GIT"))


def cohort_dir() -> Path:
    return data_dir() / "synthetic" / "git"


def registered_repos() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for part in os.environ.get("UNDERSTUDY_GIT_REPOS", "").split(","):
        name, _, path = part.strip().partition("=")
        if SLUG.match(name) and path and (Path(path).expanduser() / ".git").exists():
            out[name] = Path(path).expanduser()
    return out


# ------------------------------------------------------------------------------------------------ digest cache
class DigestCache:
    """Model digests by commit id (enums only), persisted atomically. Rules digests are cheap and never cached."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._data: dict[str, dict] = {}

    def _load(self) -> None:
        p = data_dir() / "git" / "digest_cache.json"
        if p != self._path:
            self._path = p
            try:
                self._data = json.loads(p.read_text(encoding="utf-8")).get("digests", {})
            except (OSError, ValueError):
                self._data = {}

    def get(self, sha: str) -> dict | None:
        with self._lock:
            self._load()
            return self._data.get(sha)

    def put_many(self, pairs: dict[str, dict]) -> None:
        with self._lock:
            self._load()
            self._data.update(pairs)
            assert self._path is not None
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"v": 1, "digests": self._data}), encoding="utf-8")
            os.replace(tmp, self._path)


CACHE = DigestCache()
_warm_lock = threading.Lock()
_warming: set[str] = set()


def model_available() -> bool:
    lm = dg._localmodel()
    if lm is None:
        return False
    try:
        from ..localmodel import mode
        return str(mode()) == "model"
    except Exception:
        return False


def _warm(paths: list[Path], key: str) -> None:
    try:
        for path in paths:
            items = [it for it in GitSource(path).read() if CACHE.get(it.fields["sha"]) is None]
            for i in range(0, len(items), 16):
                chunk = items[i:i + 16]
                digs, info = dg.commit_digests(chunk, backend="model")
                CACHE.put_many({it.fields["sha"]: d for it, d in zip(chunk, digs)})
    except Exception as exc:     # a model that falls over simply leaves the cache cold
        log.warning("git digest warm-up stopped (%s)", type(exc).__name__)
    finally:
        with _warm_lock:
            _warming.discard(key)


def start_warm(paths: list[Path]) -> bool:
    key = "|".join(sorted(str(p) for p in paths))
    with _warm_lock:
        if key in _warming:
            return False
        _warming.add(key)
    threading.Thread(target=_warm, args=(paths, key), name="git-digest-warm", daemon=True).start()
    return True


def records_for(paths: list[Path], backend: str = "auto", author: str | None = None,
                author_path: Path | None = None) -> tuple[dict[Path, list[CommitRecord]], dict]:
    """Records for several repos, all digested the same way (``author`` filters only ``author_path``). ``info``:
    ``{source, model_share, warming, impl}``."""
    items = {p: list(GitSource(p, author=author if p == author_path else None).read()) for p in paths}
    use_model = backend in ("auto", "model") and model_available()
    warming = False
    if use_model:
        covered = all(CACHE.get(it.fields["sha"]) is not None for its in items.values() for it in its)
        if not covered and backend == "model":
            for its in items.values():
                miss = [it for it in its if CACHE.get(it.fields["sha"]) is None]
                for i in range(0, len(miss), 16):
                    chunk = miss[i:i + 16]
                    digs, _ = dg.commit_digests(chunk, backend="model")
                    CACHE.put_many({it.fields["sha"]: d for it, d in zip(chunk, digs)})
            covered = True
        if not covered:
            warming = start_warm(paths) or True
            use_model = False
    out: dict[Path, list[CommitRecord]] = {}
    impl = "localmodel"
    for p, its in items.items():
        if use_model:
            digs = [CACHE.get(it.fields["sha"]) for it in its]
            recs = _records_with(its, digs)
        else:
            recs, info = records_from_items(its, backend="rules" if backend != "builtin" else "builtin")
            impl = info.impl
        out[p] = recs
    return out, {"source": "model" if use_model else "rules", "model_share": 1.0 if use_model else 0.0, "warming": warming, "impl": impl}


def _records_with(items, digests) -> list[CommitRecord]:
    from .source import author_key

    out = []
    for it, d in zip(items, digests):
        f = it.fields
        out.append(CommitRecord(t=it.t0.timestamp(), tz_min=int(f.get("tz_min", 0)), author_key=author_key(f.get("author", "")),
                                parents=2 if f.get("is_merge") else 1, n_files=int(f.get("n_files", 0)), added=int(f.get("additions", 0)),
                                deleted=int(f.get("deletions", 0)), category=d["category"], size_bucket=d["size_bucket"],
                                touches_tests=bool(d["touches_tests"]), risk=d["risk"], message_quality=d["message_quality"]))
    out.sort(key=lambda r: (r.t, r.author_key))
    return out


# ------------------------------------------------------------------------------------------------ registry
def cohort() -> dict:
    """The synthetic cohort index (materialised on first use). Maps ids to repo paths."""
    d = cohort_dir()
    idx = synth.ensure_cohort(d)
    return {"dir": d, "learners": {k: d / v for k, v in idx["learners"].items()}, "experts": {k: d / v for k, v in idx["experts"].items()}}


def repo_id_for(person: str) -> str:
    return "r_" + person[2:] if person.startswith("p_") else "r_" + person


def resolve(person: str | None, repo: str | None) -> Target:
    reg = registered_repos()
    if repo and repo in reg:
        return Target(person or "p_self", repo, reg[repo], "registered")
    c = cohort()
    person = person or DEFAULT_PERSON
    if person not in c["learners"]:
        raise GitServiceError("unknown_person", f"No learner repository for {person!r}. Known people: {', '.join(sorted(c['learners']))}.", 404)
    rid = repo_id_for(person)
    if repo and repo != rid:
        raise GitServiceError("unknown_repo", f"No repository {repo!r} for {person!r}. Known repositories: {rid}"
                              + (f", {', '.join(sorted(reg))}" if reg else "") + ".", 404)
    return Target(person, rid, c["learners"][person], "synthetic")


def people() -> dict:
    c = cohort()
    return {"learners": [{"person": p, "repo": repo_id_for(p)} for p in sorted(c["learners"])], "experts": sorted(c["experts"]),
            "registered": sorted(registered_repos()), "default_person": DEFAULT_PERSON}


# ------------------------------------------------------------------------------------------------ analysis
def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


_result_cache: dict[tuple, tuple[float, dict]] = {}
_result_lock = threading.Lock()


def habits_for_repo(path: str | os.PathLike, label: str = "p_self", repo_id: str = "r_local", **kw: Any) -> dict:
    """Analyse one local repository by path (library use: tests, canary flows). Treated as a registered repo (mixed origin).
    The HTTP route never calls this: a request cannot name a path."""
    return habits(target=Target(label, repo_id, Path(path), "registered"), **kw)


def habits(person: str | None = None, repo: str | None = None, *, author: str | None = None, backend: str = "auto",
           reword: bool | None = None, port: Any = None, with_placebo: bool = False, target: Target | None = None) -> dict:
    """The ``GET /git/habits`` payload: ``{meta, data}``. Raises ``GitServiceError`` for an unknown person or repo."""
    t = target or resolve(person, repo)
    c = cohort()
    key = (t.person, t.repo_id, author, backend, bool(reword), with_placebo, str(cohort_dir()))
    ttl = 3600.0 if t.kind == "synthetic" else 20.0
    if port is None:
        with _result_lock:
            hit = _result_cache.get(key)
        if hit and time.time() - hit[0] < ttl and not model_available():
            return hit[1]
    paths = [t.path, *c["experts"].values()]
    recs, info = records_for(paths, backend=backend, author=author, author_path=t.path)
    learner_recs = recs[t.path]
    experts: dict[str, CommitTable] = {}
    for name, p in c["experts"].items():
        experts[name] = build_table(recs[p])
    ltable = build_table(learner_recs)
    rows = habit_rows(ltable, experts, B=B_REQUEST, seed=_seed(t.person, t.repo_id))
    origin = "synthetic" if t.kind == "synthetic" else "mixed"
    sugg = suggest.select(rows, n_experts=len(experts), reference_origin="synthetic")
    sugg = suggest.reword(sugg, rows, port=port, enabled=reword) if (reword or port is not None) else sugg
    habits_out = suggest.attach(rows, sugg)
    feats = compute_features(learner_recs, table=ltable)
    data: dict[str, Any] = {
        "person": t.person, "repo": t.repo_id, "habits": habits_out, "suggestions": sugg,
        "digest_source": info["source"], "digest_model_share": info["model_share"], "digest_warming": info["warming"],
        "n_commits": ltable.n, "features": feats,
        "reference": {"n_experts": len(experts), "origin": "synthetic", "note": "scripted developers with baseline habits; nobody is real"},
    }
    if with_placebo:
        data["placebo"] = placebo(experts)
    split = ("learner days resampled with replacement; reference experts resampled by person and by day; "
             f"{B_REQUEST} draws, 95% percentile intervals")
    note = ("Planted-habit data: every learner here is scripted. " if t.kind == "synthetic" else
            "This repository is real and local (read-only, aggregates only); the reference experts are generated, so the comparison "
            "shows how far the history is from a scripted baseline, not from real experts. ")
    meta = {"origin": origin, "n": ltable.n, "n_unit": "commits", "split": split, "interval_level": 0.95,
            "note": note + "Habits are commit-level shares; a flagged habit differs from the reference by at least its floor with an interval that excludes zero.",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    out = {"meta": meta, "data": data}
    if port is None:
        with _result_lock:
            _result_cache[key] = (time.time(), out)
    return out


def clear_caches() -> None:
    with _result_lock:
        _result_cache.clear()


__all__ = ["GitServiceError", "habits", "habits_for_repo", "people", "resolve", "records_for", "flag_on", "HABITS"]
