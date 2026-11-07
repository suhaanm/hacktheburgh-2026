"""Run one participant through the pre-registered blocks against the real pipeline in a private world:

    extension (real, in headless Chromium) -> isolated engine -> coach brain -> overlay drawn in the page -> participant reacts
    -> POST /coach/feedback -> the case is scored by the ORACLE of the sandbox from the state the page reported

One browser context per case (a fresh extension profile). Each case: reset the sandbox, put the engine's study mode in the case's state (train for a coached practice,
off for an uncoached one, post_test for the unassisted pre- and post-test), open the case page with capture on, let the participant act, grade, score. Mirrors
``evals/study_sim/runner.py`` (benefits); the differences are role-generic rules, one sandbox page per case (no tabs), an oracle verdict with four outcomes, and a pre-test.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from evals.study_sim import analysis_io as sim_io
from evals.study_sim.infra import BATCH_FLUSH_S, EngineProc, ExtBrowser, clean_env, onboard, read_events, snapshot_env

from .coach_roles import CoachPoller, Mode, NudgeCounts, Rules, Shown
from .design import ParticipantSpec, Slot
from .observe_roles import (HIDE_OVERLAY_JS, OVERLAY_JS, SNAPSHOT_JS, Executed, RAction, is_forbidden, match_option_js, url_allowed, url_parts)
from .participant import HarnessModelError, StepContext
from .roles import cfg, skill_pack_id

OWNER = "study-roles"
PACE_S = 2.0
WALL_CAP_S = 900
MAX_EMPTY = 3
MAX_ATTEMPTS = 3
COOLDOWN_S = 130


# ---------------------------------------------------------------------------------------------------------------- a private world
class RoleWorld:
    """One worker's private world: its own sandbox server (own port, own process) and the extension build bound to this run. Never the shared sites."""

    def __init__(self, role: str, name: str, port: int, ext_dist: Path) -> None:
        self.role, self.name, self.port, self.ext_dist = role, name, port, Path(ext_dist)
        self.proc: subprocess.Popen | None = None
        self.log_path = Path(os.environ.get("TMPDIR", "/tmp")) / f"study-roles-{name}.log"
        self.epoch = 0

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def case_url(self, task: str, variant: int, layout: str = "", glitch: str = "") -> str:
        q = "&".join(x for x in (f"layout={layout}" if layout else "", f"glitch={glitch}" if glitch else "") if x)
        return f"{self.base}/task/{task}/{variant}" + (f"?{q}" if q else "")

    def allowed_ports(self) -> set[int]:
        return {self.port}

    def start(self, timeout: float = 40.0) -> None:
        if self.proc:
            return
        mod = cfg(self.role).module
        code = f"import time\nfrom {mod} import make_server\ns = make_server({self.port}).start()\nprint('up', flush=True)\ntime.sleep(10**7)\n"
        env, cwd = snapshot_env(clean_env({}))
        self.proc = subprocess.Popen([sys.executable, "-c", code], cwd=cwd, env=env, stdout=open(self.log_path, "ab"), stderr=subprocess.STDOUT, start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"sandbox for world {self.name} exited early; see {self.log_path}")
            if self.up():
                return
            time.sleep(0.3)
        raise RuntimeError(f"sandbox for world {self.name} did not come up")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.proc = None

    def up(self) -> bool:
        try:
            return httpx.get(f"{self.base}/healthz", timeout=2).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def reset(self) -> int:
        r = httpx.post(f"{self.base}/__reset", timeout=5)
        r.raise_for_status()
        self.epoch = int(r.json()["epoch"])
        return self.epoch

    def state(self) -> dict:
        r = httpx.get(f"{self.base}/__state", timeout=5)
        r.raise_for_status()
        return r.json()


