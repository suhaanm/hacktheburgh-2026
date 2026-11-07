"""Data-analysis exemplar (BGA-5): profile a CSV and chart it, in a sandbox with no network.

Roles: `data_profiler` and `chart_builder`. Each child writes a vetted script into its workspace, runs it in the
sandbox, and emits a typed result. CODE then recounts the table with its own independent implementation and compares
(row count, columns, missing share, mean, spread, range, the extreme value, the chart's bars), and checks that the chart
file is a real picture. Planted facts live in the synthetic fixture, with a truth dict beside it.
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path
from typing import Any

from ..results import VerifyCtx, close, png_ok, register_schema, register_verifier
from ..spec import Check, RoleDef, register_role
from .base import Exemplar, Menu, WorkspaceNeeds, register_exemplar, register_menu, script_text

# ------------------------------------------------------------------------------------------------ output schemas
PROFILE_V1: dict[str, Any] = {
    "type": "object", "required": ["n_rows", "columns", "outliers"], "additionalProperties": False,
    "properties": {
        "n_rows": {"type": "integer", "minimum": 0},
        "columns": {"type": "array", "maxItems": 40, "items": {
            "type": "object", "required": ["name", "kind", "missing_share"], "additionalProperties": False,
            "properties": {"name": {"type": "string", "maxLength": 60}, "kind": {"enum": ["numeric", "categorical"]},
                           "missing_share": {"type": "number", "minimum": 0, "maximum": 1},
                           "mean": {"type": "number"}, "std": {"type": "number"}, "min": {"type": "number"},
                           "max": {"type": "number"}}}},
        "outliers": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "required": ["column", "row", "value", "z"], "additionalProperties": False,
            "properties": {"column": {"type": "string", "maxLength": 60}, "row": {"type": "integer"},
                           "value": {"type": "number"}, "z": {"type": "number"}}}},
    },
}
CHART_V1: dict[str, Any] = {
    "type": "object", "required": ["chart_file", "kind", "x", "y", "n_points", "values"], "additionalProperties": False,
    "properties": {
        "chart_file": {"type": "string", "pattern": "^[A-Za-z0-9._-]{1,60}$"}, "kind": {"enum": ["bar", "hist", "line"]},
        "x": {"type": "string", "maxLength": 60}, "y": {"type": "string", "maxLength": 60},
        "n_points": {"type": "integer", "minimum": 0},
        "values": {"type": "array", "maxItems": 40, "items": {
            "type": "object", "required": ["label", "value"], "additionalProperties": False,
            "properties": {"label": {"type": "string", "maxLength": 60}, "value": {"type": "number"}}}},
    },
}
register_schema("profile_v1", PROFILE_V1)
register_schema("chart_v1", CHART_V1)

_TOOLS = frozenset({"write_workspace", "run_python", "emit_result", "list_dir", "read_file"})
register_role(RoleDef("data_profiler", "Profile one table: counts, missing share, means, extremes.", _TOOLS,
                      frozenset({"tmp"}), "profile_v1", "data_profiler"))
register_role(RoleDef("chart_builder", "Draw one bar chart from one table and report its bars.", _TOOLS,
                      frozenset({"tmp"}), "chart_v1", "chart_builder"))
register_menu("data_profiler", Menu(files={"input": "input/data.csv", "script": "profile.py", "result": "result.json"},
                                    templates={"profile_csv": script_text("profile_csv.py")}),
              "Profile the table the worker named: row count, missing share, means and the extreme values.")
register_menu("chart_builder", Menu(files={"input": "input/data.csv", "script": "chart.py", "result": "result.json"},
                                    templates={"chart_csv": script_text("chart_csv.py")}),
              "Draw one bar chart of the table the worker named and report each bar.")


# ------------------------------------------------------------------------------------------------ the fixture
REGIONS = ("north", "south", "east", "west")
PRICE = {"north": 20.0, "south": 22.0, "east": 18.0, "west": 25.0}
OUTLIER_ROW = 137


def make_sales_csv(dest: Path, *, seed: int = 7, n: int = 240, canary: str | None = None,
                   outlier_row: int = OUTLIER_ROW) -> dict[str, Any]:
    """A synthetic sales table with PLANTED facts: units average exactly 5.0, one revenue outlier (row 137),
    every 8th discount missing (12.5 percent), and a known top region. Returns the truth dict (also the check values).
    `canary` adds name and email columns carrying unique tokens for the leak tests. `n` should be a multiple of 40 so the
    planted means and shares are exact; `outlier_row` moves the planted outlier."""
    rng = random.Random(seed)
    cols = ["order_id", "region", "units", "unit_price", "discount", "revenue", "customer_age"]
    if canary:
        cols += ["customer", "email"]
    rows = []
    totals = {r: 0.0 for r in REGIONS}
    for i in range(1, n + 1):
        region = REGIONS[i % 4]
        units = (3, 4, 5, 6, 7)[i % 5]
        disc = None if i % 8 == 0 else rng.choice((0.0, 0.05, 0.1))
        revenue = round(units * PRICE[region] * (1 - (disc or 0.0)), 2)
        if i == outlier_row:
            revenue = round(revenue * 40, 2)
        totals[region] += revenue
        row = [i, region, units, PRICE[region], "" if disc is None else disc, revenue, 18 + (i * 7) % 50]
        if canary:
            row += [f"Customer {canary}{i % 7}", f"{canary.lower()}{i % 7}@example.com"]
        rows.append(row)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)
    return {"n_rows": n, "units_mean": sum((3, 4, 5, 6, 7)[i % 5] for i in range(1, n + 1)) / n,
            "outlier": {"column": "revenue", "row": outlier_row},
            "discount_missing_share": sum(1 for i in range(1, n + 1) if i % 8 == 0) / n,
            "region_totals": {k: round(v, 4) for k, v in totals.items()}, "top_region": max(totals, key=totals.get)}


# ------------------------------------------------------------------------------------------------ independent recount
def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def recount_profile(csv_path: Path) -> dict[str, Any]:
    """The trusted recount the verifier compares a child's claim with (written separately from the sandbox template)."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    n = len(rows)
    cols: dict[str, dict[str, Any]] = {}
    outl: set[tuple[str, int]] = set()
    top: tuple[float, str, int] | None = None
    for name in (rows[0].keys() if rows else []):
        present = [(r.get(name) or "").strip() for r in rows]
        vals = [v for v in present if v != ""]
        nums = [_num(v) for v in vals]
        info: dict[str, Any] = {"missing_share": (n - len(vals)) / n if n else 0.0}
        if vals and all(x is not None for x in nums):
            xs = [x for x in nums if x is not None]
            mean = sum(xs) / len(xs)
            std = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
            info.update(kind="numeric", mean=mean, std=std, min=min(xs), max=max(xs))
            if std > 0 and name != "order_id":
                for i, v in enumerate(present):
                    x = _num(v)
                    if x is not None and abs((x - mean) / std) >= 3.5:
                        rid = _num(rows[i].get("order_id"))
                        outl.add((name, int(rid) if rid is not None else i + 1))
                        z = abs((x - mean) / std)
                        if top is None or z > top[0]:
                            top = (z, name, int(rid) if rid is not None else i + 1)
        else:
            info["kind"] = "categorical"
        cols[name] = info
    return {"n_rows": n, "columns": cols, "outliers": outl, "top_outlier": top}


