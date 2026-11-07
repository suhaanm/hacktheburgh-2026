"""Vetted template: a phased, resumable data pipeline for order lines. Runs in the sandbox (no network, writes only in the
workspace). Inputs: input/orders.csv, input/customers.csv, input/control.json (the ledger's total, which excludes lines on
hold). control.json in the workspace names ONE phase per run; state.json records what is done; intermediate files are in scratch/.

  profile    count rows, exact duplicate lines, lines priced in pence (currency GBX) and quantity outliers (more than 50 times
             the median quantity)
  dedupe     drop exact duplicate lines (keep the first)
  units      convert pence to pounds (GBX -> GBP, price / 100)
  outliers   put outlier lines on hold: out of the working table, listed for review
  join       attach each line's region from the customers table (from the latest cleaned table that exists)
  aggregate  revenue by region and the grand total, to the penny
  chart      a bar chart of revenue by region
  reconcile  compare the grand total with the ledger's control total; this is the sanity check before a total is trusted
  final      write result.json (total_trusted is true only if the reconcile phase ran and the gap is zero)

Cleaning phases may be skipped; later phases then use the latest table that exists, so a skipped phase shows up as a total that
does not reconcile. After each run it writes status.json (typed numbers only). input/fault.json {"crash_on_call": k} crashes the
k-th call once (failure injection).
"""
import csv
import json
import os
import statistics
import sys

sys.dont_write_bytecode = True
STATE, STATUS = "state.json", "status.json"
# each phase reads its logical predecessor (never its own output), so running a phase again after a crash gives the same answer
PRED = {"dedupe": ["input/orders.csv"],
        "units": ["scratch/orders_dedup.csv", "input/orders.csv"],
        "outliers": ["scratch/orders_units.csv", "scratch/orders_dedup.csv", "input/orders.csv"],
        "join": ["scratch/orders_clean.csv", "scratch/orders_units.csv", "scratch/orders_dedup.csv", "input/orders.csv"]}
OUTLIER_X = 50


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"calls": 0, "crashed": False, "phases": [], "sig": {}, "outliers": [], "agg": None, "rec": None}


def save_state(st):
    json.dump(st, open(STATE + ".tmp", "w"))
    os.replace(STATE + ".tmp", STATE)


