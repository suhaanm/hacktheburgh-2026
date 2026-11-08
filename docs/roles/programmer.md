# Programmer on Knack

Role pack `programmer`, depth `standard`: full content for the whole job, **written from the job, not validated with people**. The only parts that have been run are three skills in a sandbox, with simulated participants (language model), not people. Facts below come from `packages/packs/programmer/`. Anything that is a guess is marked as one.

## Who they are

An engineer who reads code and logs, makes small changes, and gets them reviewed and merged without breaking the build. The pack is written for someone in their first year or two on a team: the person who has been told "reproduce it first" and "read your own diff" and does not yet do it every time. A senior engineer shows up in the data as the expert reference, not as the user.

## A day in their work (the pack's expert week, hand-authored, not measured)

Stand-up at 10:00 (15 minutes). Deep work from 10:30 to 12:30, the protected block for debugging and design. Lunch away from the desk at 13:00. Meetings only in the afternoon: planning on Monday, a 1:1 on Wednesday, a retro on Thursday. A pull-request review slot from 16:00 to 16:45. The calendar layer reads this to say when a meeting lands in the peak-focus window; it never reads titles or attendees.

## The cogs, and where novices lose time

Knack turns events into **cogs**: short, named stretches of work. Twenty-two for this role: ten from the first release, twelve added for the rest of the job. "Where novices lose time" is a **hypothesis from the job** for every cog except the three with a sandbox study (marked *study*).

| Task family | Cog | The work | Where a novice loses time (hypothesis) |
|---|---|---|---|
| fix a failing build | READ_TRACE, READ_CODE, EDIT_CODE, RUN_TESTS, COMMIT | read the failure, change one thing, run, commit | edits before reading the trace; re-runs without reading |
| (same) | PROBE_EDGE *study*, INSPECT_INPUT *study*, WRITE_TEST *study*, REVIEW_DIFF *study*, SEARCH_DOCS | edges, real inputs, failing test first, read the diff, look it up | skips the edge; trusts the visible tests; commits unrelated lines |
| find the regression | REPRODUCE_LOCALLY, BISECT_CHANGE | make it fail on your machine, halve the history | fixes by guessing instead of halving |
| add observability | ADD_LOGGING | a log line with ids where the failure hides | fixes it and leaves nothing for next time |
| ship a change | WRITE_COMMIT_MSG, OPEN_PR, READ_CI, ANSWER_REVIEW | message, pull request, CI, review replies | vague message; one huge pull request; asks for review before reading CI |
| review a pull request | REVIEW_PEER | review a colleague's change | approves without reading the diff |
| release and watch | WATCH_PROD, ROLL_BACK | watch the first ten minutes, roll back one step | walks away; rolls back without looking |
| speed up a hot path | PROFILE_HOTPATH | find the widest bar first | optimises by hunch |
| change the schema safely | WRITE_MIGRATION | small steps with an undo | one irreversible step |

## What Knack watches

L0 only: **event type plus a zone name** (for example `ci_checks`, `prod_logs`, `rollback_control`). No page text, no URL, no field value. Zones come from element selectors in the pack's capture config for GitHub and GitLab pull requests, CI dashboards, log and error-tracking tools, release consoles, a profiler, a database console and hosted dev environments, plus the tested sandbox. **The selectors for real tools are best-effort and not tested against live sites.** Commit message, review and pull request boxes are deliberately not on the sensitive list, so that writing them is visible at all; their text is still never read.

What it cannot see: ADD_LOGGING has no distinct control in an editor, so it shows only where a tool or `data-understudy-zone` marks one (zone `logging_panel`). In a terminal, REPRODUCE_LOCALLY and RUN_TESTS look alike; the order disambiguates. Whether a log line holds ids or values, or a migration has an undo, is not visible.

## What it coaches

Eighteen skills, each with a hint at L1 (a question), L2 (a few words) and L3 (a nudge); L4 is silence. The hints are terse and ask, never answer ("Can you make this fail on your own machine, with one command, before you change anything?"). Twelve checks are new and optional, in task families, and four are **critical gates**: reproduce before you bisect, write the message before you open the pull request, read CI before you answer the review, watch the release before you roll back. A gate is spoken for only when the next step has started without it. The Cue prompt is a label of at most 32 characters and a reason of at most 12 words ("Next: Reproduce it locally. A failure you can repeat on your machine is half fixed.").

## What it automates

Thirteen routine templates, every one opt-in and one at a time. Each carries what its own worst action does (`irreversibility`), its share of judgement steps, its steps in plain words and the tools it would use. Held back by rule, never proposed: **review-queue-triage** (judgement on every pass), **rollback-after-alert** (irreversible), **reply-to-review-comments** (outward and judgement). Proposed with a stop: open a draft pull request (never requests review or merges), check CI on my pull requests (read only), watch the logs for ten minutes (never rolls back or deploys), bisect a range, dry-run a migration on a scratch copy (never the real database), and the original re-run of a failed CI job. Nothing here merges, deploys, rolls back, force-pushes or deletes without the worker's own click.

## Tools it connects to

Onboarding asks five more questions after the usual five: team size, how often they review, on-call, release cadence and how often they want a prompt. The answers set how many prompts a day Knack allows and how long it waits for a quiet moment, add risk patterns (a rollback always needs the worker's own click), and decide which connections to suggest. Suggestions only, by preset id; the connections layer resolves them and nothing connects until the worker says so. Git host and CI suggest `github`; chat `slack`; the issue tracker `linear`; logs and error tracking `sentry`; a database console `postgres`; an on-call rota or daily releases add `sentry` and `slack`.

## Three demo moments

1. **The edge you did not try** (sandbox task "Wrong number of pages"). The fix passes the visible tests and fails the hidden edge. The coach rings the console and asks "what happens at the edges: empty, one item, exactly full, one past the end?". Measured pipeline, simulated participants.
2. **One clean commit** (sandbox task "Fix it, commit only the fix"). The coach asks "is every line in this diff part of the fix, and nothing else?" before the commit.
3. **Re-run the failed build for me** (planted routine `rerun-failed-ci`, synthetic data). It appears in the repeat list, reads the log, re-runs the job and stops before any merge or deploy; the worker clicks Automate.

## Honest limits

- The twelve new cogs, the twelve new skills' hints, the 12 new templates, the habits and the follow-up mappings have **no synthetic traces and no study behind them**. Dashboards and the engine show "not enough data" for them, never a number. Dwell priors are the expert medians written into the pack and are not measured.
- Minutes, build cost and risk on a routine are illustrations (a flat £15 an hour is a placeholder, not a claim about this role).
- Judgement shares are computed from an authored list of judgement cogs; they are definitions, not findings.
- The sandbox study used language-model participants. It says nothing about whether people learn from the hints.
- No claim that novices become experts. The claim is that Knack shows where a novice loses time against an expert, coaches that step with help that fades, and takes over only what the worker opts into.
