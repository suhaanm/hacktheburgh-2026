# Simulated study: language-model participants, not people

**simulated participants (language model), not people.** This is an end-to-end test of the pipeline under realistic use, a probe of whether the coach's prompts change a language-model novice's later unassisted behaviour, and an A/A control of the measurement chain. It is **not** the live study, it never fills the `study` section of the report, and it cannot show that people learn. Pre-registered in `evals/study_sim/PLAN.md` before any model-driven run.

**Status: complete.** n = 16 coached-arm silicon participants and n = 8 in the A/A sham arm (planned 16 and 8). Models: gpt-5.4-mini.

> **An earlier run (run1) was aborted after GO and is not analysed:** typed values from the structured model reply carried JSON artifacts (about 11% of fills) that blocked the calculators' numeric fields; harness repair, see PLAN.md amendment 1. Its spend (US$0.393, 336 calls) counts against the cap. See the amendment log in PLAN.md. The lead and I saw two post-test scores (p_sim01 and p_sim03) in the progress log before the repair; the repair was judged on a defect of the reply interface (typed values with JSON artifacts), not on outcomes, and nothing was analysed by arm.

> **An earlier run (run2) was aborted after GO and is not analysed:** aborted about 3 minutes in, before any participant finished, to freeze the pipeline under test (PLAN.md amendment 3); no participant data exists. Its spend (US$0.006, 6 calls) counts against the cap. See the amendment log in PLAN.md.

> **An earlier run (run3) was aborted after GO and is not analysed:** restarted about 8 minutes in, before any participant finished, to add the engine-event export (PLAN.md amendment 4); no participant data exists. Its spend (US$0.353, 293 calls) counts against the cap. See the amendment log in PLAN.md.

## 1. Headline: unassisted skill score, coached skill minus uncoached skill

Mean difference **0.094** (95% t interval [-0.0512, 0.2387], n = 16); exact two-sided sign-flip p = 0.500000 (smallest possible 3.05e-05). Scores run from 0 to 1 on the post-test, read from the sandbox state exactly as `analyze.py score` does.

**Reading:** the interval includes zero. This is consistent with no effect and with a moderate one; with 16 participants a null is not evidence of no effect (see power below).

**Floor check (descriptive, not a pre-registered estimate).** Of the 32 unassisted post-tests in the coached arm, 30 (94%) scored 0, 18 hit the action cap, 11 ended with no calculation at all in the sandbox and only 1 with a saved draft; in the A/A arm 16 of 16 scored 0 and 8 hit the cap. **The measurement is at the floor: the headline and the A/A comparison say very little about the coach**, whatever their sign.

| per-participant difference | value |
|---|---|
| p_sim01 | 0.0 |
| p_sim02 | 0.0 |
| p_sim03 | 0.0 |
| p_sim04 | 0.0 |
| p_sim09 | 0.0 |
| p_sim10 | 0.0 |
| p_sim11 | 0.0 |
| p_sim12 | 0.5 |
| p_sim17 | 0.0 |
| p_sim18 | 0.0 |
| p_sim19 | 0.0 |
| p_sim20 | 0.0 |
| p_sim21 | 1.0 |
| p_sim22 | 0.0 |
| p_sim23 | 0.0 |
| p_sim24 | 0.0 |

## 2. Per skill (different people, same skill; descriptive, no p-value)

| skill | n coached | mean score coached | n uncoached | mean score uncoached | difference | 95% bootstrap interval |
|---|---|---|---|---|---|---|
| cliff | 8 | 0.188 | 8 | 0.000 | 0.188 | [0.0, 0.4375] |
| reconcile | 8 | 0.000 | 8 | 0.000 | 0.000 | [0.0, 0.0] |

## 3. A/A sham arm: how biased is the measurement chain?

No coaching at all (study mode off in every block), same sequences, n = 8. Mean difference 0.000 (95% t interval [0.0, 0.0]), sign-flip p = 1.000000. The true effect is zero by construction, so anything away from zero is bias or chance.
Over all 70 balanced relabellings of the A/A participants, the share with sign-flip p < 0.05 was 0.0 and the share whose interval excluded zero was 0.0 (nominal 0.05).
Coached-arm difference minus A/A difference: 0.094 (95% bootstrap interval [0.0, 0.25]).

