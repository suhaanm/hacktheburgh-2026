# PLAN (follow-up): conformal prediction intervals and sets, pre-registration

Written by the HRT-STRENGTHEN track on Sun 8 Nov 2026, about 02:00 GMT, **before any number of this plan has been computed on any pool**. The commit that adds this file
comes before the first run, on dev or held-out seeds. After the commit this file changes only by dated entries in the amendment log at the bottom. Model ID of the author:
claude-sonnet-5-5. Everything is from generators we wrote; no model call is made.

## 1. Why this follow-up exists, and what it is not

A quantitative judge asks for the uncertainty of a forecast, not only for its score. The ledger part (`PLAN.md`) scores probabilities. This plan asks a different
question: **if the product shows a range ("done in 8 to 40 minutes") or a set ("progress or stuck"), does the range cover the truth as often as it says, on people the
range was not fitted on, and what happens when the world changes?** The method is split-conformal prediction (a held-back calibration set turns any predictor into a
range with a finite-sample coverage guarantee **if calibration and test cases are exchangeable**). The interesting part is the second half: exchangeability is exactly what
a change of regime breaks, so the plan registers that the coverage fails under shift and that the guard of `PLAN.md` section 6 sees the same shift.

It does not reopen any claim of `PLAN.md` or `PLAN_RECAL.md`. It is **not** designed after a held-out result of its own: no conformal number exists anywhere yet. It is
designed after the lead's request of 8 Nov about 01:45 GMT for coverage checks on held-out people in the v1 world and the three shifted worlds against a nominal 90%.

## 2. Targets, predictors and the conformal rules (all fixed here)

Nominal level **90%** (alpha = 0.10). The conformal quantile of n calibration scores is the order statistic number ceil((n + 1)(1 - alpha)) of the sorted scores (the
whole range if that exceeds n). The models are the deployed models of `PLAN.md`, **fitted once on its TRAIN pool and frozen**; the conformal quantile is the only thing
computed from calibration data, and nothing is fitted after deployment.

