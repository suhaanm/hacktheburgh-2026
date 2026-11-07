"""The deterministic reply (REQ-6): what the feature says with no model at all, and what every model reply falls back to.

``build_reply(request)`` returns the same strict shape a model must produce (``provenance.REPLY_SCHEMA``): sections of sentences,
each with the packet fields it uses, and the default coach-menu ids. Every sentence is built from the packet by code through
``numbers.render``, so every number is a field of the packet written in a form the provenance check accepts. A test runs the check
over the template for every packet in the synthetic cohort and every intent: a template that fails its own check is a bug.

Wording follows the honesty rules: "associated with", never "because"; the sign of a difference is spoken ("longer",
"shorter", "saved"); a single case is said to have no interval of its own; nothing says a novice becomes an expert.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, NamedTuple

from . import intent as I
from . import numbers as _N
from . import vocab as V
from .menu import default_choice
from .packet import EvidencePacket, ExplainRequest


class Style:
    """How numbers are spoken. The default is ``numbers.render`` (the canonical form). ``fakes.VariedStyle`` speaks the same values in
    the other forms of the rounding table, to measure how often the check wrongly rejects a faithful reply."""

    def render(self, value: float, unit: str) -> str:
        return _N.render(value, unit)

    def range(self, lo: float, hi: float, unit: str) -> str:
        return _N.render_range(lo, hi, unit)


_STYLE: contextvars.ContextVar[Style] = contextvars.ContextVar("evidence_style", default=Style())


@contextlib.contextmanager
def use_style(style: Style) -> Iterator[None]:
    tok = _STYLE.set(style)
    try:
        yield
    finally:
        _STYLE.reset(tok)


def render(value: float, unit: str) -> str:
    return _STYLE.get().render(value, unit)


def render_range(lo: float, hi: float, unit: str) -> str:
    return _STYLE.get().range(lo, hi, unit)


class S(NamedTuple):
    text: str
    uses: list[str]


def _dir(v: float) -> str:
    return "longer" if v >= 0 else "shorter"


def _sec(v: float) -> str:
    return render(abs(v), "s")


# ------------------------------------------------------------------------------------------------ pieces
def case_line(pk: EvidencePacket) -> S | None:
    g = pk.gap
    if g is None or g.case_s is None or g.reference_s is None:
        return None
    uses = ["gap.case_s", "gap.reference_s"]
    head = f"On this case you took {_sec(g.case_s)} against {_sec(g.reference_s)} for the nearest expert"
    if g.gap_s is None or abs(g.gap_s) < 0.5:
        return S(head + ", about the same.", uses)
    uses.append("gap.gap_s")
    text = f"{head}, which is {_sec(g.gap_s)} {_dir(g.gap_s)}"
    if g.gap_lo is not None and g.gap_hi is not None:
        text += f" ({render_range(g.gap_lo, g.gap_hi, 's')})."
        uses += ["gap.gap_lo", "gap.gap_hi"]
    else:
        text += "; a single case has no interval of its own."
    return S(text, uses)


def habit_lines(pk: EvidencePacket, k: int = 3) -> list[S]:
    pos = sorted(((hid, h) for hid, h in pk.habits.items() if h.seconds >= 0.5), key=lambda t: -t[1].seconds)[:k]
    out: list[S] = []
    if pos:
        parts = [f"{V.HABIT_NAME[hid]} with {_sec(h.seconds)}" for hid, h in pos]
        body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        out.append(S(f"The alignment associates {body}.", [f"habit.{hid}.seconds" for hid, _ in pos]))
    for hid, h in pk.habits.items():
        if h.seconds <= -0.5:
            out.append(S(f"The alignment also shows {V.HABIT_NAME[hid]} as {_sec(h.seconds)} saved.", [f"habit.{hid}.seconds"]))
    return out


def rank_line(pk: EvidencePacket) -> S | None:
    pos = sorted(((hid, h) for hid, h in pk.habits.items() if h.seconds >= 0.5), key=lambda t: -t[1].seconds)
    if not pos:
        return None
    hid, h = pos[0]
    return S(f"The largest part of this case's gap is associated with {V.HABIT_NAME[hid]}, with {_sec(h.seconds)}.", [f"habit.{hid}.seconds"])


def cohort_line(pk: EvidencePacket) -> S | None:
    g = pk.gap
    if g is None or g.cohort_gap_s is None:
        return None
    uses = ["gap.cohort_gap_s", "meta.n"]
    text = (f"Across the {render(pk.meta.n, 'count')} {V.N_UNIT_PHRASE[pk.meta.n_unit]} in this data, novices take on average "
            f"{_sec(g.cohort_gap_s)} {_dir(g.cohort_gap_s)} per case than their nearest expert")
    if g.cohort_lo is not None and g.cohort_hi is not None:
        text += f" ({render_range(g.cohort_lo, g.cohort_hi, 's')})."
        uses += ["gap.cohort_lo", "gap.cohort_hi"]
    else:
        text += "."
    return S(text, uses)


def controls_line(pk: EvidencePacket) -> S | None:
    g = pk.gap
    if g is None or g.placebo_s is None:
        return None
    uses = ["gap.placebo_s"]
    text = f"As a check on the method, comparing experts with each other gives {_sec(g.placebo_s)} {_dir(g.placebo_s)}"
    if g.placebo_lo is not None and g.placebo_hi is not None:
        zero = g.placebo_lo <= 0 <= g.placebo_hi
        text += f" ({render_range(g.placebo_lo, g.placebo_hi, 's')}), which {'includes' if zero else 'does not include'} zero."
        uses += ["gap.placebo_lo", "gap.placebo_hi"]
    else:
        text += "."
    return S(text, uses)


def cohort_habit_line(pk: EvidencePacket, hid: str) -> S | None:
    h = pk.cohort_habits.get(hid)
    if h is None or h.seconds < 0.5:
        return None
    uses = [f"cohort_habit.{hid}.seconds"]
    text = f"Across the cohort, {_sec(h.seconds)} per case is associated with {V.HABIT_NAME[hid]}"
    if h.lo is not None and h.hi is not None:
        text += f" ({render_range(h.lo, h.hi, 's')})."
        uses += [f"cohort_habit.{hid}.lo", f"cohort_habit.{hid}.hi"]
    else:
        text += "."
    return S(text, uses)


def counterfactual_line(pk: EvidencePacket) -> S | None:
    cands = [(hid, h) for hid, h in pk.habits.items() if h.counterfactual_s is not None and h.counterfactual_s >= 0.5]
    if not cands:
        return None
    hid, h = max(cands, key=lambda t: t[1].counterfactual_s)
    uses = [f"habit.{hid}.counterfactual_s"]
    text = f"The model estimates that fixing {V.HABIT_NAME[hid]} alone would save {_sec(h.counterfactual_s)}"
    if h.cf_lo is not None and h.cf_hi is not None:
        text += f" ({render_range(h.cf_lo, h.cf_hi, 's')})."
        uses += [f"habit.{hid}.cf_lo", f"habit.{hid}.cf_hi"]
    else:
        text += "."
    return S(text, uses)


def consequence_lines(pk: EvidencePacket) -> list[S]:
    out = []
    for step, c in pk.consequences.items():
        if c.p_error is None:
            continue
        uses = [f"consequence.{step}.p_error"]
        text = f"In the sandbox households, a wrong answer came out {render(c.p_error, 'frac')} of the time when {V.STEP_NAME[step]} was left out"
        if c.lo is not None and c.hi is not None:
            text += f" ({render_range(c.lo, c.hi, 'frac')})"
            uses += [f"consequence.{step}.lo", f"consequence.{step}.hi"]
        if c.mean_gbp is not None and c.n is not None:
            text += f"; when it was wrong the mean error was {render(c.mean_gbp, 'gbp')} a month (n = {render(c.n, 'count')} households)."
            uses += [f"consequence.{step}.mean_gbp", f"consequence.{step}.n"]
        else:
            text += "."
        out.append(S(text, uses))
    return out


def hazard_lines(pk: EvidencePacket) -> list[S]:
    h = pk.hazard
    if h is None:
        return []
    who = "a trained model" if h.source == "model" else "a simple rule"
    out: list[S] = []
    if h.peak_p is not None and h.mean_p is not None:
        text = f"Over this work the stuck reading peaked at {render(h.peak_p, 'frac')} and averaged {render(h.mean_p, 'frac')}, from {who}"
        uses = ["hazard.peak_p", "hazard.mean_p"]
        if h.alarm_threshold is not None:
            text += f"; the alarm threshold is {render(h.alarm_threshold, 'frac')}"
            uses.append("hazard.alarm_threshold")
        out.append(S(text + ".", uses + ["hazard.source"]))
    elif h.p_now is not None:
        text = f"The stuck reading was {render(h.p_now, 'frac')}, from {who}"
        uses = ["hazard.p_now", "hazard.source"]
        if h.p_lo is not None and h.p_hi is not None:
            text += f" ({render_range(h.p_lo, h.p_hi, 'frac')})"
            uses += ["hazard.p_lo", "hazard.p_hi"]
        out.append(S(text + ".", uses))
    if h.model_log_loss is not None and h.baseline_log_loss is not None:
        out.append(S(f"On held-out data the model's log loss is {render(h.model_log_loss, 'score')} against {render(h.baseline_log_loss, 'score')} "
                     "for a baseline that only uses time since progress.", ["hazard.model_log_loss", "hazard.baseline_log_loss"]))
    if h.false_alarms_per_hour is not None:
        text = f"It gives {render(h.false_alarms_per_hour, 'per_hour')} false alarms"
        uses = ["hazard.false_alarms_per_hour"]
        if h.fa_lo is not None and h.fa_hi is not None:
            text += f" ({render_range(h.fa_lo, h.fa_hi, 'per_hour')})"
            uses += ["hazard.fa_lo", "hazard.fa_hi"]
        out.append(S(text + ".", uses))
    if h.calibration in ("overconfident", "underconfident"):
        out.append(S(f"Its probabilities were found to be {h.calibration} in testing.", ["hazard.calibration"]))
    return out


def progress_line(pk: EvidencePacket) -> S | None:
    p = pk.progress
    if p is None:
        return None
    text = f"The model expects about {render(p.expected_min, 'min')} until the next progress event"
    uses = ["progress.expected_min"]
    if p.lo is not None and p.hi is not None:
        text += f" ({render_range(p.lo, p.hi, 'min')})."
        uses += ["progress.lo", "progress.hi"]
    else:
        text += "."
    return S(text, uses)


def coach_line(pk: EvidencePacket) -> S | None:
    c = pk.coach
    if c is None:
        return None
    reasons = [V.REASON_NAME[r] for r in c.reasons[:2]]
    why = f"; recorded: {' and '.join(reasons)}" if reasons else ""
    return S(f"At this moment the coach {V.ACTION_PHRASE[c.action]}, at help level {c.level}{why}.", ["coach.action", "coach.level", "coach.reasons"])


def routine_lines(pk: EvidencePacket, trust_only: bool = False, k: int = 2) -> list[S]:
    out: list[S] = []
    rows = sorted(pk.routines.items(), key=lambda t: -(t[1].minutes_per_week or 0.0))[:k]
    for kind, r in rows:
        name = V.ROUTINE_NAME[kind]
        uses = [f"routine.{kind}"]
        if not trust_only:
            bits = []
            if r.episodes is not None:
                bits.append(f"was seen {render(r.episodes, 'count')} times")
            if r.minutes_per_week is not None:
                bits.append(f"takes about {render(r.minutes_per_week, 'min')} a week")
            text = f"The routine of {name} " + (" and ".join(bits) + " and is " if bits else "is ") + V.STATUS_PHRASE[r.status] + "."
            out.append(S(text, uses))
            if r.hours_lo is not None and r.hours_hi is not None and r.horizon_weeks:
                out.append(S(f"The forecast saving from {name} is {render_range(r.hours_lo, r.hours_hi, 'h')} over the next {render(r.horizon_weeks, 'weeks')}.", uses))
        text = f"The routine of {name} is at trust rung {r.rung}"
        if r.shadow_runs:
            text += f", with {render(r.shadow_runs, 'count')} shadow runs and a lower bound of {render(r.wilson_lower, 'frac')} on its match rate"
        if r.next_rung and r.runs_to_next is not None:
            text += f"; {render(r.runs_to_next, 'count')} more clean {'run' if r.runs_to_next == 1 else 'runs'} in a row would reach rung {r.next_rung}"
        out.append(S(text + ".", uses))
    return out


def stale_lines(pk: EvidencePacket, ids: tuple[str, ...]) -> list[S]:
    """A block that is stale is said to be stale, with its age when the source gave one (an absent block is said by the intent's own
    "there is no ..." line)."""
    out: list[S] = []
    for b in ids:
        info = pk.blocks.get(b)
        if info is None or info.status != "stale":
            continue
        if info.age_s is not None:
            out.append(S(f"The {V.BLOCK_NAME[b]} is {render(info.age_s, 's')} old and stale, so read it with care.", [f"block.{b}.age_s"]))
        else:
            out.append(S(f"The {V.BLOCK_NAME[b]} is stale, so read it with care.", [f"block.{b}.status"]))
    return out


def nothing_line(what: str) -> S:
    return S(f"There is no {what} in the current data to answer that with.", [])


def _first(*xs: S | None) -> list[S]:
    return [x for x in xs if x is not None]


# ------------------------------------------------------------------------------------------------ intents
def compose(req: ExplainRequest) -> tuple[str, list[S]]:
    """``(section kind, sentences)`` for the request's intent, at most five sentences."""
    pk, q = req.packet, req.question
    it = q.intent
    out: list[S]
    kind = "answer"
    stale_for = {"where_time_went": ("genome",), "why_slow": ("genome",), "biggest_habit": ("genome",), "compare_expert": ("genome",),
                 "stuck_reading": ("hazard", "coach"), "how_sure": ("genome", "hazard"), "routine_worth": ("routines",),
                 "trust_level": ("routines",), "what_to_practise": ("genome",)}.get(it, ())
    if it == "where_time_went":
        kind = "explanation"
        out = stale_lines(pk, stale_for) + _first(case_line(pk)) + habit_lines(pk) + _first(cohort_line(pk), counterfactual_line(pk))
        out += (consequence_lines(pk)[:1] or hazard_lines(pk)[:1])
    elif it == "why_slow":
        out = stale_lines(pk, stale_for)
        if q.asked_s is not None and pk.gap is not None and pk.gap.case_s is not None and q.matches_case is False:
            out.append(S(f"You asked about {_sec(q.asked_s)}, but the record shows {_sec(pk.gap.case_s)} for this case.", ["question.asked_s", "gap.case_s"]))
        out += _first(case_line(pk)) + habit_lines(pk, 2) + _first(rank_line(pk))
        out.append(S("These are associations in the recorded steps, not proof that one thing produced the other.", []))
    elif it == "biggest_habit":
        out = stale_lines(pk, stale_for) + _first(rank_line(pk))
        pos = sorted(((hid, h) for hid, h in pk.habits.items() if h.seconds >= 0.5), key=lambda t: -t[1].seconds)
        out += _first(cohort_habit_line(pk, pos[0][0]) if pos else None)
        if not out:
            pos2 = sorted(((hid, h) for hid, h in pk.cohort_habits.items() if h.seconds >= 0.5), key=lambda t: -t[1].seconds)
            out = _first(cohort_habit_line(pk, pos2[0][0]) if pos2 else None)
    elif it == "compare_expert":
        out = stale_lines(pk, stale_for) + _first(case_line(pk), cohort_line(pk), controls_line(pk))
    elif it == "stuck_reading":
        out = stale_lines(pk, stale_for) + hazard_lines(pk)[:3] + _first(coach_line(pk), progress_line(pk))
        if not out:
            out = [nothing_line("stuck reading")]
    elif it == "how_sure":
        out = stale_lines(pk, stale_for) + _first(cohort_line(pk), controls_line(pk)) + consequence_lines(pk)[:1] + hazard_lines(pk)[1:3]
        out.append(S(f"All of this rests on {render(pk.meta.n, 'count')} {V.N_UNIT_PHRASE[pk.meta.n_unit]}.", ["meta.n"]))
    elif it == "routine_worth":
        out = stale_lines(pk, stale_for) + routine_lines(pk)
        if not out:
            out = [nothing_line("routine candidate")]
    elif it == "trust_level":
        out = stale_lines(pk, stale_for) + routine_lines(pk, trust_only=True)
        if not out:
            out = [nothing_line("routine on the trust ladder")]
    elif it == "what_to_practise":
        out = stale_lines(pk, stale_for) + habit_lines(pk, 2)[:1] + _first(counterfactual_line(pk))
        if not out:
            out = [S("Nothing stands out as a habit to work on in this data.", [])]
    else:
        out = [S(I.supported_text(), [])]
    out = out[:5]
    if not out:
        out = [nothing_line("matching evidence")]
    return kind, out


