"""Synthetic calendars with planted structure (CAL-4).

Deterministic (seeded) three-week calendars (Mon 12 Oct to Sun 1 Nov 2026, the same span as the persona events) for:

* the **four personas** (nine-to-five, night owl, shift worker, irregular; their working hours come from the persona
  schedules, UTC), each with its own planted problems;
* **eight experts** (``p_exp01`` to ``p_exp08``, Europe/London) generated from the benefits-processor ``routine_expert.yaml``
  with jitter, skipped occurrences and a few accidental near-misses;
* **sixteen novices** (``p_nov01`` to ``p_nov16``) built from the same template with planted problems assigned by a fixed
  bit pattern, so every problem appears in about half of them and one novice is clean.

Planted problems (``PROBLEMS``): fragmented days, no focus blocks (meeting-heavy week), back-to-back runs, recurring
meetings in the peak focus window, no review slot, no breaks, external calls with no buffer, meetings outside hours.
Decoys exercise the parsers: cancelled and declined meetings sitting in free time, free-time placeholders, tentative
holds, an all-day out-of-office day, busy days that are not fragmented, series with exceptions and moved occurrences, and
a clock change (25 Oct) for the London calendars (half use Windows zone names, as Outlook exports do).

Output per person: ``calendar.ics`` (RFC 5545 with RRULE series, EXDATE and RECURRENCE-ID overrides) and ``calendar.json``
(the same events expanded), plus ``truth.json`` (what was planted, derived from the construction and not from the feature
code) and ``index.json`` (zone, role, usual hours). ``canary=True`` writes variants whose names, addresses, titles,
locations and descriptions carry unique planted tokens (``canary.json`` lists them) with identical structure, to prove that
nothing textual leaks through any API response or payload.

All of it is synthetic and labelled so; nothing here describes real people.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..plugins.tz import local_to_utc, resolve_tz
from ..store.paths import data_dir
from .expert import DOW, ExpertTemplate, Slot, load_template
from .model import WorkConfig, week_label

START = date(2026, 10, 12)               # Monday
N_WEEKS = 3
N_DAYS = N_WEEKS * 7
CHANGE_DATE = date(2026, 10, 26)         # persona schedule change (day 15)
ROLE = "benefits-processor"
SEED = 20261107
PROBLEMS = ("fragmented_days", "no_focus_blocks", "back_to_back_runs", "recurring_in_peak", "no_review_slot", "no_breaks",
            "unbuffered_external", "late_meetings")
PROBLEM_DOC = {
    "fragmented_days": "On k days a week every free gap is under 60 minutes with 4 or more meetings; label is per day.",
    "no_focus_blocks": "Meeting-heavy week: on every working day all free gaps are under 90 minutes; label is per week.",
    "back_to_back_runs": "On k days a week a chain of 3 to 5 meetings with 0 to 5 minutes between them; label is per day.",
    "recurring_in_peak": "Recurring meetings placed inside the peak focus window (hours planted are recorded).",
    "no_review_slot": "The daily review slot is missing all week.",
    "no_breaks": "No lunch or off-screen block all week.",
    "unbuffered_external": "An external call starts 7 minutes after a meeting ends, on k days.",
    "late_meetings": "A one-hour meeting starting after the usual finish, on k days.",
}
PERSONA_PROBLEMS = {
    "p_ninetofive": ("fragmented_days",),
    "p_nightowl": ("no_focus_blocks", "no_breaks"),
    "p_shiftwkr": ("back_to_back_runs", "unbuffered_external"),
    "p_irregular": ("recurring_in_peak", "no_review_slot"),
}

# ---------------------------------------------------------------------------------------------------- people
FIRST = ["Aisha", "Callum", "Dariusz", "Eilidh", "Farah", "Gideon", "Hana", "Ishaan", "Jocelyn", "Kofi", "Lorna", "Mateo", "Nadia",
         "Oluwaseun", "Priya", "Quentin", "Rhona", "Sanjay", "Tamsin", "Umar", "Verity", "Wei", "Xavier", "Yasmin", "Zoltan"]
LAST = ["Abara", "Brennan", "Chaudhry", "Dunmore", "Eriksen", "Fairweather", "Gallacher", "Hartnell", "Iqbal", "Jankowski", "Kerrigan",
        "Lindqvist", "Moyo", "Naidoo", "Ogilvie", "Pemberton", "Qureshi", "Rutherford", "Sinclair", "Tavares", "Underhill", "Varga"]
EXT_ORGS = ["northgatehousing.example", "alderandfinch.example", "kestrelcharity.example", "marlowlettings.example"]
INTERNAL = "fenwickcouncil.example"
GENERIC_MEETINGS = ["Case conference", "Quick sync", "Triage call", "Allocation huddle", "Policy clinic", "Escalation review",
                    "Data quality call", "Training session", "Workshop prep", "Supplier check-in", "Process walkthrough", "Rota planning"]
TOPICS = ["Heron", "Larch", "Quarry", "Willow", "Bramble", "Tern", "Cobalt", "Juniper"]
CLIENT_SURNAMES = ["Okafor", "Whitlock", "Szymanski", "Mackenzie", "Haddad", "Penrose"]


@dataclass(frozen=True)
class PersonSpec:
    person: str
    group: str                     # persona | expert | novice
    label: str
    tz_name: str
    problems: tuple[str, ...]
    seed: int
    windows_name: str = "template"  # template | persona:<slug>
    win_style: int = 0             # 0 IANA zone name in the ICS, 1 Windows zone name


def person_specs() -> list[PersonSpec]:
    from ..personas.profiles import PERSONAS
    specs: list[PersonSpec] = []
    for p in PERSONAS:
        specs.append(PersonSpec(p.person, "persona", p.label, "UTC", PERSONA_PROBLEMS[p.person], SEED + p.seed, f"persona:{p.slug}"))
    for i in range(1, 9):
        specs.append(PersonSpec(f"p_exp{i:02d}", "expert", f"Expert {i}", "Europe/London", (), SEED + 100 + i, "template", i % 2))
    for i in range(1, 17):
        bits = [(i - 1) >> k & 1 for k in range(4)]
        probs = [PROBLEMS[k] for k in range(4) if bits[k]]
        for e, name in enumerate(PROBLEMS[4:]):
            if ((i * (3 + 2 * e) + e) % 16) < 8:
                probs.append(name)
        # conflicts resolved by priority, recorded in the problem list itself
        if "recurring_in_peak" in probs:
            probs = [p for p in probs if p not in ("fragmented_days", "no_focus_blocks")]
        if "no_focus_blocks" in probs:
            probs = [p for p in probs if p != "fragmented_days"]
        specs.append(PersonSpec(f"p_nov{i:02d}", "novice", f"Novice {i}", "Europe/London", tuple(probs), SEED + 200 + i, "template", i % 2))
    return specs


# ---------------------------------------------------------------------------------------------------- plan (text-free)
@dataclass
class Occ:
    day: date
    s: int
    e: int
    slot: str                         # template slot id, or a planted kind
    kind: str                         # meeting | focus | batch | review | offscreen | break
    n_att: int = 1
    n_ext: int = 0
    online: bool = False
    series: str | None = None         # series key (slot@epoch) when recurring
    nominal: tuple[int, int] | None = None
    status: str = "confirmed"         # confirmed | cancelled | declined | tentative | free
    all_day: str | None = None        # None | oof | free
    planted: str | None = None        # problem that placed it
    title_key: str = ""


@dataclass
class SeriesInfo:
    key: str
    slot: str
    kind: str
    byday: tuple[int, ...]
    s: int
    e: int
    n_att: int
    n_ext: int
    online: bool
    first: date
    last: date
    epoch: int
    planted: str | None = None


def _round5(x: float) -> int:
    return int(round(x / 5.0) * 5)


def _windows(spec: PersonSpec, tpl: ExpertTemplate, rng: random.Random) -> dict[date, tuple[int, int] | None]:
    out: dict[date, tuple[int, int] | None] = {}
    if spec.windows_name == "template":
        for i in range(N_DAYS):
            d = START + timedelta(days=i)
            out[d] = (tpl.work.start_min, tpl.work.end_min) if d.weekday() in tpl.work.days else None
        return out
    from ..personas.profiles import PERSONA_BY_SLUG, windows_for_day
    ps = PERSONA_BY_SLUG[spec.windows_name.split(":", 1)[1]]
    wr = random.Random(f"win:{spec.person}:{SEED}")
    for i in range(N_DAYS):
        d = START + timedelta(days=i)
        wins = windows_for_day(ps, i, wr)
        if not wins:
            out[d] = None
            continue
        s, e = wins[0]
        s_m, e_m = _round5(s * 60), min(1440, _round5(e * 60))
        out[d] = (s_m, e_m) if e_m - s_m >= 180 else None
    return out


def _sequence(rng: random.Random, ws: int, we: int, t0: int, dur: tuple[int, int], gap: tuple[int, int], tail_max: int,
              lunch: tuple[int, int] | None, lunch_target: int, first_gap: tuple[int, int] | None = None) -> list[tuple[str, int, int]]:
    """Alternating meetings (and one lunch) from ``t0`` to the end of the window so that every gap stays within ``gap`` and the
    tail within ``tail_max``. Returns [(kind, s, e)] with kind meeting or lunch."""
    items: list[tuple[str, int, int]] = []
    t = t0
    lunch_done = lunch is None
    guard = 0
    while we - t >= tail_max and guard < 40:
        guard += 1
        g = rng.randint(*(first_gap if (first_gap and not items) else gap))
        d = rng.randint(*dur)
        s = _round5(t + g)
        if not lunch_done and s + d >= lunch_target:
            ls = _round5(t + g)
            le = ls + (lunch[1] - lunch[0])
            if le <= we:
                items.append(("lunch", ls, le))
                t = le
                lunch_done = True
                continue
        e = s + d
        if e > we:
            # a final meeting that ends at the window end: gap before it stays within range
            s = max(t + gap[0], we - d)
            e = we
            if e - s < 15:
                break
        items.append(("meeting", s, e))
        t = e
    return items


def _merge(iv: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def construction_week(occs: list[Occ], wins: dict[date, tuple[int, int] | None], tpl: ExpertTemplate, monday: date) -> dict[str, Any]:
    """What the plan itself contains for a week, computed from the placed occurrences by interval arithmetic (independent of
    the ICS writer, parsers and the feature code; same definitions as ``features.py``). Cancelled, declined and free-time
    entries and all-day entries are not busy time. Used by the evaluation to check the whole read path."""
    counted = ("confirmed", "tentative")
    tot = {"meeting_min": 0, "focus_60": 0, "focus_90": 0, "longest": 0, "b2b_runs": 0, "offscreen_min": 0, "fragmented_days": 0,
           "recurring_peak_min": 0, "external_unbuffered": 0, "review_slots": 0, "batch_windows": 0, "outside_min": 0, "meetings_n": 0}
    frag_days: list[int] = []
    b2b_days: list[int] = []
    off_days = {o.day for o in occs if o.all_day == "oof"}
    fr_sum, fr_n = 0.0, 0
    for i in range(7):
        d = monday + timedelta(days=i)
        day = [o for o in occs if o.day == d and not o.all_day and o.status in counted]
        meet = sorted((o.s, o.e, o) for o in day if o.kind == "meeting")
        tot["meetings_n"] += len(meet)
        tot["meeting_min"] += sum(b - a for a, b in _merge([(a, b) for a, b, _ in meet]))
        tot["offscreen_min"] += sum(b - a for a, b in _merge([(o.s, o.e) for o in day if o.kind in ("offscreen", "break")]))
        tot["review_slots"] += sum(1 for o in day if o.kind == "review")
        tot["batch_windows"] += sum(1 for o in day if o.kind == "batch")
        run: list[tuple[int, int]] = []
        runs = 0
        for a, b, _ in meet:
            if run and a - max(x[1] for x in run) <= 5:
                run.append((a, b))
            else:
                runs += 1 if len(run) >= 2 else 0
                run = [(a, b)]
        runs += 1 if len(run) >= 2 else 0
        tot["b2b_runs"] += runs
        if runs:
            b2b_days.append(i)
        win = wins.get(d)
        if win is None or d in off_days:
            tot["outside_min"] += sum(b - a for a, b in _merge([(a, b) for a, b, _ in meet]))
            continue
        ws, we = win
        tot["outside_min"] += sum(b - a for a, b in _merge([(a, b) for a, b, _ in meet])) - sum(
            b - a for a, b in _merge([(max(a, ws), min(b, we)) for a, b, _ in meet if min(b, we) > max(a, ws)]))
        pk0, pk1 = ws + tpl.work.peak[0], ws + tpl.work.peak[1]
        tot["recurring_peak_min"] += sum(max(0, min(b, pk1) - max(a, pk0)) for a, b, o in meet if o.series)
        for a, b, o in meet:
            if o.n_ext:
                prev = [pe for ps, pe, po in meet if pe <= a and po is not o] + [x.e for x in day if x.kind in ("offscreen", "break") and x.e <= a]
                if prev and a - max(prev) < 10:
                    tot["external_unbuffered"] += 1
                elif any(x.s < a < x.e for x in day if x.kind in ("meeting", "offscreen", "break") and x is not o):
                    tot["external_unbuffered"] += 1          # starts while something else is running
        busy = _merge([(max(o.s, ws), min(o.e, we)) for o in day if o.kind in ("meeting", "offscreen", "break") and min(o.e, we) > max(o.s, ws)])
        gaps, cur = [], ws
        for a, b in busy:
            if a - cur >= 5:
                gaps.append(a - cur)
            cur = max(cur, b)
        if we - cur >= 5:
            gaps.append(we - cur)
        f60 = sum(1 for g in gaps if g >= 60)
        tot["focus_60"] += f60
        tot["focus_90"] += sum(1 for g in gaps if g >= 90)
        tot["longest"] = max([tot["longest"], *gaps])
        total = sum(gaps)
        fr_sum += 1.0 if total < 15 else 1.0 - sum(g * g for g in gaps) / (total * total)
        fr_n += 1
        if len(meet) >= 4 and f60 == 0:
            tot["fragmented_days"] += 1
            frag_days.append(i)
    return {"meeting_h": round(tot["meeting_min"] / 60, 2), "focus_blocks_60": tot["focus_60"], "focus_blocks_90": tot["focus_90"],
            "longest_focus_min": tot["longest"], "back_to_back_runs": tot["b2b_runs"], "offscreen_h": round(tot["offscreen_min"] / 60, 2),
            "fragmentation": round(fr_sum / fr_n, 3) if fr_n else 0.0, "fragmented_days": tot["fragmented_days"], "fragmented_day_list": frag_days,
            "back_to_back_day_list": b2b_days, "recurring_in_peak_h": round(tot["recurring_peak_min"] / 60, 2),
            "external_unbuffered_n": tot["external_unbuffered"], "review_slots": tot["review_slots"], "batch_windows": tot["batch_windows"],
            "outside_hours_h": round(tot["outside_min"] / 60, 2), "meetings_n": tot["meetings_n"], "days_worked": fr_n}


def plan_person(spec: PersonSpec) -> tuple[list[Occ], dict[str, SeriesInfo], dict[str, Any], dict[date, tuple[int, int] | None]]:
    tpl = load_template(ROLE)
    rng = random.Random(f"plan:{spec.person}:{spec.seed}")
    wins = _windows(spec, tpl, rng)
    jitter = int(tpl.synth.get("jitter_min", 10))
    skip_p = float(tpl.synth.get("skip_prob", 0.05))
    probs = set(spec.problems)
    occs: list[Occ] = []
    series: dict[str, SeriesInfo] = {}
    truth_weeks: dict[str, dict[str, Any]] = {}
    # per series, per person jitter chosen once (the whole series moves together)
    series_jit: dict[str, int] = {s.id: _round5(rng.randint(-jitter, jitter)) for s in tpl.slots}
    variant_b = spec.group == "expert" and spec.person in ("p_exp07", "p_exp08")
    off_day = None
    if spec.group in ("expert", "novice") and rng.random() < 0.3:
        off_day = START + timedelta(days=7 + 4)          # Friday of week 2: all-day out of office
    peak_series: list[tuple[str, tuple[int, ...], int, int]] = []
    if "recurring_in_peak" in probs:
        peak_series = [("peak_alloc", (0, 1, 2, 3, 4), 40, 30), ("peak_triage", (1, 3), 100, 45)]    # (slot, days, offset after window start, minutes)

    for w in range(N_WEEKS):
        monday = START + timedelta(days=7 * w)
        wk = week_label(monday)
        dows = [i for i in range(7) if wins[monday + timedelta(days=i)] and monday + timedelta(days=i) != off_day]
        frag: list[int] = []
        b2b: list[int] = []
        unbuf: list[int] = []
        late: list[int] = []
        if "no_focus_blocks" in probs:
            frag_candidates: list[int] = []
        else:
            frag_candidates = dows
        if "fragmented_days" in probs and frag_candidates:
            frag = sorted(rng.sample(frag_candidates, min(len(frag_candidates), rng.choice([1, 2, 3, 4]) if spec.group == "novice" else 3)))
        taken = set(frag) | (set(dows) if "no_focus_blocks" in probs else set())
        if "back_to_back_runs" in probs:
            cand = [d for d in dows if d not in taken and d in (0, 1, 2, 3, 4)]
            b2b = sorted(rng.sample(cand, min(len(cand), rng.choice([1, 2, 3]) if spec.group == "novice" else 3)))
        taken |= set(b2b)
        if "unbuffered_external" in probs:
            cand = [d for d in dows if d not in taken and d in (0, 1, 2, 3, 4)]
            unbuf = sorted(rng.sample(cand, min(len(cand), rng.choice([1, 2]))))
        if "late_meetings" in probs:
            cand = [d for d in dows if d not in frag and d in (0, 1, 2, 3, 4)]
            late = sorted(rng.sample(cand, min(len(cand), rng.choice([1, 2]))))
        peak_hours = 0.0
        busy_ok_day = rng.choice(dows) if (dows and rng.random() < 0.35 and spec.group != "persona") else None

        for dow in dows:
            d = monday + timedelta(days=dow)
            ws, we = wins[d]
            shift = ws - tpl.work.start_min
            epoch = 1 if (spec.group == "persona" and d >= CHANGE_DATE) else 0
            day_occs: list[Occ] = []
            fixed: list[tuple[int, int]] = []      # planted intervals that template items must not overlap

            def add(o: Occ) -> Occ:
                day_occs.append(o)
                return o

            standup = next((s for s in tpl.slots if s.id == "standup"), None)
            lunch_slot = next((s for s in tpl.slots if s.id == "lunch"), None)
            is_frag, is_nofocus = dow in frag, "no_focus_blocks" in probs

            def slot_occ(s: Slot, planted: str | None = None) -> Occ | None:
                sj = series_jit[s.id] if s.recurring else _round5(rng.randint(-jitter, jitter))
                if s.kind in ("batch", "review", "offscreen"):
                    sj = 0 if s.kind != "offscreen" else _round5(series_jit[s.id] // 2)
                st = s.start + shift + sj
                en = s.end + shift + sj
                if st < ws:                              # keep a jittered slot inside the window
                    en += ws - st
                    st = ws
                if en > we:
                    st -= en - we
                    en = we
                if st < ws or en > we:
                    return None
                key = f"{s.id}@{epoch}" if s.recurring or s.kind in ("batch", "review", "offscreen") else None
                kind = s.kind
                return Occ(d, st, en, s.id, kind, s.attendees, 2 if s.external else 0, s.external or (s.recurring and s.attendees > 4),
                           key, (st - sj, en - sj) if key else None, planted=planted, title_key=s.id)

            if is_frag or is_nofocus:
                if standup and dow in standup.days:
                    o = slot_occ(standup)
                    if o:
                        add(o)
                start = (day_occs[0].e if day_occs else ws)
                lunch_ok = "no_breaks" not in probs and lunch_slot is not None
                lunch = (lunch_slot.start, lunch_slot.end) if lunch_ok else None
                lunch_target = (lunch_slot.start + shift) if lunch_ok else 9999
                if is_frag:
                    seq = _sequence(rng, ws, we, start, (20, 40), (10, 45), 55, lunch, lunch_target, first_gap=(5, 40))
                    pl = "fragmented_days"
                else:
                    seq = _sequence(rng, ws, we, start, (45, 60), (62, 80), 90, lunch, lunch_target, first_gap=(0, 40))
                    pl = "no_focus_blocks"
                for kind, s, e in seq:
                    if kind == "lunch":
                        add(Occ(d, s, e, "lunch", "offscreen", planted=None, title_key="lunch", series=f"lunch@{epoch}", nominal=(s, e)))
                    else:
                        n = rng.choice([2, 2, 3, 4, 6])
                        add(Occ(d, s, e, "adhoc", "meeting", n, 0, rng.random() < 0.5, None, None, planted=pl, title_key="adhoc"))
            else:
                # chains, external pairs and recurring peak series first (they take priority over template items)
                if dow in b2b:
                    cs = _round5(ws + (13 * 60 + 15 - tpl.work.start_min))
                    for k in range(rng.choice([3, 4, 5])):
                        du = rng.choice([30, 45, 60])
                        if cs + du > we - 30:
                            break
                        n = rng.choice([2, 3, 5])
                        add(Occ(d, cs, cs + du, "adhoc", "meeting", n, 0, True, None, None, planted="back_to_back_runs", title_key="adhoc"))
                        fixed.append((cs, cs + du))
                        cs += du + rng.choice([0, 0, 5])
                if dow in unbuf:
                    a0 = _round5(ws + (14 * 60 - tpl.work.start_min))
                    add(Occ(d, a0, a0 + 25, "adhoc", "meeting", 3, 0, False, None, None, planted="unbuffered_external", title_key="adhoc"))
                    add(Occ(d, a0 + 32, a0 + 77, "ext_call", "meeting", 3, 2, True, None, None, planted="unbuffered_external", title_key="ext"))
                    fixed += [(a0, a0 + 25), (a0 + 32, a0 + 77)]
                if late and dow in late:
                    ls = we + 15
                    if ls + 60 <= 1440:
                        add(Occ(d, ls, ls + 60, "late", "meeting", 3, 1, True, None, None, planted="late_meetings", title_key="late"))
                if busy_ok_day == dow and not fixed and "recurring_in_peak" not in probs:
                    # a busy but unfragmented day: four short meetings and one 70-minute gap
                    base = ws + 15
                    for i, (off, du) in enumerate(((0, 30), (45, 30), (200, 30), (320, 30))):
                        st = _round5(base + off)
                        if st + du <= we:
                            add(Occ(d, st, st + du, "adhoc", "meeting", 3, 0, False, None, None, planted=None, title_key="adhoc"))
                            fixed.append((st, st + du))
                for ps_slot, ps_days, off, du in peak_series:
                    if dow in ps_days:
                        st = _round5(ws + off)
                        key = f"{ps_slot}@{epoch}"
                        add(Occ(d, st, st + du, ps_slot, "meeting", 5, 0, True, key, (st, st + du), planted="recurring_in_peak", title_key=ps_slot))
                        fixed.append((st, st + du))
                        peak_hours += du / 60.0
                # template items
                for s in tpl.slots_on(dow):
                    if s.id == "lunch" and "no_breaks" in probs:
                        continue
                    if s.kind == "review" and "no_review_slot" in probs:
                        continue
                    if s.optional and rng.random() < skip_p and spec.group != "persona":
                        continue
                    if s.kind == "meeting" and s.id != "standup" and rng.random() < skip_p and not s.optional:
                        continue
                    o = slot_occ(s)
                    if o is None:
                        continue
                    if any(o.s < fe and o.e > fs for fs, fe in fixed):
                        continue
                    add(o)
                if variant_b and dow == 2:
                    st = _round5(ws + 15 * 60 - tpl.work.start_min)
                    add(Occ(d, st, st + 30, "briefing_qa", "meeting", 12, 0, True, f"briefing_qa@{epoch}", (st, st + 30), title_key="briefing_qa"))
            occs.extend(day_occs)

        # decoys in free time of this week: cancelled, declined, free placeholder, tentative
        decoys = rng.sample(dows, min(len(dows), 3)) if dows else []
        kinds = ["cancelled", "declined", "free", "tentative"]
        for i, dow in enumerate(decoys):
            d = monday + timedelta(days=dow)
            ws, we = wins[d]
            used = [(o.s, o.e) for o in occs if o.day == d]
            for _ in range(6):
                st = _round5(rng.randint(ws + 60, max(ws + 61, we - 90)))
                if not any(st < ue + 20 and st + 45 > us - 20 for us, ue in used):
                    occs.append(Occ(d, st, st + 45, "decoy", "meeting", 4, 0, rng.random() < 0.5, None, None, status=kinds[(i + w) % 4],
                                    planted=None, title_key="decoy"))
                    break
        if off_day and monday <= off_day < monday + timedelta(days=7):
            occs.append(Occ(off_day, 0, 1440, "ooo", "offscreen", all_day="oof", title_key="ooo"))
        truth_weeks[wk] = {
            "fragmented_days": frag, "back_to_back_days": b2b, "unbuffered_external_days": unbuf, "late_days": late,
            "no_focus_blocks": "no_focus_blocks" in probs, "no_review_slot": "no_review_slot" in probs, "no_breaks": "no_breaks" in probs,
            "recurring_in_peak_h_planted": round(peak_hours, 2),
            "busy_not_fragmented_day": busy_ok_day,
            "all_day_off": off_day.weekday() if (off_day and monday <= off_day < monday + timedelta(days=7)) else None,
        }

    # series info (nominal pattern per series key)
    by_key: dict[str, list[Occ]] = defaultdict(list)
    for o in occs:
        if o.series:
            by_key[o.series].append(o)
    for key, lst in by_key.items():
        o0 = lst[0]
        epoch = int(key.rsplit("@", 1)[1])
        lo = CHANGE_DATE if epoch == 1 else START
        hi = (CHANGE_DATE - timedelta(days=1)) if (spec.group == "persona" and epoch == 0) else START + timedelta(days=N_DAYS - 1)
        slot_days = tuple(sorted({o.day.weekday() for o in lst}))
        tslot = next((s for s in tpl.slots if s.id == o0.slot), None)
        days_nominal = tuple(sorted(tslot.days)) if tslot else slot_days
        nominal = o0.nominal or (o0.s, o0.e)
        series[key] = SeriesInfo(key, o0.slot, o0.kind, days_nominal if o0.slot not in ("peak_alloc", "peak_triage", "briefing_qa") else slot_days,
                                 nominal[0], nominal[1], o0.n_att, o0.n_ext, o0.online, lo, hi, epoch, o0.planted)
    occs.sort(key=lambda o: (o.day, o.s, o.e))
    for w in range(N_WEEKS):
        monday = START + timedelta(days=7 * w)
        truth_weeks[week_label(monday)]["construction"] = construction_week(occs, wins, tpl, monday)
    truth = {"weeks": truth_weeks, "problems": sorted(probs)}
    return occs, series, truth, wins


# ---------------------------------------------------------------------------------------------------- rendering text
class Namer:
    """Text for the plan: normal synthetic names and titles, or canary tokens (unique, non-dictionary words and codes).
    Every text is drawn once per event (or series) and cached, so the ICS and the JSON describe identical events."""

    SYL = ["zel", "quor", "bran", "thas", "vyn", "mer", "oxe", "pry", "dul", "kes", "vorn", "lith", "sark", "wend", "tarn", "ulm", "fenn", "gorl", "hesk", "jarv"]

    def __init__(self, spec: PersonSpec, canary: bool):
        self.canary = canary
        self.rng = random.Random(f"text:{spec.person}:{spec.seed}:{'c' if canary else 'n'}")
        self.tokens: list[str] = []
        self._used: set[Any] = set()
        self.me = self._person(internal=True)
        self.pool = [self._person(internal=True) for _ in range(9)]
        self.ext_pool = [self._person(internal=False) for _ in range(4)]
        self.codes = [(self._word(2).capitalize() + f"-{self.rng.randint(11, 98)}") if canary else self.rng.choice(TOPICS) for _ in range(4)]
        if canary:
            self.tokens += self.codes
        self._cache: dict[str, tuple[str, str, str]] = {}

    def _word(self, n: int) -> str:
        while True:
            w = "".join(self.rng.choice(self.SYL) for _ in range(n))
            if w not in self._used:
                self._used.add(w)
                return w

    def _person(self, internal: bool) -> tuple[str, str]:
        if self.canary:
            first, last = self._word(2).capitalize(), self._word(3).capitalize()
            dom = "canarycorp.example" if internal else f"{self._word(2)}corp.example"
            name, local = f"{first} {last}", f"{first.lower()}.{last.lower()}"
            addr = f"{local}@{dom}"
            self.tokens += [name, first, last, addr, local, dom]
            return name, addr
        while True:
            first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
            if (first, last) not in self._used:
                self._used.add((first, last))
                break
        dom = INTERNAL if internal else self.rng.choice(EXT_ORGS)
        return f"{first} {last}", f"{first.lower()}.{last.lower()}@{dom}"

    def texts(self, o: Occ, tpl: ExpertTemplate, key: str) -> tuple[str, str, str]:
        """(title, location, description) for the event or series ``key``; drawn on first use."""
        if key in self._cache:
            return self._cache[key]
        rng = self.rng
        titles = tpl.synth.get("titles", {})
        extra = {
            "peak_alloc": ["Queue allocation huddle", "Morning allocation check"], "peak_triage": ["Case triage sync", "Triage and escalations"],
            "briefing_qa": ["Briefing follow-up Q&A"], "late": ["Call with partner team (other time zone)"], "ooo": ["Out of office"],
            "ext": ["Supplier call: housing association", "Landlord forum call"], "decoy": ["Possible catch-up", "Hold: training", "Moved to next week"],
        }
        k = o.title_key
        if k in titles:
            base = rng.choice(titles[k])
        elif k in extra:
            base = rng.choice(extra[k])
        else:
            base = rng.choice(GENERIC_MEETINGS)
            if not self.canary:
                r = rng.random()
                if r < 0.45:
                    base += f": Project {rng.choice(TOPICS)}"
                elif r < 0.7:
                    base = f"1:1 with {rng.choice(self.pool)[0]}"
                elif r < 0.85:
                    base += f" ({rng.choice(CLIENT_SURNAMES)} household)"
        if o.slot == "one_to_one" and not self.canary:
            base = f"1:1 with {self.pool[0][0].split()[0]}"
        if self.canary:
            code = rng.choice(self.codes)
            client = f"{self._word(2).capitalize()}-{self._word(2).capitalize()}"
            self.tokens.append(client)
            if o.kind == "meeting" and o.slot != "standup":
                title = f"{code} {rng.choice(['contract renewal', 'appeal review', 'escalation', 'handover'])} - {client} ({base})"
            else:
                title = f"{base} - {code}"
        else:
            title = base
        loc = ""
        if o.kind == "meeting":
            if o.online:
                loc = "Microsoft Teams Meeting"
            elif self.canary:
                loc = f"{self._word(2).capitalize()} Annexe Room {rng.randint(1, 99)}"
                self.tokens.append(loc)
            else:
                loc = f"Room {rng.randint(1, 5)}.{rng.randint(1, 20):02d}, Fenwick House"
        bits: list[str] = []
        if o.kind == "meeting":
            if o.online:
                bits.append("Join: https://teams.microsoft.com/l/meetup-join/19%3ameeting_" + "".join(rng.choice("abcdef0123456789") for _ in range(24)) + "%40thread.v2/0")
            if self.canary:
                ref = f"CNRY-{rng.randint(10000, 99999)}"
                who = self._person(True)
                house = self._word(2).capitalize()
                self.tokens += [ref, house]
                bits.append(f"Agenda: discuss {who[0]}'s appeal (ref {ref}); bring the claimant letter for {house} House.")
            else:
                bits.append(f"Agenda: {rng.choice(['allocation of new cases', 'rule change walkthrough', 'backlog review', 'supplier performance'])}.")
        self._cache[key] = (title, loc, "\n".join(bits))
        return self._cache[key]


# ---------------------------------------------------------------------------------------------------- writers
def esc(v: str) -> str:
    """RFC 5545 TEXT escaping."""
    bs = chr(92)
    return v.replace(bs, bs + bs).replace(";", bs + ";").replace(",", bs + ",").replace("\n", bs + "n")


def fold(line: str) -> str:
    """RFC 5545 folding at 75 octets (continuation lines start with one space)."""
    if len(line.encode("utf-8")) <= 75:
        return line
    out, cur, n, limit = [], "", 0, 75
    for ch in line:
        b = len(ch.encode("utf-8"))
        if n + b > limit:
            out.append(cur)
            cur, n, limit = "", 0, 74
        cur += ch
        n += b
    out.append(cur)
    return "\r\n ".join(out)


LONDON_VTZ = [
    "BEGIN:VTIMEZONE", "TZID:{tzid}", "BEGIN:STANDARD", "DTSTART:16011028T020000", "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10",
    "TZOFFSETFROM:+0100", "TZOFFSETTO:+0000", "END:STANDARD", "BEGIN:DAYLIGHT", "DTSTART:16010325T010000",
    "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3", "TZOFFSETFROM:+0000", "TZOFFSETTO:+0100", "END:DAYLIGHT", "END:VTIMEZONE",
]


def _fmt_dt(d: date, minute: int) -> str:
    if minute >= 1440:                       # an end at midnight is the next day at 00:00 (T240000 is not valid)
        d, minute = d + timedelta(days=minute // 1440), minute % 1440
    return f"{d.strftime('%Y%m%d')}T{minute // 60:02d}{minute % 60:02d}00"


def _dtprop(name: str, d: date, minute: int, tz_name: str, tzid: str | None) -> str:
    return f"{name}:{_fmt_dt(d, minute)}Z" if tz_name == "UTC" else f"{name};TZID={tzid}:{_fmt_dt(d, minute)}"


def _row(o: Occ, uid: str, org: tuple[str, str], parts: list[tuple[str, str]], text: tuple[str, str, str], series_uid: str | None) -> dict[str, Any]:
    d1 = o.day + timedelta(days=1)
    return {
        "id": f"{uid}#{o.day.isoformat()}",
        "start": f"{o.day.isoformat()}T{o.s // 60:02d}:{o.s % 60:02d}:00" if not o.all_day else f"{o.day.isoformat()}T00:00:00",
        "end": (f"{o.day.isoformat()}T{o.e // 60:02d}:{o.e % 60:02d}:00" if o.e < 1440 else f"{d1.isoformat()}T00:00:00") if not o.all_day else f"{d1.isoformat()}T00:00:00",
        "title": text[0], "organizer": org[1], "attendees": [a for _, a in parts if a != org[1]] if o.kind == "meeting" else [],
        "location": text[1], "online": o.online, "recurring": series_uid is not None, "series": series_uid or "",
        "show_as": "free" if o.status == "free" else "tentative" if o.status == "tentative" else ("oof" if o.all_day == "oof" else "busy"),
        "status": "cancelled" if o.status == "cancelled" else "confirmed",
        "response": "declined" if o.status == "declined" else "none", "all_day": o.all_day is not None,
    }


def build_files(spec: PersonSpec, canary: bool = False) -> tuple[str, dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    """-> (ics text, calendar json, truth entry, canary tokens, work config dict)."""
    tpl = load_template(ROLE)
    occs, series, truth, wins = plan_person(spec)
    namer = Namer(spec, canary)
    tzid = "GMT Standard Time" if (spec.tz_name != "UTC" and spec.win_style) else spec.tz_name
    uid_dom = "canarycorp.example" if canary else INTERNAL
    me_name, me_addr = namer.me
    lines = ["BEGIN:VCALENDAR", "PRODID:-//Fenwick Council//Exchange Calendar 16.0//EN", "VERSION:2.0", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{esc(me_name if canary else 'Calendar')}", f"X-WR-TIMEZONE:{spec.tz_name}"]
    if spec.tz_name != "UTC":
        lines += [ln.format(tzid=tzid) for ln in LONDON_VTZ]
    rows: list[dict[str, Any]] = []
    prng = random.Random(f"people:{spec.person}:{spec.seed}:{'c' if canary else 'n'}")
    counter = [0]

    def uid_for(tag: str) -> str:
        counter[0] += 1
        if canary:
            tok = f"CANARYUID{counter[0]:04d}{tag[:6].upper()}"
            namer.tokens.append(tok.lower())
            return f"{tok}@{uid_dom}"
        return f"{spec.person}-{tag}-{counter[0]:04d}@{uid_dom}"

    def people_for(o: Occ) -> tuple[tuple[str, str], list[tuple[str, str]]]:
        if o.kind != "meeting":
            return (me_name, me_addr), []
        k = max(2, o.n_att)
        others = list(namer.pool)
        prng.shuffle(others)
        ext = list(namer.ext_pool)
        prng.shuffle(ext)
        parts = [(me_name, me_addr)] + others[: max(0, k - 1 - o.n_ext)] + ext[: o.n_ext]
        i = 0
        while len(parts) < k:
            addr = f"colleague{i}.{spec.person}@{uid_dom}"
            parts.append((f"Colleague {i + 1}", addr))
            if canary:
                namer.tokens.append(addr)
            i += 1
        parts = parts[:k]
        org = parts[0] if o.slot == "one_to_one" else prng.choice(parts)
        return org, parts

    def vevent(uid: str, o: Occ, org, parts, text, *, day: date, s: int, e: int, rid: str | None = None, rrule: str | None = None,
               exdates: list[str] | None = None) -> list[str]:
        ev = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:20261001T080000Z"]
        if o.all_day:
            ev += [f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}"]
        else:
            ev += [_dtprop("DTSTART", day, s, spec.tz_name, tzid), _dtprop("DTEND", day, e, spec.tz_name, tzid)]
        if rid:
            ev.append(rid)
        if rrule:
            ev.append(f"RRULE:{rrule}")
        ev += exdates or []
        ev.append(f"SUMMARY:{esc(text[0])}")
        ev.append(f'ORGANIZER;CN="{org[0]}":mailto:{org[1]}')
        for pn, pa in parts:
            ps = "ACCEPTED"
            if pa == me_addr:
                ps = "DECLINED" if o.status == "declined" else "TENTATIVE" if o.status == "tentative" else "ACCEPTED"
            ev.append(f'ATTENDEE;CN="{pn}";ROLE=REQ-PARTICIPANT;PARTSTAT={ps}:mailto:{pa}')
        if text[1]:
            ev.append(f"LOCATION:{esc(text[1])}")
        if text[2]:
            ev.append(f"DESCRIPTION:{esc(text[2])}")
        busy = "OOF" if o.all_day == "oof" else "FREE" if o.status == "free" else "TENTATIVE" if o.status == "tentative" else "BUSY"
        ev += ["CLASS:PUBLIC", "TRANSP:" + ("TRANSPARENT" if busy == "FREE" else "OPAQUE"), f"X-MICROSOFT-CDO-BUSYSTATUS:{busy}",
               f"X-MICROSOFT-CDO-ALLDAYEVENT:{'TRUE' if o.all_day else 'FALSE'}",
               "STATUS:" + ("CANCELLED" if o.status == "cancelled" else "TENTATIVE" if o.status == "tentative" else "CONFIRMED")]
        if o.online:
            ev.append("X-MICROSOFT-SKYPETEAMSMEETINGURL:https://teams.microsoft.com/l/meetup-join/19%3ameeting_x")
        ev.append("END:VEVENT")
        return ev

    by_series: dict[str, list[Occ]] = defaultdict(list)
    for o in occs:
        if o.series:
            by_series[o.series].append(o)
    for key, info in sorted(series.items()):
        lst = sorted(by_series[key], key=lambda x: x.day)
        o0 = lst[0]
        org, parts = people_for(o0)
        nominal_days = [info.first + timedelta(days=i) for i in range((info.last - info.first).days + 1)
                        if (info.first + timedelta(days=i)).weekday() in info.byday]
        if not nominal_days:
            continue
        present = {o.day: o for o in lst}
        uid = uid_for(info.slot)
        text = namer.texts(o0, tpl, key)
        byday = ",".join(DOW[i].upper()[:2] for i in info.byday)
        if info.slot in ("standup", "lunch"):
            rrule = f"FREQ=WEEKLY;BYDAY={byday};COUNT={len(nominal_days)}"
        else:
            rrule = f"FREQ=WEEKLY;BYDAY={byday};UNTIL={(info.last + timedelta(days=1)).strftime('%Y%m%d')}T000000Z"
        ex, overrides = [], []
        for nd in nominal_days:
            oc = present.get(nd)
            if oc is None:
                ex.append(_dtprop("EXDATE", nd, info.s, spec.tz_name, tzid))
            elif (oc.s, oc.e) != (info.s, info.e):
                overrides.append((oc, _dtprop("RECURRENCE-ID", nd, info.s, spec.tz_name, tzid)))
        master = Occ(nominal_days[0], info.s, info.e, o0.slot, o0.kind, o0.n_att, o0.n_ext, o0.online, key, None, title_key=o0.title_key)
        lines += vevent(uid, master, org, parts, text, day=nominal_days[0], s=info.s, e=info.e, rrule=rrule, exdates=ex)
        for oc, rid in overrides:
            lines += vevent(uid, oc, org, parts, text, day=oc.day, s=oc.s, e=oc.e, rid=rid)
        for nd in nominal_days:
            if nd in present:
                rows.append(_row(present[nd], uid, org, parts, text, uid))
    for o in occs:
        if o.series:
            continue
        org, parts = people_for(o)
        uid = uid_for(o.slot)
        text = namer.texts(o, tpl, f"s|{o.day}|{o.s}|{o.slot}")
        lines += vevent(uid, o, org, parts, text, day=o.day, s=o.s, e=o.e)
        rows.append(_row(o, uid, org, parts, text, None))
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(fold(ln) for ln in lines) + "\r\n"
    rows.sort(key=lambda r: (r["start"], r["id"]))
    cal_json = {"format": "understudy.calendar.v1", "tz": spec.tz_name, "events": rows}
    work = WorkConfig(tz=resolve_tz(spec.tz_name) or resolve_tz("UTC"), tz_name=spec.tz_name, start_min=tpl.work.start_min,
                      end_min=tpl.work.end_min, days=tpl.work.days, peak=tpl.work.peak,
                      by_date=dict(wins) if spec.windows_name != "template" else {})
    truth_entry = {"group": spec.group, "role": ROLE, "tz": spec.tz_name, "problems": truth["problems"], "weeks": truth["weeks"]}
    return ics, cal_json, truth_entry, list(dict.fromkeys(namer.tokens)), work.to_dict() | {"self_email": me_addr}


def generate(root: Path | str | None = None, *, canary: bool = False, people: list[str] | None = None) -> dict[str, Any]:
    """Write the synthetic calendars under ``<root>/synthetic/calendars`` (or ``.../calendars/canary``). Deterministic."""
    base = Path(root) if root else data_dir()
    out_dir = base / "synthetic" / "calendars" / ("canary" if canary else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {}
    truth: dict[str, Any] = {}
    all_tokens: dict[str, list[str]] = {}
    n_events = 0
    for spec in person_specs():
        if people and spec.person not in people:
            continue
        ics, cal_json, tr, tokens, work = build_files(spec, canary=canary)
        pdir = out_dir / spec.person
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "calendar.ics").write_text(ics, encoding="utf-8", newline="")
        (pdir / "calendar.json").write_text(json.dumps(cal_json, indent=1), encoding="utf-8")
        index[spec.person] = {"group": spec.group, "label": spec.label, "role": ROLE, "tz": spec.tz_name, "ics": f"{spec.person}/calendar.ics",
                              "json": f"{spec.person}/calendar.json", "work": work, "self_email": work.get("self_email")}
        truth[spec.person] = tr
        all_tokens[spec.person] = tokens
        n_events += len(cal_json["events"])
    meta = {"schema": 1, "origin": "synthetic", "seed": SEED, "start": START.isoformat(),
            "weeks": [week_label(START + timedelta(days=7 * w)) for w in range(N_WEEKS)], "n_people": len(index), "canary": canary}
    (out_dir / "index.json").write_text(json.dumps({"meta": meta, "people": index}, indent=1), encoding="utf-8")
    if not canary:
        (out_dir / "truth.json").write_text(json.dumps({
            "meta": meta, "kind": "calendar_truth",
            "description": ("Planted calendar structure for 4 personas, 8 experts and 16 novices (synthetic). The labels come from the generator's "
                            "construction, not from the feature code. Expert calendars are generated from packages/packs/benefits-processor/routine_expert.yaml."),
            "problems": PROBLEM_DOC, "expert_template": f"{ROLE}@1", "people": truth}, indent=1), encoding="utf-8")
    else:
        flat = sorted({t for toks in all_tokens.values() for t in toks})
        (out_dir / "canary.json").write_text(json.dumps({"meta": meta, "tokens": flat, "by_person": all_tokens}, indent=1), encoding="utf-8")
    return {"dir": str(out_dir), "people": len(index), "events": n_events, "canary": canary}


if __name__ == "__main__":
    import sys
    print(generate(canary="--canary" in sys.argv))