## 4. Assisted effort (action counts, not seconds) and nudges

Practice actions per case: coached mean 46.2 (n = 16), uncoached mean 43.1 (n = 16). Model latency is not human speed, so no seconds are reported. Capped cases: practice 8, post-test 18.
Coach prompts in the coached blocks: shown 12, followed 6, dismissed (explicit or ignored at case end) 6 (ignored 6); drawn with a ring 7; false 1, lagging 1; coached blocks 16.

## 5. Pipeline checks (counts)

- Participants run: 24. Events landed: 7334 (7310 from the extension), schema-valid share 1.0000; by type {'task_start': 96, 'nav': 1380, 'focus': 3035, 'click': 1210, 'progress': 152, 'coach_shown': 12, 'task_end': 6, 'coach_dismissed': 6, 'tab': 1431, 'coach_followed': 6}.
- Coach: 5669 polls, 12 prompts shown {'annotate': 12, 'nudge': 0, 'takeover_offer': 0}, outcomes {'followed': 6, 'dismissed': 0, 'ignored': 6}, stuck-signal source {'null': 4888, 'hazard': 781}.
- Ring target: 12 of 12 annotate decisions carried the zone of the missing step; ring drawn on arrival 5, at some point 7, message only 5; by zone {'reconcile_control': 4, 'cliff_button': 8}.
- Delay from the participant's first action on the case note page to the prompt: {'n': 6, 'median': 9.91, 'min': 2.38, 'max': 11.23, 'q25': 8.13, 'q75': 10.33}.
- False nudges (prompt for a step already done more than 6 s earlier): 1 of 12; lagging prompts (step done within 6 s): 1.
- **Study mode enforcement: zero nudges outside the trained skill's train block.** Polls by mode {'train': 807, 'post_test': 2949, 'off': 1913}; non-silent polls by mode {'train': 12, 'post_test': 0, 'off': 0}; coach_shown events by block and skill {'train/check-the-cliff': 8, 'train/reconcile-before-noting': 4}; violations seen none.
- Errors: engine {'tracebacks': 0, 'error_lines': 0, 'events_post_failures': 0}, extension web errors 0, coach poll errors 0, harness tracebacks 0, contaminated attempts retried 0; exclusions none.
- Typed values cleaned of structured-reply artifacts (PLAN amendment 1, same for every arm): 215 of 1994 fills and selects (0.1078).
- **Transcript-free statement:** the engine event files kept for each participant (`results/raw/<participant>/engine_events.jsonl`, 7334 events from 24 participants) contain no participant text: they are schema-valid L0 events (timestamps, types, zones, hashed ids, coach step and outcome ids). Strings that were not enum-like and had to be removed: 0 (expected 0); export errors: 0. The only model text kept anywhere is each participant's own 280-character note in `actions.jsonl`.
- Machine load while the participants ran (1-minute load average on 12 CPUs): min 17.39, max 191.09 over 281 samples; median at participant start or end 46.5 (the sampler started after the first participants; 15 of 24 have a sample within a minute of their start or end). Per participant in `load_by_participant.csv`. Timings and the coach's prompt delays are affected (see limitations).
- Code under test: a frozen snapshot of git 4e12dd8c plus 93 uncommitted files in services/ and packages/ (fingerprint 5630b3c99e9f734a, taken 2026-11-07T17:23:22Z); engines and sandbox sites ran from that copy for the whole run, the extension from one build per worker.
- Consent toggle respected: True (events while off at start [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], after switching off [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]).
- Kill flag: engine reported it in 24 of 24 participants, coach silent after it in 24. the KILL file was written in each participant's isolated data dir (never POST /kill, which would call the agent service); the engine reports it and the coach stays silent. The extension's capture is governed by its own consent toggle, not by this flag.

### Pipeline findings (about the system, not results)

