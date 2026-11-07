# Home and the top insights

> Home is one sentence and one action. Behind it a deterministic engine picks the few things worth saying, and 'nothing stands out' is a valid answer.

**Capability:** Insights and admin · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Home: one sentence, one action, Top insights engine: a few pointers, chosen by code.

## Home: one sentence, one action

**Status:** built (merged to main; measured on a prototype; owner has not used it) · **Page:** `docs/features/home-insights.md` · **Targets:** G-Research

### What it does

Home shows one sentence about the worker's week, one action and at most two quiet rows. No chart, no table, no paragraph. If an approval is blocking a job, it takes the top slot instead.

### How it works

The hero is the top pointer written from a fixed template: 'On {step} you usually take about {n} {unit} {longer or less} than the expert.' At most 16 words and one quantity. 'Why this?' opens the method (fixed rules, not a model), the interval, n and where the data came from. Something the worker must decide outranks something they could learn. When there is nothing, the screen says so in five words.

### Where to see it

Home, the first item in the sidebar and the page Knack opens on.

### Demo moment

Open Knack: the date, one sentence with its origin badge ('Synthetic data' for an engine answer from synthetic people, 'Example data' for a fixture), the button 'See where the time goes' and, if anything waits, one row '1 thing needs you'.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Words above the fold on Home fell from 173 to 47 (the sidebar from 51 words of hints to 17 words in all) and controls from 10 to 4 | design measurement of a static prototype (one browser, no users) | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

### Honest limit

The 47 words are the prototype's headline content; real screens land a little above it. The example sentence comes from the synthetic firm and carries its origin badge (Example data or Synthetic data). These are measurements of the interface, not of people.

### Hackathon target

- **G-Research (make the invisible visible)**: the one thing worth seeing, said once

## Top insights engine: a few pointers, chosen by code

**Status:** built · **Page:** `docs/features/home-insights.md` · **Targets:** G-Research, HRT

### What it does

Each week, a deterministic engine picks at most three pointers for a worker and a short list for an admin. A weak insight is suppressed, not shown weakly.

### How it works

A fixed list of candidate kinds (for example time lost on a habit, a habit improved, an independence milestone, a skill due for retention practice, a relapse, an automation opportunity). Each candidate must pass a reliability gate (minimum occurrences, an interval that excludes zero, an effect size and a sign that persists over weeks), then a family-wise control for the number of comparisons, guard metrics (faster but with more errors is a trade-off, never a celebration), diversity and caps. Text comes from a fixed template. Admin groups under 5 people are never compared. Output is deterministic: the same input twice, or shuffled, gives the same answer.

### Where to see it

Home (the hero and quiet rows); the Monday note is built from the same pointers (its palette row is specified, not yet on main); Firm for admins.

### Demo moment

Show the 'Nothing stands out this week' state next to a week with a pointer, and say that silence is a result.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| False insights on null data: 0.0037 per worker-week [0.0027, 0.0047] (62 of 16,800 person-weeks, 2,400 people; target at most 0.05: met); admin 0 of 160 admin-weeks over 40 firms (target at most 0.10: met) | synthetic firms of 60 people, held-out seeds, run once | `evals/insights/results/heldout.json` |
| Planted time loss of 15, 30 and 60 seconds selected in 99, 100 and 100 of 100 worlds; improvement 86; relapse 82; retention 100; trade-off 81; independence rise 47 (target 0.8: missed); false celebration when errors rise 14 of 100 (target 0: missed) | synthetic, 100 planted worlds per effect | `evals/insights/results/heldout.json` |
| Admin situations recovered at the gate on held-out seeds (target at least 9 in 10): plateau unit 29 of 40, programmer bottleneck 9 of 19, Simpson's-paradox role 19 of 40; 127 of 996 empty worker lists hid a planted effect | synthetic | `evals/insights/results/heldout.json` |
| No k-anonymity violation across 11 firms; 21 of 21 edge cases pass; top-3 sets stay stable when 5% of rows are dropped (Jaccard 0.88; admin top-7 0.93; target 0.8) | synthetic | `evals/insights/results/heldout.json` |

### Honest limit

Targets were fixed before the held-out run and several recall targets were missed and reported. The planted worlds are ours; the 100 planted worlds per effect do not use the seed list, so they are the same on dev and held-out. A person with more than three real effects cannot see them all.

### Hackathon target

- **G-Research (make the invisible visible)**: a few well-chosen things made visible, with silence as a valid answer
- **HRT (best use of data for predictions and decisions)**: selection under multiple comparisons with a stated false-insight rate

## 30-second spoken script

> Home is one sentence and one action: the one thing in your week most worth knowing. Behind it is an engine that picks at most three pointers, in plain code, with the template wording fixed. It would rather say nothing than say something weak: on data with nothing in it, it made a false pointer for about one worker-week in three hundred. It missed some planted effects, and we published which ones.

## Slide bullets

- Home: one sentence, one action, at most two quiet rows.
- Words above the fold 173 to 47 (prototype measurement).
- Insights chosen by code: reliability gate, comparison control, guard metrics.
- False insights on null data 0.0037 per worker-week (synthetic, held-out).
- Missed: independence rise 47 of 100 (target 0.8); reported.

## Sources

- `docs/KNACK_UX.md (section 4)`
- `docs/knack-ux/01-home.md`
- `docs/INSIGHTS_DESIGN.md`
- `evals/insights/results/heldout.json`
- `evals/insights/PLAN.md`
- `docs/knack-ux/after/after-measurements.json`

## Related pages

`firm-admin.md`, `growth-independence.md`, `evidence-and-explain.md`