def set_study_mode(engine_url: str, person: str, slot: Slot, participant: str, level: str = "L1") -> dict:
    body = {"person": person, "block": slot.mode, "skill_on": slot.skill_id if slot.mode == "train" else None, "level": level, "participant": participant,
            "block_no": slot.block, "steps_off": list(slot.steps_off)}
    r = httpx.post(f"{engine_url}/study/mode", json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def contamination(state: dict, expected_epoch: int, prev_events: int, own_actions: int) -> str:
    """'' when the sandbox state is explained by this participant alone, else a short reason (someone reset it, or it holds more than the participant could cause)."""
    if state.get("epoch") != expected_epoch:
        return f"the sandbox epoch changed ({expected_epoch} -> {state.get('epoch')}): someone reset it during the case"
    n = len(state.get("events", []))
    if n < prev_events:
        return f"the sandbox log shrank ({prev_events} -> {n})"
    if state.get("counts", {}).get("forbidden"):
        return "a forbidden control was pressed in the sandbox"
    return ""


@dataclass
class CaseResult:
    phase: str
    block: int
    slot: Slot | None = None
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
    verdict: dict | None = None
    harness_error: str = ""
    attempt: int = 1
    consent_probe_events: int | None = None


class CaseRunner:
    def __init__(self, *, spec: ParticipantSpec, slot: Slot, world: RoleWorld, engine: EngineProc, browser: ExtBrowser, policy, rules: Rules, note_to_self: str | None,
                 cap: int, pace: float = PACE_S, poll_s: float = 3.0, wall_cap_s: float = WALL_CAP_S, layout: str = "", glitch: str = "") -> None:
        self.spec, self.slot, self.world, self.engine, self.browser, self.policy, self.rules = spec, slot, world, engine, browser, policy, rules
        self.cfg = cfg(spec.role)
        self.note_to_self, self.cap, self.pace, self.wall_cap_s, self.layout, self.glitch = note_to_self, cap, pace, wall_cap_s, layout, glitch
        self.executed: list[Executed] = []
        self.history: list[str] = []
        self.used = 0
        self.snap_id = 0
        self.snap: dict = {}
        self.page = None
        self.overlay: Shown | None = None
        self.http = httpx.AsyncClient(base_url=engine.url)
        self.poller = CoachPoller(self.http, spec.person, self.executed, rules, interval=poll_s)
        self.res = CaseResult(phase=slot.phase, block=slot.block, slot=slot)
        self.prev_events = 0

    # ---- page
    async def _snapshot(self) -> dict:
        last: Exception | None = None
        for _ in range(4):
            try:
                self.snap_id += 1
                self.snap = await self.page.evaluate(SNAPSHOT_JS, self.snap_id)
                return self.snap
            except Exception as exc:  # noqa: BLE001 - the page navigated under us: wait and retry
                last = exc
                await asyncio.sleep(0.5)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:  # noqa: BLE001
                    pass
        raise RuntimeError(f"snapshot failed: {type(last).__name__}")

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
            self.overlay.ring_found = bool(self.overlay.ring_found) or await self._apply_overlay(self.overlay)

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

    # ---- actions
    async def _element(self, ref: int | None):
        if ref is None:
            return None
        h = await self.page.evaluate_handle("([i, id]) => (window.__simSnap === id && window.__simRefs && window.__simRefs[i]) || null", [ref, self.snap_id])
        return h.as_element()

    def _desc(self, ref: int | None) -> dict:
        return next((e for e in self.snap.get("elements", []) if e["ref"] == ref), {})

    async def _settle(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.25)

    async def _execute(self, a: RAction) -> Executed:
        port, path = url_parts(self.page.url)
        d = self._desc(a.ref) if a.ref is not None and a.kind in ("click", "fill", "select", "replace") else {}
        rec = Executed(t=time.monotonic(), t_wall=time.time(), kind=a.kind, ok=False, dom_id=d.get("dom_id", ""), label=d.get("label", ""), port=port, site="case", path=path)
        rec.extra["zone"] = d.get("zone", "")
        before = self.page.url
        try:
            if a.kind == "click":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                if is_forbidden(rec.label, rec.dom_id, self.cfg.forbidden_id, self.cfg.forbidden_label):
                    rec.violation = "forbidden_attempt"           # not sent: the facilitator said never to press that; recorded and the case stops
                    return rec
                await el.click(timeout=6000)
                await self._settle()
                rec.ok = True
            elif a.kind == "fill":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                await el.fill(a.text or "", timeout=6000)
                rec.ok = True
            elif a.kind == "replace":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                cur = await el.input_value()
                if not a.find or a.find not in cur:
                    raise RuntimeError("that text is not in the box")
                await el.fill(cur.replace(a.find, a.text or "", 1), timeout=6000)
                rec.ok = True
            elif a.kind == "select":
                el = await self._element(a.ref)
                if el is None:
                    raise RuntimeError("no such control (the page changed)")
                val = await el.evaluate(match_option_js(), a.text or "")
                if val is None:
                    raise RuntimeError("no such option")
                await el.select_option(value=val, timeout=4000)
                rec.ok = True
            elif a.kind == "goto":
                if a.url and not url_allowed(a.url, self.world.allowed_ports()):
                    raise RuntimeError("that address is not available here")
                if a.url and a.url.rstrip("/") != self.page.url.rstrip("/").split("?")[0] and "/task/" not in a.url:
                    raise RuntimeError("that address is not available here")
                await self.page.goto(a.url if a.url else self.page.url, wait_until="load", timeout=15000)      # no address: reload this page
                rec.ok = True
            elif a.kind == "wait":
                await asyncio.sleep(max(0.0, min(float(a.seconds or 1), 5.0)))
                rec.ok = True
            elif a.kind in ("dismiss_coach", "finish"):
                rec.ok = True
        except Exception as exc:  # noqa: BLE001 - an action that fails is part of behaviour, the participant sees it as such
            rec.error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:100]
        rec.page_changed = a.kind in ("click", "goto") and self.page.url != before
        return rec

    def _line(self, a: RAction, rec: Executed) -> str:
        what = {"click": f"clicked \"{rec.label}\"", "fill": f"filled \"{rec.label}\"", "replace": f"edited the text in \"{rec.label}\"",
                "select": f"chose \"{(a.text or '')[:30]}\" in \"{rec.label}\"", "goto": "reloaded the page", "wait": f"waited {a.seconds or 1:g}s",
                "dismiss_coach": "closed the helper note", "finish": "said you are finished"}[a.kind]
        res = "" if rec.ok else (" -- not done: " + ("you were told never to press that" if rec.violation else rec.error or "failed"))
        return f"{len(self.executed)}. {what}{res}"

    async def _case_done(self) -> bool:
        try:
            return bool(await self.page.evaluate("() => window.__caseDone === true"))
        except Exception:  # noqa: BLE001
            return False

    # ---- the loop
    async def run(self) -> CaseResult:
        t0 = time.monotonic()
        task, variant = self.slot.task, self.slot.variant
        self.page = self.browser.context.pages[0] if self.browser.context.pages else await self.browser.context.new_page()
        empty = 0
        try:
            await self.page.goto(self.world.case_url(task, variant, self.layout, self.glitch), wait_until="load", timeout=20000)
            self.poller.start()
            self.poller.t_start = time.monotonic()
            while True:
                if self.used >= self.cap:
                    self.res.reason, self.res.capped = "cap", True
                    break
                if time.monotonic() - t0 > self.wall_cap_s:
                    self.res.reason, self.res.capped = "wall_cap", True
                    break
                st = await asyncio.to_thread(self.world.state)
                why = contamination(st, self.world.epoch, self.prev_events, self.used)
                self.prev_events = len(st.get("events", []))
                if why and not why.startswith("a forbidden"):
                    self.res.harness_error = "sandbox_contaminated: " + why
                    break
                await self._drain_coach()
                snap = await self._snapshot()
                await self._ensure_overlay()
                coach = ({"message": self.overlay.message, "step": self.overlay.step} if self.overlay and not self.overlay.outcome else None)
                ctx = StepContext(spec=self.spec, slot=self.slot, obs=snap, history=self.history, used=self.used, cap=self.cap, note_to_self=self.note_to_self, coach=coach,
                                  ring_found=bool(coach and snap.get("ring_in_page")))
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
                    if k > 0 and not self.poller.queue.empty():
                        break                                         # a coach note appeared: stop and look (the rest of the plan is dropped)
                    if k > 0:
                        try:
                            if not await self.page.evaluate("(id) => window.__simSnap === id", self.snap_id):
                                break                                 # the page changed under the plan
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
                    elif self.overlay and not self.overlay.outcome and self.rules.followed_by(self.overlay.step, rec):
                        await self._resolve(self.overlay, "followed", "followed")
                    if rec.ok and a.kind == "click" and rec.dom_id == self.cfg.done_id and await self._case_done():
                        self.res.reason = "done"
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
            await asyncio.sleep(BATCH_FLUSH_S)                       # let the extension's last batch land
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

    async def grade(self) -> dict:
        """After the case: flush the page's log, run the sandbox's grader (hidden tests for the programmer), read the state, score with the oracle. Not part of the participant's time."""
        sb = self.cfg.sandbox
        await self.page.evaluate("() => window.__flush && window.__flush()")
        if self.spec.role == "programmer":
            await self.page.evaluate("(h) => window.__grade(h)", sb.hidden_payload(self.slot.task, self.slot.variant))
        else:
            await self.page.evaluate("() => window.__grade && window.__grade()")
        state = await asyncio.to_thread(self.world.state)
        verdict = sb.score(self.slot.task, self.slot.variant, state)
        verdict["events_logged"] = len(state.get("events", []))
        return verdict


