# Analysis plan: live study with four teammates (EVL-2, EVL-3, EVL-5)

**Status: written before any data exists.** The commit that adds this file must come before the first session; the git timestamp is the proof (EVL-3). After the first session this file changes only by dated entries in the amendment log at the bottom. The analysis code (`analyze.py`) and its tests were written first and run only on made-up numbers.

## 1. What the study can and cannot tell us

Four teammates, one short session each, synthetic households on local sandbox calculators. It is a **feasibility read with intervals**, not a test of an effect. The question it asks:

> After practising a skill with Understudy's coaching, do people exhibit that skill, unassisted, on a later matched case more often than after practising a different skill without coaching?

The headline is **unassisted performance on a later matched task** (EVL-5). Speed while being helped is reported separately and is never combined with it.

## 2. Design

Within-subject, counterbalanced, n = 4 (one person per sequence). Every person does two **blocks**. A block is: a practice case on one skill (coached or not), then an **unassisted** post-test on a matched case that exercises the same skill. The two blocks train **different** skills, so what is learned in block 1 cannot carry into the skill measured in block 2.

| Sequence | Block 1 (skill, practice) | Block 2 (skill, practice) |
|---|---|---|
| S1 | cliff, coached | reconcile, uncoached |
| S2 | reconcile, coached | cliff, uncoached |
| S3 | cliff, uncoached | reconcile, coached |
| S4 | reconcile, uncoached | cliff, coached |

Each skill is coached for two people and uncoached for two; the coached block comes first for two people and second for two. The skills are the pack's `check-the-cliff` (open "Check cliff edges" and read it on each calculator before writing the note) and `reconcile-before-noting` (compare the calculators and record the right reconciliation before saving the note).

