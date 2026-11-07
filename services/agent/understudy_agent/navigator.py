"""One navigator = one site task, in its own browser context (AGT-1, AGT-7, AGT-9).

The ladder (AGT-3): try tier 1 (compiled bundle). Escalate ONLY when a precondition or postcondition fails.
Recovery (AGT-7): transient error page -> reload the start page and retry tier 1, then tier 2 from scratch;
structural change -> tier 2 from where we are, then tier 2 from scratch; then tier 3 if allowed; then a human
queue item. Gate stops, injection pauses and provider safety checks are never retried.
Step cap: 20 model-driven actions per navigator (tier 2 and 3); tier-1 steps are bounded by the bundle (<= 60).
"""
from __future__ import annotations

import os
import re

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from .completion import (
    NOTE_ID_RE, REF_RE, ClaimLedger, ResultFields, parse_money, validate_result_fields,
)
from .models.port import ModelPort
from .sandbox_sites.bundles import CANONICAL_PARAMS, calculator_bundle, casenote_bundle, cliff_bundle
from .sandbox_sites.specs import CASENOTE_PATH, SITES
from .tiers.base import (
    Emit, GateStop, InjectionStop, Observation, StepBudgetExceeded, StepEvent, TierError,
)
from .tiers.browser_agent import BrowserAgent, Tier2Task
from .tiers.computer_use import Actuator, BrowserPageActuator, ComputerUse, ProviderSafetyStop
from .tiers.facts import FactStore, calculator_field_hints, casenote_field_hints
from .tiers.form_audit import FormAudit, FormAuditStop
from .tiers.dsl import DslRuntime, run_bundle
from .tiers.observe import observe
from .tiers.safety import Guard

PARAM_HELP = {
    "adults": "number of adults in the household (1 or 2)",
    "adult1_age": "age of the first adult (the claimant)",
    "adult2_age": "age of the partner, blank if none",
    "children_ages": "ages of the children, comma separated, blank if none",
    "adult1_earnings_monthly": "the first adult's take-home pay per month",
    "adult2_earnings_monthly": "the partner's take-home pay per month",
    "limited_capability": "yes or no: a health condition limits ability to work",
    "tenure": "rent or own",
    "rent_monthly": "rent per month",
    "bedrooms": "bedrooms needed",
    "savings": "total savings",
    "childcare_monthly": "childcare costs per month",
    "case_ref": "the case reference",
    "result_a": "the figure GovCalc showed",
    "result_b": "the figure Quick Estimator showed",
    "result_c": "the figure EntitledTo showed",
    "reconciliation": "agree or discrepancy",
    "note_text": "the case note text",
}

RESULT_SCHEMA: dict[str, Any] = {
    "title": "calculator_result",
    "type": "object",
    "properties": {
        "amount_text": {"type": "string", "maxLength": 40},
        "status_text": {"type": "string", "maxLength": 60},
        "ref": {"type": "string", "maxLength": 24},
    },
    "required": ["amount_text", "status_text", "ref"],
}


# The goal of the cliff-panel step of a tier-3 calculator run (module level so that the goal-text hash of a round covers it).
CLIFF_GOAL = ("Press the button labelled Check cliff edges to open the cliff panel for this result. "
              "Say you are done once the panel with the heading Cliff edges for this household is showing.")


def form_audit_mode() -> str:
    """`full` | `readback` | `off` from UNDERSTUDY_FORM_AUDIT (anything else is `full`). See Navigator._tier3."""
    m = os.environ.get("UNDERSTUDY_FORM_AUDIT", "full").strip().lower()
    return m if m in ("full", "readback", "off") else "full"


# ----------------------------------------------------------------------------- jobs
OBSTRUCTION_JS = r"""
() => {
  document.querySelectorAll('[data-obstruction-dismiss]').forEach(e => e.removeAttribute('data-obstruction-dismiss'));
  const vis = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  for (const dlg of document.querySelectorAll('[role=dialog],[role=alertdialog],[aria-modal=true]')) {
    if (!vis(dlg)) continue;
    for (const b of dlg.querySelectorAll('button,a[href],[role=button]')) {
      const t = (b.innerText || b.getAttribute('aria-label') || '').trim();
      if (vis(b) && /^(reject|decline|no,? thanks|not now|dismiss|close|got it|maybe later|skip)/i.test(t)) {
        b.setAttribute('data-obstruction-dismiss', '1'); return t.slice(0, 80);
      }
    }
  }
  return null;
}
"""


