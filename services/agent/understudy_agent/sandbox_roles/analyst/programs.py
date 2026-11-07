"""Scripted programs for the analyst workbench: lists of step tuples in the ``programs_util`` vocabulary. Pure and deterministic. Used by the sandbox tests,
the expert recordings and the fake participants.

Styles: ``expert`` (profiles the data first, cleans what it showed, reconciles with the control where there is one, cuts by the right dimension, types the
right answer with the status "Found problems and handled them"; ``variation`` 0..3 permutes the allowed order of the optional steps), ``skipper`` (trusts
the raw table: reads the total, or the overall rate, or the plain mean, and submits the naive answer as "Checked and consistent") and ``claimer`` (submits a
made-up answer as "Checked and consistent").
"""
from __future__ import annotations

from .page import LABELS
from .tasks import TASKS

CLEAN = {
    ("d-sanity-1", 1): "dupExact", ("d-sanity-1", 2): "dupKey", ("d-sanity-2", 1): "units:minutes to hours", ("d-sanity-2", 2): "units:pence to pounds",
}
GROUP = {  # the dimension(s) the expert groups by, and the measure/aggregate used to read the answer
    ("d-aggregation-1", 1): (["campaign", "device"], "conversion rate", "sum"), ("d-aggregation-1", 2): (["campaign", "customer_type"], "conversion rate", "sum"),
    ("d-aggregation-2", 1): (["customer_id"], "amount", "sum"), ("d-aggregation-2", 2): (["store"], "sales", "sum"),
}
EXCLUDE = {("d-reconcile-2", 1): ("status", ["cancelled", "refunded"]), ("d-reconcile-2", 2): ("state", ["voided", "chargeback"])}
MEASURE = {("d-sanity-1", 1): "amount", ("d-sanity-1", 2): "amount", ("d-sanity-2", 1): "time_taken", ("d-sanity-2", 2): "amount",
           ("d-reconcile-1", 1): "amount", ("d-reconcile-1", 2): "amount", ("d-reconcile-2", 1): "amount", ("d-reconcile-2", 2): "amount",
           ("d-aggregation-2", 1): "amount", ("d-aggregation-2", 2): "sales"}
JOIN_DIM = {("d-reconcile-1", 1): "region", ("d-reconcile-1", 2): "category"}


def _fmt(task_id: str, variant: int, x) -> str:
    if isinstance(x, str):
        return x
    return str(int(round(x))) if TASKS[task_id].variants[variant].tol >= 1.0 else f"{x:.2f}"


def _pivot(L: dict, by: list[str], measure: str, agg: str) -> list[tuple]:
    steps: list[tuple] = [("select", L["by"], by[0] if by else "(none)"), ("select", L["then"], by[1] if len(by) > 1 else "(none)"),
                          ("select", L["measure"], measure), ("select", L["agg"], agg), ("click", L["pivot"])]
    return steps


def _filter(L: dict, col: str, val: str) -> list[tuple]:
    return [("select", L["fcol"], col), ("select", L["fop"], "is"), ("fill", L["fval"], val)]


def _answer(L: dict, text: str, status: str) -> list[tuple]:
    return [("fill", L["answer"], text), ("select", L["status"], status), ("click", L["submit"])]


def program(task_id: str, variant: int, style: str, *, variation: int = 0, layout: str = "v1") -> list[tuple]:
    t = TASKS[task_id]
    v = t.variants[variant]
    L = LABELS[layout]
    truth, naive = v.truth, v.naive
    if style == "claimer":
        return _answer(L, "1" if isinstance(truth, float) else "C", "Checked and consistent")
    if style == "skipper":
        if t.skill == "aggregation" and task_id == "d-aggregation-1":
            return _pivot(L, ["campaign"], "conversion rate", "sum") + _answer(L, _fmt(task_id, variant, naive), "Checked and consistent")
        if task_id == "d-reconcile-1":
            return [("click", v.join["label"])] + _pivot(L, [JOIN_DIM[(task_id, variant)]], "amount", "mean") + _answer(L, _fmt(task_id, variant, naive), "Checked and consistent")
        return [("click", L["apply"])] + _answer(L, _fmt(task_id, variant, naive), "Checked and consistent")
    if style != "expert":
        raise ValueError(f"unknown style {style!r}")
    steps: list[tuple] = [("click", L["profile"])]
    opt: dict[str, list[tuple]] = {}
    if t.skill == "sanity":
        kind = CLEAN[(task_id, variant)]
        if kind.startswith("units:"):
            clean = [("select", L["rule"], kind.split(":", 1)[1]), ("click", L["units"])]
        else:
            clean = [("click", L["dupExact"] if kind == "dupExact" else L["dupKey"])]
        opt["chart"] = [("select", L["chCol"], MEASURE[(task_id, variant)]), ("click", L["chart"])]
        order = {0: ["clean", "apply"], 1: ["chart", "clean", "apply"], 2: ["clean", "chart", "apply"], 3: ["clean", "apply", "chart"]}[variation % 4]
        seg = {"clean": clean, "apply": [("click", L["apply"])], "chart": opt["chart"]}
        for k in order:
            steps += seg[k]
    elif t.skill == "reconcile" and task_id == "d-reconcile-1":
        dim = JOIN_DIM[(task_id, variant)]
        ct = [("select", L["ctMeasure"], "amount"), ("click", L["control"])]
        join = [("click", v.join["label"])]
        rest = [("click", L["norm"])] + join + ct + _pivot(L, [dim], "amount", "mean")
        order = {0: join + ct + rest, 1: join + [("click", L["control"])] + rest, 2: ct + join + ct + rest, 3: join + ct + [("click", L["dupKey"])] + rest}[variation % 4]
        steps += order
    elif t.skill == "reconcile":
        col, bad = EXCLUDE[(task_id, variant)]
        ct = [("select", L["ctMeasure"], "amount"), ("click", L["control"])]
        excl: list[tuple] = []
        for b in bad:
            excl += _filter(L, col, b) + [("click", L["excl"])]
        order = {0: ct + _pivot(L, [col], "amount", "sum") + excl + ct, 1: _pivot(L, [col], "amount", "sum") + ct + excl + ct, 2: ct + excl + ct, 3: ct + _pivot(L, [col], "amount", "count") + excl + ct}[variation % 4]
        steps += order + [("click", L["apply"])]
    else:
        by, measure, agg = GROUP[(task_id, variant)]
        first = _pivot(L, by[:1], measure, agg) if task_id == "d-aggregation-1" else []
        steps += {0: first + _pivot(L, by, measure, agg), 1: _pivot(L, by, measure, agg), 2: [("select", L["chCol"], v.columns[-1][0]), ("click", L["chart"])] + first + _pivot(L, by, measure, agg),
                  3: first + _pivot(L, by, measure, agg) + _pivot(L, by, measure, agg)}[variation % 4]
    return steps + _answer(L, _fmt(task_id, variant, truth), "Found problems and handled them")


def snippets(task_id: str, variant: int, layout: str = "v1") -> dict[str, list[tuple]]:
    """Step lists a fake participant inserts when the coach prompt for that step arrives."""
    t = TASKS[task_id]
    v = t.variants[variant]
    L = LABELS[layout]
    if (task_id, variant) in GROUP:
        by, measure, agg = GROUP[(task_id, variant)]
    else:
        by, measure, agg = (v.agg_dims[:1] or []), (MEASURE.get((task_id, variant), v.measures[0])), "sum"
    return {"profile_inputs": [("click", L["profile"])], "reconcile_to_control": [("click", L["control"])], "segment_breakdown": _pivot(L, list(by), measure, agg)}
