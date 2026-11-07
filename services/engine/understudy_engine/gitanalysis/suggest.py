"""The fixed catalogue of git suggestions (GIT-1; same guard as the calendar suggestions, CAL-3).

Code selects, never a model: a catalogue entry applies when one of its habits is *flagged* by ``compare.habit_rows`` (the
difference from the reference experts is at least the habit's floor and its interval excludes zero). The sentence is a
template filled with the learner's own numbers. A model may reword it, but only through
``understudy_engine.privacy.egress.send`` with the built-in ``git.habit_wording`` purpose, and only from two bucketed ratios
and a commit count: if anything fails the templated sentence stands. Every suggestion cites its numbers and the expert
reference. Suggestions are advice: nothing here changes a repository, and a worker can dismiss any of them.

Catalogue (the five from the brief):

    GIT_SMALLER_COMMITS         big_commits
    GIT_TESTS_WITH_CHANGES      tests_with_changes
    GIT_RUN_TESTS_BEFORE_COMMIT fix_after_fix, reverts
    GIT_CLEARER_MESSAGES        vague_messages
    GIT_PROTECT_LATE_NIGHT      late_night
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Sequence

log = logging.getLogger("understudy.gitanalysis")

MAX_WORDING_CHARS = 280


@dataclass(frozen=True)
class Entry:
    id: str
    template: str          # a short template id (the calendar layer's "template" field)
    habits: tuple[str, ...]
    advice: str            # the closing sentence of the templated text


CATALOGUE: dict[str, Entry] = {e.id: e for e in (
    Entry("GIT_SMALLER_COMMITS", "smaller_commits", ("big_commits",),
          "Try committing each logical step on its own, so every change can be reviewed and undone separately."),
    Entry("GIT_TESTS_WITH_CHANGES", "tests_with_changes", ("tests_with_changes",),
          "Add or update a test in the same commit as the change it covers."),
    Entry("GIT_RUN_TESTS_BEFORE_COMMIT", "run_tests_before_commit", ("fix_after_fix", "reverts"),
          "Running the tests before you commit is the usual way to avoid this."),
    Entry("GIT_CLEARER_MESSAGES", "clearer_messages", ("vague_messages",),
          "A subject that says what changed, and a line on why when it is not obvious, helps reviewers and future you."),
    Entry("GIT_PROTECT_LATE_NIGHT", "protect_late_night", ("late_night",),
          "Consider stopping earlier, or reading late changes through again in the morning before they are merged."),
)}
HABIT_TO_ENTRY = {h: e.id for e in CATALOGUE.values() for h in e.habits}

# habit id -> the privacy track's ``git.habit`` vocabulary id (vague_messages is added to it on first use)
PRIVACY_HABIT = {"big_commits": "huge_commits", "tests_with_changes": "no_tests", "fix_after_fix": "fix_after_fix",
                 "reverts": "many_reverts", "late_night": "late_night_commits", "vague_messages": "vague_messages"}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{round(100 * x)}%"


def _of(row: dict) -> str:
    return f"{row['n_num']} of {row['n_den']}"


def _sentence(entry: Entry, rows: dict[str, dict]) -> str:
    """The templated text: the learner's numbers, the expert reference, then the advice."""
    if entry.id == "GIT_SMALLER_COMMITS":
        r = rows["big_commits"]
        head = (f"{_pct(r['learner'])} of your commits changed more than 250 lines ({_of(r)}); "
                f"the reference experts' share is {_pct(r['expert'])}.")
    elif entry.id == "GIT_TESTS_WITH_CHANGES":
        r = rows["tests_with_changes"]
        head = (f"Only {_pct(r['learner'])} of your feature and fix commits touched a test file ({_of(r)}); "
                f"the reference experts' share is {_pct(r['expert'])}.")
    elif entry.id == "GIT_RUN_TESTS_BEFORE_COMMIT":
        parts = []
        if "fix_after_fix" in rows:
            r = rows["fix_after_fix"]
            parts.append(f"{_pct(r['learner'])} of your fixes were followed by another fix within an hour ({_of(r)}; experts {_pct(r['expert'])})")
        if "reverts" in rows:
            r = rows["reverts"]
            parts.append(f"{_pct(r['learner'])} of your commits were reverts ({_of(r)}; experts {_pct(r['expert'])})")
        head = "; ".join(parts) + "."
        head = head[0].upper() + head[1:]
    elif entry.id == "GIT_CLEARER_MESSAGES":
        r = rows["vague_messages"]
        head = (f"{_pct(r['learner'])} of your commit messages were vague, such as one or two generic words ({_of(r)}); "
                f"the reference experts' share is {_pct(r['expert'])}.")
    else:
        r = rows["late_night"]
        head = (f"{_pct(r['learner'])} of your commits landed between midnight and 5am ({_of(r)}); "
                f"the reference experts' share is {_pct(r['expert'])}.")
    return f"{head} {entry.advice}"