def digest_for_note(res: CaseResult) -> str:
    lines = list(res.history[-40:])
    shown = [f"The helper app showed this note on your screen: \"{s.message}\" (you then {{}}.)".format(
        {"followed": "did what it pointed at", "dismissed": "closed it", "ignored": "carried on without acting on it"}.get(s.outcome or "", "carried on")) for s in res.shown]
    end = {"done": "You pressed the button that ends the case.", "finish": "You said you were finished.", "cap": "Time was called before you finished.",
           "wall_cap": "Time was called before you finished.", "violation": "You were stopped because you tried to press the forbidden button.", "no_actions": "You stopped."}.get(res.reason, "The case ended.")
    return "\n".join(lines + shown + [end])


# ---------------------------------------------------------------------------------------------------------------- one participant
@dataclass
class ParticipantResult:
    spec: ParticipantSpec
    rows: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)
    exclusion: str = ""
    wall_s: float = 0.0


async def run_participant(spec: ParticipantSpec, *, world: RoleWorld, pw, make_policy, outdir: Path, model_id: str, pace: float = PACE_S, cap: int | None = None, poll_s: float = 3.0,
                          layout: str = "", glitch: str = "", keep_engine: bool = False, slots: list[Slot] | None = None, on_finish=None, log=print) -> ParticipantResult:
    """``make_policy(spec, slot, phase)`` returns an object with ``decide(ctx)`` and ``write_note(digest)``. ``slots`` overrides the participant's cases (the expert
    recordings run one case); ``on_finish(engine)`` is called, in a thread, after the last case and before the engine is cleaned up (to read the stored events)."""
    from . import analysis_rows

    t_all = time.monotonic()
    c = cfg(spec.role)
    cap = cap or c.cap_actions
    rules = Rules(spec.role)
    out = ParticipantResult(spec=spec)
    engine = EngineProc()
    checks: dict = {"consent_probe_events": None, "consent_off_events_after": None}
    all_shown: list[Shown] = []
    all_polls: list = []
    violations: list[str] = []
    errors: list[str] = []
    note_by_skill: dict[str, str] = {}
    exclusion = ""
    contaminated: list[str] = []
    first_case = True
    slots = slots or spec.slots()
    try:
        await asyncio.to_thread(engine.start)
        await asyncio.to_thread(onboard, engine.url, spec.person, spec.role)
        for si, slot in enumerate(slots):
            final: CaseResult | None = None
            policy = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                policy = make_policy(spec, slot, slot.phase)
                browser = ExtBrowser(pw, engine.url, spec.person, world.ext_dist, role=spec.role)
                res: CaseResult | None = None
                try:
                    if not world.up():
                        raise RuntimeError(f"the sandbox of world {world.name} is not up")
                    await asyncio.to_thread(world.reset)
                    await browser.open()
                    if first_case:
                        checks["consent_probe_events"] = await _consent_probe(world, browser, engine, spec.person, slot, c.start_selector)
                        first_case = False
                        await asyncio.to_thread(world.reset)
                    await asyncio.to_thread(set_study_mode, engine.url, spec.person, slot, spec.pid)
                    await browser.capture(True)
                    runner = CaseRunner(spec=spec, slot=slot, world=world, engine=engine, browser=browser, policy=policy, rules=rules,
                                        note_to_self=note_by_skill.get(slot.skill) if slot.phase == "post" else None, cap=cap, pace=pace, poll_s=poll_s, layout=layout, glitch=glitch)
                    runner.poller.mode = Mode(slot.mode, slot.skill if slot.mode == "train" else None, f"{spec.pid} block {slot.block} {slot.phase}")
                    res = await runner.run()
                    if not res.harness_error:
                        res.verdict = await runner.grade()
                        st = await asyncio.to_thread(world.state)
                        why = contamination(st, world.epoch, 0, res.used)
                        if why and not why.startswith("a forbidden"):
                            res.harness_error = "sandbox_contaminated: " + why
                    await browser.capture(False)
                    if si == len(slots) - 1 and not res.harness_error:
                        checks["consent_off_events_after"] = await _consent_off_probe(world, browser, engine, spec.person, slot)
                    errors += res.errors + browser.errors
                except Exception as exc:  # noqa: BLE001
                    if type(exc).__name__ == "BudgetExhausted":
                        exclusion = exclusion or "budget exhausted mid-participant"
                        raise
                    res = res or CaseResult(phase=slot.phase, block=slot.block, slot=slot)
                    res.harness_error = res.harness_error or f"{type(exc).__name__}: {str(exc)[:160]}"
                    errors.append(traceback.format_exc()[-500:])
                finally:
                    await browser.close()
                res.attempt = attempt
                if res.harness_error.startswith("sandbox_contaminated") and attempt < MAX_ATTEMPTS:
                    contaminated.append(f"block {slot.block} {slot.phase} attempt {attempt}: {res.harness_error}")
                    log(f"{spec.pid}: {contaminated[-1]} -- retrying after a pause (the model's answers are cached)")
                    await asyncio.sleep(COOLDOWN_S if res.shown else 20)
                    continue
                final = res
                break
            assert final is not None
            out.cases.append(final)
            all_shown += final.shown
            all_polls += final.polls
            violations += final.violations
            if final.harness_error:
                exclusion = exclusion or f"harness error in block {slot.block} {slot.phase}: {final.harness_error}"
            elif slot.phase == "practice":
                note = await policy.write_note(digest_for_note(final))
                note_by_skill[slot.skill] = note
                out.actions.append({"participant": spec.pid, "block": slot.block, "phase": slot.phase, "kind": "note", "text": note})
            out.actions += _action_rows(spec, slot, final)
            if exclusion:
                break
        checks["contaminated_attempts"] = contaminated
        await asyncio.sleep(0.5)
        coached_skill_id = next((b.skill_id for b in spec.blocks if b.coach_on), None)
        checks.update(await asyncio.to_thread(sim_io.landing_checks, engine.data, spec.person, coached_skill_id))
        checks.update(await asyncio.to_thread(_kill_check, engine, spec.person))
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "BudgetExhausted":
            exclusion = exclusion or "budget exhausted"
            raise
        exclusion = exclusion or f"harness error: {type(exc).__name__}: {str(exc)[:200]}"
        errors.append(traceback.format_exc()[-500:])
    finally:
        checks["engine_log"] = engine.log_issues()
        if on_finish is not None:
            try:
                await asyncio.to_thread(on_finish, engine)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"on_finish: {type(exc).__name__}: {str(exc)[:120]}")
        if not keep_engine:
            await asyncio.to_thread(engine.cleanup)
        out.exclusion = exclusion
        out.wall_s = round(time.monotonic() - t_all, 1)
    checks["coach"] = {"shown": [sim_io.shown_row(s) for s in all_shown], "polls": len(all_polls),
                       "p_source": {k: sum(1 for p in all_polls if p.p_source == k) for k in {p.p_source for p in all_polls}},
                       "decisions_non_silent": sum(1 for p in all_polls if p.action != "silent"),
                       "polls_by_mode": {m: sum(1 for p in all_polls if p.mode == m) for m in ("train", "post_test", "off")},
                       "non_silent_by_mode": {m: sum(1 for p in all_polls if p.mode == m and p.action != "silent") for m in ("train", "post_test", "off")},
                       "reason_codes": {f"{m}/{code}": sum(1 for p in all_polls if p.mode == m and code in (p.reason_codes or [])) for m in ("train", "post_test", "off")
                                        for code in sorted({c for p in all_polls for c in (p.reason_codes or [])})}}
    checks["study_mode_violations"] = violations
    checks["errors"] = errors
    out.checks = checks
    out.rows = analysis_rows.block_rows(spec, out.cases, model_id, exclusion)
    return out


