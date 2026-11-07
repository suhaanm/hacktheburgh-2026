# What did not hold up

> We published the results that went the wrong way: the stuck model and genome on harder data, ML v2, the simulated study, computer use, and parts of Cue and the attention router.

**Capability:** Evidence and honesty · **Status:** verified · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Generator-mismatch test (the realism matrix), ML v2, held-out: mostly negative, The simulated study sat at the floor, Other results that went the wrong way.

## Generator-mismatch test (the realism matrix)

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** G-Research, HRT

### What it does

We asked how much of each result survives when the pipeline is tested on a synthetic generator it was not built on. Much of it does not.

### How it works

Three structurally different generators (continuous person effects, many valid paths, noisy capture, interruptions, a label that is a hidden state, not read from an emission table) with 40 people per dataset and three replicates. Every ordered pair of fit family and test family is scored, with a person-cluster bootstrap. Five expectations were pre-registered and scored afterwards.

**What is different.** We tested our own methods on generators they were not built on and published the drop, with expectations registered beforehand.

### Where to see it

Evidence (Findings), the realism section; evals/realism/INTERPRETATION.md.

### Demo moment

On Evidence, open the first finding: the stuck model's advantage depends on the generator. Read the two numbers: 0.071 nats on its own generator, 0.008 to 0.015 on harder ones.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Stuck model: edge over time-since-progress 0.071 falls to 0.008 to 0.015 nats per bin; a model trained on the first generator is 0.43 to 0.53 nats worse than the baseline on the others and overshoots the false-alarm budget 1.7 to 4.2 times | synthetic, 120 people per cell | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |
| Genome: precision 92% and recall 95% fall to 48 to 71% and 49 to 68%; false attribution rises from 1.1 s to 46 to 59 s per case | synthetic, 87 to 92 people per family | `evals/report.md (Findings)` |
| Routine finder: raw precision 22% on the first generator is 44 to 97% on the others, recall falls to 45 to 92%; proposals after the gate stay at 74 to 100% precision | synthetic, 120 people per cell | `evals/report.md (Findings)` |
| Of the five pre-registered expectations: three held, one half-wrong, one not supported | synthetic | `evals/realism/INTERPRETATION.md` |

### Honest limit

All three generators were written by the same team as the analytics and share the person hierarchy, interruption process and task grammar. Passing or failing this test says how robust the methods are to these changes, not how real workers behave. The only evidence about real people would be the live study, which has not been run.

### Hackathon target

- **G-Research (make the invisible visible)**: the invisible limits of our own methods, shown
- **HRT (best use of data for predictions and decisions)**: a result tested out of distribution

## ML v2, held-out: mostly negative

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** HRT

### What it does

We tried to improve the stuck model and the genome with pre-registered candidates. Most were rejected on held-out data, and the reports say so.

### How it works

Candidates and rules were frozen before the held-out run, which ran once. The primary metric for the genome families is the mean absolute error in seconds of the recovered price of a deficit, paired against the first method; for the stuck model it is log loss, paired against the first model, with adjusted intervals.

**What is different.** Candidates and decision rules were frozen before a single held-out run, and the rejections are reported as findings.

### Where to see it

Evidence (Findings: ML v2); evals/mlv2/PLAN.md and results.

### Demo moment

On Evidence, read: the expert-envelope ensemble and the counterfactual price were rejected as harmful, by 3.81 and 1.17 seconds.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Genome candidates: the expert envelope (E4) +3.81 s [+2.30, +5.19] and the counterfactual price (Q1) +1.17 s [+0.44, +1.87] absolute error: both rejected as harmful; only learned substitution costs (E1) was accepted, -0.92 s [-1.85, -0.21] | synthetic, 6 held-out apprentice cohorts, 96 novices | `evals/report.md (Findings); evals/mlv2/results/heldout_genome.json` |
| Stuck model: gradient boosting with Platt calibration accepted as a small gain, -0.0039 nats (99.3% interval [-0.0062, -0.0017]); under mismatch the plain time-since-progress rule beats the first model in all three roles | synthetic, 32 held-out people; mismatch matrix | `evals/mlv2/results/heldout_hazard.json; evals/mlv2/results/heldout_mismatch.json` |
| Neither version transfers to the language-model participants' traces: log loss 1.43 and 1.46 against 1.08 for the base rate | simulated participants (language model), not people, 24 participants | `evals/mlv2/results/transfer_sim.json` |

### Honest limit

Held-out replicates share our generator, so they catch overfitting to one noise draw, not learning the generator. No variant qualified for the data-analyst role.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: pre-registration, held-out discipline and honest nulls

## The simulated study sat at the floor

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** HRT, G-Research

### What it does

We ran a pre-registered study with language-model participants (not people) to test the pipeline and whether coaching changes later unassisted work. The outcome sat at the floor, so it says nothing about the coach.

