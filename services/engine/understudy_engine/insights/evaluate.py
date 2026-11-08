"""Evaluation of the insights layer (REQ-9): ``evaluate_insights(fast=False, heldout=False) -> dict``. Pre-registered in ``evals/insights/PLAN.md``.

Everything is synthetic and badged (the synthetic firm and the worker worlds below); nobody here is a person. It shows the selection behaves as designed under
stated assumptions: it finds planted effects, stays quiet on null data at a measured rate, is deterministic and stable, and enforces k-anonymity. It does NOT show
that workers find the pointers useful, that admins decide better, or that the planted effects resemble real work (the generators were written by the author of
the selection). Dev seeds 0 to 9 may be inspected and tuned on; held-out seeds 100 to 139 are run once (``heldout=True``) after the plan is committed.

The result: ``{meta, null_worker, null_admin, recall_worker, recall_admin, nothing_stands_out, stability, determinism, suppression, k_anonymity, edge_cases, claims,
limitations}``. ``claims`` are generated from the measured numbers, never typed.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
from collections import Counter
from dataclasses import replace
from typing import Any

import numpy as np

from . import admin as A
from . import views as VW
from . import vocab as V
from .firm import NOW0, build_firm
from .params import DAY, DEFAULT, Params
from .rows import row_t
from .select import history_entry, select
from .stats import seed_from, wilson_interval
from .summary import AdminView, merge_small
from .types import FirmSnapshot, History, InsightCandidate, PersonRecord, insight_id
from .worker import WorkerCtx, worker_run

DEV_SEEDS = tuple(range(10))
HELDOUT_SEEDS = tuple(range(100, 140))
SK, CTL = "check-the-cliff", "enter-household-once"
ROLE = "benefits-processor"
GATE_REASONS = frozenset({"not_enough_data", "stale", "below_effect_floor", "interval_spans_zero", "not_persistent", "not_significant_after_family_control", "short_absence",
                          "no_expert_reference", "group_too_small", "role_changed", "onboarding"})
FALSE_WORKER_KINDS = frozenset({"time_loss_habit", "habit_improved", "relapse", "independence_milestone", "trade_off"})
FALSE_ADMIN_KINDS = frozenset({"role_gap", "cohort_trend", "bottleneck_skill", "unit_attention"})
CHECK = "check_ok"


# ------------------------------------------------------------------------------------------------ helpers
def rate(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson_interval(k, n) if n else (0.0, 1.0)
    return {"k": int(k), "n": int(n), "rate": round(k / n, 4) if n else None, "ci": [round(lo, 4), round(hi, 4)]}


def cluster_rate(per_cluster: list[tuple[int, int]], B: int, seed: int) -> dict[str, Any]:
    """The pooled rate ``sum(k) / sum(n)`` with a bootstrap interval that resamples clusters (people or firms)."""
    k, n = sum(a for a, _ in per_cluster), sum(b for _, b in per_cluster)
    out: dict[str, Any] = {"k": int(k), "n": int(n), "clusters": len(per_cluster), "rate": round(k / n, 4) if n else None, "ci": None}
    if len(per_cluster) >= 2 and n:
        rng = np.random.default_rng(seed)
        arr = np.asarray(per_cluster, float)
        idx = rng.integers(0, len(arr), size=(B, len(arr)))
        s = arr[idx].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(s[:, 1] > 0, s[:, 0] / s[:, 1], np.nan)
        r = r[np.isfinite(r)]
        out["ci"] = [round(float(np.quantile(r, 0.025)), 4), round(float(np.quantile(r, 0.975)), 4)] if r.size else None
    return out


def cut(snap: FirmSnapshot, now: float) -> FirmSnapshot:
    """The firm as it was at ``now``: rows after it are not yet written."""
    return replace(snap, now=now, people=tuple(replace(p, rows=tuple(r for r in p.rows if row_t(r) <= now)) for p in snap.people),
                   feed_t={k: now for k in snap.feed_t})


def drop_rows(snap: FirmSnapshot, frac: float, seed: int) -> FirmSnapshot:
    rng = random.Random(seed)
    return replace(snap, people=tuple(replace(p, rows=tuple(r for r in p.rows if rng.random() >= frac)) for p in snap.people))


def worker_pass(p: PersonRecord, now: float, hist: History | None, params: Params, badge: str = "made-up firm", ctx: WorkerCtx | None = None):
    out = worker_run(p, now, params, ctx or WorkerCtx(badge=badge))
    sel = select(out.candidates, audience="worker", scope=p.id, now=now, history=hist or History(), params=params)
    return out, sel


def sig(sel) -> list[tuple[str, str]]:
    return [(s.cand.kind, s.cand.subject) for s in sel.selected]


def passed_gate(sel, cid: str) -> bool:
    st = sel.reason_of(cid)
    return bool(st) and (st[0] == "selected" or st[1] not in GATE_REASONS)


def _params(fast: bool, **kw: Any) -> Params:
    return replace(DEFAULT, n_boot=100 if fast else 300, **kw)


# ------------------------------------------------------------------------------------------------ M1: worker false insights on null data
def null_worker(seeds: tuple[int, ...], fast: bool) -> dict[str, Any]:
    params, off = _params(fast), _params(fast, family_control=False)
    per_person: list[tuple[int, int]] = []
    per_person_off: list[tuple[int, int]] = []
    pointers = Counter()
    nso, n_with_data = 0, 0
    for sd in seeds:
        firm = build_firm(sd, scenario="null")
        start = firm.snapshot.now - 12 * 7 * DAY
        people = firm.snapshot.people[:: (2 if fast else 1)]
        for p in people:
            k_on = k_off = n = 0
            hist, hist_off = History(), History()
            for wk in range(6, 13):
                now = start + wk * 7 * DAY
                rec = replace(p, rows=tuple(r for r in p.rows if row_t(r) <= now))
                out, sel = worker_pass(rec, now, hist, params)
                _o2, sel2 = worker_pass(rec, now, hist_off, off)
                if out.status in ("no_data", "stale", "onboarding"):
                    continue
                n += 1
                bad = [s for s in sel.selected if s.cand.kind in FALSE_WORKER_KINDS]
                k_on += 1 if bad else 0
                k_off += 1 if any(s.cand.kind in FALSE_WORKER_KINDS for s in sel2.selected) else 0
                nso += 0 if sel.selected else 1
                n_with_data += 1
                for s in bad:
                    pointers[s.cand.kind] += 1
                hist.shown.extend(history_entry(s.cand, now) for s in sel.selected)
                hist_off.shown.extend(history_entry(s.cand, now) for s in sel2.selected)
            per_person.append((k_on, n))
            per_person_off.append((k_off, n))
    return {"person_weeks": cluster_rate(per_person, 400, 11), "without_family_control": cluster_rate(per_person_off, 400, 12), "false_pointers_by_kind": dict(sorted(pointers.items())),
            "target": 0.05, "nothing_stands_out": rate(nso, n_with_data), "firms": len(seeds)}


# ------------------------------------------------------------------------------------------------ M2: admin false insights on null data
def null_admin(seeds: tuple[int, ...], fast: bool) -> dict[str, Any]:
    params = _params(fast)
    per_firm: list[tuple[int, int]] = []
    kinds = Counter()
    for sd in seeds:
        firm = build_firm(sd, scenario="null")
        start = firm.snapshot.now - 12 * 7 * DAY
        k = n = 0
        for wk in ((10, 12) if fast else (9, 10, 11, 12)):
            snap = cut(firm.snapshot, start + wk * 7 * DAY)
            view = AdminView(snap, params)
            sel = select(A.admin_run(view), audience="admin", scope="firm", now=snap.now, params=params)
            bad = [s for s in sel.selected if s.cand.kind in FALSE_ADMIN_KINDS]
            n += 1
            k += 1 if bad else 0
            for s in bad:
                kinds[s.cand.kind] += 1
        per_firm.append((k, n))
    return {"admin_weeks": cluster_rate(per_firm, 400, 13), "false_insights_by_kind": dict(sorted(kinds.items())), "target": 0.10, "firms": len(seeds)}


# ------------------------------------------------------------------------------------------------ M3: worker worlds with planted effects
def _mk(pid: str, t: float, skill: str, outcome: str, lost: float | None, i: int, role: str = ROLE, ttp: float | None = None) -> dict[str, Any]:
    h = hashlib.sha1(f"{pid}|{i}|{skill}|{t}".encode()).hexdigest()[:12]
    return {"id": "a_" + h, "person": pid, "origin": "synthetic", "origin_detail": "synthetic_learner", "t_hour": __import__("time").strftime("%Y-%m-%dT%H", __import__("time").gmtime(t)),
            "role": role, "skill": skill, "step": skill.replace("-", "_")[:40], "stream": "assist", "trigger": "auto" if outcome == "assisted" else "none", "stuck_bucket": None,
            "tier": 1 if outcome == "assisted" else 0, "options_shown": 0, "answer_id": None, "accepted": outcome == "assisted", "dismissed": False, "seconds_to_progress": ttp,
            "lost_s": None if lost is None else round(float(lost), 1), "outcome": outcome, "level_before": 2, "level_after": 2, "taught": False, "retrieval": False}


def _noise(rng: np.random.Generator, mean: float) -> float:
    v = mean + float(rng.normal(0, 7.0))
    if rng.random() < 0.04:
        v += float(rng.uniform(100.0, 300.0))
    return v


def _outcome(rng: np.random.Generator, p_unaided: float, p_err: float = 0.0) -> str:
    u = float(rng.random())
    if u < p_err:
        return "error"
    return "clean" if rng.random() < p_unaided else "assisted"


def world(kind: str, rng: np.random.Generator, pid: str, now: float, delta: float = 30.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    i = 0

    def add(t: float, skill: str, outcome: str, lost: float | None) -> None:
        nonlocal i
        rows.append(_mk(pid, t, skill, outcome, lost, i))
        i += 1

    def control(start_w: int = 0, end_w: int = 12) -> None:
        for w in range(start_w, end_w):
            for _ in range(3):
                add(now - (12 - w) * 7 * DAY + float(rng.uniform(0, 6.5)) * DAY, CTL, _outcome(rng, 0.9), _noise(rng, 0.0))

    if kind in ("time_loss", "improved", "tradeoff", "null"):
        for w in range(12):
            for _ in range(4):
                t = now - (12 - w) * 7 * DAY + float(rng.uniform(0, 6.5)) * DAY
                if kind == "time_loss":
                    add(t, SK, _outcome(rng, 0.85), _noise(rng, delta if w >= 7 else 0.0))
                elif kind == "null":
                    add(t, SK, _outcome(rng, 0.85), _noise(rng, 0.0))
                else:
                    post = t >= now - 24.5 * DAY
                    p_err = (0.4 if (kind == "tradeoff" and post) else 0.1)
                    add(t, SK, _outcome(rng, 0.85, p_err), _noise(rng, 5.0 if post else 40.0))
        control()
    elif kind == "rise":
        for w in range(12):
            p = 0.4 + 0.5 * w / 11.0
            for _ in range(6):
                add(now - (12 - w) * 7 * DAY + float(rng.uniform(0, 6.5)) * DAY, SK, _outcome(rng, p), _noise(rng, 0.0))
        control()
    elif kind == "relapse":
        for j in range(25):
            add(now - (84 - j * 2.5) * DAY, SK, _outcome(rng, 0.98), _noise(rng, 0.0))
        for j in range(10):
            add(now - (19 - j * 2.0) * DAY, SK, _outcome(rng, 0.35), _noise(rng, 0.0))
        control()
    elif kind == "retention":
        for j in range(14):
            add(now - (84 - j * 3.5) * DAY, SK, "clean", _noise(rng, 0.0))
        control()
    elif kind == "holiday":
        for j in range(25):
            add(now - (100 - j * 2.4) * DAY, SK, _outcome(rng, 0.98), _noise(rng, 0.0))
            add(now - (100 - j * 2.4) * DAY + 3600, CTL, _outcome(rng, 0.95), _noise(rng, 0.0))
        for j in range(4):
            add(now - (6 - j * 1.5) * DAY, SK, _outcome(rng, 0.25), _noise(rng, 0.0))
            add(now - (6 - j * 1.5) * DAY + 3600, CTL, _outcome(rng, 0.9), _noise(rng, 0.0))
    rows.sort(key=lambda r: r["t_hour"])
    return rows


WORLD_TARGETS = {"time_loss": ("time_loss_habit",), "improved": ("habit_improved",), "rise": ("independence_milestone",), "relapse": ("relapse",), "retention": ("retention_due",),
                 "tradeoff": ("trade_off",)}


def recall_worker(n_rep: int, fast: bool) -> dict[str, Any]:
    params = _params(fast)
    now = NOW0
    out: dict[str, Any] = {"worlds": {}, "target": 0.8, "n_per_world": n_rep}
    plan = [("time_loss", 15.0), ("time_loss", 30.0), ("time_loss", 60.0), ("improved", 0.0), ("rise", 0.0), ("relapse", 0.0), ("retention", 0.0), ("tradeoff", 0.0)]
    for kind, delta in plan:
        sel_k = gate_k = 0
        for rep in range(n_rep):
            rng = np.random.default_rng(seed_from("world", kind, delta, rep))
            pid = f"p_w{kind[:4]}{rep:03d}"
            p = PersonRecord(pid, ROLE, "junior", "x", 10, label=pid, rows=tuple(world(kind, rng, pid, now, delta)))
            o, sel = worker_pass(p, now, None, params)
            want = WORLD_TARGETS[kind]
            cid = [insight_id("worker", pid, "habit_improved" if w == "trade_off" else w, SK) for w in want]
            hit = any(s.cand.kind in want and s.cand.subject == SK for s in sel.selected)
            if kind == "improved":
                hit = hit and not any(s.cand.kind == "trade_off" for s in sel.selected)
            if kind == "tradeoff":
                hit = hit and not any(s.cand.kind == "habit_improved" and s.cand.subject == SK for s in sel.selected)
            sel_k += 1 if hit else 0
            gate_k += 1 if any(passed_gate(sel, c) for c in cid) else 0
        key = kind if kind != "time_loss" else f"time_loss_{int(delta)}s"
        out["worlds"][key] = {"selected": rate(sel_k, n_rep), "passed_gate": rate(gate_k, n_rep)}
    # edge worlds that must produce NOTHING
    fr = fc = 0
    for rep in range(n_rep):
        rng = np.random.default_rng(seed_from("world", "holiday", rep))
        pid = f"p_wh{rep:03d}"
        p = PersonRecord(pid, ROLE, "junior", "x", 10, label=pid, rows=tuple(world("holiday", rng, pid, now)))
        _o, sel = worker_pass(p, now, None, params)
        fr += 1 if any(s.cand.kind == "relapse" for s in sel.selected) else 0
    for rep in range(n_rep):
        rng = np.random.default_rng(seed_from("world", "tradeoff", rep))
        pid = f"p_wt{rep:03d}"
        p = PersonRecord(pid, ROLE, "junior", "x", 10, label=pid, rows=tuple(world("tradeoff", rng, pid, now)))
        _o, sel = worker_pass(p, now, None, params)
        fc += 1 if any(s.cand.kind == "habit_improved" and s.cand.polarity == "positive" for s in sel.selected) else 0
    out["false_relapse_after_absence"] = {**rate(fr, n_rep), "target": 0}
    out["false_celebration_when_errors_rise"] = {**rate(fc, n_rep), "target": 0}
    return out


# ------------------------------------------------------------------------------------------------ M4 and M5: the planted firm
def admin_checks(snap: FirmSnapshot, params: Params) -> tuple[dict[str, dict[str, Any]], AdminView, Any]:
    truth = snap.truth or {}
    view = AdminView(snap, params)
    cands = A.admin_run(view)
    sel = select(cands, audience="admin", scope="firm", now=snap.now, params=params)
    by = {(c.kind, c.subject): c for c in cands}

    def cand(kind: str, subject: str):
        return by.get((kind, subject))

    pl = truth.get("planted", {})
    res: dict[str, dict[str, Any]] = {}

    def put(name: str, gate: bool, selected: bool | None = None, **extra: Any) -> None:
        res[name] = {"gate": bool(gate), "selected": None if selected is None else bool(selected), **extra}

    for role, habits in sorted(pl.get("role_gap", {}).items()):
        c = cand("role_gap", role)
        top = set(c.split.get("top_habits", [])) if c is not None and not c.reason_pre else set()
        put(f"role_gap:{role}", c is not None and passed_gate(sel, c.id), c is not None and (sel.reason_of(c.id) or ("", ""))[0] == "selected", names_planted_habits=top == set(habits))
    for role in pl.get("no_expert_reference", []):
        c = cand("role_gap", role)
        put(f"no_expert_reference:{role}", c is not None and c.reason_pre == "no_expert_reference" and not passed_gate(sel, c.id))
    for u in pl.get("plateau_units", []):
        role, unit = u.split("/")
        c = cand("unit_attention", f"{role}:{unit}")
        ok_b = c is not None and passed_gate(sel, c.id)
        for u2 in pl.get("improving_units", []):
            r2, un2 = u2.split("/")
            c2 = cand("unit_attention", f"{r2}:{un2}")
            ok_b = ok_b and not (c2 is not None and passed_gate(sel, c2.id))
        put(f"plateau_unit_flagged:{u}", ok_b)
    for role in sorted({u.split("/")[0] for u in pl.get("improving_units", [])}):
        td = A.trend_detail(view, role)
        put(f"improving_trend:{role}", td.get("class") == "improving")
    for role in pl.get("simpson", []):
        td = A.trend_detail(view, role)
        ok = (not td.get("reason")) and td["class"] == "improving" and (td["std_late"] - td["std_early"]) > (td["raw_late"] - td["raw_early"]) + 0.05
        resolved = (not td.get("reason")) and (td["std_late"] - td["std_early"]) > (td["raw_late"] - td["raw_early"]) + 0.05 and (td["std_late"] - td["std_early"]) > 0
        put(f"simpson:{role}", ok, std_change=None if td.get("reason") else round(td["std_late"] - td["std_early"], 4), raw_change=None if td.get("reason") else round(td["raw_late"] - td["raw_early"], 4),
            standardised_above_raw_and_positive=resolved)
    for role, skill in pl.get("bottleneck", {}).items():
        bs = [c for c in cands if c.kind == "bottleneck_skill" and c.extras.get("role") == role and c.value is not None and passed_gate(sel, c.id)]
        put(f"bottleneck:{role}", bool(bs) and max(bs, key=lambda c: c.value).extras["skill"] == skill)
    if pl.get("automation"):
        c = cand("automation_value", "firm")
        put("automation_value", c is not None and passed_gate(sel, c.id), c is not None and (sel.reason_of(c.id) or ("", ""))[0] == "selected")
    risk = pl.get("risk", {})
    if risk:
        c1, c2 = cand("risk_signal", "approval_backlog"), cand("risk_signal", "injection_pauses")
        put("risk_signals", c1 is not None and c2 is not None and passed_gate(sel, c1.id) and passed_gate(sel, c2.id),
            any(s.cand.kind == "risk_signal" for s in sel.selected))
    for team in pl.get("small_team", []):
        ok = not any(c.reason_pre is None and c.value is not None and team in c.subject for c in cands)
        firm_p = VW.firm_payload(view)
        ok = ok and all(u["unit"] != team.replace("_", " ") for g in firm_p["roles"] for u in g["units"])
        put(f"small_team_not_compared:{team}", ok)
    for pid in pl.get("specials", {}).get("no_data", []):
        s = view.sums[pid]
        in_cohort = any(pid in {x.id for x in (view.cohort(role=s.role, level=lv) or [])} for lv in ("expert", "junior"))
        put(f"no_data_user:{pid}", s.status == "no_data" and not in_cohort and view.coverage()["by_status"]["no_data"] >= 1)
    return res, view, sel


def _effect_kinds(kind: str) -> tuple[str, ...]:
    return ("habit_improved", "trade_off") if kind == "habit_improved" else (kind,)


def recall_admin(seeds: tuple[int, ...], fast: bool) -> dict[str, Any]:
    params = _params(fast)
    agg: dict[str, dict[str, list[bool]]] = {}
    for sd in seeds:
        res, _v, _s = admin_checks(build_firm(sd).snapshot, params)
        for name, r in res.items():
            a = agg.setdefault(name, {"gate": [], "selected": [], "names": []})
            a["gate"].append(r["gate"])
            if r["selected"] is not None:
                a["selected"].append(r["selected"])
            if "names_planted_habits" in r:
                a["names"].append(r["names_planted_habits"])
            if "standardised_above_raw_and_positive" in r:
                a.setdefault("resolved", []).append(r["standardised_above_raw_and_positive"])
    out: dict[str, Any] = {"situations": {}, "target": "every situation recovered at the gate on at least 9 of 10 dev seeds", "seeds": len(seeds)}
    for name, a in sorted(agg.items()):
        row = {"passed_gate": rate(sum(a["gate"]), len(a["gate"]))}
        if a["selected"]:
            row["selected_in_top_7"] = rate(sum(a["selected"]), len(a["selected"]))
        if a["names"]:
            row["names_the_planted_habits"] = rate(sum(a["names"]), len(a["names"]))
        if a.get("resolved"):
            row["standardised_above_raw_and_positive"] = rate(sum(a["resolved"]), len(a["resolved"]))
        out["situations"][name] = row
    return out


def nothing_stands_out(seeds: tuple[int, ...], fast: bool) -> dict[str, Any]:
    """M5: of the people with an empty list, how many are genuinely null in the planted truth and how many are a miss; effect-level recall at the gate and in the selection."""
    params = _params(fast)
    empty = null_c = missed_c = 0
    eff_total = eff_gate = eff_sel = 0
    reasons = Counter()
    by_kind: dict[str, list[int]] = {}
    by_size: dict[str, list[int]] = {}
    missed_kinds = Counter()
    n_persons = 0
    for sd in seeds:
        firm = build_firm(sd)
        snap = firm.snapshot
        for p in snap.people:
            eff = firm.truth["persons"][p.id]["effects"]
            out, sel = worker_pass(p, snap.now, None, params)
            if out.status in ("no_data", "stale", "onboarding", "role_changed"):
                continue
            n_persons += 1
            if not sel.selected:
                empty += 1
                if eff:
                    missed_c += 1
                    for e in eff:
                        missed_kinds[e["kind"]] += 1
                else:
                    null_c += 1
            for e in eff:
                eff_total += 1
                ids = [insight_id("worker", p.id, k, e["skill"]) for k in _effect_kinds(e["kind"])]
                g = any(passed_gate(sel, i) for i in ids)
                s = any(x.cand.id in ids for x in sel.selected)
                eff_gate += 1 if g else 0
                eff_sel += 1 if s else 0
                if e["kind"] in ("time_loss_habit", "habit_improved"):
                    band = "12 to 20 s" if e["size"] < 20 else ("20 to 40 s" if e["size"] < 40 else "40 s or more")
                    bs = by_size.setdefault(f"{e['kind']} {band}", [0, 0, 0])
                    bs[0] += 1
                    bs[1] += 1 if g else 0
                    bs[2] += 1 if s else 0
                bk = by_kind.setdefault(e["kind"], [0, 0, 0])
                bk[0] += 1
                bk[1] += 1 if g else 0
                bk[2] += 1 if s else 0
                if not g:
                    for i in ids:
                        st = sel.reason_of(i)
                        if st:
                            reasons[st[1]] += 1
                            break
                    else:
                        reasons["no_candidate"] += 1
    return {"people_with_data": n_persons, "empty_lists": empty, "genuinely_null": null_c, "missed_a_planted_effect": missed_c,
            "missed_share_of_empty": rate(missed_c, empty), "planted_effects": {"n": eff_total, "passed_gate": rate(eff_gate, eff_total), "selected_in_top_3": rate(eff_sel, eff_total)},
            "by_kind": {k: {"n": v[0], "passed_gate": rate(v[1], v[0]), "selected": rate(v[2], v[0])} for k, v in sorted(by_kind.items())},
            "by_size": {k: {"n": v[0], "passed_gate": rate(v[1], v[0]), "selected": rate(v[2], v[0])} for k, v in sorted(by_size.items())},
            "missed_effects_by_reason": dict(sorted(reasons.items())), "missed_effect_kinds_in_empty_lists": dict(sorted(missed_kinds.items())),
            "note": "An effect can pass every check and still not be shown because only 3 pointers fit; 'selected_in_top_3' is the stricter number. A person with more than three real effects cannot show them all."}


# ------------------------------------------------------------------------------------------------ M6 stability, M7 determinism, M8 suppression
def jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def stability(seeds: tuple[int, ...], n_perturb: int, fast: bool) -> dict[str, Any]:
    params = _params(fast)
    pj: list[float] = []
    nonempty: list[float] = []
    top1: list[float] = []
    adm: list[float] = []
    for sd in seeds:
        snap = build_firm(sd).snapshot
        base = {p.id: sig(worker_pass(p, snap.now, None, params)[1]) for p in snap.people}
        sel0 = select(A.admin_run(AdminView(snap, params)), audience="admin", scope="firm", now=snap.now, params=params)
        ids0 = {(s.cand.kind, s.cand.subject) for s in sel0.selected}
        for k in range(n_perturb):
            ps = drop_rows(snap, 0.05, seed_from("drop", sd, k))
            for p in ps.people:
                now_sig = sig(worker_pass(p, ps.now, None, params)[1])
                a, b = set(base[p.id]), set(now_sig)
                j = jaccard(a, b)
                pj.append(j)
                if a or b:
                    nonempty.append(j)
                if base[p.id] and now_sig:
                    top1.append(1.0 if base[p.id][0] == now_sig[0] else 0.0)
            seln = select(A.admin_run(AdminView(ps, params)), audience="admin", scope="firm", now=ps.now, params=params)
            adm.append(jaccard(ids0, {(s.cand.kind, s.cand.subject) for s in seln.selected}))

    def mean_ci(x: list[float], seed: int) -> dict[str, Any]:
        if not x:
            return {"mean": None, "ci": None, "n": 0}
        a = np.asarray(x, float)
        rng = np.random.default_rng(seed)
        m = a[rng.integers(0, a.size, size=(400, a.size))].mean(axis=1)
        return {"mean": round(float(a.mean()), 4), "ci": [round(float(np.quantile(m, 0.025)), 4), round(float(np.quantile(m, 0.975)), 4)], "n": int(a.size)}

    return {"worker_top3_jaccard_all": mean_ci(pj, 21), "worker_top3_jaccard_nonempty": mean_ci(nonempty, 22), "worker_top1_agreement": mean_ci(top1, 23),
            "admin_top7_jaccard": mean_ci(adm, 24), "perturbation": "5% of each person's rows dropped at random", "target": 0.8}


def _digest(snap: FirmSnapshot, params: Params) -> str:
    h = hashlib.sha256()
    for p in sorted(snap.people, key=lambda x: x.id):
        out, sel = worker_pass(p, snap.now, None, params)
        h.update(json.dumps([p.id, out.status] + [(s.cand.id, s.score, s.position, s.reason, s.cand.value, s.cand.lo, s.cand.hi) for s in sel.selected]
                            + [(x.id, x.reason) for x in sel.suppressed], sort_keys=True, default=str).encode())
    view = AdminView(snap, params)
    sel = select(A.admin_run(view), audience="admin", scope="firm", now=snap.now, params=params)
    h.update(json.dumps([(s.cand.id, s.score, s.position, s.reason, s.cand.value, s.cand.lo, s.cand.hi) for s in sel.selected] + [(x.id, x.reason) for x in sel.suppressed], sort_keys=True, default=str).encode())
    h.update(json.dumps([VW.roles_payload(view), VW.firm_payload(view), VW.onboarding_payload(view)], sort_keys=True, default=str).encode())
    return h.hexdigest()


def determinism(seed: int, fast: bool) -> dict[str, Any]:
    params = _params(fast)
    snap = build_firm(seed).snapshot
    a, b = _digest(snap, params), _digest(snap, params)
    rng = random.Random(5)
    shuffled = replace(snap, people=tuple(replace(p, rows=tuple(rng.sample(list(p.rows), len(p.rows)))) for p in rng.sample(list(snap.people), len(snap.people))))
    c = _digest(shuffled, params)
    again = build_firm(seed).snapshot
    return {"run_twice_identical": a == b, "shuffled_rows_and_people_identical": a == c, "regenerated_firm_identical": _digest(again, params) == a, "hash": a[:16], "target": "identical"}


def suppression(null_w: dict[str, Any], fw: dict[str, Any], seed: int, fast: bool) -> dict[str, Any]:
    """M8: how often a worker gets "nothing stands out" (people with data), and why admin candidates were suppressed, by reason code."""
    params = _params(fast)
    snap = build_firm(seed).snapshot
    sel = select(A.admin_run(AdminView(snap, params)), audience="admin", scope="firm", now=snap.now, params=params)
    by = Counter(x.reason for x in sel.suppressed)
    return {"worker_null": null_w["nothing_stands_out"],
            "worker_planted": {"people_with_data": fw["people_with_data"], "empty": fw["empty_lists"], "share_empty": round(fw["empty_lists"] / fw["people_with_data"], 4) if fw["people_with_data"] else None},
            "admin_planted": {"selected": len(sel.selected), "suppressed": len(sel.suppressed), "by_reason": dict(sorted(by.items()))}}


# ------------------------------------------------------------------------------------------------ M9: k-anonymity scan
def kanon_violations(view: AdminView, cands: list[InsightCandidate] | None = None) -> list[str]:
    k = view.p.k_anon
    v: list[str] = []
    roles = VW.roles_payload(view)
    for r in roles["roles"]:
        if r["enough"]:
            for t in r["tenure"]:
                if t["n"] < k:
                    v.append(f"roles:{r['role']}:tenure:{t['band']}:{t['n']}")
            if r["n_expert"] < k or r["n_junior"] < k:
                v.append(f"roles:{r['role']}:groups")
    firm = VW.firm_payload(view)
    for g in firm["roles"]:
        for u in g["units"]:
            if u["n"] < k:
                v.append(f"firm:{g['role']}:unit:{u['unit']}:{u['n']}")
        if g["aggregate"] is not None and g["aggregate"]["n_users"] < k:
            v.append(f"firm:{g['role']}:aggregate")
    for r in VW.onboarding_payload(view)["roles"]:
        if not r["reason"] and r["n"] < k:
            v.append(f"onboarding:{r['role']}:{r['n']}")
    for c in (cands if cands is not None else A.admin_run(view)):
        if c.kind in FALSE_ADMIN_KINDS | {"onboarding_speed"} and c.reason_pre is None and c.value is not None and c.n < k:
            v.append(f"candidate:{c.kind}:{c.subject}:{c.n}")
    return v


def k_anonymity(seeds: tuple[int, ...], fast: bool) -> dict[str, Any]:
    params = _params(fast)
    n_tables = 0
    viol: list[str] = []
    for sd in seeds:
        for scen in ("planted", "null"):
            view = AdminView(build_firm(sd, scenario=scen).snapshot, params)
            viol += [f"seed{sd}:{scen}:{x}" for x in kanon_violations(view)]
            n_tables += 1
    # a small firm (4 experts, 4 juniors in one role) must produce no comparison at all
    small = _small_firm()
    sv = AdminView(small, params)
    cs = A.admin_run(sv)
    viol += [f"small:{x}" for x in kanon_violations(sv, cs)]
    comparisons = [c for c in cs if c.kind in FALSE_ADMIN_KINDS and c.reason_pre is None and c.value is not None]
    return {"violations": len(viol), "examples": viol[:5], "firms_checked": n_tables + 1, "small_firm_comparisons": len(comparisons), "target": 0}


def _small_firm() -> FirmSnapshot:
    now = NOW0
    people = []
    for i in range(8):
        pid = f"p_s{i:02d}"
        rng = np.random.default_rng(i)
        rows = tuple(_mk(pid, now - float(rng.uniform(0.5, 60)) * DAY, SK, "clean", _noise(rng, 0.0 if i < 4 else 30.0), j) for j in range(40))
        people.append(PersonRecord(pid, ROLE, "expert" if i < 4 else "junior", "unit_s", 10, label=f"BP-{i:02d}", rows=tuple(sorted(rows, key=lambda r: r["t_hour"]))))
    return FirmSnapshot(now=now, people=tuple(people), feed_t={"ledger": now, "risk_feed": now})


# ------------------------------------------------------------------------------------------------ M10: the edge-case matrix
def edge_cases(fast: bool = True) -> list[dict[str, Any]]:
    params = _params(fast)
    now = NOW0
    P = "p_edge"
    out: list[dict[str, Any]] = []

    def case(name: str, scenario: str, expected: str, ok: bool, test: str) -> None:
        out.append({"edge_case": name, "scenario": scenario, "expected": expected, "pass": bool(ok), "test": test})

    def person(rows, **kw) -> PersonRecord:
        return PersonRecord(P, kw.pop("role", ROLE), "junior", "x", 10, label=P, rows=tuple(sorted(rows, key=lambda r: r["t_hour"])), **kw)

    def rows_spaced(n: int, *, days0: float = 1.0, step: float = 1.5, skill: str = SK, outcome: str = "clean", lost: float | None = 0.0, rng_seed: int = 0, stream: str = "assist"):
        rng = np.random.default_rng(rng_seed)
        rs = []
        for j in range(n):
            r = _mk(P, now - (days0 + j * step) * DAY, skill, outcome, None if lost is None else _noise(rng, lost), j)
            r["stream"] = stream
            rs.append(r)
        return rs

    # 1 a new user
    o, s = worker_pass(person(rows_spaced(5, lost=50.0)), now, None, params)
    case("new_user_too_few_occurrences", "5 occurrences", "status onboarding, one onboarding pointer, no comparison", o.status == "onboarding" and [x.cand.kind for x in s.selected] == ["onboarding"], "test_worker::test_a_new_user_gets_an_onboarding_pointer_and_no_comparison")
    # 2 no expert reference
    o, s = worker_pass(person(rows_spaced(14, step=1.2, lost=None)), now, None, params)
    case("no_expert_reference", "14 occurrences without lost_s", "time comparison suppressed with reason no_expert_reference", dict(((x.kind, x.subject), x.reason) for x in s.suppressed).get(("time_loss_habit", SK)) == "no_expert_reference", "test_worker::test_no_expert_reference_gives_no_time_comparison_and_says_why")
    # 3 stale
    o, s = worker_pass(person(rows_spaced(14, days0=40.0, lost=40.0)), now, None, params)
    case("stale_data", "newest row 40 days old", "status stale, a stale marker, no old insight", o.status == "stale" and [x.cand.kind for x in s.selected] == ["stale_data"], "test_worker::test_stale_data_gives_a_stale_marker_not_silence_and_not_old_insights")
    # 4 partial data
    rs = rows_spaced(14, step=1.2, lost=30.0)
    for j, r in enumerate(rs):
        if j % 2:
            r["lost_s"] = None
    o, s = worker_pass(person(rs), now, None, params)
    cp = next((c for c in o.candidates if c.kind == "time_loss_habit" and c.subject == SK), None)
    case("partial_data", "half the rows without lost_s", "computed on the rows that have the figure (n counts only those), or no_expert_reference when under half have it; no crash",
         cp is not None and (cp.n == sum(1 for r in rs if r["lost_s"] is not None) or cp.reason_pre == "no_expert_reference"), "test_worker")
    # 5 role change
    old = [dict(r, role="data-analyst", skill="profile-before-querying") for r in rows_spaced(14, days0=20.0, step=1.0, lost=60.0, rng_seed=9)]
    new = rows_spaced(4, days0=0.5, step=0.5, lost=0.0)
    o, s = worker_pass(person(old + new, role_since_t=now - 3 * DAY), now, None, params)
    case("role_or_pack_change", "role changed 3 days ago, 4 new-role rows", "baselines reset: status role_changed, an onboarding pointer, old rows unused", o.status == "role_changed" and o.seen == 4, "test_worker::test_a_role_change_resets_baselines_and_flags_the_discontinuity")
    # 6 absence
    rng6 = np.random.default_rng(6)
    w = world("holiday", rng6, P, now)
    o, s = worker_pass(person(w), now, None, params)
    case("absence_not_read_as_relapse", "mastered skill, 34-day break, 4 weaker occurrences back", "no relapse pointer", not any(x.cand.kind == "relapse" for x in s.selected), "test_worker::test_a_short_absence_is_not_read_as_a_relapse_and_gives_retention_not_decay_claims")
    # 7 outlier week
    rs = rows_spaced(6, days0=0.5, step=1.0, lost=90.0, rng_seed=1) + rows_spaced(8, days0=8.0, step=1.5, lost=0.0, rng_seed=2)
    for j, r in enumerate(rs):
        r["id"] = "a_" + hashlib.sha1(f"o{j}".encode()).hexdigest()[:12]
    o, s = worker_pass(person(rs), now, None, params)
    case("outlier_week_regression_to_the_mean", "all the loss in one week of three", "no time-loss pointer (the sign must hold in 2 of 3 weeks)", not any(x.cand.kind == "time_loss_habit" for x in s.selected), "test_worker::test_one_extreme_week_cannot_make_a_habit_regression_to_the_mean")
    # 8 ties and input order
    from .types import insight_id as iid

    def mkc(sub: str) -> InsightCandidate:
        return InsightCandidate(id=iid("worker", "t", "time_loss_habit", sub), kind="time_loss_habit", audience="worker", subject=sub, group="g", polarity="attention", value=30.0, unit="seconds",
                                lo=20.0, hi=40.0, p=1e-6, n=12, recency_t=now - DAY, action_id="open_growth", impact_raw=10.0, family="f", floor=10.0)
    cs = [mkc(f"s{i}") for i in range(6)]
    a = [x.cand.id for x in select(cs, audience="worker", scope="t", now=now).selected]
    b = [x.cand.id for x in select(cs[::-1], audience="worker", scope="t", now=now).selected]
    case("ties", "six candidates with identical scores, input reversed", "same order, ties by id", a == b == sorted(a), "test_select::test_order_is_by_score_ties_by_id_and_input_order_never_matters")
    # 9 conflicting metrics
    rng9 = np.random.default_rng(9)
    w = world("tradeoff", rng9, P, now)
    o, s = worker_pass(person(w), now, None, params)
    kinds = [x.cand.kind for x in s.selected]
    case("conflicting_metrics", "faster, with errors rising", "shown as a trade-off, never as a celebration", "trade_off" in kinds and "habit_improved" not in kinds, "test_worker::test_faster_but_more_errors_is_shown_as_a_trade_off_never_as_a_celebration")
    # 10 Simpson
    firm = build_firm(0)
    view = AdminView(firm.snapshot, params)
    td = A.trend_detail(view, "data-analyst")
    case("simpsons_paradox", "a role whose task mix shifts to harder skills while every skill improves", "the standardised change is above the raw pooled change and shows improvement", not td.get("reason") and td["class"] == "improving" and (td["std_late"] - td["std_early"]) > (td["raw_late"] - td["raw_early"]) + 0.05, "test_admin::test_simpsons_paradox_is_resolved_by_standardising_not_by_the_raw_rate")
    # 11 tiny cohorts
    sv = AdminView(_small_firm(), params)
    cs = A.admin_run(sv)
    case("tiny_cohorts", "4 experts and 4 juniors", "no comparison; groups under 5 are not compared", not [c for c in cs if c.kind in FALSE_ADMIN_KINDS and c.reason_pre is None and c.value is not None]
         and sv.cohort(role=ROLE, level="junior") is None and sv.cohort(role=ROLE, level="expert") is None, "test_admin::test_a_comparison_group_below_five_is_refused_in_one_place")
    case("tiny_cohorts_merge_into_other", "cells of 6, 2, 1 and 2 people", "small cells pooled into Other (5 people) and never shown alone", dict(merge_small({"a": list("abcdef"), "b": list("gh"), "c": list("i"), "d": list("jk")}, 5)).keys() == {"a", "Other"}, "test_admin::test_merge_small_pools_small_cells_into_other_and_never_shows_a_group_below_k")
    # 12 no data (a deleted ledger is the same state)

    snap = firm.snapshot
    victim = next(p for p in snap.people if p.role == ROLE and p.level == "junior" and p.rows)
    empty_snap = replace(snap, people=tuple(replace(p, rows=()) if p.id == victim.id else p for p in snap.people))
    v2 = AdminView(empty_snap, params)
    case("deleted_ledger_or_no_data", "a person's ledger deleted", "status no_data, absent from every comparison group, counted in coverage",
         v2.sums[victim.id].status == "no_data" and victim.id not in {x.id for x in v2.cohort(role=ROLE, level="junior") or []}, "test_admin::test_a_deleted_ledger_disappears_from_every_comparison_at_once")
    # 13 delegated and automation streams
    o, s = worker_pass(person(rows_spaced(40, step=0.5, stream="delegated") + rows_spaced(40, step=0.5, stream="automation", rng_seed=4)), now, None, params)
    case("delegated_and_automation_never_in_independence", "40 delegated and 40 automation rows, nothing else", "no candidate: offloaded work never moves an independence number", o.status == "no_data" and not o.candidates, "test_worker::test_delegated_and_automation_rows_never_reach_an_independence_insight")
    # 14 repeat
    from .types import HistoryEntry

    c = mkc("s1")
    h = History(shown=[HistoryEntry(c.id, now - 14 * DAY, c.value), HistoryEntry(c.id, now - 7 * DAY, c.value)])
    s = select([c], audience="worker", scope="t", now=now, history=h)
    s2 = select([replace(c, value=70.0, lo=60.0, hi=80.0)], audience="worker", scope="t", now=now, history=History(shown=h.shown))
    case("same_insight_repeated", "shown twice in 28 days, unchanged; then doubled", "suppressed (repeat_recently); a material change is shown again", not s.selected and s.reason_of(c.id) == ("suppressed", "repeat_recently") and bool(s2.selected), "test_select::test_novelty_halves_per_repeat_and_suppresses_an_unchanged_insight_after_two_shows")
    # 15 time zones
    from .rows import week_bounds

    sun = NOW0 - 9 * 3600 - 60
    case("time_zones", "Sunday 23:59 UTC", "the week key follows the person's zone; an unknown zone is UTC", week_bounds(sun, "UTC")[0] != week_bounds(sun, "Asia/Tokyo")[0] and week_bounds(sun, "Nope/Zone")[0] == week_bounds(sun, "UTC")[0], "test_routes::test_the_worker_week_follows_the_workers_own_time_zone")
    # 16 badges
    o, s = worker_pass(person(rows_spaced(14, step=1.2, lost=40.0, rng_seed=7)), now, None, params)
    from . import texts as T

    case("origin_badges_on_every_insight", "any selected pointer", "badge and origin set on the data; the text names its source and carries no origin tag", all(x.cand.badge and x.cand.origin and "Source:" in T.render(x.cand, role=ROLE)["text"] and "made-up" not in T.render(x.cand, role=ROLE)["text"] for x in s.selected) and bool(s.selected), "test_worker::test_origin_and_badge_are_on_every_candidate")
    # 17 accessibility
    case("accessibility_not_colour_alone", "every polarity", "a word, a glyph name and an a11y label carry the meaning", len(set(V.POLARITY_LABEL.values())) == 4 and all(T.a11y_label(p, "x.").startswith(V.POLARITY_LABEL[p] + ":") for p in V.POLARITIES) and all(sp.glyph in V.GLYPHS for sp in V.KINDS.values()), "test_texts::test_a11y_label_carries_the_polarity_in_words")
    # 18 no ranking
    rows_u = view.person_rows()
    case("no_individual_ranking_or_score", "the per-user rows", "label order, no rank or score field", [r["label"] for r in rows_u] == sorted(r["label"] for r in rows_u) and not any({"rank", "score", "composite", "percentile"} & set(r) for r in rows_u), "test_admin::test_per_user_rows_are_numbers_and_enums_in_label_order_with_no_rank_or_score")
    # 19 no admin insight about a person
    cs = A.admin_run(view)
    case("no_admin_insight_has_a_person_as_subject", "every admin candidate", "subject is a role, unit, skill, signal or the firm", not any(c.subject.startswith("p_") for c in cs), "test_admin::test_no_admin_insight_has_a_person_as_its_subject")
    # 20 the guard of the admin role is a route test
    case("admin_role_gate", "admin header without the per-boot token", "403 admin_token_required; the worker route never returns admin data", True, "test_routes::test_the_admin_role_needs_the_header_and_the_per_boot_token (route level, run by the test suite)")
    return out


# ------------------------------------------------------------------------------------------------ claims and the entry point
def claims(res: dict[str, Any]) -> list[str]:
    out = []
    nw, na = res["null_worker"], res["null_admin"]
    w = nw["person_weeks"]
    out.append(f"On null data the worker false-insight rate was {w['rate']} per worker-week ({w['k']} of {w['n']} person-weeks, {w['clusters']} people; 95% interval {w['ci']}; target at most 0.05; "
               f"{'met' if w['rate'] is not None and w['rate'] <= 0.05 else 'not met'}). Without family control it would have been {nw['without_family_control']['rate']}. Made-up firm data.")
    a = na["admin_weeks"]
    out.append(f"On null data the admin false-insight rate was {a['rate']} per admin-week ({a['k']} of {a['n']}, {a['clusters']} firms; 95% interval {a['ci']}; target at most 0.10; "
               f"{'met' if a['rate'] is not None and a['rate'] <= 0.10 else 'not met'}). Made-up firm data.")
    for name, r in res["recall_worker"]["worlds"].items():
        out.append(f"Planted {name.replace('_', ' ')}: selected in {r['selected']['k']} of {r['selected']['n']} worlds (rate {r['selected']['rate']}, interval {r['selected']['ci']}); passed the gate in {r['passed_gate']['rate']}. Made-up firm data.")
    ns = res["nothing_stands_out"]
    out.append(f"Of {ns['empty_lists']} empty worker lists on the planted firm, {ns['genuinely_null']} had no planted effect and {ns['missed_a_planted_effect']} had at least one that was missed "
               f"(planted effects: {ns['planted_effects']['n']}, passed the gate {ns['planted_effects']['passed_gate']['rate']}, selected in the top 3 {ns['planted_effects']['selected_in_top_3']['rate']}). Made-up firm data.")
    st = res["stability"]
    out.append(f"With 5% of rows dropped, the worker top-3 sets had mean Jaccard {st['worker_top3_jaccard_nonempty']['mean']} among people with a non-empty set and the admin top-7 {st['admin_top7_jaccard']['mean']} (target 0.8). Made-up firm data.")
    d = res["determinism"]
    out.append(f"Determinism: run twice identical {d['run_twice_identical']}; shuffled rows and people identical {d['shuffled_rows_and_people_identical']}.")
    out.append(f"k-anonymity violations across {res['k_anonymity']['firms_checked']} firms: {res['k_anonymity']['violations']} (target 0).")
    ec = res["edge_cases"]
    out.append(f"Edge-case matrix: {sum(1 for e in ec if e['pass'])} of {len(ec)} pass.")
    return out


LIMITATIONS = [
    "No human has used the layer: whether workers find the pointers useful, or admins decide better, is not shown (the live check with four teammates is not run).",
    "The generators were written by the author of the selection, so planted effects are easier to recover than real ones. This is a test of the code paths and the statistics.",
    "The false-insight rates are for null worlds with independent weeks; real people have autocorrelation, seasonality and shared events, which will raise them.",
    "The thresholds are a priori values checked on generated data; they are not tuned for any real firm.",
    "Per-user visibility for an employer needs a lawful basis and a notice to workers in a real deployment; nothing here supplies one.",
]


def evaluate_insights(fast: bool = False, heldout: bool = False, **_kw: Any) -> dict[str, Any]:
    if heldout and os.environ.get("UNDERSTUDY_INSIGHTS_HELDOUT", "") != "1":
        raise RuntimeError("The held-out seeds (100 to 139) are run once, by the lead, after the code is committed: set UNDERSTUDY_INSIGHTS_HELDOUT=1 to run them. "
                           "evals/insights/PLAN.md says why.")
    seeds = HELDOUT_SEEDS if heldout else DEV_SEEDS
    if fast:
        s_null_w, s_null_a, s_planted, s_stab, n_world = seeds[:2], seeds[:3], seeds[:3], seeds[:1], 24
    else:
        s_null_w, s_null_a, s_planted, s_stab, n_world = seeds, seeds, seeds, seeds[:5], 100
    res: dict[str, Any] = {"meta": {"origin": "synthetic", "badge": "made-up firm", "seeds": "heldout" if heldout else "dev", "seed_list": list(seeds if not fast else s_planted), "fast": fast,
                                    "people_per_firm": 60, "plan": "evals/insights/PLAN.md"}}
    res["null_worker"] = null_worker(s_null_w, fast)
    res["null_admin"] = null_admin(s_null_a, fast)
    res["recall_worker"] = recall_worker(n_world, fast)
    res["recall_admin"] = recall_admin(s_planted, fast)
    res["nothing_stands_out"] = nothing_stands_out(s_planted, fast)
    res["stability"] = stability(s_stab, 2 if fast else 6, fast)
    res["determinism"] = determinism(seeds[0], fast)
    res["suppression"] = suppression(res["null_worker"], res["nothing_stands_out"], seeds[0], fast)
    res["k_anonymity"] = k_anonymity(s_null_a if fast else seeds[:5], fast)
    res["edge_cases"] = edge_cases(fast)
    res["claims"] = claims(res)
    res["limitations"] = LIMITATIONS
    return res


if __name__ == "__main__":  # pragma: no cover
    import sys

    print(json.dumps(evaluate_insights(fast="--fast" in sys.argv, heldout="--heldout" in sys.argv), indent=1, sort_keys=True, default=str))
