"""The page of one analyst case: a shell that loads ``static/analyst.js`` and a JSON description of the case. The truth, the naive answer and the
partial answers are NOT in it (only the data, the question, the control figures and the lookup table)."""
from __future__ import annotations

import html
import json

from .tasks import FOOTER, TASKS

DATASET = {("d-sanity-1", 1): "orders", ("d-sanity-1", 2): "tickets", ("d-sanity-2", 1): "deliveries", ("d-sanity-2", 2): "sales",
           ("d-reconcile-1", 1): "orders", ("d-reconcile-1", 2): "order_lines", ("d-reconcile-2", 1): "orders", ("d-reconcile-2", 2): "payments",
           ("d-aggregation-1", 1): "campaign_results", ("d-aggregation-1", 2): "campaign_results", ("d-aggregation-2", 1): "orders", ("d-aggregation-2", 2): "daily_sales"}

LABELS = {
    "v1": {"tableMain": "Table", "fcol": "Filter column", "fop": "Filter operator", "fval": "Filter value", "scol": "Sort column", "sdir": "Sort direction", "apply": "Apply",
           "profile": "Profile data", "by": "Group by", "then": "Then by", "measure": "Measure", "agg": "Aggregate", "pivot": "Pivot", "dupExact": "Remove exact duplicates",
           "dupKey": "Remove duplicates by key", "rule": "Unit rule", "units": "Convert units", "norm": "Normalise IDs", "join": "Join lookup table",
           "excl": "Exclude rows matching the filter", "undo": "Undo last clean", "ctMeasure": "Control measure", "control": "Compare with control",
           "chCol": "Chart column", "chart": "Draw chart", "answer": "Answer", "status": "Status of the data", "submit": "Submit answer",
           "publish": "Publish to the shared dashboard"},
    "v2": {"tableMain": "Dataset", "fcol": "Where column", "fop": "Where operator", "fval": "Where value", "scol": "Order by column", "sdir": "Order direction", "apply": "Run view",
           "profile": "Check the data", "by": "Split by", "then": "And by", "measure": "Quantity", "agg": "Calculation", "pivot": "Summarise", "dupExact": "Drop identical rows",
           "dupKey": "Drop repeated keys", "rule": "Unit conversion", "units": "Apply conversion", "norm": "Tidy IDs", "join": "Attach lookup table",
           "excl": "Remove rows matching the filter", "undo": "Step back", "ctMeasure": "Ledger measure", "control": "Check against ledger",
           "chCol": "Plot column", "chart": "Make chart", "answer": "Your answer", "status": "How sure are you of the data", "submit": "Send answer",
           "publish": "Share on the team dashboard"},
}


def case_json(task_id: str, variant: int, layout: str) -> dict:
    t = TASKS[task_id]
    v = t.variants[variant]
    return {"task": task_id, "variant": variant, "layout": layout, "title": t.title, "question": v.question, "footer": FOOTER, "dataset": DATASET[(task_id, variant)],
            "columns": [list(c) for c in v.columns], "rows": [list(r) for r in v.rows], "key": v.key, "unit_rules": list(v.unit_rules), "id_columns": list(v.id_columns),
            "join": v.join, "control": v.control, "rate": v.rate, "agg_dims": list(v.agg_dims), "answer_hint": v.answer_hint, "labels": LABELS[layout]}


def render_page(task_id: str, variant: int, ctx: dict) -> str:
    layout = ctx.get("layout", "v1")
    data = json.dumps(case_json(task_id, variant, layout)).replace("</", "<\\/")
    title = TASKS[task_id].title
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(title)} - analysis workbench</title><link rel=\"stylesheet\" href=\"/static/analyst.css\"></head>"
            f"<body><main id=\"app\"></main><script id=\"case\" type=\"application/json\">{data}</script>"
            f"<script src=\"/static/analyst.js\"></script></body></html>")
