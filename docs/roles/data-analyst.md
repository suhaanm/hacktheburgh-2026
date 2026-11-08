# Data analyst on Knack

Role pack `data-analyst`, depth `standard`: full content for the whole job, **written from the job, not validated with people**. The only parts that have been run are three skills in a sandbox, with simulated participants (language model), not people. Facts below come from `packages/packs/data-analyst/`. Anything that is a guess is marked as one.

## Who they are

Someone who pulls numbers from a warehouse, checks them, and turns them into charts and reports that other people rely on. The pack is written for an analyst in their first year or two: fluent enough to get a number out, not yet in the habit of asking where it came from, what one row is, how sure it is, and whether it still runs next week. A mistake here does not break a build; it quietly changes someone else's decision, which is why the pack's tone is detailed and states the assumption and the check.

## A day in their work (the pack's expert week, hand-authored, not measured)

Stand-up at 08:30 (15 minutes). A protected analysis block from 09:00 to 11:30. Lunch away from the desk at 12:15. Stakeholder syncs batched into Tuesday and Thursday afternoons, a weekly metrics sync on Monday, a client call on Wednesday, and a metrics review slot at 16:00. The calendar layer reads this to say when a meeting lands in the focus window; it never reads titles or attendees.

## The cogs, and where novices lose time

Knack turns events into **cogs**: short, named stretches of work. Twenty-one for this role: ten from the first release, eleven added for the rest of the job. "Where novices lose time" is a **hypothesis from the job** for every cog except the three skills with a sandbox study (marked *study*).

| Task family | Cog | The work | Where a novice loses time (hypothesis) |
|---|---|---|---|
| refresh a metric | LOAD_DATA, WRITE_QUERY, RUN_QUERY, INSPECT_RESULT, PLOT, EXPORT_RESULT | get it, query it, read it, chart it, send it | trusts the total and never reads three raw rows |
| (same) | PROFILE_DATA *study*, CLEAN_DATA, RECONCILE_CONTROL *study*, GROUP_AGG *study* | profile, fix, compare with the control figure, cut by segment | skips the profile; reports a total that misses the control; averages across segments |
| analyse and check | TRACE_SOURCE, JOIN_TABLES, SET_GRAIN, CHECK_MAGNITUDE, QUANTIFY_UNCERTAINTY | where a field comes from, join, what one row is, scale and units, how sure | joins on a repeated key and multiplies rows; counts the wrong unit; a number off by ten |
| report a finding | WRITE_FINDING, PEER_CHECK | the finding with its caveat; a second check | a point estimate with no caveat; shares before anyone has checked |
| automate a refresh | MAKE_REPRODUCIBLE, PARAMETERISE_REPORT, SCHEDULE_REFRESH | rerun clean, make the week an input, schedule with an alert | pastes a number from one lucky run; retypes the week; schedules with no alert |
| define a metric | DOCUMENT_METRIC | write down the definition, source, owner, caveats | one metric, three definitions |

## What Knack watches

L0 only: **event type plus a zone name** (for example `lineage_view`, `join_panel`, `schedule_panel`). No page text, no query text, no URL, no field value. Zones come from element selectors in the pack's capture config for warehouse consoles, notebooks, spreadsheets and documents, BI tools, data catalogs and lineage viewers, a writing tool, plus the tested sandbox. **The selectors for real tools are best-effort and not tested against live sites.** Finding editors, metric descriptions and review boxes are deliberately not on the sensitive list, so that writing them is visible at all; their text is still never read.

What it cannot see: whether a join multiplied rows, whether the grain was right, what the finding says, whether an alert was set on a schedule. It sees that the step happened and for how long. Row-level, personal and credential-like fields are on the sensitive list and produce no event at all.

## What it coaches

Sixteen skills, each with a hint at L1 (a question that states the assumption and the check), L2 (a few words) and L3 (a nudge); L4 is silence ("Is the key unique on both sides, and how many rows should the join return?"). Eleven checks are new and optional, in task families, and six are **critical gates**: trace the source before you join or set the grain, set the grain before you check the scale, check the scale before you state the uncertainty and write the finding, write the finding before you ask for a check, run it clean before you parameterise or schedule it. A gate is spoken for only when the next step has started without it. The Cue prompt is a label of at most 32 characters and a reason of at most 12 words ("Next: Check the scale and units. A number off by a factor of ten looks fine until checked.").

## What it automates

Thirteen routine templates, every one opt-in and one at a time, each with what its own worst action does (`irreversibility`), its share of judgement steps, its steps in plain words and the tools it would use. Held back by rule, never proposed: **magnitude-and-units-check** (judgement on every figure), **send-peer-check** (outward and judgement), **schedule-refresh-with-alert** (a standing rule: turning a recurring job on is always the worker's decision). Proposed with a stop: reload and re-profile a dataset (read only), run the saved query for a new week, compare the total with the control and draft a one-line gap note, join and count rows (stops if the count grew), break a metric down by segment, add an interval to a rate, restart and run a notebook, draft a metric definition, export the weekly extract to an agreed sheet (never emails or shares wider), and the original weekly metrics refresh (never publishes). Nothing here drops, overwrites, publishes, schedules or sends without the worker's own click.

## Tools it connects to

Onboarding asks five more questions after the usual five: where the data comes from, team size, whether anyone checks their numbers, how often they refresh the same report and how often they want a prompt. The answers set how many prompts a day Knack allows and how long it waits for a quiet moment, and decide which connections to suggest. Suggestions only, by preset id; the connections layer resolves them and nothing connects until the worker says so. A SQL console and a warehouse as a data source suggest `postgres`; spreadsheets and exports suggest `sheets`; the request queue `linear`; a catalog or a writing tool `notion`; chat and "always checked" `slack`.

## Three demo moments

1. **The total that does not match** (sandbox task "Net sales against the ledger"). The table averages every order, cancelled and refunded ones too; the finance ledger counts only the completed ones. The coach asks "does your total match the figure the finance system holds? If not, what explains the gap?". Measured pipeline, simulated participants.
2. **Which campaign converts better** (sandbox task of the same name). The overall rates point one way and flip once the data is cut by device or customer type. The coach asks whether the overall number hides a difference between segments.
3. **Refresh the weekly metrics for me** (planted routine `weekly-metric-refresh`, synthetic data). It appears in the repeat list, runs the saved query, pastes the rows and refreshes the chart, and stops before any publish; the worker clicks Automate.

## Honest limits

- The eleven new cogs, the eleven new skills' hints, the twelve new templates, the habits and the follow-up mappings have **no synthetic traces and no study behind them**. Dashboards and the engine show "not enough data" for them, never a number. Dwell priors are the expert medians written into the pack and are not measured.
- Minutes, build cost and risk on a routine are illustrations (a flat £15 an hour is a placeholder, not a claim about this role).
- Judgement shares are computed from an authored list of judgement cogs; they are definitions, not findings.
- The sandbox study used language-model participants. It says nothing about whether people learn from the hints.
- No claim that novices become experts. The claim is that Knack shows where a novice loses time against an expert, coaches that step with help that fades, and takes over only what the worker opts into.
