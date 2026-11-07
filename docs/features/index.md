# Knack feature index

31 pages and 56 entries (features, plus four write-ups of results that did not hold up), for the pitch (Hack the Burgh XIII), the launch video, the demo and the submission video. The master document is `docs/PITCH_FEATURES.md`; the 20 video claims are in `video-beats.md`; the 25 hardest judge questions are in `faq.md`.

**Status words.** `verified`: the lead saw it work end to end (`docs/FEATURE_CATALOGUE.md`). `built`: built and tested by its track, on main, not yet seen end to end by the lead. `landing`: not on main yet (another agent's branch, or its document has not landed). `not run`: designed or built but never run. The status is taken from the sources at the time of writing (see the time stamp in `docs/PITCH_FEATURES.md`); nothing here was run by the author.

**Evidence labels.** `synthetic`: data we generated. `simulated`: language-model participants, not people. `real model, small n`: a language model on our sandbox sites. `offline tests`: the code behaves as specified; no model, no people. `owner-present`: a supervised check with the owner at the machine. `not run`: no data. Nothing in this folder is evidence about real workers; the live study (n = 4) has not been run.

## See the work

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Text-free capture](capture.md) | Text-free capture (Chrome extension and event store) | built | G-Research, Wordsmith |
| [Work genome: where time goes](work-genome.md) | Work genome: aligned traces priced in seconds; Controls: placebo and shuffled-label null; What skipping costs in answers | Work genome: aligned traces priced in seconds: verified; Controls: placebo and shuffled-label null: verified; What skipping costs in answers: built | G-Research, HRT |
| [Stuck prediction and the Forecasts scorecard](stuck-model.md) | Stuck prediction and the Forecasts scorecard | verified | HRT |
| [Your hours and how work connects](work-graph-and-hours.md) | Your hours: presence map and away forecast; How work connects: the work graph | built | G-Research, HRT |
| [Calendar layer and git habits](calendar-and-git.md) | Calendar layer (week ribbon, Outlook and Teams adapters); Git habits for programmers | built | G-Research, HRT |

## Coach on the screen

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Live coach and fading help](live-coach.md) | Live coach: one decision at a time, with a dignity gate; Fading help: levels L1 to L4 decided by code | verified | HRT |
| [On-screen annotations](screen-annotations.md) | On-screen annotations: ring, one label, ghost cursor | built | G-Research |
| [Awareness and glances](awareness-glances.md) | On-device awareness and triggered glances | built | G-Research |

## Step in when stuck

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Cue: stuck rescue](cue.md) | Cue: stuck rescue | built | G-Research, HRT |

## Agents that do the work safely

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Benefits agent and 'code decides done'](benefits-agent.md) | Benefits agent on three sandbox calculators; Code decides 'done'; Independent verifier (a second model family) | Benefits agent on three sandbox calculators: verified; Code decides 'done': verified; Independent verifier (a second model family): built | Wordsmith |
| [Eight security layers](security-layers.md) | Eight security layers, approval queue and audit log | verified | Wordsmith |
| [Computer use and the real-click ladder](computer-use.md) | Computer use on the sandbox calculators; Real-click ladder (R0 to R4) and the arm switch | built | Wordsmith |
| [Background agents and overnight runs](background-agents.md) | Background agents: parent and child; Overnight runs and the morning report | built | HRT, Wordsmith |
| [Stop everything](stop-everything.md) | Stop everything: the kill switch | built | Wordsmith |

## Routines and automations

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Routines: found, proposed, trusted one at a time](routines.md) | Routine finder and proposals; Watch first and the trust ladder; Could automate: the repeat list | Routine finder and proposals: built; Watch first and the trust ladder: verified; Could automate: the repeat list: built | G-Research, HRT, Wordsmith |
| [Needs you](needs-you.md) | Needs you: one list for decisions | built | Wordsmith |
| [Decisions under uncertainty](hrt-decisions.md) | When to build an automation: ski rental with predictions; Review routing under a risk bound | built | HRT |

## Connections and MCP plugins

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Connections: curated plugins](connections.md) | Connections: curated MCP plugins with role presets | landing | Wordsmith |

## Voice and Hey Knack

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Hey Knack: voice that points](hey-knack.md) | Hey Knack: an on-device wake phrase; Voice guidance and 'do it for me' behind a click | built | G-Research, Wordsmith |
| [Models, routing and the local model](models-and-routing.md) | Model routing: Gemini by default, checked at boot; Local model digests (a 7B model on this Mac); Spoken lines (ElevenLabs, fixed vocabulary) | built | G-Research, HRT, Wordsmith |

## Insights and admin

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Home and the top insights](home-insights.md) | Home: one sentence, one action; Top insights engine: a few pointers, chosen by code | built | G-Research, HRT |
| [Firm, Roles and Onboarding for admins](firm-admin.md) | Admin views: Firm, Roles, Onboarding; Monday note, firm brief and prediction scorecard | built | G-Research, HRT |

## Growth and independence

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Growth and the independence score](growth-independence.md) | Growth and the independence score | built | G-Research, HRT |

## A calm product: window, attention, context

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [One attention layer](attention-router.md) | One attention layer: a router, a digest, quiet states | built | HRT |
| [Context engineering for long runs](context-engineering.md) | Context engineering: typed, bounded, fresh | built | Wordsmith |
| [One app, one window, one pill, three clicks](knack-shell.md) | One app, one window, one corner pill; First run in three clicks; Command palette and keyboard | built | G-Research, Wordsmith |

## Privacy and safety

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Privacy spine: egress guard and ledger](privacy-ledger.md) | Egress guard, ledger and canary tests | built | G-Research, Wordsmith |
| [Your data and the memory file you own](your-data.md) | Your data: see and delete; Memory file the worker owns | built | G-Research |

## Evidence and honesty

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Evidence page, make eval and the explainer](evidence-and-explain.md) | Evidence page, make eval and the limitations register; Plain-English explainer with a number check | Evidence page, make eval and the limitations register: verified; Plain-English explainer with a number check: built | G-Research, HRT |
| [What did not hold up](what-did-not-hold-up.md) | Generator-mismatch test (the realism matrix); ML v2, held-out: mostly negative; The simulated study sat at the floor; Other results that went the wrong way | verified | G-Research, HRT |

## Roles

| Page | Features on it | Status | Targets |
|---|---|---|---|
| [Role packs](role-packs.md) | Role packs: benefits processor deep, analyst and programmer thin; Deeper programmer and data-analyst roles | Role packs: benefits processor deep, analyst and programmer thin: built; Deeper programmer and data-analyst roles: landing | G-Research, Wordsmith |

## Also in this folder

- [video-beats.md](video-beats.md): 20 one-line claims with the proof shot, tagged teaser, demo or technical.
- [faq.md](faq.md): the 25 hardest judge questions with short, truthful answers.
