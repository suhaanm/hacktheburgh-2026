# Growth and the independence score

> One curve answers whether you need less help than before. It measures help needed, not expertise.

**Capability:** Growth and independence · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (built; evaluated on simulated learners; no person has used it) · **Page:** `docs/features/growth-independence.md` · **Targets:** HRT, G-Research

## What it does

Knack counts the steps you finished with no accepted cue and shows the trend with its interval. The screen says what it measures: help needed, not expertise. Work done for you, such as overnight automations, never changes the score.

## How it works

An assist ledger holds one row per assist episode with enums and numbers only: no text and no screenshots. Three streams are kept apart: assist (feeds the score), delegated and automation (shown as offloaded work, never in the score). Independence is the share of the last 20 occurrences of a skill finished with no accepted cue, with a Wilson lower bound. The help-need trend is a Theil-Sen slope with a bootstrap interval. Gap closure compares seconds lost with the first five occurrences, and retention counts unaided success on the first occurrence three or more days after being taught. A composite from 0 to 100 exists (weights stated as assumptions) but the headline is the trend. Dismissing a cue without completing the step is not independence; an error is penalised. The curve starts after 10 steps.

## Where to see it

Growth in the sidebar: a one-sentence title, one chart with its band, skills as rows, and closed disclosures (The fade, Your ledger, What Knack did for you). Export and delete are in Your data.

## Demo moment

Open Growth: 'You need help less often than you did.' One chart, one band, and the printed line 'Measures help needed, not expertise.' Open About this data to show n, the interval and the window. Until a worker has a ledger of their own it shows an example learner, badged Example data (docs/drafts/DEMO_SCRIPT.md, beat 4; confirm before the demo).

## Evidence and its label

| What | Label | Source |
|---|---|---|
| The composite overstates mastery for learners who do not improve and rises 10 points or more in about a third of them; independence and the trend are the evidence, and the trend has low power | synthetic, 240 simulated learners with planted curves | `evals/report.md (Limitations register, cue-score-composite, and Cue analysis)` |
| A planted independence rise was selected as a pointer in 47 of 100 worlds (target 0.8: missed); false celebration when errors rise 14 of 100 (target 0) | synthetic, 100 planted worlds per effect | `evals/insights/results/heldout.json` |

## Honest limit

No person has used it. The claim is 'needs less help', never 'became an expert'. The composite is experimental and in no headline. The insights engine finds only about half of the planted independence rises, so Growth may show a rise that Home does not mention.

## Hackathon target

- **HRT (best use of data for predictions and decisions)**: a measured trend with an interval, not a single score
- **G-Research (make the invisible visible)**: learning made visible

## 30-second spoken script

> Growth answers one question: do you need less help than you did? It counts the steps you finished with no accepted cue and draws one curve with its uncertainty. It measures help needed, not expertise, and it says so on the screen. Work an agent did for you overnight never changes the score. The screen shows example data until you have ten steps of your own, and no person has used it yet.

## Slide bullets

- One chart: share of steps finished with no accepted cue, with its band.
- Printed limit: measures help needed, not expertise.
- Overnight and delegated work never move the score.
- Dismissing a cue without finishing the step is not independence.
- Simulated learners only; the planted-rise recall is 47 of 100 (target 0.8, missed).

## Sources

- `docs/REQ7_PLAN.md (section 5)`
- `docs/knack-ux/04-growth.md`
- `evals/report.md (Cue analysis, Limitations register)`
- `evals/insights/results/heldout.json`
- `docs/KNACK_UX.md (section 3)`
- `docs/drafts/DEMO_SCRIPT.md (beat 4)`

## Related pages

`cue.md`, `live-coach.md`, `home-insights.md`, `your-data.md`
