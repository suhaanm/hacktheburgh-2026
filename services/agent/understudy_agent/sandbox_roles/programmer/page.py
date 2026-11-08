"""The page of one programmer case: a shell that loads ``static/programmer.js`` and a JSON description of the case. The hidden tests, the
reference solutions and the naive fixes are NOT in it."""
from __future__ import annotations

import html
import json

from .tasks import TASKS, ticket

DOCS = """Array.prototype.slice(start, end)   copy of part of a list; end is not included
Math.ceil(x) rounds up, Math.floor(x) rounds down, Math.trunc(x) drops the fraction
a?.b   undefined instead of an error when a is null or undefined;   a ?? b   b when a is null or undefined
list.filter(fn)   a new list with the items for which fn returns true
n.toFixed(2)   the number as text with two decimals"""

LABELS = {
    "v1": {"editor": "Editor", "run": "Run tests", "output": "Test output", "probe": "Try an expression", "probeRun": "Evaluate", "inputs": "Sample inputs",
           "docs": "Language docs", "diff": "Review diff", "message": "Message", "commit": "Commit", "done": "Mark done", "deploy": "Deploy to production"},
    "v2": {"editor": "Source editor", "run": "Execute test suite", "output": "Suite results", "probe": "Quick check", "probeRun": "Try it", "inputs": "Input values",
           "docs": "Reference", "diff": "Show changes", "message": "Snapshot note", "commit": "Save snapshot", "done": "Finish ticket", "deploy": "Release to live"},
}


def case_json(task_id: str, variant: int, layout: str) -> dict:
    t = TASKS[task_id]
    v = t.variants[variant]
    src = [p for p in v.files if p.startswith("src/") and p in v.reference]
    return {"task": task_id, "variant": variant, "layout": layout, "ticket": list(ticket(task_id, variant)), "files": v.files, "head_overrides": v.head_overrides,
            "inputs": v.inputs, "docs": DOCS, "labels": LABELS[layout], "entry": v.entry or src[0]}


def render_page(task_id: str, variant: int, ctx: dict) -> str:
    layout = ctx.get("layout", "v1")
    title = TASKS[task_id].variants[variant].ticket[0]
    data = json.dumps(case_json(task_id, variant, layout)).replace("</", "<\\/")
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(title)} - workbench</title><link rel=\"stylesheet\" href=\"/static/programmer.css\"></head>"
            f"<body><main id=\"app\"></main><script id=\"case\" type=\"application/json\">{data}</script>"
            f"<script src=\"/static/programmer.js\"></script></body></html>")