def build_reply(req: ExplainRequest) -> dict:
    kind, sents = compose(req)
    return {"sections": [{"kind": kind, "sentences": [{"text": s.text, "uses": s.uses} for s in sents]}],
            "coach_actions": default_choice(req.packet) if req.question.intent not in ("unsupported",) else []}


# ------------------------------------------------------------------------------------------------ the draft (local reword mode)
class TokenStyle(Style):
    """Records every number the templates speak and writes a marker in its place, so a draft can carry ``{field.path}`` placeholders
    instead of figures (see ``build_draft``)."""

    def __init__(self) -> None:
        self.seq: list[tuple[float, str, str]] = []

    def _mark(self, value: float, unit: str, role: str) -> str:
        self.seq.append((value, unit, role))
        return f"\x00{len(self.seq) - 1}\x00"

    def render(self, value: float, unit: str) -> str:
        return self._mark(value, unit, "point")

    def range(self, lo: float, hi: float, unit: str) -> str:
        return f"between {self._mark(lo, unit, 'lo')} and {self._mark(hi, unit, 'hi')}"


def build_draft(req: ExplainRequest) -> list[dict]:
    """The template reply with each figure replaced by the ``{field.path}`` placeholder of the field it speaks. Code writes it, from the
    packet only, so it holds no worker text and is safe to show the local model; ``provenance.expand_placeholders`` turns it back into the
    canonical text. A figure that cannot be tied to a field of its sentence is written out in full."""
    import re

    from .packet import facts

    tab = facts(req)
    style = TokenStyle()
    with use_style(style):
        _, sents = compose(req)
    out = []
    for sent in sents:
        covered = [f for u in sent.uses for f in tab.under(u)]
        used: set[str] = set()
        paths: list[str] = []

        def sub(m: "re.Match[str]") -> str:
            value, unit, role = style.seq[int(m.group(1))]
            for f in covered:
                if f.path in used or f.unit != unit or f.role != role or abs(abs(f.value) - abs(value)) > 1e-9:
                    continue
                used.add(f.path)
                paths.append(f.path)
                return "{" + f.path + "}"
            return _N.render(abs(value), unit)

        text = re.sub(r"\x00(\d+)\x00", sub, sent.text)
        out.append({"text": text, "uses": paths or list(sent.uses)})
    return out
