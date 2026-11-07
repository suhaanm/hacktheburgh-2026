# Cue and independence score: pre-registered evaluation plan

Written Sat 7 Nov 2026 by the CUE-ENGINE track, before any held-out replicate was run. Everything here is SIMULATED or SYNTHETIC: simulated workers and simulated learners, expert paths from generators. Nothing in this plan, and no result from it, says that Cue works on people. The live study (n = 4) is the only evidence about people.

What was already looked at when this was written (so nobody has to trust memory): the candidate evaluation (no tuning exists in it), and on the score's DEV replicates only the two mastery replays `engine_default` and `evidence_only` and the first trend design (see "Score validation"). No Cue-simulation result of any kind had been produced.

## 0. Seeds and splits

| Thing | Dev | Held-out |
|---|---|---|
| Score validation, simulated learners | replicate seeds 0 to 59 per kind | 10 000 to 10 059 per kind |
| Cue simulation, workers | population seed 11, 40 workers | population seed 77, 40 different workers |
| Cue simulation, session randomness | replicate seeds 0 to 4 | 1000 to 1004 |
| Candidates | no tuning exists; leave-one-person-out over experts | the same (nothing held back) |

Thresholds and choices are made on DEV only. The held-out run happens once, after the lead has committed this file, and its numbers are reported whatever they are. A change after a held-out look is reported as a post-hoc change.

## 1. Candidates (CUE-1)

Model fixed before any run: an n-gram of order 3 with Dirichlet backoff (beta 2, alpha 0.1) over expert cogs, masked by the pack's order rules (`StepPolicy.track`, `next_ready`), interchangeable steps collapsed. Evaluated leave-one-person-out with a person-level cluster bootstrap (95%), on step boundaries (headline) and on all positions. Baselines: most common next cog overall, bigram only (no rules), n-gram without the rules; ablation: order 1 with rules. Families: A (8 apprentice experts), B (30 experts sampled from the pack rules), cross-family both ways, plus the programmer and data-analyst packs on family B. Metrics: top-1, top-3, Brier of the top-1 probability, ECE (10 bins), reliability table, negative log-likelihood, paired differences against bigram-only. Acceptance: top-1 above the best baseline with the paired interval excluding 0 on A and on B. The reading that must accompany the numbers: the pack order rules do most of the work, family A is 8 people with two orderings, family B follows the pack rules by construction.

## 2. Score validation (CUE-7, GRO-1 data)

Simulated learners (`cue/simlearn.py`, assumptions stated in the module): kinds improving, flat, forgetting (a 21-day absence), gamer (dismisses every cue); 3 skills x 40 occurrences; 60 learners per kind; planted latent mastery, truth known. Estimands, bias, interval coverage, false rise and gaming sensitivity as defined in `cue/evaluate_score.py`.

Trend: Theil-Sen slope of the assisted share over non-overlapping blocks of 10 occurrences, per 10 occurrences, with a bootstrap that resamples the occurrences inside each block; direction `less_help` / `more_help` only when the 95% interval excludes 0, otherwise `steady`, which is read "cannot tell yet". The block design was chosen on dev from five candidates (blocks of 5, 10, 15; sliding windows of 20 and 30) as the best power among those with a false-rise rate at or below 5% on flat learners, preferring the design that can start earliest (3 blocks = 30 occurrences). Power and the occurrences needed are stated in the payload (`trend.needed_more`, `trend.power_note`) from a dev simulation of a linear fall of 0.3 in the assisted share (0.5 to 0.2): the smallest number of occurrences with at least 80% power, 100 learners per size.

Mastery replay variants, declared before they were run (V0 and V1 had been seen on dev):

| Variant | Replay |
|---|---|
| V0 engine_default | `skills/tracing` defaults; assisted and abandoned give no evidence |
| V1 evidence_only | V0 without the learning step after a counted run |
| V2 conservative | learning gain 0.03 after a clean run, none after an error; memory stability starts at 3 days, grows by 1.2 per clean run, at most 30 days (stronger forgetting) |
| V3 assisted_as_failure | V2, and an assisted occurrence counts as an error observation (the learner could not do it unaided) |