- A prompt arrives about 9.91 s (median of n = 6; min 2.38, max 11.23) after the participant's first action on the case note page: the extension batches events every 2 s and the coach needs two consecutive signals at 3 s polls. A participant who finishes the note page faster never sees it.
- Prompt targets served, by zone: {'reconcile_control': 4, 'cliff_button': 8}. The cliff ring can only be drawn on a calculator result tab (the Check cliff edges button lives there), not on the case note page where the prompt usually arrives (ring drawn on arrival 5 of 12, at some point 7). The reconcile target was results_tabs (no page element) when the plan was written; the frozen pipeline serves reconcile_control, the case note's dropdown, which exists.
- The engine's RECONCILE signal was a browser tab switch (results_tabs) and is now also a click or focus on the dropdown (reconcile_control); tab events recorded in this run: 1431. Comparing calculators within one tab never satisfied the older signal.

## 6. Cost

Estimated spend US$4.75 of the US$8 cap (of which US$0.75 was spent by the aborted runs); 3196 model calls (0 cache hits); tokens {'in': 3904682, 'out': 403649}. Prices were set from the environment and are an ASSUMPTION (supplied by the lead, not verified against a bill): in 0.75, out 4.5 per million tokens. For reference, the same tokens at the fast-tier rates of 0.75 and 4.50 would cost US$4.75.

## 7. What this does not show

- (high) The participants are language-model agents, not people. Nothing here shows that people learn from the coach, and nothing here is a user study.
- (high) The only 'memory' a participant has is a note of at most 280 characters that it wrote itself after the practice case and sees again at the post-test of the same skill. Every case starts from a fresh model context. That is a prompt, not learning in any human sense.
- (high) A model that is shown 'check cliff edges before you copy this result' can simply do what it says. A higher score after coaching can therefore be instruction following plus a self-written note, not retention of a skill.
- (high) The coach prompts, the sandbox sites, the households, the scoring rule and the personas were all written by us.
- (high) With 16 coached-arm participants the analysis has about 6% false positives and 12%, 29% and 76% power for a small, medium and large true effect (engine-analytics Monte Carlo, interval excludes zero); sign-flip p below 0.05 has less. A null or small result does not show that the coach has no effect; a result counts as clear only if the interval excludes zero.
- (medium) The counterbalanced design cancels a fixed block-2 shift and generic carry-over, not spill-over of the coached gain to the other skill in block 2, which dilutes the contrast. Because each block starts from a fresh model context, order and fatigue effects are absent by construction.
- (medium) Timing is not human. Each action is followed by a fixed 2 s pause and the model's own latency varies, so effort is reported as ACTION COUNTS and the coach's poll-to-prompt delay is a property of the pipeline, not of people. A fast participant can finish the note page before a prompt arrives.
- (medium) The coach is real but the overlay renderer is simulated: a ring is drawn only when an element carrying the target zone exists on the page the participant is on. The cliff button exists only on a calculator result tab, not on the case note page where the prompt usually arrives. The reconcile target was `results_tabs` (no page element) when the plan was written; the pipeline snapshot used targets `reconcile_control` (the case note's dropdown), which exists. The by-zone table shows which was served.
- (medium) Participants are reached through the shared model port's fast-tier check call, whose fixed instructions tell the model to treat quoted material as data. That may make it less responsive to on-page text in both arms.
- (medium) The build machine was heavily loaded by other agents' tests while the participants ran (1-minute load average above 100 on 12 CPUs, sampled and reported), so wall-clock times, the coach's 3 s polls, the extension's event flush and the prompt delays are slower and noisier than on an idle machine. Action counts are not affected; timings are.
- (medium) One model (id read from the environment and recorded in the CSV) and one family of personas written by us. Results say nothing about other models.
- (medium) Scores come from the sandbox state exactly as analyze.py scores them (cliff 0, 1 or 2 of 2; reconcile 0 or 1), so ties and ceilings are likely and the t interval is not exact for such discrete scores.

We do not claim that people learn from the coach, that the coach works on real benefits work, that a model's note is memory, any effect on speed, or statistical significance beyond what the exact sign-flip test gives. After GO nothing about the prompts, personas, cases, caps, pace, scoring or analysis was changed except the harness repairs and reporting additions in the amendment log of PLAN.md, each dated, the repairs made before any run's participants were analysed by arm.