def _strength(row: dict) -> float:
    """How far past its floor a flagged habit is (for ordering)."""
    d = row.get("delta")
    return 0.0 if d is None else abs(d) / max(row["min_delta"], 1e-9)


def select(rows: Sequence[dict], *, n_experts: int = 0, reference_origin: str = "synthetic", limit: int | None = None) -> list[dict]:
    """Choose catalogue entries from the flagged habit rows. Deterministic; strongest first. Each result:

    ``{id, template, habits, text, text_templated, wording, numbers, expert_ref, risk, can_draft}``."""
    by_habit = {r["id"]: r for r in rows if r.get("flagged")}
    out = []
    for entry in CATALOGUE.values():
        hit = {h: by_habit[h] for h in entry.habits if h in by_habit}
        if not hit:
            continue
        text = _sentence(entry, hit)
        primary = max(hit.values(), key=_strength)
        out.append({
            "id": entry.id, "template": entry.template, "habits": sorted(hit), "text": text, "text_templated": text, "wording": "template",
            "numbers": {h: {"learner": r["learner"], "expert": r["expert"], "delta": r["delta"], "ci": r["ci"], "n_num": r["n_num"], "n_den": r["n_den"]}
                        for h, r in hit.items()},
            "expert_ref": {"values": {h: r["expert"] for h, r in hit.items()}, "n_experts": n_experts, "origin": reference_origin,
                           "note": "the mean of each reference expert's own share"},
            "risk": "low", "can_draft": False, "primary_habit": primary["id"], "_strength": _strength(primary),
        })
    out.sort(key=lambda s: -s["_strength"])
    for s in out:
        del s["_strength"]
    return out[:limit] if limit else out


def attach(rows: list[dict], suggestions: Sequence[dict]) -> list[dict]:
    """Return copies of the habit rows with ``suggestion`` set (catalogue id, text) on each flagged habit's primary entry."""
    by_id = {s["id"]: s for s in suggestions}
    out = []
    for r in rows:
        r = dict(r)
        eid = HABIT_TO_ENTRY.get(r["id"])
        if r.get("flagged") and eid in by_id:
            s = by_id[eid]
            r["suggestion"] = {"id": s["id"], "text": s["text"], "wording": s["wording"]}
        out.append(r)
    return out


# --------------------------------------------------------------------------------------------- optional rewording
def _payload(row: dict) -> dict[str, Any]:
    return {"habit": PRIVACY_HABIT[row["id"]], "learner_ratio": float(row["learner"]), "expert_ratio": float(row["expert"]), "n_commits": int(row["n_den"])}


def reword(suggestions: Sequence[dict], rows: Sequence[dict], *, port: Any = None, enabled: bool | None = None) -> list[dict]:
    """Optionally reword each suggestion through the privacy spine (``git.habit_wording``). Returns new dicts.

    Off unless ``enabled`` (default: ``UNDERSTUDY_GIT_REWORD=1`` and not mock mode; a test passes ``port``). Any failure keeps
    the templated sentence. The model sees one habit id from a fixed vocabulary, two ratios in 10% steps and a commit count:
    no message, path, name or date. Its answer is one short plain sentence, shown as text and never executed."""
    if enabled is None:
        enabled = port is not None or (os.environ.get("UNDERSTUDY_GIT_REWORD", "") == "1"
                                       and os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() not in ("1", "true", "yes"))
    if not enabled:
        return [dict(s) for s in suggestions]
    try:
        from ..privacy import egress
        from ..privacy.payload import register_vocabulary

        register_vocabulary("git.habit", ["vague_messages"], extend=True)
    except Exception as exc:     # privacy spine not importable: templated sentences stand
        log.info("git rewording unavailable (%s); using templates", type(exc).__name__)
        return [dict(s) for s in suggestions]
    by_habit = {r["id"]: r for r in rows}
    out = []
    for s in suggestions:
        s = dict(s)
        primary = by_habit[s["primary_habit"]]
        try:
            res = egress.send("git.habit_wording", _payload(primary), port=port)
            text = res.output.get("text") if isinstance(res.output, dict) else None
            if isinstance(text, str) and text.strip() and "\n" not in text and len(text) <= MAX_WORDING_CHARS:
                s["text"], s["wording"], s["ledger_id"] = text.strip(), "model", res.ledger_id
        except Exception as exc:   # EgressError and anything else: fail closed to the template
            log.info("git rewording failed (%s); using the template", type(exc).__name__)
        out.append(s)
    return out


__all__ = ["CATALOGUE", "HABIT_TO_ENTRY", "attach", "reword", "select"]
