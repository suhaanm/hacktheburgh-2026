"""Vetted template: profile one CSV. Runs inside the sandbox: no network, writes only in the workspace.
Reads input/data.csv; writes result.json (what the child emits) and out/profile.json (for the worker)."""
import csv
import json
import math
import os

OUTLIER_Z = 3.5


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


with open("input/data.csv", newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))
names = list(rows[0].keys()) if rows else []
n = len(rows)
columns, outliers = [], []
for name in names:
    raw = [(r.get(name) or "").strip() for r in rows]
    present = [v for v in raw if v != ""]
    missing_share = round((n - len(present)) / n, 6) if n else 0.0
    vals = [num(v) for v in present]
    if present and all(v is not None for v in vals):
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        columns.append({"name": name, "kind": "numeric", "missing_share": missing_share, "mean": round(mean, 6),
                        "std": round(std, 6), "min": min(vals), "max": max(vals)})
        if std > 0 and name != "order_id":
            for i, v in enumerate(raw):
                x = num(v)
                if x is None:
                    continue
                z = (x - mean) / std
                if abs(z) >= OUTLIER_Z:
                    rid = rows[i].get("order_id")
                    outliers.append({"column": name, "row": int(float(rid)) if num(rid) is not None else i + 1,
                                     "value": x, "z": round(z, 3)})
    else:
        columns.append({"name": name, "kind": "categorical", "missing_share": missing_share})
outliers = sorted(outliers, key=lambda o: -abs(o["z"]))[:20]
result = {"n_rows": n, "columns": columns, "outliers": outliers}
os.makedirs("out", exist_ok=True)
with open("result.json", "w", encoding="utf-8") as fh:
    json.dump(result, fh)
with open("out/profile.json", "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=1)
print("profiled", n, "rows")
