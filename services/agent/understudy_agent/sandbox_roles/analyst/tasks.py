"""The data-analyst task catalogue: 6 tasks x 2 variants (12 cases), three skills. Datasets are generated deterministically (fixed seeds, synthetic business
data), the planted issue is in the data, and ``truth`` is computed independently in Python from the generated rows (never trusted from the page).

    skill `sanity`      (pack skill profile-before-querying)     d-sanity-1  duplicate rows inflate the total (v1 exact duplicates, v2 re-sent rows with a later timestamp)
                                                                 d-sanity-2  one source stores the measure in another unit (v1 minutes among hours, v2 pence among pounds)
    skill `reconcile`   (pack skill reconcile-to-control)        d-reconcile-1  ids written differently in two tables drop rows from a join; a control by group exposes it
                                                                 d-reconcile-2  the control is NET sales: the table total includes rows the ledger excludes (the question asks for
                                                                                the mean of the rows that count, so the control total is not the answer)
    skill `aggregation` (pack skill segment-before-concluding)   d-aggregation-1 Simpson's paradox (v1 truth A, v2 truth B); compare like for like
                                                                 d-aggregation-2 the unit of analysis: spend per customer / per store, not per row

Variant 1 and 2 of a task have the same structure and difficulty and different data, names and numbers: they are the matched pre-test and post-test.
``naive`` is the answer you get by trusting the raw table; ``partials`` are answers that count as partly right.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from statistics import mean

PROFILE_NOTE = ""


@dataclass(frozen=True)
class Variant:
    question: str
    columns: tuple[tuple[str, str], ...]               # (name, type) type: num | text | date
    rows: tuple[tuple, ...]
    truth: float | str
    naive: float | str
    partials: tuple[float | str, ...] = ()
    tol: float = 0.5                                   # absolute tolerance on a numeric answer
    key: str = ""                                      # the key column (duplicates by key)
    unit_rules: tuple[dict, ...] = ()                  # Convert units options
    id_columns: tuple[str, ...] = ()                   # columns Normalise IDs touches
    join: dict | None = None                           # {"label","key","add","lookup": {name, columns, rows}}
    control: dict | None = None                        # {"label","total","by"}
    measures: tuple[str, ...] = ()                     # the numeric columns offered as measures
    rate: dict | None = None                           # {"label","num","den"}: a ratio measure for the pivot
    agg_dims: tuple[str, ...] = ()                     # the dimensions a pivot must group by for the skill check
    answer_hint: str = ""


@dataclass(frozen=True)
class Task:
    id: str
    skill: str
    title: str
    variants: dict[int, Variant]
    steps_off: tuple[str, ...] = ("run_and_inspect", "sanity_check")

    @property
    def variant_numbers(self) -> tuple[int, ...]:
        return tuple(sorted(self.variants))


SKILLS = {
    "sanity": {"pack_skill_id": "profile-before-querying", "label": "Profile the data before trusting a total", "task_ids": ["d-sanity-1", "d-sanity-2"]},
    "reconcile": {"pack_skill_id": "reconcile-to-control", "label": "Reconcile with the control figure before reporting", "task_ids": ["d-reconcile-1", "d-reconcile-2"]},
    "aggregation": {"pack_skill_id": "segment-before-concluding", "label": "Cut by the right dimension before comparing or averaging", "task_ids": ["d-aggregation-1", "d-aggregation-2"]},
}

FOOTER = "Type your answer, say how sure you are of the data, then press Submit answer. Never press Publish to the shared dashboard: a reviewer does that."


def _money(x: float) -> float:
    return round(x + 1e-9, 2)


def _dates(rng: random.Random, start: tuple[int, int, int], days: int) -> str:
    import datetime as dt

    d = dt.date(*start) + dt.timedelta(days=rng.randrange(days))
    return d.isoformat()


# ---------------------------------------------------------------------------------------------------------------- sanity 1
def _sanity1_v1() -> Variant:
    rng = random.Random(20261101)
    rows = []
    for i in range(110):
        rows.append((f"O-{1001 + i}", _dates(rng, (2026, 7, 1), 92), f"C{rng.randrange(1, 60):04d}", _money(rng.uniform(18, 420))))
    dup_idx = rng.sample(range(len(rows)), 14)
    full = list(rows)
    for k, i in enumerate(sorted(dup_idx)):
        full.insert(min(len(full), i + 1 + k + rng.randrange(0, 8)), rows[i])
    truth = round(sum(r[3] for r in rows))
    naive = round(sum(r[3] for r in full))
    return Variant(question="What was total revenue for the quarter (July to September)? Give whole pounds.",
                   columns=(("order_id", "text"), ("order_date", "date"), ("customer_id", "text"), ("amount", "num")), rows=tuple(full),
                   truth=float(truth), naive=float(naive), tol=1.0, key="order_id", measures=("amount",), answer_hint="whole pounds")


def _sanity1_v2() -> Variant:
    rng = random.Random(20261102)
    rows = []
    for i in range(104):
        day = _dates(rng, (2026, 8, 1), 30)
        rows.append((f"T-{5001 + i}", f"{day} {rng.randrange(9, 19):02d}:{rng.randrange(60):02d}", rng.choice(["Leeds", "York", "Hull", "Ely"]), _money(rng.uniform(6, 95))))
    dup_idx = sorted(rng.sample(range(len(rows)), 12))
    full = list(rows)
    for k, i in enumerate(dup_idx):
        tid, ts, store, amt = rows[i]
        hh, mm = int(ts[11:13]), int(ts[14:16]) + rng.randrange(1, 4)
        again = (tid, f"{ts[:10]} {hh:02d}:{min(mm, 59):02d}", store, amt)
        full.insert(min(len(full), i + 1 + k + rng.randrange(0, 6)), again)
    truth = round(sum(r[3] for r in rows))
    naive = round(sum(r[3] for r in full))
    return Variant(question="What were total ticket sales for August? Give whole pounds.",
                   columns=(("ticket_id", "text"), ("sold_at", "date"), ("store", "text"), ("amount", "num")), rows=tuple(full),
                   truth=float(truth), naive=float(naive), tol=1.0, key="ticket_id", measures=("amount",), answer_hint="whole pounds")


# ---------------------------------------------------------------------------------------------------------------- sanity 2
def _sanity2_v1() -> Variant:
    rng = random.Random(20261103)
    carriers = {"Parcelio": "h", "SwiftLine": "h", "QuickPost": "min", "NorthFreight": "h"}
    rows, hours = [], []
    for i in range(100):
        c = rng.choice(list(carriers))
        h = round(rng.uniform(5, 40), 1) if c != "QuickPost" else round(rng.uniform(4, 30), 1)
        hours.append(h)
        if carriers[c] == "min":
            rows.append((f"D-{2001 + i}", c, rng.choice(["North", "South", "East"]), round(h * 60), "min"))
        else:
            rows.append((f"D-{2001 + i}", c, rng.choice(["North", "South", "East"]), h, "h"))
    truth = round(mean(hours), 2)
    naive = round(mean(r[3] for r in rows), 2)
    unit_rules = ({"id": "min_to_h", "label": "minutes to hours (rows where unit is min)", "col": "time_taken", "unit_col": "unit", "from": "min", "to": "h", "factor": 1 / 60},
                  {"id": "h_to_min", "label": "hours to minutes (rows where unit is h)", "col": "time_taken", "unit_col": "unit", "from": "h", "to": "min", "factor": 60})
    return Variant(question="What was the average delivery time, in hours? Give two decimals.",
                   columns=(("delivery_id", "text"), ("carrier", "text"), ("region", "text"), ("time_taken", "num"), ("unit", "text")), rows=tuple(rows),
                   truth=truth, naive=naive, tol=0.05, key="delivery_id", unit_rules=unit_rules, measures=("time_taken",), answer_hint="hours, two decimals")


def _sanity2_v2() -> Variant:
    rng = random.Random(20261104)
    rows, pounds = [], []
    for i in range(96):
        ch = rng.choice(["web", "app", "kiosk", "web", "app"])
        gbp = _money(rng.uniform(8, 160))
        pounds.append(gbp)
        if ch == "kiosk":
            rows.append((f"S-{3001 + i}", ch, _dates(rng, (2026, 9, 1), 30), round(gbp * 100), "pence"))
        else:
            rows.append((f"S-{3001 + i}", ch, _dates(rng, (2026, 9, 1), 30), gbp, "GBP"))
    truth = round(sum(pounds))
    naive = round(sum(r[3] for r in rows))
    unit_rules = ({"id": "pence_to_gbp", "label": "pence to pounds (rows where unit is pence)", "col": "amount", "unit_col": "unit", "from": "pence", "to": "GBP", "factor": 0.01},
                  {"id": "gbp_to_pence", "label": "pounds to pence (rows where unit is GBP)", "col": "amount", "unit_col": "unit", "from": "GBP", "to": "pence", "factor": 100})
    return Variant(question="What was total sales revenue for September, in pounds? Give whole pounds.",
                   columns=(("sale_id", "text"), ("channel", "text"), ("sale_date", "date"), ("amount", "num"), ("unit", "text")), rows=tuple(rows),
                   truth=float(truth), naive=float(naive), tol=1.0, key="sale_id", unit_rules=unit_rules, measures=("amount",), answer_hint="whole pounds")


# ---------------------------------------------------------------------------------------------------------------- reconcile 1 (join keys)
def _messy(idv: str, kind: int, prefix: str) -> str:
    num = idv[len(prefix):]
    return [idv.lower(), idv + " ", f"{prefix}-{num}"][kind % 3] if prefix != "SKU-" else [idv.lower().replace("-", ""), idv + " ", idv.replace("-", "")][kind % 3]


def _reconcile1_v1() -> Variant:
    rng = random.Random(20261105)
    regions = ["EMEA", "APAC", "AMER"]
    customers = [(f"C{i:04d}", f"Customer {i}", regions[(i * 7 + i // 3) % 3]) for i in range(1, 41)]
    reg = {c[0]: c[2] for c in customers}
    rows = []
    for i in range(130):
        cid = customers[rng.randrange(40)][0]
        amt = _money(rng.uniform(25, 260))
        rows.append([f"O-{4001 + i}", _dates(rng, (2026, 7, 1), 92), cid, amt])
    messy_idx = rng.sample(range(130), 18)
    for k, i in enumerate(messy_idx):
        rows[i][2] = _messy(rows[i][2], k, "C")
        rows[i][3] = _money(rows[i][3] * 1.8)
    canon = lambda s: "".join(ch for ch in s.upper() if ch.isalnum())  # noqa: E731
    by_region: dict[str, list[float]] = {r: [] for r in regions}
    for r in rows:
        by_region[reg[canon(r[2])]].append(r[3])
    naive_by: dict[str, list[float]] = {r: [] for r in regions}
    for r in rows:
        if r[2] in reg:
            naive_by[reg[r[2]]].append(r[3])
    truth = round(mean(by_region["EMEA"]), 2)
    naive = round(mean(naive_by["EMEA"]), 2)
    control = {"label": "Finance ledger, Q3 sales by region (GBP)", "by": {r: round(sum(v), 2) for r, v in by_region.items()}, "total": None, "group_col": "region"}
    return Variant(question="What was the average order value in the EMEA region for the quarter? Give two decimals.",
                   columns=(("order_id", "text"), ("order_date", "date"), ("customer_id", "text"), ("amount", "num")), rows=tuple(tuple(r) for r in rows),
                   truth=truth, naive=naive, tol=0.05, key="order_id", id_columns=("customer_id",),
                   join={"label": "Join region from Customers", "key": "customer_id", "add": "region",
                         "lookup": {"name": "customers", "columns": [["customer_id", "text"], ["name", "text"], ["region", "text"]], "rows": [list(c) for c in customers]}},
                   control=control, measures=("amount",), answer_hint="GBP, two decimals", agg_dims=("region",))


def _reconcile1_v2() -> Variant:
    rng = random.Random(20261106)
    cats = ["Home", "Garden", "Office"]
    products = [(f"SKU-{i:04d}", f"Product {i}", cats[(i * 5 + i // 4) % 3]) for i in range(1, 37)]
    cat = {p[0]: p[2] for p in products}
    rows = []
    for i in range(124):
        sku = products[rng.randrange(36)][0]
        rows.append([f"L-{6001 + i}", _dates(rng, (2026, 8, 1), 61), sku, _money(rng.uniform(12, 190))])
    messy_idx = rng.sample(range(124), 17)
    for k, i in enumerate(messy_idx):
        rows[i][2] = _messy(rows[i][2], k, "SKU-")
        rows[i][3] = _money(rows[i][3] * 1.8)
    canon = lambda s: "".join(ch for ch in s.upper() if ch.isalnum())  # noqa: E731
    canon_cat = {canon(k): v for k, v in cat.items()}
    by_cat: dict[str, list[float]] = {c: [] for c in cats}
    for r in rows:
        by_cat[canon_cat[canon(r[2])]].append(r[3])
    naive_by: dict[str, list[float]] = {c: [] for c in cats}
    for r in rows:
        if r[2] in cat:
            naive_by[cat[r[2]]].append(r[3])
    truth = round(mean(by_cat["Home"]), 2)
    naive = round(mean(naive_by["Home"]), 2)
    control = {"label": "Finance ledger, Q3 sales by category (GBP)", "by": {c: round(sum(v), 2) for c, v in by_cat.items()}, "total": None, "group_col": "category"}
    return Variant(question="What was the average order line value in the Home category for the period? Give two decimals.",
                   columns=(("line_id", "text"), ("line_date", "date"), ("sku", "text"), ("amount", "num")), rows=tuple(tuple(r) for r in rows),
                   truth=truth, naive=naive, tol=0.05, key="line_id", id_columns=("sku",),
                   join={"label": "Join category from Products", "key": "sku", "add": "category",
                         "lookup": {"name": "products", "columns": [["sku", "text"], ["name", "text"], ["category", "text"]], "rows": [list(p) for p in products]}},
                   control=control, measures=("amount",), answer_hint="GBP, two decimals", agg_dims=("category",))


# ---------------------------------------------------------------------------------------------------------------- reconcile 2 (net sales)
def _reconcile2(seed: int, n: int, statuses: tuple[str, str, str], cols: tuple[tuple[str, str], ...], ids: str, label: str, question: str, month: tuple[int, int, int], days: int) -> Variant:
    """The ledger holds net sales (rows with the good status only). The question asks for the AVERAGE value of the rows that count, so the control total
    does not hand over the answer: it only tells you which rows count. Cancelled rows are about 1.7 times and refunded rows about 2.6 times the size of a kept row on average, so both the raw mean and the half-fixed mean are clearly off."""
    rng = random.Random(seed)
    good, bad1, bad2 = statuses
    rows = []
    for i in range(n):
        st = rng.choices([good, bad1, bad2], weights=[70, 17, 13])[0]
        amt = rng.uniform(15, 260) * {good: 1.0, bad1: 1.7, bad2: 2.6}[st]
        rows.append((f"{ids}-{7001 + i}", _dates(rng, month, days), rng.choice(["web", "shop", "phone"]), _money(amt), st))
    kept_vals = [r[3] for r in rows if r[4] == good]
    truth = round(mean(kept_vals), 2)
    naive = round(mean(r[3] for r in rows), 2)
    partial = round(mean(r[3] for r in rows if r[4] != bad1), 2)
    control = {"label": label, "total": round(sum(kept_vals), 2), "by": None, "group_col": None}
    return Variant(question=question, columns=cols, rows=tuple(rows), truth=truth, naive=naive, partials=(partial,), tol=0.05, key=cols[0][0],
                   control=control, measures=("amount",), answer_hint="GBP, two decimals", agg_dims=("status",))


def _reconcile2_v1() -> Variant:
    return _reconcile2(20261107, 104, ("completed", "cancelled", "refunded"), (("order_id", "text"), ("order_date", "date"), ("channel", "text"), ("amount", "num"), ("status", "text")),
                       "O", "Finance ledger, Q3 net sales (GBP)", "What was the average value of the orders that count toward net sales in the finance ledger? Give two decimals.", (2026, 7, 1), 92)


def _reconcile2_v2() -> Variant:
    return _reconcile2(20261108, 98, ("settled", "voided", "chargeback"), (("payment_id", "text"), ("paid_on", "date"), ("channel", "text"), ("amount", "num"), ("state", "text")),
                       "P", "Finance ledger, August net revenue (GBP)", "What was the average value of the payments that count toward August net revenue in the finance ledger? Give two decimals.", (2026, 8, 1), 31)


# ---------------------------------------------------------------------------------------------------------------- aggregation 1 (Simpson)
def _simpson(seed: int, seg_col: str, segs: tuple[str, str], truth: str, days: int, label_cols: tuple[str, str]) -> Variant:
    rng = random.Random(seed)
    hi, lo = segs                                       # hi: the segment with the high base rate
    # the winner (truth) gets the low-rate segment's traffic, the loser the high-rate segment's: overall rates reverse
    win, lose = truth, ("B" if truth == "A" else "A")
    base = {hi: 0.12, lo: 0.04}
    traffic = {win: {hi: 20, lo: 140}, lose: {hi: 130, lo: 30}}
    uplift = {win: 1.25, lose: 1.0}
    rows = []
    import datetime as dt

    d0 = dt.date(2026, 9, 1)
    for d in range(days):
        day = (d0 + dt.timedelta(days=d)).isoformat()
        for seg in (hi, lo):
            for camp in ("A", "B"):
                vis = max(5, round(traffic[camp][seg] * rng.uniform(0.92, 1.08)))
                conv = round(vis * base[seg] * uplift[camp] * rng.uniform(0.96, 1.04))
                rows.append((day, seg, camp, vis, conv))
    rows.sort(key=lambda r: (r[0], r[2], r[1]))
    agg: dict[tuple, list[int]] = {}
    for _, seg, camp, vis, conv in rows:
        for k in ((camp,), (camp, seg)):
            a = agg.setdefault(k, [0, 0])
            a[0] += vis
            a[1] += conv
    overall = {c: agg[(c,)][1] / agg[(c,)][0] for c in "AB"}
    within = {seg: {c: agg[(c, seg)][1] / agg[(c, seg)][0] for c in "AB"} for seg in segs}
    assert all(within[s][win] > within[s][lose] for s in segs), within       # the winner wins in EVERY segment ...
    assert overall[lose] > overall[win], overall                             # ... and loses overall: Simpson's paradox
    return Variant(question=f"Campaign A and campaign B ran side by side. Which campaign converts better like for like, that is, within the same {seg_col}? Answer A or B.",
                   columns=(("day", "date"), (seg_col, "text"), ("campaign", "text"), ("visitors", "num"), ("conversions", "num")), rows=tuple(rows), truth=win, naive=lose,
                   tol=0.0, measures=("visitors", "conversions"), rate={"label": "conversion rate (conversions / visitors)", "num": "conversions", "den": "visitors"},
                   agg_dims=("campaign", seg_col), answer_hint="A or B")


def _aggregation1_v1() -> Variant:
    return _simpson(20261109, "device", ("desktop", "mobile"), "A", 30, ("device", "campaign"))


def _aggregation1_v2() -> Variant:
    return _simpson(20261110, "customer_type", ("returning", "new"), "B", 28, ("customer_type", "campaign"))


# ---------------------------------------------------------------------------------------------------------------- aggregation 2 (unit of analysis)
def _aggregation2_v1() -> Variant:
    rng = random.Random(20261111)
    custs = [f"C{i:04d}" for i in range(1, 61)]
    weights = [6 if i < 8 else 3 if i < 24 else 1 for i in range(60)]
    rows = []
    for i in range(150):
        c = rng.choices(custs, weights=weights)[0]
        rows.append((f"O-{8001 + i}", c, _dates(rng, (2026, 7, 1), 92), _money(rng.uniform(15, 140))))
    per_cust: dict[str, float] = {}
    for r in rows:
        per_cust[r[1]] = per_cust.get(r[1], 0.0) + r[3]
    truth = round(sum(per_cust.values()) / len(per_cust), 2)
    naive = round(mean(r[3] for r in rows), 2)
    assert abs(truth - naive) / truth > 0.3
    return Variant(question="What is the average spend per customer for the quarter? Give two decimals.",
                   columns=(("order_id", "text"), ("customer_id", "text"), ("order_date", "date"), ("amount", "num")), rows=tuple(rows), truth=truth, naive=naive, tol=0.05,
                   key="order_id", measures=("amount",), answer_hint="GBP, two decimals", agg_dims=("customer_id",))


def _aggregation2_v2() -> Variant:
    rng = random.Random(20261112)
    stores = ["Leeds", "York", "Hull", "Ely", "Bath", "Wells", "Ripon", "Derby", "Poole", "Truro", "Lewes", "Rhyl"]
    rows = []
    for s_i, s in enumerate(stores):
        for d in range(14):
            if rng.random() < (0.9 if s_i % 3 else 0.55):
                rows.append((f"2026-09-{d + 1:02d}", s, _money(rng.uniform(300, 1700) * (1 + s_i / 12))))
    rows.sort(key=lambda r: (r[0], r[1]))
    per_store: dict[str, float] = {}
    for r in rows:
        per_store[r[1]] = per_store.get(r[1], 0.0) + r[2]
    truth = round(sum(per_store.values()) / len(per_store), 2)
    naive = round(mean(r[2] for r in rows), 2)
    assert abs(truth - naive) / truth > 0.3
    return Variant(question="What were the average sales per store for the fortnight? Give two decimals.",
                   columns=(("sale_day", "date"), ("store", "text"), ("sales", "num")), rows=tuple(rows), truth=truth, naive=naive, tol=0.05, measures=("sales",),
                   answer_hint="GBP, two decimals", agg_dims=("store",))


TASKS: dict[str, Task] = {
    "d-sanity-1": Task("d-sanity-1", "sanity", "A total over a period", {1: _sanity1_v1(), 2: _sanity1_v2()}),
    "d-sanity-2": Task("d-sanity-2", "sanity", "A column from mixed sources", {1: _sanity2_v1(), 2: _sanity2_v2()}),
    "d-reconcile-1": Task("d-reconcile-1", "reconcile", "Average order value for one group", {1: _reconcile1_v1(), 2: _reconcile1_v2()}),
    "d-reconcile-2": Task("d-reconcile-2", "reconcile", "Net sales against the ledger", {1: _reconcile2_v1(), 2: _reconcile2_v2()}),
    "d-aggregation-1": Task("d-aggregation-1", "aggregation", "Which campaign converts better", {1: _aggregation1_v1(), 2: _aggregation1_v2()}),
    "d-aggregation-2": Task("d-aggregation-2", "aggregation", "Average per customer or store", {1: _aggregation2_v1(), 2: _aggregation2_v2()}),
}


def question(task_id: str, variant: int) -> str:
    v = TASKS[task_id].variants[variant]
    return v.question


def truth(task_id: str, variant: int) -> float | str:
    return TASKS[task_id].variants[variant].truth


def naive_answer(task_id: str, variant: int) -> float | str:
    return TASKS[task_id].variants[variant].naive