### How it works

16 coached and 8 sham-arm participants, within-participant and counterbalanced, with an A/A arm in which the coach is silent in every block. Participants are language models with a 280-character self-written note as 'memory'. A follow-up pilot with more reasoning effort was stopped by its own criterion.

**What is different.** A study design was run end to end with language-model participants to test the pipeline and its enforcement, with an A/A arm and a power calculation, and a null reported as a null.

### Where to see it

Evidence (Findings and the simulated section); evals/study_sim/REPORT.md.

### Demo moment

On Evidence, read: 30 of 32 unassisted post-tests scored 0; the study validated the pipeline and the enforcement (no nudge outside the trained skill's block), not the coach.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Mean difference 0.094 [-0.051, 0.239], exact p = 0.5; 30 of 32 coached post-tests scored 0 and 16 of 16 A/A post-tests; the action cap was hit in 18 of 32 | simulated participants (language model), not people, n = 16 + 8 | `evals/study_sim/REPORT.md; evals/report.md (Simulated participants)` |
| Enforcement held: 0 non-silent coach polls in post-test blocks and 0 in blocks with the coach off; 12 nudges were shown, all in train blocks | simulated | `evals/study_sim/REPORT.md (section 5)` |
| Run 5 pilot stopped: 0 of 6 post-tests above zero (needed 3) | simulated | `evals/report.md (Simulated participants)` |
| What the n = 4 live design could detect: the smallest possible exact p is 0.125; for a medium effect the interval excludes zero 4.4% of the time at n = 4 and 27.3% at n = 16 | Monte Carlo of the design, 10,000 replications; a property of the design | `evals/report.md (Study power)` |

### Honest limit

The live study with four teammates has not been run. The role studies (programmer, analyst) were not run: one of three programmer feasibility pilots was usable and none are results. A higher score after coaching could be instruction-following plus a self-written note, not learning.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a power calculation done before spending a study
- **G-Research (make the invisible visible)**: a null reported as a null

## Other results that went the wrong way

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** G-Research

### What it does

Four more results that did not meet their targets, stated beside the features they concern.

### How it works

Each target was written before its held-out run; a miss is reported, not reworded.

**What is different.** Targets were written before the held-out runs; a miss is reported against its target.

### Where to see it

Evidence (Findings and sections); each feature page lists its own miss.

### Demo moment

Pick one and read it: 'Cue did not make people resume faster at the median.'

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Cue: 'faster to resume' not met (median paired difference 0.0 s [-9.5, 0.0]); false-nudge target met at 0.73 an hour | synthetic, 40 simulated personas, 481.5 hours | `evals/cue/held_out.json` |
| Attention router: criterion 7 not met (+0.33 can-wait toasts a day [+0.08, +0.58]); 11 of 12 met | synthetic, 200 simulated workers | `evals/attention/report_held_out.json` |
| Insights: planted independence rise selected in 47 of 100 worlds (target 0.8); false celebration when errors rise 14 of 100 (target 0) | synthetic, 100 worlds per effect | `evals/insights/results/heldout.json` |
| Computer use, held-out clean n = 4: 1 completed; injected n = 20: 20 of 20 paused at step 0 (detector, text only) | real model (OpenAI), our sandbox | `evals/report.md (Agentic evaluation)` |

### Honest limit

These are all simulated or sandbox results; none is about real workers.

### Hackathon target

- **G-Research (make the invisible visible)**: our own failures made visible

## 30-second spoken script

> Here is what did not hold up. On harder synthetic data the stuck model's edge over a plain rule falls to a few thousandths. The genome's precision drops from ninety-two to about sixty percent. Most of our machine-learning improvements were rejected on held-out data. Our simulated study sat at the floor and says nothing about the coach. And computer use completed one of four held-out households. We publish these on the Evidence page, next to the numbers that went well.

## Slide bullets

- Stuck model: edge 0.071 falls to 0.008 to 0.015 nats on harder generators.
- Genome: precision 92% falls to 48 to 71%.
- ML v2 held-out: ensemble and counterfactual rejected as harmful.
- Simulated study at the floor: 30 of 32 post-tests scored 0; says nothing about the coach.
- Computer use held-out: 1 of 4; Cue and attention targets partly missed.

## Sources

- `evals/report.md (Findings)`
- `evals/realism/INTERPRETATION.md`
- `evals/mlv2/PLAN.md`
- `evals/mlv2/results/`
- `evals/study_sim/REPORT.md`
- `evals/cue/held_out.json`
- `evals/attention/report_held_out.json`
- `evals/insights/results/heldout.json`
- `README.md (What did not hold up)`

## Related pages

`evidence-and-explain.md`, `stuck-model.md`, `work-genome.md`, `computer-use.md`
