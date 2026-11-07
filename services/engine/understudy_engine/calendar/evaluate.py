"""Evaluation of the calendar layer (NFR-11): what it recovers from calendars with planted structure, how well, and what it does not show.

Everything here is on **synthetic** calendars (4 personas, 8 experts, 16 novices, 3 weeks each) whose structure was planted by a
generator that does not use the feature code. Nothing is validated on real people, and the expert side is synthetic too (generated
from the role template), so agreement with it is by construction.

Sections:

* ``read_path``: do ICS text, RRULE expansion, zones and the decoys (cancelled, declined, free, tentative, all-day) give the features
  the generator's own interval arithmetic gives? (match rates per feature, ICS and JSON exports);
* ``pattern_recovery``: precision and recall of each planted problem, per day or per person-week, against the planted *intent*, with
  95% intervals from a cluster bootstrap by person (accidental near-misses count as false positives);
* ``week_gap``: the week-ribbon distance to the nearest expert week for planted, clean and expert weeks (the expert-against-expert placebo
  should be near zero), and whether the feature gap flags the planted feature in the planted direction;
* ``suggestions``: catalogue coverage, and per-template precision and recall against the planted cause, expert false-alarm rate;
* ``leak_canary``: every canary-seeded name, address, title, location and id searched for in every API payload, suggestion, real-check
  result and captured outbound request;
* ``limitations``.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from statistics import fmean
from typing import Any, Iterable

from . import canary_run, service
from . import suggest as sug
from .expert import gap_rows
from .model import week_label
from .store import CalendarStore, default_store
from .synth import PROBLEMS

LEVEL = 0.95
EXACT = ("focus_blocks_60", "focus_blocks_90", "longest_focus_min", "back_to_back_runs", "fragmented_days", "external_unbuffered_n", "review_slots",
         "batch_windows", "meetings_n", "days_worked")
HOURS = ("meeting_h", "offscreen_h", "recurring_in_peak_h", "outside_hours_h")

# Which planted problems should produce each template (the planted cause of each suggestion). The generator builds ``fragmented_days`` and
# ``no_focus_blocks`` by replacing whole days with meetings, which also removes that day's batch window and review slot and adds meeting
# hours; chains and peak-window series add meeting hours too. Those side effects are part of how the weeks are built, so they are listed as
# causes here (the widening for the meeting-load template was made after a first run showed over-cap meeting loads in weeks with chains and
# peak-window series; the first run's precision for it was 0.27).
TEMPLATE_CAUSES: dict[str, tuple[str, ...]] = {
    "focus_shortfall": ("no_focus_blocks", "fragmented_days"),           # protect_focus_block (one-off) or auto_hold_scheduling (repeating)
    "batch_similar_work": ("fragmented_days", "no_focus_blocks"),
    "add_review_slot": ("no_review_slot", "no_focus_blocks", "fragmented_days"),
    "offcomputer_break": ("no_breaks",),
    "reduce_back_to_back": ("back_to_back_runs",),
    "move_recurring_out_of_peak": ("recurring_in_peak",),
    "buffer_before_external": ("unbuffered_external",),
    "trim_meeting_load": ("no_focus_blocks", "fragmented_days", "back_to_back_runs", "recurring_in_peak"),
    "protect_working_edges": ("late_meetings",),
}
LOGICAL = {"focus_shortfall": ("protect_focus_block", "auto_hold_scheduling")}
PRIMARY_FEATURE = {"fragmented_days": ("fragmented_days", +1), "no_focus_blocks": ("focus_blocks_90", -1), "back_to_back_runs": ("back_to_back_runs", +1),
                   "recurring_in_peak": ("recurring_in_peak_h", +1), "no_review_slot": ("review_slots", -1), "no_breaks": ("offscreen_h", -1),
                   "unbuffered_external": ("external_unbuffered_n", +1), "late_meetings": ("outside_hours_h", +1)}


def week_problems(t: dict[str, Any]) -> set[str]:
    """The planted problems actually present in one person-week (a problem assigned to a person may find no free day to land on in a week)."""
    out = set()
    if t["fragmented_days"]:
        out.add("fragmented_days")
    if t["no_focus_blocks"]:
        out.add("no_focus_blocks")
    if t["back_to_back_days"]:
        out.add("back_to_back_runs")
    if t["recurring_in_peak_h_planted"] > 0:
        out.add("recurring_in_peak")
    if t["no_review_slot"]:
        out.add("no_review_slot")
    if t["no_breaks"]:
        out.add("no_breaks")
    if t["unbuffered_external_days"]:
        out.add("unbuffered_external")
    if t["late_days"]:
        out.add("late_meetings")
    return out


# ---------------------------------------------------------------------------------------------------- statistics
def _pct(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[int(round(q * (len(sorted_vals) - 1)))]


def _prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None]:
    return (tp / (tp + fp) if tp + fp else None), (tp / (tp + fn) if tp + fn else None)


def cluster_prf(units: dict[str, list[tuple[bool, bool]]], n_boot: int, seed: int) -> dict[str, Any]:
    """Precision and recall of (truth, predicted) pairs grouped by person, with a cluster bootstrap over people."""
    def counts(groups: Iterable[list[tuple[bool, bool]]]) -> tuple[int, int, int, int]:
        tp = fp = fn = tn = 0
        for g in groups:
            for t, p in g:
                tp += t and p
                fp += (not t) and p
                fn += t and (not p)
                tn += (not t) and (not p)
        return tp, fp, fn, tn

    people = sorted(units)
    tp, fp, fn, tn = counts(units[p] for p in people)
    prec, rec = _prf(tp, fp, fn)
    rng = random.Random(seed)
    ps: list[float] = []
    rs: list[float] = []
    for _ in range(n_boot):
        b = counts(units[rng.choice(people)] for _ in people)
        pb, rb = _prf(b[0], b[1], b[2])
        if pb is not None:
            ps.append(pb)
        if rb is not None:
            rs.append(rb)
    ps.sort()
    rs.sort()
    ci = lambda v: [round(_pct(v, 0.025), 3), round(_pct(v, 0.975), 3)] if len(v) >= 20 else None
    return {"n": tp + fp + fn + tn, "positives": tp + fn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": None if prec is None else round(prec, 3), "precision_ci": ci(ps),
            "recall": None if rec is None else round(rec, 3), "recall_ci": ci(rs)}


def cluster_mean_ci(values: dict[str, list[float]], n_boot: int, seed: int) -> dict[str, Any]:
    """Mean of per-person means with a cluster bootstrap interval."""
    means = {p: fmean(v) for p, v in values.items() if v}
    if not means:
        return {"mean": None, "ci": None, "n_people": 0}
    people = sorted(means)
    rng = random.Random(seed)
    draws = sorted(fmean(means[rng.choice(people)] for _ in people) for _ in range(n_boot))
    return {"mean": round(fmean(means.values()), 4), "ci": [round(_pct(draws, 0.025), 4), round(_pct(draws, 0.975), 4)], "n_people": len(people)}


# ---------------------------------------------------------------------------------------------------- sections
def _meta(origin: str, n: int, n_unit: str, split: str | None, note: str | None) -> dict[str, Any]:
    return {"origin": origin, "n": n, "n_unit": n_unit, "split": split, "interval_level": LEVEL, "note": note,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def read_path(store: CalendarStore) -> dict[str, Any]:
    truth = store.truth()["people"]
    out: dict[str, Any] = {}
    for kind in ("ics", "json"):
        match: dict[str, int] = defaultdict(int)
        n = 0
        for p in store.people():
            pc = store.get(p, kind)
            for m in pc.weeks:
                f = pc.week(m).features
                c = truth[p]["weeks"][week_label(m)]["construction"]
                n += 1
                for k in EXACT:
                    match[k] += f[k] == c[k]
                for k in HOURS:
                    match[k] += abs(f[k] - c[k]) <= 0.06
                match["fragmentation"] += abs(f["fragmentation"] - c["fragmentation"]) <= 0.01
        out[kind] = {"person_weeks": n, "match_rate": {k: round(v / n, 4) for k, v in sorted(match.items())}}
    a = {p: store.get(p, "ics") for p in store.people()}
    b = {p: store.get(p, "json") for p in store.people()}
    out["ics_equals_json"] = all(sorted((x.start, x.end, x.kind, x.n_attendees) for x in a[p].blocks) == sorted((x.start, x.end, x.kind, x.n_attendees) for x in b[p].blocks)
                                 for p in a)
    out["decoys_ignored"] = {"cancelled": sum(pc.stats.cancelled for pc in a.values()), "declined": sum(pc.stats.declined for pc in a.values()),
                             "free_time": sum(pc.stats.free_skipped for pc in a.values()), "days_off": sum(pc.stats.days_off for pc in a.values())}
    return out


def pattern_recovery(store: CalendarStore, n_boot: int, seed: int) -> dict[str, Any]:
    truth = store.truth()["people"]
    day_units: dict[str, dict[str, list[tuple[bool, bool]]]] = {"fragmented_day": defaultdict(list), "back_to_back_day": defaultdict(list)}
    week_units: dict[str, dict[str, list[tuple[bool, bool]]]] = {k: defaultdict(list) for k in (
        "no_focus_blocks", "recurring_in_peak", "no_review_slot", "no_breaks", "unbuffered_external", "late_meetings")}
    err_peak: list[float] = []
    err_late: list[float] = []
    for p in store.people():
        pc = store.get(p)
        for m in pc.weeks:
            wa = pc.week(m)
            t = truth[p]["weeks"][week_label(m)]
            f = wa.features
            for d in wa.days:
                if not d.working:
                    continue
                day_units["fragmented_day"][p].append((d.dow in t["fragmented_days"], bool(d.metrics["fragmented"])))
                day_units["back_to_back_day"][p].append((d.dow in t["back_to_back_days"] or d.dow in t["tolerated_back_to_back_days"], d.metrics["b2b_runs"] > 0))
            week_units["no_focus_blocks"][p].append((bool(t["no_focus_blocks"]), f["focus_blocks_90"] == 0))
            week_units["recurring_in_peak"][p].append((t["recurring_in_peak_h_planted"] > 0, f["recurring_in_peak_h"] > 0))
            week_units["no_review_slot"][p].append((bool(t["no_review_slot"]), f["review_slots"] == 0))
            week_units["no_breaks"][p].append((bool(t["no_breaks"]), f["offscreen_h"] == 0))
            week_units["unbuffered_external"][p].append((bool(t["unbuffered_external_days"]), f["external_unbuffered_n"] > 0))
            week_units["late_meetings"][p].append((bool(t["late_days"]), f["outside_hours_h"] > 0))
            if t["recurring_in_peak_h_planted"] > 0:
                err_peak.append(abs(f["recurring_in_peak_h"] - t["recurring_in_peak_h_planted"]))
            if t["late_days"]:
                err_late.append(abs(f["outside_hours_h"] - len(t["late_days"])))
    rows = {}
    implied = {"no_review_slot": {"no_focus_blocks", "fragmented_days"}, "no_focus_blocks": {"fragmented_days"}}
    for i, (name, units) in enumerate({**day_units, **week_units}.items()):
        r = cluster_prf(units, n_boot, seed + i)
        r["unit"] = "person-day" if name in day_units else "person-week"
        if name in implied:
            # false positives that sit in weeks where another planted problem builds the week from meetings (no review slot, no focus block)
            r["fp_in_weeks_with_implying_problem"] = sum(
                1 for p, pairs in units.items() for (t, pred), wk in zip(pairs, [week_label(m) for m in store.get(p).weeks])
                if pred and not t and week_problems(truth[p]["weeks"][wk]) & implied[name])
        rows[name] = r
    tp = sum(r["tp"] for r in rows.values())
    fp = sum(r["fp"] for r in rows.values())
    fn = sum(r["fn"] for r in rows.values())
    po, ro = _prf(tp, fp, fn)
    return {"rows": rows, "overall": {"precision": round(po, 3) if po is not None else None, "recall": round(ro, 3) if ro is not None else None,
                                      "note": "micro-average over the eight problem types"},
            "magnitude": {"recurring_in_peak_h_mae": round(fmean(err_peak), 3) if err_peak else None,
                          "late_meeting_hours_mae": round(fmean(err_late), 3) if err_late else None},
            "problems": list(PROBLEMS)}


def week_gap(store: CalendarStore, n_boot: int, seed: int) -> dict[str, Any]:
    truth = store.truth()["people"]
    ref = service.reference_for(store, "benefits-processor")
    planted: dict[str, list[float]] = defaultdict(list)
    clean: dict[str, list[float]] = defaultdict(list)
    sig_hits: dict[str, list[tuple[bool, bool]]] = {k: [] for k in PRIMARY_FEATURE}
    for p in store.people():
        if store.info(p)["group"] == "expert":
            continue
        pc = store.get(p)
        for m in pc.weeks:
            wa = pc.week(m)
            probs = week_problems(truth[p]["weeks"][week_label(m)])
            dist = ref.nearest(wa)[1].distance
            (planted if probs else clean)[p].append(dist)
            rows = {r["feature"]: r for r in gap_rows(wa.features, ref, n_boot=60, seed=seed)}
            for prob, (feat, sign) in PRIMARY_FEATURE.items():
                r = rows[feat]
                hit = bool(r["significant"]) and (r["delta"] > 0 if sign > 0 else r["delta"] < 0)
                sig_hits[prob].append((prob in probs, hit))
    placebo = ref.placebo(n_boot=n_boot)
    pl_all = []
    for w in ref.weeks:
        pl_all.append(ref.nearest(w.wa, exclude=w.person)[1].distance)
    pl_all.sort()
    thr = _pct(pl_all, 0.95)
    plant_weeks = [d for v in planted.values() for d in v]
    # expert weeks the feature gap would flag (false-alarm rate of the gap, leave-one-out)
    exp_sig = exp_n = 0
    for p in store.people("expert"):
        pc = store.get(p)
        for m in pc.weeks:
            for r in gap_rows(pc.week(m).features, ref, exclude=p, n_boot=60, seed=seed):
                exp_n += 1
                exp_sig += bool(r["significant"])
    free_n = free_flag = 0
    free_by_feature: dict[str, int] = {f: 0 for f, _ in PRIMARY_FEATURE.values()}
    for p in store.people():
        info = store.info(p)
        pc = store.get(p)
        for m in pc.weeks:
            if week_problems(truth[p]["weeks"][week_label(m)]) and info["group"] != "expert":
                continue
            rows2 = {r["feature"]: r for r in gap_rows(pc.week(m).features, ref, exclude=p if info["group"] == "expert" else None, n_boot=60, seed=seed)}
            free_n += 1
            for prob, (feat, sign) in PRIMARY_FEATURE.items():
                r = rows2[feat]
                bad = bool(r["significant"]) and (r["delta"] > 0 if sign > 0 else r["delta"] < 0)
                free_by_feature[feat] += bad
                free_flag += bad
    by_problem = {}
    for prob, pairs in sig_hits.items():
        tp = sum(t and h for t, h in pairs)
        fn = sum(t and not h for t, h in pairs)
        fp = sum((not t) and h for t, h in pairs)
        by_problem[prob] = {"feature": PRIMARY_FEATURE[prob][0], "direction": "above" if PRIMARY_FEATURE[prob][1] > 0 else "below",
                            "weeks_with_problem": tp + fn, "flagged_in_planted_direction": tp,
                            "recall": round(tp / (tp + fn), 3) if tp + fn else None, "flagged_without_this_problem": fp, "weeks_without_this_problem": len(pairs) - tp - fn}
    return {
        "ribbon_distance": {"planted": cluster_mean_ci(planted, n_boot, seed), "clean_control": cluster_mean_ci(clean, n_boot, seed + 1),
                            "expert_placebo": {"mean": placebo["distance"], "ci": placebo["ci"], "n_people": placebo["n_experts"]},
                            "placebo_95th_percentile": round(thr, 4),
                            "planted_weeks_beyond_placebo_95th": round(sum(d > thr for d in plant_weeks) / len(plant_weeks), 3) if plant_weeks else None,
                            "n_planted_weeks": len(plant_weeks)},
        "feature_gap": {"by_problem": by_problem, "expert_false_alarm_rate": round(exp_sig / exp_n, 3) if exp_n else None,
                        "problem_free_weeks": {"weeks": free_n, "primary_feature_flags": free_flag, "checks": free_n * len(PRIMARY_FEATURE),
                                               "flags_by_feature": free_by_feature,
                                               "note": "weeks of experts (leave-one-out) and of the clean novice: a flag here is a false alarm"},
                        "rule": "interval of the difference excludes zero AND the week lies outside the range of the other experts' weeks"},
    }


def suggestions(store: CalendarStore, n_boot: int, seed: int) -> dict[str, Any]:
    truth = store.truth()["people"]
    units: dict[str, dict[str, list[tuple[bool, bool]]]] = {t: defaultdict(list) for t in TEMPLATE_CAUSES}
    hits: dict[str, int] = {t: 0 for t in sug.TEMPLATE_IDS}
    exp_weeks = exp_flag = 0
    n_sug = 0
    for p in store.people():
        pc = store.get(p)
        for m in pc.weeks:
            probs = week_problems(truth[p]["weeks"][week_label(m)])
            rep = service.suggestions_report(store, p, week_label(m))
            got = {s["template"] for s in rep["suggestions"]}
            n_sug += len(got)
            for t in sug.TEMPLATE_IDS:
                hits[t] += t in got
            for logical, causes in TEMPLATE_CAUSES.items():
                fired = bool(got & set(LOGICAL.get(logical, (logical,))))
                units[logical][p].append((bool(probs & set(causes)), fired))
            if pc.group == "expert":
                exp_weeks += 1
                exp_flag += bool(got)
    rows = {}
    for i, t in enumerate(TEMPLATE_CAUSES):
        r = cluster_prf(units[t], n_boot, seed + i)
        r["triggered_person_weeks"] = sum(hits[x] for x in LOGICAL.get(t, (t,)))
        r["planted_causes"] = list(TEMPLATE_CAUSES[t])
        r["templates"] = list(LOGICAL.get(t, (t,)))
        rows[t] = r
    tp = sum(r["tp"] for r in rows.values())
    fp = sum(r["fp"] for r in rows.values())
    fn = sum(r["fn"] for r in rows.values())
    po, ro = _prf(tp, fp, fn)
    return {"catalogue_size": len(sug.TEMPLATES), "templates_triggered": sum(1 for v in hits.values() if v), "coverage": round(sum(1 for v in hits.values() if v) / len(hits), 3),
            "triggered_by_template": hits, "rows": rows, "overall": {"precision": round(po, 3) if po is not None else None, "recall": round(ro, 3) if ro is not None else None},
            "expert_weeks": exp_weeks, "expert_weeks_with_a_suggestion": exp_flag,
            "expert_false_alarm_rate": round(exp_flag / exp_weeks, 3) if exp_weeks else None, "suggestions_made": n_sug,
            "note": ("Truth is the planted cause of each suggestion (see TEMPLATE_CAUSES; the one-off and the repeating focus-block templates are scored as one "
                     "'focus shortfall' because they split the same cause by how often it repeats). A problem planted below the expert tolerance (one fragmented "
                     "day, one back-to-back run, one late meeting) is not suggested by design and counts as a miss; an accidental near-miss in a clean week counts "
                     "as a false positive.")}


def leak_canary(fast: bool) -> dict[str, Any]:
    cs = CalendarStore(canary=True)
    tokens = json.loads((cs.directory / "canary.json").read_text(encoding="utf-8"))["tokens"]
    people = None
    if fast:
        people = ["p_ninetofive", "p_nightowl", "p_shiftwkr", "p_irregular", "p_exp01", "p_nov02", "p_nov05", "p_nov07"]
    rep = canary_run.run_leak_check(cs, tokens, people=people)
    out = rep.as_dict()
    out["leaked_prefixes"] = rep.leaked_tokens
    out["verdict"] = "no planted token appeared anywhere" if rep.leaked == 0 and rep.control_detected else "LEAK or broken control: see counts"
    return out


LIMITATIONS = [
    {"id": "cal-synthetic-only", "severity": "high",
     "text": ("Every calendar number is on synthetic calendars with planted structure (4 personas, 8 experts, 16 novices, 3 weeks). Nothing about the "
              "calendar layer is validated on real people, and one read-only aggregate check of the owner's own calendar says nothing about anyone else.")},
    {"id": "cal-experts-synthetic", "severity": "high",
     "text": ("The expert reference is generated from the role template that also defines the targets, so agreement with it is by construction. "
              "The template is hand-authored, not measured on real experts, and real experts differ by person, team and week.")},
    {"id": "cal-rules-not-learned", "severity": "medium",
     "text": ("Event kinds (meeting, focus, break, off-screen) come from keyword rules on titles and attendee counts. Real titles are messier; a meeting with no "
              "invitees is read as the owner's own time, and a focus block that is not named as one is invisible. Calendar hygiene differs from how people really work.")},
    {"id": "cal-recall-by-design", "severity": "low",
     "text": ("A problem planted below the expert tolerance (one fragmented day, one back-to-back run) is not suggested, by design. Recall against the planted "
              "intent is therefore below 1; the thresholds come from the template, not from the truth labels.")},
    {"id": "cal-interval-scope", "severity": "medium",
     "text": ("Gap intervals cover uncertainty in the expert reference (8 synthetic experts) only, not a learner's week-to-week variation; a week is flagged only if it "
              "also lies outside the range of expert weeks. Three weeks per person is thin.")},
    {"id": "cal-graph-unverified", "severity": "medium",
     "text": ("The Microsoft Graph adapters were tested against recorded fake responses written from the public documentation; they have never been run against a live "
              "tenant by this code, and tenant policy decides what a signed-in worker may read.")},
    {"id": "cal-leak-claim-scope", "severity": "medium",
     "text": ("The leak result is measured: the exact planted names, addresses, titles, locations and ids did not appear in any payload, suggestion or captured request. "
              "It does not rule out a paraphrase or an encoding, and model calls the worker asks for are recorded in the egress ledger, not hidden.")},
]


def evaluate_calendar(fast: bool = False, *, store: CalendarStore | None = None, seed: int = 20261107) -> dict[str, Any]:
    """The full calendar evaluation as a dict with ``meta`` and ``limitations``. ``fast`` cuts bootstrap resamples and the leak check's people."""
    st = store or default_store()
    n_boot = 100 if fast else 500
    truth = st.truth()
    n_people = len(st.people())
    out: dict[str, Any] = {
        "meta": _meta("synthetic", n_people, "people", "none: planted truth, no fitted model; intervals are a cluster bootstrap by person",
                      "Calendars with planted structure, labelled synthetic; nothing here is validated on real people."),
        "statement": ("These results are on synthetic calendars with planted structure. They show that the pipeline recovers what was planted and where it "
                      "does not; they do not show that real people's weeks look like this, and nothing is validated on real people."),
        "cohort": {"personas": len(st.people("persona")), "experts": len(st.people("expert")), "novices": len(st.people("novice")),
                   "weeks_each": len((truth or {}).get("meta", {}).get("weeks", [])), "problem_types": list(PROBLEMS)},
        "read_path": read_path(st),
        "pattern_recovery": pattern_recovery(st, n_boot, seed),
        "week_gap": week_gap(st, n_boot, seed),
        "suggestions": suggestions(st, n_boot, seed),
        "leak_canary": leak_canary(fast),
        "limitations": LIMITATIONS,
    }
    out["leak_canary"]["note"] = ("Planted tokens: names, addresses, titles, locations, descriptions and ids in the calendar fields the code reads, "
                                   "plus a positive control that the scan can see one.")
    return out
