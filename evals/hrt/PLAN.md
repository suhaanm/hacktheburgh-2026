# PLAN: prospective prediction ledger and decisions scoreboard (HRT track), pre-registration

Written by the HRT-STRENGTHEN track (Track H) on Sun 8 Nov 2026, about 00:35 GMT, **before any evaluation on a held-out pool and before any
number of this plan has been computed on any pool**. The commit that adds this file comes before the first held-out run; its git timestamp is
the proof. After the commit this file changes only by dated entries in the amendment log at the bottom. Nothing in sections 2 to 9 is edited
after the fact. Model ID of the author: claude-sonnet-5-5.

Everything here is **synthetic or simulated** (our own seeded generators). A result here shows how the method behaves against a known
mechanism that we wrote. It never shows that real workers, real agents or real reviewers behave this way. The live study (n = 4) is not run,
and nothing here is a claim about it.

## 1. What this adds, and why a prediction-and-decision judge would ask for it

The existing evidence scores the stuck model by **leave one person out** on a pooled table. That protocol is sound for "does it work for a new
person", but it is not how the model is used: in use, a prediction is made now, the outcome arrives later, and the model has seen only the
past. Two questions follow that LOPO cannot answer.

1. **Predict first, score later.** If every prediction is written to an append-only record *before* its outcome exists, and scored only from
   that record, is the model still better than the dumbest competent predictor, and is it calibrated, on data it never saw and that is
   later in time than anything it was fitted on? (Parts P1 to P3.)
2. **What happens when the world changes?** The realism study found that the stuck model's edge falls on harder generators and that a model
   fitted on v1 is worse than "time since progress" there. Reporting that is honest; **noticing it while it happens, and falling back, is a
   decision**, and a decision can be scored: its premium (what it costs when nothing is wrong) and its payout (what it saves when the model
   is wrong), against always trusting the model, never trusting it, and an oracle that knew. (Part P4.)

The second half asks the same of every decision rule we ship: **realised cost against a naive policy and an oracle policy, with paired
intervals and a stated multiple-comparison correction** (Part D).

## 2. Data pools and seeds (all new; none used by any earlier evaluation)

Seeds used before this plan, by track: mlv2 persona replicates `base + 10 r` (r = 0..3) and `base + 1000 r` (r = 1..16) for bases 1101, 2202,
3303, 4404; mlv2 apprentices 8808 + ...; realism `20261107 + 1000 f + 100 q + 10 k + kind`; routing 0 to 2026 and re-draws at `seed + 1000 + i`;
OPE `seed + 1000 + i`; ski rental 101. A scan of the engine and evals sources for every integer of five to nine digits on a line mentioning a seed
found 10000, 10059, 12345, 20000, 46656, 100000, 104729, 964049, 5696411 and 20261107 (the calendar and realism base). **A test
(`tests/hrt/test_pools.py`) asserts that every seed below is disjoint from all of those, from the mlv2 and realism formulas, and from each other.**
(The scan covers what is in the repository on 8 Nov 00:30; it cannot see a track's unmerged branch, which is why the pools are far from every
value found.)

| Pool | What | Seeds | Use |
|---|---|---|---|
| **TRAIN** (deployment history) | v1 personas, 4 types x replicates k = 1..4 (16 persona-streams of 21 days) | `base + 100003 k`, base in {1101, 2202, 3303, 4404} | fits the deployed hazard, time-to-progress and error-risk models once; never touched again |
| **DEV** | v1 personas k = 5, 6 (8 persona-streams); v2 workweeks, each of 3 families, 2 deployments | v1: `base + 100003 k`; v2: `6100000 + 1009 k + 100 f` (f = family index markov 0, latent_skill 1, process_trace 2), k = 1, 2 | debugging, the freeze of section 7, **never reported as evidence** |
| **HELD** | v1 personas k = 11..18 (8 deployments x 4 types = 32 persona-streams); v2 workweeks, 3 families x 8 deployments of 20 people x 14 days (480 people) | v1: `base + 100003 k`; v2: `6100000 + 1009 k + 100 f`, k = 11..18 | **single final run** of section 8 |
| **ROUTE** (error-risk worlds) | routing case streams from `simulate_cases` and a drift variant; TRAIN stream 1500 cases, DEV deployments 2, HELD 8 per world | `7200000 + 313 k` (TRAIN k = 1; DEV k = 2, 3; HELD k = 11..18); the drift variant uses the same seeds with the drift mechanism of section 5.4 | Part P6 |
| **DECIDE** (the scoreboard) | fresh simulated worlds per row | `9300000 + 211 k + 10000 j` (row j: ski 0, routing 1, presence 2, nudge 3); DEV k = 1..3; HELD k = 11..(10 + K) | Part D |

