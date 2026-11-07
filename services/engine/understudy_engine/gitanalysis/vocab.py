"""Fixed vocabularies for commit digests. They are the local-model track's (understudy_engine.localmodel.schemas); this copy
exists so the features and the built-in fallback do not depend on that package being importable.

Everything that leaves the source adapter is one of these enums or a number (PRV-4). Free text (subjects, bodies,
paths, author names) exists only inside ``RawItem.fields`` for as long as one digest call takes.
"""
from __future__ import annotations

CATEGORIES = ("feature", "fix", "refactor", "test", "docs", "chore", "revert", "other")      # as the local-model track: no "merge" (parents tell us)
SIZE_BUCKETS = ("tiny", "small", "medium", "large", "huge")
RISKS = ("low", "medium", "high")
MESSAGE_QUALITY = ("vague", "ok", "clear")

# Lines changed (added plus deleted, binary files excluded) at or below each edge fall into the bucket.
SIZE_EDGES = (10, 50, 250, 1000)
GIANT_BUCKETS = frozenset({"large", "huge"})      # over 250 lines changed: the big-commit habit

DIGEST_FIELDS = ("category", "size_bucket", "touches_tests", "risk", "message_quality")

# Cogs of the programmer pack that commit digests map to (packages/packs/programmer/git_mapping.yaml).
GIT_COGS = ("CODE", "TEST", "REFACTOR", "COMMIT", "REVERT")


def size_bucket(lines: int) -> str:
    for edge, name in zip(SIZE_EDGES, SIZE_BUCKETS):
        if lines <= edge:
            return name
    return SIZE_BUCKETS[-1]


def valid_digest(d: object) -> bool:
    """True when ``d`` has every digest field with a value from the fixed vocabularies and nothing else."""
    if not isinstance(d, dict):
        return False
    return (
        d.get("category") in CATEGORIES
        and d.get("size_bucket") in SIZE_BUCKETS
        and isinstance(d.get("touches_tests"), bool)
        and d.get("risk") in RISKS
        and d.get("message_quality") in MESSAGE_QUALITY
    )
