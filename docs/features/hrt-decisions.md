# Decisions under uncertainty

> When to build an automation, which agent outputs a human must check, and how to judge a policy before switching it on.

**Capability:** Routines and automations · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers When to build an automation: ski rental with predictions, Review routing under a risk bound.

## When to build an automation: ski rental with predictions

**Status:** built · **Page:** `docs/features/hrt-decisions.md` · **Targets:** HRT

### What it does

Building an automation costs effort and saves time only if the routine keeps coming back. Knack uses a ski-rental rule with a forecast to decide when to propose building.

### How it works

With the cost of building b (in units of one manual run), a forecast y of remaining runs and a trust parameter lambda between 0 and 1: if y is at least b, build after about lambda times b runs; otherwise after b divided by lambda. The rule is 1 + 1/lambda robust and 1 + lambda consistent (Kumar, Purohit and Svitkina); the constants were checked numerically. Lambda is chosen from past forecast error, a heuristic labelled as one.

**What is different.** A rule with a proven worst case is applied to the build-or-wait decision with a forecast, and the table shows where building at once beats it.

### Where to see it

Behind the proposals in Needs you and the value line on a proposal; Evidence has the regret table.

### Demo moment

Say the table in one line: with predictions regret is 1.33 against 1.78 for building at break-even, and building at once, at 1.27, beats both at the simulated cost.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Regret (hindsight best = 1.0): ski rental with predictions (lambda 0.2) 1.332 [1.322, 1.342]; build at break-even 1.776 [1.765, 1.786]; build now 1.273 [1.257, 1.290] | synthetic, 4,000 simulated routines, build cost 16 manual runs | `evals/report.md (Ski-rental build timing)` |

### Honest limit

Simulated routines with a stated mechanism, not real build decisions. Building at once beats the prediction rule at the simulated cost, so the rule is not uniformly best.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision rule with a proven worst case and a measured regret

## Review routing under a risk bound

**Status:** built · **Page:** `docs/features/hrt-decisions.md` · **Targets:** HRT

### What it does

Auto-approve the safest agent outputs and send the rest to a person, with a stated bound on the error rate of what is auto-approved.

### How it works

Features: case complexity, the worker's trace, worker-versus-agent disagreement and agent confidence. Calibrated scores rank cases. The auto-approved set is the largest one whose Clopper-Pearson upper bound on the error rate is at most 0.05 on a calibration split; the bound is then checked on a held-out split.

**What is different.** The auto-approved set is the largest one whose Clopper-Pearson bound stays under the target, checked on held-out cases, with the circularity stated.

### Where to see it

Evidence (review routing); not a screen of its own.

### Demo moment

Say: held-out error 0.0% at 93.8% coverage, and the page says why that is circular.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Held-out error 0.0% [0.0, 1.7] at 93.8% coverage; target 0.05; the bound held | synthetic, 900 households (train 450, calibration 225, held-out 225) | `evals/report.md (Review routing and risk control)` |

### Honest limit

Circular: the calculators' quirks and the households that trigger them were planted by us, so the router finds our planted structure. The bound holds for cases like the calibration cases; a new rule or calculator breaks it silently. Review time per case is an assumption.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: risk control with a held-out check, stated as circular

## 30-second spoken script

> Three decisions that need numbers. When to build an automation: a ski-rental rule with a forecast, which in simulation had regret of one point three against one point eight for the naive rule. Which agent outputs a person must check: a risk bound checked on held-out cases. And a new coaching policy is judged on old logs before it is switched on. All three are synthetic, and the page says where each one is circular.

## Slide bullets

- Ski rental with predictions: regret 1.33 against 1.78 at break-even (synthetic).
- Building at once, 1.27, beats both at the simulated cost: shown.
- Review routing: Clopper-Pearson bound, checked on a held-out split.
- Held-out error 0.0% at 93.8% coverage; circular, and stated.
- The start-or-wait rule and off-policy checks are on the Your hours and Live coach pages.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.1 routing, routines)`
- `docs/reference-notes/ski-rental.md`
- `docs/reference-notes/moa.md`
- `evals/report.md (Ski-rental build timing, Review routing and risk control)`
- `docs/drafts/CLAIMS.md (C09, C10)`

## Related pages

`routines.md`, `work-graph-and-hours.md`, `live-coach.md`, `stuck-model.md`
