# Proactive briefing: three cards at most, press to fire

> Knack prepares up to three cards when it has something worth saying, and does nothing until you press one. Zero cards is a normal answer.

**Capability:** Routines and automations · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (engine built and tested; development-set evaluation only; cards now arrive as rows in Needs you) · **Page:** `docs/features/proactive-briefing.md` · **Targets:** HRT, Wordsmith

## What it does

From routines, skill gaps, calendar and commit suggestions and agent results, Knack ranks what could be worth a card, shows at most three, and prepares the action behind each. Nothing fires unprompted: pressing a card is what starts anything.

## How it works

Four steps in code. Judge ranks candidates and prefers fewer, even zero. Verify re-checks each candidate against the current state and drops stale ones. Prepare builds the editable content from templates (a model may reword through the egress guard). Fire acts only on the worker's press: it either puts an approval item in the queue or starts a background run that only reads, never both unprompted. Each card carries a risk class and source tags. Acceptance is learned from the worker's reactions, starting from a prior of 0.4 for the role. The design idea (judge, prepare, execute on press, drop stale items) comes from the owner's notes on Sentient OS and was re-implemented in our own code and words.

**What is different.** Nothing fires unprompted, stale candidates are dropped before a card is drawn, and zero cards is a valid result.

## Where to see it

Needs you: a prepared action is a row. After a press the screen says what was made, for example 'Created an item here for your approval. Nothing runs until you approve it.'

## Demo moment

Press a prepared card in Needs you; the line says what it made and that nothing runs until you approve. Then open Background runs to show a read-only run that was started.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| The shipped judge: 101 of 124 cards were worth surfacing (precision 82% [70.4, 89.9]), recall 86% [75.5, 93.2]; against 55% [49.8, 60.5] for raw top three with no checks, 51% for random three and 46% [41.2, 49.9] for everything with no cap | synthetic, 145 replayed decisions over 35 people; bootstrap over people | `evals/report.md (Proactive cards)` |
| 145 briefings: cap of 3 cards, 0 cap violations, mean 0.86 cards; unprompted fires 0; unprompted agent spawns 0 | synthetic | `evals/report.md (Proactive cards)` |

## Honest limit

'Worth surfacing' is our definition, fixed before the runs, then revised after the first replays; there is no held-out data, so these are development-set figures. Acceptance learning is shown only on a simulated worker with fixed rates. All personas are synthetic. Whether real workers find the cards useful is unmeasured.

## Hackathon target

- **HRT (best use of data for predictions and decisions)**: a ranking decision with a hard cap, judged against three baselines
- **Wordsmith (most complicated end-to-end browser-use workflow)**: prepared actions that wait for a press

## 30-second spoken script

> Knack does not push. It prepares at most three cards when it has something worth saying: a routine to try, a skill to practise, a suggestion from your calendar or commits. It checks each one is still current, drafts the action, and then waits. Nothing fires until you press a card. In simulation the judge was right about eight in ten cards, and it made zero unprompted fires. Zero cards is a normal answer.

## Slide bullets

- At most three cards; fewer, even zero.
- Judge, verify, prepare, press to fire: nothing runs unprompted.
- Press either queues an approval or starts a read-only run, never both.
- Judge precision 82% against 46% for 'everything' (synthetic, 145 decisions).
- Development-set figures; no held-out data.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (14.6)`
- `docs/IDEA_BOARD.md (extensions)`
- `evals/report.md (Proactive cards, Limitations register)`
- `apps/dashboard/src/screens/NeedsYou/model.ts`
- `docs/reference-notes/computer-use-comparison.md`

## Related pages

`needs-you.md`, `routines.md`, `attention-router.md`
