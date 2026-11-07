---
title: "We built a coach that gets less helpful on purpose, and measured where it fails"
published: false
description: "Understudy: aligned expert and novice traces, a coach that fades, and automations the worker opts into one at a time. What we measured, what we could not, and what broke."
tags: # TODO(lead): the DEV Writing Challenge tag, plus up to three of: ai, python, javascript, security
cover_image: # TODO(lead)
---

<!-- DRAFT for the MLH DEV Writing Challenge. Numbers are from evals/report.md (2026-11-07T15:42:27Z, mock mode); re-pull before publishing. PENDING = needs the live study. -->

A new hire and an expert open the same three calculators for the same household. The expert's note says the calculators disagree and why. The novice's note copies the first figure. Where did the minutes and the correctness go?

We built **Understudy** at Hack the Burgh to answer that for one job (a UK benefits processor, on made-up households and sandbox calculators), and to do something about it: coach on the real screen with help that fades, and automate only what the worker has mastered and agrees to hand over. This post is about how it works, what we measured, and, mostly, what went wrong.

## How it works

**Capture that cannot leak text.** A Chrome extension logs events as roles and salted hashes: nothing about page text, URLs or field values. Even the page *region* is an enum, so a click looks like this (an excerpt):

```json
{ "type": "click", "target": { "role": "button", "label_hash": "h:9f2c1a2b3c4d", "domain_hash": "d:77aa00112233" },
  "meta": { "zone": "cliff_button" }, "task_id": "t_bb4a0573e0f6" }
```

Fields on a sensitive list (passwords, card numbers, National Insurance numbers, health questions) are never touched, and a form that holds a password or another sensitive control is dropped whole. We tested that with a hostile page that has secrets in every place we could think of, and with the real extension in a real browser: typing in a login form produced zero events.

**A work genome.** A rule file maps events to cognitive steps ("enter household", "read result", "check cliff", "reconcile"). We align a novice's sequence with the nearest expert's (Needleman-Wunsch, gaps priced in seconds) and report the gap with intervals and two controls: expert against expert, and shuffled labels. If the controls do not sit near zero, the picture is an artefact.

**A coach that fades.** Four help levels per skill, decided by plain deterministic code, not a model, so a chatty model cannot talk the product out of fading. A dignity gate holds the coach back until two stuck signals in a row. The nudge is a question, not the answer.

**Automation that asks.** A finder clusters repeated episodes into routines and proposes one at a time. The worker chooses: not now, never, shadow, with approval. A trust ladder promotes a routine only after a stated number of clean shadow runs, using a Wilson lower bound. Routines are a JSON step language that an interpreter runs; we never execute generated code. Irreversible steps wait in a queue for a human click.

**The model proposes, code decides.** Eight security layers stand between page content and actions, mostly code: sanitising, a quarantined reader that returns schema-checked fields only, typed actions, an action-class gate, data-flow rules, an injection detector, a goal-drift check, protected settings.

## What we measured

Everything below is synthetic unless it says otherwise, and every number has its n, split and interval.

- On synthetic apprentices with planted deficits (n = 16 people) the genome recovers which deficit was injected: precision 92% [84.5, 98.6], recall 95% [88.6, 100]. The real novice-to-expert gap is 229.6 s per case [192.7, 272.6]; expert-against-expert is 7.1 s [-2.8, 18.4].
- Stuck prediction, leave one person out (four personas): log loss 0.436 against 0.509 for the two baselines.
- The dignity gate cuts false nudges from 1.83 to 0.05 an hour, at the price of reaching fewer stuck moments (21% down to 5%).
- A scripted red team against 42 attacks: 0.0% success with every layer on (upper bound 8.4%), 100% with all layers off. False pauses on 31 clean pages: 0.0% [0.0, 11.0].
- On sandbox calculators, 40 of 40 agent runs pass, including 20 with injected failures, and none made a false success claim. That run uses a deterministic mock model.
- The live study with four teammates: **PENDING**. Its analysis plan was committed before any data: with four people the exact sign-flip p-value cannot go below 0.125, so we will report per-person differences and an interval and claim no significance.

## What failed

We think this section is the useful one.

- **Our first coach was silent on every real browsing session.** We had tests, synthetic data and a coach that worked on both. Then we ran the real extension against the real engine, and the coach answered "no active task" every time: it opens a task on a `task_start` event and the extension had never emitted one. The synthetic data did, so nothing tested it. The fix was markers in the role pack that say what a calculator page, a result page and a saved note mean.
- **The genome priced skipping as a time saving.** A novice who skips the cliff check is *faster*, so the waterfall shows a negative "skipped steps" bar. Correct arithmetic, misleading story. We now price skips in answers: with 200 synthetic households, trusting a random single calculator is wrong on about 10% of them, and skipping the cliff panel leaves an edge unwarned on 107, material on 42. Our first version of that table used the first calculator as the policy, which is faithful by construction in our sandbox, so skipping looked harmless. We caught it because the answer was zero.
- **Several results are weak and we publish them.** Skill tracing saturates on high-volume synthetic personas (mean Spearman 0.18). Review routing is circular: it finds the quirks we planted in the calculators, and adds little over the spread of their answers. The hazard's false alarms overshoot the budget on held-out people (1.21 an hour against 1.0). Off-policy evaluation intervals missed the true value in the detailed run, though coverage over 24 replications was 96% for IPS and 88% for doubly robust.
- **A regular expression only worked in Python.** Our JSON Schemas used `(?i)` to make a pattern case-insensitive. That is valid in Python and invalid in JavaScript, and it broke the schema validation in our TypeScript tests.
- **The first real-click check clicked the wrong window.** Our actuator reported success while the click and some typed characters went into another app's window: the scale factor was 1.0 on a Retina screen, and the focus guard ran before the click, not after. Real desktop runs were frozen until the fixes were made and the owner re-approved a retest (TODO(lead): the result). The code we started from had shipped with the real actuator on by default; we turned it off and say so in the README.
- **Our oracle is not the law.** It is a simplified rule set; against PolicyEngine UK it agrees within a pound on 8 of 20 households.

## What we would do next

Run the study. Run the red team against a real model, not a script. Get real traces from a pilot team. Replace the sandbox calculators with a consenting partner's tools. And keep the one rule that saved us most often: every number gets a baseline, a split and an interval, and every chart says what it does not show.

<!-- TODO(lead): link the repo and the demo video; add a screenshot of the work ribbon and of the Evidence page. -->
