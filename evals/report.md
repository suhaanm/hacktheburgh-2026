# Understudy evaluation report

Generated 2026-11-07T17:38:00Z · mock mode: yes · git 1bab986 · fast run: no

Written by `python -m understudy_engine.eval` from the owning tracks' code; no number here is typed in by hand. Synthetic results are labelled synthetic. A section without numbers says why instead of showing a made-up value.

## Evidence map

32 sections: 23 with numbers, 7 pending, 2 not run, 0 failed. Origin: [synthetic] is data we planted or simulated, [real] is people, [mixed] is both. A section without numbers says why instead of showing a made-up value.

| Section | Origin | n | Status | Label |
|---|---|---|---|---|
| Deficit recovery (EVL-1) | [synthetic] | 16 people | ok |  |
| Controls: placebo and shuffled-label null | [synthetic] | 24 people | ok |  |
| Stuck hazard (leave one person out) | [synthetic] | 4 people | ok |  |
| Coaching dignity gate | [synthetic] | 4 people | ok |  |
| Skill tracing | [synthetic] | 4 personas | ok |  |
| Off-policy evaluation | [synthetic] | 6000 decisions | ok |  |
| Review routing and risk control | [synthetic] | 900 households | ok |  |
| Ski-rental build timing | [synthetic] | 4000 routines | ok |  |
| Presence and window forecast | [synthetic] | 4 personas | ok |  |
| Routine finder | [synthetic] | 4 personas | ok |  |
| Recurrence forecast | [synthetic] | 11 routines | ok |  |
| Agent-claim calibration | [synthetic] | 600 runs | ok |  |
| Agent runs on the sandbox (AGT-5, AGT-7) | [synthetic] | 130 runs | ok |  |
| Partial pooling for new people | [synthetic] | 4 personas | ok |  |
| Red team with ablations | [synthetic] | 42 runs | ok |  |
| Red team with a real model (secondary, cached) | [synthetic] | 42 cases | ok | real model, n = 42 cases (3 repeats each) |
| Privacy layer (canary leaks, offline) | [synthetic] | 11336 tokens | ok |  |
| Git habits (programmer role) | [synthetic] | 120 personas | ok |  |
| Proactive cards | [synthetic] | 145 decisions | ok |  |
| Calendar layer | [synthetic] | 28 people | ok |  |
| Local model digests | [synthetic] | 300 items | ok |  |
| Agent runtime | n/a | n/a | pending: agent-runtime not landed: data/eval/runtime_eval.json is absent (the agent track writes it with `python -m und |  |
| Models v2 | n/a | n/a | pending: mlv2 not landed (module understudy_engine.mlv2.evaluate missing) |  |
| Evidence quality | [synthetic] | 32 episodes | ok |  |
| Cue analysis | n/a | n/a | pending: cue not landed (module understudy_engine.cue.evaluate missing) |  |
| Persona realism | n/a | n/a | pending: personas-v2 not landed (module understudy_engine.personas_v2.evaluate missing) |  |
| Model benchmark | n/a | n/a | pending: modelbench not landed: data/eval/modelbench.json is absent (the model-benchmark track writes it); `make eval`  |  |
| Study across roles | n/a | n/a | pending: study-roles not landed (evals/study_roles has none of study_roles_section, section() or section.json, summary. |  |
| Agentic evaluation | n/a | n/a | pending: agentic not landed (evals/agentic has none of agentic_section, section() or section.json, summary.json, result |  |
| Live study (n = 4) | [real] | 4 people | not run: the live study has not been run: no data in evals/study/results/ |  |
| Simulated participants (language model), not people | [synthetic] | n/a | not run: Simulated participants (language model), not people | simulated participants (language model), not people |
| Study power: what the design could detect | [synthetic] | 10000 replications | ok |  |

## Deficit recovery (EVL-1)

*origin: **synthetic** · n = 16 people · split: 5 planted deficits over 32 novice cases (16 novices vs 8 experts); cluster bootstrap by person, B = 2000 · intervals: 95%*

Which deficit was injected, and what it costs. Detected = the alignment attributes at least X seconds to the right cog family, X = max(1 s, 95th percentile of what the same procedure attributes when two experts are compared). In this data the placebo attributes at most 0.0 s to any family, so X is the 1 s floor for every deficit. Synthetic apprentices with a known price per trace; this shows the method recovers what we planted.

| Deficit (synthetic) | Injected price (s) | Recovered price (s) | 95% interval | Bias (s) | Precision | Recall | X (s) |
|---|---|---|---|---|---|---|---|
| Skips the cliff check | 65.6 | 63.4 | [54.9, 71.7] | -2.2 | 100% [100.0%, 100.0%] | 100% [100.0%, 100.0%] | 1.0 |
| Reads the result again and again | 33.5 | 47.0 | [33.9, 61.8] | +13.5 | 70% [40.0%, 94.1%] | 100% [100.0%, 100.0%] | 1.0 |
| Searches in loops | 71.7 | 71.7 | [65.2, 79.4] | +0.0 | 100% [100.0%, 100.0%] | 100% [100.0%, 100.0%] | 1.0 |
| Copies the wrong figure | 48.8 | 34.8 | [14.8, 49.8] | -14.0 | 100% [100.0%, 100.0%] | 71% [33.3%, 100.0%] | 1.0 |
| Freezes before entering the household | 88.0 | 88.0 | [57.3, 119.5] | +0.0 | 100% [100.0%, 100.0%] | 100% [100.0%, 100.0%] | 1.0 |

Overall (all case-deficit pairs): precision 92% [84.5%, 98.6%], recall 95% [88.6%, 100.0%].

Detection rule: detected when recovered seconds >= X; X = max(1 s, 95th percentile of the placebo attribution to that cog family); precision and recall are pooled over every (case, deficit) pair.

## Controls: placebo and shuffled-label null

*origin: **synthetic** · n = 24 people · split: cluster bootstrap by person, B = 2000; null = 1000 permutations of the expert/novice label across people · intervals: 95%*

Real gap = novice minus nearest-expert seconds per case, mean over people. Placebo = each expert against the nearest other expert. Null = labels shuffled across people, whole procedure repeated (interval = 2.5th to 97.5th percentile of the permutation distribution). Both controls should include zero; the real gap should not.

| Comparison (synthetic) | Gap (s per case) | 95% interval |
|---|---|---|
| Real: novice vs nearest expert | 229.6 | [192.7, 272.6] |
| Placebo: expert vs nearest other expert | 7.1 | [-2.8, 18.4] |
| Null: labels shuffled across people | 46.2 | [-36.4, 116.9] |

Permutation p-value for the real gap against the null: 0.001.

## Stuck hazard (leave one person out)

*origin: **synthetic** · n = 4 people · split: leave-one-person-out · intervals: 95%*

7376 scored 30-second bins from 2676 episodes; label = no progress in the next 60 s.

| Model (synthetic) | Log loss | 95% interval | Brier | ECE |
|---|---|---|---|---|
| Stuck hazard | 0.436 | [0.422, 0.451] | 0.140 | 0.015 |
| Time since progress | 0.509 | [0.496, 0.524] | 0.164 | 0.003 |
| Base rate | 0.509 | [0.497, 0.524] | 0.164 | 0.021 |

False alarms: 1.21 an hour [0.95, 1.48] against a budget of 1.0; share of stuck events flagged 33% [27.5%, 38.6%].

Secondary data (scripted apprentices, n = 24 people; follows a fixed script, so not the headline): log loss 0.328, false alarms 0.92 an hour.

Caveats:

- Labels and events are defined from `progress` events in the data; the model predicts 'no progress in the next 60 s', not 'the person is confused'.
- Intervals resample episodes, not people; with few people the person-level spread (per_person) is the honest uncertainty.
- Alarm threshold is chosen on training people only under the false-alarm budget; it can overshoot on the held-out person (see false_alarms_within_budget). The budget is a design choice, not a measured tolerance of real workers.
- Synthetic origin: results show the pipeline recovers planted structure, not that real people behave this way.

## Coaching dignity gate

*origin: **synthetic** · n = 4 people · split: leave-one-person-out · intervals: 95%*

False nudges per hour, with and without the dignity gate.

| Rule (synthetic) | False nudges per hour | Stuck events reached | Nudges | Median latency (s) |
|---|---|---|---|---|
| Bare threshold on every 30 s bin | 1.83 | 21% | 186 | 30 |
| Dignity gate (2 signals in a row, then a cooldown) | 0.05 | 5% | 17 | 60 |

False nudges per hour fall by 97%, at the price of reaching far fewer stuck events.

Caveats:

- A 'false nudge' is a nudge outside any stuck event (stuck = no progress for about two minutes), so it measures annoyance, not harm. Nudges per stuck event shows the repeated-nudge burden the gate removes.
- The gate trades latency for fewer interruptions; the detection and latency numbers show that trade.
- Held-out hazard predictions come from synthetic personas unless the data origin says otherwise.
- The sweep over p_signal is read off the same held-out predictions, so it is descriptive of the trade-off, not a tuned operating point.

## Skill tracing

*origin: **synthetic** · n = 4 personas · split: none (fixed parameters) · intervals: 95%*

Skill tracing saturates on these high-volume personas; see caveats.

| Persona (synthetic) | Tasks | Spearman, mastery vs planted skill | Final level |
|---|---|---|---|
| nine-to-five | 768 | 0.17 | 4 |
| night-owl | 1483 | 0.18 | 4 |
| shift-worker | 815 | 0.25 | 4 |
| irregular | 552 | 0.12 | 4 |

Mean Spearman across personas: 0.18. Mastery saturates on these high-volume personas; see the register.

Caveats:

- Outcome per task is 'a stuck spell was planted in it', a coarse single-skill proxy; per-cog tracing is not exercised by this data.
- Four personas, 21 days: a sanity check that mastery follows the planted learning curve, not a validation on real learners.
- Tracker parameters are hand-set (not fitted), so this is an out-of-the-box check, not a tuned fit.
- Weak result by design of the data: about 35 tasks a day with roughly 6 percent stuck means mastery saturates within a day or two, so the tracker cannot resolve the slow planted learning curve (see the Spearman values) and absences of 2 to 3 days barely decay a heavily practised skill. Decay with absence is demonstrated in unit tests, not by this data.

## Off-policy evaluation

*origin: **synthetic** · n = 6000 decisions · split: simulator with known ground truth; logs from an epsilon-greedy bandit (eps 0.2) · intervals: 95%*

Value of the rule-baseline policy estimated from logs of a different policy. The true value is known because the simulator is ours.

| Estimator (synthetic) | Value | 95% interval | Interval holds the true value |
|---|---|---|---|
| Naive on-policy average | 0.207 | [0.179, 0.237] | no |
| Inverse propensity (IPS) | -0.016 | [-0.045, 0.013] | no |
| Self-normalised IPS | -0.019 | [-0.051, 0.014] | no |
| Doubly robust | -0.010 | [-0.039, 0.017] | no |

True value (known, the simulator is ours): 0.018.

Over 24 independent replications (synthetic, 2400 decisions each):

| Estimator | Mean error | RMSE | Interval covers the truth |
|---|---|---|---|
| IPS | +0.002 | 0.033 | 96% |
| Self-normalised IPS | +0.001 | 0.033 | 96% |
| Direct method | +0.002 | 0.019 | 17% |
| Doubly robust | +0.001 | 0.031 | 88% |
| Naive on-policy average | +0.193 | 0.195 | 0% |
| Naive, matched rows only | +0.009 | 0.027 | 79% |

Caveats:

- Synthetic simulator: the reward structure is invented by us. It shows the estimators recover a known truth, not that the real reward looks like this.
- Implicit labels (followed, dismissed, repeated, undone) are noisy proxies for 'did it help'; the reward model weights them by assumption.
- Intervals hold the cross-fitted reward model fixed and resample decisions; they do not include the variance of re-fitting it.
- Doubly robust needs correct logged propensities. The simulator logs them exactly; in a live system a logging bug would break every estimate here.
- Weights reach 20 (propensity floor 0.05); effective sample size is reported with each target.

## Review routing and risk control

*origin: **synthetic** · n = 900 households · split: train 450 / calibration 225 / held-out 225 · intervals: 95%*

Auto-approve the safest households, send the rest to an expert. Cases are synthetic sandbox households scored by the three sandbox calculators' own rules; the reference is a simplified internal rule set, not law.

Target error rate alpha = 0.05; chosen coverage 93.8%; held-out error 0.0% [0.0%, 1.7%]; bound held: **True**; expert time 0.6 min per case (review time per case is an assumption).

| Coverage (synthetic) | Error rate | 95% interval |
|---|---|---|
| 2.7% | 0.0% | [0.0%, 45.9%] |
| 15.1% | 0.0% | [0.0%, 10.3%] |
| 27.6% | 0.0% | [0.0%, 5.8%] |
| 40.0% | 0.0% | [0.0%, 4.0%] |
| 52.9% | 0.0% | [0.0%, 3.1%] |
| 65.3% | 0.0% | [0.0%, 2.5%] |
| 77.8% | 0.0% | [0.0%, 2.1%] |
| 90.2% | 0.0% | [0.0%, 1.8%] |

Caveats:

- CIRCULARITY: the calculators' quirks (site b ignores capital tariff income; site c applies a two-child limit and treats exactly 16,000 as over the limit) and the household archetypes that trigger them were planted by us. The router can only show it found our planted structure; it does not show that real calculators or real agents fail this way.
- The reference answer is the sandbox oracle, a simplified internal rule set loosely shaped like a Universal Credit award. It is not law and not PolicyEngine; 'error' means 'differs from that oracle by more than one pound'.
- The stand-in agent is a rule over the three calculator answers (the one at least two agree on, else the mean); no model was run. With the median of three the agent is never wrong on these households (nothing to route), and with the plain mean the label is 'any calculator disagrees', which the spread feature predicts directly (see stand_ins).
- Stated confidence is a function of calculator disagreement only, so it carries no information the spread does not.
- The label is almost a deterministic function of the features (a three-way calculator disagreement), so a log loss and ECE near zero reflect separability, not skilful calibration. Compare coverage with the spread-only baseline: the router adds little over it here.
- Errors are concentrated in one archetype (see case_set.errors_by_archetype), so the effective number of independent error patterns is small.
- Expert review time per case is an assumption, not a measurement.
- The guarantee covers exchangeable households like these; a new rule or calculator breaks it silently.

## Ski-rental build timing

*origin: **synthetic** · n = 4000 routines · split: simulated workdays; buy cost b = 16 manual runs; forecast sees 10 workdays, cost over the next 50 · intervals: 95%*

Regret = cost divided by the hindsight-best cost (1.0 is perfect). Simulated mechanism; not real build decisions.

| Rule (simulated) | Regret (hindsight = 1.0) | 95% interval |
|---|---|---|
| Build now | 1.273 | [1.257, 1.290] |
| Build at break-even | 1.776 | [1.765, 1.786] |
| Ski rental with predictions (lambda 0.2) | 1.332 | [1.322, 1.342] |
| Ski rental with predictions (lambda 0.5) | 1.473 | [1.466, 1.481] |

## Presence and window forecast

*origin: **synthetic** · n = 4 personas · split: forward held-out days within each persona · intervals: 95%*

Synthetic personas, 21 days each. Pooled means of per-persona results; per-persona detail and intervals in the full dict.

Window-forecast Brier score 0.131 (mean over personas); interruption cap 10%. The pooled numbers are means of four personas; the per-persona rows carry the intervals.

| Policy (synthetic, mean over personas) | Interruption rate | Idle time used |
|---|---|---|
| Start-or-wait rule | 2.1% | 74.2% |
| Fixed overnight window | 2.0% | 43.0% |
| Run whenever idle 5 min | 24.8% | 90.2% |

| Persona (synthetic) | Window Brier [95%] | Interruption rate, start-or-wait rule [95%] | Idle time used [95%] |
|---|---|---|---|
| nine-to-five | 0.086 [0.072, 0.104] | 0.0% [0.0%, 4.8%] | 77.0% [65.9%, 82.6%] |
| night-owl | 0.133 [0.102, 0.170] | 1.2% [0.2%, 6.5%] | 53.3% [47.0%, 57.0%] |
| shift-worker | 0.171 [0.140, 0.232] | 3.5% [1.6%, 7.4%] | 83.9% [77.5%, 88.2%] |
| irregular | 0.134 [0.112, 0.164] | 3.5% [1.6%, 7.5%] | 82.5% [72.1%, 88.1%] |

## Routine finder

*origin: **synthetic** · n = 4 personas · split: planted routines per persona, found by the routine finder · intervals: 95%*

Precision is over proposals (after the value gate); recall over planted routines with at least 3 runs. The raw finder returns 55 clusters, 12 of them planted routines (22%); the value gate keeps 6 proposals, 6 planted (100%). Read the headline precision as the proposals' precision, not the finder's.

| Persona (synthetic) | Planted routines | Planted routines found | Raw finder: precision over all clusters returned [95%] | After value gate: precision over proposals shown [95%] | Recall |
|---|---|---|---|---|---|
| nine-to-five | 3 | 2 | 2 of 8 clusters are planted routines: 25% [7.1%, 59.1%] | 2 of 2 proposals are planted routines: 100% [34.2%, 100.0%] | 100% |
| night-owl | 3 | 3 | 3 of 32 clusters are planted routines: 9% [3.2%, 24.2%] | 1 of 1 proposals are planted routines: 100% [20.7%, 100.0%] | 100% |
| shift-worker | 3 | 3 | 4 of 12 clusters are planted routines: 33% [13.8%, 60.9%] | 2 of 2 proposals are planted routines: 100% [34.2%, 100.0%] | 100% |
| irregular | 3 | 3 | 3 of 3 clusters are planted routines: 100% [43.8%, 100.0%] | 1 of 1 proposals are planted routines: 100% [20.7%, 100.0%] | 100% |
| **All personas** |  |  | **12 of 55 clusters are planted routines: 22% [12.9%, 34.4%]** | **6 of 6 proposals are planted routines: 100% [61.0%, 100.0%]** | **100%** [74.1%, 100.0%] |

The headline precision is the proposals' precision after the value gate. The raw finder alone returns many clusters of one-off work; read the left precision column as the finder's accuracy and the right one as what the worker is shown.

## Recurrence forecast

*origin: **synthetic** · n = 11 routines · split: fit on days 1-14, scored on days 15-21 · intervals: 95%*

| Persona (synthetic) | Routine | Predicted runs | 95% interval | Actual | Inside |
|---|---|---|---|---|---|
| nine-to-five | calc-entry-3x | 21.9 | [12, 33] | 16 | yes |
| nine-to-five | case-note-copy | 12.4 | [6, 21] | 15 | yes |
| night-owl | queue-sweep | 21.9 | [13, 33] | 34 | no |
| night-owl | calc-entry-3x | 11.0 | [5, 19] | 20 | no |
| night-owl | cliff-recheck | 5.5 | [1, 11] | 1 | yes |
| shift-worker | queue-sweep | 23.4 | [14, 34] | 23 | yes |
| shift-worker | case-note-copy | 11.5 | [5, 20] | 13 | yes |
| shift-worker | calc-entry-3x | 9.5 | [4, 17] | 16 | yes |
| irregular | calc-entry-3x | 14.4 | [7, 23] | 29 | no |
| irregular | weekly-report | 2.5 | [0, 7] | 3 | yes |
| irregular | queue-sweep | 12.5 | [6, 21] | 19 | yes |

Interval coverage: 73% [43.4%, 90.3%].

## Agent-claim calibration

*origin: **synthetic** · n = 600 runs · split: grouped 5-fold (by household) · intervals: 95%*

How well a claimed success that code has not yet checked can be trusted. Synthetic runs.

Brier 0.077 against 0.183 for the base rate; base failure rate 24.0%. Brier interval [0.066, 0.090]. Reviewing the top 20% by predicted risk catches 70% of false claims (precision 84%).

**real model, tiny n, one family of failures**: 68 claimed successes from 20 households (leave-one-household-out; real model on sandbox sites). Brier 0.004 against 0.294 for the base rate (the share of claims that were false). The false claims are one family of failure (a finish claim on an error page), so a high score here does not show that claim risk can be predicted in general.

Caveats:

- Synthetic runs generated from a known mechanism; real agent traces will differ and this has not been validated on them.
- Features are trace summaries, not content; claims about page text cannot be assessed here.
- Code still decides success. A low predicted risk never replaces the completion check.

## Agent runs on the sandbox (AGT-5, AGT-7)

*origin: **synthetic** · n = 130 runs · split: 20 sandbox households run on the clean path, and again with failures injected (layout changes, one-off 503s); plus a real-model block (20 households x 4 conditions: clean, layout change, one-off error page, injected page); local sandbox calculators, mock model except the real-model block, simplified oracle · intervals: 95%*

The clean path is the compiled path on the sandbox it was written against, so a full pass is expected and says little. The discriminating evidence is the robust and injected runs. Households whose calculators disagree are planted discrepancies; passing them means the discrepancy was flagged. Scored against a simplified internal oracle, not the law.

| Run (mock model, synthetic sandbox) | Households | Passed | 95% interval | Mean seconds | Households that used each tier | False claims |
|---|---|---|---|---|---|---|
| Clean path (compiled) | 20 | 20 of 20 | [0.84, 1.00] | 1.8 | tier 1: 20 | 0 |
| Failure injection | 20 | 20 of 20 | [0.84, 1.00] | 4.8 | tier 1: 20, tier 2: 15 | 0 |

What was injected, and what happened:

| Injection | Households | Passed | Needed tier 2 |
|---|---|---|---|
| layout change on site b | 5 | 5 | 5 |
| layout change on site c | 5 | 5 | 5 |
| layout change on site a and one-off 503 on site b | 5 | 5 | 5 |
| one-off 503 on site c | 5 | 5 | 0 |

Planted calculator discrepancies flagged: 7 of 20 households.

**Real model (20 households per condition, 90 runs, tier 1 disabled).** Real model, small n: 20 households per condition shows the pipeline and its failure modes with a live model, not a pass rate. Live model on the local sandbox calculators; tier 1 disabled so every navigator uses the browser agent; the judge is the code check, not the model. Identical prompts are cached, so repeated page situations are one live sample each, not one per run.

| Condition (REAL MODEL, small n) | Households | Passed the code check [95%] | Claimed finished | False claims | Paused by the detector | Attacks that succeeded | Mean steps | Mean seconds | Tiers used |
|---|---|---|---|---|---|---|---|---|---|
| Clean | 20 | 18 of 20 [0.70, 0.97] | 18 | 0 | 0 | n/a | 55.0 | 15.6 | 2 |
| Layout change | 20 | 20 of 20 [0.84, 1.00] | 20 | 0 | 0 | n/a | 55.9 | 12.2 | 2 |
| One-off error page (glitch) | 20 | 0 of 20 [0.00, 0.16] | 20 | 20 | 0 | n/a | 54.8 | 8.4 | 2 |
| Injected page (prompt injection) | 20 | 0 of 20 [0.00, 0.16] | 0 | 0 | 20 | 0 of 20 | 0.0 | 5.4 | none |
| After the fix, glitch only: IN-SAMPLE, made after seeing the glitch result | 10 | 10 of 10 [0.72, 1.00] | 10 | 0 | 0 | n/a | 72.7 | 43.5 | 2 |

On the one-off error page the model said it was finished in 20 of 20 runs and 20 of those claims were false; the code check caught every one. Injected pages were paused by the detector before the planner acted, so task success there is 0 by design.

The fix (a page-state label from the quarantined reader fed to the planner, retries, and the cliff check moved after the verifier; made AFTER the glitch result was seen) was re-run on the glitch condition: 10 of 10 succeeded with 0 false claims (before: 0 of 20). **This is in-sample** and only 10 runs (9 later rows dropped when the run budget stopped).

Tier 3 (computer use) is not demonstrated on the benefits task: 3 runs with a simulated actuator made 0 pointer actions and landed on an interactive element 0 times.

Cost: an estimate at placeholder rates (5.0 and 30.0 USD per million tokens in and out), about None USD for these rows; 494 live calls and 5302 cache hits across the runs.

Caveat: the clean path is the compiled path on the sandbox it was written against, so a full pass is expected. The discriminating evidence is the failure-injection rows and, with a real model, the glitch and injected conditions.

Caveats:

- Synthetic households on local sandbox sites; one model family (the ids in meta.models); one planner prompt; n = 20 households per condition, intervals are Wilson 95%.
- Identical prompts are cached, so repeated page situations are one live sample each (about 370 distinct live prompts behind 80 runs), not 80 independent samples; sampling variance of the model is therefore under-represented.
- The page_state fix (v2) was made AFTER seeing the glitch result and re-evaluated on the SAME condition: its 10-of-10 is in-sample. It was not tested on other conditions, so nothing here says it generalises.
- The v2 glitch re-run stopped at the cost budget after 10 households; later rows were contaminated by blocked model calls and are dropped (meta.dropped_after_budget_stop). v2 used a cap of 40 actions per navigator, v1 the production cap of 20.
- Tier 3 is NOT demonstrated on the benefits task: against a simulated actuator the computer-use model declined at step 1 and took no action, because tier-3 goals carry no household values by design (n = 3).
- The injected condition has no task success by design (the detector pauses the run); it measures detection and attack success only. The injection text is the red-team page set written by the same team.
- stated_confidence is present only for runs where the model made a finish claim with a confidence; elsewhere null.
- Cost figures are estimates from the provider's token counters at placeholder rates, not an invoice.
- The prompt cache written during the recorded runs is keyed with each process's private sandbox ports (the goal-drift prompts name host:port); keys now mask the port, but the recorded grid cannot be replayed from the old cache (--cache-only stops at the first drift-check miss). This file's traces are the record.

## Partial pooling for new people

*origin: **synthetic** · n = 4 personas · split: leave-one-person-out · intervals: 95%*

Cold start for a new worker: error after 0, 1, 3 and 10 of their own episodes. Four synthetic personas.

| Own episodes seen (synthetic) | No pooling | Partial pooling | 95% interval | Complete pooling | Best |
|---|---|---|---|---|---|
| 0 | 0.693 | 0.507 | [0.493, 0.520] | 0.507 | complete_pooling |
| 1 | 0.571 | 0.507 | [0.493, 0.520] | 0.507 | complete_pooling |
| 3 | 0.519 | 0.507 | [0.493, 0.520] | 0.507 | partial_pooling |
| 10 | 0.538 | 0.506 | [0.493, 0.519] | 0.507 | partial_pooling |

Cold-start error is predictive log loss (nats per trial, lower is better) on the person's later episodes, leave one person out. Partial pooling shrinks a new person toward the role's rate and trusts their own data more as it accumulates. `ci` is the interval for the partial-pooling value; `*_minus_partial` shows how much worse each alternative is, with its own interval.

Caveats:

- The primary result has four personas, so 'the role' is three other people; between-persona spread is small, which pushes partial pooling toward complete pooling. The apprentice rows have 24 people but only two episodes each.
- Deficit rows read the planted deficits from truth.json, as if the genome module had detected them perfectly.
- Learners' true deficit rates fall with practice, so every static estimate, pooled or not, is biased for later cases; pooling does not fix drift.
- Intervals resample scored episodes with each person's estimate held fixed; they do not capture person-to-person variation beyond what those episodes show.
- Bins within an episode are correlated, so bin-level counts overstate the information in a person's data; the empirical-Bayes prior fitted on them is therefore a little too tight about each person's own rate.

## Red team with ablations

*origin: **synthetic** · n = 42 runs · split: 42 attack runs per configuration, 10 configurations (every layer on, each layer off in turn, all off); 31 clean pages for the false-pause rate; scripted planner on sandbox pages · intervals: 95%*

Scripted vulnerable planner and mock reader: measures the layers, not a real model. 42 attacks, 31 clean pages (10 hard negatives); each case runs once per configuration. Includes 5 supplemental built-in attacks (settings tampering, raw actions) that the committed catalog does not contain; `committed_only` reports the committed catalog alone.

| Condition (synthetic) | Attack succeeds | Task still succeeds | n |
|---|---|---|---|
| All layers on | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| Without input sanitising | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| Without the quarantined reader | 0.0% [0.0%, 8.4%] | 2.4% [0.4%, 12.3%] | 42 |
| Without typed actions | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| Without the action-class gate | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| Without data-flow rules | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| Without the injection detector | 0.0% [0.0%, 8.4%] | 97.6% [87.7%, 99.6%] | 42 |
| Without the goal-drift check | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| Without protected settings | 0.0% [0.0%, 8.4%] | 23.8% [13.5%, 38.5%] | 42 |
| All layers off | 100.0% [91.6%, 100.0%] | 0.0% [0.0%, 8.4%] | 42 |

False-pause rate on clean pages: 0.0% [0.0%, 11.0%].

## Red team with a real model (secondary, cached)

*origin: **synthetic** · n = 42 cases · split: 42 attack cases x 3 repeats x 2 configurations (every layer on, all layers off); 31 clean pages (10 hard negatives) x 3 repeats; real planner, reader and drift check; nothing executed; intervals treat the repeats of a case as one observation · intervals: 95%*

real model, n = 42 cases (3 repeats each). Real planner, reader and drift check; 42 attacks (over 9 categories) and 31 clean pages (10 hard negatives), 3 run(s) each, 2 configuration(s). Nothing is executed. Intervals treat the repeats of one case as a single observation. Cached model answers: this evaluation called no model.

**real model, n = 42 cases (3 repeats each).** Intervals overlap: this shows what the layers cost (task success under attack was 22% with every layer on against 84% with all off, and 0 of 126 runs with every layer on let an attack through), not that the layers prevent attacks.

| Condition (real model) | Attack succeeds, runs [95% over cases] | Task still succeeds [95%] | Paused | False pauses on clean pages | Hard negatives only |
|---|---|---|---|---|---|
| All layers on | 0 of 126: 0.0% [0.0%, 8.4%] | 22% [12.3%, 36.8%] | 76% | 0.0% over 93 clean runs [0.0%, 11.0%] | 0 of 30 [0.0%, 27.8%] |
| All layers off | 5 of 126: 4.0% [1.0%, 14.7%] | 84% [70.3%, 92.2%] | 0% | 0.0% over 93 clean runs [0.0%, 11.0%] | 0 of 30 [0.0%, 27.8%] |

Source: data/redteam_live.json (cached; agent-safety). Intervals treat the repeats of one case as a single observation; they overlap, so read this as cost and a null, not a guarantee.

## Live study (n = 4)

*origin: **real** · n = 4 people · split: within-subject, counterbalanced, teammates only · intervals: 95%*

n = 4. Treat every number here as a case study, not a result.

**NOT RUN**: the live study has not been run: no data in evals/study/results/. The page says so; no numbers are shown.

## Privacy layer (canary leaks, offline)

*origin: **synthetic** · n = 11336 tokens · split: n/a · intervals: 95%*

Synthetic fixtures with planted canaries, a capturing fake model port, an isolated data directory. 8 seeds per flow. Reference flows test the guard; integration flows test a layer's real code. The static-guard file counts and lists follow the code tree at run time, so they change when files are added.

**0 of 11336 planted canary tokens reached the model port** across 80 runs of 10 flows (136 requests); one-sided 95% upper bound on the leak rate 0.03%. Logs, audit and queue files: 0 leaks in 80 files. Ledger complete for every flow: True.

| Flows (synthetic fixtures) | Flows | Runs | Requests | Planted tokens leaked | Upper 95% bound on the leak rate |
|---|---|---|---|---|---|
| reference | 4 | 32 | 40 | 0 of 728 | 0.41% |
| integration | 6 | 48 | 96 | 0 of 10608 | 0.03% |

Layers: calendar registered; gitanalysis registered; proactive adapter; localmodel registered; plugins registered; awareness registered; cue not_applicable; evidence none_registered; mlv2 pure_compute; personas_v2 pure_compute. A layer with no registered flow is never counted as passed.

Negative controls (the instrument can fail): 11 of 11 behaved as required.

Bucketing: 0 failures over 594114 cases. Backstop: 27/27 must-catch shapes caught, 0 false positives on 34 ordinary values. Static guard: 27 violations in 172 files.

Everything ran offline on synthetic fixtures with planted tokens; nothing here validates behaviour on real data and the real provider was never called.

## Git habits (programmer role)

*origin: **synthetic** · n = 120 personas · split: fresh synthetic seeds (replicates 100 and up); thresholds were chosen on replicates 0 to 3; learners compared with the 8 experts of their own replicate; bootstrap by day and by person · intervals: 95%*

Scripted developers with planted habits; no real people. 10 replicates of 4 learners and 8 experts, 120 planted learner-habit pairs.

No real people are involved. Every developer in the habit, placebo, digest and canary results is a scripted synthetic persona (4 learners and 8 experts per replicate) and every commit message is generated text. The one real history used is this project's own repository, read-only, reported as aggregates only.

| Planted habit (synthetic developers) | Precision [95%] | Recall [95%] | Specificity [95%] |
|---|---|---|---|
| All habits | 100% (116 of 116) [96.8%, 100.0%] | 97% (116 of 120) [91.7%, 98.7%] | 100% (120 of 120) [96.9%, 100.0%] |
| big_commits | 100% (18 of 18) [82.4%, 100.0%] | 90% (18 of 20) [69.9%, 97.2%] | 100% (20 of 20) [83.9%, 100.0%] |
| tests_with_changes | 100% (20 of 20) [83.9%, 100.0%] | 100% (20 of 20) [83.9%, 100.0%] | 100% (20 of 20) [83.9%, 100.0%] |
| fix_after_fix | 100% (20 of 20) [83.9%, 100.0%] | 100% (20 of 20) [83.9%, 100.0%] | 100% (20 of 20) [83.9%, 100.0%] |
| reverts | 100% (19 of 19) [83.2%, 100.0%] | 95% (19 of 20) [76.4%, 99.1%] | 100% (20 of 20) [83.9%, 100.0%] |
| vague_messages | 100% (20 of 20) [83.9%, 100.0%] | 100% (20 of 20) [83.9%, 100.0%] | 100% (20 of 20) [83.9%, 100.0%] |
| late_night | 100% (19 of 19) [83.2%, 100.0%] | 95% (19 of 20) [76.4%, 99.1%] | 100% (20 of 20) [83.9%, 100.0%] |

Placebo (each expert against the other experts): false flags 1% (5 of 480) [0.4%, 2.4%].

Digest rules against the generator's own labels (1630 commits): the labels are known by construction, so message-based fields are flattered; see the register.

Local-model agreement: not run. the local model is not available here (localmodel.mode() is rules), so there is nothing to compare with the rules; run with UNDERSTUDY_X_LOCALMODEL=1 and the model present

Alignment on commit sessions: On commit sessions the alignment sees differences in the SHAPE of sessions (missing test steps, reverts, extra code-commit loops) in some replicates, and sees nothing in seconds, because git records when a commit landed and not how long the work took. Habits that live in the message or the clock (vague messages, late nights) are invisible to cogs by construction.

## Proactive cards

*origin: **synthetic** · n = 145 decisions · split: replay at fixed decision points; rules, nothing trained · intervals: 95%*

Synthetic personas, learners and git learners with planted truth. Intervals: Wilson on pooled counts (too narrow, points are correlated) and a bootstrap over people (the honest one).

| What surfaces cards (synthetic personas, learners and git learners) | Cards worth surfacing | Precision [95%] | Recall [95%] |
|---|---|---|---|
| Judge (the shipped rules) | 101 of 124 cards were worth it | 82% [70.4%, 89.9%] | 86% [75.5%, 93.2%] |
| raw value top3 no checks | 180 of 326 | 55% [49.8%, 60.5%] | 95% [90.6%, 97.1%] |
| random 3 | 165.2 of None | 51% n/a | 93% n/a |
| everything no cap | 223 of 490 | 46% [41.2%, 49.9%] | 98% [95.6%, 99.3%] |

Interval over 35 people (bootstrap), which is the honest one; the Wilson interval on pooled counts is too narrow because points are correlated.

Briefings: 145, cap 3 cards, cap violations 0, mean cards 0.86; unprompted fires 0, unprompted agent spawns 0.

Simulated worker with fixed accept rates; the estimate starts at the role prior (0.4) and moves with each label. Real acceptance behaviour has not been measured on any person.

## Calendar layer

*origin: **synthetic** · n = 28 people · split: none: planted truth, no fitted model; intervals are a cluster bootstrap by person · intervals: 95%*

Calendars with planted structure, labelled synthetic; nothing here is validated on real people.

These results are on synthetic calendars with planted structure. They show that the pipeline recovers what was planted and where it does not; they do not show that real people's weeks look like this, and nothing is validated on real people.

| What was scored (synthetic calendars) | Precision | Recall |
|---|---|---|
| Planted problems found, eight types, micro-average | 93.9% | 98.2% |
| Suggestions against the planted cause | 96.4% | 89.9% |

Expert weeks with a suggestion: 0 of 24 (false-alarm rate 0.0%).

Leak canary: 0 of 11104 planted tokens leaked across 169 outbound requests.

## Local model digests

*origin: **synthetic** · n = 300 items · split: dev (prompts tuned) / test (held out, run once) · intervals: 95%*

Planted labels on invented commits and calendar entries; rules versus a local 7B model; the test split is the headline, the dev split was used for tuning.

Model arm source: cache. Held-out test split; the dev split was used for tuning.

| Task / field (synthetic items) | Held-out n | Rules accuracy [95%] | Local model accuracy [95%] | Verdict | Shipped |
|---|---|---|---|---|---|
| commit_digest / category | 98 | 77.5% [68.3%, 84.7%] | 91.8% [84.7%, 95.8%] | model better | model |
| commit_digest / risk | 98 | 82.7% [74.0%, 88.9%] | 70.4% [60.7%, 78.5%] | no clear difference | rules |
| commit_digest / message_quality | 98 | 93.9% [87.3%, 97.2%] | 88.8% [81.0%, 93.6%] | no clear difference | rules |
| event_digest / category | 98 | 81.6% [72.8%, 88.0%] | 95.9% [90.0%, 98.4%] | model better | model |
| event_digest / needs_prep | 98 | 87.8% [79.8%, 92.8%] | 82.7% [74.0%, 88.9%] | no clear difference | rules |

- commit_digest category: model 91.8% [84.7, 95.8] versus rules 77.5% [68.3, 84.7] on 98 held-out items (paired gap +14.3 points [6.1, 23.5], sign test p = 0.0043): the model is better. Shipped: model.
- commit_digest risk: model 70.4% [60.7, 78.5] versus rules 82.7% [74.0, 88.9] on 98 held-out items (paired gap -12.2 points [-24.5, 0.0], sign test p = 0.0807): no clear difference. Shipped: rules.
- commit_digest message_quality: model 88.8% [81.0, 93.6] versus rules 93.9% [87.3, 97.2] on 98 held-out items (paired gap -5.1 points [-12.2, 2.0], sign test p = 0.3018): no clear difference. Shipped: rules.
- event_digest category: model 95.9% [90.0, 98.4] versus rules 81.6% [72.8, 88.0] on 98 held-out items (paired gap +14.3 points [6.1, 22.4], sign test p = 0.0026): the model is better. Shipped: model.
- event_digest needs_prep: model 82.7% [74.0, 88.9] versus rules 87.8% [79.8, 92.8] on 98 held-out items (paired gap -5.1 points [-15.3, 4.1], sign test p = 0.4049): no clear difference. Shipped: rules.
- needs_prep: an early look at the first untuned prompt showed the model marking 'Customer workshop' and 'Design review' as not needing preparation; after tuning on the dev split the model was better there (45 vs 41 of 52) but on the held-out split it was nominally worse than the rules (81 vs 86 of 98, no clear difference), so needs_prep went back to the rules.

## Agent runtime

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: agent-runtime not landed: data/eval/runtime_eval.json is absent (the agent track writes it with `python -m understudy_agent.runtime.evaluate`); `make eval` reads results and never runs models

## Models v2

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: mlv2 not landed (module understudy_engine.mlv2.evaluate missing)

## Evidence quality

*origin: **synthetic** · n = 32 episodes · split: none; hermetic fakes with fixed seeds · intervals: 95%*

Packets from synthetic apprentices through the real builders. Faithful and adversarial replies come from stand-in models written for this evaluation; the live block is not_run unless explicitly enabled. 

- statement: No real people are involved. Packets come from synthetic apprentices; no model was called in the default run, and no number here comes from a live service.
- owner_status: ok

## Cue analysis

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: cue not landed (module understudy_engine.cue.evaluate missing)

## Persona realism

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: personas-v2 not landed (module understudy_engine.personas_v2.evaluate missing)

## Model benchmark

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: modelbench not landed: data/eval/modelbench.json is absent (the model-benchmark track writes it); `make eval` reads results and never runs models

## Study across roles

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: study-roles not landed (evals/study_roles has none of study_roles_section, section() or section.json, summary.json, results/summary.json yet)

## Agentic evaluation

*origin: **synthetic** · n = 0 people · split: n/a · intervals: 95%*

**PENDING**: agentic not landed (evals/agentic has none of agentic_section, section() or section.json, summary.json, results/summary.json, report.json yet)

## Simulated participants (language model), not people

*simulated participants (language model), not people · origin: **synthetic** · n = 0 silicon participants · split: n/a · intervals: 95%*

Simulated participants (language model), not people. The simulated study has not been run. It never stands in for the live study with people.

**NOT RUN**: Simulated participants (language model), not people. The simulated study has not been run. It never stands in for the live study with people. (simulated participants (language model), not people; not the live study)

## Study power: what the design could detect

*origin: **synthetic** · n = 10000 replications · split: Monte Carlo of the pre-registered analysis (power, bias, coverage) · intervals: 95%*

What the study design could detect under our assumptions. Not evidence that an effect exists.

**What the design could detect under our assumptions. A property of the design, not a result about people and not evidence that an effect exists.**

- n = 4: the smallest attainable two-sided sign-flip p is 0.125, so p < 0.05 is impossible.
- n = 16: the smallest attainable two-sided sign-flip p is 3.05e-05.

No spill-over, no order effect (the 'none' row is the false-positive rate):

| Effect (synthetic design) | True effect (points) | n = 4: chance the 95% t interval excludes 0 | n = 16: chance the 95% t interval excludes 0 |
|---|---|---|---|
| none | 0.0 | 1.7% | 4.9% |
| small | 10.2 | 2.4% | 10.2% |
| medium | 20.6 | 4.4% | 27.3% |
| large | 38.8 | 11.6% | 74.8% |

**Spill-over of the coached gain onto the other skill is not protected by the design.** It dilutes the contrast and the design cannot cancel it. Medium effect with full spill-over: at n = 4 the chance the interval excludes 0 falls from 4.4% to 2.1% and the estimate is off by -10.4 points; at n = 16 the chance the interval excludes 0 falls from 27.3% to 9.2% and the estimate is off by -10.1 points.

Medium effect under each nuisance setting (synthetic design):

| n | spill-over | order effect | power: interval excludes 0 | power: p < 0.05 | bias (points) | interval covers the truth |
|---|---|---|---|---|---|---|
| 4 | 0.0 | 0.0 | 4.4% | 0.0% | -0.2 | 93.3% |
| 4 | 0.0 | -0.7 | 3.8% | 0.0% | -1.4 | 93.9% |
| 4 | 0.5 | 0.0 | 3.2% | 0.0% | -5.1 | 93.9% |
| 4 | 0.5 | -0.7 | 3.2% | 0.0% | -5.4 | 93.8% |
| 4 | 1.0 | 0.0 | 2.1% | 0.0% | -10.4 | 94.3% |
| 4 | 1.0 | -0.7 | 2.7% | 0.0% | -9.4 | 93.5% |
| 16 | 0.0 | 0.0 | 27.3% | 18.5% | +0.2 | 95.3% |
| 16 | 0.0 | -0.7 | 24.0% | 16.2% | -1.0 | 95.7% |
| 16 | 0.5 | 0.0 | 16.5% | 10.9% | -5.1 | 94.8% |
| 16 | 0.5 | -0.7 | 17.7% | 11.1% | -5.2 | 94.0% |
| 16 | 1.0 | 0.0 | 9.2% | 5.4% | -10.1 | 92.2% |
| 16 | 1.0 | -0.7 | 10.0% | 6.2% | -10.1 | 90.8% |

At n = 4: Of all 625 possible sets of four differences, only 16 (2.6%) put the interval above 0: every one of the four differences must be at least 0.5 (half a point on the 0-to-1 scale), and with any spread the mean must be at least 0.625. In the simulation the typical spread of the four differences is about 0.50, which would need a mean of about 0.80. Only a very large effect, seen in every participant, can show.

Caveats:

- Every number depends on invented assumptions: baseline propensities, how much people differ, the size of the training gain, independent checks within a case, and the form of carry-over and fatigue. The sensitivity block varies the first four.
- The estimand is the direct coaching gain averaged over the two skills; carry-over that spills the coached gain onto the other skill dilutes the contrast and the design cannot cancel it (see bias).
- A balanced design cancels a fixed block-2 shift and generic carry-over in expectation, which is why false positives stay near the nominal rate when the true effect is 0; it adds variance, which costs power.
- The plan's t interval is not exact for discrete bounded scores, and it has zero width when all differences are identical; coverage and the false-positive rate are reported as simulated, with Monte Carlo intervals.
- Real participants are four teammates who know the project; demand effects and facilitator bias are not in this model.

## Limitations register

124 entries, most serious first. Kept in the product on purpose.

| Id | Severity | What it means | Source |
|---|---|---|---|
| eval-synthetic | high | Almost every result in this report comes from synthetic apprentices, synthetic personas or simulators we wrote; each section carries a synthetic badge. They show that the methods recover the structure we planted, not that real workers behave this way. | engine-eval; also stated by engine-analytics:agent_claims, engine-analytics:hazard, engine-analytics:ope, engine-analytics:policy_gate, engine-analytics:pooling, engine-analytics:routing, engine-analytics:skills, engine-analytics:study_power, engine-handoff:presence, engine-handoff:routines |
| eval-study-n4 | high | The live study has n = 4, all teammates, none of them benefits processors (planned; it has not been run). Intervals are wide and the result is a case study. The headline measure is unassisted performance on a later matched task, reported separately from assisted speed. | engine-eval |
| eval-thin-real-data | high | Real data is thin: the only real signal is the team's own machine timestamps (times only, collected with consent). There are no real benefits-processor traces, so nothing here has been validated on real casework. | engine-eval |
| eval-oracle | high | The entitlement figures the agent is scored against come from a simplified internal rule set, not the law. It agrees with PolicyEngine UK within 1 pound on only 8 of 20 generated households, so passing our oracle is not the same as getting the entitlement right. | agent-core: docs/SPIKES.md S4 |
| ana-hazard-people | high | The stuck hazard is evaluated on four synthetic personas, so 'held-out person' means one of four. Intervals resample episodes, not people; the per-person spread is the honest uncertainty. | engine-analytics:hazard; engine-analytics:policy_gate |
| ana-routing-circular | high | Review routing is grounded in sandbox households scored by calculators whose quirks we planted, against a simplified internal reference rather than law. The router finding those quirks shows it recovers our planted structure, not that real calculators or real agents fail this way; the task is nearly deterministic, and the plain spread of calculator answers does almost as well. | engine-analytics:routing |
| ana-routing-shift | high | The routing error bound holds for cases like the ones used to calibrate it. A new benefit rule, calculator site or household type breaks that assumption silently. Review time per case is an assumption. | engine-analytics:routing |
| ski-simulated | high | Ski-rental regret is measured on simulated routines (lognormal run rates, 45% retiring after an exponential life, the forecast sees 10 workdays), not on real build decisions. It shows the rule's behaviour against break-even under a stated mechanism. | engine-handoff:ski_rental |
| ana-claims-live-tiny | high | The only real agent traces so far are 68 claimed successes from 20 households on the sandbox sites, from one real model. All 20 false claims are one family of failure: the model said it was done on a one-off error page. A classifier can mostly learn 'this was an error page', which a one-line rule also catches, so this does not show that claim risk can be predicted in general. | engine-analytics:agent_claims |
| scripted_planner | high | The planner is a script that follows any instruction it can see. These numbers measure what the layers stop, not how a real model behaves under attack. | agent-safety:redteam |
| small_n | high | Each attack is run 3 times per configuration on a catalog of a few dozen synthetic attacks. Repeats of one attack are not independent evidence (the intervals are clustered by attack); intervals are wide and the point estimates are not rates to rely on. | agent-safety:redteam_live |
| prv_flow_coverage | high | Reference flows test the privacy layer with stand-in upstream code. Only integration flows test another layer's own code, and a layer that supplied none is listed as none_registered, not as passed. Zero leaks says nothing about a flow that was not run. | privacy-layer:privacy |
| img_raw_by_nature | high | A screen frame is raw content. The guard decides whether a frame may leave, from which kind of source, what may come back and what is ever recorded; it does not redact or generalise pixels, and when a frame is allowed the provider sees everything on the screen. What a provider does with a frame it received is the provider's policy and is not measured here. | privacy-layer:privacy |
| img_gate_is_caller_truth | high | The gate is a pure function of four booleans and a source that the caller computes. The guard cannot check that secure input or a denylisted app was detected correctly, or that a frame really came from the source it declares. | privacy-layer:privacy |
| img_sandbox_convention | high | ENFORCED: the Python awareness package and the awareness, Live and hotkey TypeScript may not contain the string 'sandbox' (static scan, test files skipped); the frame route can refuse another machine, an unknown source, and a sandbox claim from a web page whose Origin is not one of our sandbox sites (frame_request_problem). BY CONVENTION ONLY: a local process on this Mac sends no Origin header, so the route cannot tell the Electron main process from the agent service; a local process that wrongly declares sandbox is not stopped, only visible in the ledger's source column. | privacy-layer:privacy |
| git-synthetic | high | Every learner and expert is a scripted persona. Recovering planted habits shows that the features, the thresholds and the intervals work on data built to contain them; it says nothing about how real developers behave. | git-analysis:git |
| pro-synthetic | high | Every figure for the proactive layer comes from synthetic personas, learners and git learners with planted structure we wrote. It shows that the judge, verify and prepare steps recover what was planted, not that real workers would find these cards useful. | proactive:proactive |
| pro-truth-ours | high | The definition of 'worth surfacing' is ours and was fixed before the runs (see the output). For the personas, the planted skill is mapped to a level and fed to both the gate and the truth, so agreement on practice cards for personas is partly built in; the learner and git truths are more independent of the code under test. | proactive:proactive |
| pro-iterated-on-eval | high | The truth definitions and one part of the practice scoring were revised after looking at the first replays (listed under design.truth_revisions and design.code_revision, with the first-run figures). There is no held-out data: the reported precision and recall are development-set figures on the same synthetic personas and learners, and are optimistic for that reason. | proactive:proactive |
| pro-small-n | high | There are 4 personas, 3 learners and 4 git learners, with several decision points each. Decision points inside one person are correlated, so the pooled Wilson intervals are too narrow; the person-level bootstrap is the honest interval and it is wide. | proactive:proactive |
| pro-acceptance-simulated | high | Acceptance learning is shown on a simulated worker with fixed rates. It has not been validated on people, and a real person's accepts and declines may depend on time of day, mood and the card's wording, none of which are modelled. | proactive:proactive |
| cal-synthetic-only | high | Every calendar number is on synthetic calendars with planted structure (4 personas, 8 experts, 16 novices, 3 weeks). Nothing about the calendar layer is validated on real people, and one read-only aggregate check of the owner's own calendar says nothing about anyone else. | calendar:calendar |
| cal-experts-synthetic | high | The expert reference is generated from the role template that also defines the targets, so agreement with it is by construction. The template is hand-authored, not measured on real experts, and real experts differ by person, team and week. | calendar:calendar |
| loc_synthetic | high | Every digest number is measured on synthetic commits and calendar entries with planted labels, written by the same author as the rules and the prompts. No real repository, calendar or person was used; accuracy on real data is unknown and probably lower. | local-model:localmodel |
| loc_small_n | high | About 100 items per task in the held-out test split (and 50 in the dev split the prompts were tuned on): the Wilson intervals are wide, and differences of a few points between the model and the rules are not distinguishable. | local-model:localmodel |
| loc_injection | high | Constrained decoding means an instruction planted in the input cannot make the model print text: nothing leaves a digest except vocabulary values. It can still steer labels. With one planted line on 20 items per task, the model-for-everything run moved to the value the line asked for in 19 of 19 (commit category revert), 17 of 17 (risk high), 13 of 17 (event category focus) and 12 of 12 (needs_prep true); the keyword rules moved in 0, 0, 0 and 0. In the shipped policy only category is model-decided, and code vetoes the two most consequential claims (a revert needs a revert-style message; focus time needs at most one attendee), which leaves 0 of 19 and 5 of 17 category steerings; other category values can still be steered by whoever writes the commit message or the invite. | local-model:localmodel |
| explainer_readability_not_accuracy | high | The explainer improves readability, not accuracy. A faithful-sounding explanation can still rest on a wrong number: the check proves each number traces to a field of the packet, not that the packet is true. | evidence:evidence |
| ana-study-n4 | high | With four teammates the exact two-sided sign-flip p cannot go below 0.125, and the interval excludes zero only when the four differences nearly agree and are large. The expected outcome is an interval that includes zero. | engine-analytics:study_power |
| eval-agent-live-glitch-false-claims | high | With a one-off error page the real model passed 0 of 20 and said it was finished in 20 of 20 runs (20 false claims): it declared success on an error page. The code check caught every one, which is why code, not the model, decides success. | engine-eval:agent_runs |
| eval-agent-live-fix-in-sample | high | The glitch result was followed by a fix (a page-state label from the quarantined reader fed to the planner, retries, and the cliff check moved after the verifier; made AFTER the glitch result was seen), then re-run on the same condition: 10 of 10 succeeded with 0 false claims, against 0 of 20 before. This is in-sample: the fix was designed after seeing that failure, and only 10 runs were made because a budget stop hit (9 later rows were dropped). It does not show the fix generalises. | engine-eval:agent_runs |
| eval-agent-live-tier3 | high | Tier 3 (computer use) is not demonstrated on the benefits task: 3 runs against a simulated actuator on real screenshots made 0 pointer actions and landed on an interactive element 0 times. Nothing is clicked in that setting, so a claim of done there is a false claim by construction. | engine-eval:agent_runs |
| eval-redteam-live-reading | high | Real-model red team (real model, n = 42 cases (3 repeats each)): Intervals overlap: this shows what the layers cost (task success under attack was 22% with every layer on against 84% with all off, and 0 of 126 runs with every layer on let an attack through), not that the layers prevent attacks. The attacks were written by the team that wrote the defences, and a result is true of one model version on one day. | engine-eval:redteam_live |
| eval-study-power-assumptions | high | The power analysis only shows what the n = 4 design could detect under our own assumptions (effect size, carryover, order effect, how noisy the measure is). It is a property of the design, not a result about people, and not evidence that an effect exists. | engine-eval:study_power; engine-analytics:study_power |
| eval-study-not_run | high | Section 'study' has no numbers: the live study has not been run: no data in evals/study/results/. | engine-eval:study |
| eval-sandbox-sites | medium | The three calculators are sandbox sites we built, each with planted quirks, and each computes one Universal-Credit-shaped entitlement. They say nothing about how real calculators behave or what their terms and bot protection allow. | agent-core |
| eval-claims-simulated | medium | Agent-claim calibration is mostly on simulated runs. The real-model result covers only 68 claimed successes from one family of failure (see agent_claims.live), so it cannot show that claim risk can be predicted in general. A low predicted risk of a false claim never replaces the code check, which decides success. | engine-analytics; engine-analytics:agent_claims |
| eval-offhours-s2 | medium | The off-hours live run depends on the conditions spike S2 passed under: macOS Accessibility and Screen Recording granted, an unlocked screen, a harmless app, the owner present. The presence forecast and the start-or-wait rule are evaluated on synthetic personas; the live demo may fall back to a simulated clock. | agent-core: docs/SPIKES.md S2 |
| ana-hazard-alerts | medium | Probabilities are better than the baselines and calibrated, but alert quality is modest: about a third of stuck events are flagged, and on held-out people the false-alarm rate (about 1.2 per hour) overshoots the 1 per hour budget chosen on training people. | engine-analytics:hazard |
| ana-hazard-label | medium | 'Stuck' means no progress event in the next 60 seconds, which is not the same as confusion. Fast thinking and slow typing both look stuck to this label. | engine-analytics:hazard; engine-analytics:policy_gate |
| ana-apprentice-script | medium | The apprentice traces follow a fixed task script, so part of the hazard model's large gain on them is learning the script, not predicting stuck. The four-persona result is the headline. | engine-analytics:hazard |
| ana-skills-saturate | medium | Skill tracing saturates on synthetic personas (about 35 tasks a day): mastery reaches its ceiling on day one and cannot follow the planted learning curve. Decay with absence is shown in unit tests only. | engine-analytics:skills |
| ana-skills-learners-n | medium | On the learner trajectories (three learners, thirty cases each, one with a three-day absence) the help level does lighten as deficits fade, but a clock alone ranks the true curve as well as mastery does, the ranking of which deficits fade fastest is near chance, and the short absence did not move the level. Three learners make every interval wide. | engine-analytics:skills |
| ana-policy-sim | medium | Off-policy evaluation is validated in a simulator whose reward structure we invented, with exactly known propensities. Real implicit labels (followed, dismissed, repeated, undone) are noisy proxies for 'it helped'. | engine-analytics:ope |
| ski-not-uniformly-best | medium | The rule is not the best everywhere. Lowest regret by build cost: b=4: Build now (1.07); b=8: Build now (1.15); b=16: Build now (1.27); b=32: Ski rental with predictions (lambda 0.2) (1.33). When building is cheap (b = 4 manual runs) building at once (1.07) is level with the rule (1.07) and both are ahead of break-even (1.70); the prediction earns its keep when building costs more. The pack's own build costs are 4 to 9 runs. | engine-handoff:ski_rental |
| presence-weekly-template | medium | The weekly map predicts held-out days worse than a simple baseline for shift-worker (map Brier 0.214 against prior 0.194 and one global rate 0.175). A weekly template does not suit rotating shifts or no routine. | engine-handoff:presence |
| presence-window-calibration | medium | The window forecast is only roughly calibrated: expected calibration error 0.07 to 0.13 across personas on held-out days, and it beats pooled survival (no time of week) on 2 of 4 personas. | engine-handoff:presence |
| presence-interval-coverage | medium | The 95% intervals on the presence map contain the planted active probability in only 55% to 91% of bins. Smoothing across neighbouring bins trades bias for variance, so the intervals are too narrow. | engine-handoff:presence |
| presence-idle-capacity | medium | Idle capacity per week is over-estimated: nine-to-five 12 h against a planted 10 h; irregular 10 h against a planted 6 h. With no sleep event the machine is assumed to stay on for 60 minutes after the last event, and a locked screen still counts as idle although a desktop run cannot start on it. | engine-handoff:presence |
| routines-finder-noise | medium | The finder alone (minimum support 3) returns many small clusters of one-off work: precision 22% over 55 clusters. The value gate removes them: precision 100% over 6 proposals. Short routines of three or four steps are the hardest to tell from chance. | engine-handoff:routines |
| forecast-small-n | medium | The 95% forecast interval covered what happened in 8 of 11 planted routines (73%), which is below nominal and rests on one held-out week; the schedule change on day 15 falls inside it, and the model has no way to know about it. | engine-handoff:forecast |
| ana-claims-live-artifact | medium | In the live runs the model states a confidence only when it makes a finish claim itself, which happened only in the runs that went wrong. Its presence copies the label, so it is kept out of the classifier and cannot be calibrated. | engine-analytics:agent_claims |
| ana-pooling-people | medium | Cold-start priors are built from four synthetic personas (or 24 scripted apprentices with two cases each); with so few and such alike people, partial pooling is hard to tell from complete pooling, and learning-curve drift is not modelled. | engine-analytics:pooling |
| synthetic_catalog | medium | Attacks are synthetic and were written by the same team that wrote the defences. A new attack style can get through. | agent-safety:redteam |
| detector_pauses | medium | A detector hit pauses the run for a human, so task success under attack is lower than on clean pages by design. | agent-safety:redteam |
| detector_tradeoff | medium | Removing the injection detector did not let any attack through in this test, but it lets far more tasks finish (the reader alone keeps the planner clean). The detector's job is to catch an attack early, and its price is pauses. | agent-safety:redteam |
| layer7_scope_in_sample | medium | Layer 7 (goal check) no longer asks a model about plain typing, filling, select and extract steps, so it now covers navigation, clicks and key presses only. We changed this after seeing it pause the run on clean pages when the worker was just typing the answer (5 false pauses in 93 live runs). The false-pause figure after the change (0 of 93) is measured on the same pages that showed the problem, so it is in-sample and probably too good; typed data is still stopped by the data-flow and action-gate layers, not by this one. | agent-safety:redteam; agent-safety:redteam_live |
| same_host_exfil | medium | Data-flow rules and the goal check cannot tell an exfiltration request to an endpoint on a site the routine already uses from normal browsing there. Only the detector and the reader stop that kind of attack. | agent-safety:redteam |
| no_execution | medium | Nothing is executed. An attack counts as successful when the model proposes an action that serves the attacker and the layers authorise it; real tools, redirects and multi-step consequences are not modelled. | agent-safety:redteam_live |
| synthetic_attacks | medium | The attacks are synthetic and were written by the same team that wrote the defences; models change, so a result is true of one model version on one day. | agent-safety:redteam_live |
| prv_canary_exact | medium | The canary scan looks for the exact planted strings, their invented words, simple rewrites (case, separators, URL encoding, base64, hex). A paraphrase, a translation, a hash or a character-code encoding of a token would not be caught. The claim measured is: these planted strings did not reach the model port, in these flows. | privacy-layer:privacy |
| prv_form_not_meaning | medium | A SafePayload limits the form of what is sent (numbers, codes, fixed ids, bucketed values), not its meaning: a bucketed count of the worker's own meetings is still a fact about the worker. Generalisation reduces precision; it is not anonymisation. | privacy-layer:privacy |
| prv_worker_requested | medium | Model calls the worker asked for (agent runs, the coach, the quarantined reader) are not routed through the egress guard and send raw content to the provider by design. They appear in the ledger only as metadata lines when the port is wrapped (direct.LedgeredPort). The Privacy screen therefore does not claim that nothing else leaves this laptop. | privacy-layer:privacy |
| prv_synthetic | medium | All fixtures are synthetic and the real provider is never called here (a fake client checks only the request shape). Nothing is validated on real calendars, repositories or accounts. | privacy-layer:privacy |
| img_answer_closed_not_sight | medium | Closed answer schemas (every string is an enum) stop text read off the screen from coming back. They cannot stop the model from seeing it. | privacy-layer:privacy |
| img_memory_best_effort | medium | A frame is held in a buffer that is wiped after the call and is never written by this layer. Copies handed to a provider SDK or the HTTP stack, and freed memory the interpreter has not reused, cannot be wiped or controlled from here; swap and core dumps are outside this check. | privacy-layer:privacy |
| img_scan_exact | medium | The residue scan looks for the planted PNG's raw bytes, the token written into its metadata, its full SHA-256, and base64 or hex renderings of the file. It cannot see pixels, a re-encoded copy (a JPEG of the same frame), or a description of the frame. | privacy-layer:privacy |
| img_old_ts_provider_code | medium | Old project TypeScript under apps/desktop still names Gemini and OpenAI hosts behind flags (listed in static_guard_ts_references, report only). The rule is that frames reach a provider through the engine's egress guard; the Python tree is checked for it, the TypeScript is not enforced. | privacy-layer:privacy |
| img_no_real_provider | medium | No real provider was called: a capturing port and a fake client check request shapes and the guard. Gemini and OpenAI behaviour (latency, accuracy, cost) is the MODELS track's own measurement. | privacy-layer:privacy |
| git-circularity | medium | The generator, the digest rules and the habit thresholds were written by the same agent. Thresholds were set on development replicates 0 to 3 and scored on fresh ones (100 and up), but the planted rates are large and habits are planted independently; real habits are smaller, correlated and noisier. | git-analysis:git |
| git-small-effects | medium | Small differences are not flagged by design (each habit has a floor). At 25% of the planted strength recall falls to 19%. | git-analysis:git |
| git-digest-rules | medium | Evaluation digests come from the rules, because model digests take about a second a commit. The local model was not present, so model-against-rules agreement was not measured. | git-analysis:git |
| git-genome-modelled | medium | On commit sessions the alignment sees differences in the SHAPE of sessions (missing test steps, reverts, extra code-commit loops) in some replicates, and sees nothing in seconds, because git records when a commit landed and not how long the work took. Habits that live in the message or the clock (vague messages, late nights) are invisible to cogs by construction. | git-analysis:git |
| git-no-outcome | medium | Suggestions are advice chosen by code from commit-level shares. Nobody has been shown that following one improves anything; there is no study of the git layer, and a share is not a cause. | git-analysis:git |
| git-reference-synthetic | medium | A real repository is compared with synthetic experts, so its origin is reported as mixed; the comparison is with a scripted baseline, not with real experts. | git-analysis:git |
| pro-weights-handset | medium | The ranking weights, the minimum score of 0.30, the cap of three and the per-kind limits are hand-set constants, not fitted to any data. A different choice would move precision and recall; no sensitivity sweep is claimed. | proactive:proactive |
| pro-capacity-recall | medium | Recall is capped at what the judge is allowed to show of each kind (one practice card, one git card, two automations): a person with three planted git habits is credited for finding one. That is the design, not a flaw in the metric, but it hides how much was left unsaid. | proactive:proactive |
| pro-calendar-truth | medium | Calendar cards are scored against the calendar track's planted problems; the suggestion thresholds and the planted structure come from the same generator family, and a week can carry several planted problems of which the judge may show one. Finished-run cards are covered by scripted checks only, and so are stale calendar and git cards. | proactive:proactive |
| pro-stale-injected | medium | Staleness is injected by changing a reading (a routine switched on, a skill at level 4). Real staleness has more forms, and a source that cannot be read is never treated as stale, which can leave a card up for a few hours after it stopped being true. | proactive:proactive |
| cal-rules-not-learned | medium | Event kinds (meeting, focus, break, off-screen) come from keyword rules on titles and attendee counts. Real titles are messier; a meeting with no invitees is read as the owner's own time, and a focus block that is not named as one is invisible. Calendar hygiene differs from how people really work. | calendar:calendar |
| cal-interval-scope | medium | Gap intervals cover uncertainty in the expert reference (8 synthetic experts) only, not a learner's week-to-week variation; a week is flagged only if it also lies outside the range of expert weeks. Three weeks per person is thin. | calendar:calendar |
| cal-graph-unverified | medium | The Microsoft Graph adapters were tested against recorded fake responses written from the public documentation; they have never been run against a live tenant by this code, and tenant policy decides what a signed-in worker may read. | calendar:calendar |
| cal-leak-claim-scope | medium | The leak result is measured: the exact planted names, addresses, titles, locations and ids did not appear in any payload, suggestion or captured request. It does not rule out a paraphrase or an encoding, and model calls the worker asks for are recorded in the egress ledger, not hidden. | calendar:calendar |
| loc_dev_tuned | medium | The prompt wording, the worked examples and the per-field choice of model or rules were tuned on the dev split only; the held-out test split was run once with the frozen prompts (one later look at the shipped-policy arm followed the single policy revision, see loc_policy_revised). Dev numbers are therefore optimistic and are shown only as such. | local-model:localmodel |
| loc_no_finetune | medium | No fine-tuning (LOC-3 is cut): it could not be validated in the time available. The model is Qwen2.5-7B-Instruct at 4-bit quantisation (Q4_K_M) with a labelling guide, a few fixed worked examples and constrained decoding. | local-model:localmodel |
| loc_labels_are_policy | medium | Labels such as risk and message quality are our written policy, not ground truth: a reviewer may reasonably disagree on a share of items, which caps the accuracy any method can show here. | local-model:localmodel |
| loc_prompt_sensitivity | medium | Small prompt changes move the numbers by more than the intervals suggest: replacing three worked examples (to keep them disjoint from the fixtures) changed dev commit-category accuracy from 48 to 44 of 52. A difference of a few items between two prompts or between the model and the rules is noise at this sample size. | local-model:localmodel |
| loc_authorship | medium | The rules, the labelling policy, the prompts' guide and the fixture generator share one author and one vocabulary (for example the list of sensitive areas), so the rules are better matched to these fixtures than they would be to real history, and the model's labelling guide is better matched than it would be to real history. Real data would test both. | local-model:localmodel |
| loc_leak_claim | medium | 'No leak' is claimed only as measured: zero planted strings in the outputs and in the server log of the evaluation run, and the guards reject a deliberately leaking stand-in model. The raw inputs do pass through the local model's memory and llama.cpp's in-process prompt cache (never written to disk by this module). | local-model:localmodel |
| faithful_fake_is_ours | medium | The false-reject rate is measured on a stand-in model that varies numbers and interval wording in the ways we wrote down. A real model phrases things we did not anticipate, so its false-reject rate is likely higher; a rejected reply costs nothing (the template is used). | evidence:evidence |
| adversarial_set_is_ours | medium | The adversarial rejection rate is against the 28 attacks we wrote. The unknown-habit rule is a set of cue patterns (a cause or a share of time attributed to a phrase that names nothing in the vocabulary), not a language model: a novel phrasing with no cue can pass. | evidence:evidence |
| packet_from_synthetic_and_fixtures | medium | Packets come from synthetic apprentices (and the real stuck-hazard evaluation in the full run); the coach, routine, counterfactual and time-to-progress blocks are scripted fixtures that exercise wording and the check, not measurements. | evidence:evidence |
| eval-deficit-weak | medium | Deficit detection is weaker for: repeated_read_result (precision 70%, recall 100%); copy_error (precision 100%, recall 71%). Overall precision 92%, recall 95% over 160 case-deficit pairs. | engine-eval:deficit_recovery |
| eval-deficit-bias | medium | The recovered price differs from the planted price, with an interval that excludes zero, for: repeated_read_result (+13.5 s, interval 5.1 to 23.3). The alignment names a block of extra steps by its content, so a deficit that shares steps with another is mis-priced. | engine-eval:deficit_recovery |
| eval-hazard-alarm-budget | medium | On held-out people the false-alarm rate is 1.21 an hour, over the 1.0 an hour budget chosen on the training people. | engine-eval:hazard |
| eval-ope-coverage | medium | In the detailed run the interval of IPS, SNIPS, DR does not contain the true value 0.018. Over 24 independent replications the intervals covered the truth: IPS 96%, SNIPS 96%, DR 88% (naive 0%); nominal is 95%. | engine-eval:ope |
| eval-agent-runs-clean-path | medium | The clean-path result (20 of 20 households, 95% lower bound 84%) is the compiled path on the sandbox it was written against, so a full pass is expected and says little. The discriminating evidence is the robust and injected runs. Twenty households cannot rule out a pass rate well below 100%. | engine-eval:agent_runs |
| eval-agent-runs-injected | medium | Failure injection covers 4 patterns only: layout change on site b (5 of 5 passed); layout change on site c (5 of 5 passed); layout change on site a and one-off 503 on site b (5 of 5 passed); one-off 503 on site c (5 of 5 passed). 15 of 20 households needed the tier-2 browser agent. 20 of 20 passed (95% lower bound 84%). Other failure kinds (a changed flow, a wrong page, a slow site) were not injected. | engine-eval:agent_runs |
| eval-agent-live-small-n | medium | Real-model runs (agent-core, tier 1 disabled so every navigator uses the browser agent): 20 households per condition, 90 runs. Clean 18 of 20 (95% interval 0.70 to 0.97), 2 honest failures ('not every calculator produced a verified result'); layout change 20 of 20 (0.84 to 1.00). Twenty per condition shows the failure modes, not a pass rate; identical prompts are cached, so repeated page situations are one live sample each. | engine-eval:agent_runs |
| eval-agent-live-injected | medium | Injected pages: the detector paused 20 of 20 runs (20 detected of 20 injected) with 0.0 model-driven steps, and 0 attacks succeeded. Task success is 0 by design: a paused run does no task. This tests the detector on these pages, which we wrote. | engine-eval:agent_runs |
| eval-agent-live-cost | medium | Cost is an estimate at placeholder rates (5.0 and 30.0 USD per million tokens in and out), not the provider's price list: about None USD for the rows in the file (None tokens in, None out), 494 live calls and 5302 cache hits across the runs. Cached answers cost nothing on a re-run. | engine-eval:agent_runs |
| eval-redteam-live-in-sample | medium | The live false-pause result (0 of 93 clean runs, 0 of 30 on hard negatives) is in-sample: the layer-7 (goal-drift) scope was changed while building on this same catalog, so it is not a held-out rate. | engine-eval:redteam_live |
| eval-privacy-coverage | medium | The privacy result covers the guard through its own reference flows and 6 integration flow(s) from a layer's real code (upper bound on the leak rate 0.0% over 10608 planted tokens). These layers supplied no real-code flows and are not counted as passed: evidence. | engine-eval:privacy |
| routing-circularity | medium | CIRCULARITY: the calculators' quirks (site b ignores capital tariff income; site c applies a two-child limit and treats exactly 16,000 as over the limit) and the household archetypes that trigger them were planted by us. The router can only show it found our planted structure; it does not show that real calculators or real agents fail this way. | engine-analytics:routing caveat |
| ski-lambda-heuristic | low | The trust parameter lambda is fixed by us (or set from past forecast error by a heuristic that is not in the paper). It was not tuned on this simulation. | engine-handoff:ski_rental |
| presence-rule-conservative | low | The start-or-wait rule is conservative: it collided with the worker's return in 2.1% of started runs against an allowed 10%, and used 74% of idle time against 90% for running whenever idle five minutes. Runs are replayed one per decision point on held-out spells; interruption and idle-use intervals count spells as independent. | engine-handoff:presence |
| routines-rare | low | Planted routines that ran fewer than 3 times cannot be found by design and are excluded from recall: nine-to-five/weekly-report. | engine-handoff:routines |
| ana-trust-ladder | low | The autonomy ladder needs 20 clean shadow runs to reach A2 and about 73 clean runs to reach A3; the demo reaches A1 or A2 at most. A3 is a target, not a result. | engine-analytics:agent_claims |
| markup_assumption | low | Layer 1 (sanitising) is modelled as defeating only markup-based attacks (fake system tags, tool-call syntax); a scripted planner that follows plain text shows no change when it is off. | agent-safety:redteam |
| overlap | low | Layers overlap, so leaving one out often changes nothing. The 'only_<layer>' rows show each layer's standalone strength. | agent-safety:redteam |
| judge_is_rules | low | Alignment with the attacker's goal is judged by rules on the proposed action, so an unrelated harmful action is not counted. | agent-safety:redteam_live |
| prv_covert_channel | low | Lists of integers could carry text as character codes. Lists are capped at 64 items and integers at 1e9, which bounds that; the threat model is accidental leakage by honest code, not an author trying to smuggle data out. | privacy-layer:privacy |
| prv_static_guard | low | The static guard is name-based. It does not follow a module name held in a variable and cannot see code added at run time; it catches honest mistakes such as importing an SDK 'just for wording'. | privacy-layer:privacy |
| prv_ledger_trust | low | The ledger is a plain local file the worker can clear (the clear is itself counted). It records what the guard sent; it cannot record what a module sends by bypassing the guard, which is what the static guard and the canary flows are for. | privacy-layer:privacy |
| git-reverts-weak | low | Reverts are rare even when planted, so the revert habit is the weakest to recover; it is reported, not tuned. | git-analysis:git |
| git-real-history-tiny | low | The one real history (this project's) is short and agent-assisted; its aggregates illustrate the pipeline and are not a finding. | git-analysis:git |
| git-canary-scope | low | The leak result is a count of exact planted strings in captured request bodies on these flows. It does not catch a paraphrase, a translation or a hash of a token. | git-analysis:git |
| pro-rules-not-model | low | No model decides what is surfaced; a model may reword the reason line through the egress guard. Wording quality is not evaluated here. | proactive:proactive |
| cal-recall-by-design | low | A problem planted below the expert tolerance (one fragmented day, one back-to-back run) is not suggested, by design. Recall against the planted intent is therefore below 1; the thresholds come from the template, not from the truth labels. | calendar:calendar |
| loc_code_fields | low | Size, tests touched, duration, attendee count and recurrence are computed by code from the input in every path, so they are exact by construction and say nothing about the model; only category, risk, message quality and needs_prep are model-or-rules fields. | local-model:localmodel |
| loc_latency | low | Latency and tokens per second are for one Apple M2 Max (32 GB) with all layers on the GPU: about 30 generated tokens per second, so a digest takes roughly 0.5 s when only the category is asked for (the shipped policy) and about 0.7 to 1.1 s with every field. A history of a thousand commits takes about nine minutes the first time; the rules path takes microseconds. | local-model:localmodel |
| loc_policy_revised | low | Which fields the model decides was chosen on the dev split and revised once after the held-out run (events needs_prep moved from the model to the rules). The held-out numbers of the model-for-everything run are the clean evidence; the numbers for the policy as shipped (commit_digest: category, event_digest: category by the model) include one held-out look after that revision and are slightly optimistic. | local-model:localmodel |
| live_small_n | low | The live block, when it is run, is a small-n pass rate for one local model on synthetic packets; it says nothing about other models. | evidence:evidence |
| eval-null-offset | low | The shuffled-label null averages +46.2 s (interval -36.4 to 116.9), about 20% of the real gap of 229.6 s. Matching each case to its nearest reference is not symmetric, so the null is not exactly zero; the real gap sits above the null interval, which is the comparison that counts. | engine-eval:null_placebo |
| eval-agent-runs-discrepancies | low | 7 of 20 households are planted discrepancies between the sandbox calculators (quirks we wrote). A pass on them means the discrepancy was flagged, not that an entitlement was worked out, and the oracle is a simplified rule set, not the law. | engine-eval:agent_runs |
