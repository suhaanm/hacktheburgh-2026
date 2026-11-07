"""The context manifest: metadata ABOUT an assembled prompt, never its content.

Section names, token counts, how many items were dropped, which inputs were stale or missing, a short hash of the stable
prefix. It is what the cost meter and the egress ledger record per call. There is no field that can hold prompt text, and
`assert_metadata_only` fails if anyone tries to put one in (a name that is not a short id, a value that is not a number, a bool
or a short id).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SECTION_NAME_RE = re.compile(r"^[a-z0-9_.-]{1,40}$")
KIND_RE = re.compile(r"^[a-z0-9_.-]{1,40}$")
HASH_RE = re.compile(r"^[0-9a-f]{12}$")


@dataclass(frozen=True)
class SectionStat:
    name: str
    tokens: int
    stable: bool
    trust: str                 # code | worker | untrusted
    items_kept: int
    items_dropped: int


@dataclass(frozen=True)
class Manifest:
    audience: str
    sections: tuple[SectionStat, ...]
    dropped_items: int
    dropped_sections: tuple[str, ...]
    prefix_hash: str           # 12 hex of the sha256 of the stable prefix text ("" hash of nothing when there is no stable section)
    prefix_tokens: int
    total_tokens: int
    budget_tokens: int | None
    stale: tuple[str, ...]
    missing: tuple[str, ...]
    image_frames: int
    required_over_budget: bool

    def to_meter_dict(self) -> dict[str, Any]:
        """Exactly the whitelist the models meter keeps (agreed with the MODELS track): sections [{name, tokens, stable}],
        dropped_items, prefix_hash, prefix_tokens, total_tokens; plus the two optional keys `stale` and `image_frames`."""
        return {
            "sections": [{"name": s.name, "tokens": s.tokens, "stable": s.stable} for s in self.sections],
            "dropped_items": self.dropped_items,
            "prefix_hash": self.prefix_hash,
            "prefix_tokens": self.prefix_tokens,
            "total_tokens": self.total_tokens,
            "stale": list(self.stale),
            "image_frames": self.image_frames,
        }

    def to_ledger_dict(self) -> dict[str, Any]:
        """The fuller record for the egress ledger or a run log. Still metadata only."""
        d = self.to_meter_dict()
        d.update({
            "audience": self.audience,
            "sections": [{"name": s.name, "tokens": s.tokens, "stable": s.stable, "trust": s.trust, "kept": s.items_kept,
                          "dropped": s.items_dropped} for s in self.sections],
            "dropped_sections": list(self.dropped_sections),
            "budget_tokens": self.budget_tokens,
            "missing": list(self.missing),
            "required_over_budget": self.required_over_budget,
        })
        return d

    def tokens_of(self, name: str) -> int:
        return next((s.tokens for s in self.sections if s.name == name), 0)


def assert_metadata_only(d: Any, *, path: str = "$") -> None:
    """Raise ValueError if `d` (a manifest dict) holds anything but numbers, bools, short ids and lists or dicts of those.
    A string must look like an id (lower case letters, digits, `_ . -`, at most 40 characters), a 12-hex hash, or one of the
    fixed words used by the manifest. Prompt text can never pass."""
    if isinstance(d, dict):
        for k, v in d.items():
            if not isinstance(k, str) or not KIND_RE.match(k):
                raise ValueError(f"manifest key at {path} is not a short id")
            assert_metadata_only(v, path=f"{path}.{k}")
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d):
            assert_metadata_only(v, path=f"{path}[{i}]")
    elif isinstance(d, bool) or d is None or isinstance(d, (int, float)):
        return
    elif isinstance(d, str):
        if not (KIND_RE.match(d) or HASH_RE.match(d) or d == ""):
            raise ValueError(f"manifest value at {path} is a string that is not a short id")
    else:
        raise ValueError(f"manifest value at {path} has type {type(d).__name__}")