class CalculatorJob:
    kind = "calculator"

    def __init__(self, site: str, params: dict[str, str]) -> None:
        self.site = site
        self.params = params
        self.label = SITES[site].name
        self.start_path = SITES[site].start_path
        self.allowed_params = tuple(CANONICAL_PARAMS)
        self.param_help = {k: PARAM_HELP[k] for k in self.allowed_params}
        self.goal = f"Enter this household into {self.label}. " + self.goal_words

    def bundle(self, layout: str) -> dict[str, Any]:
        return calculator_bundle(self.site, layout)

    schema = RESULT_SCHEMA
    goal_words = ("Click each field and type the matching fact, press the Tab key after a drop-down choice, and press "
                  "Continue, Next, Calculate, Show results, See entitlement or Work it out to move on. "
                  "Fill in EVERY field of the household details (adults, age, children, pay, earnings, health, rent, housing, "
                  "bedrooms, savings, childcare), then press the button that gives the estimate. Entering one field is "
                  "never the end: you are finished only when the estimate page, showing a monthly amount and a reference, "
                  "is on screen. Then reply DONE.")

    def looks_final(self, obs: Observation) -> bool:
        return bool(REF_RE.search(obs.text)) and parse_money(obs.text) is not None

    def parse(self, obs: Observation, fields: dict[str, Any] | None) -> dict[str, Any] | None:
        """Code check on what the quarantined reader returned. None = not (yet) a valid result page."""
        if not fields or self.finalize(fields) is None:
            return None
        return dict(fields)

    def finalize(self, outputs: dict[str, Any]) -> ResultFields | None:
        fields, _ = validate_result_fields(self.site, outputs)
        return fields

    def facts(self) -> FactStore:
        """The handles tier 3 may type for this site; values resolve in code at actuation time."""
        return FactStore.for_calculator(self.site, self.params)

    def final_labels(self) -> tuple[str, ...]:
        """The name(s) of the button that asks for the calculation (the last forward button, in both layouts): the pre-submit audit holds
        its press until every fact is in the form (tiers/form_audit.py). The goal text is not touched by this."""
        spec = SITES[self.site]
        return tuple(dict.fromkeys((spec.button_labels("v1")[-1], spec.button_labels("v2")[-1])))

    def forward_labels(self) -> tuple[str, ...]:
        """The buttons that move on from a page that is not the last (site A's Continue and Next, site C's Next: your money and Continue to
        finances): the form audit holds their press while a handle that belongs on the page in front of it is not entered."""
        spec = SITES[self.site]
        final = set(self.final_labels())
        return tuple(dict.fromkeys(x for layout in ("v1", "v2") for x in spec.button_labels(layout) if x not in final))

    def field_hints(self) -> dict[str, tuple[str, ...]]:
        return calculator_field_hints(self.site)


class CaseNoteJob:
    kind = "casenote"
    site = "casenote"
    label = "case note"
    start_path = CASENOTE_PATH

    def __init__(self, params: dict[str, str]) -> None:
        self.params = params
        self.allowed_params = ("case_ref", "result_a", "result_b", "result_c", "reconciliation", "note_text")
        self.param_help = {k: PARAM_HELP[k] for k in self.allowed_params}
        self.goal = "Fill in the case note form and save it as a draft. " + self.goal_words

    def bundle(self, layout: str) -> dict[str, Any]:
        return casenote_bundle(layout)

    schema = None
    goal_words = ("Click each field and type the matching fact, press the Tab key after a drop-down choice, and press "
                  "Save draft. Fill in EVERY field (the case reference, the GovCalc, Quick Estimator and EntitledTo results, the "
                  "reconciliation and the note), then press Save draft. You are finished only when the saved draft page, with "
                  "a note number and the word Draft, is on screen. Then reply DONE.")

    def looks_final(self, obs: Observation) -> bool:
        return bool(NOTE_ID_RE.search(obs.text)) and "Draft" in obs.text

    def parse(self, obs: Observation, fields: dict[str, Any] | None) -> dict[str, Any] | None:
        m = NOTE_ID_RE.search(obs.text)
        return {"note_id": m.group(0), "status": "Draft", "body": obs.text} if m else None

    def facts(self) -> FactStore:
        return FactStore.for_casenote(self.params)

    def final_labels(self) -> tuple[str, ...]:
        return ("Save draft",)

    def field_hints(self) -> dict[str, tuple[str, ...]]:
        return casenote_field_hints()

    def finalize(self, outputs: dict[str, Any]) -> dict[str, Any] | None:
        nid = str(outputs.get("note_id", ""))
        if not NOTE_ID_RE.fullmatch(nid):
            return None
        return {"note_id": nid, "status": outputs.get("status", ""), "body": outputs.get("body", "")}


