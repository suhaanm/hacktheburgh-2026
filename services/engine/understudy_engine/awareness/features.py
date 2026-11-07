"""Awareness features for the stuck hazard (ANA-5 extension, AWR-5): ``awareness_features(window) -> dict[str, float]``.

This module only builds the columns. The hazard track decides whether to append them to its design matrix and runs the ablation
(hazard with and without them, leave-one-person-out); nothing here edits ``hazard/`` and nothing here claims the columns help. On the
synthetic awareness events (``synth.py``) the coupling between stuck spells and cursor behaviour is ASSUMED by the generator, so a lift
there shows only that the pipeline can use a planted signal, not that real behaviour carries one.

``window`` is the awareness events (raw dicts: both ``window`` and ``glance`` types) that happened in the span BEFORE the bin start, i.e.
events with ``t + window_s <= bin_start`` and ``t > bin_start - span_s``: use ``features_by_bin`` which does that with a bisect, so no
future event can leak into a bin. An empty window gives all zeros with ``aw_coverage`` 0 (the model can tell "no data" from "no
movement" only through that column).

Columns (all floats, finite, always present, in this order; ``AWARENESS_COLUMNS``):

  aw_coverage            share of the span covered by window events (0..1)
  aw_dwell_share         share of windows with a dwell (cursor parked 1.2 s or more without a click)
  aw_dwell_s_max         longest dwell in the span, seconds
  aw_wander_mean_log     mean of ln(wander) over windows (0 = straight; larger = path much longer than displacement)
  aw_wander_max_log      max of ln(wander)
  aw_back_forth_sum      reversals between two far-apart places, summed
  aw_speed_bursts_sum    fast flicks, summed
  aw_idle_gap_max_s      longest stretch without cursor movement, seconds
  aw_sys_idle_mean_log   mean of ln(1 + seconds since last keyboard or pointer input at window end)
  aw_input_active_share  share of windows where the cursor was still but input was recent (keys or a click: the permission-free typing proxy)
  aw_app_switches        changes of app kind between consecutive windows
  aw_app_browser, aw_app_spreadsheet, aw_app_email, aw_app_code_editor, aw_app_terminal, aw_app_chat, aw_app_other, aw_app_unknown
                         share of windows in each app kind
  aw_zone_alternation    1 if the cursor alternated between two named zones (A, B, A) in some window, else 0
  aw_glance_any          1 if a glance happened in the span
  aw_glance_blocked      1 if a glance saw a blocker other than none/unknown
  aw_glance_conf         the highest confidence among glances that saw a blocker, else 0
  aw_trigger_hotkey      1 if the worker pressed the glance hotkey in the span (their own ask for help)
  aw_trigger_loop        1 if a loop signature fired in the span

Deliberately NOT a column: the "stuck" trigger. It is derived from the hazard model's own earlier output, so using it as a feature would
feed the model its own prediction.
"""
from __future__ import annotations

import bisect
import math
from typing import Any, Mapping, Sequence

from . import schema

AWARENESS_COLUMNS: tuple[str, ...] = (
    "aw_coverage", "aw_dwell_share", "aw_dwell_s_max", "aw_wander_mean_log", "aw_wander_max_log", "aw_back_forth_sum", "aw_speed_bursts_sum",
    "aw_idle_gap_max_s", "aw_sys_idle_mean_log", "aw_input_active_share", "aw_app_switches",
    "aw_app_browser", "aw_app_spreadsheet", "aw_app_email", "aw_app_code_editor", "aw_app_terminal", "aw_app_chat", "aw_app_other", "aw_app_unknown",
    "aw_zone_alternation", "aw_glance_any", "aw_glance_blocked", "aw_glance_conf", "aw_trigger_hotkey", "aw_trigger_loop",
)
_APP_COLUMNS = {k: f"aw_app_{k}" for k in schema.APP_KINDS_OR_UNKNOWN}
_STILL_FRACTION = 0.9      # a window whose longest stationary stretch is this share of it counts as "the cursor was still"
_RECENT_INPUT_S = 1.5


