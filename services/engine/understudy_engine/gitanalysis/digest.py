"""Commit digests: the only thing that leaves the source adapter.

The digest comes from the local-model track: ``understudy_engine.localmodel.digest.commit_digest_ex`` (a local model when
the layer flag is on, a model is running and mock mode is off; its own deterministic rules otherwise; it never raises on
model trouble). This module adapts a commit ``RawItem`` to that interface and the result back to ``CommitRecord`` fields.
``rules_commit_digest`` below is a small built-in fallback with the same output shape, used ONLY when the local-model
package cannot be imported (or for tests that need to exercise that path).

Input handed to the local-model track (one dict per commit; raw text, because the model is local):
``{"message": subject + body, "paths": [...], "additions": N, "deletions": N, "files_changed": N}``.
Output per item (same order): ``{category, size_bucket, touches_tests, risk, message_quality}`` from the fixed vocabularies in
``vocab``. Every digest is re-checked against the vocabularies here; a malformed one is replaced by the built-in digest.

``backend``: ``auto`` (the local-model track decides: model or its rules), ``rules`` (its rules only, never the model),
``model`` (raise unless the model produced the digests), ``builtin`` (this module's fallback, no local-model import).
"""
from __future__ import annotations

import importlib
import logging
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .vocab import size_bucket, valid_digest

log = logging.getLogger("understudy.gitanalysis")

# ------------------------------------------------------------------ built-in fallback (used only without localmodel)
_TEST_PATH = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__|testing)/|(^|/)test_[^/]*\.\w+$|_test\.\w+$|\.(test|spec)\.\w+$|"
    r"(^|/)[^/]*Tests?\.(java|kt|cs|swift)$|(^|/)conftest\.py$", re.IGNORECASE)
_DOC_PATH = re.compile(r"(^|/)(docs?|documentation)/|\.(md|rst|txt|adoc)$|(^|/)(README|LICENSE|CHANGELOG|NOTICE)[^/]*$", re.IGNORECASE)
_CHORE_PATH = re.compile(
    r"(^|/)(\.github|\.circleci|\.gitlab|ci|scripts?|deploy|infra)/|(^|/)(Makefile|Dockerfile|pyproject\.toml|package(-lock)?\.json|"
    r"uv\.lock|poetry\.lock|requirements[^/]*\.txt|setup\.(py|cfg)|tox\.ini|\.gitignore|\.pre-commit-config\.yaml)$", re.IGNORECASE)
_KW = {
    "revert": re.compile(r"^\s*revert\b", re.I),
    "fix": re.compile(r"\b(fix(es|ed|ing)?|bug(fix)?|hotfix|patch(es|ed)?|oops|typo|resolve[sd]?|repair(ed|s)?|broken|regression|crash(es)?)\b", re.I),
    "refactor": re.compile(r"\b(refactor(ed|ing|s)?|clean[- ]?up|rename[sd]?|restructure[sd]?|simplif(y|ied|ies)|extract(ed|s)?|reorgani[sz]e[sd]?|tidy|dedupe?)\b", re.I),
    "test": re.compile(r"\b(tests?|testing|coverage|pytest|unittest|spec)\b", re.I),
    "docs": re.compile(r"\b(docs?|documentation|readme|changelog|comment(s|ed)?|docstrings?)\b", re.I),
    "chore": re.compile(r"\b(bump|deps?|dependenc(y|ies)|ci|lint(ing)?|format(ting)?|config(ure|uration)?|release|version|gitignore|chore|upgrade|pin)\b", re.I),
    "feature": re.compile(r"\b(add(s|ed|ing)?|implement(s|ed|ing)?|feat(ure)?|introduce[sd]?|support(s|ed|ing)?|new|create[sd]?|enable[sd]?|allow(s|ed)?|build|wire)\b", re.I),
}
_VAGUE_EXACT = frozenset({
    "update", "updates", "updated", "fix", "fixes", "fixed", "wip", "stuff", "changes", "change", "misc", "more", "more work", "asdf",
    "test", "tests", "tmp", "temp", "commit", "work", "save", "progress", "final", "done", "ok", "okay", "again", "fix stuff", "fix fix",
    "minor", "small changes", "quick fix", "cleanup", "tweaks", "stuff and things", "updated code", "it works", "oops", "some changes"})
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def is_doc_path(path: str) -> bool:
    return bool(_DOC_PATH.search(path)) and not is_test_path(path)


def message_quality(subject: str) -> str:
    s = (subject or "").strip()
    low = s.lower().rstrip(" .!?,:;")
    words = _WORD.findall(s)
    if not s or low in _VAGUE_EXACT or len(words) < 2 or (len(words) == 2 and len(s) < 12):
        return "vague"
    return "clear" if len(words) >= 5 else "ok"


