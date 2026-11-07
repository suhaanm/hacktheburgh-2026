# Models, routing and the local model

> Gemini for every model role by default, a local model for private digests, ElevenLabs for fixed spoken lines. Model ids come from the environment and are checked at boot.

**Capability:** Models and modes · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Model routing: Gemini by default, checked at boot, Local model digests (a 7B model on this Mac), Spoken lines (ElevenLabs, fixed vocabulary), Mock mode: the whole product offline.

## Model routing: Gemini by default, checked at boot

**Status:** built (live boot check and small planner and fast calls pass; computer use on Gemini needs its own iterations) · **Page:** `docs/features/models-and-routing.md` · **Targets:** Wordsmith, HRT

### What it does

Every model role runs on Gemini by default: a planner, fast checks, pointing and glances, a verifier, computer use and live voice. OpenAI is an explicit opt-in. The More, Models and cost screen shows which model, how fast and what it costs.

### How it works

One model port with providers behind it. Roles map to environment variables (accurate, fast, computer use, live) and nothing hard-codes a model name; at boot the key's model list is read and a missing id stops start-up with the usable ids. Every call that leaves a Python service goes through the egress guard and a metadata-only ledger. The routes were chosen by a bake-off on our sandbox screens. The OpenAI key was revoked by OpenAI on 7 Nov (cause unknown) and the owner moved every OpenAI role to Gemini (D49); one further Gemini model on the key (Argon) is never configured, and a test guards that.

### Where to see it

More, then Models and cost; Settings, 'Use live models' is the master switch (it restarts the engine, about 20 seconds); the sidebar status line says Live models or Running with example data.

### Demo moment

Show the status line 'Live models', then Models and cost: the route for each role, latency and cost. Flip Use live models off and the line becomes 'Running with example data'.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Pointing: Gemini flash-lite 95% [90, 98] (140 of 147), median 0.93 s, about US$0.0005 a call; Gemini flash 95% [90, 97], median 3.31 s, about US$0.0017; OpenAI fast 75% [67, 81], median 1.72 s, about US$0.0015. The routed variant (flash-lite first) was identical to flash-lite alone | synthetic sandbox screenshots, 147 positives and 43 negatives; cost is an estimate | `evals/modelbench/REPORT.md (section 1)` |
| Verifier: all three models right on all 30 images, so the set cannot choose between them | synthetic sandbox screenshots | `evals/modelbench/REPORT.md (section 3)` |
| Recommendation recorded by the benchmark: flash-lite primary for pointing, no escalation needed, Gemini acceptable as verifier | synthetic | `evals/report.md (Model benchmark)` |

### Honest limit

The bake-off is on screenshots of our own sandbox pages with 147 pointing cases; it is not a claim about real apps. Computer use on Gemini has development results only (see the computer-use page). Every earlier number measured with OpenAI models is evidence about that configuration, not about Gemini.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: model roles chosen by measurement, behind one port
- **HRT (best use of data for predictions and decisions)**: a routing decision judged on accuracy, latency and cost

## Local model digests (a 7B model on this Mac)

**Status:** built · **Page:** `docs/features/models-and-routing.md` · **Targets:** HRT, G-Research

### What it does

Raw commits and calendar entries are turned into short enums on the Mac by a local model, so the frontier model sees digests and never the text. If the local model is absent, plain rules do the job.

### How it works

A 7B model (Qwen2.5, 4-bit) runs on the loopback through llama.cpp with constrained decoding, so nothing leaves a digest except vocabulary values. For each field the shipped policy keeps whichever of the model or the rules did better on a held-out split: the model for category, the rules for risk, message quality and whether preparation is needed. Code vetoes the two most consequential claims (a revert needs a revert-style message; focus time needs at most one attendee).

### Where to see it

Behind Git habits and Calendar; More, then Models and cost shows local-model status.

### Demo moment

