"""One navigator = one site task, in its own browser context (AGT-1, AGT-7, AGT-9).

The ladder (AGT-3): try tier 1 (compiled bundle). Escalate ONLY when a precondition or postcondition fails.
Recovery (AGT-7): transient error page -> reload the start page and retry tier 1, then tier 2 from scratch;
structural change -> tier 2 from where we are, then tier 2 from scratch; then tier 3 if allowed; then a human
queue item. Gate stops, injection pauses and provider safety checks are never retried.
Step cap: 20 model-driven actions per navigator (tier 2 and 3); tier-1 steps are bounded by the bundle (<= 60).
"""
from __future__ import annotations

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


# ----------------------------------------------------------------------------- jobs
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
    goal_words = ("Fill in the household details (adults, age, children, pay, earnings, health, rent, housing, "
                  "bedrooms, savings, childcare) and press Continue, Next, Calculate, Show results, See entitlement "
                  "or Work it out to reach the estimate page.")

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
    goal_words = ("Fill in the case reference, the GovCalc, Quick Estimator and EntitledTo results, the "
                  "reconciliation and the note, then press Save draft.")

    def looks_final(self, obs: Observation) -> bool:
        return bool(NOTE_ID_RE.search(obs.text)) and "Draft" in obs.text

    def parse(self, obs: Observation, fields: dict[str, Any] | None) -> dict[str, Any] | None:
        m = NOTE_ID_RE.search(obs.text)
        return {"note_id": m.group(0), "status": "Draft", "body": obs.text} if m else None

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
        max_actions: int = 20,
        allow_tier3: bool = False,
        page_state: bool = False,
        defer_cliff: bool = False,
        actuator_factory: Callable[[Any], Actuator] | None = None,
        shot_hook: Callable[[str, bytes], None] | None = None,
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
        self.actuator_factory = actuator_factory or (lambda page: BrowserPageActuator(page))
        self.steps = 0
        self.tiers_used: list[int] = []

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
        page = await self.context.new_page()
        await page.goto(self.base_url + job.start_path + self.query, wait_until="domcontentloaded")
        await self._scan(page)
        return page

    async def _scan(self, page: Any) -> None:
        """Injection detector over visible text, hidden elements and alt text. A hit pauses the run."""
        await self.guard.observe(page, navigator=self.id, step=self.steps, tier=0)

    async def _read_final(self, page: Any, job: Any) -> dict[str, Any] | None:
        """Fresh observation of the page; if it looks final, the quarantined reader and the code check decide."""
        obs = await observe(page)
        if not job.looks_final(obs):
            return None
        seen = await asyncio.to_thread(self.guard.observe_obs, obs, schema=job.schema, navigator=self.id)
        return job.parse(obs, seen.fields)

    # ------------------------------------------------------------------ tiers
    async def _tier1(self, page: Any, job: Any) -> dict[str, Any]:
        self.guard.set_mode("compiled")
        bundle = self.bundle_override or job.bundle(self.bundle_layout)
        rt = DslRuntime(page=page, params=job.params, base_url=self.base_url, query=self.query,
                        navigator=self.id, emit=self._emit, guard=self.guard, is_current=self.is_current,
                        step_start=self.steps, pre_timeout_ms=1500, post_timeout_ms=2500)
        res = await run_bundle(bundle, rt)
        await self._scan(page)  # the result page is scanned too before its numbers are trusted
        return res.outputs

    async def _tier2(self, page: Any, job: Any) -> dict[str, Any]:
        if self.t_left <= 0:
            raise StepBudgetExceeded("no model-driven actions left for this navigator")

        agent = BrowserAgent(self.model, self.guard, navigator=self.id, emit=self._emit,
                             is_current=self.is_current, step_start=self.steps, max_actions=self.t_left,
                             ledger=self.ledger, page_state=self.page_state)
        try:
            res = await agent.run(page, Tier2Task(job.goal, job.params, job.allowed_params, job.looks_final,
                                                  job.schema, job.parse, job.param_help))
        finally:
            self.t_left -= agent.used
        assert res.outputs is not None
        return res.outputs

    async def _tier3(self, page: Any, job: Any) -> dict[str, Any]:
        actuator = self.actuator_factory(page)
        cu = ComputerUse(self.model, actuator, self.guard, navigator=self.id, emit=self._emit,
                         is_current=self.is_current, step_start=self.steps, max_steps=min(self.t_left, 20))
        last: dict[str, Any] = {}

        async def verify() -> bool:
            raw = await self._read_final(page, job)
            if raw is not None:
                last.update(raw)
            return raw is not None

        res = await cu.run(job.goal, verify)
        self.t_left -= res.steps
        if res.false_claim:
            self.ledger.record(f"tier3:{self.id}", True, False, "computer-use Done not confirmed by code")
        if res.outcome != "done":
            raise TierError(f"tier 3 ended {res.outcome}")
        return last

    # ------------------------------------------------------------------ the ladder
    async def run(self, job: Any) -> NavResult:
        res = NavResult(nav_id=self.id, site=job.site)
        page: Any = await self._fresh_page(job)
        plan = ["t1_keep"] if self.use_tier1 else ["t2_keep"]
        tried = 0
        try:
            while True:
                if not self.is_current():
                    raise asyncio.CancelledError()
                if not plan:
                    plan = ["t3_keep"] if (self.allow_tier3 and self.t_left > 0 and not any(
                        a["tier"] == 3 for a in res.attempts)) else []
                if not plan:
                    break
                tier_s, mode = plan.pop(0).split("_")
                tier = int(tier_s[1])
                if mode == "fresh":
                    page = await self._fresh_page(job, page)
                tried += 1
                try:
                    if tier == 1:
                        outputs = await self._tier1(page, job)
                    elif tier == 2:
                        outputs = await self._tier2(page, job)
                    else:
                        outputs = await self._tier3(page, job)
                    value = job.finalize(outputs)
                    if value is None:
                        raise TierError("outputs failed code validation")
                    res.value, res.state, res.page = value, "done", page
                    res.raw_outputs = outputs
                    if job.kind == "calculator" and not self.defer_cliff:
                        await self._cliff_check(page, job, outputs, res)
                    break
                except (GateStop, InjectionStop, ProviderSafetyStop, asyncio.CancelledError):
                    raise
                except Exception as exc:  # noqa: BLE001 - every other failure is a recovery case
                    kind = type(exc).__name__
                    res.attempts.append({"tier": tier, "mode": mode, "error": kind, "detail": str(exc)[:100]})
                    self._note("escalate", False, f"tier {tier} failed: {kind}", tier)
                    transient = False
                    try:
                        transient = (await page.locator('[role="alert"]').count()) > 0
                    except Exception:  # noqa: BLE001
                        pass
                    if tried >= 5:
                        plan = []
                    elif tier == 1:
                        plan = ["t1_fresh", "t2_fresh"] if transient else ["t2_keep", "t2_fresh"]
                    elif tier == 2 and not any(a["mode"] == "fresh" and a["tier"] == 2 for a in res.attempts):
                        plan = ["t2_fresh"]
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
            evidence={"screenshots": [], "extracted": {}, "expected": {}, "diff": [],
                      "tier_log": [{"attempt": i + 1, "tier": a["tier"], "error": a["error"]}
                                   for i, a in enumerate(res.attempts)]})
        self.guard.note("escalate", "human", "attempts_exhausted")
        res.state, res.queue_id = "escalated", item["id"]
        res.error = res.attempts[-1]["error"] if res.attempts else "unknown"