A **deployment** is one independent replicate of a world: one chronological stream, one ledger. The v1 world's deployment is 4 persona-streams
(one of each type) merged by time. A v2 deployment is one workweeks draw of 20 people. People are the bootstrap cluster (section 6).

## 3. Part P: the ledger and what is scored from it

### 3.1 The ledger (code, not a model)

`understudy_engine/hrt/ledger.py`. Append-only; every entry carries `seq`, `prev` (the hash of the previous entry) and `hash` (sha256 of
the canonical JSON of the entry and `prev`). `verify()` recomputes the chain. Rules enforced in code, each with a test:

1. A prediction records `made_at`, `kind`, `stream` (a hashed person or case id), the probability (or the discrete CDF), the **name and
   version of the model and of every baseline that predicted the same thing at the same moment**, and `horizon_s`. `made_at` never goes back
   (a prediction older than the newest entry is refused).
2. An outcome may be appended once per prediction, only for an existing prediction, and only with `resolved_at >= made_at + horizon_s`.
3. A baseline that learns online (the running base rate) may use only outcomes with `resolved_at <= made_at` (`resolved_before(t)`).
4. Scoring reads only resolved predictions, reports the number still pending, and **refuses** (returns a stub with the reason) below 200
   resolved predictions or when a stream has a gap in its sequence numbers.
5. Nothing in the record stores page text, URLs, names or field values: a stream key is a salted hash; a probability and a label are numbers.

### 3.2 What each deployed predictor is

