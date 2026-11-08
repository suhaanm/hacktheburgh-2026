# Knack feature index

As of Sun 08 Nov 2026, 02:45 UTC, checked against main at 1a2cdc6.

35 pages and 70 entries (features, plus four write-ups of results that did not hold up), for the pitch (Hack the Burgh XIII), the launch video, the demo and the submission video. The master document is `docs/PITCH_FEATURES.md`; the 25 video claims are in `video-beats.md`; the 28 hardest judge questions are in `faq.md`.

**Status words.** `verified`: the lead saw it work end to end (`docs/FEATURE_CATALOGUE.md`). `built`: built and tested by its track, on main, not yet seen end to end by the lead. `landing`: not on main yet (another agent's branch, or its document has not landed). `not run`: designed or built but never run. The status is taken from the sources at the time of writing (see the time stamp in `docs/PITCH_FEATURES.md`); nothing here was run by the author.

**Evidence labels.** `synthetic`: data we generated. `simulated`: language-model participants, not people. `real model, small n`: a language model on our sandbox sites. `offline tests`: the code behaves as specified; no model, no people. `owner-present`: a supervised check with the owner at the machine. `not run`: no data. Nothing in this folder is evidence about real workers; the live study (n = 4) has not been run.

## See the work

| Feature | Page | Status | Targets |
|---|---|---|---|
| Text-free capture (Chrome extension and event store) | [capture](capture.md) | **built** | G-Research, Wordsmith |
| Work genome: aligned traces priced in seconds | [work-genome](work-genome.md) | **verified** (verified on its own generator; degrades on harder synthetic data) | G-Research |
| Controls: placebo and shuffled-label null | [work-genome](work-genome.md) | **verified** | G-Research |
| What skipping costs in answers | [work-genome](work-genome.md) | **built** | G-Research, HRT |
| Stuck prediction and the Forecasts scorecard | [stuck-model](stuck-model.md) | **verified** (verified on its own generator; does not transfer to harder synthetic data) | HRT |
| Your hours: presence map and away forecast | [work-graph-and-hours](work-graph-and-hours.md) | **built** | HRT, G-Research |
| How work connects: the work graph | [work-graph-and-hours](work-graph-and-hours.md) | **built** | G-Research |
| Calendar layer (week ribbon, Outlook and Teams adapters) | [calendar-and-git](calendar-and-git.md) | **built** | G-Research |
| Git habits for programmers | [calendar-and-git](calendar-and-git.md) | **built** | G-Research, HRT |

## Coach on the screen

| Feature | Page | Status | Targets |
|---|---|---|---|
| Live coach: one decision at a time, with a dignity gate | [live-coach](live-coach.md) | **verified** | HRT |
| Fading help: levels L1 to L4 decided by code | [live-coach](live-coach.md) | **verified** | HRT |
| On-screen annotations: ring, one label, ghost cursor | [screen-annotations](screen-annotations.md) | **built** (the lead viewed screenshots; not yet confirmed end to end on a real Chrome tab) | G-Research |
| On-device awareness and triggered glances | [awareness-glances](awareness-glances.md) | **built** (layer is on by default; no frame is sent until the worker records consent; macOS Screen Recording is the owner's to grant) | G-Research |

## Step in when stuck

| Feature | Page | Status | Targets |
|---|---|---|---|
| Cue: stuck rescue | [cue](cue.md) | **built** (engine and desktop code built and tested; evaluated on simulated workers only; not run on a real desktop) | HRT, G-Research |

## Agents that do the work safely

| Feature | Page | Status | Targets |
|---|---|---|---|
| Benefits agent on three sandbox calculators | [benefits-agent](benefits-agent.md) | **verified** (verified in mock mode: ends with an item in the approval queue and 0 false claims) | Wordsmith |
| Code decides 'done' | [benefits-agent](benefits-agent.md) | **verified** | Wordsmith |
| Independent verifier (a second model family) | [benefits-agent](benefits-agent.md) | **built** (routed by default to Gemini flash-lite; its evaluation set is small and easy) | Wordsmith |
| Eight security layers, approval queue and audit log | [security-layers](security-layers.md) | **verified** | Wordsmith |
| Optional sign-in step-up for irreversible approvals (Auth0) | [security-layers](security-layers.md) | **built** (built; not configured: it needs the owner's Auth0 domain and client ID, and is never on the demo's critical path) | Wordsmith |
| Computer use on the sandbox calculators | [computer-use](computer-use.md) | **built** (Gemini, held-out and pre-registered: 18 of 20 clean households completed with correct inputs, below the bar we set; the earlier OpenAI configuration completed 1 of 4; nothing has driven a real desktop) | Wordsmith |
| Real-click ladder (R0 to R4) and the arm switch | [computer-use](computer-use.md) | **built** (read-only rung R0 ran once; nothing else has run) | Wordsmith |
| Background agents: parent and child | [background-agents](background-agents.md) | **built** | Wordsmith |
| Overnight runs and the morning report | [background-agents](background-agents.md) | **built** | Wordsmith, HRT |
| Live background task list: a finish shows up without a refresh | [background-agents](background-agents.md) | **built** (owner requests 4.15 and 4.16 (Track C); documented in docs/knack-ux/background-tasks.md; on main; the tasks service it prefers is on main since 01:42 UTC; not seen end to end by the lead) | Wordsmith |
| Stop everything: the kill switch | [stop-everything](stop-everything.md) | **built** | Wordsmith |
| Open-ended tasks, skills in context and Claude background agents | [open-ended-tasks](open-ended-tasks.md) | **built** (owner decision D63 (01:05 UTC); merged to main at 01:42 UTC (fded20e): the service, API, router, Claude command runner, skills and browser runner, the consent cards and task list in the dashboard; the page has the rest) | Wordsmith |

## Routines and automations

| Feature | Page | Status | Targets |
|---|---|---|---|
| Routine finder and proposals | [routines](routines.md) | **built** (the routine card and queue were seen working in the dashboard; the finder is mixed on harder synthetic data) | Wordsmith, HRT |
| Watch first and the trust ladder | [routines](routines.md) | **verified** | Wordsmith, HRT |
| Could automate: the repeat list | [routines](routines.md) | **built** | Wordsmith, G-Research |
| Needs you: one list for decisions | [needs-you](needs-you.md) | **built** (merged to main; seen in a harness and in hidden end-to-end runs; owner has not used it) | Wordsmith |
| When to build an automation: ski rental with predictions | [hrt-decisions](hrt-decisions.md) | **built** | HRT |
| Review routing under a risk bound | [hrt-decisions](hrt-decisions.md) | **built** | HRT |
| Proactive briefing: judge, verify, prepare, press to fire | [proactive-briefing](proactive-briefing.md) | **built** (engine built and tested; development-set evaluation only; cards now arrive as rows in Needs you) | HRT, Wordsmith |

## Connections and MCP plugins

| Feature | Page | Status | Targets |
|---|---|---|---|
| Connections: curated MCP plugins with role presets | [connections](connections.md) | **built** (owner decision D55; merged to main at 01:28 UTC (97b633f) with docs/CONNECTIONS.md; built and tested by its track, not seen end to end by the lead; nothing real has been connected) | Wordsmith |

## Voice and Hey Knack

| Feature | Page | Status | Targets |
|---|---|---|---|
| Hey Knack: an on-device wake phrase | [hey-knack](hey-knack.md) | **built** (code and tests are built and merged; not run with a real microphone yet; the page has the rest) | G-Research |
| Voice guidance and 'do it for me' behind a click | [hey-knack](hey-knack.md) | **built** (the click path fails closed until the first supervised real-click test has passed) | Wordsmith, G-Research |

## Models and modes

| Feature | Page | Status | Targets |
|---|---|---|---|
| Model routing: Gemini by default, checked at boot | [models-and-routing](models-and-routing.md) | **built** (live boot check and small planner and fast calls pass; computer use on Gemini was run once on held-out households: 18 of 20, below its bar) | Wordsmith, HRT |
| Local model digests (a 7B model on this Mac) | [models-and-routing](models-and-routing.md) | **built** | HRT, G-Research |
| Spoken lines (ElevenLabs, fixed vocabulary) | [models-and-routing](models-and-routing.md) | **built** | Wordsmith |
| Mock mode: the whole product offline | [models-and-routing](models-and-routing.md) | **verified** | Wordsmith |

## Insights and admin

| Feature | Page | Status | Targets |
|---|---|---|---|
| Home: one sentence, one action | [home-insights](home-insights.md) | **built** (merged to main; measured on a prototype; owner has not used it) | G-Research |
| Top insights engine: a few pointers, chosen by code | [home-insights](home-insights.md) | **built** | G-Research, HRT |
| Admin views: Firm, Roles, Onboarding | [firm-admin](firm-admin.md) | **built** (UI merged to main; the firm is synthetic; owner request 4.4 (made-up people for several users): Track R found the cause of the blank live Admin view, the engine read this device's own ledger (one person); the page has the rest) | G-Research, HRT |
| Monday note, firm brief and prediction scorecard | [firm-admin](firm-admin.md) | **built** | HRT |

## Growth and independence

| Feature | Page | Status | Targets |
|---|---|---|---|
| Growth and the independence score | [growth-independence](growth-independence.md) | **built** (built; evaluated on simulated learners; no person has used it) | HRT, G-Research |

## A calm product: window, attention, context

| Feature | Page | Status | Targets |
|---|---|---|---|
| One attention layer: a router, a digest, quiet states | [attention-router](attention-router.md) | **built** (engine built; desktop wiring built; held-out simulated evaluation met 11 of 12 criteria) | HRT |
| Context engineering: typed, bounded, fresh | [context-engineering](context-engineering.md) | **built** | Wordsmith |
| One app, one window, one corner pill | [knack-shell](knack-shell.md) | **built** (merged to main; hidden end-to-end run passes; first visible launch with the owner pending) | Wordsmith |
| First run: role, three consents and a check | [knack-shell](knack-shell.md) | **built** (owner decision D58; on main since 02:39 UTC (d9f8929): a role screen, one consent card each for capture, screen glances and voice, and a 'Check it works' screen; the page has the rest) | G-Research |
| Command palette and keyboard | [knack-shell](knack-shell.md) | **built** (shortcuts and the palette are on main; some of the spec's palette verbs are not) | Wordsmith |
| Design system with budgets as tests | [design-system](design-system.md) | **built** (tokens, components and check scripts merged to main; screens still being brought to budget by their tracks) | G-Research |
| The Knack mark and brand | [design-system](design-system.md) | **built** | G-Research |

## Privacy and safety

| Feature | Page | Status | Targets |
|---|---|---|---|
| Egress guard, ledger and canary tests | [privacy-ledger](privacy-ledger.md) | **built** (built, with a known gap: older desktop paths are gated off by default but not re-reviewed independently) | G-Research, Wordsmith |
| Your data: see and delete | [your-data](your-data.md) | **built** (merged to main; owner has not used it) | G-Research |
| Memory file the worker owns | [your-data](your-data.md) | **built** | G-Research |

## Evidence and honesty

| Feature | Page | Status | Targets |
|---|---|---|---|
| Evidence page, make eval and the limitations register | [evidence-and-explain](evidence-and-explain.md) | **verified** | G-Research, HRT |
| Plain-English explainer with a number check | [evidence-and-explain](evidence-and-explain.md) | **built** | G-Research |
| Generator-mismatch test (the realism matrix) | [what-did-not-hold-up](what-did-not-hold-up.md) | **verified** | G-Research, HRT |
| ML v2, held-out: mostly negative | [what-did-not-hold-up](what-did-not-hold-up.md) | **verified** | HRT |
| The simulated study sat at the floor | [what-did-not-hold-up](what-did-not-hold-up.md) | **verified** | HRT, G-Research |
| Other results that went the wrong way | [what-did-not-hold-up](what-did-not-hold-up.md) | **verified** | G-Research |
| Prospective prediction ledger and forward scoring | [hrt-prospective-ledger](hrt-prospective-ledger.md) | **built** (decision D59; plan registered at 00:35 UTC before any held-out run; merged to main at 02:26 UTC (1984605) with the code, the held-out results, docs/HRT_BRIEF.md and the Evidence blocks; the page has the rest) | HRT |
| Drift guard: noticing when the model stops beating the baseline | [hrt-prospective-ledger](hrt-prospective-ledger.md) | **built** (as above: on main since 02:26 UTC) | HRT |
| Decisions scoreboard: realised cost against a naive policy and an oracle | [hrt-prospective-ledger](hrt-prospective-ledger.md) | **built** (as above: on main since 02:26 UTC) | HRT |
| Online recalibration: rescuing the model instead of discarding it | [hrt-prospective-ledger](hrt-prospective-ledger.md) | **built** (follow-up plan registered at 01:25 UTC after the first held-out result was seen (the plan says so), amended once (A1) after a dev run, frozen at 01:26 UTC, run once on new seeds; the page has the rest) | HRT |
| Ranges and sets: conformal intervals, and where their promise breaks | [hrt-prospective-ledger](hrt-prospective-ledger.md) | **built** (registered in evals/hrt/PLAN_CONFORMAL.md before any number existed, amended once (A1) after one dev run, run once on new seeds; on main since 02:26 UTC (1984605); the running product does not use it) | HRT |
| Decision value against prediction accuracy: did the better forecast buy a better decision? | [hrt-prospective-ledger](hrt-prospective-ledger.md) | **built** (registered in evals/hrt/PLAN_VALUE.md after the first held-out results (so the sign of the log-loss differences in the shifted worlds was already known; the decision claim V2 was not computed before); the page has the rest) | HRT |

## Roles

| Feature | Page | Status | Targets |
|---|---|---|---|
| Role packs: the format, and the deep benefits processor pack | [role-packs](role-packs.md) | **built** | G-Research, Wordsmith |
| Programmer pack at standard depth | [role-packs](role-packs.md) | **built** (ROLE-DEPTH (Track F), merged to main at 01:15 UTC (08b9908); docs/roles/programmer.md and packages/packs/programmer are on main; no study and no real traces; not seen end to end by the lead; the page has the rest) | G-Research, Wordsmith |
| Data analyst pack at standard depth | [role-packs](role-packs.md) | **built** (ROLE-DEPTH (Track F), merged to main at 01:15 UTC (08b9908); docs/roles/data-analyst.md and packages/packs/data-analyst are on main; no study and no real traces; not seen end to end by the lead; the page has the rest) | G-Research, Wordsmith |

## Also in this folder

- [video-beats.md](video-beats.md): 25 one-line claims with the proof shot, tagged teaser, demo or technical.
- [faq.md](faq.md): the 28 hardest judge questions with short, truthful answers.
