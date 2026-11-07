# Routines: found, proposed, trusted one at a time

> Knack finds repeated work and proposes an automation. The worker opts in one routine at a time, and autonomy is earned by matching what the worker does.

**Capability:** Routines and automations · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Routine finder and proposals, Watch first and the trust ladder, Could automate: the repeat list.

## Routine finder and proposals

**Status:** built (the routine card and queue were seen working in the dashboard; the finder is mixed on harder synthetic data) · **Page:** `docs/features/routines.md` · **Targets:** Wordsmith, HRT

### What it does

Knack finds work you repeat, estimates how much time automating it would save, and proposes it with three equal choices: Watch first, Not now, Never. Nothing runs until you choose.

### How it works

Episodes are segmented and clustered by alignment distance, with at least 3 supports. Each cluster is scored by count, minutes a week, variability and judgement share (searches, compares and decides divided by length) and matched to the role pack's routine templates. A value gate then keeps only proposals with a worthwhile saving. A recurrence forecast gives an interval on future runs. Proposals arrive only at episode boundaries, at most a few a day, and the system learns P(accept) per person. A routine is a JSON step language with a precondition and postcondition per step: model-written code is never executed.

**What is different.** A routine is eligible for automation only if the worker has mastered its steps or the pack marks it as not learning-relevant; otherwise Knack coaches it instead of taking it over.

### Where to see it

Needs you (the proposal is a row with three equal buttons and 'More ways to say yes'); Routines, Running and Could automate.

### Demo moment

A routine row 'Enter the household into three calculators': 'Seen 58 times in 3 weeks', what it touches, 'It will never submit'. Press Watch first. Nothing is saved or sent.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Raw finder: 12 of 55 clusters were planted routines (22% [12.9, 34.4]); after the value gate 6 of 6 proposals were planted (100% [61.0, 100.0]); recall 100% [74.1, 100.0] | synthetic, 4 personas | `evals/report.md (Routine finder)` |
| On three harder generators: raw precision 44 to 97%, recall 45 to 92%, proposal precision after the gate 74 to 100%; the cut height does not transfer | synthetic, 120 people per cell | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |
| Recurrence forecast: 8 of 11 routines inside their interval (73% [43.4, 90.3]) | synthetic, fit on days 1 to 14, scored on days 15 to 21 | `evals/report.md (Recurrence forecast)` |

### Honest limit

The raw finder returns many clusters of one-off work; the gate does the work. The high precision on harder generators partly reflects less repeated structure in generated ad hoc work. All people are synthetic. Whether real workers find the proposals useful is unmeasured.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: from observed repetition to an approved, scripted browser routine
- **HRT (best use of data for predictions and decisions)**: a value estimate with an interval and a gate

## Watch first and the trust ladder

**Status:** verified · **Page:** `docs/features/routines.md` · **Targets:** Wordsmith, HRT

### What it does

A routine earns autonomy by practising beside the worker. In Watch first it shadows real work without saving or sending, and a record of matches decides whether it may step up. Autonomy goes down again on any failure.

### How it works

Four rungs: observe; suggest and shadow; do with approval; do then report. Promotion from shadow to 'asks first' needs at least 20 shadow runs with a Wilson lower bound of 0.8 on matches (20 clean runs give about 0.84). The top rung needs a lower bound of 0.95 (about 75 clean runs), a target the demo does not reach, and the screen says so. A failure, an undo within seconds or an injection hit demotes one rung. A divergence in shadow counts as a non-match. In the app the rungs read Watching, Asks first and Runs on its own; 'while I'm away' is its own switch, and irreversible steps in unattended runs need a separate per-routine opt-in.

**What is different.** Autonomy is earned by matching what the worker does, with a Wilson lower bound on shadow matches, and any failure, undo or injection hit demotes it.

### Where to see it

Routines: a row opens in place with a three-state control; a step up is enabled only when the record earned it and a disabled step prints what it needs.

