# PLAN (follow-up): recalibrating the deployed model online, pre-registration

Written by the HRT-STRENGTHEN track on Sun 8 Nov 2026, about 01:25 GMT, **before any number of this plan has been computed on any pool**. The commit that adds this
file comes before the first run on the new seeds. After the commit this file changes only by dated entries in the amendment log at the bottom. Model ID of the author:
claude-sonnet-5-5. Everything is from generators we wrote.

## 1. Why this follow-up exists, and what it is not

`evals/hrt/PLAN.md` was run once on held-out seeds (`evals/hrt/results/heldout_ledger.json`, 8 of 10 registered claims passed). Two things it found motivate this
follow-up, so **this arm was designed after seeing that result**, and it says so:

* in the shifted worlds the deployed model is worse than a naive predictor and its calibration slope is negative; the guard's remedy is to throw the model away;
* in the error-risk world after a rule change the model stays better than the naive predictor but its calibration intercept moves from about -0.13 to about +1.03, and
  nothing recalibrates it (gap 7 of `docs/HRT_BRIEF.md`).

A quantitative judge's obvious next question is whether **recalibrating the model online, from the outcomes the ledger has already resolved,** rescues it, instead of
discarding it. This plan registers that question on **new seeds** (section 2), with its claims and pass rules fixed before any run. It does not reopen any claim of
`PLAN.md`, and nothing of the earlier held-out results is tuned toward it: the arm's parameters (section 3) are fixed here from first principles, not from those results.

## 2. Pools (new seeds; none used by any earlier evaluation or by `PLAN.md`)

Same generators and the same frozen deployed models as `PLAN.md` (fitted once on its TRAIN pool). A test asserts every seed here is disjoint from every seed `PLAN.md`
used and from the earlier evaluations'.

| Pool | What | k |
|---|---|---|
| **DEV** | v1 deployments (4 persona streams each), 2 deployments per v2 family, 2 error-risk deployments per world | 29, 30 |
| **HELD** | v1 deployments, v2 workweeks (3 families, 20 people x 14 days), error-risk streams of 4,000 cases, 8 deployments each | 21 to 28 |

Seeds are `worlds.v1_seed(type, k)`, `worlds.v2_seed(family, k)`, `worlds.route_seed(k)`. The error-risk drift world is `PLAN.md` section 5.4 (rule change at case 1,500,
review lag 50).

## 3. The arm (a decision rule; code, not a model)

A third predictor is written to the ledger beside the model and the naive baselines: **`recal`**, the deployed model's forecast passed through an online logistic
recalibration, `p' = sigmoid(a + b logit(p))`, where `(a, b)` is fitted **only on outcomes the ledger has already resolved** (`resolved_at <= made_at`), by damped Newton on the
negative log likelihood plus a ridge pulling `(a, b)` toward `(0, 1)` with strength **20** (on the summed loss), refitted every **200** newly resolved outcomes (before
the first refit `recal` equals the model). Probabilities are clipped to [0.01, 0.99] as in `PLAN.md`. These settings are fixed here.

## 4. Claims, decided before any number exists

Intervals: the same 95% person-cluster bootstrap (B = 2000, error risk: blocks of 100 cases), paired on the same resamples. "Beats" means the upper end of the paired
interval of (recal minus the comparator) is below zero.

| ID | Claim | Pass rule |
|---|---|---|
| **R1** | Error risk, rule change: **after the change** (cases from 1,500 on, pooled over the 8 drift deployments) `recal` beats the frozen model on log loss | upper end of the interval < 0 |
| **R2** | No harm without a change: in the v1 world and in the error-risk world with no change, `recal` is **not worse than the frozen model by more than 0.005 nats** (non-inferiority) | upper end of the interval <= +0.005 in both worlds |
| **R3** | Shifted hazard worlds: `recal` beats the frozen model in **each of the three** families | upper end < 0 in all three |
| **R4** | Calibration is restored: in the error-risk drift world after the change, the 95% interval of `recal`'s calibration intercept contains 0 | interval contains 0 |

Reported and **not** claims (no pass rule, so no way to pass or fail by choosing a comparator): `recal` against the best naive predictor in each shifted world (does
recalibration rescue the model?), `recal` against the frozen model in the v1 world, and `recal`'s calibration slope in every world.

A claim that fails is a finding and is printed.

## 5. Discipline

`python -m understudy_engine.hrt.run_recal dev | heldout`; the held-out command refuses without `UNDERSTUDY_HRT_HELDOUT=1`, without a freeze of part `recal` (code and
plan hashes), after a change, or on a second run (`evals/hrt/heldout_log.jsonl`). Dev is for debugging only and is never reported as evidence.

## 6. What this cannot show

All of `PLAN.md` section 9 applies. In addition: `recal` is fitted on the same kind of outcomes it is then scored on, in worlds whose drift is a single step (a new
rule at case 1,500) or a different generator from the start; a drift that keeps changing, or one that makes the ranking of cases wrong (not only the scale), is
not what an intercept and a slope can repair. A negative result on R3 would say so.

## Amendment log

**A1, Sun 8 Nov 2026 about 01:40 GMT, after one dev run (DEV seeds k = 29, 30, never reported as evidence), before the freeze and before any run on the new seeds.**
The dev run showed the registered arm `recal` (a fit on **all** resolved outcomes) is slow to follow a rule change: in the drift world after the change its calibration
intercept was still about +0.6 (the frozen model's was about +1.1), because 1,500 outcomes from before the change keep pulling the fit back. R4 as registered (the
intercept interval of `recal` contains 0) failed on dev for that reason and **stays registered and will be reported whatever it does**. The registered arm is not
changed. Added, before the freeze, one further arm with a fixed setting chosen here from first principles (a window of the 2,000 most recent resolved outcomes, so that
a fit forgets a regime after a few thousand outcomes; no other window was tried, on dev or anywhere) and three further claims:

* **`recal_w`**: as `recal` (same ridge 20, refit every 200 resolved outcomes, same clipping) but fitted only on the **2,000 most recent resolved outcomes** (all of them
  while fewer than 2,000 have resolved).
* **R5** Error risk, rule change: after the change `recal_w` beats the frozen model **and** beats `recal` on log loss. Pass: the upper ends of both paired intervals < 0.
* **R6** Error risk, rule change: after the change the 95% interval of `recal_w`'s calibration intercept contains 0.
* **R7** No harm for `recal_w`: in the v1 world and in the error-risk world with no change, `recal_w` is not worse than the frozen model by more than **0.01** nats
  (non-inferiority; a windowed fit is noisier than a growing one, so the margin is twice R2's, fixed here). Pass: upper end of both intervals <= +0.01.

Reported, not claims: `recal_w` against the best naive predictor in each shifted world, and `recal_w` against the frozen model in each shifted world. The dev run also
showed, for reading only: in the shifted hazard worlds `recal` came close to the online base rate (it did not clearly beat it), so this plan makes no claim that
recalibration beats a naive predictor there; it asks whether it **rescues the model from being far worse than one**.
