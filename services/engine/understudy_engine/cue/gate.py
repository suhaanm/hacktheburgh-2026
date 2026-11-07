"""The Cue decision gate (CUE-3): pure code, deterministic. Inputs in, one ``CueDecision`` and the next state out.

    kind   none      the default. Silence is a decision with a reason id, never a missing answer.
           confirm   silent: a retrieval practice step (teach and fade) or "only if asked"; the UI shows nothing until the step is done.
           cue       a tier: 1 ring on the target, 2 ring plus a chip (40 characters), 3 ghost-cursor demo (needs a target), 4 voice
                     whisper (8 words, only when the caller says ``voice_ok``).
           ask       ONE multiple-choice question per stuck episode, when the path prior or the screen is ambiguous.
           offer     a small "want a hand?" chip, only after a long stall (default 90 s) and once per episode.

Order of the rules (the first that fires wins; the reason id is the first of ``why.reasons``):
  consent, denylist/secure input (never bypassed, not even when asked) -> quiet hour or quiet hotkey -> flow (typing burst, or less
  than 2 s of quiet) -> away -> no candidates -> "I know this" -> retrieval practice (confirm) -> level 4 -> the stuck signal
  (the dignity gate of ``policy.gate``: ``need`` consecutive readings at or above ``p_signal``) -> minimum stall by level and
  mastery -> 90 s between episodes of the same skill -> hard caps (3 shown in 10 minutes, daily budget) -> ambiguity (question,
  then offer) -> tier choice with escalation 25 s after the previous tier and immediate de-escalation on progress.

A worker who ASKED bypasses quiet, flow, level 4, the stall minimum, the caps and the cooldown; never consent, the denylist or secure
input. The state is a frozen value; ``dry`` callers simply discard the returned state.

An optional ``chooser`` (the tier bandit) may pick among the actions the hard rules allow; it can silence, never exceed them.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from ..policy.gate import GateParams, GateState, gate_step
from .candidates import margin_of
from .params import DEFAULT, CueParams
from .question import ambiguity_type, build_question, can_ask
from .types import OTHER, Candidate, CueDecision, CueInput, Grounding
from .vocab import chip_text, whisper_text

NEG = -1e18
Chooser = Callable[[tuple[str, ...], str, dict], "tuple[str, float]"]
ACTIONS = ("none", "ring", "chip", "ask", "voice")       # the bandit's action set (tier 3 is rule-governed)
ASKED_FLAG = "asked"


# ------------------------------------------------------------------------------------------------ state
@dataclass(frozen=True)
class Episode:
    id: str
    anchor_t: float                  # last_progress_t when the episode opened: a later one means progress
    opened_t: float
    step_id: str
    skill: str
    tier: int = 0                    # highest tier shown
    tier_t: float = NEG              # when the current display started
    kind: str = "none"               # what the current display is: cue | ask | offer | none
    shown_n: int = 0
    first_shown_t: float | None = None
    questions: int = 0
    offers: int = 0
    options: tuple[str, ...] = ()
    answered: str | None = None
    accepted: bool = False
    dismissed: int = 0
    know_this: bool = False
    help_wanted: bool = False        # an offer was accepted or a question answered: show a cue at the next poll
    asked: bool = False              # the episode began with the worker asking
    defer_until: float = 0.0
    retrieval: bool = False
    trigger: str = "auto"
    p_first: float | None = None     # the stuck probability when the first intervention was shown
    qtype: str | None = None         # the question template in use


@dataclass(frozen=True)
class CueState:
    gate: GateState = field(default_factory=GateState)
    shown_ts: tuple[float, ...] = ()
    skill_last: tuple[tuple[str, float], ...] = ()
    know_until: tuple[tuple[str, float], ...] = ()
    day: str = ""
    budget_used: int = 0
    quiet_until: float = 0.0
    episode: Episode | None = None


@dataclass
class GateResult:
    decision: CueDecision
    state: CueState
    shown: bool = False              # a new intervention appeared on this call
    opened: bool = False             # a new episode opened on this call
    choice: dict | None = None       # bandit log: action, propensity, allowed, rule action, context


def _get(pairs: tuple[tuple[str, float], ...], key: str, default: float = NEG) -> float:
    for k, v in pairs:
        if k == key:
            return v
    return default


def _put(pairs: tuple[tuple[str, float], ...], key: str, val: float) -> tuple[tuple[str, float], ...]:
    return tuple((k, v) for k, v in pairs if k != key) + ((key, val),)


def _day(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")


def episode_id(person: str, t: float) -> str:
    return "e_" + hashlib.sha1(f"{person}|{t:.3f}".encode()).hexdigest()[:12]


def _roll(st: CueState, now: float) -> CueState:
    d = _day(now)
    return st if st.day == d else replace(st, day=d, budget_used=0)


# ------------------------------------------------------------------------------------------------ helpers
def _grounded(g: Grounding | None, step: Candidate, p: CueParams) -> bool:
    """A usable target: found, names this step (or an interchangeable one), confident, and with a box."""
    if g is None or not g.found or g.box_2d is None or g.chosen is None or g.confidence < p.ground_conf_thr:
        return False
    return g.chosen == step.id or g.chosen in {step.group}


def _target(g: Grounding | None, step: Candidate, p: CueParams) -> dict | None:
    if g is None:
        return None
    if _grounded(g, step, p):
        return {"box_2d": list(g.box_2d), "source": g.source, "confidence": round(float(g.confidence), 3)}
    return {"box_2d": None, "source": g.source if g.source in ("dom", "vision") else "none", "confidence": round(float(g.confidence), 3)}


def _step_dict(c: Candidate, reason_text) -> dict:
    d = {"id": c.id, "label": c.label, "reason_id": c.reason_id}
    d["reason_text"] = reason_text(c.reason_id) if reason_text and c.reason_id else None
    return d


def cooldown_remaining(st: CueState, inp: CueInput, p: CueParams, skill: str | None = None) -> float:
    """Seconds until the earliest moment an unrequested intervention could be allowed again (0 when nothing holds it)."""
    now = inp.now
    waits = [0.0]
    recent = sorted(t for t in st.shown_ts if now - t < p.cap_window_s)
    if len(recent) >= p.max_cues_window:
        waits.append(recent[len(recent) - p.max_cues_window] + p.cap_window_s - now)
    if skill:
        last = _get(st.skill_last, skill)
        if st.episode is None and now - last < p.skill_gap_s:
            waits.append(last + p.skill_gap_s - now)
    ep = st.episode
    if ep is not None and ep.tier > 0:
        waits.append(ep.tier_t + p.escalate_s - now)
    if now < st.quiet_until:
        waits.append(st.quiet_until - now)
    return max(0.0, max(waits))


class _B:
    """Builds the decision and result for one call."""

    def __init__(self, inp: CueInput, st: CueState, p: CueParams, reason_text) -> None:
        self.inp, self.st, self.p, self.reason_text = inp, st, p, reason_text
        c = inp.candidates
        self.top = c[0] if c else None
        self.margin = margin_of(c)

    def why(self, reasons: list[str], path_p: float | None = None, margin: float | None = None) -> dict:
        top = self.top
        return {"path_prob": round(top.p if path_p is None and top else (path_p or 0.0), 4), "margin": round(self.margin if margin is None else margin, 4),
                "p_stuck": round(float(self.inp.p_stuck), 4), "mastery": round(float(self.inp.mastery), 4), "level": int(self.inp.level),
                "reasons": reasons}

    def base(self, kind: str, reasons: list[str], **kw) -> CueDecision:
        st, inp, p = self.st, self.inp, self.p
        ep = st.episode
        d = CueDecision(kind=kind, episode_id=ep.id if ep else None, why=self.why(reasons, kw.pop("path_p", None), kw.pop("margin", None)),
                        budget_left=max(0, p.daily_budget - st.budget_used),
                        cooldown_s=round(cooldown_remaining(st, inp, p, self.top.skill if self.top else None), 1),
                        source="model" if inp.p_source == "model" else "rule")
        for k, v in kw.items():
            setattr(d, k, v)
        return d

    def none(self, reason: str, st: CueState | None = None, extra: list[str] | None = None) -> GateResult:
        if st is not None:
            self.st = st
        return GateResult(self.base("none", [reason] + (extra or [])), self.st)

    def confirm(self, extra: list[str] | None = None) -> GateResult:
        top = self.top
        d = self.base("confirm", ["retrieval_withheld"] + (extra or []), step=_step_dict(top, self.reason_text) if top else None, retrieval=True)
        return GateResult(d, self.st)


def _asked_eff(inp: CueInput, st: CueState) -> bool:
    return inp.asked or bool(st.episode and st.episode.help_wanted)


# ------------------------------------------------------------------------------------------------ the gate
def decide(inp: CueInput, st: CueState, p: CueParams = DEFAULT, *, chooser: Chooser | None = None,
           reason_text: Callable[[str | None], str | None] | None = None) -> GateResult:
    now = inp.now
    st = _roll(st, now)
    b = _B(inp, st, p, reason_text)
    ep = st.episode
    primed = GateState(p.need, st.gate.last_act_t)

    # 0. progress ends the episode at once (de-escalate); a very old episode times out
    if ep is not None:
        if inp.last_progress_t > ep.anchor_t + 1e-6:
            return b.none("progress", replace(st, episode=None, gate=GateState(0, st.gate.last_act_t)))
        if now - max(ep.opened_t, ep.tier_t if ep.tier_t > NEG / 2 else ep.opened_t) > p.episode_timeout_s:
            return b.none("timeout", replace(st, episode=None, gate=GateState(0, st.gate.last_act_t)))

    asked = _asked_eff(inp, st)
    # 1. consent and the denylist: never bypassed
    if not inp.consent:
        return b.none("no_consent")
    if inp.denied:
        return b.none("denied")
    # 2. quiet, flow, away: the worker's attention first
    if not asked and (inp.quiet_hour or now < st.quiet_until):
        return b.none("quiet")
    if not asked and (inp.typing_burst or inp.quiet_s < p.quiet_required_s):
        return b.none("flow")
    if inp.away and not asked:
        gd = gate_step(st.gate, 0.0, now, unsure=True, params=GateParams(need=p.need, cooldown_s=0.0, p_signal=p.p_signal))
        return b.none("unsure_away", replace(st, gate=gd.state))
    top = b.top
    if top is None:
        return b.none("no_candidates")
    # 3. "I know this" for this skill
    if not asked and (_get(st.know_until, top.skill) > now or (ep is not None and ep.know_this)):
        return b.none("know_this")
    # 4. retrieval practice: withhold, confirm afterwards; the long-stall offer below is the only way out
    retrieval = inp.retrieval_due and not asked
    if retrieval and inp.stall_s < p.offer_after_s:
        return b.confirm()
    # 5. level 4: the worker has it
    if inp.level >= 4 and not asked and not retrieval:
        return b.none("level_4")

    # 6. the stuck signal, an episode
    opened = False
    if ep is None:
        if asked:
            ep = Episode(episode_id(inp.person, now), inp.last_progress_t, now, top.id, top.skill, asked=True, trigger="asked", retrieval=retrieval)
            st = replace(st, episode=ep)
            b.st = st
            opened = True
        else:
            gd = gate_step(st.gate, inp.p_stuck, now, params=GateParams(need=p.need, cooldown_s=0.0, p_signal=p.p_signal))
            if not gd.act:
                return b.none("not_stuck" if gd.reason == "below_threshold" else "wait_signals", replace(st, gate=gd.state))
            if inp.stall_s < p.stall_min(inp.level, inp.mastery) and not retrieval:
                return b.none("below_stall_min", replace(st, gate=primed))
            if now - _get(st.skill_last, top.skill) < p.skill_gap_s:
                return b.none("cooldown_skill", replace(st, gate=primed))
            ep = Episode(episode_id(inp.person, now), inp.last_progress_t, now, top.id, top.skill, trigger="auto", retrieval=retrieval)
            st = replace(st, episode=ep, gate=GateState(0, now))
            b.st = st
            opened = True
    elif not asked and inp.p_stuck < p.p_signal and ep.tier > 0:
        return b.none("recovered")
    if ep.dismissed and not asked:
        return b.none("dismissed_in_episode")

    shown_so_far = ep.tier > 0 or ep.kind in ("ask", "offer")
    # 7. a display that is still up keeps being returned (not a new intervention, nothing counted)
    if shown_so_far and not asked and ep.tier_t > NEG / 2 and now - ep.tier_t < p.display_s:
        d = _again(b, ep, top, inp, p, reason_text)
        if d is not None:
            return GateResult(d, b.st)

    # 8. hard caps on anything unrequested
    if not asked:
        recent = [t for t in st.shown_ts if now - t < p.cap_window_s]
        if len(recent) >= p.max_cues_window:
            return b.none("cap_10min")
        if st.budget_used >= p.daily_budget:
            return b.none("budget_spent")
        if now < ep.defer_until:
            return b.none("deferred")
        if ep.tier > 0 and now - ep.tier_t < p.escalate_s:
            return b.none("waiting_escalation")
        if ep.kind in ("ask", "offer") and ep.tier == 0 and now - ep.tier_t < p.escalate_s:
            return b.none("waiting_escalation")

    # 9. what to say: the step, ambiguity, grounding
    g = inp.grounding
    cands = inp.candidates
    step = top
    reasons: list[str] = ["asked" if asked else "stuck_signal"]
    if ep.answered and ep.answered != OTHER:
        pick = next((c for c in cands if c.id == ep.answered or c.group == ep.answered), None)
        if pick is not None:
            step = pick
        reasons.append("answer_known")
        amb = None
    else:
        grounded0 = _grounded(g, top, p)
        amb = ambiguity_type(cands, g, margin_thr=p.margin_thr, min_path_p=p.min_path_p, confident_p=p.confident_p,
                             ground_conf_thr=p.ground_conf_thr, grounded=grounded0)
    grounded = _grounded(g, step, p)
    if grounded:
        reasons.append("grounded_dom" if g.source == "dom" else "grounded_vision")   # type: ignore[union-attr]
    else:
        reasons.append("ungrounded")
    if inp.stall_s >= p.offer_after_s:
        reasons.append("long_stall")
    ground_wanted = g is None or g.for_step is None or g.for_step != step.id

    def with_ground(d: CueDecision) -> CueDecision:
        if ground_wanted:
            d.ground_wanted = True
            d.menu = [{"id": c.id, "label": c.label} for c in cands[:4]]
        return d

    if amb is not None:
        reasons.append("path_close_call" if amb == "close_call" else ("screen_disagrees" if amb == "screen_disagrees" else "ungrounded"))
        if ep.questions < p.max_questions and can_ask(cands) and (asked or inp.stall_s >= p.stall_min(inp.level, inp.mastery)):
            q, options = build_question(cands, amb, g)
            ep2 = replace(ep, kind="ask", tier_t=now, shown_n=ep.shown_n + 1, questions=ep.questions + 1, first_shown_t=ep.first_shown_t if ep.first_shown_t is not None else now, p_first=ep.p_first if ep.p_first is not None else inp.p_stuck,
                          options=tuple(o["id"] for o in options), help_wanted=False, qtype=amb)
            st2 = _count(replace(st, episode=ep2), ep2, now, p, asked, first=ep.shown_n == 0)
            b.st = st2
            d = b.base("ask", reasons, step=_step_dict(top, reason_text), options=options, question=q, new=True,
                       say={"chip": q["text"][:40], "whisper": None}, expires_in_s=p.display_s, path_p=top.p)
            return GateResult(with_ground(d), st2, shown=True, opened=opened)
        if asked or (inp.stall_s >= p.offer_after_s and ep.offers < p.max_offers and ep.kind != "offer"):
            if not asked:
                return _offer(b, ep, top, reasons, now, p, with_ground, st, asked, opened, reason_text)
            # the worker asked and it is still ambiguous: cue the best guess, text only
        else:
            return b.none("ambiguous_after_question" if ep.questions else "below_stall_min", extra=reasons[:0])
    elif retrieval:
        return _offer(b, ep, top, reasons, now, p, with_ground, st, asked, opened, reason_text)

    # 10. the tier: start by level, escalate one step at a time, ring needs a target, voice needs voice_ok
    if ep.tier == 0:
        tier = p.start_tier(inp.level)
        if asked:
            tier = max(tier, 2)
        lvl_reason = f"level_{min(int(inp.level), 3)}"
        reasons.append(lvl_reason)
    else:
        tier = ep.tier + 1
        reasons.append("escalated")
    if tier == 1 and not grounded:
        tier = 2
    if tier == 3 and not grounded:
        tier = 4
    if tier >= 4 and not inp.voice_ok:
        reasons.append("voice_capped")
        if not asked and (ep.tier >= 3 or (ep.tier == 2 and not grounded)):
            return b.none("ladder_done", extra=["voice_capped"] + (["no_target_for_tier"] if not grounded else []))
        tier = 3 if grounded else 2
    tier = min(tier, 4)
    if tier <= ep.tier and not asked:
        return b.none("ladder_done")

    # 11. the bandit may choose among what the hard rules allow (it can silence; it cannot exceed them)
    choice = None
    rule_action = {1: "ring", 2: "chip", 3: "chip", 4: "voice"}[tier]
    if chooser is not None and not asked:
        allowed = ["none", rule_action]
        if tier == 1:
            allowed.append("chip")
        if amb is None and can_ask(cands) and ep.questions < p.max_questions and tier >= 1:
            allowed.append("ask")
        allowed_t = tuple(a for a in ACTIONS if a in allowed)
        act, prop = chooser(allowed_t, rule_action, {"p_stuck": inp.p_stuck, "margin": b.margin, "level": inp.level, "mastery": inp.mastery, "tier": tier})
        choice = {"action": act, "propensity": prop, "allowed": list(allowed_t), "rule": rule_action}
        if act == "none":
            ep3 = replace(ep, defer_until=now + p.defer_s)
            r = b.none("deferred", replace(st, episode=ep3))
            r.choice = choice
            return r
        if act == "ask":
            q, options = build_question(cands, "close_call", g)
            ep2 = replace(ep, kind="ask", tier_t=now, shown_n=ep.shown_n + 1, questions=ep.questions + 1,
                          first_shown_t=ep.first_shown_t if ep.first_shown_t is not None else now, p_first=ep.p_first if ep.p_first is not None else inp.p_stuck, options=tuple(o["id"] for o in options), qtype="close_call")
            st2 = _count(replace(st, episode=ep2), ep2, now, p, asked, first=ep.shown_n == 0)
            d = b.base("ask", reasons, step=_step_dict(top, reason_text), options=options, question=q, new=True,
                       say={"chip": q["text"][:40], "whisper": None}, expires_in_s=p.display_s)
            b.st = st2
            return GateResult(with_ground(d), st2, shown=True, opened=opened, choice=choice)
        if act == "ring" and grounded:
            tier = 1
        elif act == "chip":
            tier = max(2, tier) if ep.tier == 0 else tier
        elif act == "voice" and inp.voice_ok:
            tier = 4
    ep2 = replace(ep, tier=tier, kind="cue", tier_t=now, shown_n=ep.shown_n + 1, help_wanted=False,
                  first_shown_t=ep.first_shown_t if ep.first_shown_t is not None else now, p_first=ep.p_first if ep.p_first is not None else inp.p_stuck, step_id=step.id, skill=step.skill)
    st2 = _count(replace(st, episode=ep2), ep2, now, p, asked, first=ep.shown_n == 0)
    b.st = st2
    d = b.base("cue", reasons, step=_step_dict(step, reason_text), tier=tier, new=True, expires_in_s=p.display_s,
               target=_target(g, step, p) if tier != 2 or grounded else _target(g, step, p),
               say=_say(step, tier, inp.voice_ok), path_p=step.p if not (ep.answered and ep.answered != OTHER) else 1.0,
               margin=b.margin if not (ep.answered and ep.answered != OTHER) else 1.0)
    return GateResult(with_ground(d), st2, shown=True, opened=opened, choice=choice)


def _say(step: Candidate, tier: int, voice_ok: bool) -> dict:
    chip = chip_text(step.label) if tier >= 2 else None
    whisper = whisper_text(step.label) if (tier >= 4 and voice_ok) else None
    return {"chip": chip, "whisper": whisper}


def _count(st: CueState, ep: Episode, now: float, p: CueParams, asked: bool, first: bool) -> CueState:
    """Book a new intervention: asked ones are free of caps and budget (the caps limit what Cue does on its own)."""
    skill_last = _put(st.skill_last, ep.skill, now) if first else st.skill_last
    if asked:
        return replace(st, skill_last=skill_last)
    shown = tuple(t for t in st.shown_ts if now - t < p.cap_window_s) + (now,)
    return replace(st, shown_ts=shown, budget_used=st.budget_used + 1, skill_last=skill_last)


def _offer(b: _B, ep: Episode, top: Candidate, reasons: list[str], now: float, p: CueParams, with_ground, st: CueState,
           asked: bool, opened: bool, reason_text) -> GateResult:
    if ep.offers >= p.max_offers or b.inp.stall_s < p.offer_after_s:
        return b.none("below_stall_min" if b.inp.stall_s < p.offer_after_s else "ambiguous_after_question")
    ep2 = replace(ep, kind="offer", tier_t=now, shown_n=ep.shown_n + 1, offers=ep.offers + 1,
                  first_shown_t=ep.first_shown_t if ep.first_shown_t is not None else now, p_first=ep.p_first if ep.p_first is not None else b.inp.p_stuck)
    st2 = _count(replace(st, episode=ep2), ep2, now, p, asked, first=ep.shown_n == 0)
    b.st = st2
    d = b.base("offer", reasons + ["long_stall"] if "long_stall" not in reasons else reasons, step=_step_dict(top, reason_text), new=True,
               say={"chip": "Want a hand?", "whisper": None}, expires_in_s=p.display_s)
    return GateResult(with_ground(d), st2, shown=True, opened=opened)


def _again(b: _B, ep: Episode, top: Candidate, inp: CueInput, p: CueParams, reason_text) -> CueDecision | None:
    """The display that is still up, rebuilt from the current input (same tier, nothing new)."""
    g = inp.grounding
    step = next((c for c in inp.candidates if c.id == ep.step_id), top)
    left = round(max(0.0, p.display_s - (inp.now - ep.tier_t)), 1)
    reasons = ["persisting"]
    if ep.kind == "ask":
        cands = inp.candidates
        q, options = build_question(cands, ep.qtype or "close_call", g) if can_ask(cands) else (None, None)
        if q is None:
            return None
        opts = [{"id": o, "label": next((c.label for c in cands if c.id == o), "Something else" if o == OTHER else o)} for o in ep.options] or options
        return b.base("ask", reasons, step=_step_dict(top, reason_text), options=opts, question=q, new=False, expires_in_s=left,
                      say={"chip": q["text"][:40], "whisper": None})
    if ep.kind == "offer":
        return b.base("offer", reasons, step=_step_dict(top, reason_text), new=False, expires_in_s=left, say={"chip": "Want a hand?", "whisper": None})
    return b.base("cue", reasons, step=_step_dict(step, reason_text), tier=ep.tier, new=False, expires_in_s=left, target=_target(g, step, p),
                  say=_say(step, ep.tier, inp.voice_ok))


# ------------------------------------------------------------------------------------------------ feedback events
def apply_event(st: CueState, event: str, now: float, p: CueParams = DEFAULT, *, answer_id: str | None = None) -> CueState:
    """Fold one worker reaction into the state. Pure; unknown events raise ``ValueError``."""
    ep = st.episode
    if event not in ("shown", "accepted", "dismissed", "answered", "resolved", "abandoned", "know_this"):
        raise ValueError(f"unknown event {event!r}")
    if event in ("resolved", "abandoned"):
        return replace(st, episode=None, gate=GateState(0, st.gate.last_act_t))
    if ep is None or event == "shown":
        return st
    ended = ep.tier_t if ep.tier_t < NEG / 2 else now
    ends_now = min(ended, now - p.display_s)
    if event == "accepted":
        ep2 = replace(ep, accepted=True, tier_t=ends_now if ep.kind == "offer" else ep.tier_t, help_wanted=ep.kind == "offer",
                      kind="none" if ep.kind == "offer" else ep.kind)
    elif event == "dismissed":
        ep2 = replace(ep, dismissed=ep.dismissed + 1, tier_t=ends_now)
    elif event == "answered":
        ans = answer_id or OTHER
        ep2 = replace(ep, answered=ans, accepted=True, tier_t=ends_now, kind="none", help_wanted=ans != OTHER)
    else:  # know_this
        ep2 = replace(ep, know_this=True, tier_t=ends_now)
        return replace(st, episode=ep2, know_until=_put(st.know_until, ep.skill, now + p.know_this_hold_s))
    return replace(st, episode=ep2)


def set_quiet(st: CueState, now: float, minutes: float) -> CueState:
    return replace(st, quiet_until=max(now, now + 60.0 * max(0.0, minutes)) if minutes > 0 else 0.0)