def zeros() -> dict[str, float]:
    return {c: 0.0 for c in AWARENESS_COLUMNS}


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def awareness_features(window: Sequence[Mapping[str, Any]], *, span_s: float = 30.0) -> dict[str, float]:
    """Features of the awareness events in ``window`` over a span of ``span_s`` seconds. Malformed events are skipped, never raised on."""
    out = zeros()
    wins = []
    glances = []
    for e in window:
        if not isinstance(e, Mapping):
            continue
        if e.get("type") == "window" and isinstance(e.get("cursor"), Mapping):
            wins.append(e)
        elif e.get("type") == "glance" and isinstance(e.get("glance"), Mapping):
            glances.append(e)
    if wins:
        n = len(wins)
        ordered = sorted(wins, key=lambda e: str(e.get("t", "")))
        cur = [w["cursor"] for w in ordered]
        ws = [max(0.5, _num(w.get("window_s"), 2.0)) for w in ordered]
        out["aw_coverage"] = min(1.0, sum(ws) / max(1e-9, span_s))
        out["aw_dwell_share"] = sum(1 for c in cur if _num(c.get("dwell_s")) > 0) / n
        out["aw_dwell_s_max"] = max(_num(c.get("dwell_s")) for c in cur)
        logs = [math.log(max(1.0, _num(c.get("wander"), 1.0))) for c in cur]
        out["aw_wander_mean_log"] = sum(logs) / n
        out["aw_wander_max_log"] = max(logs)
        out["aw_back_forth_sum"] = sum(_num(c.get("back_forth")) for c in cur)
        out["aw_speed_bursts_sum"] = sum(_num(c.get("speed_bursts")) for c in cur)
        out["aw_idle_gap_max_s"] = max(_num(c.get("idle_gap_s")) for c in cur)
        idle = [(_num(w.get("sys_idle_s"), -1.0)) for w in ordered]
        known = [x for x in idle if x >= 0]
        out["aw_sys_idle_mean_log"] = sum(math.log1p(x) for x in known) / len(known) if known else 0.0
        active = sum(1 for c, w_s, x in zip(cur, ws, idle) if x >= 0 and x < _RECENT_INPUT_S and _num(c.get("idle_gap_s")) >= _STILL_FRACTION * w_s)
        out["aw_input_active_share"] = active / n
        kinds = [str(w.get("app_kind", "unknown")) for w in ordered]
        out["aw_app_switches"] = float(sum(1 for a, b in zip(kinds, kinds[1:]) if a != b))
        for k, col in _APP_COLUMNS.items():
            out[col] = kinds.count(k) / n
        out["aw_zone_alternation"] = 1.0 if any(c.get("zone_a") and c.get("zone_b") for c in cur) else 0.0
    if glances:
        out["aw_glance_any"] = 1.0
        blocked = [g["glance"] for g in glances if g["glance"].get("blocker") not in (None, *schema.NO_BLOCK)]
        if blocked:
            out["aw_glance_blocked"] = 1.0
            out["aw_glance_conf"] = max(_num(g.get("confidence")) for g in blocked)
        trig = {g.get("trigger") for g in glances}
        out["aw_trigger_hotkey"] = 1.0 if "hotkey" in trig else 0.0
        out["aw_trigger_loop"] = 1.0 if "loop" in trig else 0.0
    return out


def awareness_vector(window: Sequence[Mapping[str, Any]], *, span_s: float = 30.0) -> list[float]:
    f = awareness_features(window, span_s=span_s)
    return [f[c] for c in AWARENESS_COLUMNS]


def features_by_bin(events: Sequence[Mapping[str, Any]], bin_starts: Sequence[float], *, span_s: float = 30.0) -> list[dict[str, float]]:
    """One feature dict per bin start (unix seconds): the events that finished within the ``span_s`` seconds BEFORE the start, and none after.

    ``events`` need not be sorted. Times are parsed once. A window event counts when ``t + window_s <= bin_start``; a glance when
    ``t <= bin_start``."""
    rows: list[tuple[float, float, Mapping[str, Any]]] = []                 # (end, start, event)
    for e in events:
        try:
            t = schema.parse_time(e["t"])
        except (KeyError, TypeError, ValueError):
            continue
        end = t + (_num(e.get("window_s"), 2.0) if e.get("type") == "window" else 0.0)
        rows.append((end, t, e))
    rows.sort(key=lambda r: r[0])
    ends = [r[0] for r in rows]
    out = []
    for b in bin_starts:
        hi = bisect.bisect_right(ends, b)
        lo = bisect.bisect_right(ends, b - span_s)
        out.append(awareness_features([r[2] for r in rows[lo:hi]], span_s=span_s))
    return out