def table(name):
    with open(name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def latest(phase):
    for t in PRED.get(phase, ["input/orders.csv"]):
        if os.path.exists(t):
            return t
    raise SystemExit("no orders table")


def write_table(name, rows, fields):
    os.makedirs("scratch", exist_ok=True)
    with open(name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def amount(r):
    return float(r["qty"]) * float(r["unit_price"])


def main():
    st = load_state()
    st["calls"] += 1
    fault = json.load(open("input/fault.json")) if os.path.exists("input/fault.json") else {}
    if fault.get("crash_on_call") == st["calls"] and not st["crashed"]:
        st["crashed"] = True
        save_state(st)
        raise RuntimeError("injected fault")
    phase = json.load(open("control.json"))["phase"]
    rows = table(latest(phase))
    fields = list(rows[0].keys()) if rows else []
    sig = st["sig"]
    if phase == "profile":
        raw = table("input/orders.csv")
        seen, dups = set(), 0
        for r in raw:
            k = tuple(r.values())
            dups += k in seen
            seen.add(k)
        med = statistics.median(float(r["qty"]) for r in raw)
        sig.update(rows_in=len(raw), duplicates_found=dups, unit_suspects=sum(1 for r in raw if r["currency"] == "GBX"),
                   outliers_found=sum(1 for r in raw if float(r["qty"]) > OUTLIER_X * med))
    elif phase == "dedupe":
        seen, out = set(), []
        for r in rows:
            k = tuple(r.values())
            if k not in seen:
                seen.add(k)
                out.append(r)
        write_table("scratch/orders_dedup.csv", out, fields)
        sig.update(duplicates_removed=len(rows) - len(out), rows_out=len(out))
    elif phase == "units":
        n = 0
        for r in rows:
            if r["currency"] == "GBX":
                r["unit_price"] = repr(round(float(r["unit_price"]) / 100, 6))
                r["currency"] = "GBP"
                n += 1
        write_table("scratch/orders_units.csv", rows, fields)
        sig.update(unit_fixes=n, rows_out=len(rows))
    elif phase == "outliers":
        med = statistics.median(float(r["qty"]) for r in rows)
        hold = [r for r in rows if float(r["qty"]) > OUTLIER_X * med]
        keep = [r for r in rows if float(r["qty"]) <= OUTLIER_X * med]
        write_table("scratch/orders_clean.csv", keep, fields)
        st["outliers"] = sorted(int(r["line_id"]) for r in hold)
        sig.update(outliers_flagged=len(hold), rows_out=len(keep))
    elif phase == "join":
        region = {r["customer_id"]: r["region"] for r in table("input/customers.csv")}
        write_table("scratch/joined.csv", [dict(r, region=region.get(r["customer_id"], "unknown")) for r in rows], fields + ["region"])
        sig.update(rows_out=len(rows))
    elif phase == "aggregate":
        j = table("scratch/joined.csv") if os.path.exists("scratch/joined.csv") else None
        if j is None:
            raise SystemExit("join first")
        tot = {}
        for r in j:
            tot[r["region"]] = tot.get(r["region"], 0.0) + amount(r)
        st["agg"] = {"regions": {k: round(v, 2) for k, v in sorted(tot.items())}, "grand": round(sum(amount(r) for r in j), 2),
                     "rows": len(j)}
        sig.update(rows_out=len(j))
    elif phase == "chart":
        if not st["agg"]:
            raise SystemExit("aggregate first")
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        os.makedirs("out", exist_ok=True)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
        ax.bar(list(st["agg"]["regions"]), list(st["agg"]["regions"].values()), color="#4c78a8")
        ax.set_title("Revenue by region (GBP)")
        fig.tight_layout()
        fig.savefig("out/revenue_by_region.png")
    elif phase == "reconcile":
        if not st["agg"]:
            raise SystemExit("aggregate first")
        control = json.load(open("input/control.json"))["ledger_total_gbp"]
        gap = round((st["agg"]["grand"] - control) * 100)
        st["rec"] = {"control": control, "gap_cents": gap}
        sig.update(reconcile_gap_cents=max(-999999, min(999999, gap)), reconciled=1 if gap == 0 else 0)
    elif phase == "final":
        agg, rec = st["agg"], st["rec"]
        result = {"rows_in": len(table("input/orders.csv")), "rows_out": agg["rows"] if agg else 0,
                  "duplicates_removed": sig.get("duplicates_removed", 0), "unit_fixes": sig.get("unit_fixes", 0),
                  "outlier_lines": st["outliers"][:20],
                  "region_totals": [{"region": k, "total": v} for k, v in (agg["regions"].items() if agg else [])],
                  "grand_total": agg["grand"] if agg else 0.0, "control_total": rec["control"] if rec else 0.0,
                  "reconciled": bool(rec and rec["gap_cents"] == 0), "total_trusted": bool(rec and rec["gap_cents"] == 0),
                  "chart_file": "revenue_by_region.png" if os.path.exists("out/revenue_by_region.png") else ""}
        json.dump(result, open("result.json", "w"))
        os.makedirs("out", exist_ok=True)
        json.dump(result, open("out/pipeline_summary.json", "w"), indent=1)
    else:
        raise SystemExit("unknown phase")
    st["phases"].append(phase)
    st["sig"] = sig
    save_state(st)
    json.dump({"signals": {**{k: v for k, v in sig.items()}, "phases_done": len(st["phases"])}}, open(STATUS, "w"))
    print("phase", phase, "done")


main()
