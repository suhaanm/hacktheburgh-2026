# Work genome: where time goes

> Aligns a novice's steps to the nearest expert's and prices each gap in seconds and in answers, with controls so the gap is not an artefact.

**Capability:** See the work · **Status:** verified · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Work genome: aligned traces priced in seconds, Controls: placebo and shuffled-label null, What skipping costs in answers.

## Work genome: aligned traces priced in seconds

**Status:** verified (verified on its own generator; degrades on harder synthetic data) · **Page:** `docs/features/work-genome.md` · **Targets:** G-Research

### What it does

Aligns a novice's steps with the nearest expert's and puts a price in seconds on each gap: a skipped check, a result read again and again, a figure copied from the wrong place. The screen shows an expert trace above a novice's, gaps hatched, seconds lost beneath.

### How it works

Events become steps through the role pack's mapping. A sequence alignment (Needleman-Wunsch, with a cost for each pair of step types) pairs each novice trace with the nearest expert trace. A step with no partner costs the time it took; a mismatched pair costs the difference in dwell. The gap is split by habit with a regression on behaviour counts, and intervals come from a bootstrap by person. A transition graph lists the step-to-step moves a novice never makes, and a replay slider plays a recorded trace on a virtual clock with idle gaps squeezed (the same events always give the same state). Everything here is plain code: no language model.

### Where to see it

More, then Where time goes (address #/genome). The Home hero's action, See where the time goes, opens it on that step. Settings, Views, Pinned views puts it in the sidebar.

### Demo moment

Open Where time goes. Point at the Synthetic badge, the ribbon (expert above, novice below, gaps hatched), and the waterfall that splits the seconds by habit. Say: the interval on the real gap does not include zero, and the badge says synthetic.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Precision 92% [84.5, 98.6], recall 95% [88.6, 100.0] on planted deficits (16 people, 5 deficits over 32 novice cases; first generator) | synthetic | `evals/report.md (Deficit recovery)` |
| Weakest on 'reads the result again and again' (precision 70% [40.0, 94.1]) and 'copies the wrong figure' (recall 71% [33.3, 100.0]) | synthetic | `evals/report.md (Deficit recovery)` |
| On three harder generator families precision falls to 48 to 71% and recall to 49 to 68%; thresholds fitted on the first generator keep recall (87 to 95%) but precision falls to 33 to 56% | synthetic, 87 to 92 people per family | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |

### Honest limit

The 92% and 95% describe our own generator, not workers. On harder synthetic data about a third of detections are wrong and the thresholds do not carry from one world to another. ML v2's pre-registered ensemble and counterfactual price were rejected as harmful on held-out cohorts, so the first alignment stays the default and there is no validated counterfactual in seconds.

### Hackathon target

- **G-Research (make the invisible visible)**: the expert's hidden policy made visible as priced gaps

## Controls: placebo and shuffled-label null

**Status:** verified · **Page:** `docs/features/work-genome.md` · **Targets:** G-Research

### What it does

Before a gap is shown, Knack compares experts with experts and re-runs the whole analysis after shuffling who is novice and who is expert. If the real gap does not stand clear of both, it is an artefact.

### How it works

The placebo aligns each expert to the nearest other expert. The null shuffles the expert and novice labels across people and repeats the whole procedure, 1,000 permutations. Both should include zero; the real gap should not. The Evidence page prints both beside the real gap.

### Where to see it

Where time goes (the controls under the ribbon) and Evidence (More, For reviewers).

### Demo moment

On Where time goes, read the three numbers aloud: 229.6 seconds a case for the real gap, 7.1 for expert against expert, 46.2 for the shuffled null. The first interval excludes zero; the other two include it.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Real gap 229.6 s per case [192.7, 272.6]; placebo 7.1 s [-2.8, 18.4]; shuffled-label null 46.2 s [-36.4, 116.9]; permutation p = 0.001 | synthetic, 24 people, 1,000 permutations | `evals/report.md (Controls)` |

### Honest limit

The null is not zero: about 20% of the real gap, because nearest-reference matching is not symmetric. Both control intervals include zero, but they are wide.

### Hackathon target

- **G-Research (make the invisible visible)**: a baseline beside every gap

## What skipping costs in answers

**Status:** built · **Page:** `docs/features/work-genome.md` · **Targets:** G-Research, HRT

### What it does

Skipping a step looks free in seconds, so Knack also prices it in answers: how often skipping the reconcile step puts a wrong figure in the case note, and how often skipping the cliff check leaves a nearby edge unwarned.

### How it works

On 200 synthetic households scored by the sandbox oracle, skipping reconcile means writing one calculator's figure into the note without comparing the three. Skipping the cliff check means no warning that a small documented change (savings, rent, childcare, earnings) would move the award. The result is a count with an interval.

### Where to see it

Where time goes (the answers view beside the seconds) and Evidence.

### Demo moment

Say it in one line: skipping the cliff check costs almost nothing in seconds, but on 107 of 200 households it leaves a nearby edge unwarned, and on 42 of those a small change moves the award by more than 50 pounds a month.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Skipping reconcile is wrong on about 20.7 of 200 households (10.3% [7.8, 13.0]) | synthetic, 200 households, bootstrap by household | `evals/cases/skip_consequences.json` |
| Skipping the cliff check leaves a nearby edge unwarned on 107 of 200 (53.5% [46.6, 60.3]); a small change moves the award by more than 50 pounds a month on 42 of those 107 | synthetic, 200 households, Wilson interval | `evals/cases/skip_consequences.json` |

### Honest limit

The calculators' quirks and the oracle are ours. The oracle is a simplified rule set, not law: it agrees with PolicyEngine UK within 1 pound on only 8 of 20 generated households. Households cycle through 12 archetypes, so the interval describes this mix only.

### Hackathon target

- **G-Research (make the invisible visible)**: the cost of a hidden habit in answers, not only seconds
- **HRT (best use of data for predictions and decisions)**: a decision with a stated cost

## 30-second spoken script

> Two people do the same job. One is slower and gets a different answer, and nobody can see where. Knack aligns the novice's steps to the nearest expert's and prices each gap in seconds. Then it checks itself: expert against expert, and shuffled labels, both near zero. On our synthetic data the real gap is about 230 seconds a case. The badge says synthetic, because it is.

## Slide bullets

- Aligns a novice's steps to the nearest expert's; every gap priced in seconds.
- Two controls: expert against expert 7.1 s, shuffled labels 46.2 s, real gap 229.6 s (synthetic, n = 24).
- Skipping a check is free in seconds and costly in answers: 107 of 200 households unwarned.
- Precision 92% on our generator, 48 to 71% on harder ones: both shown.
- Everything is synthetic and badged; plain code, no language model.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.1 genome)`
- `docs/UI_DIRECTION.md`
- `evals/report.md (Deficit recovery, Controls, Findings)`
- `evals/realism/INTERPRETATION.md`
- `evals/cases/skip_consequences.json`
- `docs/FEATURE_CATALOGUE.md`
- `docs/KNACK_UX.md (section 3)`

## Related pages

`stuck-model.md`, `evidence-and-explain.md`, `what-did-not-hold-up.md`
