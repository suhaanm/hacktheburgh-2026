# Stuck prediction and the Forecasts scorecard

> Predicts 'no progress in the next minute' inside a stated false-alarm budget, and shows how well it does against two plain baselines.

**Capability:** See the work · **Status:** verified · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** verified (verified on its own generator; does not transfer to harder synthetic data) · **Page:** `docs/features/stuck-model.md` · **Targets:** HRT

## What it does

Every 30 seconds Knack estimates the chance that there will be no progress in the next minute, and raises an alarm only inside a false-alarm budget of 1.0 an hour. The Forecasts screen shows the reliability diagram beside two baselines.

## How it works

Bins of 30 seconds. Features: the last three step types, dwell, repeated actions, time since progress and a role prior. The first model (v1) is a hand-written logistic regression. It is scored leave one person out; the alarm threshold is chosen on the training people only, under the budget; scoring is by event (episodes detected, false alarms an hour), not by window. v2 (gradient boosting with monotone constraints, Platt-calibrated) was accepted as a small gain for the benefits processor and the programmer. The prediction is one input to the coach and to Cue; both also need deterministic signals.

**What is different.** It is scored by event with a false-alarm budget and set beside two plain baselines at the same budget, and its shortfall against them is published on the same screen.

## Where to see it

More, then Forecasts (address #/forecasts; for admins, Firm, Forecasts). The coach and Cue use the same signal.

## Demo moment

Open Forecasts. Show the reliability diagram, then the two baselines (base rate, time since progress), then false alarms an hour against the budget of 1.0. Say the model's edge over the plain rule is small on harder data, and the page says so.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Log loss 0.436 [0.422, 0.451] against 0.509 [0.496, 0.524] (time since progress) and 0.509 [0.497, 0.524] (base rate); flags 33% [27.5, 38.6] of stuck events; false alarms 1.21 an hour [0.95, 1.48] against a budget of 1.0 | synthetic, 4 people, leave one person out | `evals/report.md (Stuck hazard)` |
| The edge over time-since-progress falls from 0.071 to 0.008 to 0.015 nats per bin on three harder generators; a model trained on the first generator is 0.43 to 0.53 nats worse than that baseline there | synthetic, 120 people per cell | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |
| A4 accepted as a small gain: log loss -0.0039 nats (99.3% interval [-0.0062, -0.0017]) against v1 | synthetic, 32 held-out people | `evals/mlv2/results/heldout_hazard.json` |
| Under generator mismatch the plain time-since-progress rule beats v1: -0.021 [-0.034, -0.010] (benefits processor), -0.024 [-0.034, -0.014] (analyst), -0.030 [-0.041, -0.019] (programmer) | synthetic, pooled off-diagonal cells | `evals/report.md (Findings)` |
| Neither v1 nor v2 transfers to the language-model participants' traces: log loss 1.43 [1.25, 1.60] and 1.46 [1.31, 1.61] against 1.08 [1.00, 1.15] for the base rate | simulated participants (language model), not people; 24 participants, 419 bins | `evals/report.md (Findings); evals/mlv2/results/transfer_sim.json` |

## Honest limit

The honest claim is that a simple time-since-progress rule does about as well as the full model once the generator changes; the first headline mostly reflects our generator. The false-alarm budget is broken in many mismatch cells. The product decision (keep v1 or make the rule the default signal) is pending with the owner; the coach and Cue work either way because they also gate on deterministic signals.

## Hackathon target

- **HRT (best use of data for predictions and decisions)**: a prediction with a stated budget, baselines, and its shortfall shown

## 30-second spoken script

> Knack predicts, every thirty seconds, whether you are about to make no progress for a minute. It may only raise an alarm inside a budget of one false alarm an hour. On our own synthetic data it beats two plain baselines. On harder synthetic data its edge over a simple time-since-progress rule shrinks to a few thousandths. We publish both, and the screen shows the baselines next to the model.

## Slide bullets

- 30-second bins; alarm only inside 1.0 false alarms an hour.
- Log loss 0.436 against 0.509 for both baselines (synthetic, n = 4).
- On harder generators the edge falls to 0.008 to 0.015 nats; a simple rule does about as well.
- Fails to transfer to language-model participants' traces: shown, not hidden.
- Used as one input only; code gates what it triggers.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.1 hazard)`
- `evals/report.md (Stuck hazard, Findings)`
- `evals/realism/INTERPRETATION.md`
- `evals/mlv2/results/heldout_hazard.json`
- `evals/mlv2/results/transfer_sim.json`
- `docs/reference-notes/stride.md`
- `docs/FIX_LEDGER.md (section G)`
- `apps/dashboard/src/screens/Predictions/Predictions.tsx`

## Related pages

`live-coach.md`, `cue.md`, `what-did-not-hold-up.md`
