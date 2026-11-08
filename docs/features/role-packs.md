# Role packs

> One deep role (UK benefits processor) and two that started thin and are now at standard depth (data analyst, programmer), so Knack is not a benefits tool with the name changed.

**Capability:** Roles · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Role packs: the format, and the deep benefits processor pack, Programmer pack at standard depth, Data analyst pack at standard depth.

## Role packs: the format, and the deep benefits processor pack

**Status:** built · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

### What it does

A role pack turns raw events into steps, says what an expert does, which actions need a click, what tone to use, which routines to look for and what to teach in what order. The benefits processor pack is deep; the data analyst and programmer packs started as thin starting points and were raised to standard depth (the next two entries).

### How it works

A pack is a validated folder (id, onboarding questions for tools, risky actions, tone, pace and hours; extra step types and their mapping from events; expert steps with allowed reorderings; risk classes with label patterns; routine templates; a curriculum; persona parameters; priors for pooling). The benefits pack also has an oracle, task configuration and sandbox sites. The data analyst and programmer packs fill every key but the oracle, tasks and the full expert policy of the benefits pack, and differ visibly in questions, steps, risk classes and tone: the programmer's risky actions are force-push, deleting a branch, merging to main and publishing; the benefits processor's are submitting a case, issuing a payment and sending a letter. A loader checks packs against a JSON Schema and the pack format reserves a slot for plugin references.

**What is different.** A role is a validated folder of data (steps, expert policy, risk classes, tone, routines, curriculum), so adding a job is adding data, and the thin packs differ visibly in their risky actions.

### Where to see it

First run (the role cards and 'Not sure yet'), the account menu (Change profile changes the name and the role; Set up again reruns first run), and the Admin Roles view.

### Demo moment

At first run, choose each of the three cards; show how the four lines on the 'what Knack will remember' screen differ (tools, never-without-me actions, hours).

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Pack format and loader covered by 66 test functions; packs validate against the schema | offline tests (static count) | `evals/report.facts.json (tests.by_dir, packages/packs/tests)` |
| Thin roles on harder synthetic generators: routine finder raw precision 88 to 98%, recall 60 to 92%, proposal precision 100%; git habits for the programmer: precision 116 of 116, recall 116 of 120 | synthetic | `evals/report.md (Findings, and Git habits)` |
| Stuck model: the accepted v2 improvement qualifies for benefits processor and programmer; no variant qualified for data analyst | synthetic, held-out | `evals/mlv2/results/heldout_hazard.json` |

### Honest limit

The data analyst and programmer packs are written from the job and have not been validated on real work. Genome recovery was not evaluated for them because the named-deficit labels belong to the benefits pack. Even the deep pack has no real benefits-processor data behind it. Both were raised to standard depth, which is on main since 01:15 UTC (next two entries).

### Hackathon target

- **G-Research (make the invisible visible)**: the same lens on three different jobs
- **Wordsmith (most complicated end-to-end browser-use workflow)**: one workflow deep, two shallow

## Programmer pack at standard depth

**Status:** built (ROLE-DEPTH (Track F), merged to main at 01:15 UTC (08b9908); docs/roles/programmer.md and packages/packs/programmer are on main; no study and no real traces; not seen end to end by the lead; additive only (D55, D56 item 6)) · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

### What it does

The programmer role gets full content for the whole job: 22 step types (10 from the first release, 12 added), 18 coached skills with hints at three levels, 4 critical gates and 13 routine templates. It is written from the job and not validated with people.

### How it works

Each skill has a hint at L1 (a question), L2 (a few words) and L3 (a nudge); L4 is silence. Four gates are spoken for only when the next step has started without them: reproduce before you bisect, write the commit message before you open the pull request, read CI before you answer the review, watch the release before you roll back. Capture is event type plus a zone name only (for example ci_checks or rollback_control), never page text, URLs or values. Thirteen routine templates are opt-in, one at a time, each stating what its own worst action does and its share of judgement steps; three are held back by rule and never proposed (review queue triage, rollback after an alert, replying to review comments); nothing merges, deploys, rolls back, force-pushes or deletes without the worker's own click. Onboarding asks five more questions (team size, review frequency, on-call, release cadence, how often to prompt), which set the prompt budget and add risk patterns, and it suggests connection presets by id, only as suggestions.

**What is different.** Additive only: new optional steps on new step types, so nothing already measured changes; four gates are spoken for only when the next step has started without them, and irreversible actions always wait for the worker's click.

### Where to see it

First run (the Programmer role card), Routines (the repeat list), Growth 'My commits' and the coach in the sandbox; the pack's own page is docs/roles/programmer.md.

### Demo moment

The edge you did not try (sandbox task 'Wrong number of pages'): the fix passes the visible tests and misses a hidden edge; the coach rings the console and asks what happens at empty, one item, exactly full, one past the end. Or 'Re-run the failed build for me': a planted routine appears in the repeat list, reads the log, re-runs the job and stops before any merge or deploy; the worker clicks Automate.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Only three skills have been run, in a sandbox with simulated participants; the twelve new step types, their hints, the new templates and follow-up mappings have no synthetic traces and no study, so screens show 'not enough data' for them, never a number | simulated participants (language model), not people; the rest not run | `docs/roles/programmer.md` |

