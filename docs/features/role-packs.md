# Role packs

> One deep role (UK benefits processor) and two thin ones (data analyst, programmer), so Knack is not a benefits tool with the name changed.

**Capability:** Roles · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Role packs: benefits processor deep, analyst and programmer thin, Deeper programmer and data-analyst roles.

## Role packs: benefits processor deep, analyst and programmer thin

**Status:** built · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

### What it does

A role pack turns raw events into steps, says what an expert does, which actions need a click, what tone to use, which routines to look for and what to teach in what order. The benefits processor pack is deep; the data analyst and programmer packs are thin starting points.

### How it works

A pack is a validated folder (id, onboarding questions for tools, risky actions, tone, pace and hours; extra step types and their mapping from events; expert steps with allowed reorderings; risk classes with label patterns; routine templates; a curriculum; persona parameters; priors for pooling). The benefits pack also has an oracle, task configuration and sandbox sites. The thin packs fill every key but the oracle, tasks and the full expert policy, and differ visibly in questions, steps, risk classes and tone: the programmer's risky actions are force-push, deleting a branch, merging to main and publishing; the benefits processor's are submitting a case, issuing a payment and sending a letter. A loader checks packs against a JSON Schema and the pack format reserves a slot for plugin references.

### Where to see it

First run (the role cards), Settings, Set up again, and the Admin Roles view.

### Demo moment

At first run, choose each of the three cards; show how the four lines on the 'what Knack will remember' screen differ (tools, never-without-me actions, hours).

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Pack format and loader covered by 66 test functions; packs validate against the schema | offline tests (static count) | `evals/report.facts.json (tests.by_dir, packages/packs/tests)` |
| Thin roles on harder synthetic generators: routine finder raw precision 88 to 98%, recall 60 to 92%, proposal precision 100%; git habits for the programmer: precision 116 of 116, recall 116 of 120 | synthetic | `evals/report.md (Findings, and Git habits)` |
| Stuck model: the accepted v2 improvement qualifies for benefits processor and programmer; no variant qualified for data analyst | synthetic, held-out | `evals/mlv2/results/heldout_hazard.json` |

### Honest limit

The thin packs are starting points and have not been validated on real work. Genome recovery was not evaluated for them because the named-deficit labels belong to the benefits pack. Even the deep pack has no real benefits-processor data behind it.

### Hackathon target

- **G-Research (make the invisible visible)**: the same lens on three different jobs
- **Wordsmith (most complicated end-to-end browser-use workflow)**: one workflow deep, two shallow

## Deeper programmer and data-analyst roles

**Status:** landing (ROLE-DEPTH (Track F), additive only; docs/roles/*.md have not landed) · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

### What it does

The two thin roles are being given more depth: more steps, habits and sandbox tasks, without changing any existing id, expert path or generator parameter.

### How it works

Per owner decision D55 the work is additive only. The role studies already use private sandbox worlds for the programmer (editor, tests, console) and the analyst (table, filter, pivot, chart with planted data issues).

### Where to see it

Not on main yet; see docs/roles/ when it lands.

### Demo moment

Not yet available. Do not show until it lands.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Nothing to quote yet; the role studies themselves were not run (1 of 3 programmer feasibility pilots was usable; no analyst pilot) | not run | `evals/report.md (Study across roles)` |

### Honest limit

Not verified. Update this entry from docs/roles/*.md after it lands.

### Hackathon target

- **G-Research (make the invisible visible)**: more than one job
- **Wordsmith (most complicated end-to-end browser-use workflow)**: more than one workflow

## 30-second spoken script

> Knack is not just a benefits tool. A role pack tells it what an expert does in a job, which actions always need a click, and what to teach in what order. We built one deep pack, a UK benefits processor, and two thin ones, a data analyst and a programmer, which differ visibly in their questions and risky actions. The thin ones are starting points, not validated, and a deeper version of both is landing now.

## Slide bullets

- A pack: steps, expert policy, risky actions, tone, routines, curriculum.
- Deep: UK benefits processor. Thin: data analyst, programmer.
- Different risky actions per role: force-push and merge for programmers, submit and pay for benefits.
- Thin packs are starting points, not validated.
- Deeper roles landing (additive only).

## Sources

- `docs/IMPLEMENTATION_SPEC.md (6.3)`
- `packages/packs/benefits-processor/pack.yaml`
- `packages/packs/programmer/pack.yaml`
- `docs/SPEC_LIST.md (D4)`
- `docs/DECISIONS.md (D55)`
- `evals/report.md`
- `docs/roles/ (landing, branch)`

## Related pages

`connections.md`, `knack-shell.md`, `firm-admin.md`
