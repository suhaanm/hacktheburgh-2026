from __future__ import annotations

from datetime import datetime, timedelta, timezone

from understudy_engine.store import validate_row

T0 = datetime(2026, 11, 9, 9, 0, 0, tzinfo=timezone.utc)
_n = [0]


def ev(dt: float, typ: str, zone: str | None = None, *, task: str | None = "t_h1", person: str = "p_hand", origin: str = "synthetic",
       source: str = "browser", actor: str = "human", t0: datetime = T0, role: str = "benefits-processor", **meta):
    _n[0] += 1
    row = {
        "schema": 1, "id": f"hand{_n[0]:07d}", "t": (t0 + timedelta(seconds=dt)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "origin": origin, "actor": actor, "person": person, "role": role, "source": source, "type": typ,
    }
    if task:
        row["task_id"] = task
    m = dict(meta)
    if zone:
        m["zone"] = zone
    if m:
        row["meta"] = m
    return validate_row(row)


def read(task, t, **kw):
    """READ the record, 8 s."""
    return [ev(t, "focus", "doc", task=task, **kw), ev(t + 7, "scroll", "doc", task=task, **kw)]


def calc(task, t, site="calc1", **kw):
    """OPEN_CALCULATOR, ENTER_HOUSEHOLD, READ_RESULT, then a progress event: ~44 s."""
    return [
        ev(t, "nav", "calc_site", task=task, site=site, **kw),
        ev(t + 6, "click", "household_form", task=task, **kw), ev(t + 14, "click", "household_form", task=task, **kw),
        ev(t + 24, "focus", "calc_result", task=task, **kw), ev(t + 30, "scroll", "calc_result", task=task, **kw),
        ev(t + 31, "progress", task=task, kind="result_read", **kw),
    ]


def cliff(task, t, **kw):
    return [ev(t, "click", "cliff_button", task=task, **kw), ev(t + 4, "scroll", "cliff_panel", task=task, **kw)]


def reconcile(task, t, **kw):
    return [ev(t, "tab", "results_tabs", task=task, **kw), ev(t + 6, "click", "results_tabs", task=task, **kw)]


def copy_to_note(task, t, **kw):
    return [ev(t, "copy", "calc_result", task=task, **kw), ev(t + 3, "tab", "case_note", task=task, **kw), ev(t + 8, "paste", "case_note", task=task, **kw)]


def expert_task(task, t, **kw):
    """A clean case: read, three calculators each with its cliff check, reconcile, copy to the note. About 220 s."""
    out = [ev(t, "task_start", task=task, source="desk", **kw)]
    out += read(task, t + 1, **kw)
    cur = t + 12
    for i, site in enumerate(("calc1", "calc2", "calc3")):
        out += calc(task, cur, site, **kw)
        out += cliff(task, cur + 35, **kw)
        cur += 45
    out += reconcile(task, cur + 5, **kw)
    out += copy_to_note(task, cur + 20, **kw)
    out.append(ev(cur + 32, "task_end", task=task, source="desk", **kw))
    return sorted(out, key=lambda e: (e.t, e.id))


def signature_events(task="t_h1"):
    """Read the record, run calculator 1, read its result, then start copying toward the note without the cliff check."""
    return [ev(0, "task_start", task=task, source="desk")] + read(task, 1) + calc(task, 12) + copy_to_note(task, 50)
