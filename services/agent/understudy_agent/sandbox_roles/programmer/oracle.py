"""The programmer oracle: scores one finished case from the state the page reported (``GET /__state``), no model, no network.

Input: ``state`` = {"events": [...], "final": {...}} where ``final`` is what ``window.__grade(hidden)`` posted after the case (the harness
calls it; the participant cannot). Output: a Verdict dict as in ``sandbox_roles.base``:

    outcome  correct            2   visible and hidden tests pass, the fix is committed, and the task's discipline conditions hold
             partial            1   the reported bug is fixed (visible and core tests pass) but a hidden EDGE test fails (``edge_cases_missed``),
                                    or everything passes but the fix is not committed / a discipline condition is missing
             wrong              0   the reported bug is not fixed (a visible or core hidden test fails) and the participant did not press Mark done
             claimed_done_wrong 0   the same, after pressing Mark done (the false claim)
    claimed_done: Mark done was pressed;  skill_check_done: the process indicator of the task's skill (see ``skill_check``).

Discipline conditions: test_first (p-discipline-1): the participant's new test fails on the ORIGINAL code and passes on the fix, the first edit of the
test file came before the first edit of a source file, and source and test are in a commit. commit_hygiene (p-discipline-2): the commits hold only
the fix file(s), a message of at least three words that is not generic and names the change, and the diff was opened before the first commit.
"""
from __future__ import annotations

import re

from .tasks import GENERIC_MESSAGES, TASKS, src_paths, test_path


def _events(state: dict, kind: str) -> list[dict]:
    return [e for e in state.get("events", []) if e.get("kind") == kind]


def _first_seq(events: list[dict]) -> int | None:
    return min((e["seq"] for e in events), default=None)


def first_source_edit_seq(state: dict) -> int | None:
    return _first_seq([e for e in _events(state, "edit") if not e.get("is_test") and str(e.get("file", "")).startswith("src/")])


def first_test_edit_seq(state: dict) -> int | None:
    return _first_seq([e for e in _events(state, "edit") if e.get("is_test")])


def good_message(message: str, keywords: tuple[str, ...]) -> bool:
    words = re.findall(r"[A-Za-z0-9']+", message or "")
    if len(words) < 3:
        return False
    if all(w.lower() in GENERIC_MESSAGES for w in words):
        return False
    low = (message or "").lower()
    return any(k.lower() in low for k in keywords) if keywords else True


def skill_check(task_kind: str, state: dict) -> bool:
    """The process indicator for the task's skill."""
    src_edit = first_source_edit_seq(state)
    if task_kind == "boundary":
        probes = _events(state, "probe")
        return any(src_edit is None or p["seq"] > src_edit for p in probes)
    if task_kind == "missing":
        opened = _first_seq(_events(state, "inputs_open"))
        return opened is not None and (src_edit is None or opened < src_edit)
    if task_kind == "test_first":
        t = first_test_edit_seq(state)
        return t is not None and (src_edit is None or t < src_edit)
    if task_kind == "commit_hygiene":
        d = _first_seq(_events(state, "diff_open"))
        c = _first_seq(_events(state, "commit"))
        return d is not None and (c is None or d < c)
    raise ValueError(task_kind)


def score(task_id: str, variant: int, state: dict) -> dict:
    task = TASKS[task_id]
    final = state.get("final")
    if not final:
        raise ValueError("not graded: state['final'] is missing (call window.__grade(hidden_payload) after the case)")
    v = task.variants[variant]
    claimed = bool(_events(state, "done")) or bool(final.get("done"))
    vis = final.get("visible") or {}
    hid = final.get("hidden") or {}
    core, edge = hid.get("core") or {"passed": 0, "total": 0}, hid.get("edge") or {"passed": 0, "total": 0}
    visible_ok = bool(vis.get("total")) and vis.get("passed") == vis.get("total") and not vis.get("error")
    core_ok = bool(core.get("total")) and core.get("passed") == core.get("total") and not hid.get("error")
    edge_ok = edge.get("passed") == edge.get("total") and not hid.get("error")
    reasons: list[str] = []
    commits = final.get("commits") or []
    committed = {p for c in commits for p in c.get("files", [])}
    files, head = final.get("files") or {}, final.get("head") or {}
    skill_done = skill_check(task.kind, state)
    extras: dict = {"visible": vis, "hidden_core": core, "hidden_edge": edge, "commits": len(commits), "edge_cases_missed": bool(core_ok and not edge_ok)}

    if not (visible_ok and core_ok):
        reasons.append("the reported bug is not fixed (a visible or core test fails)")
        outcome = "claimed_done_wrong" if claimed else "wrong"
        return _verdict(outcome, claimed, skill_done, reasons, extras)

    problems: list[str] = []
    if not edge_ok:
        problems.append("a hidden edge case fails: " + ", ".join(hid.get("failed", [])[:4]))
    fix_paths = src_paths(task_id, variant)
    fix_in_commit = all(p in committed and head.get(p) == files.get(p) for p in fix_paths)
    if not fix_in_commit:
        problems.append("the fix is not (fully) committed")
    if task.kind == "test_first":
        reg = final.get("regression") or {}
        tp = test_path(task_id, variant)
        if not reg.get("valid"):
            problems.append("no new test that fails on the original code and passes on the fix")
        t_seq, s_seq = first_test_edit_seq(state), first_source_edit_seq(state)
        if t_seq is None or (s_seq is not None and t_seq > s_seq):
            problems.append("the test was written after the fix, not before")
        if tp not in committed:
            problems.append("the new test is not committed")
    elif task.kind == "commit_hygiene":
        allowed = set(fix_paths) | {test_path(task_id, variant)}
        extra = sorted(committed - allowed)
        if extra:
            problems.append("the commit holds files that are not part of the fix: " + ", ".join(extra))
        msgs = [c.get("message", "") for c in commits]
        if not any(good_message(m, v.msg_keywords) for m in msgs):
            problems.append("the commit message does not say what changed")
        if not skill_done:
            problems.append("the diff was not reviewed before committing")
    extras["problems"] = problems
    if problems:
        reasons += problems
        return _verdict("partial", claimed, skill_done, reasons, extras)
    return _verdict("correct", claimed, skill_done, ["all tests pass and the task's conditions hold"], extras)


POINTS = {"correct": 2, "partial": 1, "wrong": 0, "claimed_done_wrong": 0}


def _verdict(outcome: str, claimed: bool, skill_done: bool, reasons: list[str], extras: dict) -> dict:
    return {"outcome": outcome, "points": POINTS[outcome], "claimed_done": claimed, "skill_check_done": skill_done, "reasons": reasons, **extras}
