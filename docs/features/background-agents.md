# Background agents and overnight runs

> A parent agent gives small, budgeted jobs to child agents in a sandbox. Code verifies every result. Overnight work waits for you in the morning.

**Capability:** Agents that do the work safely · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (landing).** The lead's views rule (`docs/knack-ux/views.md`, from owner requests 4.1, 4.2, 4.11, 4.12 and 4.17 at about 00:50 UTC) is reorganising where screens live. Where this page says 'More, <screen>', check `apps/dashboard/src/components/home/navModel.ts` on main for the final place. For a worker, background tasks and their results sit in Routines and are meant to update live without a refresh, and to show as small pills at the top right while they work (owner requests 4.15 and 4.21, landing); 'Background runs' is an Admin 'More' row.

This page covers Background agents: parent and child, Overnight runs and the morning report, Live background task list: a finish shows up without a refresh.

## Background agents: parent and child

**Status:** built · **Page:** `docs/features/background-agents.md` · **Targets:** Wordsmith

### What it does

While you work on something else, Knack can run helpers that profile a dataset, find test gaps in a repository or draft a weekly summary. Each helper has a budget, a sandboxed workspace and a result that code checks.

### How it works

A parent plans and hands typed specs to children, each following a written role playbook (exemplars exist for programming, data and creative work). In the default menu mode the model only sequences vetted steps by id; the analysis is done by scripts written in advance, so file text never reaches the model. Raw mode (free-form model-written code) exists only in the foreground, on files the worker named. Each child has step, token and time budgets, an isolated workspace, a lease that a child can only narrow, and results that code recounts from the source. Human input signalled from the desktop makes a child yield and write a checkpoint.

**What is different.** In the default mode the model only orders vetted steps by id and scripts do the analysis, results are recounted by code, and a child's lease can only narrow its parent's.

### Where to see it

More, then Background runs. Results arrive in Needs you.

### Demo moment

Start a data or programming helper and show its result card: the number, the evidence and a 'verified' mark that code, not the model, set.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Planted facts recovered and verified: data profile 6 of 6, data chart 6 of 6, commit analysis 4 of 4, test gap 1 of 1, refactor suggestion 1 of 1, weekly summary 3 of 3; false claims injected and caught 4 of 4 | synthetic fixtures, mock model, offline | `evals/report.md (Agent runtime)` |
| Stop call median 1.9 ms; stop to finished median 33 ms; kill flag to finished median 39 ms (max 97 ms); human input to yielded median 30 ms; all within 1 s in 8 of 8 trials | synthetic, measured on a busy laptop | `evals/report.json (runtime, stop)` |
| Isolation: 21 attempts to write outside the workspace (traversal, absolute path, symlink, hard link, credential names, sandboxed scripts); 0 succeeded | synthetic, offline | `evals/report.json (runtime, isolation)` |
| Long-horizon runs: 9 of 9 completed and verified (Wilson [0.70, 1.00]); 2 injected false claims caught | synthetic fixtures | `evals/report.json (runtime, headline)` |

### Honest limit

Every fixture is synthetic with planted facts. Menu mode shows a model can plan and drive a menu, not that it can analyse data. The detector paused 6 of 7 planted injections in the runtime test (none obeyed). One live smoke run per task is not a benchmark.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: parent and child agents with budgets, isolation and code-verified results

## Overnight runs and the morning report

**Status:** built · **Page:** `docs/features/background-agents.md` · **Targets:** Wordsmith, HRT

### What it does

A routine the worker opted in for can run while they are away, then leave one summary for the morning. Irreversible steps still wait for a click.

### How it works

The engine's presence model says whether a window is likely long enough and the machine is unlocked; the agent service starts a checkpointed run with keep-awake and aborts within a second when idle time drops. Frames never leave the device in an unattended run, and an unattended run never writes to a real account. Irreversible actions in an unattended run need a per-routine opt-in. The morning report is one card on return; overnight work never changes the independence score.

**What is different.** Whether to start is a decision on the worker's return forecast; the morning report is one line; and overnight work is excluded from the independence score.

### Where to see it

Needs you (one line: 'Since you were away: 1 run finished, 0 failed', with Details); Routines, 'Run while I'm away' is its own switch on a routine.

### Demo moment

Show the morning line in Needs you and open its Details: ran, failed, yielded, and the audit log. Say that nothing ran unapproved.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The overnight attention scenario passes: the approval is the first thing shown on return, exactly once, with a badge from the moment it arrived and at most one reminder | synthetic, simulated workers | `evals/attention/report_held_out.json (scenario S1)` |
| Overnight batch long-horizon suite passes offline with 0 false claims and 0 ungated submissions | offline tests, no model | `evals/report.md (Agentic evaluation, LH-5)` |