def recount_chart(csv_path: Path) -> dict[str, Any]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    header = list(rows[0].keys()) if rows else []
    numeric = [c for c in header if (v := [(r.get(c) or "").strip() for r in rows if (r.get(c) or "").strip()]) and all(_num(x) is not None for x in v)]
    text = [c for c in header if c not in numeric]
    x_col = next((c for c in text if 2 <= len({(r.get(c) or "").strip() for r in rows}) <= 12), None)
    y_col = "revenue" if "revenue" in numeric else (numeric[-1] if numeric else None)
    totals: dict[str, float] = {}
    for r in rows:
        y = _num(r.get(y_col)) if y_col else None
        if y is not None and x_col:
            k = (r.get(x_col) or "").strip()
            totals[k] = totals.get(k, 0.0) + y
    return {"header": header, "x": x_col, "y": y_col, "totals": totals}


# ------------------------------------------------------------------------------------------------ verifiers
def _csv_of(ctx: VerifyCtx) -> Path:
    return Path(ctx.params["csv_path"])


def verify_profile(ctx: VerifyCtx) -> list[Check]:
    truth = recount_profile(_csv_of(ctx))
    out = ctx.output
    got = {c["name"]: c for c in out["columns"]}
    checks = [Check(name="rows_match", ok=out["n_rows"] == truth["n_rows"]),
              Check(name="columns_match", ok=set(got) == set(truth["columns"]))]
    bad_missing = bad_numeric = 0
    for name, t in truth["columns"].items():
        g = got.get(name)
        if g is None:
            bad_missing += 1
            continue
        if g["kind"] != t["kind"] or not close(g["missing_share"], t["missing_share"], 1e-4, 1e-4):
            bad_missing += 1
        if t["kind"] == "numeric":
            for k in ("mean", "std", "min", "max"):
                if k not in g or not close(g[k], t[k], 1e-4, 1e-4):
                    bad_numeric += 1
    checks.append(Check(name="missing_and_kinds_match", ok=bad_missing == 0, detail=f"bad={bad_missing}"))
    checks.append(Check(name="numeric_summary_match", ok=bad_numeric == 0, detail=f"bad={bad_numeric}"))
    claimed = {(o["column"], o["row"]) for o in out["outliers"]}
    top = truth["top_outlier"]
    checks.append(Check(name="outliers_match", ok=claimed == truth["outliers"] and (top is None or (top[1], top[2]) in claimed)))
    return checks


