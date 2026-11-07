"""Run one participant through the protocol's blocks against the real pipeline, serialised on the shared sandbox sites.

    extension (real, in headless Chromium) -> isolated engine -> coach brain -> overlay drawn in the page -> participant reacts
    -> POST /coach/feedback -> score from the sandbox state exactly as ``analyze.py score`` does

One browser context per case (a fresh extension profile, so the extension's open task cannot leak between cases). One lock hold
per case on the shared sites (reset, run, read state), never across the model's thinking about a different participant.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import analysis_io
from .checks import contamination, counts_of
from .coach import CoachPoller, Mode, NudgeCounts, Shown, followed_by
from .design import BlockPlan, ParticipantSpec, household_card, load_cases
from .infra import BATCH_FLUSH_S, EngineProc, ExtBrowser, World, onboard, read_events, set_study_mode
from .observe import (HIDE_OVERLAY_JS, OVERLAY_JS, SNAPSHOT_JS, Action, Executed, clean_typed, is_submit_control, url_allowed, url_parts)
from .participant import HarnessModelError, StepContext, sleep_s

OWNER = "study-sim"
PACE_S = 2.0                 # seconds after each action (typing and reading time), so events land and the coach can see the case unfold
CAP_ACTIONS = 60             # per case (PLAN section 4); a stand-in for the 5 and 4 minute caps
WALL_CAP_S = 900             # hang guard only
LOCK_TIMEOUT_S = 3600
MAX_EMPTY = 3
MAX_ATTEMPTS = 3            # a case is restarted (same prompts, cached) if the shared sandbox was touched by someone else
COOLDOWN_S = 130            # the coach's own cooldown is 120 s

study_dir = analysis_io.STUDY
sys.path.insert(0, str(study_dir))
import analyze as A  # noqa: E402  (the pre-registered analysis, imported never edited)


@dataclass
class CaseResult:
    phase: str
    block: int
    reason: str = ""
    used: int = 0
    capped: bool = False
    wall_s: float = 0.0
    executed: list[Executed] = field(default_factory=list)
    shown: list[Shown] = field(default_factory=list)
    polls: list = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    protocol_violation: str = ""
    history: list[str] = field(default_factory=list)
    state: dict | None = None
    score: tuple[int, int] | None = None
    consent_probe_events: int | None = None
    harness_error: str = ""
    attempt: int = 1


class CaseRunner:
    def __init__(self, *, spec: ParticipantSpec, world: World, engine: EngineProc, browser: ExtBrowser, policy, card: str, phase: str, block: BlockPlan,
                 note_to_self: str | None, cap: int = CAP_ACTIONS, pace: float = PACE_S, poll_s: float = 3.0, wall_cap_s: float = WALL_CAP_S) -> None:
        self.spec, self.world, self.engine, self.browser, self.policy, self.card, self.phase, self.block = spec, world, engine, browser, policy, card, phase, block
        self.urls = {'gov': world.url_gov, 'quick': world.url_quick, 'note': world.url_note}
        self.note_to_self, self.cap, self.pace, self.wall_cap_s = note_to_self, cap, pace, wall_cap_s
        self.executed: list[Executed] = []
        self.history: list[str] = []
        self.used = 0
        self.snap_id = 0
        self.snap: dict = {}
        self.page = None
        self.overlay: Shown | None = None
        self.http = httpx.AsyncClient(base_url=engine.url)
        self.poller = CoachPoller(self.http, spec.person, self.executed, interval=poll_s)
        self.res = CaseResult(phase=phase, block=block.block)
        self._prev_counts: dict | None = None
        self.poll_s = poll_s

    # ------------------------------------------------------------------ pages
    @property
    def pages(self):
        return self.browser.context.pages

    async def _tabs(self) -> list[dict]:
        out = []
        for i, p in enumerate(self.pages):
            try:
                title = await p.title()
            except Exception:  # noqa: BLE001
                title = ""
            out.append({"index": i, "url": p.url, "title": title, "active": p is self.page, "name": self._tab_name(p.url)})
        return out

    def _tab_name(self, url: str) -> str:
        port, path = url_parts(url)
        site = self.world.site_of(port)
        if path.startswith("/casenote"):
            return "Case note page"
        return {"a": "GovCalc", "b": "Quick Estimator", "c": "EntitledTo (not part of your task)"}.get(site or "", "blank page" if not url or url == "about:blank" else "other")

    async def _snapshot(self) -> dict:
        last: Exception | None = None
        for _ in range(4):
            try:
                self.snap_id += 1
                snap = await self.page.evaluate(SNAPSHOT_JS, self.snap_id)
                self.snap = snap
                return snap
            except Exception as exc:  # noqa: BLE001 - the page navigated under us: wait and retry
                last = exc
                await asyncio.sleep(0.5)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:  # noqa: BLE001
                    pass
        raise RuntimeError(f"snapshot failed: {type(last).__name__}")

    # ------------------------------------------------------------------ the coach overlay (renderer simulated, coach real)
    async def _apply_overlay(self, sh: Shown) -> bool:
        try:
            r = await self.page.evaluate(OVERLAY_JS, {"message": sh.message, "zone": sh.zone if sh.action != "nudge" else None, "action": sh.action})
            return bool(r.get("found"))
        except Exception:  # noqa: BLE001
            return False

    async def _ensure_overlay(self) -> None:
        if not self.overlay or self.overlay.outcome:
            return
        try:
            present = await self.page.evaluate("() => !!document.getElementById('__sim_overlay')")
        except Exception:  # noqa: BLE001
            return
        if not present:
            found = await self._apply_overlay(self.overlay)
            self.overlay.ring_found = bool(self.overlay.ring_found) or found

    async def _drain_coach(self) -> None:
        while not self.poller.queue.empty():
            sh = self.poller.queue.get_nowait()
            if self.overlay and not self.overlay.outcome:
                await self._resolve(self.overlay, "ignored", "dismissed")
            self.overlay = sh
            sh.ring_found = await self._apply_overlay(sh)
            sh.ring_on_arrival = sh.ring_found

    async def _resolve(self, sh: Shown, outcome: str, post: str) -> None:
        sh.outcome, sh.t_outcome = outcome, time.monotonic()
        await self.poller.feedback(sh, post)
        try:
            await self.page.evaluate(HIDE_OVERLAY_JS)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ actions
    async def _element(self, ref: int | None):
        if ref is None:
            return None
        h = await self.page.evaluate_handle("([i, id]) => (window.__simSnap === id && window.__simRefs && window.__simRefs[i]) || null", [ref, self.snap_id])
        return h.as_element()

    def _desc(self, ref: int | None) -> dict:
        return next((e for e in self.snap.get("elements", []) if e["ref"] == ref), {})

    async def _execute(self, a: Action) -> Executed:
        port, path = url_parts(self.page.url)
        d = self._desc(a.ref) if (a.ref is not None and a.kind in ("click", "fill", "select")) else {}
        rec = Executed(t=time.monotonic(), t_wall=time.time(), kind=a.kind, ok=False, dom_id=d.get("dom_id", ""), label=d.get("label", ""), port=port, site=self.world.site_of(port), path=path)
        before = self.page.url
        try:
            if a.kind == "click":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                if is_submit_control(rec.label, rec.dom_id):
                    rec.violation = "submit_attempt"          # not sent: the protocol forbids it; recorded and the case stops
                    rec.ok = False
                    return rec
                rec.extra["zone"] = await el.evaluate("e => { const z = e.closest('[data-understudy-zone]'); return z ? z.getAttribute('data-understudy-zone') : ''; }")
                await el.click(timeout=6000)
                await self._settle()
                rec.ok = True
            elif a.kind == "fill":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                typed = clean_typed(a.text or "")
                rec.extra["cleaned"] = typed != (a.text or "")
                await el.fill(typed, timeout=6000)
                rec.ok = True
            elif a.kind == "select":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                chosen = clean_typed(a.text or "")
                rec.extra["cleaned"] = chosen != (a.text or "")
                val = await el.evaluate(
                    "(e, w) => { const o = Array.from(e.options); const n = s => s.trim().toLowerCase(); w = n(w);"
                    " const m = o.find(x => n(x.text) === w || n(x.value) === w) || o.find(x => n(x.text).startsWith(w) || n(x.value).startsWith(w))"
                    " || o.find(x => n(x.text).includes(w)); return m ? m.value : null; }", chosen)
                if val is None:
                    raise RuntimeError("no such option")
                await el.select_option(value=val, timeout=4000)
                rec.ok = True
            elif a.kind == "goto":
                if not url_allowed(a.url or "", self.world.allowed_ports()):
                    raise RuntimeError("that address is not available here")
                await self.page.goto(a.url, wait_until="load", timeout=15000)
                rec.ok = True
                rec.port, rec.path = url_parts(self.page.url)
                rec.site = self.world.site_of(rec.port)
            elif a.kind == "new_tab":
                if a.url and not url_allowed(a.url, self.world.allowed_ports()):
                    raise RuntimeError("that address is not available here")
                p = await self.browser.context.new_page()
                self.page = p
                await p.bring_to_front()
                if a.url:
                    await p.goto(a.url, wait_until="load", timeout=15000)
                rec.ok = True
                rec.port, rec.path = url_parts(self.page.url)
                rec.site = self.world.site_of(rec.port)
            elif a.kind == "switch_tab":
                pgs = self.pages
                if a.ref is None or not (0 <= a.ref < len(pgs)):
                    raise RuntimeError("no such tab")
                self.page = pgs[a.ref]
                await self.page.bring_to_front()
                await asyncio.sleep(0.4)
                rec.ok = True
                rec.port, rec.path = url_parts(self.page.url)
                rec.site = self.world.site_of(rec.port)
            elif a.kind == "wait":
                await asyncio.sleep(sleep_s(a.seconds or 1))
                rec.ok = True
            elif a.kind == "dismiss_coach":
                rec.ok = True
            elif a.kind == "finish":
                rec.ok = True
        except Exception as exc:  # noqa: BLE001 - an action that fails is part of behaviour, the participant sees it as such
            rec.error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:100]
        rec.page_changed = a.kind in ("click", "goto", "new_tab", "switch_tab") and (self.page.url != before or a.kind in ("new_tab", "switch_tab"))
        return rec

    async def _settle(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.25)

    def _line(self, a: Action, rec: Executed) -> str:
        what = {"click": f"clicked \"{rec.label}\"", "fill": f"typed into \"{rec.label}\"", "select": f"chose \"{(a.text or '')[:30]}\" in \"{rec.label}\"",
                "goto": f"opened {a.url}", "new_tab": f"opened a new tab{(' at ' + a.url) if a.url else ''}", "switch_tab": f"switched to tab {a.ref}",
                "wait": f"waited {a.seconds or 1:g}s", "dismiss_coach": "closed the helper note", "finish": "said you are finished"}[a.kind]
        res = "" if rec.ok else (" -- not done: " + ("the protocol says never to press that" if rec.violation else rec.error or "failed"))
        return f"{len(self.executed)}. {what}{res}"

    async def _after_save(self) -> None:
        """The case ends when the draft is saved (the stopwatch stops), but the saved note page shows the forbidden button, so the participant
        gets one more look: if it tries to press 'Submit to claimant record' that is recorded as a protocol violation (the click is not sent)."""
        await self._settle()
        snap = await self._snapshot()
        ctx = StepContext(spec=self.spec, phase=self.phase, card=self.card, obs=snap, tabs=await self._tabs(), history=self.history, used=self.used,
                          cap=self.cap, urls=self.urls, note_to_self=self.note_to_self, coach=None, ring_found=False)
        for a in await self.policy.decide(ctx):
            if a.kind == "click":
                d = self._desc(a.ref)
                if is_submit_control(d.get("label", ""), d.get("dom_id", "")):
                    port, path = url_parts(self.page.url)
                    rec = Executed(t=time.monotonic(), t_wall=time.time(), kind="click", ok=False, dom_id=d.get("dom_id", ""), label=d.get("label", ""),
                                   port=port, site=self.world.site_of(port), path=path, violation="submit_attempt")
                    self.executed.append(rec)
                    self.history.append(self._line(a, rec))
                    self.res.protocol_violation = "submit_attempt"
                    return
            if a.kind in ("finish",):
                return

    # ------------------------------------------------------------------ the loop
    async def run(self) -> CaseResult:
        t0 = time.monotonic()
        self.page = self.pages[0] if self.pages else await self.browser.context.new_page()
        empty = 0
        self.poller.start()
        try:
            while True:
                if self.used >= self.cap:
                    self.res.reason, self.res.capped = "cap", True
                    break
                if time.monotonic() - t0 > self.wall_cap_s:
                    self.res.reason, self.res.capped = "wall_cap", True
                    break
                st = await asyncio.to_thread(self.world.state)
                why = contamination(st, self.executed, self._prev_counts)
                self._prev_counts = counts_of(st)
                if why:
                    self.res.harness_error = "sandbox_contaminated: " + why
                    break
                await self._drain_coach()
                snap = await self._snapshot()
                await self._ensure_overlay()
                ctx = StepContext(spec=self.spec, phase=self.phase, card=self.card, obs=snap, tabs=await self._tabs(), history=self.history,
                                  used=self.used, urls=self.urls, cap=self.cap, note_to_self=self.note_to_self,
                                  coach=({"message": self.overlay.message} if self.overlay and not self.overlay.outcome else None),
                                  ring_found=bool(self.overlay and not self.overlay.outcome and snap.get("ring_in_page")))
                actions = await self.policy.decide(ctx)
                if not actions:
                    empty += 1
                    if empty >= MAX_EMPTY:
                        self.res.reason = "no_actions"
                        break
                    await asyncio.sleep(1.0)
                    continue
                empty = 0
                stop = False
                for k, a in enumerate(actions):
                    if k > 0 and (not self.poller.queue.empty()):
                        break                                       # a coach note appeared: stop and look (the rest of the plan is dropped)
                    if k > 0:
                        try:
                            if not await self.page.evaluate("(id) => window.__simSnap === id", self.snap_id):
                                break                               # the page changed under the plan
                        except Exception:  # noqa: BLE001
                            break
                    if a.kind == "finish":
                        self.res.reason = "finish"
                        stop = True
                        break
                    rec = await self._execute(a)
                    if a.kind != "dismiss_coach":
                        self.used += 1
                    self.executed.append(rec)
                    self.history.append(self._line(a, rec))
                    if rec.violation:
                        self.res.protocol_violation, self.res.reason = rec.violation, "violation"
                        stop = True
                        break
                    if a.kind == "dismiss_coach" and self.overlay and not self.overlay.outcome:
                        await self._resolve(self.overlay, "dismissed", "dismissed")
                    elif self.overlay and not self.overlay.outcome and followed_by(self.overlay.skill, rec):
                        await self._resolve(self.overlay, "followed", "followed")
                    if rec.ok and a.kind == "click" and rec.dom_id in ("save-draft", "cn-save") and url_parts(self.page.url)[1].startswith("/casenote/CN-"):
                        self.res.reason = "saved"
                        await self._after_save()
                        stop = True
                        break
                    await asyncio.sleep(self.pace)
                    if rec.page_changed:
                        break
                if stop:
                    break
        except HarnessModelError as exc:
            self.res.harness_error = f"model: {exc}"
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "BudgetExhausted":
                self.res.harness_error = "budget_exhausted"
                raise
            self.res.harness_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            self.res.errors.append(traceback.format_exc()[-400:])
        finally:
            await asyncio.sleep(BATCH_FLUSH_S)                  # let the extension's last batch land
            await self.poller.poll_once()
            await self._drain_coach()
            await self.poller.stop()
            if self.overlay and not self.overlay.outcome:
                await self._resolve(self.overlay, "ignored", "dismissed")
            await self.http.aclose()
            self.res.wall_s = round(time.monotonic() - t0, 1)
            self.res.used = self.used
            self.res.executed, self.res.shown, self.res.polls = self.executed, self.poller.shown, self.poller.polls
            self.res.violations = list(self.poller.violations)
            self.res.errors += self.poller.errors
            self.res.history = list(self.history)
        return self.res


def digest_for_note(res: CaseResult) -> str:
    lines = list(res.history[-40:])
    shown = [f"The helper app showed this note on your screen: \"{s.message}\" (you then {{}}.)".format(
        {"followed": "did what it pointed at", "dismissed": "closed it", "ignored": "carried on without acting on it"}.get(s.outcome or "", "carried on")) for s in res.shown]
    end = {"saved": "You saved a draft case note.", "finish": "You said you were finished.", "cap": "Time was called before you finished.",
           "wall_cap": "Time was called before you finished.", "violation": "You were stopped because you tried to press the forbidden button.",
           "no_actions": "You stopped."}.get(res.reason, "The case ended.")
    return "\n".join(lines + shown + [end])


# ------------------------------------------------------------------------------------------------ one participant
@dataclass
class ParticipantResult:
    spec: ParticipantSpec
    rows: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)
    exclusion: str = ""
    wall_s: float = 0.0


async def run_participant(spec: ParticipantSpec, *, world: World, pw, make_policy, outdir: Path, model_id: str, lock=(None, None), pace: float = PACE_S,
                          cap: int = CAP_ACTIONS, poll_s: float = 3.0, keep_engine: bool = False, log=print) -> ParticipantResult:
    """``make_policy(spec, case_dict, phase, world)`` returns an object with ``decide(ctx)`` and ``write_note(digest)``.
    ``lock`` = (acquire(owner, timeout), release(owner)) for the shared sandbox sites; None means the caller holds nothing (tests)."""
    t_all = time.monotonic()
    cases = load_cases()
    out = ParticipantResult(spec=spec)
    acquire, release = lock
    engine = EngineProc()
    checks: dict = {"consent_probe_events": None, "consent_off_events_after": None}
    all_shown: list[Shown] = []
    all_polls: list = []
    violations: list[str] = []
    errors: list[str] = []
    note_by_skill: dict[str, str] = {}
    exclusion = ""
    try:
        await asyncio.to_thread(engine.start)
        await asyncio.to_thread(onboard, engine.url, spec.person)
        raw_dir = outdir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        first_case = True
        contaminated_attempts: list[str] = []
        for blk in spec.blocks:
            skill_on = blk.skill_id
            for phase in ("practice", "post"):
                case_id = blk.practice_case if phase == "practice" else blk.post_case
                case = cases[case_id]
                mode = (Mode("train", blk.skill, f"{spec.pid} block {blk.block} practice") if (phase == "practice" and blk.coach_on)
                        else Mode("off", None, f"{spec.pid} block {blk.block} practice") if phase == "practice"
                        else Mode("post_test", None, f"{spec.pid} block {blk.block} post-test"))
                final: CaseResult | None = None
                policy = None
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    policy = make_policy(spec, case, phase, world)
                    browser = ExtBrowser(pw, engine.url, spec.person, world.ext_dist)
                    held = False
                    res: CaseResult | None = None
                    try:
                        if acquire:
                            await asyncio.to_thread(acquire, OWNER, LOCK_TIMEOUT_S)
                            held = True
                        if not world.up():
                            raise RuntimeError(f"the sandbox sites of world {world.name} are not up")
                        await asyncio.to_thread(world.reset)
                        await browser.open()
                        if first_case:
                            checks["consent_probe_events"] = await _consent_probe(world, browser, engine, spec.person)
                            first_case = False
                        await asyncio.to_thread(set_study_mode, engine.url, spec.person, mode.block, skill_on if mode.block == "train" else None, spec.pid, blk.block)
                        await browser.capture(True)
                        runner = CaseRunner(spec=spec, world=world, engine=engine, browser=browser, policy=policy, card=household_card(case), phase=phase, block=blk,
                                            note_to_self=note_by_skill.get(blk.skill) if phase == "post" else None, cap=cap, pace=pace, poll_s=poll_s)
                        runner.poller.mode = mode
                        res = await runner.run()
                        state = await asyncio.to_thread(world.state)
                        why = contamination(state, res.executed, runner._prev_counts, saved=(res.reason == "saved"))
                        if why and not res.harness_error:
                            res.harness_error = "sandbox_contaminated: " + why
                        if phase == "post" and not res.harness_error:
                            res.state = state
                            res.score = A.score_post_test(blk.skill, state)
                            (raw_dir / f"{spec.pid}-block{blk.block}-post.json").write_text(json.dumps(state, indent=1))
                        await browser.capture(False)
                        if blk is spec.blocks[-1] and phase == "post" and not res.harness_error:
                            checks["consent_off_events_after"] = await _consent_off_probe(world, browser, engine, spec.person)
                        errors += res.errors + browser.errors
                    except Exception as exc:  # noqa: BLE001
                        if type(exc).__name__ == "BudgetExhausted":
                            exclusion = exclusion or "budget exhausted mid-participant"
                            raise
                        res = res or CaseResult(phase=phase, block=blk.block)
                        res.harness_error = res.harness_error or f"{type(exc).__name__}: {str(exc)[:160]}"
                        errors.append(traceback.format_exc()[-500:])
                    finally:
                        try:
                            await browser.close()
                        finally:
                            if held:
                                await asyncio.to_thread(release, OWNER)
                    res.attempt = attempt
                    if res.harness_error.startswith("sandbox_contaminated") and attempt < MAX_ATTEMPTS:
                        contaminated_attempts.append(f"block {blk.block} {phase} attempt {attempt}: {res.harness_error}")
                        log(f"{spec.pid}: {contaminated_attempts[-1]} -- retrying after a pause (the model's answers are cached)")
                        quiet = COOLDOWN_S if res.shown else 20
                        await asyncio.sleep(quiet)                     # the coach's own cooldown must have passed if it spoke in the aborted attempt
                        continue
                    final = res
                    break
                assert final is not None
                out.cases.append(final)
                all_shown += final.shown
                all_polls += final.polls
                violations += final.violations
                if final.harness_error:
                    exclusion = exclusion or f"harness error in block {blk.block} {phase}: {final.harness_error}"
                elif phase == "practice":
                    note = await policy.write_note(digest_for_note(final))
                    note_by_skill[blk.skill] = note
                    out.actions.append({"participant": spec.pid, "block": blk.block, "phase": phase, "kind": "note", "text": note})
                out.actions += _action_rows(spec, blk, phase, final)
                if exclusion:
                    break
            if exclusion:
                break
        checks["contaminated_attempts"] = contaminated_attempts
        # what landed
        await asyncio.sleep(0.5)
        coached_skill_id = next((b.skill_id for b in spec.blocks if b.coach_on), None)
        checks.update(await asyncio.to_thread(analysis_io.landing_checks, engine.data, spec.person, coached_skill_id))
        checks.update(await asyncio.to_thread(_kill_check, engine, spec.person))
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "BudgetExhausted":
            exclusion = exclusion or "budget exhausted"
            raise
        exclusion = exclusion or f"harness error: {type(exc).__name__}: {str(exc)[:200]}"
        errors.append(traceback.format_exc()[-500:])
    finally:
        checks["engine_log"] = engine.log_issues()
        if not keep_engine:
            await asyncio.to_thread(engine.cleanup)
        out.exclusion = exclusion
        out.wall_s = round(time.monotonic() - t_all, 1)
    counts_by_block = _counts(out.cases, spec)
    checks["coach"] = {"shown": [analysis_io.shown_row(s) for s in all_shown], "polls": len(all_polls),
                       "p_source": {k: sum(1 for p in all_polls if p.p_source == k) for k in {p.p_source for p in all_polls}},
                       "decisions_non_silent": sum(1 for p in all_polls if p.action != "silent"),
                       "polls_by_mode": {m: sum(1 for p in all_polls if p.mode == m) for m in ("train", "post_test", "off")},
                       "non_silent_by_mode": {m: sum(1 for p in all_polls if p.mode == m and p.action != "silent") for m in ("train", "post_test", "off")}}
    checks["study_mode_violations"] = violations
    fills = [e for c in out.cases for e in c.executed if e.kind in ("fill", "select")]
    checks["typed_values_cleaned"] = {"fills_and_selects": len(fills), "cleaned": sum(1 for e in fills if e.extra.get("cleaned"))}
    checks["errors"] = errors
    out.checks = checks
    out.rows = analysis_io.block_rows(spec, out.cases, counts_by_block, model_id, exclusion, wall_by_case=None)
    return out


def _counts(cases: list[CaseResult], spec: ParticipantSpec) -> dict[int, NudgeCounts]:
    by: dict[int, NudgeCounts] = {}
    for c in cases:
        if c.phase == "practice":
            by[c.block] = NudgeCounts.of(c.shown)
    return by


def _action_rows(spec: ParticipantSpec, blk: BlockPlan, phase: str, res: CaseResult) -> list[dict]:
    rows = []
    for i, e in enumerate(res.executed, start=1):
        rows.append({"participant": spec.pid, "block": blk.block, "phase": phase, "i": i, "kind": e.kind, "ok": e.ok, "dom_id": e.dom_id,
                     "zone": e.extra.get("zone", ""), "port": e.port, "path": e.path, "violation": e.violation, "error": e.error[:40],
                     "cleaned": bool(e.extra.get("cleaned"))})
    for s in res.shown:
        rows.append({"participant": spec.pid, "block": blk.block, "phase": phase, "kind": "coach_shown", **analysis_io.shown_row(s)})
    return rows


async def _consent_probe(world: World, browser: ExtBrowser, engine: EngineProc, person: str) -> int:
    """Consent toggle OFF: browse a calculator page and type into it; the extension must send nothing."""
    page = browser.context.pages[0] if browser.context.pages else await browser.context.new_page()
    await page.goto(world.url_gov, wait_until="load")
    try:
        await page.fill("[name='your_age']", "40", timeout=3000)
        await page.click("#continue", timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(BATCH_FLUSH_S)
    n = len(await asyncio.to_thread(read_events, engine.url, person))
    await page.goto("about:blank")
    return n


async def _consent_off_probe(world: World, browser: ExtBrowser, engine: EngineProc, person: str) -> int:
    """After the consent toggle is switched OFF again: browse and type; the number of events must not grow. Returns the growth."""
    n0 = len(await asyncio.to_thread(read_events, engine.url, person))
    page = browser.context.pages[0]
    await page.goto(world.url_gov, wait_until="load")
    try:
        await page.fill("[name='your_age']", "41", timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(BATCH_FLUSH_S)
    return len(await asyncio.to_thread(read_events, engine.url, person)) - n0


def _kill_check(engine: EngineProc, person: str) -> dict:
    """Write the kill flag in the ISOLATED data dir (never POST /kill: that would call the agent service) and see what the engine says."""
    (engine.data / "KILL").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\nstudy-sim kill-flag check\n")
    try:
        k = httpx.get(f"{engine.url}/kill", timeout=5).json()
        c = httpx.get(f"{engine.url}/coach/next", params={"person": person, "dry": "true"}, timeout=10).json().get("data", {})
        return {"kill": {"engine_reports_killed": bool(k.get("killed")), "coach_action_after_kill": c.get("action")}}
    except Exception as exc:  # noqa: BLE001
        return {"kill": {"error": type(exc).__name__}}