* **Stuck hazard.** `HazardModel("full")` (the product's model), fitted once on TRAIN bins and **frozen**. Bin, label and features are v1's:
  30 s bins, label 1 iff no `progress` event in the next 60 s, features use only what has happened up to the bin (a test truncates each episode
  at the bin and checks the features are unchanged: no leakage by construction).
* **Naive baselines** (all predicting the same label at the same moment):
  `online_base`: the running share of *resolved* labels in this deployment's stream (prior: TRAIN base rate with weight 20 observations);
  `frozen_tsp`: `HazardModel("tsp")` fitted on TRAIN (time since progress only); `frozen_base`: the TRAIN base rate.
* **Time to progress** (stretch, P5). `DiscreteTimeModel("full")` of `mlv2.tte` fitted on TRAIN, frozen; baselines: frozen Kaplan-Meier constant.
* **Error risk** (P6). `RoutingModel` (logistic, Platt) fitted and calibrated on the ROUTE TRAIN stream, frozen; baseline: running share of
  resolved errors.

### 3.3 Scoring (proper scoring rules; all lower is better)

Per deployment and pooled per world: **log loss**, **Brier**, **ECE** (10 equal-width bins) and the **reliability table**; the **calibration
intercept and slope** from the logistic recalibration `logit P(y = 1) = a + b logit(p)` (slope 1 and intercept 0 are perfect; a slope below 1
means over-confident). Time to progress: the **truncated CRPS** (seconds): the sum over the observed steps of the squared difference
between the predicted CDF and the step function of what happened, times the step length, divided by the number of observed steps; an origin
censored after s steps contributes only the s steps it observed, so censoring is handled and nothing is imputed. Probabilities are clipped to
[0.01, 0.99] (so a single bin can cost at most 4.6 nats) before any score; this is a protocol choice, stated here.

## 4. Part P claims, decided before any held-out number exists

Intervals everywhere: **95% percentile cluster bootstrap resampling people** (B = 2000, the same resamples for every model compared, so
differences are paired). A person is one stream key; a replicate draw gives new people. "Beats" means the **upper end of the paired interval of
(model minus baseline) is below zero**; "worse" means the lower end is above zero; otherwise "no clear difference".

| ID | Claim | Pass rule |
|---|---|---|
| **P1** | In the **v1 world** (fresh seeds, no refit), the deployed stuck hazard beats **both** `online_base` and `frozen_tsp` on log loss | the upper end of both paired intervals is below 0 |
| **P2** | In the v1 world it is **calibrated**: the 95% interval of the calibration slope contains 1 and that of the intercept contains 0 | both contain |
| **P3** | In the **shifted worlds** (v2 workweeks: markov, latent_skill, process_trace) the deployed model is **worse than the better of the two naive baselines in at least 2 of the 3 families** (the realism finding, replicated prospectively on new seeds) | per family: the lower end of (model minus the better baseline, chosen on that family's pooled log loss) is above 0; count families |
| **P4a** | The **guard** (section 4.1) raises no flag in at least 7 of the 8 v1 deployments | flags <= 1 of 8 |
| **P4b** | The guard raises a flag in at least 6 of 8 deployments of every family in which P3's condition holds | per family |
| **P4c** | The guard's **premium** is small: in the v1 world the guarded system's mean log loss is within 0.01 nats of always trusting the model | paired mean difference <= 0.01 |
| **P4d** | The guard's **payout**: in a family where the model is worse than the fallback by more than 0.05 nats, guarded is better than always-model by more than 0.02 nats | paired mean difference <= -0.02 |
| **P6a** | Error risk, no drift: the routing model beats `online_base` on log loss and its slope interval contains 1 | as P1 and P2 |
| **P6b** | Error risk, with a rule change halfway (section 5.4): the guard flags in at least 6 of 8 deployments and in at most 1 of 8 no-drift deployments | counts |
| **P5** (stretch; may be cut, and then the section says **not run**) | Time to progress, v1 world: the model's CRPS beats the Kaplan-Meier constant | paired interval below 0 |

Results are reported whether or not they pass. **A failed claim is a finding and is printed as one.** No claim is changed after the held-out run.

### 4.1 The guard (a decision rule; the model proposes, code decides)

Per deployment, over its stream in the order outcomes resolve:

* The **fallback** is `online_base` (the dumbest competent adaptive predictor). The model is the primary.
* The evidence is an **e-process** against "the model is no worse than the fallback": per episode (per case for P6) the bounded difference
  `d = mean log loss of the model minus mean log loss of the fallback` over the episode's bins, clipped to [-B, B] with B = 4.6; the capital
  `K_t = K_{t-1} (1 + lambda d_t / B)` with **lambda = 0.8** fixed, `K_0 = 1`; a flag is raised the first time `K_t >= 20` (so under the null
  the chance of ever flagging is at most 5%, by Ville's inequality, if each d has conditional mean at most 0). Episodes of one person are
  treated as exchangeable; bins inside one episode overlap in time, which is why the unit is the episode and not the bin.
* After a flag the system uses the fallback for the rest of the stream (no return in this plan; a return rule is future work).
* **Decision accounting.** Four strategies per deployment, scored on the mean log loss over all of the deployment's bins: always the model;
  always the fallback; the guard; the **oracle**, which picks whichever of the first two is better over that deployment in hindsight.
  Regret = a strategy's mean log loss minus the oracle's. The unit is the deployment (8 per world), so these intervals are wide; flag counts
  are reported as counts with exact (Clopper-Pearson) intervals.

## 5. Part D: the decisions scoreboard

One row per decision rule we ship. For each, a **naive policy**, an **oracle policy**, and the **realised cost** (or value) in the rule's own
unit, on K fresh replicate worlds, with the paired difference to the naive policy and its interval. All primary and exploratory cells are
listed in the output; nothing is dropped.

| Row | Decision | Shipped rule | Naive policies | Oracle | Unit | Replicates (K) |
|---|---|---|---|---|---|---|
| D1 | when to build an automation | ski rental with predictions, trust lambda learned online (`routines.skirental.choose_lambda`) | break-even (rent until rent paid = price); build at once; never build | hindsight `min(runs, b)` | manual-run equivalents per routine (lower is better) | 40 worlds x 500 routines |
| D2 | which cases an expert reviews, under a 30% review budget | the routing model's risk ranking (`routing.model`), top 30% reviewed | review a random 30%; rank by agent confidence only; rank by calculator disagreement only | rank by the generator's true error probability (a ceiling for any predictor); and review exactly the wrong ones (hindsight) | escaped errors per 100 cases at the same expert cost (lower is better) | 40 worlds x 3000 cases |
| D3 | when to start a background run | the presence window rule (`presence.evaluate.evaluate_decisions`) | run whenever idle five minutes; fixed overnight window | start iff the spell will last long enough (knows each spell's length) | value per held-out day, `completed runs - (L/G) x collisions`, with L/G = 9 implied by the 10% interruption cap | 8 replicates x 4 personas |
| D4 | speak, annotate, take over or stay silent | the contextual bandit's greedy snapshot (`policy.bandit`) | the rule baseline (`policy.rules`); always nudge; never speak | the exact optimum of the simulator's reward | simulator reward per decision, exact in expectation (higher is better) | 30 simulator runs |
| D5 | Cue: speak at a stuck moment | (recorded: `evals/cue/held_out.json`, run once by the Cue track) | silence | n/a | seconds to resume | **read, not re-run** |
| D6 | the help-level ladder | deterministic code cross-checked against a written spec (COA-3) | n/a | n/a | n/a | **not scored**: it is a rule with no outcome to score until the live study |

**Primary contrasts (the pre-registered family of 4)**, chosen before any data:
**D1** shipped rule minus break-even at b = 8 manual runs (the pack's own build costs are 4 to 9); **D2** model minus random at the 30% budget;
**D3** rule minus run-whenever-idle at L/G = 9; **D4** bandit snapshot minus the rule baseline. For each, the unit is the replicate and the
interval is a paired percentile bootstrap over replicates (B = 4000). **Multiple comparisons:** the family of 4 primary contrasts is reported at
the Bonferroni-adjusted level 98.75% beside the nominal 95%, and a contrast is called a win only if its **adjusted** interval excludes 0 in the
good direction. Every other cell (other build costs b, other naive policies, other loss ratios L/G in {1, 3, 27}, other budgets) is
**exploratory**, labelled with the number of exploratory cells in its row, and is never used to say a rule works.

A **sensitivity** is part of each row, because decision value depends on a cost the data cannot supply: D1 over b in {4, 8, 16, 32}; D2 the
**break-even cost of an escaped error**, in minutes of expert time, above which the model's routing beats not reviewing and below which
reviewing nothing is cheaper (and the same against reviewing everything); D3 over L/G; D4 none (the reward is the simulator's).

### 5.4 The drift world for error risk

`simulate_cases` with its mechanism changed from case 1500 on ("a new benefit rule"): the intercept of the error logit rises by 1.0 and the
`near_cliff x self_employed` term doubles. The routing model is not told. Cases are timestamped by arrival index; an outcome resolves 50 cases
after the case arrives (the review lag). The online base rate sees outcomes only after that lag.

## 6. Statistics, once

* Cluster bootstrap: people (stream keys) for Part P; replicate worlds for Part D. B = 2000 (P) or 4000 (D) percentile draws; seed fixed in code.
* Level 95% nominal; 98.75% for the four primary scoreboard contrasts. Flag counts: Clopper-Pearson 95%.
* The v1 world has four persona types, so its 32 persona-streams are 8 draws of 4 types: intervals treat the 32 as exchangeable draws of a
  4-type population; that is a model and is said in the section.
* No test is run on a dev pool and reported. No threshold, margin, lambda or pass rule is changed after the freeze (section 7).

## 7. Discipline: dev, freeze, held-out

1. **Dev** (`python -m understudy_engine.hrt.run dev`): DEV pool only. Debugging and sanity checks. Writes `evals/hrt/results/dev_*.json`.
2. **Freeze** (`python -m understudy_engine.hrt.run freeze`): writes `evals/hrt/results/frozen.json` with the sha256 of every file in
   `understudy_engine/hrt/` and of this plan. Every parameter named in sections 3 to 5 (lambda 0.8, B 4.6, flag 20, prior weight 20, the
   clip, the budget 0.30, b = 8, L/G = 9, the seeds, K) is **fixed by this plan, not by dev data**. If dev shows one is plainly broken, the fix
   is a dated amendment below, the broken setting stays in the record with its dev result, and nothing is tuned toward a better-looking answer.
3. **Held-out** (`UNDERSTUDY_HRT_HELDOUT=1 python -m understudy_engine.hrt.run heldout --part ledger|decisions`): refuses without the token, without
   `frozen.json`, with a code hash that differs from the frozen one (an edit after the freeze), or if the part already has a `start` line in
   `evals/hrt/heldout_log.jsonl`. It appends `start` (time, hashes) before touching held-out seeds and `done` after, and writes
   `evals/hrt/results/heldout_<part>.json` once. A re-run needs a declared amendment.

## 8. What the report will say whatever happens

* Origin **synthetic**; n and unit on every table; the split ("frozen at deployment; scored forward in time"; "fresh replicate worlds").
* The model's **edge over the naive baselines** and its **sign under shift**, with intervals.
* The **guard's premium and payout** against always-model, always-fallback and the oracle.
* For each decision row: naive, shipped, oracle, with the **share of the naive-to-oracle gap the shipped rule closes** (stated with its
  interval only where the denominator is clearly above zero).
* The limits, in section 9, in the same section of the report.

## 9. What this cannot show

1. Everything is generated by us. The v2 worlds differ structurally from v1, but they are still ours; a held-out replicate catches overfitting
   to one noise draw, never "the model learned our generators".
2. The guard's false-flag guarantee needs each episode's loss difference to have conditional mean at most zero given the past. Episodes of
   one person are not independent, so the guarantee is a design target that the 8 no-drift deployments check, not a proof.
3. Eight deployments per world give wide intervals for guard counts and for the strategy comparison.
4. The loss ratio L/G, the review minutes per case, the build cost b and the reward weights are **assumptions**, which is why each has a sweep.
5. The oracle policies are not implementable (they use the future or the generator); they bound what is possible, nothing else.
6. Nothing here was measured on real people, real agents or real reviewers. The live study (n = 4) has not run.
7. The ledger is built and tested, but **no live predictions have been recorded by the running product yet**; until they are, a real
   prospective result does not exist.

## Amendment log

**A1, Sun 8 Nov 2026 about 00:55 GMT, before any dev or held-out number exists** (code and tests only had been written; the pure modules
`ledger`, `scoring`, `guard` and `worlds` are tested on made-up data). Three clarifications, none of which uses data:

1. **P6 stream key.** Cases have no person. For the error-risk world the ledger's stream key is a block of 100 consecutive arrivals (hashed with
   the deployment id) and the bootstrap cluster is that block. The unit of the guard's e-process is one case.
2. **P4b and P6b are two-sided.** A guard that flags a model which is still better than the fallback is wrong, as is one that stays silent
   about a model that is worse. So: in every shifted family where P3's condition holds the guard must flag in at least 6 of 8 deployments, **and**
   in every family where the model is clearly better than the better naive baseline (upper end of the paired interval below 0) it must flag in at
   most 1 of 8. A family with no clear difference either way is reported with its counts and is not counted for or against the guard. For P6b the pre-change half of every drift deployment and the no-drift deployments
   count as "model better" cases; the post-change half counts as "model worse" only if the paired interval (model minus online base, pooled over
   the post-change cases of the 8 drift deployments) has its lower end above 0, otherwise the post-change model is still better than the fallback
   and a flag there is a false flag. Each outcome is reported with its counts either way.
3. **Replay order.** Predictions and outcomes are written to the ledger in time order (an outcome at the same instant as a prediction is written
   first, because it is then known), the online base rate is read through `Ledger.resolved_before`, and `verify()` is run before scoring. A test
   checks that the online base rate each prediction recorded equals the running mean of the outcomes resolved by its `made_at`.
