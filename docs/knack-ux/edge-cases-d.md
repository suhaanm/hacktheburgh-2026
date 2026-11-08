# Edge cases: the worker's insight screens (Growth and its sections)

Track D. The data these screens draw can be empty, thin, huge, broken or odd. For each state: what the worker sees, and the test that proves it. A state is never a blank page, and never shows `NaN`, `undefined`, `null`, `Infinity` or `Invalid Date`. The Admin screens have their own matrix: `edge-cases-d-admin.md`.

Two kinds of test:

- `src/components/growth/edge-cases.dom.test.ts` renders each section for real (jsdom) with the state in the engine's answer and reads the text a person would read, closed disclosures opened. Every test also checks that no other person's id, no count of people, no "colleagues" and no group of "experts" appears.
- `src/lib/worker-strip.test.ts` pins the pure words: the headline sentences, the one-experienced-worker voice, the n of a group replaced by what the screen draws.
- `src/screens/Growth/growth-sections.dom.test.ts` renders the whole Growth page and applies the view-audit's firm and internals rules to all of its text, closed disclosures included.

## My steps against an experienced worker's

| State | What is shown | Test |
|---|---|---|
| No steps at all (empty ribbon) | the headline "Your steps appear here once Knack has seen you do this task." and an empty state; no chart | `steps: empty ribbon says so in words` |
| One case (the ribbon is always one case) | the case is the whole picture; the footer says "n: 1 case", never the engine's group size | `steps: the engine's group figure, its note and both person ids are never drawn`, `ownMeta: a unit about people becomes one case and the split is dropped` |
| NaN or missing seconds in a segment, NaN figure for the case | the segment counts as zero seconds; the figure is ignored and the ribbon's own columns are summed; no NaN anywhere | `steps: NaN seconds and a NaN figure for the case never reach the screen`, `stepsHeadline: uses the engine's own figure ... ignores NaN` |
| Negative gain (faster than the experienced worker) | "Your steps matched an experienced worker's on this case, with no time lost." Never "-45 s longer" | `steps: a negative gain ... says the steps matched`, `stepsHeadline: no time lost` |
| Under 5 seconds lost | the same "matched" sentence | `stepsHeadline: no time lost: the steps matched` |
| 10 000 segments | the ribbon lays out and stays finite, in under 15 s on a test machine; the rows list only the four biggest losses | `steps: 10 000 segments draw in a reasonable time and stay finite` |
| Very long or unicode step name | shown as words (underscores to spaces, first capital); the ribbon block shortens it to what fits | `steps: a very long and a unicode step name stay words` |
| A generator with no steps for the experienced worker | the worker's steps are named "only you did this"; the headline still names the biggest loss | `steps: a generator with no steps for the expert ...`, `describeColumn in the worker's voice` |
| The group wording (novice, expert, "average over all novices") | never drawn: lanes say "Experienced worker" and "You"; the column sentences say "you" | `describeColumn in the worker's voice`, `Growth: draws nothing a worker must not see` |
| The explanation names a group size ("Based on n = 24 people") | the number goes, the group stays: "Based on a group of people" | `Growth: draws nothing a worker must not see` (with the explanation run on example data), `noCounts` in `workerText` |
| The engine is down | the example case and the one "Example data" pill for the page; the section says where its numbers came from | `Growth: holds exactly one origin pill` |

## Where my time goes

| State | What is shown | Test |
|---|---|---|
| No calendar blocks and no hours | the headline "Your week and hours appear here once a calendar is connected." and "No calendar blocks this week" with what to do | `time: an empty week and no hours say so in words` |
| Null or NaN week figures | the plain headline "Your week against the expert's." (no number), no NaN | `time: null and NaN features fall back to a plain sentence` |
| A week in the future, years ago, or not a date | the label as given ("Week 2, 2031", "1999-W52", the text itself); never "Invalid Date" | `time: a week dated in the future, years ago or not a date ...` |
| A gap whose interval spans zero | "within noise", and "0 of 1 differences are clear"; never presented as a difference | `time: a gap row with an interval that spans zero ...` |
| 10 000 calendar blocks | the week table lists seven rows, then "Show all N"; the page stays small | `time: 10 000 calendar blocks list seven rows, then Show all` |
| Hours map with every bin at zero, calendar with no experienced-worker week | the hours sentence falls back; the second ribbon is left out; no NaN | `time: an hours map with every bin at zero ...` |
| No suggestions | "Nothing to suggest: your week is close to the experienced worker's"; the line that nothing is sent, booked or changed stays | `time: no suggestions says ...` |
| The engine lists other people, the experienced worker's id, a count of experts | none is drawn; the baseline is "An experienced worker's week"; the footer's note about the group is dropped | `time: never names another person or counts the experts ...` |
| Meeting sizes ("5 to 9 people") | the worker's own meeting sizes are their own data and are shown | exempted in the tests, as in the view audit |

## My commits (programmers)

| State | What is shown | Test |
|---|---|---|
| No repository registered, no habits | "Your commit habits appear here once a repository is registered." and "No commits to read yet" | `commits: no habits says a repository has to be registered` |
| NaN or null shares and intervals | "n/a" for a share or difference, "no interval" for an interval; never NaN | `commits: NaN and null shares and intervals never reach the screen` |
| 10 000 commits | "10,000 commits were counted." with a thousands separator | `commits: 10 000 commits are counted ...` |
| Interval spans zero | not flagged; the headline says no habit stands out | `commits: an interval that spans zero is not flagged` |
| Very long or unicode habit label | the label wraps over two lines in the chart; the table shows it whole | `commits: a very long and a unicode habit label stay words` |
| The plural "experts" and "the 8 experts" | never drawn: "an experienced worker" | `commits: the plural 'experts' ...`, `oneExpert` |
| A role that is not a programmer | the section is not on the page unless the address names it | `Growth: My commits is for programmers` |

## How my routines connect

The graph belongs to its own track (embedded, no title, no badge). It has its own edge-case tests: `src/screens/Graph.dom.test.ts`. Nothing mapped yet reads "Nothing is mapped yet. Knack adds things as it sees your work."

## My progress

The growth model's states (empty, early, ready, plateau, sparse, deleted record) are pinned in `src/components/growth/model.test.ts` and `engine-contract.test.ts`. The Limits no longer print the composite's weights, the engine's caveat about other learners, or the unrun-study sentence: the worker's limit is "This is an example, not your work. The method has not been tested on real people yet." (`model.test.ts: origin and limits`).

## The page

| State | What is shown | Test |
|---|---|---|
| A section is named in the address | it scrolls into view and opens; the others stay closed | `Growth: opens the section the address names` |
| One origin pill | one for the whole page, "Example data" when any section is showing example data | `Growth: holds exactly one origin pill` |
| One section fails to load | that section says so and offers "Try again"; the others still draw | each section draws its own error state (`StepsSection`, `TimeSection`, `CommitsSection`) |