### Demo moment

Open a routine row: its state in words (Watching, Asks first or Runs on its own) and, when a step up has not been earned, the printed need. Press Watch first on a proposal; show the queue stays empty.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Wilson thresholds and the rung rules are code with unit tests; no live shadow data exists | offline tests; no people | `docs/IMPLEMENTATION_SPEC.md (7.1 trust)` |

### Honest limit

The ladder is a mechanism with synthetic evidence only. The top rung is not reachable in the demo by design. The shadow record on real work has never been collected.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: earned autonomy with a hard consent record
- **HRT (best use of data for predictions and decisions)**: promotion decided by a confidence bound

## Could automate: the repeat list

**Status:** built · **Page:** `docs/features/routines.md` · **Targets:** Wordsmith, G-Research

### What it does

A compact list of actions you repeat that could be automated, ranked by minutes saved a week. Automate opens a 'Watch first' peek; it never runs anything.

### How it works

Ranked by estimated minutes saved a week, then by count. A sequence that matches a pack routine needs 3 repeats; an unmatched sequence needs 5 repeats on at least 2 days. Seven rows then Show all; folds for Already automated and Hidden. One honest line says what repeats but is not offered: work that needs judgement, an irreversible first step, work that is too varied, or denylisted work. A firm aggregate suppresses groups under 5 people. It is inspired by the JetBrains Key Promoter X list of missed shortcuts, but counts repeated actions and never nags.

**What is different.** One row per repeated task even across tools, ranked by minutes saved, with an honest line for what repeats but is not offered and why.

### Where to see it

Routines, tab Could automate.

### Demo moment

Open Could automate: 'Read the case, then open the calculators: about 25 minutes a week'. Press Automate; the Watch first peek opens; nothing starts.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| 26 of 27 pre-written expectations met (96.3% [81.7, 99.3]); routines named by the pack listed for 60 of 60 people at 3, 5 and 8 repeats; unnamed routines 0 of 60 at 3 repeats by design and 60 of 60 at 5 and 8; people with no planted repeat got a row 0 of 60 times | synthetic, 60 people per cell, development seeds only | `evals/report.md (Hit list)` |
| Missed: top row unchanged when 5% of episodes are dropped, 53 of 60 (expected at least 0.9) | synthetic, development seeds | `evals/report.md (Hit list)` |

### Honest limit

Development seeds only, with worlds written by the author of the rules: no held-out claim. Seen rendered in a harness; the order of the rows and the minutes are estimates with intervals behind a Hint.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: finding the automatable part of a complicated workflow
- **G-Research (make the invisible visible)**: the repeated work made visible

## 30-second spoken script

> Knack notices work you repeat, estimates what automating it would save, and asks. Three equal buttons: Watch first, Not now, Never. Watch first lets the routine practise beside you, saving and sending nothing. It earns more autonomy only by matching what you do, with a confidence bound, and loses it on any failure. Automations are a small step language, never generated code. The proposal says what it touches and what it will never do.

## Slide bullets

- Finder: clusters of repeated work, scored by minutes, variability and judgement share.
- Value gate: 6 of 6 proposals planted, though the raw finder is 22% precise (synthetic).
- Watch first, Not now, Never carry equal weight.
- Trust ladder: 20 shadow runs and a Wilson bound of 0.8 to ask first; demote on failure.
- Automations are a JSON step language; code is never generated.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (6.5, 7.1 routines, trust)`
- `docs/knack-ux/03-routines.md`
- `docs/knack-ux/02-needs-you.md`
- `docs/DECISIONS.md (D46)`
- `docs/reference-notes/okidoki.md`
- `docs/reference-notes/drigil.md`
- `evals/report.md (Routine finder, Hit list, Recurrence forecast)`
- `evals/realism/INTERPRETATION.md`

## Related pages

`needs-you.md`, `hrt-decisions.md`, `background-agents.md`, `your-data.md`