# ----------------------------------------------------------------------------- result
@dataclass
class NavResult:
    nav_id: str
    site: str
    state: str = "running"          # done | escalated | failed
    value: Any = None               # ResultFields (calculator) or dict (case note)
    page: Any = None
    tiers_used: list[int] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    false_claims: int = 0
    queue_id: str | None = None
    error: str = ""
    cliff_checked: bool = False
    cliff_text: str = ""
    raw_outputs: dict[str, Any] = field(default_factory=dict)
    inputs_audit: str = "n/a"       # the form audit's verdict on what was entered (tier 3 only): n/a | unaudited | clean | mismatch | uncertain


class Navigator:
    def __init__(
        self,
        nav_id: str,
        *,
        context: Any,
        model: ModelPort,
        guard: Guard,
        base_url: str,
        emit: Emit | None = None,
        is_current: Callable[[], bool] = lambda: True,
        query: str = "",
        ledger: ClaimLedger | None = None,
        use_tier1: bool = True,
        bundle_layout: str = "v1",
        bundle: dict[str, Any] | None = None,
        max_actions: int = 150,
        allow_tier3: bool = False,
        page_state: bool = False,
        defer_cliff: bool = False,
        start_tier: int = 1,
        clear_obstructions: bool = True,
        t3_max_steps: int = 200,
        stall_limit: int = 12,
        pause: Any = None,
        actuator_factory: Callable[[Any], Actuator] | None = None,
        shot_hook: Callable[[str, bytes], None] | None = None,
        resume: dict[str, Any] | None = None,
        on_snapshot: Callable[[str, int, dict[str, Any]], None] | None = None,
    ) -> None:
        self.id, self.context, self.model, self.guard = nav_id, context, model, guard
        self.base_url, self.query = base_url.rstrip("/"), query
        self._emit_out = emit
        self.is_current = is_current
        self.ledger = ledger or ClaimLedger()
        self.use_tier1, self.bundle_layout, self.bundle_override = use_tier1, bundle_layout, bundle
        self.t_left = max_actions
        self.allow_tier3 = allow_tier3
        self.page_state, self.defer_cliff = page_state, defer_cliff
        self.start_tier, self.t3_max_steps, self.stall_limit, self.pause = start_tier, t3_max_steps, stall_limit, pause
        self.clear_obstructions = clear_obstructions
        self.obstructions_cleared = 0
        self.actuator_factory = actuator_factory or (lambda page: BrowserPageActuator(page))
        self.steps = 0
        # RESUME (LH-2): `resume = {"steps": n, "wm": <WorkingMemory.snapshot()>}` from a checkpoint. Step numbers continue from n, and the
        # first tier-3 attempt is seeded from the snapshot on what is a FRESH page (a killed browser keeps no form).
        self._wm_snap: dict[str, Any] | None = None
        if resume:
            self.steps = max(0, int(resume.get("steps", 0)))
            self._wm_snap = resume.get("wm")
        self.on_snapshot = on_snapshot
        self.wm_carried = 0                          # tier-3 attempts that started from an earlier attempt's (or a checkpoint's) memory
        self.tier3_steps = 0
        self.t3_runs: list[dict[str, Any]] = []     # one record per tier-3 attempt: outcome, counts and the model's own closing words
        self.refusals = 0
        self.tiers_used: list[int] = []
        self.last_inputs_audit = "n/a"                  # the latest tier-3 attempt's form-audit state (tiers/form_audit.py)
        self.last_audit_summary: dict[str, Any] = {}    # and its summary: enums, counts and handle ids only

    # ------------------------------------------------------------------ plumbing
    def _emit(self, ev: StepEvent) -> None:
        self.steps = max(self.steps, ev.step)
        if ev.tier not in self.tiers_used:
            self.tiers_used.append(ev.tier)
        if self._emit_out:
            self._emit_out(ev)

    def _note(self, action: str, ok: bool, detail: str, tier: int) -> None:
        self.steps += 1
        self._emit(StepEvent(navigator=self.id, step=self.steps, tier=tier, action=action, ok=ok, detail=detail))

    async def _fresh_page(self, job: Any, old: Any = None) -> Any:
        if old is not None:
            try:
                await old.close()
            except Exception:  # noqa: BLE001
                pass
        self.guard.new_page()
        page = await self.context.new_page()
        await page.goto(self.base_url + job.start_path + self.query, wait_until="domcontentloaded")
        await self._scan(page)
        if self.clear_obstructions:
            await self._clear_obstruction(page)
        return page

    async def _clear_obstruction(self, page: Any) -> bool:
        """A cookie or consent dialog in the way: press its reject, decline or close button (never accept), through the
        pipeline like any other click. Returns True if one was dismissed."""
        try:
            label = await page.evaluate(OBSTRUCTION_JS)
        except Exception:  # noqa: BLE001 - a page that cannot be inspected has nothing to dismiss
            return False
        if not label:
            return False
        sel = '[data-obstruction-dismiss="1"]'
        seen = await self.guard.observe(page, navigator=self.id, tier=1)
        dec = self.guard.authorise({"kind": "click_element", "args": {"selector": sel, "label": str(label)[:120]}}, seen,
                                   label=str(label), role="button", url=page.url)
        self.guard.require(dec, str(label), navigator=self.id)
        await page.locator(sel).click(timeout=3000)
        self.guard.record(dec, True)
        self.obstructions_cleared += 1
        self._note("dismiss_obstruction", True, "dialog", 1)
        return True

    async def _scan(self, page: Any) -> None:
        """Injection detector over visible text, hidden elements and alt text. A hit pauses the run."""
        await self.guard.observe(page, navigator=self.id, step=self.steps, tier=0)

    async def _read_final(self, page: Any, job: Any, *, fresh: bool = False) -> dict[str, Any] | None:
        """Fresh observation of the page; if it looks final, the quarantined reader and the code check decide. `fresh=True` (the
        orchestrator's verification) bypasses the reader's memo: the second read must be a second read."""
        obs = await observe(page)
        if not job.looks_final(obs):
            return None
        seen = await asyncio.to_thread(self.guard.observe_obs, obs, schema=job.schema, navigator=self.id, fresh=fresh)
        return job.parse(obs, seen.fields)

    # ------------------------------------------------------------------ tiers
    async def _tier1(self, page: Any, job: Any) -> dict[str, Any]:
        self.guard.set_mode("compiled")
        bundle = self.bundle_override or job.bundle(self.bundle_layout)
        rt = DslRuntime(page=page, params=job.params, base_url=self.base_url, query=self.query,
                        navigator=self.id, emit=self._emit, guard=self.guard, is_current=self.is_current,
                        step_start=self.steps, pre_timeout_ms=1500, post_timeout_ms=2500, pause=self.pause)
        res = await run_bundle(bundle, rt)
        await self._scan(page)  # the result page is scanned too before its numbers are trusted
        return res.outputs

    async def _tier2(self, page: Any, job: Any) -> dict[str, Any]:
        if self.t_left <= 0:
            raise StepBudgetExceeded("no model-driven actions left for this navigator")

        agent = BrowserAgent(self.model, self.guard, navigator=self.id, emit=self._emit,
                             is_current=self.is_current, step_start=self.steps, max_actions=self.t_left,
                             ledger=self.ledger, page_state=self.page_state, pause=self.pause,
                             stall_limit=self.stall_limit)
        try:
            res = await agent.run(page, Tier2Task(job.goal, job.params, job.allowed_params, job.looks_final,
                                                  job.schema, job.parse, job.param_help))
        finally:
            self.t_left -= agent.used
        assert res.outputs is not None
        return res.outputs

    def _snap(self, steps: int, snap: dict[str, Any]) -> None:
        self._wm_snap = snap
        if self.on_snapshot is not None:
            self.on_snapshot(self.id, self.steps, snap)

    async def _tier3(self, page: Any, job: Any, kept: bool = False) -> dict[str, Any]:
        """Computer use on this page: screenshots, clicks, and typed FACT HANDLES (never values). A later attempt is seeded from the
        memory of the earlier one: what code verified and the step count carry over; the handles typed on a page carry over only when
        the page is kept (`kept`), and on a fresh page every handle is pending again (page-scoped facts stay page-scoped)."""
        actuator = self.actuator_factory(page)
        vp = page.viewport_size or {"width": 1280, "height": 800}
        if self._wm_snap is not None:
            self.wm_carried += 1
        facts = job.facts()
        # The typed-input read-back and the pre-submit audit (tiers/form_audit.py). Sandbox jobs know the page's own ids for each handle and
        # the name of the final button; a job without a fact store has nothing to audit. UNDERSTUDY_FORM_AUDIT picks the arm of an A/B on the
        # development households (never the default of a confirmation): `full` (default) = read-back, pending-handles guard on the final button
        # and the Done requirement; `readback` = read-back, notes and records only, no guard and no Done requirement; `off` = nothing (the build
        # as it was at the first held-out round, as far as typing goes).
        mode = form_audit_mode()
        audit = None if (facts is None or mode == "off") else FormAudit(
            facts, final_labels=() if mode == "readback" else getattr(job, "final_labels", lambda: ())(),
            forward_labels=() if mode == "readback" else getattr(job, "forward_labels", lambda: ())(),
            field_hints=getattr(job, "field_hints", lambda: {})(), strict_stray=True)
        cu = ComputerUse(self.model, actuator, self.guard, navigator=self.id, emit=self._emit,
                         is_current=self.is_current, step_start=self.steps, max_steps=self.t3_max_steps,
                         facts=facts, stall_limit=self.stall_limit, pause=self.pause,
                         screenshot_size=(int(vp["width"]), int(vp["height"])),
                         resume_wm=self._wm_snap, page_kept=kept, on_snapshot=self._snap,
                         postcondition=f"final_page_{re.sub(r'[^a-z0-9]', '', str(job.site).lower())[:20] or 'x'}",
                         form_audit=audit)
        last: dict[str, Any] = {}

        async def verify() -> bool:
            raw = await self._read_final(page, job)
            if raw is not None:
                last.update(raw)
            return raw is not None

        def audit_record() -> dict[str, Any]:
            if audit is None or cu._audit_in_use() is None:      # no audit took part (a desktop or simulated actuator, or no handles)
                return {}
            s = audit.summary()
            return {"inputs": s["state"], "form_audit": {**{k: v for k, v in s.items() if k != "records"}, "records": s["records"][:80]},
                    "readback_failures": sum(1 for r in s["records"] if r["k"] == "readback" and r["match"] == "no")}

        try:
            res = await cu.run(job.goal, verify)
        except BaseException as exc:
            extra = audit_record()
            self.last_inputs_audit = extra.get("inputs", "n/a")
            self.last_audit_summary = extra.get("form_audit", {})
            self.t3_runs.append({"navigator": self.id, "outcome": f"stopped:{type(exc).__name__}", "steps": cu.last_steps, **extra})
            raise
        extra = audit_record()
        self.last_inputs_audit = extra.get("inputs", "n/a")
        self.last_audit_summary = extra.get("form_audit", {})
        self.t3_runs.append({"navigator": self.id, "outcome": res.outcome, "steps": res.steps, "progress_steps": res.progress_steps,
                             "refusals": res.refusals, "claimed_done": res.claimed_done, "false_claim": res.false_claim,
                             "resets": res.resets, "nudges": res.nudges, "premature_claims": res.premature_claims,
                             "prompt_chars": list(res.prompt_chars),
                             "summary": re.sub(r"\d{3,}", "#", res.last_summary or "")[:300], **extra})   # the model's own words, digit runs masked
        self.tier3_steps += res.steps
        self.refusals += res.refusals
        if res.false_claim:
            self.ledger.record(f"tier3:{self.id}", True, False, "computer-use Done not confirmed by code")
        if res.outcome != "done":
            raise TierError(f"tier 3 ended {res.outcome}")
        return last

    # ------------------------------------------------------------------ the ladder
    async def run(self, job: Any) -> NavResult:
        res = NavResult(nav_id=self.id, site=job.site)
        page: Any = await self._fresh_page(job)
        plan = ["t3_keep"] if self.start_tier == 3 else (["t1_keep"] if self.use_tier1 else ["t2_keep"])
        tried = 0
        try:
            while True:
                if not self.is_current():
                    raise asyncio.CancelledError()
                if not plan:
                    plan = ["t3_keep"] if (self.allow_tier3 and self.t_left > 0 and self.start_tier != 3 and not any(
                        a["tier"] == 3 for a in res.attempts)) else []
                if not plan:
                    break
                tier_s, mode = plan.pop(0).split("_")
                tier = int(tier_s[1])
                if mode == "fresh":
                    page = await self._fresh_page(job, page)
                tried += 1
                self.last_inputs_audit, self.last_audit_summary = "n/a", {}
                try:
                    if tier == 1:
                        outputs = await self._tier1(page, job)
                    elif tier == 2:
                        outputs = await self._tier2(page, job)
                    else:
                        outputs = await self._tier3(page, job, mode == "keep" and bool(res.attempts))
                    value = job.finalize(outputs)
                    if value is None:
                        raise TierError("outputs failed code validation")
                    res.value, res.state, res.page = value, "done", page
                    res.raw_outputs = outputs
                    res.inputs_audit = self.last_inputs_audit
                    if job.kind == "calculator" and not self.defer_cliff:
                        await self._cliff_check(page, job, outputs, res)
                    break
                except (GateStop, InjectionStop, ProviderSafetyStop, asyncio.CancelledError):
                    raise
                except Exception as exc:  # noqa: BLE001 - every other failure is a recovery case
                    kind = type(exc).__name__
                    res.attempts.append({"tier": tier, "mode": mode, "error": kind, "detail": str(exc)[:100]})
                    self._note("escalate", False, f"tier {tier} failed: {kind}", tier)
                    if self.clear_obstructions and await self._clear_obstruction(page):
                        plan = [f"t{tier}_fresh"] + plan      # a dialog was in the way: same tier again, on a fresh page
                        continue
                    transient = False
                    try:
                        transient = (await page.locator('[role="alert"]').count()) > 0
                    except Exception:  # noqa: BLE001
                        pass
                    if isinstance(exc, FormAuditStop) and not exc.retryable:
                        plan = []                    # the audit could not decide (a control it cannot read): a second try would see the same
                    elif tried >= 5:
                        plan = []
                    elif tier == 1:
                        plan = ["t1_fresh", "t2_fresh"] if transient else ["t2_keep", "t2_fresh"]
                    elif tier == 2 and not any(a["mode"] == "fresh" and a["tier"] == 2 for a in res.attempts):
                        plan = ["t2_fresh"]
                    elif tier == 3 and self.start_tier == 3 and not any(a["mode"] == "fresh" and a["tier"] == 3 for a in res.attempts):
                        plan = ["t3_fresh"]     # tier-3-only run: one restart on a fresh page (a 503, a blanked form)
                    else:
                        plan = []
            if res.state != "done":
                await self._escalate_to_human(res, job)
        finally:
            res.steps, res.tiers_used = self.steps, list(self.tiers_used)
            res.false_claims = sum(1 for c in self.ledger.claims if c["false_claim"] and self.id in c["source"])
        return res

    async def cliff_check(self, job: Any, res: NavResult) -> None:
        """Public: do the cliff check on this navigator's finished page (the orchestrator calls it AFTER the verifier has
        re-read the result, so the cliff panel's own figures can never confuse the verification)."""
        if job.kind == "calculator" and res.state == "done" and res.page is not None:
            await self._cliff_check(res.page, job, res.raw_outputs, res)

    async def _cliff_check(self, page: Any, job: Any, outputs: dict[str, Any], res: NavResult) -> None:
        """CHECK_CLIFF, the expert's signature step. Already done by a tier-1 bundle, otherwise do it now."""
        if not outputs.get("cliff") and self.start_tier == 3:
            await self._cliff_tier3(page, job, res)
            return
        if not outputs.get("cliff") and not self.use_tier1:
            await self._cliff_tier2(page, job, res)
            return
        if not outputs.get("cliff"):
            self.guard.set_mode("compiled")
            rt = DslRuntime(page=page, params={}, base_url=self.base_url, navigator=self.id, emit=self._emit,
                            guard=self.guard, is_current=self.is_current, step_start=self.steps,
                            pre_timeout_ms=1500, post_timeout_ms=3000)
            try:
                outputs = {**outputs, **(await run_bundle(cliff_bundle(job.site), rt)).outputs}
            except (GateStop, InjectionStop, asyncio.CancelledError):
                raise
            except Exception as exc:  # noqa: BLE001 - a missing panel is reported, not fatal
                self._note("cliff_check", False, type(exc).__name__, 1)
        res.cliff_text = str(outputs.get("cliff", ""))
        res.cliff_checked = bool(res.cliff_text)

    async def _cliff_tier3(self, page: Any, job: Any, res: NavResult) -> None:
        """Tier-3-only runs do the cliff check by computer use too: press the button, read the panel."""
        marker = "Cliff edges for this household"
        vp = page.viewport_size or {"width": 1280, "height": 800}
        cu = ComputerUse(self.model, self.actuator_factory(page), self.guard, navigator=self.id, emit=self._emit,
                         is_current=self.is_current, step_start=self.steps, max_steps=8, stall_limit=6,
                         pause=self.pause, screenshot_size=(int(vp["width"]), int(vp["height"])),
                         facts=FactStore({}, {}))        # nothing to type here: any typed text is refused

        async def verify() -> bool:
            return marker in (await observe(page)).text

        try:
            out = await cu.run(CLIFF_GOAL, verify)
        except (GateStop, InjectionStop, asyncio.CancelledError):
            raise
        except Exception as exc:  # noqa: BLE001 - a missing panel is reported, not fatal
            self._note("cliff_check", False, type(exc).__name__, 3)
            return
        if out.outcome == "done":
            text = (await observe(page)).text
            res.cliff_text = text[text.index(marker):][:600] if marker in text else ""
            res.cliff_checked = bool(res.cliff_text)

    async def _cliff_tier2(self, page: Any, job: Any, res: NavResult) -> None:
        """With tier 1 switched off the cliff check is the browser agent's job too: press the button, read the panel."""
        marker = "Cliff edges for this household"

        def final(obs: Observation) -> bool:
            return marker in obs.text

        def parse(obs: Observation, fields: dict[str, Any] | None) -> dict[str, Any] | None:
            return {"cliff": obs.text[obs.text.index(marker):][:600]} if marker in obs.text else None

        agent = BrowserAgent(self.model, self.guard, navigator=self.id, emit=self._emit, is_current=self.is_current,
                             step_start=self.steps, max_actions=max(1, min(4, self.t_left)), ledger=self.ledger,
                             page_state=self.page_state)
        task = Tier2Task("Press Check cliff edges to open the cliff panel for this result and read it.", job.params,
                         (), final, None, parse, {})
        try:
            out = await agent.run(page, task)
        except (GateStop, InjectionStop, asyncio.CancelledError):
            raise
        except Exception as exc:  # noqa: BLE001 - a missing panel is reported, not fatal
            self._note("cliff_check", False, type(exc).__name__, 2)
            return
        finally:
            self.t_left -= agent.used
        res.cliff_text = str((out.outputs or {}).get("cliff", ""))
        res.cliff_checked = bool(res.cliff_text)

    async def _escalate_to_human(self, res: NavResult, job: Any) -> None:
        item = self.guard.enqueue(
            kind="batch_result", title=f"Needs a human: {job.label}",
            summary=f"{self.id} could not finish after {len(res.attempts)} attempts; nothing was submitted.",
            risk_class="normal",
            evidence={"screenshots": [], "extracted": ({"inputs_audit": self.last_inputs_audit,
                                                         "handles_not_entered": list(self.last_audit_summary.get("pending", []))[:12]}
                                                        if self.last_inputs_audit != "n/a" else {}),
                      "expected": {}, "diff": [],
                      "tier_log": [{"attempt": i + 1, "tier": a["tier"], "error": a["error"]}
                                   for i, a in enumerate(res.attempts)]})
        self.guard.note("escalate", "human", "attempts_exhausted")
        res.state, res.queue_id = "escalated", item["id"]
        res.error = res.attempts[-1]["error"] if res.attempts else "unknown"
