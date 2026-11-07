# Context engineering for long runs

> Every model call gets minimal, typed, fresh context. Long runs keep a bounded working memory. Trusted and untrusted text never mix.

**Capability:** A calm product: window, attention, context · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built · **Page:** `docs/features/context-engineering.md` · **Targets:** Wordsmith

## What it does

What each model sees is built by code from typed facts, with a budget, a freshness check and a record of what was left out. A long run carries a small working memory instead of a growing transcript.

## How it works

An audit listed every model-facing call site and its prompt sections. A shared library assembles prompts under nine rules: typed first; trust enforced by audience (the planner never receives raw untrusted text; the reader receives untrusted text but no worker memory); stable first and volatile last so a provider can cache; bounded, with a fixed truncation order and nothing cut mid-item; code-held task state after a resume; one frame and at most one thumbnail; keyed, capped retrieval from the memory file (at most six lines); fresh or named; and measured with a metadata-only manifest. Computer use runs statelessly by default.

**What is different.** Prompts are built from typed facts under a budget with a freshness check, trusted and untrusted text never share a prompt, and a long run carries code-held state instead of a transcript.

## Where to see it

Not visible on a screen. It is behind every agent run and shows up as cost and latency in Models and cost.

## Demo moment

Not a visual moment. Say it with a number: computer-use prompts stay flat at about 2.8 thousand tokens a step instead of growing.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Stateless computer use measured 74,548 input tokens over 27 steps (about 2.76k a step, flat); the chained thread it replaced measured 211,852 over 25 calls (about 8.5k a call and growing) | real model, one run each, n = 1 | `docs/CONTEXT_ENGINEERING.md (section 1.1); evals/agentic/ITERATIONS.md` |
| Tier 3 through the real loop over 100 steps: the prompt text stayed 672 to 752 estimated tokens per step; tier 2 consecutive prompts share about 55% of their text | test doubles as the model; measures what the loops send, not what a model does | `docs/CONTEXT_ENGINEERING.md (section 1.6)` |
| Background runtime: the typed context payload grows from 66 to 288 tokens over 14 steps; after step 8 the maximum is 1.08 times the first eight steps' maximum | synthetic fixtures | `evals/report.json (runtime, headline)` |
| Modelled over 150 steps: a chained thread reaches 285.7k tokens at step 150 (21.6M cumulative); the library stays at about 2.8k a step (0.42M cumulative), a calibration to one live run, not an independent check | modelled with the real history functions; no model call | `docs/CONTEXT_ENGINEERING.md (section 5.1)` |
| 800 attempts to put raw untrusted text into a planner, checker, computer-use or vision packet were all refused; 0 leaks of worker memory to the reader; 56 freshness cases with 0 wrong decisions | offline tests with synthetic injection strings | `docs/CONTEXT_ENGINEERING.md (sections 5.4 and 5.6)` |

## Honest limit

Token counts are estimates (characters divided by 3.6) beside the provider's usage fields. The measured runs use test doubles or n = 1 live runs; nothing here is a live-model result at scale. The reader still re-reads the same page often; a memo is not built. At the time the document was written, keyed retrieval from the memory file was built and tested but not yet in any prompt, and no live-model result shows a gain in completion, steps or false claims.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a long-horizon browser workflow that does not drown in its own history

## 30-second spoken script

> A long task can drown in its own history. Knack builds what each model sees from typed facts, with a budget and a freshness check, and it keeps a small working memory instead of a growing transcript. In computer use the prompt stays flat at about two thousand eight hundred tokens a step, where the chained version we replaced grew to about eight and a half thousand a call. Trusted and untrusted text never mix.

## Slide bullets

- Every call site audited; one library builds prompts.
- Typed first, trusted and untrusted kept apart, stable prefix first.
- Bounded working memory; one frame; keyed memory retrieval of at most six lines.
- Stateless computer use: about 2.76k tokens a step, flat (n = 1).
- Estimates, test doubles and single runs: said plainly.

## Sources

- `docs/CONTEXT_ENGINEERING.md`
- `evals/context/PLAN.md`
- `evals/agentic/ITERATIONS.md`
- `evals/report.json (sections.runtime)`

## Related pages

`computer-use.md`, `background-agents.md`, `privacy-ledger.md`