def verify_chart(ctx: VerifyCtx) -> list[Check]:
    truth = recount_chart(_csv_of(ctx))
    out = ctx.output
    pic = None
    if ctx.ws is not None and ctx.ws.work is not None:
        pic = ctx.ws.work / "out" / out["chart_file"]
    values = {v["label"]: v["value"] for v in out["values"]}
    checks = [Check(name="chart_is_a_picture", ok=bool(pic and pic.is_file() and not pic.is_symlink() and png_ok(pic))),
              Check(name="axes_exist", ok=out["x"] in truth["header"] and out["y"] in truth["header"]),
              Check(name="axes_match", ok=out["x"] == truth["x"] and out["y"] == truth["y"]),
              Check(name="bar_count_matches", ok=out["n_points"] == len(truth["totals"]) == len(out["values"])),
              Check(name="bars_match", ok=set(values) == set(truth["totals"]) and all(
                  close(values[k], truth["totals"][k], 1e-4, 1e-3) for k in values if k in truth["totals"]))]
    return checks


register_verifier("data_profiler", verify_profile)
register_verifier("chart_builder", verify_chart)


# ------------------------------------------------------------------------------------------------ the spawn kinds
def prepare(params: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    p = dict(params or {})
    if not p.get("csv_path"):
        truth = make_sales_csv(run_dir / "fixtures" / "sales.csv", canary=p.get("canary"))
        p.update(csv_path=str(run_dir / "fixtures" / "sales.csv"), synthetic=True, truth=truth)
    path = Path(str(p["csv_path"])).expanduser()
    if not path.is_file() or path.is_symlink():
        raise ValueError("csv_path must name a regular file")
    p["csv_path"] = str(path.resolve())
    return p


def needs(role: str, params: dict[str, Any]) -> WorkspaceNeeds:
    return WorkspaceNeeds(inputs=((Path(params["csv_path"]), "data.csv"),))


def mock_steps(role: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    template = "profile_csv" if role == "data_profiler" else "chart_csv"
    return [{"tool": "write_workspace", "file": "script", "template": template},
            {"tool": "run_python", "file": "script"},
            {"tool": "emit_result", "file": "result"}]


for _kind, _roles, _title in (
    ("data.profile", ("data_profiler",), "Profile a CSV"),
    ("data.chart", ("chart_builder",), "Chart a CSV"),
    ("data.suite", ("data_profiler", "chart_builder"), "Profile and chart a CSV in parallel"),
):
    register_exemplar(Exemplar(kind=_kind, title=_title, describe=_title + " in a sandbox with no network.", roles=_roles,
                               needs=needs, prepare=prepare, mock_steps=mock_steps, explicit_files=("csv_path",)))
