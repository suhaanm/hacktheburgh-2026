# Data separation: Growth and its sections (Track D)

The checklist from `docs/knack-ux/views.md`, section "Data separation checklist for each screen owner", done for the worker's insight page. Each field the screen draws is marked **own** (the worker's own work), **baseline** (ONE experienced worker's way of doing the task, unnamed, never an average of colleagues, never a count of them), **firm** (never drawn on a worker screen) or **internal** (never drawn on a worker screen). A worker view draws only own and baseline.

How it is enforced, in code and in tests:

- `src/lib/voice.ts`: `oneExpert` (the group of experts becomes "an experienced worker"), `noCounts` (a group's size leaves the sentence; "2 of 10 learners" becomes "2 in 10 cases"), `isCohortFact` and `restsOnCohort` (facts and sentences about the group are dropped), `safeWhy` (an engine reason that names people is replaced by a plain sentence).
- `src/lib/ownMeta.ts`: the engine's n of a group ("24 people") is swapped for what the screen draws (one case, one week, N commits); a footer note that describes how the group was made is dropped.
- `src/components/growth/GrowthSection.tsx`: `SectionError` never prints the engine's own message; one origin pill for the page.
- Tests: `src/screens/Growth/growth-sections.dom.test.ts` renders the whole page and applies the view audit's firm and internals rules to every character of text, closed disclosures included; `src/components/growth/edge-cases.dom.test.ts` and `src/lib/worker-strip.test.ts` pin the words. `scripts/view-audit.mjs` (Track R) runs the same rules on the live pages and the API responses.

## My progress

| Field | Class | Note |
|---|---|---|
| The independence curve, its interval, the "first 5" baseline | own | the worker's own steps |
| Skills and their direction ("less help") | own | |
| The fade (help level over time) | own | |
| Your record (export and forget) | own | the word "ledger" is only in Settings, Advanced |
| What Knack did for you (delegated and overnight work) | own | |
| n in "About this data" | own | "N steps" |
| Limits | own | the composite's weights, the engine's caveat about other learners and the unrun-study sentence are not printed; the example line says "This is an example, not your work. The method has not been tested on real people yet." |
| The trend power note | own | speaks in cases ("2 in 10 cases"), not in learners |
| Composite score and its caveat | internal | closed, experimental, counts removed |

## Where my time goes

| Field | Class | Note |
|---|---|---|
| Your week's blocks (kind, time, size of the meeting) | own | meeting sizes are the worker's own calendar |
| An experienced worker's week | baseline | titled "An experienced worker's week", no person id |
| The gap rows (you, experienced worker, difference, interval) | own and baseline | the "Experts range from" column (a spread across experts) is not drawn |
| Distance and out-of-step minutes | own and baseline | the placebo (expert against expert), its n of experts and the nearest expert's id are not drawn |
| Ideas for a calmer week | own | templated; the experienced worker's numbers are the baseline |
| Working hours map, idle capacity, will the window last, quiet hours | own | the worker's own settings, saved by the worker's own click |
| The list of people with a calendar, the week picker | firm | not called in the worker view |
| Footer n and note | own | "n: 1 week"; the note about how the expert reference was made is dropped |

## My steps against an experienced worker's

| Field | Class | Note |
|---|---|---|
| The ribbon: the worker's case against one experienced worker's trace | own and baseline | lanes read "You" and "Experienced worker"; no person id |
| Seconds lost per step, the four biggest | own | |
| What skipping a step costs (sandbox households) | baseline | households in the sandbox, not people |
| Explain this case | own | only own-case facts: every fact and sentence that rests on a group figure is left out; "n = 24 people" becomes "a group of people" |
| The group's mean gap, its bootstrap interval, the controls (placebo, null), the waterfall | firm | not drawn |
| The reference choice (nearest expert or consensus), "Average over all novices", the transition graph of all novices | firm | not drawn |
| The case's person id, the expert's person id | firm | not drawn |

## How my routines connect

| Field | Class | Note |
|---|---|---|
| The worker's own routines, skills and notes as a graph | own | Track G's component, embedded, names only on hover, focus or click |

## My commits (programmers)

| Field | Class | Note |
|---|---|---|
| The worker's commit habits (shares of their own commits) | own | counts and shares only, no message, file name or author |
| The experienced worker's share per habit | baseline | "Experienced worker", never "the experts" |
| n commits | own | "10,000 commits were counted" |
| The learner list, the repository list, the number of experts, the reference note | firm | not drawn |

## What no worker screen of mine draws

Models, model names, cost, tokens, latency, routing, the call list, evidence tables, the limitations register, hashes and run ids. Models and Evidence are Admin More rows; a worker who opens them by address sees only the Admin gate sentence.
