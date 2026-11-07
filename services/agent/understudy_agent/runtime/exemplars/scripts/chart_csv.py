"""Vetted template: one bar chart from one CSV. Runs inside the sandbox: no network, writes only in the workspace.
x is the first text column with 2 to 12 distinct values; y is the numeric column named revenue, else the last numeric one;
each bar is the total of y for one x value. Writes out/chart.png and result.json (what the child emits)."""
import csv
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


with open("input/data.csv", newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))
names = list(rows[0].keys()) if rows else []
numeric, text = [], []
for name in names:
    vals = [(r.get(name) or "").strip() for r in rows]
    present = [v for v in vals if v != ""]
    (numeric if present and all(num(v) is not None for v in present) else text).append(name)
x_col = next((c for c in text if 2 <= len({(r.get(c) or "").strip() for r in rows}) <= 12), None)
y_col = "revenue" if "revenue" in numeric else (numeric[-1] if numeric else None)
if x_col is None or y_col is None:
    raise SystemExit("no chartable columns")
totals = {}
for r in rows:
    y = num(r.get(y_col))
    if y is not None:
        label = (r.get(x_col) or "").strip()
        totals[label] = totals.get(label, 0.0) + y
labels = sorted(totals)
values = [round(totals[k], 4) for k in labels]
os.makedirs("out", exist_ok=True)
fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
ax.bar(labels, values, color="#4c78a8")
ax.set_xlabel(x_col)
ax.set_ylabel(y_col + " (total)")
ax.set_title(y_col + " by " + x_col)
fig.tight_layout()
fig.savefig("out/chart.png")
result = {"chart_file": "chart.png", "kind": "bar", "x": x_col, "y": y_col, "n_points": len(labels),
          "values": [{"label": k, "value": v} for k, v in zip(labels, values)]}
with open("result.json", "w", encoding="utf-8") as fh:
    json.dump(result, fh)
print("charted", len(labels), "bars")