Acceptance rule for the mastery term (dev only): a variant is adopted if, across the four learner kinds, (a) its mean absolute mastery bias is the lowest of the four, (b) the composite bias on FLAT learners is below 5 points, (c) the composite false-rise rate on flat learners (up 10 points or more between occurrence 30 and 120) is not above V0's, and (d) independence coverage is unchanged (it does not depend on mastery, so this is a check of the code). If no variant meets (a) to (c) the mastery term is left out of any headline and the payload says so. The composite stays in the payload as `composite_experimental` with its measured caveat whatever happens; no copy may call it an improvement measure.

Held-out check: the adopted variant (or V0 if none) is run once on seeds 10 000 to 10 059 and reported next to dev.

## 3. Cue simulation

### World model (my assumptions, not facts about people)

Workers: 40 per population, 10 around each v1 persona (nine-to-five, night-owl, shift-worker, irregular: their `speed` and initial skill `s0`), with person effects (speed lognormal sd 0.2; stuck propensity, pause propensity, acceptance propensity drawn per person). A `personas_v2` generator is used instead when it exists and exposes the same parameters; otherwise this file is the whole story.

Cases: the benefits pack. A case is a random linear extension of the pack's order (people differ in how often they batch the cliff checks), 8 to 10 steps. Per step: work time lognormal around the pack's expert median times the person's speed (sd 0.25); a thinking pause with a person-level probability (lognormal, median 25 s, sd 0.8: NOT stuck, a false-nudge opportunity); a stuck stall with probability `base x (1 - mastery)^1.2` at steps that carry a skill (the worker does not know the next step; duration lognormal, median 80 s, sd 0.7). Progress events are emitted at each step end. Mastery per skill rises with practice and help; the gate sees the REAL level engine and tracing model (`skills/tracker`), not the planted value.

Stuck signal: the headline run uses the coach's real rule fallback, `heuristic_p` of time since progress (`coach/signals.py`). An emulated model signal (a calibrated stuck probability with a stated AUC) is a secondary sweep and is labelled as an emulation.

Input rhythm: during work the worker types or clicks (quiet time under 2 s most ticks, so the flow rule holds Cue back); during pauses and stalls the cursor moves occasionally (stall more than pause).

Candidates come from the real `NextStepModel` fitted on experts sampled with a different seed from the workers' own paths. Grounding is a FAKE port that is right at a configurable rate (60% to 100% sweep): wrong means not found (half) or confidently another menu step (half).

Worker reactions (parameters in `cue/simulate.py`, all stated there): a correct cue to a stuck worker is followed with probability `accept x tier boost x (1 - 0.5 mastery)`, and then the stall ends a lognormal reaction time (median 6 s) later; a wrong cue adds 8 s of confusion; a question with the needed step among the options is answered within about 4 s (then the cue for it follows); a cue shown to a worker who is not stuck is a false nudge: it costs seconds of lost focus (ring 3, chip 5, ghost 8, ask 10, offer 3) and is dismissed with probability 0.85. Interruption seconds are added to the step.

### Design

The same random plan (durations, stalls, reaction draws) is run twice: with no Cue, and with Cue in the loop, so stall effects are PAIRED per episode. The gate is the real `cue/gate.decide`, polled every 2.5 s, with voice never allowed (visual by default). Intervals are percentile bootstraps over WORKERS (cluster = person), pooling that worker's replicates.

### Metrics (every one with n, split, a person-level interval, a baseline and the synthetic badge)

False nudges per hour (design target at most 1.0: a design choice, not a measured tolerance); share of stuck episodes where a correct cue (or a question with the right option) appeared; median seconds from the first cue to resuming, paired against the no-cue counterfactual remaining stall; acceptance and dismissal rates; silence precision (share of silent ticks that were genuinely not stuck, against the always-silent baseline, which equals the base rate) and the share of stuck seconds that stayed silent; questions per episode; cues per hour; net seconds saved per hour (stall seconds saved minus interruption seconds); wrong-target cues per hour; effect of grounding accuracy (60, 70, 80, 90, 100%).

