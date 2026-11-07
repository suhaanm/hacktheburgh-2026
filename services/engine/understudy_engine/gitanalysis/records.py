"""From a repository to commit records: numbers and enums only.

``load_records`` reads the raw items (source adapter), digests them (local model or rules) and drops the raw text. What
comes back, ``CommitRecord``, has no subject, body, path or author name: it is safe to keep, aggregate and (after the
privacy track's bucketing) send. This is where PRV-4 is enforced for the git layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .digest import DigestInfo, commit_digests
from .source import GitSource, author_key


@dataclass(frozen=True, slots=True)
class CommitRecord:
    t: float                 # unix seconds (author time)
    tz_min: int              # author UTC offset, minutes
    author_key: str          # grouping key (hash), not a name
    parents: int
    n_files: int
    added: int
    deleted: int
    category: str
    size_bucket: str
    touches_tests: bool
    risk: str
    message_quality: str

    @property
    def lines(self) -> int:
        return self.added + self.deleted

    def as_dict(self) -> dict:
        return asdict(self)


def records_from_items(items, backend: str = "auto") -> tuple[list[CommitRecord], DigestInfo]:
    items = list(items)
    digests, info = commit_digests(items, backend=backend)
    out: list[CommitRecord] = []
    for it, dg in zip(items, digests):
        f = it.fields
        out.append(CommitRecord(
            t=it.t0.timestamp(), tz_min=int(f.get("tz_min", 0)), author_key=author_key(f.get("author", "")),
            parents=2 if f.get("is_merge") else 1, n_files=int(f.get("n_files", 0)), added=int(f.get("additions", 0)),
            deleted=int(f.get("deletions", 0)), category=dg["category"], size_bucket=dg["size_bucket"],
            touches_tests=bool(dg["touches_tests"]), risk=dg["risk"], message_quality=dg["message_quality"],
        ))
    out.sort(key=lambda r: (r.t, r.author_key))
    return out, info


def load_records(repo: str | Path, *, since=None, author: str | None = None, backend: str = "auto",
                 max_commits: int = 5000) -> tuple[list[CommitRecord], DigestInfo]:
    """Read ``repo`` (read-only), digest every commit and return records (oldest first) plus how they were digested."""
    src = GitSource(repo, author=author, max_commits=max_commits)
    return records_from_items(src.read(since), backend=backend)


def split_by_author(records: list[CommitRecord]) -> dict[str, list[CommitRecord]]:
    out: dict[str, list[CommitRecord]] = {}
    for r in records:
        out.setdefault(r.author_key, []).append(r)
    return out