def _action_rows(spec: ParticipantSpec, slot: Slot, res: CaseResult) -> list[dict]:
    rows = []
    for i, e in enumerate(res.executed, start=1):
        rows.append({"participant": spec.pid, "block": slot.block, "phase": slot.phase, "task": slot.task, "variant": slot.variant, "i": i, "kind": e.kind, "ok": e.ok,
                     "dom_id": e.dom_id, "zone": e.extra.get("zone", ""), "violation": e.violation, "error": e.error[:40]})
    for s in res.shown:
        rows.append({"participant": spec.pid, "block": slot.block, "phase": slot.phase, "kind": "coach_shown", **sim_io.shown_row(s)})
    if res.verdict:
        rows.append({"participant": spec.pid, "block": slot.block, "phase": slot.phase, "kind": "verdict", "task": slot.task, "variant": slot.variant,
                     **{k: res.verdict[k] for k in ("outcome", "points", "claimed_done", "skill_check_done") if k in res.verdict}})
    return rows


async def _consent_probe(world: RoleWorld, browser: ExtBrowser, engine: EngineProc, person: str, slot: Slot, start_selector: str) -> int:
    """Consent toggle OFF: load a case page and press a button; the extension must send nothing."""
    page = browser.context.pages[0] if browser.context.pages else await browser.context.new_page()
    await page.goto(world.case_url(slot.task, slot.variant), wait_until="load")
    try:
        await page.locator("main button").first.click(timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(BATCH_FLUSH_S)
    n = len(await asyncio.to_thread(read_events, engine.url, person))
    await page.goto("about:blank")
    return n


async def _consent_off_probe(world: RoleWorld, browser: ExtBrowser, engine: EngineProc, person: str, slot: Slot) -> int:
    """After the consent toggle is OFF again: browse and press a button; the number of events must not grow. Returns the growth."""
    n0 = len(await asyncio.to_thread(read_events, engine.url, person))
    page = browser.context.pages[0]
    await page.goto(world.case_url(slot.task, slot.variant), wait_until="load")
    try:
        await page.locator("main button").first.click(timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(BATCH_FLUSH_S)
    return len(await asyncio.to_thread(read_events, engine.url, person)) - n0


def _kill_check(engine: EngineProc, person: str) -> dict:
    """Write the kill flag in the ISOLATED data dir (never POST /kill: that would call the agent service) and see what the engine says."""
    (engine.data / "KILL").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\nstudy-roles kill-flag check\n")
    try:
        k = httpx.get(f"{engine.url}/kill", timeout=5).json()
        co = httpx.get(f"{engine.url}/coach/next", params={"person": person, "dry": "true"}, timeout=10).json().get("data", {})
        return {"kill": {"engine_reports_killed": bool(k.get("killed")), "coach_action_after_kill": co.get("action")}}
    except Exception as exc:  # noqa: BLE001
        return {"kill": {"error": type(exc).__name__}}