| Target | What is predicted | Predictor (frozen) | Conformal rule |
|---|---|---|---|
| **T0 stuck set** | the label of `PLAN.md` (no progress in the next 60 s): a set of labels from {0, 1} | the deployed `full` hazard model, probability p of label 1 | score = 1 - p(true label); the set contains label y when 1 - p(y) is at most the calibrated quantile |
| **T1 time to next progress** | the 30-second step (1 to 10) in which the next progress event falls, or 11 for "not within five minutes" | the deployed time-to-progress head (`mlv2/tte.py`), CDF F over ten steps | conformalised quantile regression on step quantiles: q_lo = first step with F >= alpha/2, q_hi = first step with F >= 1 - alpha/2 (11 if never); score = max(q_lo - y, y - q_hi); range [q_lo - Q, q_hi + Q] |
| **T2 time to finish** | seconds from the origin to the end of the episode (the task's end in the generator), at least 60 | a ridge regression (strength 1.0 on the standardised columns, fixed here, not tuned) of log seconds remaining on seven causal columns: log(1 + seconds since the episode began), log(1 + progress events so far), and the five dense hazard columns (`log_dwell`, `repeat_run`, `reformulations`, `log_tsp`, `tsp_lin`) | score = absolute residual in log seconds; range [exp(yhat - Q), exp(yhat + Q)] |

Origins: every 30-second bin of `build_bins`. **T1 uses only the origins with all ten steps observable** (the episode lasts at least 300 s after the origin), because the
outcome is then known exactly; the others are censored and are excluded from calibration and scoring alike. The share excluded is printed. This restricts the claim to
"origins at least five minutes before the end of an episode" (a property the product cannot observe at forecast time); that is a limitation, stated again in section 8.
T0 and T2 use every origin.

**Dumbest competent baselines, calibrated the same way on the same pool**: T0 the base-rate model (p = TRAIN base rate for every origin); T1 the Kaplan-Meier
constant CDF of the head's baseline (`mlv2.tte.KMConstant`); T2 the constant median of log seconds remaining over TRAIN. A baseline has the same coverage guarantee
under exchangeability, so the question is only which one is **narrower** at the same coverage.

## 3. Pools (new seeds; none used by any earlier evaluation, by `PLAN.md` or by `PLAN_RECAL.md`)

| Pool | What | k |
|---|---|---|
| **TRAIN** | as `PLAN.md` (the deployed models are fitted here, once) | 1 to 4 |
| **CAL-v1** | v1 deployments (four persona streams each): the calibration set at deployment | 31 to 34 |
| **CAL-shift** | one deployment of each v2 family (20 people x 14 days): used only by the "recalibrated" arm (claim K5) | 51 |
| **HELD** | v1 deployments (8, four streams each); v2 deployments of each family (8, 20 people x 14 days each) | 41 to 48 |
| **DEV** | v1 and v2 deployments (2 each), CAL-shift deployment | 35, 36; 52 |

Seeds are `worlds.v1_seed(type, k)` and `worlds.v2_seed(family, k)`. A test asserts every seed here is disjoint from every seed of `PLAN.md`, `PLAN_RECAL.md` and the
earlier evaluations'. People in CAL, HELD and TRAIN are different people (new seeds draw new people; a v1 stream is one person of one of four persona types).

## 4. What is computed (the same for every world)

* **Standard arm**: the conformal quantile of each target from the CAL-v1 pool, applied unchanged to the held-out origins of the v1 world and of each shifted world (the
  deployment-time calibration meeting a world that has changed).
* **Recalibrated arm** (shifted worlds only): the conformal quantile re-computed on the CAL-shift deployment of the same family (one deployment of the new world that has
  resolved) and applied to that world's held-out deployments. The model itself stays frozen.
* **Coverage**: the share of held-out origins whose truth lies in its range or set, pooled over a world's deployments, with a 95% interval from a bootstrap that resamples
  **people** (B = 2000, seed 0); per-deployment coverage is also stored. **Width**: T0 the share of singleton sets, of two-label sets and of empty sets; T1 the mean
  length in steps with a paired (same resamples) interval for the model minus the baseline; T2 the calibrated half-width Q for the model and the baseline (the range is
  constant in log space, so there is nothing to resample) and the factor exp(2Q) by which the upper end exceeds the lower.
* **The guard**: for T0 only, each held-out deployment's stuck forecasts are replayed through the ledger exactly as in `PLAN.md` section 3 and the guard of section 6
  (lambda 0.8, threshold 20, fallback the online base rate) is run on the same deployment; a 2 x 2 table of "T0 coverage below 0.85" against "guard flagged" is stored
  per world.

## 5. Claims, decided before any number exists

| ID | Claim | Pass rule |
|---|---|---|
| **K1a, K1b, K1c** | Validity where calibrated: in the **v1 world** the standard arm's coverage of T0 (K1a), T1 (K1b) and T2 (K1c) is consistent with the nominal 90% | the 95% interval of coverage contains 0.90 (each target is a separate claim) |
| **K2a, K2b, K2c** | The guarantee fails under shift: the standard arm **under-covers** in the shifted worlds, for T0 (K2a), T1 (K2b), T2 (K2c) | the upper end of the 95% coverage interval is below 0.90 in at least 2 of the 3 shifted worlds |
| **K3** | The models earn their width: in the v1 world, at the same nominal level, T1's range is shorter than the Kaplan-Meier baseline's and T2's calibrated half-width Q is smaller than the constant baseline's | T1: the upper end of the paired interval of (model minus baseline) mean length is below 0; T2: Q(model) < Q(baseline) (a comparison of two calibration quantiles, with no interval) |
| **K4** | The guard sees what the coverage loses: every held-out deployment, in any shifted world, whose T0 coverage is below **0.85** (nominal less five points) is one in which the guard raised a flag, and the guard flags at most 1 of the 8 v1 deployments | all of the low-coverage shifted deployments are flagged **and** v1 flags <= 1 of 8. If fewer than 3 shifted deployments fall below 0.85 the claim is reported as **not testable** (neither passed nor failed) |
| **K5a, K5b, K5c** | The range can be rescued by recalibrating the quantile on one deployment of the new world, without touching the model: for T0 (K5a), T1 (K5b), T2 (K5c) | the 95% coverage interval of the recalibrated arm contains 0.90 in at least 2 of the 3 shifted worlds |

Reported and **not** claims (no pass rule): per-deployment coverage; T0 set composition; the recalibrated arm's width against the standard arm's; coverage at 0.85 and 0.95
nominal (not computed); the share of T1 origins excluded.

A claim that fails is a finding and is printed. A claim that cannot be tested under its own rule is printed as not testable.

## 6. Multiplicity

This part registers **11 claims** (K1a to c, K2a to c, K3, K4, K5a to c). With the 10 of `PLAN.md`, the 7 of `PLAN_RECAL.md` and the four decision contrasts of the
scoreboard, the HRT section has **32 registered claims or contrasts**. Most of the claims here are "the interval contains the nominal level" or "at least 2 of 3" rules,
which are not hypothesis tests with p-values; the brief (`docs/HRT_BRIEF.md`) states the family size, and shows Holm-adjusted p-values beside the raw ones for the
directional paired contrasts only, **derived after the fact from the reported intervals and flagged as such**. No claim of this plan is adjusted by choice of a comparator.

## 7. Discipline

`python -m understudy_engine.hrt.run_conformal dev | freeze | heldout`; the held-out command refuses without `UNDERSTUDY_HRT_HELDOUT=1`, without a freeze of part `conformal`
(code and plan hashes), after a change, or on a second run (`evals/hrt/heldout_log.jsonl`). Dev is for debugging only and is never reported as evidence. Pure functions
(quantile, sets, intervals, causal feature builder) have tests that run before any dev run.

## 8. What this cannot show

All of `PLAN.md` section 9 applies. In addition:

* The conformal guarantee needs calibration and test cases to be exchangeable. **Origins from one episode, and episodes from one person, are not exchangeable**, so
  coverage can fall short of 90% even in the world the quantile was calibrated for; K1 tests that, with people as the resampling unit.
* Coverage is marginal over origins, not conditional on a person or a situation: a worker who differs from the pool can be badly covered while the pool-wide figure is
  at 90%.
* T1 is scored on the origins with five minutes of episode ahead; T2's target is the end of the episode as the generator defines it. Both are our definitions.
* Split-conformal, not CV+ (CV+ needs a refit per calibration fold; not done for lack of time, not because it is worse). One calibration split per world.
* The recalibrated arm is calibrated on a deployment of the very generator it is then scored on. A world that keeps changing is not what one quantile repairs.
* Discrete targets (T0, T1) make split-conformal coverage conservative (it can exceed the nominal level); the interval of a coverage figure that exceeds 0.90 does not
  count against K1 but is reported.
* Nothing here is about real workers; the live study (n = 4) has not run.

## Amendment log

**A1, Sun 8 Nov 2026 about 02:15 GMT, after one dev run (DEV seeds k = 35, 36 and 52, never reported as evidence; its output is kept as `evals/hrt/results/dev_conformal_first.json`),
before the freeze and before any run on the held-out seeds.** The dev run showed four things about the plan as registered. Nothing below changes a pass rule except where it says so.

1. **T1's horizon was badly chosen.** With a five-minute horizon only 1.8% of the calibration origins (589 of 31,941) and 1.8% of the v1 dev origins (267 of 14,542) have all
   ten steps observable, because the v1 episodes are short; the v2 worlds keep 17% to 37%. A v1 result on 267 origins and eight people says almost nothing. The calibration
   pool alone (not any coverage number) gives the share of origins with at least k observable steps in v1: 100% for k = 2, 41% for k = 4, 15% for k = 6. **T1 is changed to
   a two-minute horizon, four steps (supersedes the T1 row of section 2):** the range is over steps 1 to 4 plus 5 for "not within two minutes", the head's CDF is cut at step 4,
   q_lo and q_hi are the first of steps 1 to 4 whose CDF reaches alpha/2 and 1 - alpha/2 (5 if none), the Kaplan-Meier baseline is cut the same way, and an origin counts when
   all four steps are observable. The choice rule, fixed here before any coverage number of the new design exists: **the longest horizon in whole minutes observable for at
   least 25% of the calibration origins** (one minute 100%, two minutes 41%, three minutes 15%). Everything else about T1 is as registered.
2. **The plan contradicted itself about over-coverage.** Section 5 says K1 and K5 pass when the coverage interval "contains 0.90"; the last paragraph of section 8 said an
   interval above 0.90 "does not count against K1". Dev showed it matters: after recalibrating, the finish-time range covered 99.6% in one world (K5c), because the range was
   about 750 times wide from end to end. **The table governs and the sentence in section 8 is withdrawn**: K1 and K5 pass only when the interval contains 0.90, so a range that
   over-covers fails the rule, and the brief prints for every coverage figure whether it is under (upper end below 0.90), consistent, or over (lower end above 0.90).
3. **Coverage can be restored by making the answer useless, and the plan only asked about coverage.** On dev, the recalibrated arm's finish-time range was 43 to 750 times
   wide from end to end and its stuck sets held both labels in 74% to 97% of origins. Width is already "reported, not a claim"; this amendment makes it **part of every table
   the brief and the page print beside the coverage figure** (set sizes for T0, mean length for T1, the end-to-end factor for T2), and adds one reported arm, **recentred
   (T2 only)**: shift the model's log prediction by the median log residual on the calibration pool, then take the conformal quantile of the absolute residual about the shifted
   prediction (the same data, one more parameter, no claim attached). It is there to say whether the width is a bias that one number removes or a spread that nothing removes.
4. **For reading only, what dev said about the claims**, so that nobody thinks they were chosen to pass: K1a to c held, K2a to c held, K3 held (the finish-time model's Q was
   only 0.006 smaller than the constant baseline's), K4 held (6 of 6 low-coverage deployments flagged), K5a held, **K5b and K5c did not**. K5b and K5c stay as registered.
