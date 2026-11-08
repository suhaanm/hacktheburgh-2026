"""Deeper onboarding (RD, 7 Nov 2026): what the answers to a pack's follow-up questions set, add and suggest.

A pack's ``pack.yaml`` may carry ``onboarding.followups`` (questions asked after the five fixed ones), each option with ``sets`` (named
parameters), optionally ``risk_class`` and ``patterns`` (risk patterns the answer adds), and a pack-level ``suggest_connections`` mapping
from an answer (``question:value``) to connection preset ids. This module turns a set of answers into one plain result. It is pure: it reads
pack data it is given, asks nobody anything, stores nothing, connects to nothing and never calls a model. Wiring the result into the memory
file or the onboarding screen is the caller's decision (``memory.onboarding`` does not call it today, and the dashboard does not render the
follow-ups yet).

How answers combine, fixed here so a screen and a test agree:

* A question the person did not answer takes its default option(s) for ``sets`` and risk patterns (the same rule the fixed questions use).
  Suggestions come only from answers the person actually gave: a default is not a request.
* ``pace`` and ``tone``: the later question in pack order wins. ``cue_daily_budget``: the smallest value wins (the quietest answer).
  ``cue_quiet_required_s``: the largest value wins (the longest wait). ``traits``: merged, the later question wins a clash.
* An unknown question or option is never an error here: it is listed in ``unknown`` and ignored, so a stale client cannot break onboarding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .loader import Pack, load_pack

FIXED_IDS = ("tools", "risky", "tone", "pace", "hours")
BUDGET_BOUNDS = (1, 30)
QUIET_BOUNDS = (0.5, 10.0)


@dataclass(frozen=True)
class Resolved:
    sets: dict[str, Any] = field(default_factory=dict)          # pace, tone, cue_daily_budget, cue_quiet_required_s, traits
    risk: dict[str, list[str]] = field(default_factory=lambda: {"irreversible": [], "outward": []})
    suggestions: list[str] = field(default_factory=list)        # connection preset ids, first seen first, no repeats
    unknown: list[str] = field(default_factory=list)            # answers that named no known question or option

    def to_dict(self) -> dict[str, Any]:
        return {"sets": self.sets, "risk": self.risk, "suggestions": self.suggestions, "unknown": self.unknown}


def followups_of(pack: Pack) -> list[dict]:
    """The pack's follow-up questions in order (empty for a pack that has none)."""
    return [q for q in ((pack.data.get("onboarding") or {}).get("followups") or []) if isinstance(q, dict)]


def followup_questions(role_or_pack: str | Pack) -> list[dict]:
    """The follow-ups shaped like ``memory.onboarding.questions_payload`` entries (id, prompt, why, kind, options with value, label, default)."""
    pack = load_pack(role_or_pack) if isinstance(role_or_pack, str) else role_or_pack
    out = []
    for q in followups_of(pack):
        item: dict[str, Any] = {"id": q["id"], "prompt": q.get("prompt", ""), "kind": q.get("kind", "single")}
        if q.get("why"):
            item["why"] = q["why"]
        item["options"] = [{k: o[k] for k in ("value", "label", "default") if k in o} for o in q.get("options", [])]
        out.append(item)
    return out


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _merge(sets: dict[str, Any], new: dict[str, Any]) -> None:
    for key, val in new.items():
        if key == "traits":
            sets.setdefault("traits", {}).update(val)
        elif key == "cue_daily_budget":
            lo, hi = BUDGET_BOUNDS
            v = max(lo, min(hi, int(val)))
            sets[key] = min(sets[key], v) if key in sets else v
        elif key == "cue_quiet_required_s":
            lo, hi = QUIET_BOUNDS
            v = max(lo, min(hi, float(val)))
            sets[key] = max(sets[key], v) if key in sets else v
        else:
            sets[key] = val


def resolve(role_or_pack: str | Pack, answers: dict[str, Any] | None = None) -> Resolved:
    """What the answers set, add and suggest. ``answers`` maps a question id to a value (single) or a list of values (multi), for the
    follow-ups and, optionally, the fixed questions (only so that ``suggest_connections`` can read ``tools:git_host``)."""
    pack = load_pack(role_or_pack) if isinstance(role_or_pack, str) else role_or_pack
    answers = dict(answers or {})
    fus = followups_of(pack)
    fixed = {q["id"]: q for q in (pack.data.get("onboarding") or {}).get("questions", [])}
    known = {q["id"]: {o["value"] for o in q.get("options", [])} for q in [*fixed.values(), *fus]}
    unknown: list[str] = []
    for qid, given in answers.items():
        if qid not in known:
            unknown.append(qid)
            continue
        unknown += [f"{qid}:{v}" for v in _as_list(given) if v not in known[qid]]

    sets: dict[str, Any] = {}
    risk: dict[str, list[str]] = {"irreversible": [], "outward": []}
    for q in fus:
        chosen = [v for v in _as_list(answers.get(q["id"])) if v in known[q["id"]]]
        if not chosen:
            chosen = [o["value"] for o in q["options"] if o.get("default")]
        by_value = {o["value"]: o for o in q["options"]}
        for v in chosen:
            o = by_value[v]
            _merge(sets, o.get("sets") or {})
            if o.get("risk_class") in risk:
                for p in o.get("patterns", []):
                    if p not in risk[o["risk_class"]]:
                        risk[o["risk_class"]].append(p)

    suggestions: list[str] = []
    table = pack.data.get("suggest_connections") or {}
    for qid, given in answers.items():
        if qid not in known:
            continue
        for v in _as_list(given):
            if v in known[qid]:
                for preset in table.get(f"{qid}:{v}", []):
                    if preset not in suggestions:
                        suggestions.append(preset)
    return Resolved(sets=sets, risk=risk, suggestions=suggestions, unknown=unknown)