Not a visual moment. Say it when showing a commit digest: the category came from a model running on this laptop.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Commit category: model 91.8% [84.7, 95.8] against rules 77.5% [68.3, 84.7]; event category: model 95.9% [90.0, 98.4] against rules 81.6% [72.8, 88.0] (98 held-out items each; sign test p = 0.0043 and 0.0026) | synthetic items with planted labels, held-out split run once | `evals/report.md (Local model digests)` |
| Risk, message quality and needs-prep: no clear difference, so the rules are shipped | synthetic, 98 items each | `evals/report.md (Local model digests)` |
| With one planted line in the input, a model-for-everything run moved to the line's value in 19 of 19, 17 of 17, 13 of 17 and 12 of 12 cases; the keyword rules in 0; the shipped policy leaves 0 of 19 and 5 of 17 category steerings | synthetic, 20 items per task | `evals/report.md (Limitations register: loc_injection)` |

### Honest limit

Synthetic commits and entries written by the author of the rules and prompts; accuracy on real data is unknown and probably lower. About 100 items per task, so differences of a few points are not distinguishable. The model can still be steered by whoever writes a commit message or an invite.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a model-or-rules choice per field decided on held-out data
- **G-Research (make the invisible visible)**: private data turned into numbers without leaving the Mac

## Spoken lines (ElevenLabs, fixed vocabulary)

**Status:** built · **Page:** `docs/features/models-and-routing.md` · **Targets:** Wordsmith

### What it does

Short spoken prompts come from a fixed set of lines, not from a model. A voice reads a line by id.

### How it works

Knack sends a line id, never free text, and the call is listed in the ledger. Cached audio supports the offline demo. Cue speaks only when asked (decision D36). A developer escape hatch that lifts the fixed-lines rule exists and is off.

### Where to see it

Spoken cues and the morning briefing, when voice is on.

### Demo moment

Trigger a cached line; show the ledger row that lists the line id and no text.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measured result: the fixed-vocabulary rule is enforced in code and covered by tests | offline tests; no evaluation of voice quality | `docs/FLAGS.md; docs/REQ5_PLAN.md` |

### Honest limit

Not measured for quality or latency. Voice is on by default but depends on the ElevenLabs key; the offline demo uses cached audio.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a calm voice that cannot say anything unplanned

## Mock mode: the whole product offline

**Status:** verified · **Page:** `docs/features/models-and-routing.md` · **Targets:** Wordsmith

### What it does

The same product runs with no model calls and no network: scripted, deterministic answers on example data. The sidebar status line says 'Running with example data' and screens that show example rows keep their own Example data badge.

### How it works

Mock mode is set by the demo command: it seeds an isolated home under data/ (never the worker's real folder), starts the engine, the agent service and the three sandbox sites, and opens the dashboard. Provider calls are replaced by scripted, deterministic ports. The app itself starts in live mode when a Gemini key is present and in mock mode when it is not.

### Where to see it

Sidebar status line; Settings, Use live models.

### Demo moment

Turn wifi off, run the demo command, and walk the dashboard: every screen loads on example data.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| In the lead's sweep all 28 screens and views loaded against the live stack with no page errors; a benefits-agent run in mock mode ended with an item in the approval queue and 0 false claims | mock mode, example data; seen by the lead on 7 Nov about 21:20 UTC | `docs/MVP_STATUS.md` |

### Honest limit

Mock results are scripted: they show the product runs end to end, not that a model does the work. The sweep was before the Knack shell merged; re-run it at the freeze.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a reproducible, offline walk-through of a complicated workflow

## 30-second spoken script

> Every model role in Knack runs on Gemini by default, behind one port, with the model names read from the environment and checked at start-up. We measured the routes: on our sandbox screens the fast Gemini model found the right element ninety-five percent of the time, in under a second. Private text, like commits and calendar entries, is turned into short labels by a model running on this Mac. Spoken lines are a fixed set, read by id.

## Slide bullets

- Gemini for planner, fast checks, pointing, verifier, live voice by default; OpenAI opt-in.
- Model ids from the environment, checked at boot; none hard-coded.
- Pointing: flash-lite 95% [90, 98], median 0.93 s (synthetic sandbox screens).
- Local 7B model for private digests: 91.8% against 77.5% for rules on commit category.
- Spoken lines by id only; no free text leaves.

## Sources

- `docs/FLAGS.md (Provider)`
- `docs/DECISIONS.md (D47, D49)`
- `docs/REQ5_PLAN.md`
- `evals/modelbench/REPORT.md`
- `evals/report.md (Model benchmark, Local model digests)`
- `docs/IMPLEMENTATION_SPEC.md (14.3)`

## Related pages

`privacy-ledger.md`, `screen-annotations.md`, `hey-knack.md`