Cases come from `evals/cases/households_200.json`. To fit the time budget each case uses two calculators, GovCalc (a) and Quick Estimator (b), and the case note is saved as a draft only. Two matched pairs were chosen by rule (`make_assignments.py`, output `assignments.json`, fixed before data): same archetype, same cliff flags, savings within a thousand pounds, calculators a and b differ by more than one pound (so the correct reconciliation is "discrepancy", which is never the form's default). Which member of a pair is the practice case alternates between participants.

## 3. Measures

**Primary (headline, unassisted).** *Skill score* of the post-test, in [0, 1], read from the sandbox state and the saved note, not judged by the facilitator:
- cliff: calculators (of the two used) whose cliff panel was opened during the post-test, divided by 2 (the sandbox state is reset before each case, and `analyze.py score` computes it from the saved state);
- reconcile: 1 if the saved draft's reconciliation field equals "discrepancy", else 0.

Per participant, the **difference** d = score(coached skill) minus score(uncoached skill). Four values.

**Secondary, reported separately and labelled.**
- *Assisted speed*: practice-case seconds, coached minus uncoached, per participant.
- *Unassisted speed*: post-test seconds, coached minus uncoached.
- *Coach use*: nudges shown, followed, dismissed in coached blocks (counts, not rates; see section 7).
- *Ratings* (1 to 5, one question each, not averaged into anything): the help came at the right moment; the help interrupted me; I would want this at work.

A block that hits its time cap (practice 5 minutes, post-test 4 minutes) is scored as it stands and flagged `capped`.

## 4. Hypotheses

- **H1 (primary, directional, exploratory).** The mean of d is greater than 0.
- **H2 (descriptive).** Assisted practice time differs between coached and uncoached blocks. No direction is claimed; coaching may slow a first attempt.
- **H3 (descriptive).** Coached participants do not do worse unassisted than uncoached ones: all four d are at least 0.

Nothing is tested against a significance threshold. Decisions about wording (section 8) are fixed now.

## 5. Analysis

1. Check the design (`design_problems`): each participant has blocks 1 and 2, both skills, one coached and one uncoached block, and matches `assignments.json`. Problems are listed in the report, not silently fixed.
2. Compute the four per-participant differences d.
3. Report all four values, their mean, and a **95% t interval** on the mean (df = 3, so the multiplier is 3.18). The t interval assumes roughly normal differences, which four points cannot check; say so beside it.
4. Report the exact two-sided **sign-flip** p-value over all 2^4 sign patterns for completeness. Its smallest possible value is **0.125**, so it cannot reach 0.05 by construction.
5. Repeat steps 2 to 3 for assisted speed and unassisted speed, on their own rows of the report.
6. No pooling across opportunities (they are nested in people), no covariates, no model, no multiple-comparison adjustment because only H1 is primary.

## 6. Precision, stated in advance

With n = 4 the 95% interval half-width is **1.59** times the standard deviation of the differences. A paired t test at alpha 0.05 has 80% power only for a standardised effect of about **2.1** (power is about 29% at 1.0 and 75% at 2.0). Only a very large effect could show clearly; anything smaller will have an interval that includes zero. That is the expected outcome, and the report will say it.

## 7. Exclusions and deviations (decided before looking at outcomes)

A participant is excluded **entirely** (both blocks) only if, decided by the facilitator before looking at any scores:
- they have prior experience processing benefits claims (screening question), or
- a technical failure (a site crash, a `?glitch` response, the coach failing to start or failing to stop in the post-test) invalidates a block and the block cannot be repeated on a spare matched case within the session, or
- they stop before finishing both blocks.

No exclusion is based on a score, a time, or whether the result looks as hoped. Every exclusion is listed with its reason; excluded people reduce n, and every chart prints the n it actually has. Protocol deviations (a hint given, a block repeated, a cap hit) go in the `notes` column and are listed in the report. Nudge counts come from the coach's own log (coach_shown, coach_followed, coach_dismissed events), counted per block.

## 8. Reporting rules

- Every number carries its n ("n = 4 teammates") and its interval. Every chart says teammates, not target workers; synthetic households; sandbox calculators.
- The headline and assisted speed appear as separate items and are never summed, averaged or plotted on one axis.
- All four individual differences are shown as points.
- Wording is fixed in advance. If all four d are at least 0 and the interval excludes 0: "In all four participants the coached skill was shown at least as often unassisted as the uncoached skill; the interval is wide." If the interval includes 0 (expected): "Consistent with no effect and with a large effect; four people cannot tell." If any d is negative, the negative value is shown and named.

## 9. What we will NOT claim

- That the system works on real benefits work, real calculators, or real claimants.
- That novices become experts, or that the effect lasts beyond the session.
- Anything about people other than these four, or about the population they come from.
- Statistical significance, or that the study "validates" the product.
- An effect on speed: assisted and unassisted times are descriptive.
- That coaching beats a human trainer, or that it beats a different amount of practice.

## 10. Threats to validity (listed so they are not rediscovered later)

- Four people who know the project: demand effects, familiarity with what the coach looks for. The facilitator is the builder and cannot be blind.
- The "Check cliff edges" button is visible on every result page, so an uncoached person may find it unprompted; that is the baseline, but it makes the cliff score less sensitive than the reconcile score.
- Skill scores have few possible values (0, 1/2, 1 and 0, 1), so ties and ceilings are likely.
- Case version: pairs are matched by rule, not proven equivalent; alternating the practice/post roles between people does not remove a case effect, it spreads it.
- Time caps truncate slow participants and may hide skill they would have shown.
- Order and fatigue effects are balanced across conditions in expectation, not removed.

## 11. Data

`evals/study/results/participants.csv`, one row per participant and block, columns exactly as `analyze.COLUMNS`: participant, sequence, block, skill, condition, practice_case, post_case, practice_seconds, practice_capped, post_seconds, post_capped, post_checks_done, post_checks_possible, nudges_shown, nudges_followed, nudges_dismissed, exclusion, notes. Raw sandbox state per block goes in `results/raw/`. `analyze.py` writes `results/summary.json` (the `study` section of the Evidence page: meta with n, n_unit, split, interval level). No names: participants are P1 to P4; the key sits with the facilitator, off the repository.

## Amendment log

_None. Entries below are dated and never edit the sections above._
