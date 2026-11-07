"""The stateful side of Cue for the routes: per-person gate state, the path prior, grounding results, the ledger and the memory line.

``LiveCue.next`` turns one poll into one ``CueDecision``: read the live context, compute the candidates, call the pure gate, notice
finished steps (those become ledger rows), return the envelope. Everything stateful lives here so the gate and the maths stay pure.
Writes happen only on non-dry polls; a dry poll computes the same answer and keeps nothing.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..coach.signals import heuristic_p
from ..core import Cog
from . import fixtures, ledger as L, teach
from . import freshness as FR
from . import paths as P
from .candidates import NextStepModel, apply_intents
from .context import ContextProvider, LiveContext, StaticProvider
from .expert_data import expert_paths_for
from .gate import CueState, apply_event, decide, episode_id, set_quiet
from .params import DEFAULT, TUNED, CueParams
from .question import answer_label, valid_answer
from .types import OTHER, Candidate, CueDecision, CueInput, Grounding
from .vocab import StepVocab, get_vocab

GROUND_TTL_S = 20.0
PROACTIVITY = ("quiet", "balanced", "eager")
SEEN_EPISODES = 64
NOTE = ("Cue is rules and counts, not a model: the next step comes from what experts did (a path prior) checked against the pack's "
        "order rules; the gate is code with hard caps. Numbers are synthetic until the live study says otherwise.")


class AttentionPort(Protocol):
    """The shared attention router (one voice at a time, one daily budget). Cue's gate stays the authority for Cue's content; before a new
    cue, question or offer reaches the screen the router may say "not now". ``request`` returns True when the slot is granted."""

    def request(self, *, person: str, source: str, kind: str, tier: int | None, episode_id: str | None, now: float) -> bool: ...

    def release(self, *, person: str, source: str, episode_id: str | None, now: float, reason: str) -> None: ...


class CueError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class PersonState:
    person: str
    role: str
    state: CueState = field(default_factory=CueState)
    model: NextStepModel | None = None
    grounding: Grounding | None = None
    done_seen: dict[str, set[str]] = field(default_factory=dict)       # task id -> steps already ledgered (or present at first sight)
    confirm_seen: dict[str, set[str]] = field(default_factory=dict)    # task id -> step groups withheld for retrieval practice
    ask_hist: dict[str, tuple[str, ...]] = field(default_factory=dict) # episode id -> cog history when its question was shown
    seen_episodes: list[str] = field(default_factory=list)
    summary_written: str | None = None
    fixture: str | None = None
    fixture_t: float = 0.0
    resolved_flag: bool = False                 # a resolved or abandoned event just closed an episode: the next poll says so once


def apply_proactivity(p: CueParams, mode: str) -> CueParams:
    """Parameter presets. The hard caps (3 in 10 minutes, one question, 90 s per skill, 25 s escalation) never change."""
    if mode == "quiet":
        return p.with_(p_signal=max(p.p_signal, 0.75), stall_min_l1=p.stall_min_l1 * 1.5, stall_min_l2=p.stall_min_l2 * 1.5,
                       stall_min_l3=p.stall_min_l3 * 1.5, daily_budget=min(p.daily_budget, 6), offer_after_s=max(p.offer_after_s, 120.0))
    if mode == "eager":
        return p.with_(p_signal=min(p.p_signal, 0.50), stall_min_l1=p.stall_min_l1 * 0.75, stall_min_l2=p.stall_min_l2 * 0.75,
                       stall_min_l3=p.stall_min_l3 * 0.75, daily_budget=max(p.daily_budget, 20), offer_after_s=min(p.offer_after_s, 60.0))
    return p


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LiveCue:
    def __init__(self, *, provider: ContextProvider | None = None, ledger: L.Ledger | None = None, clock=time.time, params: CueParams | None = None,
                 models_root: Path | str | None = None, brain_getter=None, attention: AttentionPort | None = None, chooser=None) -> None:
        self.attention = attention
        self._chooser = chooser
        self._provider = provider
        self._brain_getter = brain_getter
        self.ledger = ledger or L.Ledger()
        self.clock = clock
        self.params = params or TUNED                 # the dev-tuned parameters (evals/cue/PLAN.md); the hard caps are the same in both
        self.models_root = models_root
        self._people: dict[str, PersonState] = {}
        self._models: dict[str, tuple[NextStepModel, str]] = {}
        self._cand_cache: dict = {}
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- plumbing
    @property
    def provider(self) -> ContextProvider | None:
        if self._provider is not None:
            return self._provider
        if self._brain_getter is not None:
            brain = self._brain_getter()
            if brain is not None:
                from .context import BrainProvider

                return BrainProvider(brain)
        return None

    def _base_model(self, vocab: StepVocab) -> tuple[NextStepModel, str]:
        if vocab.role not in self._models:
            paths, source = expert_paths_for(vocab, self.models_root)
            m = NextStepModel(vocab).fit(s for cases in paths.values() for s in cases)
            self._models[vocab.role] = (m, source)
        return self._models[vocab.role]

    def _person(self, person: str, vocab: StepVocab) -> PersonState:
        ps = self._people.get(person)
        if ps is None or ps.role != vocab.role:
            base, _ = self._base_model(vocab)
            model = base.clone()
            apply_intents(model, P.assist_dir() / "intents.jsonl", person)
            ps = self._people[person] = PersonState(person, vocab.role, model=model)
        return ps

    def person_of_episode(self, episode_id: str | None) -> str | None:
        if not episode_id:
            return None
        for pid, ps in self._people.items():
            if episode_id in ps.seen_episodes or (ps.state.episode and ps.state.episode.id == episode_id):
                return pid
        return None

    def reset(self, person: str | None = None) -> None:
        with self._lock:
            if person is None:
                self._people.clear()
            else:
                self._people.pop(person, None)

    # ---------------------------------------------------------------- poll
    def next(self, person: str, *, now: float | None = None, dry: bool = False, asked: bool = False, voice_ok: bool = False,
             denied: bool = False, away: bool = False, consent: bool = True, quiet_s: float | None = None, typing: bool | None = None,
             proactivity: str = "balanced", fixture: str | None = None, fixture_t: float = 0.0) -> dict[str, Any]:
        if proactivity not in PROACTIVITY:
            raise CueError(422, "invalid_request", f"proactivity must be one of {', '.join(PROACTIVITY)}.")
        with self._lock:
            t = float(now) if now is not None else self.clock()
            ctx: LiveContext | None
            if fixture is not None:
                if not P.is_mock():
                    raise CueError(404, "no_such_fixture", "Fixtures are only served in mock mode (UNDERSTUDY_MOCK=1).")
                try:
                    ctx = fixtures.build(fixture, person, fixture_t)
                except KeyError:
                    raise CueError(404, "no_such_fixture", f"No fixture {fixture!r}. Known: {', '.join(fixtures.NAMES)}.")
                t = ctx.fixture["now"]  # type: ignore[index]
            else:
                prov = self.provider
                ctx = prov.read(person, t) if prov is not None else None
            if ctx is None or not ctx.task_open or not ctx.cogs:
                return self._envelope(self._silent("no_context", ctx.origin if ctx else "synthetic"), person, ctx.role if ctx else None, ctx)
            vocab = get_vocab(ctx.role)
            if vocab is None:
                return self._envelope(self._silent("no_context", ctx.origin), person, ctx.role, ctx)
            ps = self._person(person, vocab)
            if fixture is not None:                  # a fixture restarts when its name changes or its clock goes backwards
                if ps.fixture != fixture or fixture_t < ps.fixture_t:
                    ps.state, ps.done_seen, ps.confirm_seen, ps.ask_hist = CueState(), {}, {}, {}
                ps.fixture, ps.fixture_t = fixture, fixture_t
            params = apply_proactivity(self.params, proactivity)
            hist = ctx.cog_ids[-FR.MAX_WINDOW_COGS:]              # a bounded window of the open task's cogs, never an event log
            stale: list[str] = []
            cands = self._cached_candidates(ps, hist)
            if ctx.t is not None and fixture is None:
                age = t - ctx.t
                if age > FR.MAX_AGE_S["snapshot"]:
                    return self._envelope(self._silent("stale_input", ctx.origin, stale=["snapshot"]), person, ctx.role, ctx)
                if not FR.is_fresh("p_stuck", age):
                    stale.append("p_stuck")
            fx = ctx.fixture or {}
            if fx.get("candidates"):
                cands = [self._fixture_cand(vocab, sid, p) for sid, p in fx["candidates"]]
            teach_payload, step_done = None, False
            if not dry:
                teach_payload, step_done = self._detect_occurrences(ps, vocab, ctx, t)
            top = cands[0] if cands else None
            cog_levels = [ctx.level.get(c, 1) for c in (top.cogs if top else ())]
            level = int(fx.get("level") or (min(cog_levels) if cog_levels else 1))
            cog_mast = [ctx.mastery.get(c, 0.15) for c in (top.cogs if top else ())]
            mastery = float(fx.get("mastery") if fx.get("mastery") is not None else (min(cog_mast) if cog_mast else 0.15))
            last_prog = ctx.last_progress_t if ctx.last_progress_t is not None else (ctx.task_t0 or ctx.cogs[0][1])
            stall = max(0.0, t - last_prog)
            use_ctx_p = ctx.p_stuck is not None and "p_stuck" not in stale
            p_stuck, p_src = (ctx.p_stuck, ctx.p_source) if use_ctx_p else (heuristic_p(stall), "rule")
            if quiet_s is not None:
                qs = quiet_s
            elif ctx.last_input_t is not None:
                qs = t - ctx.last_input_t
            else:
                qs = 10.0
                stale.append("input_rhythm")                      # missing, marked rather than silently defaulted
            burst = bool(typing) if typing is not None else qs < params.quiet_required_s
            retrieval = bool(fx.get("retrieval_due", False)) if fixture else self._retrieval_due(person, top, t)
            ground = self._grounding_for(ps, top, t, fx)
            if ground is None and ps.grounding is not None and not fx and fixture is None:
                stale.append("grounding")                         # a result existed but was too old or for another step: dropped, marked
            inp = CueInput(now=t, person=person, role=ctx.role, p_stuck=float(p_stuck), p_source=p_src or "rule", last_progress_t=last_prog,
                           candidates=tuple(cands), level=level, mastery=mastery, grounding=ground, quiet_s=float(qs), typing_burst=burst, away=away,
                           consent=consent, denied=denied, asked=asked, voice_ok=voice_ok, retrieval_due=retrieval, stale=tuple(stale))
            if step_done or ps.resolved_flag:                       # the desktop learns a cue is over from a stable reason code
                if step_done and self.attention is not None and ps.state.episode is None:
                    self._release(person, None, t, "step_done")
                d0 = self._silent("step_done" if step_done else "resolved", ctx.origin, stale=stale or None)
                d0.teach = teach_payload
                ps.resolved_flag = False
                if step_done:
                    d0.why["reasons"] = ["step_done", "progress"]
                return self._envelope(d0, person, ctx.role, ctx)
            res = decide(inp, ps.state, params, reason_text=vocab.text_of, step_target=vocab.target, chooser=self._get_chooser())
            d = res.decision
            if res.choice is not None and not dry:
                self._log_choice(res.choice, inp)
            if res.shown and self.attention is not None and not dry:
                granted = False
                try:
                    granted = bool(self.attention.request(person=person, source="cue", kind=d.kind, tier=d.tier, episode_id=d.episode_id, now=t))
                except Exception:
                    granted = False                                  # a router that fails is a router that says no: silence is the safe default
                if not granted:                                      # not committed: the same decision can be offered again at the next poll
                    held = self._silent("attention_hold", ctx.origin, stale=stale or None)
                    held.episode_id = d.episode_id
                    return self._envelope(held, person, ctx.role, ctx)
            d.manifest = {"inputs_read": ["snapshot", "p_stuck", "input_rhythm", "candidates", "progress"] + (["grounding"] if ground is not None else []),
                          "inputs_stale": list(stale), "caps": {"window_cogs": FR.MAX_WINDOW_COGS, "ledger_rows": FR.MAX_LEDGER_ROWS_PER_SKILL}}
            if teach_payload is not None:
                d.teach = teach_payload
            if not dry:
                ps.state = res.state
                if res.state.episode is not None:
                    eid = res.state.episode.id
                    if eid not in ps.seen_episodes:
                        ps.seen_episodes = (ps.seen_episodes + [eid])[-SEEN_EPISODES:]
                    if d.kind == "ask":
                        ps.ask_hist[eid] = tuple(hist)
                if d.kind == "confirm" and top is not None:
                    ps.confirm_seen.setdefault(ctx.task_id or "", set()).add(top.group)
            return self._envelope(d, person, ctx.role, ctx)

    def _get_chooser(self):
        """The tier bandit, OFF unless the caller passed one or UNDERSTUDY_CUE_BANDIT=1 (exploration with logged propensities, no learning)."""
        if self._chooser is None and os.environ.get("UNDERSTUDY_CUE_BANDIT", "").strip().lower() in ("1", "true", "yes", "on"):
            from .tierbandit import EpsRuleChooser

            self._chooser = EpsRuleChooser()
        return self._chooser

    def _log_choice(self, choice: dict, inp) -> None:
        """Enums and numbers only: the allowed set, the action, its propensity and the context buckets. One line per decision opportunity."""
        from .tierbandit import context_index

        line = {"action": choice["action"], "rule": choice["rule"], "allowed": choice["allowed"], "propensity": round(float(choice["propensity"]), 4),
                "cell": context_index(inp.p_stuck, inp.candidates[0].p - (inp.candidates[1].p if len(inp.candidates) > 1 else 0.0), inp.level, inp.mastery)}
        try:
            p = P.assist_dir() / "choices.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, sort_keys=True) + "\n")
        except OSError:
            pass

    @staticmethod
    def _fixture_cand(vocab: StepVocab, sid: str, p: float) -> Candidate:
        return Candidate(id=sid, group=vocab.group(sid), label=vocab.label(sid), p=float(p), skill=vocab.skill(sid), reason_id=vocab.reason_id(sid), cogs=vocab.cogs(sid))

    def _silent(self, reason: str, origin: str, stale: list[str] | None = None) -> CueDecision:
        d = CueDecision(kind="none", why={"path_prob": 0.0, "margin": 0.0, "p_stuck": 0.0, "mastery": 0.0, "level": 1, "reasons": [reason]},
                        budget_left=self.params.daily_budget, stale=stale)
        return d

    def _cached_candidates(self, ps: PersonState, hist: tuple[str, ...]) -> list[Candidate]:
        """The candidate list for this cog window; recomputed only when the window changes (the last cog changes)."""
        key = (ps.role, tuple(hist))
        hit = self._cand_cache.get(key)
        if hit is None:
            hit = ps.model.candidates(tuple(hist))[0]              # type: ignore[union-attr]
            if len(self._cand_cache) >= FR.CANDIDATE_CACHE:
                self._cand_cache.pop(next(iter(self._cand_cache)))
            self._cand_cache[key] = hit
        return hit

    def _envelope(self, d: CueDecision, person: str, role: str | None, ctx: LiveContext | None) -> dict[str, Any]:
        n = len([r for r in self.ledger.rows(person, "assist")])
        meta = {"origin": (ctx.origin if ctx else "synthetic"), "n": n, "n_unit": "occurrences", "split": None, "interval_level": 0.95,
                "note": NOTE, "generated_at": _iso(self.clock())}
        d.meta = meta
        return {"meta": meta, "data": d.to_dict()}

    # ---------------------------------------------------------------- grounding
    def set_grounding(self, person: str, g: Grounding, now: float | None = None) -> None:
        with self._lock:
            ps = self._people.get(person)
            if ps is None:
                ps = self._people[person] = PersonState(person, "")
            ps.grounding = Grounding(found=g.found, chosen=g.chosen, available=g.available, box_2d=g.box_2d, confidence=g.confidence, source=g.source,
                                     for_step=g.for_step, t=self.clock() if now is None else now)

    def _grounding_for(self, ps: PersonState, top: Candidate | None, t: float, fx: dict) -> Grounding | None:
        if fx.get("grounding") is not None:
            g = fx["grounding"]
            return Grounding(found=g["found"], chosen=g["chosen"], available=tuple(g["available"]),
                             box_2d=tuple(g["box_2d"]) if g["box_2d"] else None, confidence=g["confidence"], source=g["source"], for_step=g["for_step"], t=t)
        if "grounding" in fx or top is None:
            return None
        g = ps.grounding
        if g is None or g.t is None or t - g.t > GROUND_TTL_S or g.for_step not in (top.id, top.group):
            return None
        return g

    # ---------------------------------------------------------------- retrieval and teaching
    def _retrieval_due(self, person: str, top: Candidate | None, now: float) -> bool:
        if top is None:
            return False
        rows = self.ledger.rows(person, "assist", skill=top.skill, limit=FR.MAX_LEDGER_ROWS_PER_SKILL, newest_first=True)[::-1]    # keyed by skill, capped
        return teach.retrieval_due(teach.skill_memory(rows, now), now)

    # ---------------------------------------------------------------- occurrences -> ledger rows
    def _detect_occurrences(self, ps: PersonState, vocab: StepVocab, ctx: LiveContext, now: float) -> tuple[dict | None, bool]:
        policy = vocab.policy
        cogs = [Cog(t0, ctx.cogs[i + 1][1] if i + 1 < len(ctx.cogs) else max(now, t0), c) for i, (c, t0) in enumerate(ctx.cogs)]
        prog = policy.track(cogs)
        task = ctx.task_id or ""
        seen = ps.done_seen.get(task)
        if seen is None:                                       # first sight of this task: what is already done was not watched
            ps.done_seen[task] = set(prog.done)
            return None, False
        late = {m for v in prog.violations for m in v.missing}
        out_teach = None
        step_done = False
        for sid in policy.order:
            if sid not in prog.done or sid in seen:
                continue
            seen.add(sid)
            occ = prog.occurrences[sid]
            step = policy.steps[sid]
            skill = vocab.skill(sid)
            ep = ps.state.episode
            about = ep is not None and (ep.step_id == sid or vocab.group(ep.step_id) == vocab.group(sid))
            shown = bool(about and ep.shown_n > 0)           # type: ignore[union-attr]
            followed = (occ.t1 - ep.tier_t) if (about and ep.tier_t > -1e17) else None   # type: ignore[union-attr]
            accepted = bool(about and (ep.accepted or ep.answered is not None))              # type: ignore[union-attr]
            outcome = L.classify_outcome(completed=True, error=sid in late, accepted=accepted, answered=False,
                                         followed_within_s=followed if shown else None)
            retrieval = vocab.group(sid) in ps.confirm_seen.get(task, set()) and not accepted and not shown
            rows = self.ledger.rows(ctx.person, "assist", skill=skill)
            taught = outcome == "assisted" and teach.reason_due(rows, now)
            lvls = [ctx.level.get(c, 1) for c in step.cogs]
            lvl = min(lvls) if lvls else None
            dur = occ.t1 - occ.t0
            lost = (dur - step.median_s) if step.median_s is not None else None
            row = L.make_row(
                person=ctx.person, role=ctx.role, skill=skill, step=sid, t=now, outcome=outcome, origin=ctx.origin if ctx.origin in ("real", "synthetic") else "real",
                trigger=(ep.trigger if shown else "none") if about else "none", tier=(ep.tier if about else 0),             # type: ignore[union-attr]
                options_shown=max(0, len(ep.options) - 1) if about and ep.options else 0,                               # type: ignore[union-attr]
                answer_id=ep.answered if about else None, accepted=accepted or (outcome == "assisted"),                  # type: ignore[union-attr]
                dismissed=bool(about and ep.dismissed), seconds_to_progress=(now - ep.first_shown_t) if shown and ep.first_shown_t is not None else None,  # type: ignore[union-attr]
                lost_s=lost, p_stuck=ep.p_first if shown else None, level_before=lvl, level_after=lvl, taught=taught, retrieval=retrieval)  # type: ignore[union-attr]
            self.ledger.append(row)
            if taught:
                out_teach = {"reason_id": vocab.reason_id(sid), "text": vocab.text_of(vocab.reason_id(sid))}
            if about:
                step_done = True
                ps.state = apply_event(ps.state, "resolved", now, self.params)
        return out_teach, step_done

    # ---------------------------------------------------------------- feedback
    def feedback(self, person: str, event: str, *, episode_id: str | None = None, answer_id: str | None = None, seconds: float | None = None,
                 now: float | None = None, how: str | None = None) -> dict[str, Any]:
        from .types import FEEDBACK_EVENTS

        if event not in FEEDBACK_EVENTS:
            raise CueError(422, "bad_event", f"event must be one of {', '.join(FEEDBACK_EVENTS)}.")
        with self._lock:
            t = float(now) if now is not None else self.clock()
            ps = self._people.get(person)
            if ps is None or not ps.role:
                raise CueError(404, "no_such_episode", "Cue has no state for that person yet.")
            ep = ps.state.episode
            if episode_id is not None and (ep is None or ep.id != episode_id):
                if episode_id not in ps.seen_episodes:
                    raise CueError(404, "no_such_episode", f"There is no Cue episode {episode_id}.")
                return {"episode_id": episode_id, "event": event, "recorded": False, "note": "that episode has already ended"}
            if event == "answered":
                if ep is None or not ep.options or not valid_answer(ep.options, answer_id or ""):
                    raise CueError(422, "bad_answer", "answer_id must be one of the options of the question that was asked.")
                hist = ps.ask_hist.get(ep.id, ())
                vocab = get_vocab(ps.role)
                labelled = False
                if vocab is not None and answer_id != OTHER and ps.model is not None:
                    labelled = answer_label(ps.model, hist, answer_id)          # type: ignore[arg-type]
                    if labelled:
                        self._persist_intent(person, hist, answer_id)   # type: ignore[arg-type]
                ps.state = apply_event(ps.state, "answered", t, self.params, answer_id=answer_id)
                return {"episode_id": ep.id, "event": event, "recorded": True, "intent_label": labelled}
            if event == "abandoned" and ep is not None and ep.shown_n > 0:
                self._write_abandoned(ps, ep, t)
            ps.state = apply_event(ps.state, event, t, self.params, how=how)
            if event in ("resolved", "abandoned") and ep is not None:
                ps.resolved_flag = True
            if event in ("resolved", "abandoned", "dismissed", "know_this") and self.attention is not None and ep is not None:
                self._release(person, ep.id, t, event)
            out: dict[str, Any] = {"episode_id": episode_id or (ep.id if ep else None), "event": event, "recorded": ep is not None or event in ("resolved", "abandoned", "shown")}
            if event in ("resolved", "abandoned"):
                out["memory_summary"] = self.refresh_memory_summary(person)
            return out

    def _release(self, person: str, episode_id: str | None, t: float, reason: str) -> None:
        try:
            self.attention.release(person=person, source="cue", episode_id=episode_id, now=t, reason=reason)       # type: ignore[union-attr]
        except Exception:
            pass

    def _write_abandoned(self, ps: PersonState, ep, t: float) -> None:
        vocab = get_vocab(ps.role)
        if vocab is None:
            return
        ctx = None
        row = L.make_row(person=ps.person, role=ps.role, skill=ep.skill, step=ep.step_id, t=t, outcome="abandoned", origin="real",
                         trigger=ep.trigger, tier=ep.tier, options_shown=max(0, len(ep.options) - 1) if ep.options else 0, answer_id=ep.answered,
                         accepted=ep.accepted, dismissed=bool(ep.dismissed), p_stuck=ep.p_first)
        self.ledger.append(row)

    def _persist_intent(self, person: str, hist: tuple[str, ...], step: str, k: int | None = None) -> None:
        """Stores cog ids and a step id only (pack vocabulary), the open task's bounded window, so the answer can be replayed on a fresh model."""
        p = P.assist_dir() / "intents.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"person": person, "ctx": list(hist)[-FR.MAX_WINDOW_COGS:], "step": step, "w": 3.0}, sort_keys=True) + "\n"
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line)

    def quiet(self, person: str, minutes: float, now: float | None = None) -> dict[str, Any]:
        with self._lock:
            ps = self._people.get(person)
            if ps is None:
                ps = self._people[person] = PersonState(person, "")
            t = float(now) if now is not None else self.clock()
            ps.state = set_quiet(ps.state, t, minutes)
            return {"person": person, "quiet_until": _iso(ps.state.quiet_until) if ps.state.quiet_until else None, "minutes": minutes}

    # ---------------------------------------------------------------- delete and the memory line
    def delete_ledger(self, person: str | None, actor: str = "human") -> dict[str, Any]:
        with self._lock:
            counts = self.ledger.delete(person, actor=actor)
            intents = P.assist_dir() / "intents.jsonl"
            n_intents = 0
            if intents.is_file():
                keep = []
                for line in intents.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if person is None or row.get("person") == person:
                        n_intents += 1
                    else:
                        keep.append(line)
                intents.write_text("".join(k + "\n" for k in keep), encoding="utf-8")
            memory_removed = self._remove_memory_summary()
            self.reset(person)
            return {"deleted": counts, "intents_deleted": n_intents, "memory_summary_removed": memory_removed, "audit_line": True}

    SUMMARY_ID = "l_cue_summary"

    def refresh_memory_summary(self, person: str) -> bool:
        """One line in the worker's memory file (Skill state): how often help was needed, from the ledger. Worker actor only; a
        line the worker deleted by hand stays deleted until the next assist row. Never raises."""
        try:
            from ..memory import MemoryStore
            from .score import summary_line

            rows = self.ledger.rows(person, "assist")
            if not rows:
                return False
            text = summary_line(rows)
            store = MemoryStore()
            doc = store.read()
            hit = doc.find(self.SUMMARY_ID)
            if hit is None:
                store.add_line("Skill state", text, actor="worker", note="written by Cue from your assist ledger; delete it any time", line_id=self.SUMMARY_ID)
            else:
                store.update_line(self.SUMMARY_ID, actor="worker", text=text)
            return True
        except Exception:
            return False

    def _remove_memory_summary(self) -> bool:
        try:
            from ..memory import MemoryStore

            store = MemoryStore()
            if not store.exists():
                return False
            if store.read().find(self.SUMMARY_ID) is None:
                return False
            store.forget(self.SUMMARY_ID, actor="worker")
            return True
        except Exception:
            return False
