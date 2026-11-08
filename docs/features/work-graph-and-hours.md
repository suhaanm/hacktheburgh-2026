# Your hours and how work connects

> A weekly map of when you are at the machine, and a graph of your routines, skills and notes that fades with disuse.

**Capability:** See the work · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (landing).** The lead's views rule (`docs/knack-ux/views.md`, from owner requests 4.1, 4.2, 4.11, 4.12 and 4.17 at about 00:50 UTC) is reorganising where screens live. Where this page says 'More, <screen>', check `apps/dashboard/src/components/home/navModel.ts` on main for the final place. 'Your hours' and 'How work connects' become sections of Growth ('my working hours', 'my routines map'). The graph is being moved to the new design system (owner request 4.13: an icon per node style and no visible text except on hover or click).

This page covers Your hours: presence map and away forecast, How work connects: the work graph.

## Your hours: presence map and away forecast

**Status:** built · **Page:** `docs/features/work-graph-and-hours.md` · **Targets:** HRT, G-Research

### What it does

A weekly map of when you are at your machine, with intervals, and an estimate of how long you will stay away. Knack starts a background run only when the odds that you stay away for the whole run are good enough.

### How it works

672 fifteen-minute bins a week; each has a Beta posterior for 'active', seeded from the role pack's hours and smoothed across neighbouring bins and the same hour on other days. The window forecast estimates the chance S(D | t) that a gap starting now lasts D minutes, from the worker's own past idle spells. A run of length D starts only if S(D | t) is greater than L divided by G plus L, where G is the value of finishing and L the cost of colliding with the worker's return (a critical-fractile rule). It never starts on a locked or sleeping machine.

**What is different.** The start decision is a critical-fractile rule on a forecast of how long this worker stays away, judged against two baselines, rather than 'start when idle'.

### Where to see it

More, then Your hours (address #/presence). Your data also lists the hours Knack holds.

### Demo moment

Open Your hours: the week as a heat map with intervals and the free hours it reveals. Say how the rule decides when a run may start, then show the numbers against the two baselines.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The start-or-wait rule interrupted 2.1% of started runs against 24.8% for 'run whenever idle five minutes' and 2.0% for a fixed overnight window; it used 74.2% of idle time against 90.2% and 43.0%; cap 10%; window Brier score 0.131 | synthetic, 4 personas, 21 days, forward held-out days | `evals/report.md (Presence and window forecast)` |

### Honest limit

The weekly map predicts the shift worker's held-out days worse than a simple baseline (map Brier 0.214 against 0.194 and 0.175); the 95% intervals contain the planted probability in only 55% to 91% of bins; idle capacity is over-estimated. A weekly template does not suit rotating shifts or no routine.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision rule with a cost of collision, evaluated against two baselines
- **G-Research (make the invisible visible)**: the rhythm of a working week made visible

## How work connects: the work graph

**Status:** built · **Page:** `docs/features/work-graph-and-hours.md` · **Targets:** G-Research

### What it does

A graph of routines, skills and remembered facts. Nodes link when related, merge when two routines always run together, and fade with disuse. A click shows why a node exists and lets the worker edit or delete it.

### How it works

Size is weekly minutes or mastery, colour is the node type, opacity is strength, and fading uses the same decay as the help-level engine. Deleting a memory node edits the memory file, so the graph is a view of what Knack holds, not a second store. One of the product's three signature visuals.

**What is different.** Fading is literal: nodes decay with the same rule the help levels use, and deleting a node edits the file the worker owns, so the graph is a view and not a second store.

### Where to see it

More, then How work connects (address #/graph). Settings, Views, Pinned views puts it in the sidebar.

### Demo moment

Open the graph, click a routine node to see why it exists, then delete a memory node and show the line leaving the memory file in Your data.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measured result: this screen is a view of the engine's work graph and has no evaluation of its own | no evidence yet (built; not measured) | `docs/IMPLEMENTATION_SPEC.md (7.4)` |

### Honest limit

Not measured. The Knack navigation moved it out of the sidebar into More; it stays one click from Pinned views. Visual quality is judged by eye, not by an experiment.

### Hackathon target

- **G-Research (make the invisible visible)**: motion carries meaning; fading is literal

## 30-second spoken script

> Two quiet maps. Your hours shows the shape of your week with its uncertainty, and Knack uses it to start a background job only when the odds say you will stay away. On our synthetic personas that interrupted two percent of runs, against twenty-five percent for running whenever idle. How work connects is a graph of your routines and skills that fades when you stop doing them. You can edit or delete any node.

## Slide bullets

- Weekly presence map with intervals; free hours shown.
- Start a run only if the chance you stay away beats a threshold.
- 2.1% interruptions against 24.8% for 'whenever idle' (synthetic, 4 personas).
- Weak for the shift worker: stated.
- Work graph: nodes link, merge and fade; delete a node, edit the memory.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.1 presence, 7.4)`
- `docs/UI_DIRECTION.md`
- `evals/report.md (Presence and window forecast, Limitations register)`
- `docs/KNACK_UX.md (section 3)`
- `apps/dashboard/src/components/home/navModel.ts`

## Related pages

`background-agents.md`, `routines.md`, `your-data.md`