### Tuning (dev only)

Grid: `p_signal` in {0.30, 0.40, 0.50, 0.60, 0.70} x `margin_thr` in {0.10, 0.20, 0.30}; 15 configurations x 5 dev replicates.

AMENDMENT before any tuning run (Sat 7 Nov, after the lead committed this file and after a smoke test at the default parameters, which showed that at `p_signal` 0.60 the coach's rule signal only crosses the threshold after about 83 s of no progress, so most stalls end first): the grid originally read `p_signal` in {0.55, 0.60, 0.70, 0.80} x `stall_min_l2` in {20, 35, 50} s x `margin_thr` in {0.10, 0.20} (24 configurations). It was changed to the grid above because (a) with the rule signal `stall_min_l2` is inert (the signal needs more than 58 s of stall to reach 0.30 anyway) and (b) no value of 0.55 or more could ever give early help. The smoke test also found and fixed a gate defect before any result was recorded: a typing burst did not reset the chain of consecutive stuck readings, so two micro-pauses 30 s apart in the middle of typing counted as consecutive; typing now resets the chain. No dev or held-out replicate had been tuned or scored when this amendment was written. The hard caps (3 shown per 10 minutes, one question per episode, 90 s between episodes of the same skill, escalation 25 s after the previous tier, offer after 90 s, daily budget 12) are design constants and are not tuned. Selection: among configurations whose dev false-nudge 97.5% upper bound is at most 1.0 per hour, take the highest net seconds saved per hour; if none qualifies, take the lowest false-nudge rate among those within 50% of the best net saving. Ties go to the lowest `p_signal`. The choice is written into `cue/params.py` as `TUNED` before the held-out run.

### Acceptance rules (held-out)

- Primary outcomes, a family of two: P1 false nudges per hour; P2 paired median (seconds to resume after the first cue, with Cue, minus the no-cue remaining stall). Decisions use two-sided 97.5% intervals (Bonferroni for two). P1 is MET if the upper bound is at most 1.0, POINT ONLY if the point estimate is at most 1.0 but the upper bound is above, NOT MET otherwise. P2 is MET if the upper bound is below 0.
- Secondary metrics are exploratory: 95% intervals, no claim attached.
- Invariants, zero violations allowed (checked on every tick of every run): at most 3 shown interventions in any 10 minutes (unrequested); at most one question per episode; at least 90 s between the first cues of two episodes of the same skill (unrequested); no cue at level 4 unless asked; no cue during a typing burst or with under 2 s of quiet; no whisper without `voice_ok`; chip at most 40 characters.
- Multiple comparisons: no p-values for exploratory metrics; the grounding sweep is a descriptive curve.

## 4. Tier bandit (CUE-9)

Epsilon-greedy (eps 0.2) over {none, ring, chip, ask, voice} among the actions the hard rules allow, context = (stuck-probability bucket, margin bucket, level, mastery bucket), reward from the implicit labels of `policy/labels.py` (followed within 10 s, dismissed within 4 s) minus the interruption costs, learning OFF by default. Offline evaluation on logs from the Cue simulation: IPS, SNIPS and doubly robust (`policy/ope.py`) for two target policies (the rule policy and the greedy tabular policy) against the true value of each, obtained by re-running the simulator with the same random plans. The report states the effective sample size and says whether any estimate is trustworthy enough to turn learning on; the default answer is no.

## 5. What cannot be tested here

Real people; real grounding accuracy (the 60 to 100% sweep is a what-if); the real hazard model as the stuck signal in the closed loop (an emulation is a secondary sweep); real interruption costs; whether a worker reads a ring or a chip the way the simulator says. Every Cue and score number is simulated until the live study says otherwise.

## 6. Dev outcomes, recorded before the held-out run (appended Sat 7 Nov by CUE-ENGINE)

Nothing below was tuned on held-out data; the held-out command (`python -m understudy_engine.cue.evaluate heldout`, which logs the code hashes and the hash of this file) had not been run when this section was written.

**Mastery replay (dev seeds 0 to 59, 60 learners per kind, all four variants run, every one reported).** Mean absolute bias of the mastery estimate against the planted latent mastery over the four learner kinds: V0 engine_default 0.374, V1 evidence_only 0.315, V2 conservative 0.241, V3 assisted_as_failure 0.105. Composite bias on FLAT learners (points): V0 +9.9, V1 +9.6, V2 +7.1, V3 -9.4. Flat-learner false rise (composite up 10 points or more between occurrence 30 and 120): V0 33%, V1 43%, V2 42%, V3 28%. Independence coverage identical in all four (93% / 93% / 98% / 77% by kind), as it must be. Adoption rule: V3 has the lowest mastery bias and a false-rise rate below V0's, but its flat composite bias is 9.4 points in absolute value (the composite's lower-bound independence term pulls it down about 6.5 points by design), which fails rule (b), so NO variant was adopted: V0 stays in the payload as the spec's replay, and mastery is left out of every headline. The composite is `composite_experimental`, with its measured caveat.

