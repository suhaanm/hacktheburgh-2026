"""Generic calendar suggestions (CAL-3): a fixed catalogue, selected by code.

**Code selects, text is templated.** ``suggest`` compares a learner's week features with the expert reference and the role's
targets (``routine_expert.yaml``) and returns the catalogue entries whose threshold is breached, each with its numbers and the
expert reference it was compared with. The sentence is a template filled with those numbers. A model may reword a sentence
(``reword``) only through the egress guard, from a ``CalendarSuggestionWording`` payload that holds a template id, the role, a
risk class and bucketed aggregates; a model never sees a title, a name, an address or any calendar text, and its answer is
shown to the worker, never acted on. If the guard refuses or no model is configured the templated sentence stays.

Every suggestion is opt-in and low risk: it proposes a calendar hold or a habit, and nothing here writes to a calendar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .bucket import FROM_PRIVACY
from .features import safe_features

CATALOGUE_VERSION = 1


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    cites: tuple[str, ...]            # learner feature names shown as the numbers of the suggestion
    targets: tuple[str, ...]          # target keys shown as the expert reference
    can_draft: bool
    text: str
    kind: str                         # protect | batch | review | automate | break | reduce | move | buffer | trim | edges


TEMPLATES: tuple[Template, ...] = (
    Template("protect_focus_block", "Protect a 90-minute focus block", ("focus_blocks_90", "longest_focus_min"), ("focus_blocks_90_min",), True,
             "Hold a 90-minute focus block each day. Focus blocks of 90 minutes or more this week: {focus_blocks_90} (expert pattern: at least {t_focus_blocks_90_min}).",
             "protect"),
    Template("batch_similar_work", "Batch similar work", ("batch_windows", "fragmented_days", "fragmentation"), ("batch_windows_min", "fragmented_days_max"), False,
             "Group similar work into one batch window. Batch windows this week: {batch_windows} (expert pattern: at least {t_batch_windows_min}); "
             "fragmented days: {fragmented_days} (expert pattern: at most {t_fragmented_days_max}).", "batch"),
    Template("add_review_slot", "Add a review slot", ("review_slots",), ("review_slots_min",), True,
             "Add a short review slot at the end of the day. Review slots this week: {review_slots} (expert pattern: at least {t_review_slots_min}).", "review"),
    Template("auto_hold_scheduling", "Automate scheduling with an auto-hold", ("focus_blocks_90",), ("focus_blocks_90_min",), True,
             "Let an auto-hold keep a 90-minute focus block free for you. You were short of focus blocks in {weeks_short} of {weeks_seen} weeks (this week {focus_blocks_90}, "
             "expert pattern: at least {t_focus_blocks_90_min}), so a one-off block will not stick.", "automate"),
    Template("offcomputer_break", "Schedule an off-screen break or handoff", ("offscreen_h",), ("offscreen_h_min",), True,
             "Schedule a break or handoff away from the screen. Hours away from it this week: {offscreen_h} (expert pattern: at least {t_offscreen_h_min}).",
             "break"),
    Template("reduce_back_to_back", "Reduce back-to-back meetings", ("back_to_back_runs", "longest_b2b_min"), ("back_to_back_runs_max",), False,
             "Cut back-to-back meetings. Back-to-back runs this week: {back_to_back_runs}, the longest {longest_b2b_min} minutes (expert pattern: at most "
             "{t_back_to_back_runs_max}). Try 25 or 50 minute slots with a gap.", "reduce"),
    Template("move_recurring_out_of_peak", "Move recurring meetings out of peak focus time", ("recurring_in_peak_h", "recurring_series"), ("recurring_in_peak_h_max",), False,
             "Move recurring meetings out of your peak focus time. Hours of recurring meetings in the peak window: {recurring_in_peak_h} "
             "(expert pattern: at most {t_recurring_in_peak_h_max}).", "move"),
    Template("buffer_before_external", "Add a buffer before external calls", ("external_unbuffered_n",), ("external_unbuffered_max",), True,
             "Leave at least 10 minutes before external calls. External calls with a shorter buffer: {external_unbuffered_n} "
             "(expert pattern: at most {t_external_unbuffered_max}).", "buffer"),
    Template("trim_meeting_load", "Trim the meeting load", ("meeting_h", "meeting_share"), ("meeting_h_max", "meeting_share_max"), False,
             "Trim the meeting load. Meeting hours this week: {meeting_h}, {meeting_pct}% of working time (expert pattern: at most {t_meeting_h_max} hours).",
             "trim"),
    Template("protect_working_edges", "Keep meetings inside working hours", ("outside_hours_h", "work_span_h"), ("outside_hours_h_max", "work_span_h_max"), False,
             "Keep meetings inside your usual hours. Hours outside them: {outside_hours_h}; the day spanned {work_span_h} hours "
             "(expert pattern: at most {t_outside_hours_h_max} outside and a {t_work_span_h_max}-hour span).", "edges"),
)
TEMPLATE_BY_ID = {t.id: t for t in TEMPLATES}
TEMPLATE_IDS = tuple(t.id for t in TEMPLATES)


def catalogue() -> list[dict[str, Any]]:
    return [{"id": t.id, "title": t.title, "cites": list(t.cites), "targets": list(t.targets), "can_draft": t.can_draft, "kind": t.kind} for t in TEMPLATES]


# ---------------------------------------------------------------------------------------------------- selection (code)
def _over(f: dict[str, Any], t: dict[str, float], feat: str, key: str) -> float | None:
    """Relative excess of a maximum, or None when within it."""
    if key not in t or feat not in f:
        return None
    v, lim = float(f[feat]), float(t[key])
    if v <= lim:
        return None
    return min(1.0, (v - lim) / lim) if lim else 1.0


def _under(f: dict[str, Any], t: dict[str, float], feat: str, key: str) -> float | None:
    if key not in t or feat not in f:
        return None
    v, lim = float(f[feat]), float(t[key])
    if v >= lim:
        return None
    return min(1.0, (lim - v) / lim) if lim else 1.0


def _weeks_short(history: list[dict[str, Any]] | None, t: dict[str, float]) -> tuple[int, int]:
    h = history or []
    return sum(1 for w in h if float(w.get("focus_blocks_90", 0)) < float(t.get("focus_blocks_90_min", 0))), len(h)


DAY_BOUND_MINIMA = ("focus_blocks_90_min", "focus_blocks_60_min", "review_slots_min", "batch_windows_min", "offscreen_h_min")


def scaled_targets(t: dict[str, float], days_worked: float, days_expected: int) -> dict[str, float]:
    """A week with fewer working days (leave, a bank holiday) is held to proportionally smaller day-bound minima; a full week is unchanged."""
    if days_expected <= 0 or days_worked >= days_expected:
        return t
    k = max(days_worked, 0) / days_expected
    return {**t, **{key: round(float(t[key]) * k, 3) for key in DAY_BOUND_MINIMA if key in t}}


def select(f: dict[str, Any], t: dict[str, float], history: list[dict[str, Any]] | None = None, days_expected: int = 0) -> dict[str, float]:
    """Which templates apply to this week, with a priority in (0, 1]: ``{template_id: priority}``. Pure thresholds."""
    if days_expected:
        t = scaled_targets(t, float(f.get("days_worked", days_expected)), days_expected)
    out: dict[str, float] = {}
    short90 = _under(f, t, "focus_blocks_90", "focus_blocks_90_min")
    weeks_short, weeks_seen = _weeks_short(history, t)
    persistent = weeks_seen >= 2 and weeks_short >= 2 and float(f.get("meeting_share", 0)) <= 0.5
    if short90 is not None and persistent:
        out["auto_hold_scheduling"] = short90                       # a repeating shortfall: automate, instead of a one-off block
    elif short90 is not None:
        out["protect_focus_block"] = short90
    frag = _over(f, t, "fragmented_days", "fragmented_days_max")
    frag_idx = _over(f, t, "fragmentation", "fragmentation_max")
    batch = _under(f, t, "batch_windows", "batch_windows_min")
    if batch is not None and (frag is not None or frag_idx is not None):
        out["batch_similar_work"] = max(x for x in (batch, frag, frag_idx) if x is not None)
    if (p := _under(f, t, "review_slots", "review_slots_min")) is not None:
        out["add_review_slot"] = p
    if (p := _under(f, t, "offscreen_h", "offscreen_h_min")) is not None:
        out["offcomputer_break"] = p
    if (p := _over(f, t, "back_to_back_runs", "back_to_back_runs_max")) is not None:
        out["reduce_back_to_back"] = p
    if (p := _over(f, t, "recurring_in_peak_h", "recurring_in_peak_h_max")) is not None:
        out["move_recurring_out_of_peak"] = p
    if (p := _over(f, t, "external_unbuffered_n", "external_unbuffered_max")) is not None:
        out["buffer_before_external"] = p
    loads = [x for x in (_over(f, t, "meeting_h", "meeting_h_max"), _over(f, t, "meeting_share", "meeting_share_max")) if x is not None]
    if loads:
        out["trim_meeting_load"] = max(loads)
    edges = [x for x in (_over(f, t, "outside_hours_h", "outside_hours_h_max"), _over(f, t, "work_span_h", "work_span_h_max")) if x is not None]
    if edges:
        out["protect_working_edges"] = max(edges)
    return {k: max(round(v, 3), 0.01) for k, v in out.items()}


def _num(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v - round(v)) > 1e-9 else str(int(round(v)))
    return str(v)


def render(tpl: Template, f: dict[str, Any], t: dict[str, float], history: list[dict[str, Any]] | None) -> str:
    ws, wn = _weeks_short(history, t)
    ctx: dict[str, Any] = {k: _num(v) for k, v in f.items()}
    ctx.update({f"t_{k}": _num(v) for k, v in t.items()})
    ctx.update({"weeks_short": ws, "weeks_seen": wn, "meeting_pct": int(round(100 * float(f.get("meeting_share", 0))))})
    return tpl.text.format(**ctx)


def suggest(features: dict[str, Any], ref_features: dict[str, float], targets: dict[str, float], *, history: list[dict[str, Any]] | None = None,
            person: str = "", week: str = "", max_n: int | None = None, days_expected: int = 0) -> list[dict[str, Any]]:
    """The suggestions for one week, strongest first. Each: ``{id, template, title, text, numbers, expert_ref, risk, can_draft, priority,
    week, evidence_weeks, source}``. ``numbers`` are the person's own figures (local screen only); ``expert_ref`` carries the target
    and the expert cohort value for each cited feature."""
    chosen = select(features, targets, history, days_expected)
    if days_expected:
        targets = scaled_targets(targets, float(features.get("days_worked", days_expected)), days_expected)
    out = []
    for tpl in TEMPLATES:
        if tpl.id not in chosen:
            continue
        numbers = {k: features[k] for k in tpl.cites if k in features}
        eref: dict[str, Any] = {k: targets[k] for k in tpl.targets if k in targets}
        eref.update({f"{k}_reference": round(float(ref_features[k]), 2) for k in tpl.cites if k in ref_features})
        out.append({"id": f"cal:{tpl.id}:{person}:{week}", "template": tpl.id, "title": tpl.title, "text": render(tpl, features, targets, history),
                    "numbers": numbers, "expert_ref": eref, "risk": "low", "can_draft": tpl.can_draft, "priority": chosen[tpl.id],
                    "week": week, "evidence_weeks": len(history or []) or 1, "source": "templated"})
    out.sort(key=lambda s: (-s["priority"], TEMPLATE_IDS.index(s["template"])))
    return out[:max_n] if max_n else out


# ---------------------------------------------------------------------------------------------------- optional wording (egress only)
_PRIVACY_READY = False


def register_privacy() -> bool:
    """Register this layer's template ids and named numbers with the privacy track (extend only). Idempotent; False if absent."""
    global _PRIVACY_READY
    if _PRIVACY_READY:
        return True
    try:
        from ..privacy.bucket import register_feature
        from ..privacy.payload import register_vocabulary
    except ImportError:                                     # pragma: no cover
        return False
    register_vocabulary("calendar.template", list(TEMPLATE_IDS), extend=True)
    for name, kind in (("meeting_h", "hours"), ("focus_blocks_60", "count"), ("focus_blocks_90", "count"), ("longest_focus_min", "duration_min"),
                       ("fragmentation", "ratio"), ("back_to_back_runs", "count"), ("work_span_h", "hours"), ("offscreen_h", "hours"),
                       ("meeting_share", "ratio"), ("focus_h", "hours"), ("fragmented_days", "count"), ("recurring_in_peak_h", "hours"),
                       ("external_unbuffered_n", "count"), ("review_slots", "count"), ("batch_windows", "count"), ("outside_hours_h", "hours"),
                       ("longest_b2b_min", "duration_min"), ("recurring_series", "count")):
        register_feature(name, kind)
    _PRIVACY_READY = True
    return True