### Honest limit

No real unattended run has been made: every run so far is in the sandbox or in mock mode. The overnight window depends on the presence model, which is weak for shift workers.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: unattended multi-step work with a per-routine consent record
- **HRT (best use of data for predictions and decisions)**: a start-or-wait decision under uncertainty about the worker's return

## Live background task list: a finish shows up without a refresh

**Status:** built (owner requests 4.15 and 4.16 (Track C); documented in docs/knack-ux/background-tasks.md; on main; the tasks service it prefers is on main since 01:42 UTC; not seen end to end by the lead) · **Page:** `docs/features/background-agents.md` · **Targets:** Wordsmith

### What it does

A task that finishes in the background shows as finished on the page with no refresh, and each task is one short line, as minimal as Claude Code's own task list. Running tasks come first, then ones waiting for the worker, then one that finished in the last minute so the finish is seen; the rest of today's finished tasks sit under a closed 'Done today'.

### How it works

One line per task: an icon whose shape carries the state (a spinner while it runs, a check when done, a dash when stopped, a cross when it did not finish, a dot when it waits for the worker), the job in plain words (at most 60 characters) and one note (the current step, the one result line, 'Needs your OK.' or 'Has a question.'). A click opens a plain list of steps and, for a task from the tasks service, Stop and Open folder or Open file. Ids, budgets, leases and counts the worker cannot act on are never shown here; they belong to the admin's Background runs. The data comes from one place: the tasks service when it answers, and the agent service's run list until then. The page stays live three ways: the services' event streams (each event asks for one refresh of the screen's own data, at most one every 0.4 seconds, and a broken stream is dropped and retried after 30 seconds), polling (every 2 seconds while anything is running, every 15 otherwise, waiting for the previous poll, and not at all in a hidden tab) and a refresh when the window regains focus. A refresh keeps the last good data on screen, so an open row stays open and the scroll does not move. A finish is a quiet check and one polite sentence for a screen reader, never a toast. A task that needs the worker also appears in Needs you as a consent card with Allow and Not now of equal weight.

**What is different.** A background task that finishes shows as finished with no refresh, because three plain signals (event stream, a two-second poll, window focus) each ask the screen to reload its own data and keep the last good rows on screen; the line carries only what the worker can act on.

### Where to see it

Routines (top of Running), Home (a short list of up to three), Needs you (a task that waits), and the admin's Background runs.

### Demo moment

Start a task or a routine run and stay on Routines: the line shows its current step, then turns into a check with one result line, with no refresh. Open Done today to show the rest.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The live loop is covered by tests with a fake clock and a fake stream, the line and its ordering by unit tests, the Needs you task cases by model tests, and a smoke block 'Live' in which a mocked tasks service flips a task from running to done while the page is open | offline tests; not run with a real task | `docs/knack-ux/background-tasks.md (section 'Tests')` |

### Honest limit

Seen only with a mocked tasks service and the agent service's own runs: no real task has run through it. The word 'live' means a page that refreshes itself every two seconds or on an event, not a push to the screen. Hidden tabs are not polled, so a finish is shown when the tab is seen again.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a long-running workflow the worker can leave and come back to, with the outcome visible at a glance

## 30-second spoken script

> Knack can hand small jobs to helper agents while you do something else, or overnight. Each helper gets a budget, a sandbox and a short lease. Code recounts every result from the source before it is called verified. In our tests, a stop reached a running helper in a few milliseconds, and twenty-one attempts to write outside the sandbox all failed. In the morning there is one line telling you what ran, and anything irreversible is still waiting for you.

## Slide bullets

- Parent plans, children run in a sandbox with budgets and leases.
- Menu mode: the model sequences vetted steps; file text never reaches it.
- Every result recounted by code; 4 of 4 injected false claims caught.
- Stop within 1 s in 8 of 8 trials; 0 of 21 escapes.
- Overnight: one morning line; irreversible steps wait for a click.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.2 offhours, 14.7)`
- `evals/report.md (Agent runtime, Agentic evaluation)`
- `evals/report.json (sections.runtime)`
- `evals/attention/report_held_out.json`
- `docs/knack-ux/02-needs-you.md`
- `docs/reference-notes/podscontrolmac.md`
- `docs/reference-notes/clicky-reuse.md`

## Related pages

`needs-you.md`, `work-graph-and-hours.md`, `stop-everything.md`, `routines.md`
