# Background agents and overnight runs

> A parent agent gives small, budgeted jobs to child agents in a sandbox. Code verifies every result. Overnight work waits for you in the morning.

**Capability:** Agents that do the work safely · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Background agents: parent and child, Overnight runs and the morning report.

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
