<!-- Under 400 words (counted without this comment). Claims only what evals/report.md and the smoke tests support. PENDING = needs the live study. TODO = re-pull before submitting. -->

# Understudy

**Shows where a novice loses time against an expert, coaches on the real screen with help that fades, and automates only what the worker chooses.**

## Inspiration
Tools usually do the task for you, or forget you. We wanted one that measures how much help you still need and automates only what you have mastered.

## What it does
Understudy records how people do a task (no page text, URLs or field values), aligns a novice's trace with an expert's, and prices the gap in seconds with intervals and controls. A coach draws on the real screen, lightening as skills improve. A routine finder proposes automations one at a time; the worker opts in, shadows, then lets an agent run it; irreversible steps wait for a click. A presence model decides when a background run may start; a memory file the worker owns tunes it. One deep role pack (UK benefits processor), two thin.

## How we built it
Python engine and agent service, React dashboard, an Electron coach adapted from our own earlier library, a Chrome extension, sandbox calculators. The model proposes; code decides. Eight security layers guard the agent. Everything runs offline in mock mode.

## Challenges
Evidence is thin: histories are synthetic and the live study has four teammates, so every chart shows n, split and interval. A smoke test showed the coach was silent on real browsing because capture emitted no task markers; fixed.

## Accomplishments
On synthetic apprentices the genome recovers planted deficits (precision 92%, recall 95%; gap 229.6 s against a 7.1 s placebo). Stuck-prediction log loss is 0.436 against 0.509 for baselines. A scripted red team succeeds on 0% of 42 attacks with every layer on (upper bound 8.4%) and 100% with all layers off. Agent runs on sandbox calculators: 40 of 40 pass, no false success claims (mock model).

## What we learned
Skipping a step looks free in seconds but costs answers, so we price both. We publish weak results: skill tracing saturates, routing is circular, hazard false alarms overshoot budget.

## What's next
The live study (n = 4, plan committed before data): **PENDING**. A real-model red team; real traces.

## Limits
Synthetic data, a simplified oracle (not law), n = 4, scripted attackers. We do not claim novices become experts.

**Built with:** Python, FastAPI, React, TypeScript, Electron, Chrome MV3, Playwright, OpenAI.
**Tracks:** HRT, G-Research, Wordsmith.