### Honest limit

Written from the job, not validated with people. The selectors for real tools (GitHub and GitLab pull requests, CI dashboards, logs, release consoles) are best-effort and not tested against live sites. Dwell priors are expert medians written into the pack, not measured. Minutes, cost and risk on a routine are illustrations (a flat 15 pounds an hour is a placeholder). Judgement shares come from an authored list. The pack suggests connection presets by id, including linear, which is not among the 13 preset files on main (it has jira).

### Hackathon target

- **G-Research (make the invisible visible)**: the same lens on a second job
- **Wordsmith (most complicated end-to-end browser-use workflow)**: a second workflow with irreversible steps behind the worker's click

## Data analyst pack at standard depth

**Status:** built (ROLE-DEPTH (Track F), merged to main at 01:15 UTC (08b9908); docs/roles/data-analyst.md and packages/packs/data-analyst are on main; no study and no real traces; not seen end to end by the lead; additive only (D55, D56 item 6)) · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

### What it does

The data analyst role gets full content for the whole job: 21 step types (10 from the first release, 11 added), 16 coached skills with hints at three levels, 6 critical gates and 13 routine templates. It is written from the job and not validated with people.

### How it works

Hints state the assumption and the check ('Is the key unique on both sides, and how many rows should the join return?'). Six gates are spoken for only when the next step has started without them, for example trace the source before you join, set the grain before you check the scale, check the scale before you state the uncertainty, and run it clean before you parameterise or schedule it. Capture is event type plus a zone name only (lineage_view, join_panel, schedule_panel), never query text, URLs or values; row-level, personal and credential-like fields produce no event at all. Thirteen routine templates are opt-in, one at a time; three are held back by rule (magnitude and units check, sending a peer check, schedule a refresh with an alert, because turning a recurring job on is always the worker's decision); nothing drops, overwrites, publishes, schedules or sends without the worker's own click. Onboarding asks five more questions (where the data comes from, team size, whether anyone checks the numbers, refresh frequency, prompt frequency) and suggests connection presets by id.

**What is different.** Additive only, with hints that state the assumption and the check; a standing rule keeps scheduling a recurring job always the worker's decision.

### Where to see it

First run (the Data analyst role card), Routines (the repeat list) and the coach in the sandbox; the pack's own page is docs/roles/data-analyst.md.

### Demo moment

The total that does not match (sandbox task 'Net sales against the ledger'): the table averages every order, cancelled ones too, while the ledger counts completed ones; the coach asks whether the total matches the figure the finance system holds. Or 'Refresh the weekly metrics for me': a planted routine runs the saved query, pastes the rows, refreshes the chart and stops before any publish.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Only three skills have been run, in a sandbox with simulated participants; the eleven new step types, their hints, the new templates and follow-up mappings have no synthetic traces and no study, so screens show 'not enough data' for them | simulated participants (language model), not people; the rest not run | `docs/roles/data-analyst.md` |

### Honest limit

Written from the job, not validated with people. Selectors for real warehouse consoles, notebooks, spreadsheets and BI tools are best-effort and not tested against live sites. Dwell priors, routine minutes and costs and judgement shares are authored, not measured. The pack suggests connection presets by id, including sheets and linear, which are not among the 13 preset files on main (it has google_workspace and jira). No stuck-model variant qualified for this role.

### Hackathon target

- **G-Research (make the invisible visible)**: the same lens on a third job
- **Wordsmith (most complicated end-to-end browser-use workflow)**: a third workflow, with a standing rule that scheduling is always the worker's decision

## 30-second spoken script

> Knack is not just a benefits tool. A role pack tells it what an expert does in a job, which actions always need a click, and what to teach in what order. We built one deep pack, a UK benefits processor, and two thin ones, a data analyst and a programmer, which differ visibly in their questions and risky actions. Both thin packs have now been filled out to standard depth: the programmer with twenty-two steps and four gates, the analyst with twenty-one and six. They are written from the job, not validated with people, and the new steps say not enough data until there is data.

## Slide bullets

- A pack: steps, expert policy, risky actions, tone, routines, curriculum.
- Deep: UK benefits processor. Data analyst and programmer started thin and are now at standard depth.
- Different risky actions per role: force-push and merge for programmers, submit and pay for benefits.
- Programmer: 22 step types, 18 skills, 4 gates, 13 routines; analyst: 21, 16, 6, 13.
- Written from the job, not validated with people; new steps have no traces and say not enough data.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (6.3)`
- `packages/packs/benefits-processor/pack.yaml`
- `packages/packs/programmer/pack.yaml`
- `docs/SPEC_LIST.md (D4)`
- `docs/DECISIONS.md (D55, D56 item 6)`
- `evals/report.md`
- `docs/roles/programmer.md`
- `docs/roles/data-analyst.md`
- `packages/packs/data-analyst/pack.yaml`

## Related pages

`connections.md`, `knack-shell.md`, `firm-admin.md`