**Trend.** Blocks of 10 occurrences (Theil-Sen, per 10 occurrences, bootstrap inside blocks), minimum 30 occurrences. Dev power for a steady fall of the assisted share from 0.5 to 0.2 over N occurrences (100 learners per N) was 22% (N=30), 20% (45), 12% (60), 25% (90), 29% (120), 34% (180), 43% (240), 46% (360); false "change" on a flat share 0 to 4%. 80% power is not reached within 360 occurrences, so `trend.needed_more` is null and the payload carries a power note instead; "steady" reads "cannot tell yet". Sliding windows of 20 had lower power (about 8% on the planted learners at 120 occurrences) and an OLS slope test, used only as a reference, reached 40%; the Theil-Sen interval is conservative because block shares of 10 are heavily tied.

**Tuning (15 configurations, dev).** Selected `p_signal` 0.40 and `margin_thr` 0.10 (now `params.TUNED`). `margin_thr` made no difference to any dev number: the three rows for each `p_signal` were identical, because the question fires only on close calls and the prior is rarely close. `p_signal` 0.30 saved slightly more (25.8 against 23.9 seconds an hour) but its 97.5% upper bound on false nudges was 1.01 an hour, so it was excluded by the pre-registered rule.

**Dev results at the tuned parameters (40 workers, 5 replicates, about 100 hours per replicate-population).** False nudges 0.75 an hour [0.66, 0.85] (97.5% upper bound 0.87): the design target is met on dev. Share of stalls that got a correct cue: 27%. Of the stalls that got any cue 48% were shortened; the paired mean saving per cued stall was 36.9 seconds [29.0, 43.9] (exploratory), but the paired MEDIAN, the pre-registered primary outcome P2, was 0.0 seconds because fewer than half of the cued stalls were shortened (many cues arrive just before a stall ends anyway): P2 is NOT MET on dev. Net seconds saved per hour of work: 24 [16, 31], under one percent of the working time: with the coach's rule signal, help arrives late. Silence precision 0.934 against 0.933 for always staying silent. No invariant was violated in any run. Grounding sweep 60 to 100%: correct-cue share and net saving are flat (29% to 30%, 25 to 27 seconds an hour), wrong-target cues fall from 0.05 an hour to 0 (what-if only). Emulated model signal (d-prime 1.5): 43% of stalls get a correct cue and net saving is 42 seconds an hour at 0.82 false nudges an hour.

**Bandit (dev, offline).** The greedy table's doubly robust value was +0.27 above the rule's, but only 37 effective samples of 491 logged decisions back it (max weight 20), so the report says: do not turn learning on.

**Defect found and fixed during these checks (before any recorded dev result):** a typing burst did not reset the chain of consecutive stuck readings; it now does.
