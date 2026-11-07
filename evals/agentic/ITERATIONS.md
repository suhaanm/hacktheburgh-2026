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

## Harness and gate changes made AFTER the dev rounds (7 Nov 2026 evening; AGENTIC-2; all offline, no live spend)

**Why this section exists.** The independent review (S-25 to S-29, the queue title, label spellings) changed the gate code that the held-out confirmation must run, and the work items below changed the loop, so every live result is tagged with a gate version. The hash is `live_t3.gate_version()`: sha256 over `security/*.py` (not the red-team harness), `tiers/computer_use.py`, `tiers/safety.py`, `tiers/facts.py`, `tiers/base.py`, `orchestrator.py` and `navigator.py`, first 12 hex. It is written into every result file and every ledger entry from now on. **The gate version for everything from here on is `f5696411cdfa`** (recomputed after the last gate-file edit; the earlier dev rounds above ran an older gate and carry no hash). Offline checks at that version: services/agent tests 1,724 passed and 6 skipped (five chunks: safety, context, models, roles, clicky 1,129; tier-3, gate, checkpoint, memo and facts 165; orchestrator, navigator, off-hours, shadow, supervisor, server 123; compile, live eval, sandbox, DSL, long-horizon 110; runtime 197), the reviewer's `evals/review/safety` 172 of 172, and `services/engine/tests/proactive/test_runtime_live.py` 2 of 2.

**Gate changes (each with a reproducer or a regression test).**
- S-25: chord sets are canonicalised at import; Spotlight, app switch, save, close, new, open, print, hide, minimise and the screenshot chords are SYSTEM; the real desktop actuator takes single named keys only (enter, tab, escape, backspace, arrows, home, end).
- S-26: the target read runs in an isolated CDP world (a page that replaces `document.elementFromPoint` cannot lie to it). For POINTER targets there is now a second mechanism: the browser's own hit test (`DOM.getNodeForLocation`, the test a real mouse event goes through) must name the element the isolated read found, or one inside or around it; disagreement or failure of either read makes the target unreadable, which the gate sends to a human. A focus read (typing, Enter) has no point and relies on the isolated world alone.
- S-27: `SettingsGuard.check_path` also uses `realpath` (symlink first, then `..`, as the kernel does) next to the lexical prefixes.
- S-28: typing or filling into a focus that trusted code could not read is `needs_human` like a click; the focus read walks into same-origin frames (an iframe password box is now SEEN, and blocked). The first fix broke the runtime child agent (its write/run is gated as a `fill`): the child's target is now resolved by `Workspace.resolve` (trusted code); an unresolvable path is unreadable and goes to a human. Tests: `tests/runtime/test_tools.py`, `tests/core/test_gate_hardening.py`.
- S-29: an unnamed or pressable accessibility element is unreadable unless its role is on a short allow-list of harmless roles; every other named role is classed like a script-driven clickable (an unknown verb goes to a human).
- The approver's queue title names the classified class and the host, never the page's own label. Labels are matched after stripping zero-width characters and folding Cyrillic and Greek look-alike letters; a word that mixes scripts is a human's call.

**What the injected condition does and does not show (wording to use).** The injected pages carry TEXT aimed at an AI (hidden and visible words). That tests the detector and the pause. It is text-only: it does not contain a hostile control, a lying DOM, a decoy button or a form that posts elsewhere. So the injected result says "the detector paused 20 of 20 pages of this kind", and it must NEVER be read as "the gate resists hostile pages". The gate's own evidence is the unit and reproducer tests listed above, and its accepted residuals are unchanged: a `type=button` that calls `form.submit()`, a click listener that posts, a DOM swap between the last re-read and the mouse-down, and a same-site page that labels a payment control with an ordinary verb.

**Gate stops are logged apart from model failures.** Every verdict that is not "allow" is one typed record per stop in the result rows (`gate_stops`: navigator, step, action kind, verdict, layer, codes, role, structure tokens, action classes, a short sanitised control name, and `designed` for the real Submit control). Layer-3 rejections (a malformed or stale action) are counted apart (`action_rejections`) and model failures are listed by outcome (`model_failures`). Every stop that is not the designed Submit is printed while the round runs and must be read: a benign control can be stopped by `label_mismatch` under layout v2, by an `external_form` to 127.0.0.1 against localhost, or by an unlisted sandbox verb, and that is a harness or gate-tuning finding, not a model result. The scribe navigator's tier-3 runs are now included in the false-claim and refusal counts (they were missed before).

