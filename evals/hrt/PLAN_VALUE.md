# PLAN (follow-up): did the better forecast buy a better decision? Pre-registration

Written by the HRT-STRENGTHEN track on Sun 8 Nov 2026, about 02:10 GMT, **before any number of this plan has been computed on any pool**. The commit that adds this file
comes before the first run, on dev or held-out seeds. After the commit this file changes only by dated entries in the amendment log at the bottom. Model ID of the author:
claude-sonnet-5-5. Everything is from generators we wrote; no model call is made.

## 1. Why this follow-up exists, and what it is not

A quantitative judge's last question after "is the forecast scored properly?" is "does a better score make a better decision?". `PLAN.md` scores the stuck forecasts by log
loss; the product uses them to decide **whether to interrupt**. A model can win on log loss and lose on the decision (log loss rewards the whole probability scale, the decision
only cares about one threshold), or lose on log loss and still decide well. This plan puts the two side by side, **on the same forecasts, in the same worlds, from the
same ledger record**, and asks whether the first predicts the second. It does not reopen any claim of `PLAN.md`, `PLAN_RECAL.md` or `PLAN_CONFORMAL.md`. It is designed after the
lead's request of 8 Nov about 01:45 GMT, and **after the held-out results of `PLAN.md`** (so the sign of the log-loss difference in each world is already known; section 4 says which
claims depend on that and why they are not circular).

## 2. The decision, its cost, and its rule (all fixed here)

At every origin (a 30-second bin of a person's work) the product decides to **interrupt** (offer help) or **stay quiet**. The forecast is P(no progress in the next 60 s), the
stuck label of `PLAN.md`. Two costs, stated as assumptions and not measured:

* **S = 3 minutes** of the person's time saved when an interruption lands on someone who then makes no progress for a minute (label 1);
* **A = 1 minute** of attention lost when it lands on someone who would have made progress anyway (label 0).

The net value of an origin is S when it interrupts and the label is 1, minus A when it interrupts and the label is 0, and zero when it stays quiet. **The rule is the
decision-theoretic one and is the same for every predictor: interrupt when the forecast is at least A / (A + S) = 0.25**, the break-even point for a calibrated probability.
No threshold is tuned on any pool, and no predictor gets its own.

**Policies compared**, all in the same world and on the same origins: the four recorded forecasts of the ledger, each turned into a decision by the rule above (`model`, the
online base rate `online_base`, frozen time since progress `frozen_tsp`, the frozen base rate `frozen_base`); **always interrupt**; **never interrupt** (value 0); the **hindsight
oracle** (interrupt exactly when the label is 1; not implementable); and **guarded**, the system of `PLAN.md` section 6 (the model until the guard's flag, the online base rate
from then on; lambda 0.8, threshold 20), whose flag time is read from the same ledger replay.

**Reported numbers per world**: net minutes per origin and per hour of recorded work (120 origins), interruptions per hour, net minutes per interruption, and the share of the gap
between the better of {never, always} and the oracle that a policy closes, each with the 95% person-cluster interval (B = 2000, seed 0); and, beside them, each forecast's
log loss from the same record. Sensitivity (exploratory, no claim): the same table at A = 0.25, 0.5, 2 and 4 minutes with S = 3, thresholds A / (A + S).

## 3. Pools (new seeds; none used by any earlier evaluation or by the three earlier plans)

| Pool | What | k |
|---|---|---|
| **TRAIN** | as `PLAN.md` (the deployed models are fitted there, once) | 1 to 4 |
| **DEV** | v1 and v2 deployments (2 each) | 69, 70 |
| **HELD** | v1 deployments (8, four persona streams each); v2 deployments of each of the three families (8, 20 people x 14 days each) | 61 to 68 |

Seeds are `worlds.v1_seed(type, k)` and `worlds.v2_seed(family, k)`. A test asserts they are disjoint from every seed of the earlier plans.

## 4. Claims, decided before any number exists

Intervals are person-cluster bootstrap intervals on the per-origin net value, paired on the same resamples; the guard's are over deployments (n = 8).

| ID | Claim | Pass rule |
|---|---|---|
| **V1** | In the **v1 world** the model's decisions are worth more than either naive predictor's | the lower end of the paired interval of (model minus `online_base`) and of (model minus `frozen_tsp`), in net value per origin at A = 1, is above 0 |
| **V2** | **Log loss is a usable proxy for the decision under shift**: in the shifted worlds the model, which `PLAN.md` found worse than the best naive predictor on log loss, is also worse in decision value | in at least 2 of the 3 shifted worlds the upper end of the paired interval of (model minus that same best naive predictor, the one `PLAN.md`'s log-loss comparison names for that world) in net value per origin is below 0 |
| **V3a** | **Premium**: the guard costs nothing in decision terms where nothing changed | in the v1 world the guarded policy's net value per origin is not below the always-model value by more than 0.01 minutes (the lower end of the deployment-level interval of guarded minus always-model is at least -0.01) |
| **V3b** | **Payout**: the guard earns something in decision terms where the model fails | in at least 2 of the 3 shifted worlds the lower end of the deployment-level interval of (guarded minus always-model) in net value per origin is above 0 |

Reported and **not** claims: all of the numbers in section 2; the rank agreement between the log-loss ordering and the decision-value ordering of the four forecasts in each
world (Spearman, four points, descriptive only); the sensitivity grid.

V2 depends on a result already known (the sign of the log-loss difference in each shifted world); it is **not** circular because the claim is about the decision value, which
nothing in `PLAN.md` computed, and the rule asks for the decision to be worse **too**. A claim that fails is a finding and is printed.

## 5. Multiplicity

This part registers **4 claims**. With the 32 of the three earlier plans and the scoreboard, the HRT section has **36 registered claims or contrasts** (the brief counts them from
the result files, not from this sentence). V1 and V2 are directional paired contrasts and are in the Holm table of the brief once they exist; V3a and V3b are deployment-level
and are reported with their intervals.

## 6. Discipline

`python -m understudy_engine.hrt.run_value dev | freeze | heldout`; the held-out command refuses without `UNDERSTUDY_HRT_HELDOUT=1`, without a freeze of part `value` (code and plan
hashes), after a change, or on a second run (`evals/hrt/heldout_log.jsonl`). Dev is for debugging only and is never reported as evidence. Pure functions (the decision rule, the
net value, the gap share) have tests that run before any dev run.

## 7. What this cannot show

All of `PLAN.md` section 9 applies. In addition:

* **S and A are our numbers**, and the decision is at every origin with no cooldown or interruption cap: the product caps and spaces interruptions, so "interruptions per hour"
  here is what an unthrottled rule would do, not what the product does. The ranking of predictors is the claim; the minutes are not.
* A forecast scored by log loss and decided at one threshold are two views of the same numbers; agreement between them in four worlds is four points.
* The oracle is not implementable; "gap closed" is relative to it.
* Nothing here is about real workers; the live study (n = 4) has not run.

## Amendment log

(none yet)
