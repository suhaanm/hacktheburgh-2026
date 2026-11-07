"""Weekly calendar features (CAL-1): numbers and enums only, never titles, names or free text.

Input is a list of ``Block`` objects (already text-free) plus the person's ``WorkConfig`` (usual hours, zone, peak window).
Output per week: meeting load, focus blocks of 60 and 90 minutes, longest focus block, fragmentation index, back-to-back
runs, recurring series, work-hours span, off-computer hours, and a few additive extras. Per day it also returns a
labelled segment sequence (the "week ribbon") used by the expert gap analysis.

Definitions (all in the person's local zone, within their usual window unless stated):

* free time: the window minus meetings, off-screen and break blocks. Explicit focus, batch and review blocks are free
  time (protected, not busy).
* a focus block of N minutes is a maximal run of free time of at least N minutes (60 and 90 are counted separately);
  gaps of 5 minutes or less are transitions and are ignored; gaps of 6 to 59 minutes are "slivers".
* fragmentation (per day, then the mean over working days): ``1 - sum(g^2) / (sum g)^2`` over that day's free gaps
  (0 when all free time is one block; towards 1 when it is many small pieces); a day with under 15 free minutes scores 1.
* a fragmented day has at least 4 meetings and no free gap of 60 minutes.
* back-to-back run: two or more meetings in a row with at most ``b2b_gap_min`` (default 5) minutes between them (overlaps
  count); the week's figure is the number of runs.
* recurring series: distinct recurring meeting series seen in the week; ``recurring_in_peak_h`` is the hours of recurring
  meetings inside the role's peak focus window.
* external calls without a buffer: external meetings that start within ``buffer_min`` (default 10) of the previous
  commitment that day.
* work span: mean over days with two or more commitments of last end minus first start (hours).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from .bucket import bucket_count, round_hours, round_ratio
from .model import Block, WorkConfig, attendee_bucket, fmt_hm, monday_of

# ---- segment alphabet for the week ribbon ------------------------------------------------------------------------
MEETING, FOCUS, SLIVER, BATCH, REVIEW, OFFSCREEN, DAY = "MEETING", "FOCUS", "SLIVER", "BATCH", "REVIEW", "OFFSCREEN", "DAY"
SEGMENT_KINDS = (MEETING, FOCUS, SLIVER, BATCH, REVIEW, OFFSCREEN)

CONTRACT_KEYS = ("meeting_h", "focus_blocks_60", "focus_blocks_90", "longest_focus_min", "fragmentation",
                 "back_to_back_runs", "work_span_h", "offscreen_h")
EXTRA_KEYS = ("meetings_n", "meeting_share", "focus_h", "fragmented_days", "slivers_per_day", "recurring_series", "recurring_meeting_h",
              "recurring_in_peak_h", "external_unbuffered_n", "review_slots", "batch_windows", "outside_hours_h", "days_worked",
              "short_meetings_n", "longest_b2b_min")
ALL_KEYS = CONTRACT_KEYS + EXTRA_KEYS

# how each feature is generalised before it enters an outbound payload (PRV-3)
SAFE_KIND = {"meeting_h": "hours", "focus_blocks_60": "count", "focus_blocks_90": "count", "longest_focus_min": "minutes",
             "fragmentation": "ratio", "back_to_back_runs": "count", "work_span_h": "hours", "offscreen_h": "hours",
             "meetings_n": "count", "meeting_share": "ratio", "focus_h": "hours", "fragmented_days": "count",
             "slivers_per_day": "ratio_free", "recurring_series": "count", "recurring_meeting_h": "hours",
             "recurring_in_peak_h": "hours", "external_unbuffered_n": "count", "review_slots": "count", "batch_windows": "count",
             "outside_hours_h": "hours", "days_worked": "count", "short_meetings_n": "count", "longest_b2b_min": "minutes"}

MIN_GAP = 6          # minutes: gaps of 5 minutes or less are transitions (the same limit as back to back), not free time
FOCUS_60, FOCUS_90 = 60, 90
FRAGMENTED_MIN_MEETINGS = 4


@dataclass
class DayAnalysis:
    day: date
    dow: int
    window: tuple[int, int] | None
    off: bool
    segments: list[tuple[str, int, int]] = field(default_factory=list)       # (kind, start_min, end_min) within the window
    seg_meta: list[dict[str, Any]] = field(default_factory=list)            # parallel to segments: {"out": contract kind, "n_att": int | None}
    free_runs: list[tuple[int, int]] = field(default_factory=list)
    meetings: list[tuple[int, int, Block]] = field(default_factory=list)
    commitments: list[tuple[int, int]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def working(self) -> bool:
        return self.window is not None and not self.off


@dataclass
class WeekAnalysis:
    monday: date
    features: dict[str, Any]
    days: list[DayAnalysis]
    n_blocks: int = 0

    def ribbon(self) -> list[tuple[str, float, float]]:
        """The week as a sequence of (kind, t0_s, t1_s) with a zero-length DAY marker between days, for alignment.
        Times are seconds from Monday 00:00 local."""
        out: list[tuple[str, float, float]] = []
        for d in self.days:
            if not d.working:
                continue
            base = d.dow * 86400
            out.append((DAY, base, base))
            out.extend((k, base + s * 60.0, base + e * 60.0) for k, s, e in d.segments)
        return out


def _local_minutes(b: Block, cfg: WorkConfig, day: date) -> tuple[int, int] | None:
    """The part of a block that falls on local ``day``, as minutes after midnight (end exclusive), or None."""
    s = b.start.astimezone(cfg.tz)
    e = b.end.astimezone(cfg.tz)
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=cfg.tz)
    day_end = day_start + timedelta(days=1)
    lo, hi = max(s, day_start), min(e, day_end)
    if hi <= lo:
        return None
    # wall-clock minutes (a clock-change day has 23 or 25 hours; wall-clock keeps 09:00 at 540)
    lo_m = lo.hour * 60 + lo.minute + (1 if lo.second >= 30 else 0)
    hi_m = 1440 if hi >= day_end else hi.hour * 60 + hi.minute + (1 if hi.second >= 30 else 0)
    if hi_m <= lo_m:
        return None
    return lo_m, min(hi_m, 1440)


def _runs(flags: list[bool], lo: int, hi: int) -> list[tuple[int, int]]:
    out, start = [], None
    for m in range(lo, hi):
        if flags[m]:
            if start is None:
                start = m
        elif start is not None:
            out.append((start, m))
            start = None
    if start is not None:
        out.append((start, hi))
    return out


def _union_minutes(intervals: Iterable[tuple[int, int]]) -> int:
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def analyse_day(day: date, blocks: list[Block], cfg: WorkConfig, off_dates: frozenset[date] = frozenset()) -> DayAnalysis:
    window = cfg.window(day)
    off = day in off_dates
    d = DayAnalysis(day=day, dow=day.weekday(), window=window, off=off)
    items: list[tuple[int, int, Block]] = []
    for b in blocks:
        r = _local_minutes(b, cfg, day)
        if r:
            items.append((r[0], r[1], b))
    items.sort(key=lambda x: (x[0], x[1]))
    d.meetings = [(s, e, b) for s, e, b in items if b.kind == "meeting"]
    d.commitments = [(s, e) for s, e, b in items if b.kind in ("meeting", "offscreen", "break")]
    # 1. paint the day: precedence meeting > offscreen/break > batch/review > focus > free
    level = [0] * 1440
    label = ["."] * 1440
    ident = [-1] * 1440
    prec = {"meeting": 6, "offscreen": 5, "break": 5, "batch": 4, "review": 4, "focus": 3}
    for idx, (s, e, b) in enumerate(items):
        key = b.tag if (b.kind == "focus" and b.tag) else b.kind
        lv = prec[key]
        ch = {"meeting": "M", "offscreen": "O", "break": "K", "batch": "B", "review": "R", "focus": "F"}[key]
        for m in range(s, e):
            if lv >= level[m]:
                level[m], label[m], ident[m] = lv, ch, idx
    busy_minutes = _union_minutes([(s, e) for s, e, b in items if b.kind == "meeting"])
    m = d.metrics
    m["meetings_n"] = len(d.meetings)
    m["meeting_min"] = busy_minutes
    m["short_meetings_n"] = sum(1 for s, e, _ in d.meetings if e - s <= 30)
    # back-to-back chains over meetings of the day (all hours, not only the window)
    ms = sorted(d.meetings, key=lambda x: (x[0], x[1]))
    run: list[tuple[int, int]] = []
    runs: list[list[tuple[int, int]]] = []
    for s, e, _ in ms:
        if run and s - max(x[1] for x in run) <= cfg.b2b_gap_min:
            run.append((s, e))
        else:
            if len(run) >= 2:
                runs.append(run)
            run = [(s, e)]
    if len(run) >= 2:
        runs.append(run)
    m["b2b_runs"] = len(runs)
    m["b2b_meetings"] = sum(len(r) for r in runs)
    m["longest_b2b_min"] = max((max(x[1] for x in r) - min(x[0] for x in r) for r in runs), default=0)
    # recurring meeting minutes, and the part inside the peak window
    m["recurring_min"] = sum(e - s for s, e, b in d.meetings if b.recurring)
    if d.working:
        pk0, pk1 = cfg.peak_for(window)
        m["recurring_peak_min"] = sum(max(0, min(e, pk1) - max(s, pk0)) for s, e, b in d.meetings if b.recurring)
    else:
        m["recurring_peak_min"] = 0
    # external calls without a buffer
    unbuf = 0
    for s, e, b in d.meetings:
        if not b.external:
            continue
        prev_ends = [pe for ps, pe in d.commitments if pe <= s and (ps, pe) != (s, e)]
        if prev_ends and s - max(prev_ends) < cfg.buffer_min:
            unbuf += 1
        elif any(ps < s < pe for ps, pe in d.commitments if (ps, pe) != (s, e)):
            unbuf += 1               # starts while something else is running
    m["external_unbuffered_n"] = unbuf
    m["review_slots"] = sum(1 for s, e, b in items if b.kind == "focus" and b.tag == "review")
    m["batch_windows"] = sum(1 for s, e, b in items if b.kind == "focus" and b.tag == "batch")
    m["offscreen_min"] = _union_minutes([(s, e) for s, e, b in items if b.kind in ("offscreen", "break")])
    if d.commitments or any(b.kind == "focus" for _, _, b in items):
        spans = [(s, e) for s, e, _ in items]
        m["span_min"] = (max(e for _, e in spans) - min(s for s, _ in spans)) if len(spans) >= 2 else 0
        m["has_span"] = len(spans) >= 2
    else:
        m["span_min"], m["has_span"] = 0, False
    # outside hours: meeting minutes outside the window (all of it on a non-working day)
    if window is None or off:
        m["outside_min"] = busy_minutes
    else:
        ws, we = window
        outside = [(s, e) for s, e, b in items if b.kind == "meeting"]
        inside = _union_minutes([(max(s, ws), min(e, we)) for s, e in outside if min(e, we) > max(s, ws)])
        m["outside_min"] = busy_minutes - inside
    # free time within the window
    free_runs: list[tuple[int, int]] = []
    if d.working:
        ws, we = window
        free_like = [lab in (".", "F", "B", "R") for lab in label]
        free_runs = [(s, e) for s, e in _runs(free_like, ws, we) if e - s >= MIN_GAP]
        d.free_runs = free_runs
        gaps = [e - s for s, e in free_runs]
        total = sum(gaps)
        m["free_min"] = total
        m["longest_gap"] = max(gaps, default=0)
        m["focus_60"] = sum(1 for g in gaps if g >= FOCUS_60)
        m["focus_90"] = sum(1 for g in gaps if g >= FOCUS_90)
        m["focus_min"] = sum(g for g in gaps if g >= FOCUS_60)
        m["slivers"] = sum(1 for g in gaps if g < FOCUS_60)
        m["fragmentation"] = 1.0 if total < 15 else round(1.0 - sum(g * g for g in gaps) / (total * total), 4)
        m["fragmented"] = m["meetings_n"] >= FRAGMENTED_MIN_MEETINGS and m["focus_60"] == 0
        m["window_min"] = we - ws
        # segment sequence for the ribbon
        segs: list[tuple[str, int, int]] = []
        meta: list[dict[str, Any]] = []
        mm = ws
        while mm < we:
            ch, idn = label[mm], ident[mm]
            end = mm + 1
            if ch in ("M", "B", "R", "O", "K"):
                while end < we and label[end] == ch and (ch != "M" or ident[end] == idn):
                    end += 1
                segs.append(({"M": MEETING, "B": BATCH, "R": REVIEW, "O": OFFSCREEN, "K": OFFSCREEN}[ch], mm, end))
                meta.append({"out": {"M": "meeting", "B": "focus", "R": "focus", "O": "offscreen", "K": "break"}[ch],
                             "n_att": items[idn][2].n_attendees if ch == "M" and idn >= 0 else None})
            else:                                   # free or explicit focus: merge into one run
                while end < we and label[end] in (".", "F"):
                    end += 1
                length = end - mm
                if length >= FOCUS_60:
                    segs.append((FOCUS, mm, end))
                    meta.append({"out": "free", "n_att": None})
                elif length >= MIN_GAP:
                    segs.append((SLIVER, mm, end))
                    meta.append({"out": "free", "n_att": None})
            mm = end
        d.segments = segs
        d.seg_meta = meta
    else:
        for k in ("free_min", "longest_gap", "focus_60", "focus_90", "focus_min", "slivers", "window_min"):
            m[k] = 0
        m["fragmentation"] = None
        m["fragmented"] = False
    return d


def analyse_week(blocks: list[Block], cfg: WorkConfig, monday: date, off_dates: frozenset[date] = frozenset()) -> WeekAnalysis:
    """Features and the ribbon for the week starting Monday ``monday`` (local)."""
    monday = monday_of(monday)
    days = [analyse_day(monday + timedelta(days=i), blocks, cfg, off_dates) for i in range(7)]
    work = [d for d in days if d.working]
    frag = [d.metrics["fragmentation"] for d in work]
    free_all = [e - s for d in work for s, e in d.free_runs]
    spans = [d.metrics["span_min"] for d in days if d.metrics.get("has_span")]
    series = {b.series for d in days for _, _, b in d.meetings if b.recurring and b.series}
    window_total = sum(d.metrics["window_min"] for d in work)
    meeting_min = sum(d.metrics["meeting_min"] for d in days)
    f: dict[str, Any] = {
        "meeting_h": round(meeting_min / 60.0, 2),
        "focus_blocks_60": sum(d.metrics["focus_60"] for d in work),
        "focus_blocks_90": sum(d.metrics["focus_90"] for d in work),
        "longest_focus_min": max(free_all, default=0),
        "fragmentation": round(sum(frag) / len(frag), 3) if frag else 0.0,
        "back_to_back_runs": sum(d.metrics["b2b_runs"] for d in days),
        "work_span_h": round(sum(spans) / len(spans) / 60.0, 2) if spans else 0.0,
        "offscreen_h": round(sum(d.metrics["offscreen_min"] for d in days) / 60.0, 2),
        "meetings_n": sum(d.metrics["meetings_n"] for d in days),
        "meeting_share": round(meeting_min / window_total, 3) if window_total else 0.0,
        "focus_h": round(sum(d.metrics["focus_min"] for d in work) / 60.0, 2),
        "fragmented_days": sum(1 for d in work if d.metrics["fragmented"]),
        "slivers_per_day": round(sum(d.metrics["slivers"] for d in work) / len(work), 2) if work else 0.0,
        "recurring_series": len(series),
        "recurring_meeting_h": round(sum(d.metrics["recurring_min"] for d in days) / 60.0, 2),
        "recurring_in_peak_h": round(sum(d.metrics["recurring_peak_min"] for d in days) / 60.0, 2),
        "external_unbuffered_n": sum(d.metrics["external_unbuffered_n"] for d in days),
        "review_slots": sum(d.metrics["review_slots"] for d in days),
        "batch_windows": sum(d.metrics["batch_windows"] for d in days),
        "outside_hours_h": round(sum(d.metrics["outside_min"] for d in days) / 60.0, 2),
        "days_worked": len(work),
        "short_meetings_n": sum(d.metrics["short_meetings_n"] for d in days),
        "longest_b2b_min": max((d.metrics["longest_b2b_min"] for d in days), default=0),
    }
    return WeekAnalysis(monday=monday, features=f, days=days, n_blocks=len(blocks))


def fragmented_day_indexes(wa: WeekAnalysis) -> list[int]:
    """Weekday numbers (0 = Monday) of fragmented days: numbers only."""
    return [d.dow for d in wa.days if d.working and d.metrics["fragmented"]]


def b2b_day_indexes(wa: WeekAnalysis) -> list[int]:
    return [d.dow for d in wa.days if d.metrics["b2b_runs"] > 0]


def week_blocks_json(wa: WeekAnalysis) -> list[dict[str, Any]]:
    """The week as the API returns it: per day, blocks of kind meeting | focus | break | offscreen | free, no text.
    Free time inside the usual window is filled in as ``free``. ``start``/``end`` are ``"HH:MM"`` local wall-clock strings;
    ``start_min``/``end_min`` are the same as minutes after local midnight (additive). Meetings carry
    ``n_attendees_bucket`` (``lt5``, ``5to9``, ``10plus``); ``usable`` marks free time of 60 minutes or more."""
    out = []
    for d in wa.days:
        blocks: list[dict[str, Any]] = []
        if d.working:
            for (kind, s, e), m in zip(d.segments, d.seg_meta):
                b: dict[str, Any] = {"start": fmt_hm(s), "end": fmt_hm(e), "start_min": s, "end_min": e, "kind": m["out"], "usable": kind == FOCUS}
                if m["n_att"] is not None:
                    b["n_attendees_bucket"] = attendee_bucket(int(m["n_att"]))
                blocks.append(b)
        out.append({"dow": d.dow, "date": d.day.isoformat(), "working": d.working, "blocks": blocks})
    return out


def safe_features(features: dict[str, Any], keys: Iterable[str] = CONTRACT_KEYS) -> dict[str, Any]:
    """Features generalised for an outbound payload (PRV-3): small counts become "lt5", durations round to 5 minutes, ratios
    to 10% steps. This is what any model sees; it never contains a text field because ``features`` has none."""
    out: dict[str, Any] = {}
    for k in keys:
        v = features.get(k)
        if v is None:
            continue
        kind = SAFE_KIND.get(k, "count")
        if kind == "count":
            out[k] = bucket_count(int(round(float(v))))        # an expert reference is a mean: round it to a whole count first
        elif kind == "hours":
            out[k] = round_hours(v)
        elif kind == "minutes":
            from .bucket import round_minutes
            out[k] = round_minutes(v)
        elif kind == "ratio":
            out[k] = round_ratio(min(1.0, max(0.0, float(v))))
        else:
            out[k] = round(v, 1)
    return out