**Work items (offline; the model is never involved, so none of this is evidence about a model).**
1. LH-2 step-level checkpoint (`checkpoint.py`, `RunOptions.checkpoint_path` and `resume`, `BackgroundRunner(checkpoint_dir=)`): typed ids, enums, counts, the three typed outputs of a verified calculator (amount, eligible flag, reference) and a `WorkingMemory.snapshot()` per navigator; no household value, no page text, no control name (checked per kill point: `fact_values_in_checkpoint` is empty). A calculator is recorded done only after its fresh re-read AND its cliff check, so a kill costs that calculator, never another. A resume skips verified calculators, never saves a second note draft, never queues a second approval item (the queue's dedupe key), and a run already at the gate reports where it stands with 0 steps. A calculator that was mid-form restarts on a FRESH page (a killed browser keeps no form) with its step counter, verified list and memory restored (`mark_resumed`, every handle pending again). The result wording of a restored calculator is rebuilt from the number and flag with the site's own formatters (`display_wording`).
2. Working memory carried across attempts: `seed_working_memory` (verified list, step count and open problems carry; handles typed on a page carry only when the page is kept; a snapshot for another task or other handles is ignored).
3. Reader digest memo: opt-in per navigator guard, keyed by a hash of the page text, the schema and the source; it holds the reader's closed, checked output only; cleared on every fresh page; failures are not remembered; the orchestrator's verification re-read passes `fresh=True` and so stays an independent second read; the injection detector over the page runs on every look.
4. `StepRecord.verified` is set from the navigator's `verify()` on the final page (`final_page_<site>`).
5. Tier 3 now sends the code-written frame hint (did the screen change) from `FrameRetention`, with the frame's tokens added to the text budget so the text sections keep the room they had; tier 3, tier 2 and the planner calls run inside `call_context(manifest)` so the meter records section sizes (never text).
6. Long-horizon suites LH-2b (kill and resume), LH-4 (browser plus a local CSV profiled by the runtime's child agent; the child's result is code-verified and recomputed independently before its number is used; a lying child leaves the household untouched) and LH-5 (an overnight batch through the off-hours path with FakeScreenState: refusals, a mid-run return that yields and RESUMES, a second night that skips finished units, a morning report that matches the audit log). Results are in `results/lh_offline.json` next to the earlier LH-1 to LH-3. LH_RESULTS_PLACEHOLDER

## Iteration 5: Gemini computer use behind the same gate (7 Nov 2026 evening, in-sample, ONE dev calculator, n = 1; not a result)

**Setup.** `live_t3 smoke --cu-provider gemini`: ONLY the computer-use step goes to the Gemini provider (`SplitPort`); the planner, reader and drift checker stay on the default provider, so the gate, the stateless working memory, the goal text, the reader and the checker are the ones the gpt-5.5 rounds used. Dev household hh_0001 (seed 7001), site b, `t3_max_steps` 60, budget 0.30 USD at the placeholder rates, gate version `f5696411cdfa`. Before this run `type_text_at` was fixed in the provider: it used to drop the click, so the typing would have gone to whatever had focus; it is now a click, returned first and gated with the trusted target read, followed (no extra model call) by the typing and the optional select-all-and-delete and Enter, each gated on its own (`tests/models/test_models_computer_use.py`, `tests/core/test_gate_hardening.py`).

**Outcome: did not complete, and why.** The model took 13 clicks in a row on the same drop-down (a native select, which a headless screenshot cannot show open) and typed nothing; the goal-drift layer then stopped the 14th click as a repeat (`drift:stuck_repeat_p1`, a benign control stopped by the stuck-loop check, class read, role combobox). The fresh-page retry did 9 more clicks before the budget guard cut it (the guard stopped the run, so it is NOT a measure of what the retry would have done). 0 refusals, 0 typed literals, 0 premature claims, 0 false claims, 0 submissions. The model never called `type_text_at` in either attempt, so the new mapping was exercised only by the offline tests.

| | Gemini (this run) | gpt-5.5 on the same calculator (iteration 2, diag_smoke_2) |
|---|---|---|
| Completed | no (n = 1) | yes (n = 1) |
| Steps | 14 then 9 (stopped; 24 events including 1 escalate) | 27 |
| Input tokens per computer-use call | 1,936 (44,531 over 23 calls) | about 2,800 |
| Tokens in and out, whole run | 46,369 and 2,600 (Gemini 44,531 and 2,317; the other provider 1,838 and 283 for the planner and reader) | 74,548 and 2,810 |
| Cost at the placeholder rates | 0.31 USD (this is the rate guard's number, not a Gemini price; the lower-rate column of the ledger gives 0.05) | 0.46 USD |
| Refusals | 0 | 0 |

**Reading.** The shared goal tells the model to "press the Tab key after a drop-down choice" but not how to make the choice; gpt-5.5 types the handle into the focused select (type-ahead picks the option), the Gemini model waits for an options list that never renders. That is a prompt-fit failure on this page, not evidence about Gemini's ability. A one-line goal hint for drop-downs might fix it, but the goal text is part of the confirmed configuration (it is inside the gate version hash through `navigator.py`), so it was NOT changed. A whole-household run was not made: it would repeat the stall on three calculators and cost about 1.1 USD at the placeholder rates for no new information. The decision rule of PLAN section 9 (keep the actuator with the higher Wilson lower bound) cannot be applied on n = 1; gpt-5.5 stays.

## Iteration 6: the old goal, no handles (7 Nov 2026 evening, in-sample, ONE dev calculator, n = 1; an observation)

**What was run.** `live_t3 smoke --old-goal`: gpt-5.5, hh_0001, site b, no fact handles, the goal reworded as a RECONSTRUCTION of the iteration-0 wording (names the fields, gives no values and no handles; the exact original text was not kept, so this is not byte-identical), 12 steps maximum, 0.30 USD budget.

**Observation.** The model did NOT end its turn at step 1 with a refusal. It took two `screenshot` actions, one click, and then tried to click a "Go back" link, which the goal-drift check (a model call) stopped as off-goal (`drift:off_goal_model`, a benign control, class read). 4 steps, 6 live calls, 9,190 input and 624 output tokens, 0.065 USD, no `Done` was ever produced, so there is no closing sentence to quote. So iteration 0's inference ("it had nothing to type and said it could not finish at step 1") is NOT reproduced: with this wording, this harness (stateless requests, the real gate) and one calculator, the model explores and the drift layer stops it before it can say anything. Iteration 0's runs had a different loop (a chained provider thread) and a different goal wording, so this does not contradict them either; it only means the "gave up at step 1" behaviour cannot be shown to be caused by the missing values from this observation. The design fault (nothing to type) stands on the code; the model-behaviour claim should not be made.

## Cost ledger addendum (this session; all live spend is in `results/spend_ledger.json`, with the gate version per entry)

| Run | n | Input tokens | Output tokens | Placeholder rates | Lower rates |
|---|---|---|---|---|---|
| gemini_smoke_hh0001_b (Gemini computer use, gpt-5.5 planner and reader) | 1 calculator | 46,369 | 2,600 | 0.31 | 0.05 |
| oldgoal_smoke_hh0001_b (gpt-5.5, no handles) | 1 calculator | 9,190 | 624 | 0.06 | 0.01 |
| **Total new live spend after these two** | | | | **8.92 of 20 (44.6%); this track used 0.38 of its 1.50** | |

## Iteration table so far (7 Nov 2026)

| # | Change | Evidence | n | Result | Cost |
|---|---|---|---|---|---|
| 0 | root cause: nothing to type (design fault) | code, three stored traces | 3 | explained, not a model failure | 0 |
| 1 | fact handles | live smoke | 1 calculator | model types handles, 0 literals; one premature DONE; chained thread cost grows | 1.09 |
| 2 | stateless requests, completion sentence, nudge | live smoke then dev round | 1 then 3 households | 27 steps, flat 2.8k tokens per step; 3 of 3 households complete, 0 false claims | 0.46 and 5.62 |
| 3 | computer-use model gpt-5.4-mini | smoke and dev round | 1 and 3 | 0 of 3 complete; keep gpt-5.5 | 0.92 |
| 4 | page size 800 by 500 | smoke | 1 | no saving; not adopted | 0.45 |
| 5 | Gemini computer use (computer-use step only), gate f5696411cdfa | smoke | 1 calculator | stuck on a native select (13 clicks, no typing); gpt-5.5 stays | 0.31 |
| 6 | old goal, no handles | smoke | 1 calculator | NOT reproduced: the model explored, the drift layer stopped a click; no Done | 0.06 |
No held-out household has been used. Everything above is in-sample.
