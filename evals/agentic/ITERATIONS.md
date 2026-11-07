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
| iter2_dev_r1 (gpt-5.5, stateless) | 3 households | 932,764 | 31,924 | 5.62 | 0.84 |
| diag_smoke_mini (gpt-5.4-mini) | 1 calculator | 241,612 | 13,224 | 0.24 (mini rates) | 0.24 |
| iter3_mini_r1 (gpt-5.4-mini) | 3 households | 677,824 | 38,067 | 0.68 (mini rates) | 0.68 |
| diag_smoke_800x500 (gpt-5.5) | 1 calculator | 71,533 | 3,041 | 0.45 | 0.07 |
| **Total new live spend** | | | | **8.54 of 20 (42.7%)** | |

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

### Iteration 2, dev round 1 (live, gpt-5.5, stateless, clean, dev households hh_0001 to hh_0003 of seed 7001, IN-SAMPLE)

| Household | Archetype | Outcome by code | Steps | False claims | Refusals | Cost (placeholder = list price) |
|---|---|---|---|---|---|---|
| hh_0001 | single_worker | all three calculators and the case note done, one Submit item waiting, 0 submissions | 119 | 0 | 0 | 1.95 |
| hh_0002 | couple_two_kids | same (calculator b hit one stuck loop at step 4, restarted on a fresh page, finished) | 120 | 0 | 0 | 1.85 |
| hh_0003 | lone_parent_childcare | same | 116 | 0 | 0 | 1.83 |

**3 of 3 completed through the real gate, 0 false claims, 0 refused literals, 0 nudges, 0 premature claims, 0 submissions. n = 3 and the households were seen: this is a development result, not a rate** (Wilson 95% interval for 3 of 3: 0.44 to 1.00). The judge is code: figures equal what each site is documented to show (within 0.06), the completion check passes, the case note id is present. About 150 to 180 s wall per household on a loaded machine, about 1.87 USD per household at the gpt-5.5 list prices (5 and 30 USD per million tokens).

## Iteration 3: the computer-use model (gpt-5.5 against gpt-5.4-mini; one change; in-sample)

The lead verified the list prices: gpt-5.5 is 5.00 in and 30.00 out per million tokens, gpt-5.4-mini 0.75 and 4.50. Same stateless loop, same households, `OPENAI_MODEL_COMPUTER_USE=gpt-5.4-mini` (the provider accepted it).

| Model | n | Completed | False claims | Steps per household | Cost per household |
|---|---|---|---|---|---|
| gpt-5.5 | 3 | 3 | 0 | 116 to 120 | 1.83 to 1.95 |
| gpt-5.4-mini | 3 (and one calculator smoke) | **0** | 0 (a first count of 1 was a bug in my row definition, fixed below) | 29 to 188 (did not finish) | 0.08 to 0.50 (runs that did not finish) |

What the mini model did: on the single-calculator smoke it clicked 65 times and typed one handle in 80 actions (it hit the 45-step cap twice); in the household round hh_0001 stopped on two stuck loops and a step cap on calculator c, hh_0002 and hh_0003 were stopped by the ACTION GATE on calculator c (a needs-human verdict; it did not fire once in the gpt-5.5 runs), and in one run it answered `FAILED: missing household facts` (it did not use the handles). Its navigators that finished were verified by code.
**Metric bug found and fixed:** the row field `false_claim` counted a run as a false claim whenever ANY navigator had claimed done and the whole run failed; a navigator whose claim was verified (a, b in hh_0001) is not a false claim. It now counts a claimed success that code refused (the run says done and the check fails, or a navigator's Done failed verification). Under the corrected definition mini's false claims are 0 of 3. The gpt-5.5 rows were unaffected (all passed).
**Decision (the lead's rule: choose on cost only when both complete all of them, else keep gpt-5.5):** keep gpt-5.5. n = 3 cannot show equivalence, and here the cheaper model completed none.

## Iteration 4: a smaller page (800 by 500 instead of 1280 by 800) as a way to cut image tokens (one smoke, in-sample, n = 1)

Done in 33 steps (27 changed the screen), 0 refusals, figure correct; input tokens 71,533 against 74,548 at the full size, cost 0.45 against 0.46. **No meaningful saving (4 percent fewer input tokens, 6 more steps).** The provider already downsizes the frame, so the page size is not a cost lever. Not adopted; the default stays 1280 by 800 (`UNDERSTUDY_T3_VIEWPORT` exists for experiments).

## Iteration table so far (7 Nov 2026)

| # | Change | Evidence | n | Result | Cost |
|---|---|---|---|---|---|
| 0 | root cause: nothing to type (design fault) | code, three stored traces | 3 | explained, not a model failure | 0 |
| 1 | fact handles | live smoke | 1 calculator | model types handles, 0 literals; one premature DONE; chained thread cost grows | 1.09 |
| 2 | stateless requests, completion sentence, nudge | live smoke then dev round | 1 then 3 households | 27 steps, flat 2.8k tokens per step; 3 of 3 households complete, 0 false claims | 0.46 and 5.62 |
| 3 | computer-use model gpt-5.4-mini | smoke and dev round | 1 and 3 | 0 of 3 complete; keep gpt-5.5 | 0.92 |
| 4 | page size 800 by 500 | smoke | 1 | no saving; not adopted | 0.45 |
No held-out household has been used. Everything above is in-sample.
