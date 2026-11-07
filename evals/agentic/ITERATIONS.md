# Agentic reliability: iteration log

One entry per iteration, newest last. Each entry says what changed, why, the numbers before and after with n, and the cost. A fix made after looking at the failed runs of a set of households is marked **in-sample**; it is **confirmed** only on fresh held-out households (see `PLAN.md`). Live cost is an estimate from the provider's token counters at the placeholder rates in `PLAN.md`, not an invoice.

## Iteration 0: why computer use (tier 3) gave up on the benefits task (root cause, 7 Nov 2026)

**Evidence.** Three tier-3 runs from the C4 evaluation (`data/eval/agent_live_runs.json`, `tier3_simulated.runs`): `r_t3_hh_0001` (site a), `r_t3_hh_0002` (site b), `r_t3_hh_0003` (site c). In all three the computer-use model returned a finished answer at step 1 and took no action: `steps = 1`, `actions = []`, `pointer_actions = 0`, `claimed_done = false`, so the harness recorded it as a refusal, not a false claim. Token counts were small (about 2,000 to 5,200 in, 74 to 130 out), consistent with one short reply and no tool call.

**What the code shows.** The goal the model was given is built in `CalculatorJob.goal` (`navigator.py`) from a fixed sentence that names the fields to fill ("adults, age, children, pay, earnings, health, rent, ..."). It contains no household values and no way to refer to them. The tier-2 planner copes because code supplies the value for a parameter name; the tier-3 loop had no such channel: the only way to enter text was `type` with literal text the model would have to know.

**What this does and does not prove.** The stored traces hold counts and outcomes, not the model's own words (the harness did not keep `Done.summary`), so the cause is established by the design (no values anywhere in the goal, nothing to type) plus the signature of the behaviour (immediate finish without a single action), not by a quoted sentence. The first diagnostic smoke after the fix prints `Done.summary` for the old goal and the new goal so this paragraph can be upgraded from inference to observation; that result will be appended below.

**Conclusion.** An honest refusal caused by our design, not a model failure. It also means the earlier "tier 3 gave up" result says nothing about the model's ability to drive these pages.

**Fix (Iteration 1):** fact handles. The goal carries a closed vocabulary of handles such as `{household.savings}`; the model types a handle, never a value; code resolves the value at actuation time. Screens will show whatever was typed (unavoidable); prompts, logs, the audit trail and the approval queue hold handles only.

## Cost ledger (live, new spend only; estimate at the placeholder rates of PLAN.md and at the lower rates; cap US$20 at placeholder rates)

The ledger is `results/spend_ledger.json` (every live call goes through `live_t3.py`, which refuses to start a call past the cap). The model counts below are the provider's own token counters; they are estimates, not invoices.

| Run | n | Input tokens | Output tokens | Placeholder rates (5 and 30 USD per M) | Lower rates (0.75 and 4.50) |
|---|---|---|---|---|---|
| diag_smoke_1 (chained thread) | 1 calculator | 211,852 | 1,173 | 1.09 | 0.16 |
| diag_smoke_2 (stateless) | 1 calculator | 74,548 | 2,810 | 0.46 | 0.07 |

## Iteration 1: fact handles (smoke, 7 Nov 2026, in-sample: dev household hh_0002, site b, one calculator)

**Change.** The goal carries a closed list of fact handles; the model types a handle, code resolves the value at actuation (`tiers/facts.py`); typing a literal, an unknown handle or a letter key is refused and the refusal is fed back.

**Observation (diag_smoke_1, live, chained provider thread).** Attempt 1: the model clicked the first field and then answered `DONE: Clicked the "Adults in household" field.` at step 2 (a claimed success that code refused to confirm: a premature claim). Attempt 2 (fresh page): the model typed the handles in page order with a Tab key between fields, 9 handles in 18 actions, **0 refusals**, until the budget guard stopped the run (cut short by the guard: discarded, not a result). So the handles work: the model uses them without being told a value, and never typed a literal.

**What this does to the iteration 0 conclusion.** The old goal was NOT re-run (it would have cost money for a result we expected), so the quoted-sentence upgrade of iteration 0 is still not done. What the new run adds: the one early finish we saw is a model habit of ending its turn after one action; it looks the same on screen as "gave up at step 1" and may have contributed to iteration 0. The design fault (nothing to type) is still established by the code.

**Cost finding (important).** 211,852 input tokens for 25 calls (about 8,500 per call): the chained provider thread keeps every earlier frame, so the cost per step grows with the step number. A 150-step household would cost several times that. This is what iteration 2 addresses.

## Iteration 2: stateless computer use, a completion sentence, and a code-written nudge (7 Nov 2026, in-sample)

**Changes (three, made together because the smoke showed all three problems at once and a single-site smoke cannot separate them; they are listed so a later ablation can).**
1. Stateless requests: every step carries the goal and the fact list first (stable prefix), then code-built working memory (`context/working.py`: handles entered on THIS page, handles pending, the last 6 steps as typed records, a rolling summary), the refusal feedback, and ONE fresh frame; `store=false`, no provider thread. (CONTEXT agent's library, MODELS' `store=False`.)
2. The goal now says what finished looks like: every field filled, and the estimate page showing an amount and a reference on screen; one field is never the end.
3. If the model ends its turn but code says the final screen is not showing, the loop tells it so and it carries on (at most twice). The premature claim is counted and reported (`premature_claims`); it is never hidden by the retry.

**Result (diag_smoke_2, live, same household and site, in-sample).** Done in 27 steps, 23 of which changed the screen, 0 refusals, 0 nudges, 0 premature claims, the extracted figure matched what the site is documented to show (code check). Tokens 74,548 in for the whole run (about 2,800 per step, flat: the text part of the prompt stayed between 2,400 and 2,700 characters from step 1 to step 27 and the per-step cost did not grow), **cost 0.46 USD at the placeholder rates (0.07 at the lower rates) against 1.09 for a run that did not finish**. n = 1: this shows the loop can complete a calculator and that the cost is flat; it is not a success rate.

**Cost projection (honest).** About 2,800 input tokens per step; a household is about 125 steps (three calculators and the case note), so about 350,000 input tokens: **about 1.7 USD per household at the placeholder rates, 0.26 at the lower rates.** PLAN.md asks for n = 30 per condition on fresh households (three conditions, 90 households): that is about 150 USD at the placeholder rates or about 24 USD at the lower rates. The US$20 cap, counted at the placeholder rates, pays for about 11 households in total. This needs a decision from the lead (see the report); the dev rounds below are sized to it.