try:
    register_privacy()
except Exception:                                           # pragma: no cover - never let registration break an import
    pass


def wording_payload(s: dict[str, Any], role: str, ref_features: dict[str, float], features: dict[str, Any]) -> dict[str, Any]:
    """The dict for ``CalendarSuggestionWording``: a template id, the role, a risk class and aggregates for the cited features
    (generalised by the egress guard and, here, beforehand). Contains no text from any calendar item because none exists past
    ``normalize.to_blocks``."""
    tpl = TEMPLATE_BY_ID[s["template"]]
    cites = tuple(tpl.cites)
    return {"template": s["template"], "role": role, "risk": s["risk"],
            "learner": safe_features(features, cites), "expert": safe_features({k: ref_features[k] for k in cites if k in ref_features}, cites)}


def reword(s: dict[str, Any], role: str, ref_features: dict[str, float], features: dict[str, Any], *, port: Any = None,
           accept_mock: bool = False) -> dict[str, Any]:
    """Ask for a worded version of one suggestion through ``egress.send``. On any refusal or failure returns ``s`` unchanged
    (templated text). The model's answer is untrusted text: it is length-checked and shown, never executed."""
    if not register_privacy():
        return s
    try:
        from ..privacy import egress
        from ..privacy.egress import EgressError
        res = egress.send("calendar.suggestion_wording", wording_payload(s, role, ref_features, features), port=port)
    except EgressError:
        return {**s, "source": "templated"}
    except Exception:                                       # a model failure must never take the endpoint down
        return {**s, "source": "templated"}
    if res.mock and not accept_mock:                        # an offline stub's sentence is not a rewording; keep the template (the ledger line stays)
        return {**s, "source": "templated", "ledger_id": res.ledger_id}
    text = res.output.get("text") if isinstance(res.output, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > 280 or "\n" in text.strip():
        return {**s, "source": "templated"}
    return {**s, "text": text.strip(), "source": "reworded", "ledger_id": res.ledger_id}