def _category(subject: str, parents: int, paths: Sequence[str]) -> str:
    s = subject or ""
    if _KW["revert"].match(s):
        return "revert"
    if parents > 1:
        return "other"
    if paths:
        if all(is_test_path(p) for p in paths):
            return "test"
        if all(is_doc_path(p) for p in paths):
            return "docs"
        if all(_CHORE_PATH.search(p) or is_doc_path(p) for p in paths) and not _KW["fix"].search(s):
            return "chore"
    for cat in ("fix", "refactor", "docs", "test", "chore", "feature"):
        if _KW[cat].search(s):
            return cat
    return "other"


def _risk(category: str, bucket: str, n_files: int, lines: int, touches_tests: bool) -> str:
    if category == "revert" or bucket == "huge" or n_files >= 15:
        return "high"
    if category in ("docs", "test"):
        return "low"
    if bucket == "large" or n_files >= 8 or (category in ("feature", "fix", "refactor", "other") and not touches_tests and lines > 50):
        return "medium"
    return "low"


def rules_commit_digest(fields: dict) -> dict:
    """Built-in fallback digest of one commit from its ``commit.v1`` fields: enums and a bool only."""
    paths = list(fields.get("paths") or [])
    lines = int(fields.get("additions", 0)) + int(fields.get("deletions", 0))
    n_files = int(fields.get("n_files", len(paths)))
    touches = any(is_test_path(p) for p in paths)
    subject = (fields.get("message") or "").strip().split("\n", 1)[0]
    cat = _category(subject, 2 if fields.get("is_merge") else 1, paths)
    bucket = size_bucket(lines)
    return {"category": cat, "size_bucket": bucket, "touches_tests": touches,
            "risk": _risk(cat, bucket, n_files, lines, touches), "message_quality": message_quality(subject)}


# ------------------------------------------------------------------ dispatcher
@dataclass
class DigestInfo:
    source: str                 # "model" | "rules" | "mixed" (what the local-model track reports; "rules" for the built-in fallback)
    n: int
    fallbacks: int = 0          # digests replaced here because they failed the vocabulary check, plus the track's own fallbacks
    impl: str = "localmodel"    # "localmodel" | "builtin"
    model_share: float = 0.0    # share of digests the local model produced

    @property
    def label(self) -> str:
        """The contract's ``digest_source``: "model" when the model produced any of the digests, else "rules"."""
        return "model" if self.model_share > 0 else "rules"


def localmodel_item(fields: dict) -> dict:
    """The dict the local-model track's ``commit_digest`` takes (its own names: ``message``, ``paths``, ``additions``...)."""
    return {"message": fields.get("message", ""), "paths": list(fields.get("paths") or []),
            "additions": fields.get("additions", 0), "deletions": fields.get("deletions", 0),
            "files_changed": fields.get("n_files", len(fields.get("paths") or []))}


def _localmodel():
    try:
        return importlib.import_module("understudy_engine.localmodel.digest")
    except Exception:
        return None


def _fields(it) -> dict:
    return it.fields if hasattr(it, "fields") and hasattr(it, "kind") else it


def commit_digests(items: Iterable, backend: str = "auto") -> tuple[list[dict], DigestInfo]:
    """Digest RawItems (or bare ``fields`` dicts). Returns ``(digests, info)``: one digest per input, same order, enums only."""
    fields_list = [_fields(it) for it in items]
    builtin = [rules_commit_digest(f) for f in fields_list]
    lm = None if backend == "builtin" else _localmodel()
    if lm is None:
        if backend == "model":
            raise RuntimeError("local model digests requested but the local-model package is not importable")
        return builtin, DigestInfo("rules", len(builtin), impl="builtin")
    try:
        batch = lm.commit_digest_ex([localmodel_item(f) for f in fields_list], force_rules=(backend == "rules"))
        out, sources = list(batch.digests), list(batch.per_item_source)
        track_fallbacks = sum(batch.fallbacks.values())
    except Exception as exc:       # never log the message: it may echo input
        log.warning("local-model commit digest failed (%s); using the built-in rules", type(exc).__name__)
        return builtin, DigestInfo("rules", len(builtin), impl="builtin")
    if len(out) != len(builtin):
        log.warning("local-model commit digest returned %d digests for %d commits; using the built-in rules", len(out), len(builtin))
        return builtin, DigestInfo("rules", len(builtin), impl="builtin")
    final, bad = [], 0
    for got, fb in zip(out, builtin):
        if valid_digest(got):
            final.append({k: got[k] for k in ("category", "size_bucket", "touches_tests", "risk", "message_quality")})
        else:
            bad += 1
            final.append(fb)
    n_model = sum(1 for s in sources if s == "model")
    src = "model" if n_model == len(final) and final else ("rules" if n_model == 0 else "mixed")
    if backend == "model" and n_model == 0:
        raise RuntimeError("local model digests requested but the model produced none")
    return final, DigestInfo(src, len(final), fallbacks=bad + track_fallbacks, model_share=(n_model / len(final)) if final else 0.0)


__all__ = ["DigestInfo", "commit_digests", "is_doc_path", "is_test_path", "localmodel_item", "message_quality", "rules_commit_digest"]
