# Agentic reliability: iteration log

One entry per iteration, newest last. Each entry says what changed, why, the numbers before and after with n, and the cost. A fix made after looking at the failed runs of a set of households is marked **in-sample**; it is **confirmed** only on fresh held-out households (see `PLAN.md`). Live cost is an estimate from the provider's token counters at the placeholder rates in `PLAN.md`, not an invoice.

## Iteration 0: why computer use (tier 3) gave up on the benefits task (root cause, 7 Nov 2026)

**Evidence.** Three tier-3 runs from the C4 evaluation (`data/eval/agent_live_runs.json`, `tier3_simulated.runs`): `r_t3_hh_0001` (site a), `r_t3_hh_0002` (site b), `r_t3_hh_0003` (site c). In all three the computer-use model returned a finished answer at step 1 and took no action: `steps = 1`, `actions = []`, `pointer_actions = 0`, `claimed_done = false`, so the harness recorded it as a refusal, not a false claim. Token counts were small (about 2,000 to 5,200 in, 74 to 130 out), consistent with one short reply and no tool call.

**What the code shows.** The goal the model was given is built in `CalculatorJob.goal` (`navigator.py`) from a fixed sentence that names the fields to fill ("adults, age, children, pay, earnings, health, rent, ..."). It contains no household values and no way to refer to them. The tier-2 planner copes because code supplies the value for a parameter name; the tier-3 loop had no such channel: the only way to enter text was `type` with literal text the model would have to know.

**What this does and does not prove.** The stored traces hold counts and outcomes, not the model's own words (the harness did not keep `Done.summary`), so the cause is established by the design (no values anywhere in the goal, nothing to type) plus the signature of the behaviour (immediate finish without a single action), not by a quoted sentence. The first diagnostic smoke after the fix prints `Done.summary` for the old goal and the new goal so this paragraph can be upgraded from inference to observation; that result will be appended below.

**Conclusion.** An honest refusal caused by our design, not a model failure. It also means the earlier "tier 3 gave up" result says nothing about the model's ability to drive these pages.

**Fix (Iteration 1):** fact handles. The goal carries a closed vocabulary of handles such as `{household.savings}`; the model types a handle, never a value; code resolves the value at actuation time. Screens will show whatever was typed (unavoidable); prompts, logs, the audit trail and the approval queue hold handles only.
