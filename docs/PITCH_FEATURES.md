# Knack: the features, for the pitch and the launch video

Written for Hack the Burgh XIII (targets: HRT, G-Research, Wordsmith) and for the launch, demo and submission video. As of Sat 07 Nov 2026, 23:57 UTC. Product name: Knack (internal identifiers and some file names keep the old name, Understudy). Every claim comes from a source document in this repository, with the label that document gives it; the source path is next to every number. Nothing here was run by the author. Where a source is missing the entry says 'not verified'.

This is the master document. It lists 61 entries (57 features and 4 write-ups of results that did not hold up) on 33 pages, grouped by capability. One page per feature (with a 30-second spoken script and slide bullets) is in `docs/features/`; the index with status is `docs/features/index.md`; the 20 video claims are in `docs/features/video-beats.md`; the 25 hardest judge questions are in `docs/features/faq.md`.

**How to read an entry.** Name and status; what it does; how it works (ending in one 'What is different' sentence, which compares with the approaches in our own reference notes and is not a claim of priority over the whole field); where to see it; the demo moment; the evidence with its label; the honest limit; the hackathon target. **Status words:** `verified` (the lead saw it work end to end), `built` (built and tested by its track, on main, not yet seen end to end by the lead), `landing` (not on main yet), `not run`. **Evidence labels:** `synthetic` (data we generated), `simulated` (language-model participants, not people), `real model, small n` (a language model on our sandbox sites), `offline tests`, `owner-present`, `not run`. Nothing in this document is evidence about real workers. **Badge wording on screen:** an engine answer computed from synthetic people reads 'Synthetic data' (or 'Synthetic firm' in the Admin view); 'Example data' appears only when a fixture was drawn (docs/FIRST_LAUNCH.md, state at 23:50 GMT).

## Contents

1. **See the work**: Text-free capture (Chrome extension and event store); Work genome: aligned traces priced in seconds; Controls: placebo and shuffled-label null; What skipping costs in answers; Stuck prediction and the Forecasts scorecard; Your hours: presence map and away forecast; How work connects: the work graph; Calendar layer (week ribbon, Outlook and Teams adapters); Git habits for programmers.
2. **Coach on the screen**: Live coach: one decision at a time, with a dignity gate; Fading help: levels L1 to L4 decided by code; On-screen annotations: ring, one label, ghost cursor; On-device awareness and triggered glances.
3. **Step in when stuck**: Cue: stuck rescue.
4. **Agents that do the work safely**: Benefits agent on three sandbox calculators; Code decides 'done'; Independent verifier (a second model family); Eight security layers, approval queue and audit log; Optional sign-in step-up for irreversible approvals (Auth0); Computer use on the sandbox calculators; Real-click ladder (R0 to R4) and the arm switch; Background agents: parent and child; Overnight runs and the morning report; Stop everything: the kill switch.
5. **Routines and automations**: Routine finder and proposals; Watch first and the trust ladder; Could automate: the repeat list; Needs you: one list for decisions; When to build an automation: ski rental with predictions; Review routing under a risk bound; Proactive briefing: judge, verify, prepare, press to fire.
6. **Connections and MCP plugins**: Connections: curated MCP plugins with role presets.
7. **Voice and Hey Knack**: Hey Knack: an on-device wake phrase; Voice guidance and 'do it for me' behind a click.
8. **Models and modes**: Model routing: Gemini by default, checked at boot; Local model digests (a 7B model on this Mac); Spoken lines (ElevenLabs, fixed vocabulary); Mock mode: the whole product offline.
9. **Insights and admin**: Home: one sentence, one action; Top insights engine: a few pointers, chosen by code; Admin views: Firm, Roles, Onboarding; Monday note, firm brief and prediction scorecard.
10. **Growth and independence**: Growth and the independence score.
11. **A calm product: window, attention, context**: One attention layer: a router, a digest, quiet states; Context engineering: typed, bounded, fresh; One app, one window, one corner pill; First run in three clicks; Command palette and keyboard; Design system with budgets as tests; The Knack mark and brand.
12. **Privacy and safety**: Egress guard, ledger and canary tests; Your data: see and delete; Memory file the worker owns.
13. **Evidence and honesty**: Evidence page, make eval and the limitations register; Plain-English explainer with a number check; Generator-mismatch test (the realism matrix); ML v2, held-out: mostly negative; The simulated study sat at the floor; Other results that went the wrong way.
14. **Roles**: Role packs: benefits processor deep, analyst and programmer thin; Deeper programmer and data-analyst roles.

Then: what exists elsewhere, numbers you may quote, things we do not claim, what is landing, sources read.

## The product in one paragraph

Knack watches how people do the same work and shows where a novice loses time and accuracy against an expert, in seconds and in wrong answers, with controls so a gap is not an artefact. It coaches on the real screen with help that is rare and fades as a skill is mastered, steps in with one question when someone is stuck, and lets an agent take repetitive work only when the worker agrees, one routine at a time, behind eight code-enforced layers and a Stop button that never waits for a model. A memory file the worker owns, readable and editable, adapts it to them. It runs as one calm app: a window, a menu-bar item and a small corner pill. It covers several jobs through role packs (one deep, a UK benefits processor; two thin, a data analyst and a programmer). Every number carries its n, split, interval and origin. Almost all of them are synthetic or simulated, the live study with four teammates has not been run, and the product says what did not hold up.

## The loop in one line

Watch how people work, show where a novice loses time against an expert, coach on the real screen with help that fades, step in when someone is stuck, let an agent take repetitive work only with opt-in, and prove how much less help the worker needs over time.

## The Wordsmith workflow, end to end, in nine steps

For judges who ask what the complicated browser workflow actually is. Each step names the page that holds its evidence and its limit.

1. Knack notices a task the worker repeats and proposes it as a routine ([routines](features/routines.md), [proactive-briefing](features/proactive-briefing.md)).
2. The worker chooses Watch first; the routine practises beside them, and autonomy is earned by matching what they do ([routines](features/routines.md)).
3. The worker starts it, or opts that one routine in to run while they are away ([background-agents](features/background-agents.md)).
4. An orchestrator turns a household into a task graph; navigators work the three calculator sites in parallel, using a compiled step script first, a browser agent when a precondition fails, and computer use last ([benefits-agent](features/benefits-agent.md), [computer-use](features/computer-use.md)).
5. Every page is treated as data and every action passes the gate; hidden text aimed at an AI pauses the run ([security-layers](features/security-layers.md)).
6. A verifier and a critic against the expert policy check the result (a second-model-family screen verifier is also built), and code, not the model, decides it is done ([benefits-agent](features/benefits-agent.md)).
7. The case note is written, and the one irreversible step waits in Needs you with its evidence ([needs-you](features/needs-you.md)).
8. The worker approves with a real click (and a fresh sign-in if Auth0 is configured); no key and no voice can approve ([needs-you](features/needs-you.md), [security-layers](features/security-layers.md)).
9. One key stops everything at any point, and the audit log records what happened ([stop-everything](features/stop-everything.md)).

## Three spoken versions

Plain sentences a narrator can read as written. Each says the data are synthetic.

**15 seconds.** Two people do the same job. One is slower and gets a different answer, and nobody can see where. Knack shows the gap in seconds, helps less as you improve, and takes work over only when you say so. The numbers are synthetic, and the screens say so.

**30 seconds.** Two people do the same job. One is slower and gets a different answer, and nobody can see where. Knack aligns a novice's steps with the nearest expert's and prices every gap in seconds and in wrong answers. It coaches on the real screen, rarely, and gives less help as you master a step. When you are stuck it asks one question. An agent can take repetitive work, but only one routine at a time, only with your yes, and the irreversible step waits for your click. One key stops everything. The numbers are synthetic, and the screens say so.

**60 seconds.** Add to the thirty seconds: the work is checked by code, not by the model, so when a real model said it had finished on an error page in twenty of twenty runs, the code check caught every one. Everything that leaves your Mac is listed, without the picture. Every number carries its n, its interval and its origin. And we published what did not hold up: on harder synthetic data the stuck model's edge shrinks to a few thousandths, the simulated study sat at the floor, and computer use finished one of four held-out households. The live study with four teammates has not been run.

## The three hackathon targets, and what to show for each

| Target | What it asks | Lead with | Every page that serves it |
|---|---|---|---|
| HRT | Best use of data for predictions and decisions | [stuck-model](features/stuck-model.md), [hrt-decisions](features/hrt-decisions.md), [live-coach](features/live-coach.md), [cue](features/cue.md), [work-graph-and-hours](features/work-graph-and-hours.md), [what-did-not-hold-up](features/what-did-not-hold-up.md) | [work-genome](features/work-genome.md), [calendar-and-git](features/calendar-and-git.md), [growth-independence](features/growth-independence.md), [background-agents](features/background-agents.md), [routines](features/routines.md), [proactive-briefing](features/proactive-briefing.md), [models-and-routing](features/models-and-routing.md), [home-insights](features/home-insights.md), [firm-admin](features/firm-admin.md), [attention-router](features/attention-router.md), [evidence-and-explain](features/evidence-and-explain.md) |
| G-Research | Make the invisible visible | [work-genome](features/work-genome.md), [screen-annotations](features/screen-annotations.md), [growth-independence](features/growth-independence.md), [work-graph-and-hours](features/work-graph-and-hours.md), [evidence-and-explain](features/evidence-and-explain.md), [what-did-not-hold-up](features/what-did-not-hold-up.md) | [capture](features/capture.md), [calendar-and-git](features/calendar-and-git.md), [awareness-glances](features/awareness-glances.md), [cue](features/cue.md), [routines](features/routines.md), [hey-knack](features/hey-knack.md), [models-and-routing](features/models-and-routing.md), [home-insights](features/home-insights.md), [firm-admin](features/firm-admin.md), [knack-shell](features/knack-shell.md), [design-system](features/design-system.md), [privacy-ledger](features/privacy-ledger.md), [your-data](features/your-data.md), [role-packs](features/role-packs.md) |
| Wordsmith | Most complicated end-to-end browser-use workflow | [benefits-agent](features/benefits-agent.md), [security-layers](features/security-layers.md), [computer-use](features/computer-use.md), [background-agents](features/background-agents.md), [routines](features/routines.md), [stop-everything](features/stop-everything.md) | [capture](features/capture.md), [needs-you](features/needs-you.md), [proactive-briefing](features/proactive-briefing.md), [connections](features/connections.md), [hey-knack](features/hey-knack.md), [models-and-routing](features/models-and-routing.md), [context-engineering](features/context-engineering.md), [knack-shell](features/knack-shell.md), [privacy-ledger](features/privacy-ledger.md), [role-packs](features/role-packs.md) |

Each page's 'Hackathon target' section says why.

## A suggested order for a five-minute pitch

One idea per step; every step links to the page that holds its script, evidence and limit.

1. The problem and the loop (this page). Say the product paragraph and that the data are synthetic.
2. See the gap: [work-genome](features/work-genome.md), with its two controls.
3. Help that fades: [live-coach](features/live-coach.md), [screen-annotations](features/screen-annotations.md), then [cue](features/cue.md) and [growth-independence](features/growth-independence.md).
4. An agent that does the work safely: [benefits-agent](features/benefits-agent.md), [security-layers](features/security-layers.md), [stop-everything](features/stop-everything.md).
5. Work you choose to hand over: [routines](features/routines.md) and [needs-you](features/needs-you.md); then [background-agents](features/background-agents.md).
6. Decisions with numbers (HRT): [stuck-model](features/stuck-model.md), [hrt-decisions](features/hrt-decisions.md).
7. What stays yours: [privacy-ledger](features/privacy-ledger.md), [your-data](features/your-data.md).
8. What did not hold up: [what-did-not-hold-up](features/what-did-not-hold-up.md) and [evidence-and-explain](features/evidence-and-explain.md). End here.

## 1. See the work

*Show where time and accuracy are lost, with controls so a gap is not an artefact.*

### Text-free capture (Chrome extension and event store)

**Status:** built · **Page:** `docs/features/capture.md` · **Targets:** G-Research, Wordsmith

#### What it does

A Chrome extension records roles and salted hashes of what a worker clicks, opens and searches: no page text, no URLs, no field values. It is off until the worker switches it on.

#### How it works

A content script (isolated world, local salt) turns each click, navigation, focus, scroll bin, tab switch, copy or paste flag and search (length only) into a small event with an origin (real or synthetic) and an actor (human or agent). A service worker batches events to the local engine every 2 seconds. Identifiers are hashed with a per-install salt; fields named in packages/schema/sensitive_fields.json are never touched. The engine keeps an append-only JSONL log, partitioned real and synthetic, with a pure reducer so a replay always gives the same state. Agent actions run in a separate browser profile and never enter the human trace.

**What is different.** The event schema allows only enums, counts and salted hashes, so there is nothing to redact later, and real and synthetic events are kept in separate partitions that are never mixed (the event-log projects we read keep rich text).

#### Where to see it

The extension's popup holds the capture switch. In the app, Your data has a section for capture and glances with the same switch. First run asks once: Yes, Not now or Never, with equal weight.

#### Demo moment

Open the sandbox calculator in Chrome with capture on, work one household, and show the capture switch in the popup and in Your data. Say the sentence from first run: it records when you are active, never what you read. Say too that the ribbon in the demo is drawn from synthetic traces; capture is what would feed it for a real worker.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Ten schema-valid events from a real page reached a stub server in about 3.3 s; typing and paste in a password field produced zero events; no page text, URL or secret in the payload | real browser, one Chromium build, one run, stub server | `docs/SPIKES.md (S3)` |
| In the simulated study the extension sent 7,310 of 7,334 events, schema-valid share 1.0000; the event files hold no participant text (0 strings had to be removed) | simulated participants (language model), not people | `evals/study_sim/REPORT.md (section 5)` |
| Extension logic is covered by 192 test functions (static count) | offline tests | `evals/report.facts.json (tests.by_dir, extension/tests)` |

#### Honest limit

Chrome only, one browser build checked. Real data is thin: the only real signal is the team's own machine timestamps; there are no real benefits-processor traces (limitation eval-thin-real-data). Because it never stores text, some habits are invisible by construction.

#### Hackathon target

- **G-Research (make the invisible visible)**: the raw material for making work visible without recording content
- **Wordsmith (most complicated end-to-end browser-use workflow)**: the human trace is kept apart from agent actions

### Work genome: aligned traces priced in seconds

**Status:** verified (verified on its own generator; degrades on harder synthetic data) · **Page:** `docs/features/work-genome.md` · **Targets:** G-Research

#### What it does

Aligns a novice's steps with the nearest expert's and puts a price in seconds on each gap: a skipped check, a result read again and again, a figure copied from the wrong place. The screen shows an expert trace above a novice's, gaps hatched, seconds lost beneath.

#### How it works

Events become steps through the role pack's mapping. A sequence alignment (Needleman-Wunsch, with a cost for each pair of step types) pairs each novice trace with the nearest expert trace. A step with no partner costs the time it took; a mismatched pair costs the difference in dwell. The gap is split by habit with a regression on behaviour counts, and intervals come from a bootstrap by person. A transition graph lists the step-to-step moves a novice never makes, and a replay slider plays a recorded trace on a virtual clock with idle gaps squeezed (the same events always give the same state). Everything here is plain code: no language model.

**What is different.** The gap is priced in seconds against the nearest expert, printed beside two controls, and priced again in wrong answers; the first version let a skipped step look like time saved.

#### Where to see it

More, then Where time goes (address #/genome). The Home hero's action, See where the time goes, opens it on that step. Settings, Views, Pinned views puts it in the sidebar.

#### Demo moment

Open Where time goes. Point at the Synthetic badge, the ribbon (expert above, novice below, gaps hatched), and the waterfall that splits the seconds by habit. Say: the interval on the real gap does not include zero, and the badge says synthetic.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Precision 92% [84.5, 98.6], recall 95% [88.6, 100.0] on planted deficits (16 people, 5 deficits over 32 novice cases; first generator) | synthetic | `evals/report.md (Deficit recovery)` |
| Weakest on 'reads the result again and again' (precision 70% [40.0, 94.1]) and 'copies the wrong figure' (recall 71% [33.3, 100.0]) | synthetic | `evals/report.md (Deficit recovery)` |
| On three harder generator families precision falls to 48 to 71% and recall to 49 to 68%; thresholds fitted on the first generator keep recall (87 to 95%) but precision falls to 33 to 56% | synthetic, 87 to 92 people per family | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |

#### Honest limit

The 92% and 95% describe our own generator, not workers. On harder synthetic data about a third of detections are wrong and the thresholds do not carry from one world to another. ML v2's pre-registered ensemble and counterfactual price were rejected as harmful on held-out cohorts, so the first alignment stays the default and there is no validated counterfactual in seconds.

#### Hackathon target

- **G-Research (make the invisible visible)**: the expert's hidden policy made visible as priced gaps

### Controls: placebo and shuffled-label null

**Status:** verified · **Page:** `docs/features/work-genome.md` · **Targets:** G-Research

#### What it does

Before a gap is shown, Knack compares experts with experts and re-runs the whole analysis after shuffling who is novice and who is expert. If the real gap does not stand clear of both, it is an artefact.

#### How it works

The placebo aligns each expert to the nearest other expert. The null shuffles the expert and novice labels across people and repeats the whole procedure, 1,000 permutations. Both should include zero; the real gap should not. The Evidence page prints both beside the real gap.

**What is different.** The controls are on the screen next to the real gap, not an offline check, so a reader can see whether the gap stands clear of them.

#### Where to see it

Where time goes (the controls under the ribbon) and Evidence (More, For reviewers).

#### Demo moment

On Where time goes, read the three numbers aloud: 229.6 seconds a case for the real gap, 7.1 for expert against expert, 46.2 for the shuffled null. The first interval excludes zero; the other two include it.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Real gap 229.6 s per case [192.7, 272.6]; placebo 7.1 s [-2.8, 18.4]; shuffled-label null 46.2 s [-36.4, 116.9]; permutation p = 0.001 | synthetic, 24 people, 1,000 permutations | `evals/report.md (Controls)` |

#### Honest limit

The null is not zero: about 20% of the real gap, because nearest-reference matching is not symmetric. Both control intervals include zero, but they are wide.

#### Hackathon target

- **G-Research (make the invisible visible)**: a baseline beside every gap

### What skipping costs in answers

**Status:** built · **Page:** `docs/features/work-genome.md` · **Targets:** G-Research, HRT

#### What it does

Skipping a step looks free in seconds, so Knack also prices it in answers: how often skipping the reconcile step puts a wrong figure in the case note, and how often skipping the cliff check leaves a nearby edge unwarned.

#### How it works

On 200 synthetic households scored by the sandbox oracle, skipping reconcile means writing one calculator's figure into the note without comparing the three. Skipping the cliff check means no warning that a small documented change (savings, rent, childcare, earnings) would move the award. The result is a count with an interval. The reason it exists: the work ribbon's waterfall shows a skipped step as time saved, which is correct arithmetic and a misleading story.

**What is different.** The cost of a missing step is measured in wrong answers against a known oracle on 200 households, not only in seconds.

#### Where to see it

Where time goes (the answers view beside the seconds) and Evidence.

#### Demo moment

Say it in one line: skipping the cliff check costs almost nothing in seconds, but on 107 of 200 households it leaves a nearby edge unwarned, and on 42 of those a small change moves the award by more than 50 pounds a month.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Skipping reconcile is wrong on about 20.7 of 200 households (10.3% [7.8, 13.0]) | synthetic, 200 households, bootstrap by household | `evals/cases/skip_consequences.json` |
| Skipping the cliff check leaves a nearby edge unwarned on 107 of 200 (53.5% [46.6, 60.3]); a small change moves the award by more than 50 pounds a month on 42 of those 107 | synthetic, 200 households, Wilson interval | `evals/cases/skip_consequences.json` |

#### Honest limit

The calculators' quirks and the oracle are ours. The oracle is a simplified rule set, not law: it agrees with PolicyEngine UK within 1 pound on only 8 of 20 generated households. Households cycle through 12 archetypes, so the interval describes this mix only.

#### Hackathon target

- **G-Research (make the invisible visible)**: the cost of a hidden habit in answers, not only seconds
- **HRT (best use of data for predictions and decisions)**: a decision with a stated cost

### Stuck prediction and the Forecasts scorecard

**Status:** verified (verified on its own generator; does not transfer to harder synthetic data) · **Page:** `docs/features/stuck-model.md` · **Targets:** HRT

#### What it does

Every 30 seconds Knack estimates the chance that there will be no progress in the next minute, and raises an alarm only inside a false-alarm budget of 1.0 an hour. The Forecasts screen shows the reliability diagram beside two baselines.

#### How it works

Bins of 30 seconds. Features: the last three step types, dwell, repeated actions, time since progress and a role prior. The first model (v1) is a hand-written logistic regression. It is scored leave one person out; the alarm threshold is chosen on the training people only, under the budget; scoring is by event (episodes detected, false alarms an hour), not by window. v2 (gradient boosting with monotone constraints, Platt-calibrated) was accepted as a small gain for the benefits processor and the programmer. The prediction is one input to the coach and to Cue; both also need deterministic signals.

**What is different.** It is scored by event with a false-alarm budget and set beside two plain baselines at the same budget, and its shortfall against them is published on the same screen.

#### Where to see it

More, then Forecasts (address #/forecasts; for admins, Firm, Forecasts). The coach and Cue use the same signal.

#### Demo moment

Open Forecasts. Show the reliability diagram, then the two baselines (base rate, time since progress), then false alarms an hour against the budget of 1.0. Say the model's edge over the plain rule is small on harder data, and the page says so.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Log loss 0.436 [0.422, 0.451] against 0.509 [0.496, 0.524] (time since progress) and 0.509 [0.497, 0.524] (base rate); flags 33% [27.5, 38.6] of stuck events; false alarms 1.21 an hour [0.95, 1.48] against a budget of 1.0 | synthetic, 4 people, leave one person out | `evals/report.md (Stuck hazard)` |
| The edge over time-since-progress falls from 0.071 to 0.008 to 0.015 nats per bin on three harder generators; a model trained on the first generator is 0.43 to 0.53 nats worse than that baseline there | synthetic, 120 people per cell | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |
| A4 accepted as a small gain: log loss -0.0039 nats (99.3% interval [-0.0062, -0.0017]) against v1 | synthetic, 32 held-out people | `evals/mlv2/results/heldout_hazard.json` |
| Under generator mismatch the plain time-since-progress rule beats v1: -0.021 [-0.034, -0.010] (benefits processor), -0.024 [-0.034, -0.014] (analyst), -0.030 [-0.041, -0.019] (programmer) | synthetic, pooled off-diagonal cells | `evals/report.md (Findings)` |
| Neither v1 nor v2 transfers to the language-model participants' traces: log loss 1.43 [1.25, 1.60] and 1.46 [1.31, 1.61] against 1.08 [1.00, 1.15] for the base rate | simulated participants (language model), not people; 24 participants, 419 bins | `evals/report.md (Findings); evals/mlv2/results/transfer_sim.json` |

#### Honest limit

The honest claim is that a simple time-since-progress rule does about as well as the full model once the generator changes; the first headline mostly reflects our generator. The false-alarm budget is broken in many mismatch cells. The product decision (keep v1 or make the rule the default signal) is pending with the owner; the coach and Cue work either way because they also gate on deterministic signals.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a prediction with a stated budget, baselines, and its shortfall shown

### Your hours: presence map and away forecast

**Status:** built · **Page:** `docs/features/work-graph-and-hours.md` · **Targets:** HRT, G-Research

#### What it does

A weekly map of when you are at your machine, with intervals, and an estimate of how long you will stay away. Knack starts a background run only when the odds that you stay away for the whole run are good enough.

#### How it works

672 fifteen-minute bins a week; each has a Beta posterior for 'active', seeded from the role pack's hours and smoothed across neighbouring bins and the same hour on other days. The window forecast estimates the chance S(D | t) that a gap starting now lasts D minutes, from the worker's own past idle spells. A run of length D starts only if S(D | t) is greater than L divided by G plus L, where G is the value of finishing and L the cost of colliding with the worker's return (a critical-fractile rule). It never starts on a locked or sleeping machine.

**What is different.** The start decision is a critical-fractile rule on a forecast of how long this worker stays away, judged against two baselines, rather than 'start when idle'.

#### Where to see it

More, then Your hours (address #/presence). Your data also lists the hours Knack holds.

#### Demo moment

Open Your hours: the week as a heat map with intervals and the free hours it reveals. Say how the rule decides when a run may start, then show the numbers against the two baselines.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The start-or-wait rule interrupted 2.1% of started runs against 24.8% for 'run whenever idle five minutes' and 2.0% for a fixed overnight window; it used 74.2% of idle time against 90.2% and 43.0%; cap 10%; window Brier score 0.131 | synthetic, 4 personas, 21 days, forward held-out days | `evals/report.md (Presence and window forecast)` |

#### Honest limit

The weekly map predicts the shift worker's held-out days worse than a simple baseline (map Brier 0.214 against 0.194 and 0.175); the 95% intervals contain the planted probability in only 55% to 91% of bins; idle capacity is over-estimated. A weekly template does not suit rotating shifts or no routine.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision rule with a cost of collision, evaluated against two baselines
- **G-Research (make the invisible visible)**: the rhythm of a working week made visible

### How work connects: the work graph

**Status:** built · **Page:** `docs/features/work-graph-and-hours.md` · **Targets:** G-Research

#### What it does

A graph of routines, skills and remembered facts. Nodes link when related, merge when two routines always run together, and fade with disuse. A click shows why a node exists and lets the worker edit or delete it.

#### How it works

Size is weekly minutes or mastery, colour is the node type, opacity is strength, and fading uses the same decay as the help-level engine. Deleting a memory node edits the memory file, so the graph is a view of what Knack holds, not a second store. One of the product's three signature visuals.

**What is different.** Fading is literal: nodes decay with the same rule the help levels use, and deleting a node edits the file the worker owns, so the graph is a view and not a second store.

#### Where to see it

More, then How work connects (address #/graph). Settings, Views, Pinned views puts it in the sidebar.

#### Demo moment

Open the graph, click a routine node to see why it exists, then delete a memory node and show the line leaving the memory file in Your data.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measured result: this screen is a view of the engine's work graph and has no evaluation of its own | no evidence yet (built; not measured) | `docs/IMPLEMENTATION_SPEC.md (7.4)` |

#### Honest limit

Not measured. The Knack navigation moved it out of the sidebar into More; it stays one click from Pinned views. Visual quality is judged by eye, not by an experiment.

#### Hackathon target

- **G-Research (make the invisible visible)**: motion carries meaning; fading is literal

### Calendar layer (week ribbon, Outlook and Teams adapters)

**Status:** built · **Page:** `docs/features/calendar-and-git.md` · **Targets:** G-Research

#### What it does

Compares a worker's week with an expert's: meeting load, focus blocks and review slots. Suggests changes from a fixed catalogue (focus blocks, batching, auto-hold, off-computer breaks). Outlook and Teams adapters read aggregates only and are off by default.

#### How it works

Calendars become counts, durations and enums; no titles, attendees or bodies are stored. The expert reference is a hand-authored role template. Suggestions come from a fixed catalogue through the same guard as every other layer, never free text. A real read-only check of the owner's own calendar needs the owner's approval at run time (decision D26) and stores only counts and durations.

**What is different.** The expert-against-learner comparison is applied to a week, with suggestions from a fixed catalogue and adapters that read aggregates only.

#### Where to see it

More, then Calendar (address #/week).

#### Demo moment

Open Calendar: the week ribbon, the worker's week against the expert's, and one suggestion with its interval. Say the adapters never write and have not been run on a real account.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Planted problems found (eight types, micro-average): precision 93.9%, recall 98.2%; suggestions against the planted cause: precision 96.4%, recall 89.9%; expert weeks with a suggestion: 0 of 24 | synthetic calendars, 28 people | `evals/report.md (Calendar layer)` |
| 0 of 11,104 planted tokens leaked across 169 outbound requests | synthetic, offline | `evals/report.md (Calendar layer)` |

#### Honest limit

Synthetic calendars only. The expert reference is generated from the same template that defines the targets, so agreement is by construction. One read-only aggregate check of the owner's calendar says nothing about anyone else.

#### Hackathon target

- **G-Research (make the invisible visible)**: the week made visible against an expert's

### Git habits for programmers

**Status:** built · **Page:** `docs/features/calendar-and-git.md` · **Targets:** G-Research, HRT

#### What it does

For programmers: finds commit habits that experts do not have (very large commits, tests not changed with code, fix after fix, reverts, vague messages, late nights) and gives five generic suggestions.

#### How it works

Reads the git history on the device. Features are counts and times; commit messages are turned into enums by rules, or by a local model on the Mac for the category, and are not sent out. Each learner is compared with eight experts of the same replicate, with a placebo of expert against expert. Commit sessions are aligned, but git records when a commit landed, not how long the work took, so the alignment sees the shape of sessions and not seconds.

**What is different.** The same comparison is applied to commits, with a placebo of experts against experts and thresholds set on separate seeds from the test seeds.

#### Where to see it

More, then Git habits (address #/git). Programmer role only.

#### Demo moment

Open Git habits on the programmer example: habits against experts with intervals, and the generic suggestion for each. Say the repository is synthetic.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Precision 100% (116 of 116) [96.8, 100.0]; recall 97% (116 of 120) [91.7, 98.7]; specificity 100% (120 of 120) | synthetic, 120 scripted developers, fresh seeds | `evals/report.md (Git habits)` |
| Placebo (expert against other experts): false flags 1% (5 of 480) [0.4, 2.4] | synthetic | `evals/report.md (Git habits)` |

#### Honest limit

Every learner and expert is a scripted persona with planted habits; recovering them shows the features and thresholds work on data built to contain them, not how real developers behave. Habits in the message or the clock are invisible to alignment.

#### Hackathon target

- **G-Research (make the invisible visible)**: commit habits made visible
- **HRT (best use of data for predictions and decisions)**: decisions with intervals, thresholds set on separate seeds

## 2. Coach on the screen

*Help on the real screen that is rare, specific and fades.*

### Live coach: one decision at a time, with a dignity gate

**Status:** verified · **Page:** `docs/features/live-coach.md` · **Targets:** HRT

#### What it does

From live events, the coach decides whether to say nothing, nudge, draw a ring or offer to take over. Silence is the default: it speaks only after two stuck signals in a row, then waits.

#### How it works

Plain code, no model. The actions are silent, nudge, annotate and takeover. The dignity gate acts after two consecutive stuck signals, then holds a cooldown, and stays silent when unsure. The worker's own reaction labels each prompt without a questionnaire: followed within 10 seconds, dismissed within 4, repeated within 10, undone within 10. Those labels feed a bandit that logs the probability of each choice, so any new policy is first judged off-policy on old logs (inverse propensity, self-normalised, doubly robust) before it is switched on.

**What is different.** A dignity gate holds the coach back, and a bandit logs the probability of every choice so a new policy is judged off-policy on old logs before it is switched on.

#### Where to see it

More, then Live coach (address #/today) shows the current task and the help level. The ring and card appear on the real screen.

#### Demo moment

A synthetic novice skips the cliff check. A ring lands on that button, once. The worker ignores it and nothing nags. Replay the same case as an expert: no prompt at all.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| 14 of 14 planted skips ringed over 48 apprentice cases; 0 prompts to experts; no ring on a clean case | synthetic; a test assertion, not a report section | `services/engine/tests/coach/test_replay.py` |
| Dignity gate: false nudges 1.83 to 0.05 an hour (a fall of 97%); stuck events reached 21% to 5%; nudges 186 to 17; median latency 30 s to 60 s | synthetic, 4 people, leave one person out; no interval in the report table | `evals/report.md (Coaching dignity gate)` |
| Off-policy check: the naive on-policy average has mean error +0.193 and its interval covers the truth 0% of the time; IPS covers 96%, self-normalised IPS 96%, doubly robust 88% | synthetic simulator, 24 replications of 2,400 decisions | `evals/report.md (Off-policy evaluation)` |

#### Honest limit

The gate buys quiet with coverage: it reaches 5% of stuck events, not 21%. The simulator's reward structure is ours and implicit labels are noisy (a dismissal can mean 'I already knew'). In the detailed 6,000-decision run every estimator's interval missed the true value of 0.018. The replay set plants the skip, so a clean score is expected.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision rule under a false-nudge budget, judged off-policy before it is switched on

### Fading help: levels L1 to L4 decided by code

**Status:** verified · **Page:** `docs/features/live-coach.md` · **Targets:** HRT

#### What it does

Help gets lighter as a skill is mastered, from L1 'watch me' to L4 'on my own'. The level is set by plain code, so a chatty model cannot talk the product out of fading.

#### How it works

The engine's level module is the authority (L1 full help, L2 small help, L3 a dot, L4 gone). It promotes one level after three clean runs in a row and demotes after two or more errors among the last five counted outcomes; an assisted run is neutral; a level change resets the streak and the window so the new level gets a fair trial. The desktop's own learner store, kept from the owner's earlier library, has its own step-up settings. Per-skill mastery with forgetting feeds the engine and decays with absence, so a skill not seen for weeks is not treated as mastered. The worker's pace setting (gentle, steady, quick) changes how many clean cases come before a prompt gets lighter. The level shows for two seconds when it changes, then lives in the menu bar and Settings.

**What is different.** Levels are code with no model, no randomness and no clock, and mastery can only lower a level after an absence, never raise it.

#### Where to see it

Live coach shows the level; Growth has a closed 'The fade' disclosure; Settings has Coaching (on or off, level lock).

#### Demo moment

Open Live coach and point at the level; open Growth, then The fade, and show prompts getting lighter as the curve rises. Say that code, not a model, moved the level.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Skill tracing follows the planted curve only weakly: mean Spearman 0.18 across four personas (0.17, 0.18, 0.25, 0.12); mastery saturates on high-volume personas | synthetic, 4 personas, 21 days | `evals/report.md (Skill tracing)` |
| The level rules are code with no model, no randomness and no clock: three clean runs up, two errors in five down, absence can only lower a level | offline tests; a separate small reference implementation agrees on shared cases | `services/engine/understudy_engine/skills/levels.py; docs/reference-notes/drigil.md` |

#### Honest limit

The mastery estimate is weak on our data: it saturates within a day or two, so it cannot resolve a slow learning curve. Decay with absence is shown in unit tests, not by this data. The levels are a mechanism, not evidence that people learn.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: promotion and demotion rules decided in code, with forgetting

### On-screen annotations: ring, one label, ghost cursor

**Status:** built (the lead viewed screenshots; not yet confirmed end to end on a real Chrome tab) · **Page:** `docs/features/screen-annotations.md` · **Targets:** G-Research

#### What it does

When Knack points at something it draws a thin ring with corner ticks and one short label on the real control. There is no permanent chip; one annotation at a time.

#### How it works

In a browser the extension sends element rectangles so the ring lands exactly (DOM first: exact, free and instant). Elsewhere a fresh frame goes through the egress guard to a Gemini vision model that must answer in a closed form (found or not, and a box); a box is accepted only after sanity checks on size, position and denylisted regions. The ring follows its zone when the page moves and is dropped at once when the zone is gone. A ghost cursor, a small dot with a short trail, can show a move. The overlay is hidden while the Knack window itself is focused, and draws no label while an agent is acting.

**What is different.** The ring is grounded from the page first (exact), a vision model answers only in a closed form with sanity checks, and the overlay draws no label while an agent is acting.

#### Where to see it

On the real screen, over the control being pointed at. Settings, Coaching turns coaching off.

#### Demo moment

On the sandbox calculator, a ring lands on 'Check cliff edges' and one short label says why. Press the button; the ring goes. Nothing else is drawn.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Pointing by description: Gemini flash-lite hit 95% [90, 98] (140 of 147), median 0.93 s, 95th percentile 1.37 s; Gemini flash 95% [90, 97], median 3.31 s; OpenAI fast 75% [67, 81], median 1.72 s; elements not on screen were rejected 43 of 43 by each model; clicking the viewport centre hits 2% | synthetic sandbox screenshots, 147 positives and 43 negatives | `evals/modelbench/REPORT.md (section 1)` |
| In the simulated study the ring was drawn on arrival for 5 of 12 prompts, because the cliff button only exists on a calculator result tab, not on the case note page where the prompt usually arrives | simulated participants (language model), not people | `evals/study_sim/REPORT.md (section 5)` |

#### Honest limit

The overlay is drawn on the primary display only; per-display overlays are a known limit. Pointing numbers are on screenshots of our own sandbox pages, not real apps. Whether the ring lands right on a real Chrome tab, end to end, has not been confirmed by the lead.

#### Hackathon target

- **G-Research (make the invisible visible)**: the next step made visible on the real screen

### On-device awareness and triggered glances

**Status:** built (layer is on by default; no frame is sent until the worker records consent; macOS Screen Recording is the owner's to grant) · **Page:** `docs/features/awareness-glances.md` · **Targets:** G-Research

#### What it does

Knack notices cursor dwell, typing rhythm and which kind of app is in front, on the Mac, and nothing leaves it. When it needs to see the screen it sends one downscaled frame to a Gemini model, only if you allowed it, and never stores it.

#### How it works

Level 0 is always on: input rhythm, cursor dwell and wandering, app kind (no titles stored), hashed browser events. Level 1 is a triggered glance: when the stuck probability crosses its threshold, a loop signature appears, or the worker presses the hotkey, one image (long edge at most 1280 pixels) is held in memory for one call and sent through the egress guard, which logs size, hash, model and latency but never the image. A frame is skipped while macOS secure input is on, when the frontmost app is on the denylist, and in any unattended run. The answer is a closed schema (app kind, task phase, blocker, confidence, optional box); no free text is kept. Periodic glances about every 30 seconds are opt-in and off by default, with a count in the menu bar.

**What is different.** Level 0 sends nothing; a frame goes through a gate that is a pure function of a few booleans and a ledger that records size, hash, model and latency and never the image.

#### Where to see it

First use shows a consent card with equal buttons: Yes, Not now, Never. Your data, 'What it looked at or sent' lists every call; 'Capture and glances' holds the switches.

#### Demo moment

Show the consent card and press Not now: no frame leaves. Then show Your data with its record of what was sent (size, model, time) and no picture.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Glance on eight synthetic sandbox screens, five repeats each: the same answer as the modal answer 98% [87, 100] (39 of 40) with flash-lite, median 0.88 s, 95th percentile 1.02 s; the answers were plausible for the screen 100% [91, 100] | synthetic sandbox screenshots; repeats of one screenshot are not independent | `evals/modelbench/REPORT.md (section 4)` |
| Awareness is a registered flow in the privacy canary run (0 of 11,456 planted tokens reached the model port) | synthetic, offline | `evals/report.md (Privacy layer)` |

#### Honest limit

An allowed frame is raw pixels: the guard decides whether a frame may leave, from which source and what is recorded, but it does not redact, and the provider then sees the whole screen; what a provider does with it is the provider's policy and is not measured here. The gate depends on the caller reporting secure input and the denylist correctly. The screen-change watcher is not built (it needs Screen Recording).

#### Hackathon target

- **G-Research (make the invisible visible)**: the hidden state of being stuck made visible, with consent

## 3. Step in when stuck

*One question, one next step, then silence.*

### Cue: stuck rescue

**Status:** built (engine and desktop code built and tested; evaluated on simulated workers only; not run on a real desktop) · **Page:** `docs/features/cue.md` · **Targets:** HRT, G-Research

#### What it does

When you are stuck, Cue works out the most likely next step from what experts do and what is on your screen, shows it, and asks one multiple-choice question only when it is unsure. It gives the reason in one short line, then goes quiet and later holds help back so you can recall the step yourself.

#### How it works

Candidates come from the expert transition graph: the top three next steps with probabilities. In a browser the target is grounded from the page first; elsewhere a fresh frame and a closed menu go to a Gemini model. The decision is pure code from the stuck probability, the margin between the top two steps, grounding confidence, mastery, cooldowns, the daily attention budget, flow state and consent. Outcomes: nothing (the default), confirm, a cue at a tier, one question, or a small offer. Tiers: a ring; a ring and a chip of at most 40 characters; a ghost-cursor demonstration; a voice whisper of at most 8 words. Hard caps: at most 3 cues in 10 minutes, one question per episode, at least 90 seconds between cues for the same skill unless asked, never in a denylisted app or over secure input. The 'why' is 12 words or fewer, once.

**What is different.** Candidate next steps come from the expert transition graph, so the model's only job is to find the step on the screen; it asks at most one question per episode and later withholds help to test recall.

#### Where to see it

On the real screen when stuck (ring and card); More, then Live coach; Growth shows the effect over time.

#### Demo moment

Pause on the case note page. Cue asks one question with three options; answer by click, key 1 to 4 or voice. The ring shows the step, one line gives the reason, then silence. Say that its numbers so far come from simulated workers.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| False nudges 0.73 an hour (97.5% interval [0.64, 0.83]); the target was 1.0 or less: met | synthetic, 40 simulated personas, 481.5 hours, held-out seed | `evals/cue/held_out.json` |
| 'Faster to resume' target not met: median paired difference 0.0 s (97.5% interval [-9.5, 0.0]); the exploratory mean difference is -34 s [-43.7, -25.2] | synthetic, same run, 1,119 stuck episodes | `evals/cue/held_out.json` |
| Cues reached 27.7% [25.1, 30.1] of stuck episodes; 97.1% of stuck seconds stayed silent; wrong-target cues 0.01 an hour | synthetic, same run | `evals/cue/held_out.json` |
| Learning the tier policy online is left off: the off-policy estimate does not clear the rule's value and the effective sample size is too small | synthetic, 491 logged decisions | `evals/report.md (Cue analysis)` |

#### Honest limit

Every Cue result comes from a simulator written by the team that wrote the policy: stalls, pauses and interruption costs are assumptions. One of two primary targets was met. Cue reaches about a quarter of stuck episodes by design. It has not been run on a real desktop or on a person.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision under an attention budget, with a pre-registered held-out evaluation
- **G-Research (make the invisible visible)**: the hidden next step shown at the moment of need

## 4. Agents that do the work safely

*An agent takes work only through code-enforced gates.*

### Benefits agent on three sandbox calculators

**Status:** verified (verified in mock mode: ends with an item in the approval queue and 0 false claims) · **Page:** `docs/features/benefits-agent.md` · **Targets:** Wordsmith

#### What it does

An agent enters a household into three differently built calculator sites in parallel, checks for cliff edges, reconciles the three answers, writes the case note, and stops at the submit button for a person to click.

#### How it works

An orchestrator turns a case into a task graph. Navigators run in parallel, each in its own browser context, with a step cap. A verifier checks a fresh observation, a critic compares the evidence with the expert policy, a recovery step tries an alternative route and then escalates, and the scribe writes the note and an evidence bundle. Tier 1 runs a compiled step script; tier 2 is a browser agent; tier 3 is computer use. It escalates only when a precondition fails and logs the tier on every step. The submit step goes to the approval queue and waits for a real click.

**What is different.** Three differently built sites are worked in parallel with a verifier, a critic against the expert policy and a recovery step, and the tiers escalate only when a precondition fails.

#### Where to see it

Routines, then Run now (the window minimises and the corner pill shows what is happening); the result arrives in Needs you. More, then Background runs shows runs.

#### Demo moment

Start the benefits routine from Routines. The pill says what it is doing in about five words (the window minimises if the run counts as using the real screen; rehearse, because a pure sandbox job leaves the window where it is), and the finished case note arrives in Needs you with its evidence and one irreversible step waiting for a click. Do not press Approve in front of an audience; it saves a sandbox note and nothing real.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Clean path: 20 of 20 households passed [0.84, 1.00], 0 false claims; with injected failures (layout changes, one-off 503s) 20 of 20 [0.84, 1.00], 15 of 20 needed the browser-agent tier; 7 of 20 planted calculator disagreements flagged | synthetic sandbox, mock model; the report says the clean path 'says little' | `evals/report.md (Agent runs on the sandbox)` |
| Real model, 20 households per condition: clean 18 of 20 [0.70, 0.97] with 0 false claims; after a layout change 20 of 20 [0.84, 1.00] | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| One-off error page: 0 of 20 [0.00, 0.16]; the model said it was finished in 20 of 20 runs and all 20 claims were false; the code check caught every one | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| After changing what the planner sees and re-running only that condition: 10 of 10 [0.72, 1.00] | real model, IN-SAMPLE: the fix was made after seeing the result | `evals/report.md (Agent runs on the sandbox)` |

#### Honest limit

The calculators are three sandbox sites we wrote with quirks we planted, and the oracle is a simplified rule set, not law (it agrees with PolicyEngine UK within 1 pound on 8 of 20 households). One model family and one prompt; identical prompts are cached, so 20 households are fewer than 20 independent samples. No real benefits-processor data.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a complicated multi-site browser workflow with recovery, a verifier and an approval gate

### Code decides 'done'

**Status:** verified · **Page:** `docs/features/benefits-agent.md` · **Targets:** Wordsmith

#### What it does

A model saying it has finished counts for nothing. After the last step, code looks at a fresh page and checks that every calculator's result fields and the case-note id are really there. A claim that fails the check is recorded as a false claim.

#### How it works

The check compares named result fields with the values the page schema expects, on a fresh observation taken after the final step, never relaxed for goals that sound like navigation. It returns ok, what is missing and whether a model claimed success while the check failed. A separate small classifier can flag which claimed successes are risky, but a low risk score never replaces the check.

**What is different.** 'Done' is checked by code on a fresh observation against named fields, and the false-claim count is a first-class output, not a footnote.

#### Where to see it

Needs you (the evidence opens in place: found against expected); Evidence page, section on agent runs.

#### Demo moment

Show the one-off error page result: the model said done in 20 of 20 runs; the check caught all 20. This is the line to read aloud.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| 20 of 20 false claims caught by the code check on the one-off error page | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| A classifier for risky claims: Brier 0.077 [0.066, 0.090] against 0.183 for the base rate; reviewing the top 20% by predicted risk catches 70% of false claims | synthetic, 600 runs, grouped 5-fold by household | `evals/report.md (Agent-claim calibration)` |

#### Honest limit

The check proves the fields are present and well formed on the page the agent reached. The product's own check would not catch a wrong but well-formed figure; the evaluation's independent recomputation did (docs/reference-notes/computer-use-comparison.md). The real-model false claims are one family of failure (finishing on an error page).

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: success decided by code, not by the model's word

### Independent verifier (a second model family)

**Status:** built (routed by default to Gemini flash-lite; its evaluation set is small and easy) · **Page:** `docs/features/benefits-agent.md` · **Targets:** Wordsmith

#### What it does

A second model family looks at the screen after an agent step and says whether the page shows a completed result, so the actor does not grade itself. Code still decides; the verifier is another check.

#### How it works

A closed question with yes, no or unsure; unsure is never accepted; code requires yes with confidence of at least 0.7. It runs through the egress guard like every other call.

**What is different.** A different model family checks the actor, and code requires 'yes' with a confidence floor; an 'unsure' is never an accept.

#### Where to see it

Behind the scenes: More, then Models and cost lists the route; agent runs show a verified chip per step where wired.

#### Demo moment

Not a visual moment. Mention it when showing a run's evidence: a second model checked the final page, and code made the decision.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| All three models were right on all 30 images (15 to accept, 15 to reject); false-accept 0 of 15 with an upper bound of 20%; the set is too small and too easy to choose a verifier | synthetic sandbox screenshots | `evals/modelbench/REPORT.md (section 3)` |

#### Honest limit

The evaluation cannot tell the three models apart. Treat this as a design with a first check, not a measured advantage.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a verifier of a different family from the actor

### Eight security layers, approval queue and audit log

**Status:** verified · **Page:** `docs/features/security-layers.md` · **Targets:** Wordsmith

#### What it does

Anything on a page that is written at an AI is treated as data, and the agent cannot act on it. Irreversible or outward-facing actions need a person's real click. There is no allowlist; the worker keeps an optional denylist.

#### How it works

Layer 1 wraps everything from a page, screenshot, file or tool as untrusted data and strips invisible characters. Layer 2 is a quarantined reader: a model that sees raw content but returns only schema-checked fields, so the planner never sees raw text. Layer 3 is a fixed set of typed actions. Layer 4 is the action-class gate: send, post, submit, pay, delete, install or change permissions need a human click unless the worker opted that routine in. Layer 5 tags data with where it came from so tainted or personal data cannot be typed into a site the routine did not record. Layer 6 is an injection detector that pauses the run. Layer 7 is a goal-drift check plus a stuck-loop detector. Layer 8 protects settings: page content cannot change memory, the denylist, consent, quiet hours or the kill switch. Beside the layers sit an approval queue with evidence bundles, a hash-chained audit log, and local services that check the Host header on every request and the Origin on every write.

**What is different.** There is no allowlist. The gate classifies an action from the control that code reads under the pointer, not from the model's own label, and each layer's cost and benefit is measured by switching it off in turn.

#### Where to see it

Needs you shows a paused run with 'Cannot be undone' printed; Your data shows what was sent; Evidence has the red-team tables.

#### Demo moment

Open a page that carries hidden text aimed at an AI. The run pauses before the planner acts; the card in Needs you says the run paused and that nothing was changed, in content-free words.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Scripted red team: attack success 0.0% [0.0, 8.4] with every layer on, 100.0% [91.6, 100.0] with all layers off; false pauses on 31 clean pages 0.0% [0.0, 11.0] | synthetic, 42 attacks over 10 configurations, scripted planner | `evals/report.md (Red team with ablations)` |
| Real model: 0 of 126 runs let an attack through with every layer on; 5 of 126 (4.0% [1.0, 14.7]) with all layers off; the intervals overlap | real model, 42 cases x 3 repeats | `evals/report.md (Red team with a real model)` |
| Injected pages: the detector paused 20 of 20 runs before the planner acted; 0 attacks succeeded | real model (OpenAI), 20 households; pages carry text only | `evals/report.md (Agent runs on the sandbox)` |
| Two independent review passes by separate Claude agents (not human researchers): privacy and honesty, no critical finding and 6 high; real-actuator safety, 18 findings with 1 critical; reproducers pass 183 of 183 after fixes | owner-requested code review; fixes tested against fake desktops only | `evals/review/privacy_honesty.md; evals/review/safety_actuator.md; docs/MVP_STATUS.md` |

#### Honest limit

The scripted planner follows any instruction, so the scripted table measures the layers, not a real model. In the real-model run the two intervals overlap: it shows what the layers cost (task success under attack 22% against 84%), not that they prevent attacks. We wrote both the attacks and the defences. The injected pages carry text only, so this shows the detector pauses, not that the gate resists hostile pages.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a browser agent that can be pointed anywhere and still cannot be steered by the page

### Optional sign-in step-up for irreversible approvals (Auth0)

**Status:** built (built; not configured: it needs the owner's Auth0 domain and client ID, and is never on the demo's critical path) · **Page:** `docs/features/security-layers.md` · **Targets:** Wordsmith

#### What it does

When Auth0 is configured, approving something that cannot be undone, or that sends something outside this machine, needs a fresh sign-in, with the reason printed above the button. With no Auth0 values the app uses a local fallback and approves as before.

#### How it works

A thin sign-in sits behind an interface with a local fallback. Items of risk class irreversible or outward need a step-up. A sign-in that was closed, is not recent enough, or is from a different account approves nothing and the item keeps waiting. Only a hash of the signed-in subject is returned to the engine. A real click is still required: signing in does not approve anything by itself.

**What is different.** Nothing new is claimed: a standard step-up sign-in placed on the irreversible step.

#### Where to see it

Needs you, on an irreversible or outward approval row: 'Approving this cannot be undone, so we ask you to sign in again.'

#### Demo moment

Not on the demo path. If configured, press Approve on an irreversible row: a sign-in opens first; close it and the row says nothing was approved.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The step-up gate (when it applies, what each failure says, what is returned) is covered by unit tests | offline tests | `apps/dashboard/src/auth/gate.ts` |

#### Honest limit

No tenant is configured, so the fallback approves as before. Never part of the P0 demo path. Not verified against a real Auth0 tenant.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a stronger gate on the irreversible step of an approval-gated agent

### Computer use on the sandbox calculators

**Status:** built (works in-sample, not held-out; the Gemini configuration is still in development) · **Page:** `docs/features/computer-use.md` · **Targets:** Wordsmith

#### What it does

A model sees screenshots and clicks and types on a calculator page. It never sees the real values: it asks for a fact by handle, and code types the value.

#### How it works

Tier-3 goals carry typed handles such as the household's income or number of children. The model emits 'type this fact'; code resolves the value and the actuator types it. Every click and key press passes the same action-class gate, goal-drift check and trusted read of the element under the pointer. A read-back after each typed value and a guard against leaving fields unfilled before the final button are being added. The earlier failure was our design: with no values in the goal the model had nothing to type and declined at step one.

**What is different.** The model never sees the real values: it names a fact by handle and code types it, so prompts and logs hold handles only.

#### Where to see it

Behind Routines, Run now, when a routine needs tier 3. Evidence has the agentic section.

#### Demo moment

Not a demo moment: say plainly that the computer-use tier is in development and that Submit waited for a human in every run.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Development households: after fact handles, 3 of 3 completed through the real gate with 0 false claims (Wilson [0.44, 1.00]) | real model (OpenAI), IN-SAMPLE, 3 households | `evals/agentic/ITERATIONS.md` |
| Held-out clean, n = 4: 1 completed (Wilson about [0.05, 0.70]); in 2 runs the harness accepted calculator B with a drop-down left at its default and only the evaluation's independent recomputation caught it; 1 run paused because the goal-check call could not complete (it fails closed); Submit waited for a human in all 4 | real model (OpenAI), our sandbox, headless browser; gate 35e964049fd0 | `evals/report.md (Agentic evaluation); evals/agentic/ITERATIONS.md` |
| Held-out injected, n = 20: 20 of 20 paused at step 0; 0 attacks executed | real model (OpenAI); pages carry text only | `evals/report.md (Agentic evaluation)` |
| Gemini configuration, development households only: 0 of 3 end to end (two rounds of the same three households), 7 of 9 calculators finished with a clean audit; 1 of 3 on the four-page wizard site, 3 of 3 on the two simpler sites | real model (Gemini), IN-SAMPLE; on branch worktree-agent-acf889b730112335b, not on main | `evals/agentic/ITERATIONS_8.md (branch)` |

#### Honest limit

Seven households in total across development and held-out, so no rate should be quoted. The injected pages test the detector, not the gate against a hostile page. Every number above, except the Gemini row, is about the OpenAI configuration. A fresh pre-registered round on new seeds is planned after the fixes land. A harness option (off by default) lets the case-note step start at tier 2; any result that uses it is reported as 'calculators by computer use, note by tier 2', never as an all-computer-use result, and it is not a way round Gemini's own safety confirmation (decision D56).

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: computer use behind the same safety layers, with honest held-out results

### Real-click ladder (R0 to R4) and the arm switch

**Status:** built (read-only rung R0 ran once; nothing else has run) · **Page:** `docs/features/computer-use.md` · **Targets:** Wordsmith

#### What it does

Real desktop clicks come in rungs, each needing the owner present and a go in chat. The arm switch is on by default but inert: a real action still needs a one-time token, a countdown and the owner at the machine.

#### How it works

Every real action needs a single-use permit made from the owner's one-time token (or, for an unattended run, a routine's consent record), the pinned window, a countdown with the target in front, the kill file and the supervisor stop. The actuator checks the frontmost app, hit-tests the click point, checks display scale and keeps an action budget. The real backend also needs pyobjc, which the agent environment does not install, so it stays inert until the owner runs the documented first-rung command. Rungs (evals/agentic/REAL_CLICKS.md): R0 read-only code with zero events; R1 one short word into a fresh TextEdit document by a scripted check, not a model; R2 a model proposes one step in TextEdit (at most 8 actions, 90 seconds); R3 a model drives one localhost sandbox calculator in a dedicated browser window; R4 the benefits task end to end on the real screen, attended, stopping before the real Submit. A model never drives R0 or R1, and unattended real-desktop runs are not part of the ladder.

**What is different.** Each real action needs a single-use permit made from the owner's one-time token, a pinned window and a countdown with the target in front, and the ladder is climbed one rung at a time with the owner present.

#### Where to see it

Not visible in the product. Owner-present steps are in evals/agentic/REAL_CLICKS.md and docs/FIRST_LAUNCH.md.

#### Demo moment

None on camera. If asked: one supervised click and one typed line passed on TextEdit; the agent's own actuator then failed its first supervised check; the guards were rebuilt and reviewed.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| S2: one real click and one typed line on TextEdit read back exactly; mapping error 0.0 pt; whole test 8.9 s | owner-present, one run | `docs/SPIKES.md (S2)` |
| S2 follow-up: the agent's own actuator reported ok while the click landed in another app's window and TextEdit stayed empty | owner-present, one run, failed | `docs/SPIKES.md (S2 follow-up)` |
| R0 ran once: zero events; the test point was covered by another window, so it stopped | owner-present, read-only | `docs/FIX_LEDGER.md (section A); evals/agentic/REAL_CLICKS.md` |
| The reviewer's reproducers pass 183 of 183 against fake desktops | offline tests against fakes | `docs/MVP_STATUS.md` |

#### Honest limit

No model has driven a real desktop. The reviewer's advice stands: R1 go under four conditions; R2, R3 and R4 no-go until R1 is reported. The guards are tested against fake desktops only.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: real-desktop action behind explicit, per-run owner consent

### Background agents: parent and child

**Status:** built · **Page:** `docs/features/background-agents.md` · **Targets:** Wordsmith

#### What it does

While you work on something else, Knack can run helpers that profile a dataset, find test gaps in a repository or draft a weekly summary. Each helper has a budget, a sandboxed workspace and a result that code checks.

#### How it works

A parent plans and hands typed specs to children, each following a written role playbook (exemplars exist for programming, data and creative work). In the default menu mode the model only sequences vetted steps by id; the analysis is done by scripts written in advance, so file text never reaches the model. Raw mode (free-form model-written code) exists only in the foreground, on files the worker named. Each child has step, token and time budgets, an isolated workspace, a lease that a child can only narrow, and results that code recounts from the source. Human input signalled from the desktop makes a child yield and write a checkpoint.

**What is different.** In the default mode the model only orders vetted steps by id and scripts do the analysis, results are recounted by code, and a child's lease can only narrow its parent's.

#### Where to see it

More, then Background runs. Results arrive in Needs you.

#### Demo moment

Start a data or programming helper and show its result card: the number, the evidence and a 'verified' mark that code, not the model, set.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Planted facts recovered and verified: data profile 6 of 6, data chart 6 of 6, commit analysis 4 of 4, test gap 1 of 1, refactor suggestion 1 of 1, weekly summary 3 of 3; false claims injected and caught 4 of 4 | synthetic fixtures, mock model, offline | `evals/report.md (Agent runtime)` |
| Stop call median 1.9 ms; stop to finished median 33 ms; kill flag to finished median 39 ms (max 97 ms); human input to yielded median 30 ms; all within 1 s in 8 of 8 trials | synthetic, measured on a busy laptop | `evals/report.json (runtime, stop)` |
| Isolation: 21 attempts to write outside the workspace (traversal, absolute path, symlink, hard link, credential names, sandboxed scripts); 0 succeeded | synthetic, offline | `evals/report.json (runtime, isolation)` |
| Long-horizon runs: 9 of 9 completed and verified (Wilson [0.70, 1.00]); 2 injected false claims caught | synthetic fixtures | `evals/report.json (runtime, headline)` |

#### Honest limit

Every fixture is synthetic with planted facts. Menu mode shows a model can plan and drive a menu, not that it can analyse data. The detector paused 6 of 7 planted injections in the runtime test (none obeyed). One live smoke run per task is not a benchmark.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: parent and child agents with budgets, isolation and code-verified results

### Overnight runs and the morning report

**Status:** built · **Page:** `docs/features/background-agents.md` · **Targets:** Wordsmith, HRT

#### What it does

A routine the worker opted in for can run while they are away, then leave one summary for the morning. Irreversible steps still wait for a click.

#### How it works

The engine's presence model says whether a window is likely long enough and the machine is unlocked; the agent service starts a checkpointed run with keep-awake and aborts within a second when idle time drops. Frames never leave the device in an unattended run, and an unattended run never writes to a real account. Irreversible actions in an unattended run need a per-routine opt-in. The morning report is one card on return; overnight work never changes the independence score.

**What is different.** Whether to start is a decision on the worker's return forecast; the morning report is one line; and overnight work is excluded from the independence score.

#### Where to see it

Needs you (one line: 'Since you were away: 1 run finished, 0 failed', with Details); Routines, 'Run while I'm away' is its own switch on a routine.

#### Demo moment

Show the morning line in Needs you and open its Details: ran, failed, yielded, and the audit log. Say that nothing ran unapproved.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The overnight attention scenario passes: the approval is the first thing shown on return, exactly once, with a badge from the moment it arrived and at most one reminder | synthetic, simulated workers | `evals/attention/report_held_out.json (scenario S1)` |
| Overnight batch long-horizon suite passes offline with 0 false claims and 0 ungated submissions | offline tests, no model | `evals/report.md (Agentic evaluation, LH-5)` |

#### Honest limit

No real unattended run has been made: every run so far is in the sandbox or in mock mode. The overnight window depends on the presence model, which is weak for shift workers.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: unattended multi-step work with a per-routine consent record
- **HRT (best use of data for predictions and decisions)**: a start-or-wait decision under uncertainty about the worker's return

### Stop everything: the kill switch

**Status:** built · **Page:** `docs/features/stop-everything.md` · **Targets:** Wordsmith

#### What it does

A single action stops every running agent and holds them stopped until the worker presses Resume. It is reachable from the keyboard, the corner pill, the sidebar and the menu bar.

#### How it works

Stopping flips a kill flag on disk and cancels the supervisor's current generation, so the stop never waits for a model call. Results from an older generation are dropped even if a task ignores cancellation. Paths: Option-Shift-Command-K anywhere, Shift-Command-K or Shift-Escape inside Knack, the Stop button on the corner pill while something runs, a small Stop button in the sidebar, and 'Stop everything' or 'Pause for 1 hour' in the menu bar. The Stopped card stays until Resume, and Resume needs a per-boot token so a web page cannot clear it. Page content cannot change or click the kill switch.

**What is different.** Stop is a flag on disk plus a supervisor that drops stale results, so it does not depend on any model call or any in-process cooperation.

#### Where to see it

Corner pill (while working), sidebar footer, menu bar, keyboard.

#### Demo moment

Start a routine; the window minimises and the pill shows Stop. Press Option-Shift-Command-K: the pill becomes a Stopped card, and nothing continues. Press Resume.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Stop call to finished median 33 ms; kill flag to finished median 39 ms; within 1 s in 8 of 8 trials | synthetic, busy laptop | `evals/report.json (runtime, stop)` |
| The kill flag was reported by the engine in 24 of 24 simulated participants' data folders and the coach stayed silent after it in 24 of 24 | simulated participants (language model), not people | `evals/study_sim/REPORT.md (section 5)` |
| Reviewer findings that the kill hotkey never wrote the flag and that stop did not stop an in-flight action were fixed and re-verified | offline reproducers | `evals/review/safety_actuator.md (S-03, S-04)` |

#### Honest limit

Measured on a laptop other processes were also using, with fake desktops for the real actuator. The in-flight stop of a real click has not been exercised on a real desktop.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a visible, key-reachable stop for an agent that acts

## 5. Routines and automations

*Repeated work found, proposed and trusted one routine at a time.*

### Routine finder and proposals

**Status:** built (the routine card and queue were seen working in the dashboard; the finder is mixed on harder synthetic data) · **Page:** `docs/features/routines.md` · **Targets:** Wordsmith, HRT

#### What it does

Knack finds work you repeat, estimates how much time automating it would save, and proposes it with three equal choices: Watch first, Not now, Never. Nothing runs until you choose.

#### How it works

Episodes are segmented and clustered by alignment distance, with at least 3 supports. Each cluster is scored by count, minutes a week, variability and judgement share (searches, compares and decides divided by length) and matched to the role pack's routine templates. A value gate then keeps only proposals with a worthwhile saving. A recurrence forecast gives an interval on future runs. Proposals arrive only at episode boundaries, at most a few a day, and the system learns P(accept) per person. A routine is a JSON step language with a precondition and postcondition per step: model-written code is never executed.

**What is different.** A routine is eligible for automation only if the worker has mastered its steps or the pack marks it as not learning-relevant; otherwise Knack coaches it instead of taking it over.

#### Where to see it

Needs you (the proposal is a row with three equal buttons and 'More ways to say yes'); Routines, Running and Could automate.

#### Demo moment

A routine row 'Enter the household into three calculators': 'Seen 58 times in 3 weeks', what it touches, 'It will never submit'. Press Watch first. Nothing is saved or sent.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Raw finder: 12 of 55 clusters were planted routines (22% [12.9, 34.4]); after the value gate 6 of 6 proposals were planted (100% [61.0, 100.0]); recall 100% [74.1, 100.0] | synthetic, 4 personas | `evals/report.md (Routine finder)` |
| On three harder generators: raw precision 44 to 97%, recall 45 to 92%, proposal precision after the gate 74 to 100%; the cut height does not transfer | synthetic, 120 people per cell | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |
| Recurrence forecast: 8 of 11 routines inside their interval (73% [43.4, 90.3]) | synthetic, fit on days 1 to 14, scored on days 15 to 21 | `evals/report.md (Recurrence forecast)` |

#### Honest limit

The raw finder returns many clusters of one-off work; the gate does the work. The high precision on harder generators partly reflects less repeated structure in generated ad hoc work. All people are synthetic. Whether real workers find the proposals useful is unmeasured.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: from observed repetition to an approved, scripted browser routine
- **HRT (best use of data for predictions and decisions)**: a value estimate with an interval and a gate

### Watch first and the trust ladder

**Status:** verified · **Page:** `docs/features/routines.md` · **Targets:** Wordsmith, HRT

#### What it does

A routine earns autonomy by practising beside the worker. In Watch first it shadows real work without saving or sending, and a record of matches decides whether it may step up. Autonomy goes down again on any failure.

#### How it works

Four rungs: observe; suggest and shadow; do with approval; do then report. Promotion from shadow to 'asks first' needs at least 20 shadow runs with a Wilson lower bound of 0.8 on matches (20 clean runs give about 0.84). The top rung needs a lower bound of 0.95 (about 75 clean runs), a target the demo does not reach, and the screen says so. A failure, an undo within seconds or an injection hit demotes one rung. A divergence in shadow counts as a non-match. In the app the rungs read Watching, Asks first and Runs on its own; 'while I'm away' is its own switch, and irreversible steps in unattended runs need a separate per-routine opt-in.

**What is different.** Autonomy is earned by matching what the worker does, with a Wilson lower bound on shadow matches, and any failure, undo or injection hit demotes it.

#### Where to see it

Routines: a row opens in place with a three-state control; a step up is enabled only when the record earned it and a disabled step prints what it needs.

#### Demo moment

Open a routine row: its state in words (Watching, Asks first or Runs on its own) and, when a step up has not been earned, the printed need. Press Watch first on a proposal; show the queue stays empty.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Wilson thresholds and the rung rules are code with unit tests; no live shadow data exists | offline tests; no people | `docs/IMPLEMENTATION_SPEC.md (7.1 trust)` |

#### Honest limit

The ladder is a mechanism with synthetic evidence only. The top rung is not reachable in the demo by design. The shadow record on real work has never been collected.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: earned autonomy with a hard consent record
- **HRT (best use of data for predictions and decisions)**: promotion decided by a confidence bound

### Could automate: the repeat list

**Status:** built · **Page:** `docs/features/routines.md` · **Targets:** Wordsmith, G-Research

#### What it does

A compact list of actions you repeat that could be automated, ranked by minutes saved a week. Automate opens a 'Watch first' peek; it never runs anything.

#### How it works

Ranked by estimated minutes saved a week, then by count. A sequence that matches a pack routine needs 3 repeats; an unmatched sequence needs 5 repeats on at least 2 days. Seven rows then Show all; folds for Already automated and Hidden. One honest line says what repeats but is not offered: work that needs judgement, an irreversible first step, work that is too varied, or denylisted work. A firm aggregate suppresses groups under 5 people. It is inspired by the JetBrains Key Promoter X list of missed shortcuts, but counts repeated actions and never nags.

**What is different.** One row per repeated task even across tools, ranked by minutes saved, with an honest line for what repeats but is not offered and why.

#### Where to see it

Routines, tab Could automate.

#### Demo moment

Open Could automate: 'Read the case, then open the calculators: about 25 minutes a week'. Press Automate; the Watch first peek opens; nothing starts.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| 26 of 27 pre-written expectations met (96.3% [81.7, 99.3]); routines named by the pack listed for 60 of 60 people at 3, 5 and 8 repeats; unnamed routines 0 of 60 at 3 repeats by design and 60 of 60 at 5 and 8; people with no planted repeat got a row 0 of 60 times | synthetic, 60 people per cell, development seeds only | `evals/report.md (Hit list)` |
| Missed: top row unchanged when 5% of episodes are dropped, 53 of 60 (expected at least 0.9) | synthetic, development seeds | `evals/report.md (Hit list)` |

#### Honest limit

Development seeds only, with worlds written by the author of the rules: no held-out claim. Seen rendered in a harness; the order of the rows and the minutes are estimates with intervals behind a Hint.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: finding the automatable part of a complicated workflow
- **G-Research (make the invisible visible)**: the repeated work made visible

### Needs you: one list for decisions

**Status:** built (merged to main; seen in a harness and in hidden end-to-end runs; owner has not used it) · **Page:** `docs/features/needs-you.md` · **Targets:** Wordsmith

#### What it does

Approvals, paused runs, routine proposals and prepared actions are one list with one row shape, so a worker looks in one place. A decision never costs an extra click to open: each row carries its own buttons.

#### How it works

Order is the attention layer's: safety first, then time-sensitive, then the rest, newest first inside a class. Three rows show by default plus any safety or blocking row, then Show all. The consequence is printed as plain text ('Cannot be undone.'), never a pill or a Hint. Evidence (screenshots, found against expected, the tier log, the run id) opens in place. An approval can only be a real click: no keystroke, and no voice, approves anything. The same number is in the sidebar, the menu bar and the Dock badge.

**What is different.** Everything waiting for a decision is one list with one row shape, the consequence printed as plain text, and approval possible only by a real click.

#### Where to see it

Needs you in the sidebar (second item); a blocking approval also appears as a corner card.

#### Demo moment

Open Needs you with one approval and one routine proposal: 'Submit case note CN-2041. Cannot be undone.' Approve and submit (sandbox only), then the proposal's Watch first.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The after-state prototype measures 103 words above the fold for three decisions (the old Queue had 157 for two), 12 controls, 0 pills, 0 paragraphs over two lines | design measurement of a static prototype, no users | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

#### Honest limit

Measured as a prototype and checked in hidden runs, not by a person. Approvals in the demo are sandbox only. The default row count was cut to three after the first draft.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: the human decision point of an approval-gated agent

### When to build an automation: ski rental with predictions

**Status:** built · **Page:** `docs/features/hrt-decisions.md` · **Targets:** HRT

#### What it does

Building an automation costs effort and saves time only if the routine keeps coming back. Knack uses a ski-rental rule with a forecast to decide when to propose building.

#### How it works

With the cost of building b (in units of one manual run), a forecast y of remaining runs and a trust parameter lambda between 0 and 1: if y is at least b, build after about lambda times b runs; otherwise after b divided by lambda. The rule is 1 + 1/lambda robust and 1 + lambda consistent (Kumar, Purohit and Svitkina); the constants were checked numerically. Lambda is chosen from past forecast error, a heuristic labelled as one.

**What is different.** A rule with a proven worst case is applied to the build-or-wait decision with a forecast, and the table shows where building at once beats it.

#### Where to see it

Behind the proposals in Needs you and the value line on a proposal; Evidence has the regret table.

#### Demo moment

Say the table in one line: with predictions regret is 1.33 against 1.78 for building at break-even, and building at once, at 1.27, beats both at the simulated cost.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Regret (hindsight best = 1.0): ski rental with predictions (lambda 0.2) 1.332 [1.322, 1.342]; build at break-even 1.776 [1.765, 1.786]; build now 1.273 [1.257, 1.290] | synthetic, 4,000 simulated routines, build cost 16 manual runs | `evals/report.md (Ski-rental build timing)` |

#### Honest limit

Simulated routines with a stated mechanism, not real build decisions. Building at once beats the prediction rule at the simulated cost, so the rule is not uniformly best.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision rule with a proven worst case and a measured regret

### Review routing under a risk bound

**Status:** built · **Page:** `docs/features/hrt-decisions.md` · **Targets:** HRT

#### What it does

Auto-approve the safest agent outputs and send the rest to a person, with a stated bound on the error rate of what is auto-approved.

#### How it works

Features: case complexity, the worker's trace, worker-versus-agent disagreement and agent confidence. Calibrated scores rank cases. The auto-approved set is the largest one whose Clopper-Pearson upper bound on the error rate is at most 0.05 on a calibration split; the bound is then checked on a held-out split.

**What is different.** The auto-approved set is the largest one whose Clopper-Pearson bound stays under the target, checked on held-out cases, with the circularity stated.

#### Where to see it

Evidence (review routing); not a screen of its own.

#### Demo moment

Say: held-out error 0.0% at 93.8% coverage, and the page says why that is circular.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Held-out error 0.0% [0.0, 1.7] at 93.8% coverage; target 0.05; the bound held | synthetic, 900 households (train 450, calibration 225, held-out 225) | `evals/report.md (Review routing and risk control)` |

#### Honest limit

Circular: the calculators' quirks and the households that trigger them were planted by us, so the router finds our planted structure. The bound holds for cases like the calibration cases; a new rule or calculator breaks it silently. Review time per case is an assumption.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: risk control with a held-out check, stated as circular

### Proactive briefing: judge, verify, prepare, press to fire

**Status:** built (engine built and tested; development-set evaluation only; cards now arrive as rows in Needs you) · **Page:** `docs/features/proactive-briefing.md` · **Targets:** HRT, Wordsmith

#### What it does

From routines, skill gaps, calendar and commit suggestions and agent results, Knack ranks what could be worth a card, shows at most three, and prepares the action behind each. Nothing fires unprompted: pressing a card is what starts anything.

#### How it works

Four steps in code. Judge ranks candidates and prefers fewer, even zero. Verify re-checks each candidate against the current state and drops stale ones. Prepare builds the editable content from templates (a model may reword through the egress guard). Fire acts only on the worker's press: it either puts an approval item in the queue or starts a background run that only reads, never both unprompted. Each card carries a risk class and source tags. Acceptance is learned from the worker's reactions, starting from a prior of 0.4 for the role. The design idea (judge, prepare, execute on press, drop stale items) comes from the owner's notes on Sentient OS and was re-implemented in our own code and words.

**What is different.** Nothing fires unprompted, stale candidates are dropped before a card is drawn, and zero cards is a valid result.

#### Where to see it

Needs you: a prepared action is a row. After a press the screen says what was made, for example 'Created an item here for your approval. Nothing runs until you approve it.'

#### Demo moment

Press a prepared card in Needs you; the line says what it made and that nothing runs until you approve. Then open Background runs to show a read-only run that was started.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The shipped judge: 101 of 124 cards were worth surfacing (precision 82% [70.4, 89.9]), recall 86% [75.5, 93.2]; against 55% [49.8, 60.5] for raw top three with no checks, 51% for random three and 46% [41.2, 49.9] for everything with no cap | synthetic, 145 replayed decisions over 35 people; bootstrap over people | `evals/report.md (Proactive cards)` |
| 145 briefings: cap of 3 cards, 0 cap violations, mean 0.86 cards; unprompted fires 0; unprompted agent spawns 0 | synthetic | `evals/report.md (Proactive cards)` |

#### Honest limit

'Worth surfacing' is our definition, fixed before the runs, then revised after the first replays; there is no held-out data, so these are development-set figures. Acceptance learning is shown only on a simulated worker with fixed rates. All personas are synthetic. Whether real workers find the cards useful is unmeasured.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a ranking decision with a hard cap, judged against three baselines
- **Wordsmith (most complicated end-to-end browser-use workflow)**: prepared actions that wait for a press

## 6. Connections and MCP plugins

*Curated plugins, off and read-only by default.*

### Connections: curated MCP plugins with role presets

**Status:** landing (owner decision D55; CONNECTIONS (Track E) is building it on its own branch; docs/CONNECTIONS.md has not landed) · **Page:** `docs/features/connections.md` · **Targets:** Wordsmith

#### What it does

A worker can connect a few tools Knack may read from. Presets come with the role: a Dev set, a Data set and a Benefits set. Everything starts off and read-only; the list is curated, with no arbitrary servers.

#### How it works

Knack uses the official MCP Python SDK (MIT) as the client and the repository's own plugin framework for sources; hosted aggregators are not used because the data would leave the device. Presets named by the owner: Dev (GitHub, Git, Linear or Jira, Slack, Sentry, Filesystem), Data (SQLite and Postgres, BigQuery, Google Sheets and Drive, Jupyter, Notion, Slack), Benefits (Outlook, Teams, SharePoint). Presets are offered inside the role card of first run, which adds one click (first run becomes four). The demo uses local stand-ins only: a local folder, a SQLite database with the synthetic dataset, and a fake GitHub and Slack we write. No real account is used.

**What is different.** The list is curated and read-only by default, starts off, and avoids hosted aggregators so data does not leave the device.

#### Where to see it

Settings has a Connections panel; first run shows the presets under the role card (both are slots on main; the panel itself is landing).

#### Demo moment

In first run choose Programmer; the Dev preset appears, everything off. Switch on the local stand-ins; show the read-only badge and that nothing was sent.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The plugin framework for sources is covered by 41 test functions (static count); the connections panel itself has no evidence yet | offline tests; not verified for the new panel | `evals/report.facts.json (tests.by_dir, engine/plugins)` |

#### Honest limit

Not on main. This entry is written from owner decision D55; check docs/CONNECTIONS.md when it lands. Real Outlook, Teams or SharePoint access has not been run and needs the owner's approval at run time (D26). Custom servers are out of scope by decision.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow that crosses apps and servers, kept read-only and local by default

## 7. Voice and Hey Knack

*Speak to it; it points, and clicks only after a real click on Allow.*

### Hey Knack: an on-device wake phrase

**Status:** built (code and tests are built and merged; not run with a real microphone yet; the listener helper ships inside Knack.app and the first launch needs the owner's Microphone and Speech Recognition grants and an installed on-device dictation language) · **Page:** `docs/features/hey-knack.md` · **Targets:** G-Research

#### What it does

Knack is woken by the words 'hey knack'. Listening is on by default (the owner's decision), but it happens on the Mac, prints only a closed 'heard' event, and stores no audio and no transcript.

#### How it works

A native helper uses macOS on-device speech recognition. If on-device recognition is not available it turns itself off with one plain line and never falls back to server recognition. The phrase is matched by a closed accept list: a greeting (hey, hay, heya) at the start of an utterance, then the name 'knack' (close spellings only at the end of an utterance or before a request word; 'knock' only before a request word). 'Hey Jack', 'a knack for it' and 'hey knock it off' are rejected. The listener is dormant, with the microphone released, when the switch is off, the screen is locked or the Mac asleep, Stop everything is engaged, Do Not Disturb, a call, a meeting or a screen share is on, a Live conversation or an agent run is under way, or the worker is away. macOS still asks for Microphone and Speech Recognition, which only the owner can grant.

**What is different.** Recognition happens in a native helper that prints only a closed 'heard' event, so no text crosses into the app, and it fails closed instead of using server recognition.

#### Where to see it

Menu bar: a status row ('Listening for Hey Knack. Stays on this Mac, nothing stored.') and a 'Listen for Hey Knack' switch; macOS itself draws its orange microphone indicator whenever any process uses the microphone, which Knack cannot hide. First launch asks for the two macOS permissions. The corner pill shows 'Listening' after the wake.

#### Demo moment

Say 'Hey Knack'. The pill shows 'Listening', a soft cue plays, and Knack answers by voice. Try 'hey Jack': nothing happens.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The matcher is pinned by tests over more than 300 distinct ordinary sentences and more than 40 accepted variants: on the held-out set exactly one false accept ('Hey nack, nack, nack, that is all I hear from this network') and no misses; over both sets the Wilson upper bound is below 0.02 for false accepts and below 0.07 for misses | offline tests on text strings, not a microphone | `apps/desktop/src/main/wake/corpus.test.ts` |
| Measured on text strings: development set 0 false accepts in 183 ordinary sentences and 0 misses in 31 variants (the matcher was tuned on it); held-out set, written after the matcher was frozen, 1 false accept in 159 (0.63%, Wilson 0.11 to 3.48%) and 0 misses in 25 variants (Wilson 0 to 13.3%); both together 1 in 342 (0.29%, Wilson 0.05 to 1.64%) and 0 misses in 56 (Wilson 0 to 6.4%) | offline strings, not audio and not a microphone | `docs/knack-ux/09-wake-voice.md` |
| A line-for-line Swift port of the matcher agrees with the TypeScript specification over the whole corpus | offline tests | `apps/desktop/src/main/wake/matching.ts (header)` |

#### Honest limit

No real microphone has been used yet; the rates above describe the matching logic on strings, not how often a real recogniser and microphone trigger it (that needs the owner's first launch and a day of use). The one held-out false accept is 'Hey nack, nack, nack, that is all I hear from this network'; it was left and pinned in a test rather than tuned away. An unusual accent or a noisy room is untested. Earlier documents (docs/FLAGS.md, docs/FEATURE_CATALOGUE.md) still say there is no always-listening microphone; D52 supersedes that for Hey Knack.

#### Hackathon target

- **G-Research (make the invisible visible)**: nothing recorded; the invisible listener is made visible by an indicator and a switch

### Voice guidance and 'do it for me' behind a click

**Status:** built (the click path fails closed until the first supervised real-click test has passed) · **Page:** `docs/features/hey-knack.md` · **Targets:** Wordsmith, G-Research

#### What it does

After the wake, a live voice conversation starts. Knack speaks while it guides, shows the place with a ring and a ghost cursor, and never clicks for you on voice alone.

#### How it works

The wake stops the listener (releasing the microphone) and starts the Live voice conversation (Gemini), hands-free, with a soft chime. Two first-wake cards ask once, each with Yes, Not now and Never of equal weight: whether your voice may go to a cloud voice model while you talk, and whether a small picture of the screen may go about every 5 seconds; only a real mouse click answers a card. Frames go through the image gate and the ledger: never from a denylisted app or over secure input, never unattended, never stored. The conversation is bounded: started by the worker, five minutes at most, a spending cap, and a quiet half minute ends it. The model's tools are a closed set: point_at (ring and ghost cursor), clear, show_step, ask_choice, end_session and do_it_for_me. The last fails closed until the owner has completed the first supervised real-click test; a record written only by that test turns it on. Even then, voice alone is never consent: a card 'Click for you?' with Allow once or Cancel needs a real mouse click, a 20-second timer means Cancel, and the click goes through the one-time token, the per-run permit, the countdown and every real-actuator guard. It is never unattended, never a purchase, never a real account. A typed context packet (closed grammar, freshness limits; a test feeds it hostile strings) tells the session what is on the screen, what waits for approval and what the coach is doing. Holding Option-Space talks.

**What is different.** Voice can ask but never approve: the click is a separate consent, a real mouse click on a card, and the whole path stays closed until a supervised test has passed.

#### Where to see it

Corner pill (voice state and End), the ring on the real screen, the Allow card.

#### Demo moment

Ask: 'Where do I see what needs me?' A ring and a ghost cursor show Needs you; Knack does not click. Say 'do it for me': it says it will show you instead, because the first supervised test is pending.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The click state machine is covered by tests: no tool call does anything without a Live session; with no rung record the answer is always 'first supervised test pending' and no card is shown; the card's Allow counts only as a real mouse click (voice, key or timer is ignored); Stop everything wins from any state | offline tests | `apps/desktop/src/main/wake/click-machine.test.ts` |

#### Honest limit

Not run with a microphone, a Live session or a real click. The 'do it for me' path stays off until the first real-click rung is reported with the owner present, and the agent-service route it needs (POST /desktop/click) is not built (decision D56): the desktop answers 'route missing' and clicks nothing, and Knack says it will show you instead. The model's speech inside a conversation is free-form audio; every other spoken line in Knack is fixed. Voice quality and latency are not measured.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a voice-guided browser workflow with the click gated by consent
- **G-Research (make the invisible visible)**: the next step made visible and spoken

## 8. Models and modes

*Gemini by default, a local model for private digests, fixed spoken lines, and a mock mode that runs offline.*

### Model routing: Gemini by default, checked at boot

**Status:** built (live boot check and small planner and fast calls pass; computer use on Gemini needs its own iterations) · **Page:** `docs/features/models-and-routing.md` · **Targets:** Wordsmith, HRT

#### What it does

Every model role runs on Gemini by default: a planner, fast checks, pointing and glances, a verifier, computer use and live voice. OpenAI is an explicit opt-in. The More, Models and cost screen shows which model, how fast and what it costs.

#### How it works

One model port with providers behind it. Roles map to environment variables (accurate, fast, computer use, live) and nothing hard-codes a model name; at boot the key's model list is read and a missing id stops start-up with the usable ids. Every call that leaves a Python service goes through the egress guard and a metadata-only ledger. The routes were chosen by a bake-off on our sandbox screens. The OpenAI key was revoked by OpenAI on 7 Nov (cause unknown) and the owner moved every OpenAI role to Gemini (D49); one further Gemini model on the key (Argon) is never configured, and a test guards that.

**What is different.** Roles are routed by a bake-off on our own cases, model ids come from the environment and are checked at boot, and every call that leaves a service is ledgered.

#### Where to see it

More, then Models and cost; Settings, 'Use live models' is the master switch (it restarts the engine, about 20 seconds); the sidebar status line says Live models or Running with example data.

#### Demo moment

Show the status line 'Live models', then Models and cost: the route for each role, latency and cost. Flip Use live models off and the line becomes 'Running with example data'.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Pointing: Gemini flash-lite 95% [90, 98] (140 of 147), median 0.93 s, about US$0.0005 a call; Gemini flash 95% [90, 97], median 3.31 s, about US$0.0017; OpenAI fast 75% [67, 81], median 1.72 s, about US$0.0015. The routed variant (flash-lite first) was identical to flash-lite alone | synthetic sandbox screenshots, 147 positives and 43 negatives; cost is an estimate | `evals/modelbench/REPORT.md (section 1)` |
| Verifier: all three models right on all 30 images, so the set cannot choose between them | synthetic sandbox screenshots | `evals/modelbench/REPORT.md (section 3)` |
| Recommendation recorded by the benchmark: flash-lite primary for pointing, no escalation needed, Gemini acceptable as verifier | synthetic | `evals/report.md (Model benchmark)` |

#### Honest limit

The bake-off is on screenshots of our own sandbox pages with 147 pointing cases; it is not a claim about real apps. Computer use on Gemini has development results only (see the computer-use page). Every earlier number measured with OpenAI models is evidence about that configuration, not about Gemini.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: model roles chosen by measurement, behind one port
- **HRT (best use of data for predictions and decisions)**: a routing decision judged on accuracy, latency and cost

### Local model digests (a 7B model on this Mac)

**Status:** built · **Page:** `docs/features/models-and-routing.md` · **Targets:** HRT, G-Research

#### What it does

Raw commits and calendar entries are turned into short enums on the Mac by a local model, so the frontier model sees digests and never the text. If the local model is absent, plain rules do the job.

#### How it works

A 7B model (Qwen2.5, 4-bit) runs on the loopback through llama.cpp with constrained decoding, so nothing leaves a digest except vocabulary values. For each field the shipped policy keeps whichever of the model or the rules did better on a held-out split: the model for category, the rules for risk, message quality and whether preparation is needed. Code vetoes the two most consequential claims (a revert needs a revert-style message; focus time needs at most one attendee).

**What is different.** For each field the shipped policy keeps whichever of the model or the rules did better on held-out data, and code vetoes the most consequential claims.

#### Where to see it

Behind Git habits and Calendar; More, then Models and cost shows local-model status.

#### Demo moment

Not a visual moment. Say it when showing a commit digest: the category came from a model running on this laptop.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Commit category: model 91.8% [84.7, 95.8] against rules 77.5% [68.3, 84.7]; event category: model 95.9% [90.0, 98.4] against rules 81.6% [72.8, 88.0] (98 held-out items each; sign test p = 0.0043 and 0.0026) | synthetic items with planted labels, held-out split run once | `evals/report.md (Local model digests)` |
| Risk, message quality and needs-prep: no clear difference, so the rules are shipped | synthetic, 98 items each | `evals/report.md (Local model digests)` |
| With one planted line in the input, a model-for-everything run moved to the line's value in 19 of 19, 17 of 17, 13 of 17 and 12 of 12 cases; the keyword rules in 0; the shipped policy leaves 0 of 19 and 5 of 17 category steerings | synthetic, 20 items per task | `evals/report.md (Limitations register: loc_injection)` |

#### Honest limit

Synthetic commits and entries written by the author of the rules and prompts; accuracy on real data is unknown and probably lower. About 100 items per task, so differences of a few points are not distinguishable. The model can still be steered by whoever writes a commit message or an invite.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a model-or-rules choice per field decided on held-out data
- **G-Research (make the invisible visible)**: private data turned into numbers without leaving the Mac

### Spoken lines (ElevenLabs, fixed vocabulary)

**Status:** built · **Page:** `docs/features/models-and-routing.md` · **Targets:** Wordsmith

#### What it does

Short spoken prompts come from a fixed set of lines, not from a model. A voice reads a line by id.

#### How it works

Knack sends a line id, never free text, and the call is listed in the ledger. The draft submission text says cached audio supports the offline demo (the author did not confirm this in code). Cue speaks only when asked (decision D36). A developer escape hatch that lifts the fixed-lines rule exists and is off.

**What is different.** Speech is a fixed vocabulary read by id, so no model can say anything unplanned (inside a started Live conversation the model's audio is free-form).

#### Where to see it

Spoken cues and the morning briefing, when voice is on.

#### Demo moment

Trigger a cached line; show the ledger row that lists the line id and no text.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measured result: the fixed-vocabulary rule is enforced in code and covered by tests | offline tests; no evaluation of voice quality | `docs/FLAGS.md; docs/REQ5_PLAN.md` |

#### Honest limit

Not measured for quality or latency. Voice is on by default but depends on the ElevenLabs key; the offline demo uses cached audio.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a calm voice that cannot say anything unplanned

### Mock mode: the whole product offline

**Status:** verified · **Page:** `docs/features/models-and-routing.md` · **Targets:** Wordsmith

#### What it does

The same product runs with no model calls and no network: scripted, deterministic answers on example data. The sidebar status line says 'Running with example data' and screens that show example rows keep their own Example data badge.

#### How it works

Mock mode is set by the demo command: it seeds an isolated home under data/ (never the worker's real folder), starts the engine, the agent service and the three sandbox sites, and opens the dashboard. Provider calls are replaced by scripted, deterministic ports. The app itself starts in live mode when a Gemini key is present and in mock mode when it is not.

**What is different.** The whole product, including an agent run, is reproducible offline with deterministic scripted ports and an isolated home.

#### Where to see it

Sidebar status line; Settings, Use live models.

#### Demo moment

Turn wifi off, run the demo command, and walk the dashboard: every screen loads on example data.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| In the lead's sweep all 28 screens and views loaded against the live stack with no page errors (30 screens, 0 page errors at 23:50 after the Knack shell merged); a benefits-agent run in mock mode ended with an item in the approval queue and 0 false claims | mock mode and live stack, example and synthetic data; seen by the lead on 7 Nov | `docs/MVP_STATUS.md; docs/FIRST_LAUNCH.md` |

#### Honest limit

Mock results are scripted: they show the product runs end to end, not that a model does the work. Re-run the sweep at the freeze.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a reproducible, offline walk-through of a complicated workflow

## 9. Insights and admin

*A few pointers for the worker; a firm view for the admin.*

### Home: one sentence, one action

**Status:** built (merged to main; measured on a prototype; owner has not used it) · **Page:** `docs/features/home-insights.md` · **Targets:** G-Research

#### What it does

Home shows one sentence about the worker's week, one action and at most two quiet rows. No chart, no table, no paragraph. If an approval is blocking a job, it takes the top slot instead.

#### How it works

The hero is the top pointer written from a fixed template: 'On {step} you usually take about {n} {unit} {longer or less} than the expert.' At most 16 words and one quantity. 'Why this?' opens the method (fixed rules, not a model), the interval, n and where the data came from. Something the worker must decide outranks something they could learn. When there is nothing, the screen says so in five words.

**What is different.** A one-quantity rule limits a sentence to one number, and a lint checks it, so the home screen cannot grow back into a report.

#### Where to see it

Home, the first item in the sidebar and the page Knack opens on.

#### Demo moment

Open Knack: the date, one sentence with its origin badge ('Synthetic data' for an engine answer from synthetic people, 'Example data' for a fixture), the button 'See where the time goes' and, if anything waits, one row '1 thing needs you'.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Words above the fold on Home fell from 173 to 47 (the sidebar from 51 words of hints to 17 words in all) and controls from 10 to 4 | design measurement of a static prototype (one browser, no users) | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

#### Honest limit

The 47 words are the prototype's headline content; real screens land a little above it. The example sentence comes from the synthetic firm and carries its origin badge (Example data or Synthetic data). These are measurements of the interface, not of people.

#### Hackathon target

- **G-Research (make the invisible visible)**: the one thing worth seeing, said once

### Top insights engine: a few pointers, chosen by code

**Status:** built · **Page:** `docs/features/home-insights.md` · **Targets:** G-Research, HRT

#### What it does

Each week, a deterministic engine picks at most three pointers for a worker and a short list for an admin. A weak insight is suppressed, not shown weakly.

#### How it works

A fixed list of candidate kinds (for example time lost on a habit, a habit improved, an independence milestone, a skill due for retention practice, a relapse, an automation opportunity). Each candidate must pass a reliability gate (minimum occurrences, an interval that excludes zero, an effect size and a sign that persists over weeks), then a family-wise control for the number of comparisons, guard metrics (faster but with more errors is a trade-off, never a celebration), diversity and caps. Text comes from a fixed template. Admin groups under 5 people are never compared. Output is deterministic: the same input twice, or shuffled, gives the same answer.

**What is different.** Silence is a valid output: candidates pass a reliability gate and a comparison-wide control, and a weak insight is dropped, not shown weakly.

#### Where to see it

Home (the hero and quiet rows); the Monday note is built from the same pointers (its palette row is specified, not yet on main); Firm for admins.

#### Demo moment

Show the 'Nothing stands out this week' state next to a week with a pointer, and say that silence is a result.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| False insights on null data: 0.0037 per worker-week [0.0027, 0.0047] (62 of 16,800 person-weeks, 2,400 people; target at most 0.05: met); admin 0 of 160 admin-weeks over 40 firms (target at most 0.10: met) | synthetic firms of 60 people, held-out seeds, run once | `evals/insights/results/heldout.json` |
| Planted time loss of 15, 30 and 60 seconds selected in 99, 100 and 100 of 100 worlds; improvement 86; relapse 82; retention 100; trade-off 81; independence rise 47 (target 0.8: missed); false celebration when errors rise 14 of 100 (target 0: missed) | synthetic, 100 planted worlds per effect | `evals/insights/results/heldout.json` |
| Admin situations recovered at the gate on held-out seeds (target at least 9 in 10): plateau unit 29 of 40, programmer bottleneck 9 of 19, Simpson's-paradox role 19 of 40; 127 of 996 empty worker lists hid a planted effect | synthetic | `evals/insights/results/heldout.json` |
| No k-anonymity violation across 11 firms; 21 of 21 edge cases pass; top-3 sets stay stable when 5% of rows are dropped (Jaccard 0.88; admin top-7 0.93; target 0.8) | synthetic | `evals/insights/results/heldout.json` |

#### Honest limit

Targets were fixed before the held-out run and several recall targets were missed and reported. The planted worlds are ours; the 100 planted worlds per effect do not use the seed list, so they are the same on dev and held-out. A person with more than three real effects cannot see them all.

#### Hackathon target

- **G-Research (make the invisible visible)**: a few well-chosen things made visible, with silence as a valid answer
- **HRT (best use of data for predictions and decisions)**: selection under multiple comparisons with a stated false-insight rate

### Admin views: Firm, Roles, Onboarding

**Status:** built (UI merged to main; the firm is synthetic) · **Page:** `docs/features/firm-admin.md` · **Targets:** G-Research, HRT

#### What it does

A second audience. The Admin view shows where the firm loses time, compares experts and juniors by role on one scale, and shows how fast people reach independence. Names are made up and the firm is synthetic.

#### How it works

Roles are Worker and Admin; the admin switch lives in the account menu and is remembered. An admin sees summaries of numbers and enums only (counts, trend classes, intervals, per-skill independence and time-lost, automation counts): never raw events, screenshots, page or file text, memory-file contents or assist-ledger rows beyond counts. Group comparisons need at least 5 people. There is no ranking of individuals and no single performance score. Every admin text carries the line 'For coaching and onboarding, not for evaluating individuals.' A worker has a plain 'what your admin can see' page in Your data. The Firm screen shows at most three rows by default, then Show all; Roles shows one row per role as a dot-and-whisker strip; Onboarding shows one small chart per role with the median step to the target.

**What is different.** The admin sees numbers and enums only, never a ranking or a single score, groups under 5 are never compared, and the worker has a page that shows exactly what the admin can see.

#### Where to see it

Account menu, View as Admin; sidebar Firm, Roles, Onboarding; More, Firm rows (People, Automation, Risk and coverage, Forecasts, Firm brief).

#### Demo moment

Switch to Admin: Firm lists three rows with n and interval; open Roles: experts and juniors on a shared 0 to 100% scale, one row per role; show the Synthetic firm badge and say names are made up.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| No group under 5 people is ever compared: 0 k-anonymity violations across 11 firms; a person's deleted ledger disappears from every comparison at once | synthetic firms | `evals/insights/results/heldout.json` |
| Words above the fold: Firm 206 to 80; Roles 313 to 35 (the spec text says 36) | design measurement of a prototype | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

#### Honest limit

Full per-user visibility for the admin was the owner's choice (D41); the lead recommended aggregates plus opt-in individuals. Per-user visibility is workplace monitoring: a real deployment needs a lawful basis (in the UK and EU, for example a documented legitimate-interest assessment), a clear notice to workers before any data is shared, and possibly consultation. This build supplies the worker's 'what your admin can see' page but not the lawful basis or the notice. It also changes the earlier promise that logs never leave the device: these summaries are the only thing that would, and only if a deployment chooses to.

#### Hackathon target

- **G-Research (make the invisible visible)**: the firm's hidden bottlenecks made visible
- **HRT (best use of data for predictions and decisions)**: comparisons with a minimum group size and intervals

### Monday note, firm brief and prediction scorecard

**Status:** built · **Page:** `docs/features/firm-admin.md` · **Targets:** HRT

#### What it does

Extras for the admin: a short Monday note, a one-page firm brief that prints, and the stuck-prediction scorecard.

#### How it works

The Monday note is a few plain sentences built from the same deterministic insights (the engine sends ready text when it has it; otherwise it is composed from the pointers). The spec puts 'Copy my Monday note' in the command palette; that row was not on main when this was written. The firm brief is a print view of the top rows. The scorecard is the Forecasts screen (reliability diagram and baselines) read from the evaluation report.

**What is different.** Nothing new is claimed: it reuses the insights engine and the evaluation report.

#### Where to see it

Command palette, Print the firm brief (and Copy my Monday note once it lands); More, Forecasts.

#### Demo moment

Press Command-K, choose Print the firm brief; then open More, Forecasts to show the scorecard.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| No separate measurement: these reuse the insights engine and the report | see the home-insights and stuck-model pages | `docs/DECISIONS.md (D44)` |

#### Honest limit

Same synthetic firm and the same caveats as the insights engine.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a prediction scorecard beside every forecast

## 10. Growth and independence

*Whether the worker needs less help over time.*

### Growth and the independence score

**Status:** built (built; evaluated on simulated learners; no person has used it) · **Page:** `docs/features/growth-independence.md` · **Targets:** HRT, G-Research

#### What it does

Knack counts the steps you finished with no accepted cue and shows the trend with its interval. The screen says what it measures: help needed, not expertise. Work done for you, such as overnight automations, never changes the score.

#### How it works

An assist ledger holds one row per assist episode with enums and numbers only: no text and no screenshots. Three streams are kept apart: assist (feeds the score), delegated and automation (shown as offloaded work, never in the score). Independence is the share of the last 20 occurrences of a skill finished with no accepted cue, with a Wilson lower bound. The help-need trend is a Theil-Sen slope with a bootstrap interval. Gap closure compares seconds lost with the first five occurrences, and retention counts unaided success on the first occurrence three or more days after being taught. A composite from 0 to 100 exists (weights stated as assumptions) but the headline is the trend. Dismissing a cue without completing the step is not independence; an error is penalised. The curve starts after 10 steps.

**What is different.** Assisted work is kept apart from delegated and overnight work, so an agent doing the job never raises the worker's score; the headline is a trend with an interval, not a single number.

#### Where to see it

Growth in the sidebar: a one-sentence title, one chart with its band, skills as rows, and closed disclosures (The fade, Your ledger, What Knack did for you). Export and delete are in Your data.

#### Demo moment

Open Growth: 'You need help less often than you did.' One chart, one band, and the printed line 'Measures help needed, not expertise.' Open About this data to show n, the interval and the window. Until a worker has a ledger of their own it shows an example learner, badged Example data (docs/drafts/DEMO_SCRIPT.md, beat 4; confirm before the demo).

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The composite overstates mastery for learners who do not improve and rises 10 points or more in about a third of them; independence and the trend are the evidence, and the trend has low power | synthetic, 240 simulated learners with planted curves | `evals/report.md (Limitations register, cue-score-composite, and Cue analysis)` |
| A planted independence rise was selected as a pointer in 47 of 100 worlds (target 0.8: missed); false celebration when errors rise 14 of 100 (target 0) | synthetic, 100 planted worlds per effect | `evals/insights/results/heldout.json` |

#### Honest limit

No person has used it. The claim is 'needs less help', never 'became an expert'. The composite is experimental and in no headline. The insights engine finds only about half of the planted independence rises, so Growth may show a rise that Home does not mention.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a measured trend with an interval, not a single score
- **G-Research (make the invisible visible)**: learning made visible

## 11. A calm product: window, attention, context

*One window, one pill, one attention layer.*

### One attention layer: a router, a digest, quiet states

**Status:** built (engine built; desktop wiring built; held-out simulated evaluation met 11 of 12 criteria) · **Page:** `docs/features/attention-router.md` · **Targets:** HRT

#### What it does

Every part of Knack that could interrupt (Cue, briefings, approvals, agent results, pauses, the help-level glance) goes through one router. It decides whether, where, when and how loudly the worker is told. Safety is shown once and is never batched or repeated.

#### How it works

A pure function of the event, the worker's state (flow, a call, a meeting, a screen share, away, locked) and recent history. Principles in code: silence is the default; safety is never suppressed; a decision is shown once and reminded at most once; one voice at a time; nothing important sits unseen (a passive marker exists the moment an item exists); learning can only quiet; the worker can always see why (a one-line fixed reason); metadata only. Channels run from a silent log through a badge, banner, chip and toast to a question card and voice. A digest replaces pings when the worker returns. A new interrupting type needs a row in the attention table first.

**What is different.** Every producer of an interruption goes through one router with a fixed reason for every decision, and learning can only quiet, never amplify.

#### Where to see it

Everywhere a notice appears; Needs you; the corner card; Settings, Interruptions (Rarely, Balanced, Often).

#### Demo moment

In a meeting or screen share, three cues are dropped and an injection pause is still shown within seconds in content-free words; the held approval appears at the first pause after the meeting.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Against show-everything: 0.150 [0.141, 0.159] non-safety interruptions per flow hour against 1.512 [1.447, 1.582]; 0 hard-quiet breaches; 98.4% [98.0, 98.7] of important items seen in their window; median delay 85 s; 0 of 528 urgent safety items missed | synthetic, 200 simulated workers, 2,000 worker-days, frozen config | `evals/attention/report_held_out.json` |
| Against one daily digest: the digest is quieter but sees 28.3% of important items in window and misses 182 urgent safety items | synthetic, same run | `evals/attention/report_held_out.json` |
| 11 of 12 pre-registered criteria met; criterion 7 not met: later-day can-wait toasts rose by +0.33 a day [+0.08, +0.58], the wrong direction; learning made no difference to any aggregate measure | synthetic, same run; corrected after the fact and the correction is in the file | `evals/attention/report_held_out.json (post_hoc_corrections)` |

#### Honest limit

Every number is simulated: workers, schedules, reactions and attention costs are our assumptions. It shows the policy behaves as designed, not that people find it natural. A one-a-day digest costs less attention in the assumed cost model. The n = 4 teammate check was not run.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision policy judged against two baselines and a pre-registered list of criteria

### Context engineering: typed, bounded, fresh

**Status:** built · **Page:** `docs/features/context-engineering.md` · **Targets:** Wordsmith

#### What it does

What each model sees is built by code from typed facts, with a budget, a freshness check and a record of what was left out. A long run carries a small working memory instead of a growing transcript.

#### How it works

An audit listed every model-facing call site and its prompt sections. A shared library assembles prompts under nine rules: typed first; trust enforced by audience (the planner never receives raw untrusted text; the reader receives untrusted text but no worker memory); stable first and volatile last so a provider can cache; bounded, with a fixed truncation order and nothing cut mid-item; code-held task state after a resume; one frame and at most one thumbnail; keyed, capped retrieval from the memory file (at most six lines); fresh or named; and measured with a metadata-only manifest. Computer use runs statelessly by default.

**What is different.** Prompts are built from typed facts under a budget with a freshness check, trusted and untrusted text never share a prompt, and a long run carries code-held state instead of a transcript.

#### Where to see it

Not visible on a screen. It is behind every agent run and shows up as cost and latency in Models and cost.

#### Demo moment

Not a visual moment. Say it with a number: computer-use prompts stay flat at about 2.8 thousand tokens a step instead of growing.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Stateless computer use measured 74,548 input tokens over 27 steps (about 2.76k a step, flat); the chained thread it replaced measured 211,852 over 25 calls (about 8.5k a call and growing) | real model, one run each, n = 1 | `docs/CONTEXT_ENGINEERING.md (section 1.1); evals/agentic/ITERATIONS.md` |
| Tier 3 through the real loop over 100 steps: the prompt text stayed 672 to 752 estimated tokens per step; tier 2 consecutive prompts share about 55% of their text | test doubles as the model; measures what the loops send, not what a model does | `docs/CONTEXT_ENGINEERING.md (section 1.6)` |
| Background runtime: the typed context payload grows from 66 to 288 tokens over 14 steps; after step 8 the maximum is 1.08 times the first eight steps' maximum | synthetic fixtures | `evals/report.json (runtime, headline)` |
| Modelled over 150 steps: a chained thread reaches 285.7k tokens at step 150 (21.6M cumulative); the library stays at about 2.8k a step (0.42M cumulative), a calibration to one live run, not an independent check | modelled with the real history functions; no model call | `docs/CONTEXT_ENGINEERING.md (section 5.1)` |
| 800 attempts to put raw untrusted text into a planner, checker, computer-use or vision packet were all refused; 0 leaks of worker memory to the reader; 56 freshness cases with 0 wrong decisions | offline tests with synthetic injection strings | `docs/CONTEXT_ENGINEERING.md (sections 5.4 and 5.6)` |

#### Honest limit

Token counts are estimates (characters divided by 3.6) beside the provider's usage fields. The measured runs use test doubles or n = 1 live runs; nothing here is a live-model result at scale. The reader still re-reads the same page often; a memo is not built. At the time the document was written, keyed retrieval from the memory file was built and tested but not yet in any prompt, and no live-model result shows a gain in completion, steps or false claims.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a long-horizon browser workflow that does not drown in its own history

### One app, one window, one corner pill

**Status:** built (merged to main; hidden end-to-end run passes; first visible launch with the owner pending) · **Page:** `docs/features/knack-shell.md` · **Targets:** Wordsmith

#### What it does

Knack.app is the dashboard in its own window with a Dock icon and a menu-bar item. When a run that uses the worker's real screen starts from the window, the window minimises itself and a 32-pixel pill in the bottom-right corner says what is happening and offers Stop. It never pops the window back on its own. (The state table says a pure sandbox job started elsewhere, for example from Background runs, shows the pill and leaves the window where it is; Routines, Run now is specified to minimise it. Rehearse to see which happens on the demo laptop.)

#### How it works

Window: 80% by 84% of the work area, centred, remembered per display; closing hides it; the Dock icon brings it back; quitting while a job runs asks first. The pill sits bottom-right, 16 pixels from the edges, holds a label of at most five words, and is never over a password or payment field. Only one interrupting surface shows at a time, and an approval raises a card, never a modal. A pure state machine of 18 transitions decides what the window and pill do, with kill always winning. The app starts its own engine and agent: live models if a Gemini key is present, example data otherwise, with a status line that says which. Settings (Command-comma) holds Use live models, Interruptions (Rarely, Balanced, Often), Coaching, Move aside while Knack works, Open at login, Appearance and Views. Unsigned local app and dmg build with electron-builder; a signed release needs the owner's Apple Developer ID.

**What is different.** Only one interrupting surface shows at a time, the pill is a status and not an interruption, and the window never pops back on its own.

#### Where to see it

The app itself: window, Dock icon, menu bar, corner pill. The sidebar status line reads Live models or Running with example data.

#### Demo moment

Start a routine from Routines: the window minimises to the Dock after 0.4 s, the pill reads what Knack is doing and shows Stop; when it finishes the pill becomes a check, fades, and Needs you shows the result. The window does not come back by itself.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Sidebar rows 9 to 6 and sidebar words 51 to 17 on Home; the 18 window and pill transitions are each a test | design measurement and offline tests | `docs/KNACK_UX.md (sections 2, 7); docs/knack-ux/shell-transitions.json` |
| A hidden run of the real Electron app with stand-in services checks the window size, the corner column (bottom-right, 16 px, card above pill, secure-input hold, Review, done, error, voice, Stopped, resume) and writes a picture of each page | offline hidden check; no real input or capture | `apps/desktop/KNACK_BUILD.md` |

#### Honest limit

Not yet seen by the owner on a real desktop with real windows behind it; per-display overlays for the ring are a known limit; multi-display pill placement is a spec, not a tested behaviour. The app is unsigned.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: an agent that works in the background and tells the worker in five words

### First run in three clicks

**Status:** built · **Page:** `docs/features/knack-shell.md` · **Targets:** G-Research

#### What it does

First launch asks two questions and shows one summary: a role card, one capture consent, and 'Show my week'. Everything else takes the role pack's safe defaults and is editable in Your data.

#### How it works

Click 1 picks a role (three cards from the packs); the pack's tools, risky actions set to 'never without me', short tone, gradual pace and hours are written to the memory file. Click 2 is the one consent: 'It records when you are active, never what you read: no page text, no URLs, no field values. The record stays on this laptop.' Yes, Not now and Never have equal weight; Not now asks again once after a week; Never never asks again. Click 3 shows four plain lines from the file just written and opens Home. Screen glances, the microphone, Accessibility, Screen Recording and Open at login are each asked once, in context, when first needed. The role card will also offer connection presets (landing), which adds one click.

**What is different.** Two questions and one summary, with a consent whose three buttons weigh the same.

#### Where to see it

The first window on first launch (no sidebar yet). Settings, Set up again reruns it.

#### Demo moment

Launch fresh: role card, the consent with three equal buttons, 'Here is what Knack will remember', then Home with the example insight badged Example data.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| About 20 clicks over 15 screens before; 3 clicks after. Words on the first screen 159 to 20 | design measurement of a prototype | `docs/knack-ux/07-first-run.md; docs/knack-ux/after/after-measurements.json` |

#### Honest limit

Measured on a prototype and by the reducer's tests; no person has done it. Permission dialogs (Accessibility, Screen Recording, Microphone) can only be granted by the owner in System Settings.

#### Hackathon target

- **G-Research (make the invisible visible)**: nothing recorded without a plain, equal-weight yes

### Command palette and keyboard

**Status:** built (shortcuts and the palette are on main; some of the spec's palette verbs are not) · **Page:** `docs/features/knack-shell.md` · **Targets:** Wordsmith

#### What it does

Command-K goes anywhere or runs a command, Option-Space asks Knack (hold to talk), and Option-Shift-Command-K stops everything. No keystroke ever approves anything.

#### How it works

In the dashboard today: Command-1 to Command-5 go to the five destinations, Command-comma opens Settings, Command-slash opens About this screen, Shift-Command-K stops everything while Knack is frontmost (a test says no key reaches an approval). Command-K opens the palette, which lists every screen and these actions: Take the tour, Switch to the Admin view (and back) and Print the firm brief. In the desktop: Option-Space (hold to talk), Option-Shift-Command-K anywhere to stop, Option-Command-P to pause or resume for an hour. The spec adds further palette verbs (Pause for 1 hour, Stop everything, Ask Knack, Copy my Monday note, Explain this screen and a palette-only 'Delete my data' with no shortcut by design); they were not on main when this was written. A guided tour of the five destinations is one row in the account menu.

**What is different.** Nothing new is claimed; the one deliberate rule is that no keystroke can approve anything.

#### Where to see it

Anywhere in Knack; the palette is Command-K.

#### Demo moment

Press Command-K, type the name of a screen and press Return; then press Command-2 to jump to Needs you. Say that no key approves anything.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measurement; the click budgets for the ten jobs are tested by a replay script | offline tests | `docs/knack-ux/jobs.json; docs/KNACK_UX.md (section 9)` |

#### Honest limit

The tap-to-type Ask bar is a lower-priority item in the build plan and may not be complete; the palette verbs named above are specified, not all built.

#### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: reaching any action without a menu hunt

### Design system with budgets as tests

**Status:** built (tokens, components and check scripts merged to main; screens still being brought to budget by their tracks) · **Page:** `docs/features/design-system.md` · **Targets:** G-Research

#### What it does

One token file and ten rules govern every screen: one hero per screen, details behind a disclosure or a short Hint, at most seven rows in a list, no gradients, glows or emoji. The limits are numbers a script checks, so a screen cannot grow back.

#### How it works

Budgets: a hero sentence of at most 16 words; a card with 8 words of title, 20 of body, a button of 3 (a hero action 5 words, decision D56); Home at most 50 words above the fold, Needs you 120, Growth 60; no paragraph over two lines in a default view; one badge above the fold; a sidebar of 6 rows with no hint words. check-copy.mjs reads the running screens against these budgets; check-clicks.mjs replays the ten jobs and fails above their click budget; a copy lint rejects banned phrases and a visible old product name; contrast is tested at AA in both themes. Weights are 400 and 600 only; icons are 14 inline SVGs; mono capitals appear only on chart axes and the work ribbon. A Hint (a small accessible 'i') may hold a unit, a definition or an interval and is never the only copy of a fact: origin badges, consent text, consequences, errors and limits stay printed.

**What is different.** Word, click and contrast budgets are tests that fail the build, and a Hint may never hold the only copy of a fact.

#### Where to see it

Every screen; docs/knack-ux/before and after hold the screenshots; packages/design/design-system.html is the preview.

#### Demo moment

Show Home before and after, side by side: 173 words and 10 controls above the fold became 47 words and 4 controls. Then press the Hint beside a number to show the interval one tap away.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Before: median 173 words above the fold across 20 worker screens (214 across 8 admin screens); 9 of 20 worker screens exceeded 400 words in total; measured at 1440 by 900 in the live mock | design measurement, one engine in mock mode, one browser, no users | `docs/KNACK_UX.md (section 2)` |
| After, on the static prototype: Home 47 words, Needs you 103, Routines 45, Growth 53, Firm 80, first run 20 | design measurement of a prototype; the real screens land a little above | `docs/knack-ux/after/after-measurements.json` |
| A friend's published design system was diffed line by line against ours: its tokens were byte-identical to ours; the enhancement was in components and density (sentence-case labels, one calm card family, collapsed chart footers, a play-through for the work ribbon). Three of its moves would have broken our honesty rules and were adapted, not adopted | design comparison, no users | `docs/DESIGN_DIFF.md (section 1)` |

#### Honest limit

These measure the interface, not people. The budgets are our choice. The after numbers are a prototype's headline content; the screens being built will land a little above them, and some screens were still over budget when this was written (a pending list in the copy lint shrinks as tracks land). The Evidence page is exempt from the word budget by decision D45.

#### Hackathon target

- **G-Research (make the invisible visible)**: the invisible made visible without clutter

### The Knack mark and brand

**Status:** built · **Page:** `docs/features/design-system.md` · **Targets:** G-Research

#### What it does

The mark is a solid disc with a ring offset behind it: the worker, and the understudy shadowing them. It appears in the sidebar, the Dock, the menu bar and the corner pill.

#### How it works

The lockup is the glyph then the word Knack in the display face at weight 600, with the disc as tall as the capital K and one disc radius between them. The ring is never recoloured for status; status is the pill's words and the menu-bar badge. The menu-bar template has six states in a fixed priority (stopped, needs you, glance, working, paused, idle). The Dock icon is an ink tile with a teal ring on the macOS canvas. There is no tagline in the app.

**What is different.** Nothing new is claimed; it is a design choice.

#### Where to see it

Sidebar top, first-run screen, Dock, menu bar, corner pill; docs/knack-ux/knack-brand-sheet.svg.

#### Demo moment

Show the brand sheet, then the menu bar changing from idle to a working dot when a routine starts.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measurement; the mark was already in packages/design/brand, and the dashboard had not used it before the Knack pass | no evidence yet (design) | `docs/KNACK_UX.md (section 6)` |

#### Honest limit

A visual decision, judged by eye. Menu-bar states depend on desktop wiring that the owner has not seen on a real menu bar.

#### Hackathon target

- **G-Research (make the invisible visible)**: a calm identity for a product that watches work

## 12. Privacy and safety

*What stays on the device, what leaves, and how to stop it.*

### Egress guard, ledger and canary tests

**Status:** built (built, with a known gap: older desktop paths are gated off by default but not re-reviewed independently) · **Page:** `docs/features/privacy-ledger.md` · **Targets:** G-Research, Wordsmith

#### What it does

One choke point sits between Knack and any remote model. Prompts are built from typed values, every call leaves a row in a ledger the worker can read, and a canary test plants secrets to see whether any reach the model.

#### How it works

Text calls carry only typed payloads (ids, enums, numbers built by code) from registered purposes. Image calls carry one frame held in memory for one call; the ledger records size, hash, model and latency but never the image. A frame is refused while secure input is on, from a denylisted app, from an unknown source, and in any unattended run; the Gemini key lives only in the main process and renderers get ephemeral tokens. The canary harness plants synthetic secrets in eleven flows, with a capturing fake model port, and counts how many arrive. A layer that registered no flow is listed as none, never counted as passed. The older desktop code that could send screenshots and file text straight to a model is off by default (decision D38) behind one switch.

**What is different.** A layer with no registered test flow is never counted as passed, the canary harness has negative controls to show it can fail, and the picture is never kept.

#### Where to see it

Your data, section 'What it looked at or sent': every call, with a delete beside it. Evidence has the canary table.

#### Demo moment

Open Your data and the record of what was sent: a row per call with model, size and time, no picture and no text. Say what is not in it: the older desktop paths, which are off.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| 0 of 11,456 planted canary tokens reached the model port across 88 runs of 11 flows (reference flows 0 of 728; integration flows 0 of 10,728); 0 leaks in 88 log, audit and queue files; the ledger was complete for every flow; one-sided 95% upper bound on the leak rate 3.35% per run | synthetic fixtures, offline, 8 seeds per flow | `evals/report.md (Privacy layer)` |
| 11 of 11 negative controls behaved as required (the instrument can fail); bucketing 0 failures over 594,114 cases; 27 of 27 must-catch shapes caught and 0 false positives on 34 ordinary values; static guard 0 violations in 345 files | synthetic, offline | `evals/report.md (Privacy layer)` |
| Independent privacy and honesty review (a separate Claude agent): no critical finding, 6 high; five fixed and re-verified at the time, one open then (older desktop paths that sent images and file text with no gate) | code review at 17:55 on 7 Nov; decision D38 has since switched those paths off | `evals/review/privacy_honesty.md` |

#### Honest limit

Zero leaks says nothing about a flow that was not run, and the planted strings are exact strings only. An allowed frame is raw pixels: the guard does not redact them, and the provider's own policy is not measured here. Model calls the worker asked for are recorded as metadata only. The ledger cannot see other software on the laptop. The older Alongside desktop paths are off by default but have not been re-reviewed independently.

#### Hackathon target

- **G-Research (make the invisible visible)**: what left the device made visible
- **Wordsmith (most complicated end-to-end browser-use workflow)**: an agent that uses cloud models without leaking what it reads

### Your data: see and delete

**Status:** built (merged to main; owner has not used it) · **Page:** `docs/features/your-data.md` · **Targets:** G-Research

#### What it does

Your data holds five things in one place: what Knack remembers, what it measures, what it looked at or sent, what your admin can see, and the capture and glance switches. Each line has a delete beside it, and 'Delete everything' asks for an exact confirmation.

#### How it works

Seeing anything takes one click and deleting takes three at most (Your data, Forget, Forget it, confirmed inline). The delete wording is identical in every section. No file path is printed on screen. The worker's plain 'what your admin can see' page lives here. Capture, screen glances, the microphone and folders are controlled here; behaviour preferences live in Settings.

**What is different.** What Knack remembers, measures and has sent is one place with identical delete wording, instead of five scattered ones.

#### Where to see it

Your data, the fifth item in the sidebar. The spec adds a palette row 'Delete my data' with no shortcut; it was not in the palette on main when this was written.

#### Demo moment

Open Your data, press Forget beside one remembered line, confirm inline, and watch it leave. Then show What it looked at or sent with no pictures in it.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Click budget: see in 1, delete in 3; five scattered places for 'my data' became one | design measurement of the old screens; replay script for the new paths | `docs/KNACK_UX.md (section 1, J5)` |

#### Honest limit

Measured as a design, not by people. Deleting a worker's ledger removes them from admin comparisons at once (tested on synthetic firms), but nothing here shows how a real deployment would audit that.

#### Hackathon target

- **G-Research (make the invisible visible)**: the worker can see what is held about them

### Memory file the worker owns

**Status:** built · **Page:** `docs/features/your-data.md` · **Targets:** G-Research

#### What it does

Knack adapts to a worker through one readable, editable Markdown file on the device. Only the worker's own actions or approvals can write to it; page text, tool output and model text never do.

#### How it works

Sections: Preferences, Procedure, Routines, Corrections, Skill state and Never, with a revision number in the header. Writes are atomic, a stale revision is rejected, the worker's edit wins and unknown sections are kept. A worker's correction is a precedent; three consistent ones become a proposed rule whose ceiling is no looser than anything already approved; a separate approval activates it; the rule is a versioned line, so deleting the line ends it. Precedents decay with a 30-day half-life. A personal procedure rule must also match expert outcomes in a shadow comparison. The first-run defaults come from the role pack.

**What is different.** Only the worker's own actions can write to it; a correction becomes a precedent, three consistent precedents become a proposal, and a separate approval activates it as a versioned line.

#### Where to see it

Your data, 'What Knack remembers'; first run shows four plain lines from the file.

#### Demo moment

Edit a line (for example a Never line) and show the next run respecting it; delete the line and show the rule ending.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| An injection test checks that page text cannot write to memory or raise a rule's ceiling | offline tests | `docs/reference-notes/bandit.md; services/engine/tests/handoff/test_memory.py` |

#### Honest limit

Mechanism tested offline; no worker has built a memory file by use. The precedent rule is an idea re-implemented from a hackathon project, with our own decay.

#### Hackathon target

- **G-Research (make the invisible visible)**: the adaptation is a file the worker can read

## 13. Evidence and honesty

*Every number with n, split, interval and origin; failures published.*

### Evidence page, make eval and the limitations register

**Status:** verified · **Page:** `docs/features/evidence-and-explain.md` · **Targets:** G-Research, HRT

#### What it does

One command rebuilds a report from the code that owns each number; the Evidence page renders it, ending on what it does not show. Nothing in the report is typed by hand.

#### How it works

`make eval` runs each section's own code and writes evals/report.json and report.md. Each section carries its origin badge (synthetic, simulated, real, unknown), n, split and interval level. Findings are generated, not footnotes. A limitations register keeps every known weakness with a severity. A section with no numbers says why instead of showing an invented value; the live study shows 'not run'.

**What is different.** The report is generated by the code that owns each number, findings are generated rather than written, and the limitations register ships inside the product.

#### Where to see it

More, For reviewers, Evidence (address #/evidence; exempt from the word budgets).

#### Demo moment

Open Evidence: the map of sections with their origin badges, the findings, then scroll to the limitations. Point at 'Live study: not run'.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| 35 sections: 33 with numbers, 2 not run (the live study and the role studies), 0 failed; 206 limitations (67 high, 111 medium, 28 low); 7 generated findings | synthetic origin throughout except the not-run live study | `evals/report.md; evals/report.facts.json` |
| About 6,156 test functions across the code base (a static count; parametrised cases not expanded) | offline tests | `evals/report.facts.json (tests)` |

#### Honest limit

Almost everything in the report is synthetic or simulated. The register is long on purpose. The report is regenerated at the freeze; quote the last full run, not a fast run.

#### Hackathon target

- **G-Research (make the invisible visible)**: making our own uncertainty visible
- **HRT (best use of data for predictions and decisions)**: baselines and intervals beside every number

### Plain-English explainer with a number check

**Status:** built · **Page:** `docs/features/evidence-and-explain.md` · **Targets:** G-Research

#### What it does

'Explain this' writes a short plain-English account of where time went. Every number in it must trace to the data, and it may not make a causal or expert claim.

#### How it works

An evidence packet holds the typed facts. The shipped wording is a code template that passes its own check on every packet and every intent. A model's wording (a local model first; a cloud wording attempt is on by default since D48, routed to Gemini) is used only if it passes the same check; otherwise the template is shown. The check proves each number traces to a field of the packet. It does not prove the packet is true.

**What is different.** A model's words are used only if every number in them traces to the evidence packet; otherwise the code template is shown.

#### Where to see it

Beside figures on the detail screens (Explain) and in Evidence.

#### Demo moment

Press Explain on Where time goes: a short paragraph with numbers; show that it is the template wording, and that a model's rewording would be used only if it passed the check.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| The template wording passed its own check on 320 of 320 (1.000 [0.988, 1.000]) | synthetic packets from 32 apprentice episodes | `evals/report.md (Evidence quality)` |
| Live, small n: local Qwen composing freely 1 of 30; rewording a code-written draft 12 of 30 [24.6, 57.7] first, then 24 of 30 [62.7, 90.5] after fixes (same kind of packets); cloud OpenAI composing 0 of 13 [0, 22.8]; cloud Gemini flash-lite 7 of 9 [45.3, 93.7] | real models, small n, packets synthetic, recorded 7 Nov | `evals/report.md (Limitations register: model_layer_is_optional_polish)` |

#### Honest limit

It improves readability, not accuracy: a sentence can still mislead with numbers that all trace. The second local-model figure was measured after fixing what the first run showed. The model layer is optional polish; the default is the template.

#### Hackathon target

- **G-Research (make the invisible visible)**: numbers a worker can read, each traceable to its source

### Generator-mismatch test (the realism matrix)

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** G-Research, HRT

#### What it does

We asked how much of each result survives when the pipeline is tested on a synthetic generator it was not built on. Much of it does not.

#### How it works

Three structurally different generators (continuous person effects, many valid paths, noisy capture, interruptions, a label that is a hidden state, not read from an emission table) with 40 people per dataset and three replicates. Every ordered pair of fit family and test family is scored, with a person-cluster bootstrap. Five expectations were pre-registered and scored afterwards.

**What is different.** We tested our own methods on generators they were not built on and published the drop, with expectations registered beforehand.

#### Where to see it

Evidence (Findings), the realism section; evals/realism/INTERPRETATION.md.

#### Demo moment

On Evidence, open the first finding: the stuck model's advantage depends on the generator. Read the two numbers: 0.071 nats on its own generator, 0.008 to 0.015 on harder ones.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Stuck model: edge over time-since-progress 0.071 falls to 0.008 to 0.015 nats per bin; a model trained on the first generator is 0.43 to 0.53 nats worse than the baseline on the others and overshoots the false-alarm budget 1.7 to 4.2 times | synthetic, 120 people per cell | `evals/report.md (Findings); evals/realism/INTERPRETATION.md` |
| Genome: precision 92% and recall 95% fall to 48 to 71% and 49 to 68%; false attribution rises from 1.1 s to 46 to 59 s per case | synthetic, 87 to 92 people per family | `evals/report.md (Findings)` |
| Routine finder: raw precision 22% on the first generator is 44 to 97% on the others, recall falls to 45 to 92%; proposals after the gate stay at 74 to 100% precision | synthetic, 120 people per cell | `evals/report.md (Findings)` |
| Of the five pre-registered expectations: three held, one half-wrong, one not supported | synthetic | `evals/realism/INTERPRETATION.md` |

#### Honest limit

All three generators were written by the same team as the analytics and share the person hierarchy, interruption process and task grammar. Passing or failing this test says how robust the methods are to these changes, not how real workers behave. The only evidence about real people would be the live study, which has not been run.

#### Hackathon target

- **G-Research (make the invisible visible)**: the invisible limits of our own methods, shown
- **HRT (best use of data for predictions and decisions)**: a result tested out of distribution

### ML v2, held-out: mostly negative

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** HRT

#### What it does

We tried to improve the stuck model and the genome with pre-registered candidates. Most were rejected on held-out data, and the reports say so.

#### How it works

Candidates and rules were frozen before the held-out run, which ran once. The primary metric for the genome families is the mean absolute error in seconds of the recovered price of a deficit, paired against the first method; for the stuck model it is log loss, paired against the first model, with adjusted intervals.

**What is different.** Candidates and decision rules were frozen before a single held-out run, and the rejections are reported as findings.

#### Where to see it

Evidence (Findings: ML v2); evals/mlv2/PLAN.md and results.

#### Demo moment

On Evidence, read: the expert-envelope ensemble and the counterfactual price were rejected as harmful, by 3.81 and 1.17 seconds.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Genome candidates: the expert envelope (E4) +3.81 s [+2.30, +5.19] and the counterfactual price (Q1) +1.17 s [+0.44, +1.87] absolute error: both rejected as harmful; only learned substitution costs (E1) was accepted, -0.92 s [-1.85, -0.21] | synthetic, 6 held-out apprentice cohorts, 96 novices | `evals/report.md (Findings); evals/mlv2/results/heldout_genome.json` |
| Stuck model: gradient boosting with Platt calibration accepted as a small gain, -0.0039 nats (99.3% interval [-0.0062, -0.0017]); under mismatch the plain time-since-progress rule beats the first model in all three roles | synthetic, 32 held-out people; mismatch matrix | `evals/mlv2/results/heldout_hazard.json; evals/mlv2/results/heldout_mismatch.json` |
| Neither version transfers to the language-model participants' traces: log loss 1.43 and 1.46 against 1.08 for the base rate | simulated participants (language model), not people, 24 participants | `evals/mlv2/results/transfer_sim.json` |

#### Honest limit

Held-out replicates share our generator, so they catch overfitting to one noise draw, not learning the generator. No variant qualified for the data-analyst role.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: pre-registration, held-out discipline and honest nulls

### The simulated study sat at the floor

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** HRT, G-Research

#### What it does

We ran a pre-registered study with language-model participants (not people) to test the pipeline and whether coaching changes later unassisted work. The outcome sat at the floor, so it says nothing about the coach.

#### How it works

16 coached and 8 sham-arm participants, within-participant and counterbalanced, with an A/A arm in which the coach is silent in every block. Participants are language models with a 280-character self-written note as 'memory'. A follow-up pilot with more reasoning effort was stopped by its own criterion.

**What is different.** A study design was run end to end with language-model participants to test the pipeline and its enforcement, with an A/A arm and a power calculation, and a null reported as a null.

#### Where to see it

Evidence (Findings and the simulated section); evals/study_sim/REPORT.md.

#### Demo moment

On Evidence, read: 30 of 32 unassisted post-tests scored 0; the study validated the pipeline and the enforcement (no nudge outside the trained skill's block), not the coach.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Mean difference 0.094 [-0.051, 0.239], exact p = 0.5; 30 of 32 coached post-tests scored 0 and 16 of 16 A/A post-tests; the action cap was hit in 18 of 32 | simulated participants (language model), not people, n = 16 + 8 | `evals/study_sim/REPORT.md; evals/report.md (Simulated participants)` |
| Enforcement held: 0 non-silent coach polls in post-test blocks and 0 in blocks with the coach off; 12 nudges were shown, all in train blocks | simulated | `evals/study_sim/REPORT.md (section 5)` |
| Run 5 pilot stopped: 0 of 6 post-tests above zero (needed 3) | simulated | `evals/report.md (Simulated participants)` |
| What the n = 4 live design could detect: the smallest possible exact p is 0.125; for a medium effect the interval excludes zero 4.4% of the time at n = 4 and 27.3% at n = 16 | Monte Carlo of the design, 10,000 replications; a property of the design | `evals/report.md (Study power)` |

#### Honest limit

The live study with four teammates has not been run. The role studies (programmer, analyst) were not run: one of three programmer feasibility pilots was usable and none are results. A higher score after coaching could be instruction-following plus a self-written note, not learning.

#### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a power calculation done before spending a study
- **G-Research (make the invisible visible)**: a null reported as a null

### Other results that went the wrong way

**Status:** verified · **Page:** `docs/features/what-did-not-hold-up.md` · **Targets:** G-Research

#### What it does

Four more results that did not meet their targets, stated beside the features they concern.

#### How it works

Each target was written before its held-out run; a miss is reported, not reworded.

**What is different.** Targets were written before the held-out runs; a miss is reported against its target.

#### Where to see it

Evidence (Findings and sections); each feature page lists its own miss.

#### Demo moment

Pick one and read it: 'Cue did not make people resume faster at the median.'

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Cue: 'faster to resume' not met (median paired difference 0.0 s [-9.5, 0.0]); false-nudge target met at 0.73 an hour | synthetic, 40 simulated personas, 481.5 hours | `evals/cue/held_out.json` |
| Attention router: criterion 7 not met (+0.33 can-wait toasts a day [+0.08, +0.58]); 11 of 12 met | synthetic, 200 simulated workers | `evals/attention/report_held_out.json` |
| Insights: planted independence rise selected in 47 of 100 worlds (target 0.8); false celebration when errors rise 14 of 100 (target 0) | synthetic, 100 worlds per effect | `evals/insights/results/heldout.json` |
| Computer use, held-out clean n = 4: 1 completed; injected n = 20: 20 of 20 paused at step 0 (detector, text only) | real model (OpenAI), our sandbox | `evals/report.md (Agentic evaluation)` |

#### Honest limit

These are all simulated or sandbox results; none is about real workers.

#### Hackathon target

- **G-Research (make the invisible visible)**: our own failures made visible

## 14. Roles

*One deep role pack and two thin ones.*

### Role packs: benefits processor deep, analyst and programmer thin

**Status:** built · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

#### What it does

A role pack turns raw events into steps, says what an expert does, which actions need a click, what tone to use, which routines to look for and what to teach in what order. The benefits processor pack is deep; the data analyst and programmer packs are thin starting points.

#### How it works

A pack is a validated folder (id, onboarding questions for tools, risky actions, tone, pace and hours; extra step types and their mapping from events; expert steps with allowed reorderings; risk classes with label patterns; routine templates; a curriculum; persona parameters; priors for pooling). The benefits pack also has an oracle, task configuration and sandbox sites. The thin packs fill every key but the oracle, tasks and the full expert policy, and differ visibly in questions, steps, risk classes and tone: the programmer's risky actions are force-push, deleting a branch, merging to main and publishing; the benefits processor's are submitting a case, issuing a payment and sending a letter. A loader checks packs against a JSON Schema and the pack format reserves a slot for plugin references.

**What is different.** A role is a validated folder of data (steps, expert policy, risk classes, tone, routines, curriculum), so adding a job is adding data, and the thin packs differ visibly in their risky actions.

#### Where to see it

First run (the role cards), Settings, Set up again, and the Admin Roles view.

#### Demo moment

At first run, choose each of the three cards; show how the four lines on the 'what Knack will remember' screen differ (tools, never-without-me actions, hours).

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Pack format and loader covered by 66 test functions; packs validate against the schema | offline tests (static count) | `evals/report.facts.json (tests.by_dir, packages/packs/tests)` |
| Thin roles on harder synthetic generators: routine finder raw precision 88 to 98%, recall 60 to 92%, proposal precision 100%; git habits for the programmer: precision 116 of 116, recall 116 of 120 | synthetic | `evals/report.md (Findings, and Git habits)` |
| Stuck model: the accepted v2 improvement qualifies for benefits processor and programmer; no variant qualified for data analyst | synthetic, held-out | `evals/mlv2/results/heldout_hazard.json` |

#### Honest limit

The thin packs are starting points and have not been validated on real work. Genome recovery was not evaluated for them because the named-deficit labels belong to the benefits pack. Even the deep pack has no real benefits-processor data behind it.

#### Hackathon target

- **G-Research (make the invisible visible)**: the same lens on three different jobs
- **Wordsmith (most complicated end-to-end browser-use workflow)**: one workflow deep, two shallow

### Deeper programmer and data-analyst roles

**Status:** landing (ROLE-DEPTH (Track F), additive only; built overnight, not on main yet; docs/roles/*.md have not landed) · **Page:** `docs/features/role-packs.md` · **Targets:** G-Research, Wordsmith

#### What it does

The two thin roles are being given more depth: more steps and habits, without changing any existing id, expert path or generator parameter. They get a new depth value, 'standard' (full content, not validated with people), and the dashboard keeps the label 'Starter pack' for packs that are not deep.

#### How it works

Per owner decision D55 the work is additive only, and per the lead's decision D56 every new step is optional and uses new step types, so the frozen sandbox tasks and the role studies are untouched. No synthetic traces exist for the new step types, so screens that depend on them say 'not enough data'. The role studies use private sandbox worlds for the programmer (editor, tests, console) and the analyst (table, filter, pivot, chart with planted data issues).

**What is different.** Additive only: new optional steps on new step types, so nothing already measured changes.

#### Where to see it

Not on main yet; see docs/roles/ when it lands.

#### Demo moment

Not yet available. Do not show until it lands.

#### Evidence and its label

| What | Label | Source |
|---|---|---|
| Nothing to quote yet; the role studies themselves were not run (1 of 3 programmer feasibility pilots was usable; no analyst pilot) | not run | `evals/report.md (Study across roles)` |

#### Honest limit

Not verified. Update this entry from docs/roles/*.md after it lands.

#### Hackathon target

- **G-Research (make the invisible visible)**: more than one job
- **Wordsmith (most complicated end-to-end browser-use workflow)**: more than one workflow

## What exists elsewhere, and how Knack differs

We read these projects and re-implemented the ideas. We took methods, not claims, and we describe only what our read-only notes record. The licence rule, from `docs/REFERENCES.md`: only MIT sources (Clicky and its Windows fork, clickyyy, VisionOS) may be copied, with a header and a notice; Sentient OS (AGPL-3.0) is design only; for everything else we re-implemented from the idea. Nothing from `references/` was run or imported. The notes are short, so this table says less about each project than the project does about itself.

| Project | What it is, per our notes | What we took | How Knack differs | Note |
|---|---|---|---|---|
| Clicky (farzaa/clicky, MIT) and its Windows fork | The app captures screenshots, asks a model, speaks and flies a cursor overlay to a point; per our read-only study it never clicks. The fork's plugin runs single actions at screen coordinates for an outside agent. | Overlay algorithms (through the owner's earlier library, with notices); two small modules lifted into vendor/clicky with headers: a scoped lease and a post-action check; the idea of ring-accuracy fixtures. | Knack adds the expert comparison and fading help, and acts through fact handles and a deterministic gate rather than coordinates. It reads the target under the pointer before it acts, and it reports held-out completion. | `docs/reference-notes/clicky-reuse.md; docs/reference-notes/computer-use-comparison.md` |
| Sentient OS (AGPL-3.0, design only) | A real multi-step loop on real Mac apps using accessibility actions first. Per our study the loop and context handling live in an external agent command line and a vendor-signed helper, and the repository holds no task-completion measurement. | Ideas only, through a clean-room prose note: judge, verify, prepare and press-to-fire cards; read before write; retry a failed check but never replay an action. No code, comments or prompts were copied. | Knack decides 'done' in code, not from the model's final claim, and publishes a held-out completion count (1 of 4). Our study says absence of a reported failure there is absence of measurement, not evidence that it avoids our problems. | `docs/reference-notes/computer-use-comparison.md; docs/DECISIONS.md (D24, REQ-10)` |
| Okidoki (repository not available) | Idea only, from its Devpost text: record a run once, replay it deterministically, and call the model only when a precondition fails. | The shape of a routine: steps with a precondition and a postcondition; divergence counts as a non-match in shadow mode. | Routines are a JSON step language, never generated code; nothing replays on a real account; the worker opts in per routine. | `docs/reference-notes/okidoki.md` |
| VisionOS (MIT) | A coordinator with one worker and a replaceable request: a generation counter, cancel events, deadlines and a watchdog. | The pattern, rewritten in our own supervisor (no code copied). | Per-run deadlines for long benefit runs, a file kill flag the watchdog polls, and a stop that never depends on a model call. | `docs/reference-notes/vision-os.md` |
| BandIt | Idea only: a model proposes and a guard clamps to a human-approved ceiling; learned rules need three approved precedents and a separate approval. | Precedents become rules in the memory file, with a ceiling and versions. | Precedents decay (30-day half-life) and only the worker can write. | `docs/reference-notes/bandit.md` |
| MOA | A harness that seeds cases with answer keys and a simulated human, scoring accuracy, false positives and recovery. | Planted truth with a known answer, and a simulated human as the label source. | A split by person for held-out evaluation, an independent generator, and an interval on every number. | `docs/reference-notes/moa.md` |
| Mark8 | One typed event stream as the only source of truth, a pure reducer, replay on a virtual clock, and a baseline beside every prediction. | The event store, the pure reducer, replay with idle gaps squeezed, a baseline next to every number. | Events carry no free text, URLs or field values; origins are partitioned; we copy the method, not the claim. | `docs/reference-notes/mark8.md` |
| Pupil | Implicit reaction labels (stopped within 4 s means corrected; the same request within 10 s means repeated) and a gate in code. | Implicit labels for coach prompts and the code-decides gate. | Labels become a reward feeding an off-policy estimator; the logging policy is randomised with recorded propensities; held-out by person. | `docs/reference-notes/pupil.md` |
| Drigil | A fading ladder (three clean runs promote, two errors in five demote, assisted runs change nothing) and a dignity gate. | The level rules and the gate. | Mastery is continuous and decays with absence; false nudges per hour are measured on synthetic stuck episodes. | `docs/reference-notes/drigil.md` |
| Rouge | Code checks that the final observation holds the requested result before success is claimed; never-read fields kept as data. | The completion check idea and sensitive fields as data. | Structured result fields per calculator on a fresh observation; a quarantined reader and taint tracking in addition. | `docs/reference-notes/rouge.md` |
| PodsControlMac | Tags the events the automation posts so its own monitors ignore them, and backs off when real input is seen. | Agent events marked as agent; background runs yield on human input. | Yield is a first-class supervisor path with a checkpoint and a hold-off; yield measured at about 30 ms median. | `docs/reference-notes/podscontrolmac.md` |
| Stride | Event-level scoring (episodes detected, false alarms an hour), nested leave-one-subject-out with a false-alarm budget, and a limitations register. | How the stuck model is scored, and the limitations register. | Two baselines at the same alarm budget; person-level intervals; every claim says what it does not show. | `docs/reference-notes/stride.md` |
| JetBrains Key Promoter X (inspiration only) | Lists missed keyboard shortcuts. | The idea of a compact list of what you repeat. | The repeat list counts repeated actions that could be automated, ranks by minutes saved, never nags and never runs anything. | `docs/DECISIONS.md (D46)` |
| Alongside (the owner's earlier open-source library, first commit 31 Oct 2026) | The base of the desktop coach: overlay, level engine, learner store, agency policy and audit, mock mode. | Copied into apps/desktop at the start of the build; notices kept. | Its real actuator and multi-step loop were on by default; Knack turns both off and rebuilds the guards. Of 303 source files, 182 unchanged, 86 modified, 35 removed at the README's count (recompute at the freeze). | `README.md (Reuse: Alongside)` |

Not verified: any comparison with commercial products. The sources here do not cover them, so this document makes none.

## Numbers you may quote

Only with the n, the split, the interval and the origin printed beside them. Numbers that have no interval in their source (the dignity gate table, the 14 of 14 replay, the pooled start-or-wait figures, the calendar table, the section and limitation counts) are left out of this box on purpose; they stay on their pages with their label. Where two numbers are marked 'quote both', quoting one without the other would mislead. All are from the report generated on 7 Nov 2026 at 21:40 UTC unless the source says otherwise; if the report is regenerated, re-check each line against its source file before the freeze.

| Number | n and split | Origin | Source |
|---|---|---|---|
| Real novice-to-expert gap 229.6 s per case [192.7, 272.6]; expert against expert 7.1 s [-2.8, 18.4]; shuffled-label null 46.2 s [-36.4, 116.9] | 24 people; 1,000 permutations; 95% | synthetic | `evals/report.md (Controls)` |
| Planted-deficit recovery: precision 92% [84.5, 98.6], recall 95% [88.6, 100.0] on our first generator; 48 to 71% and 49 to 68% on three harder ones (per-family intervals in evals/realism/REPORT.md). Quote both | 16 people (87 to 92 per harder family); cluster bootstrap | synthetic | `evals/report.md (Deficit recovery, Findings)` |
| Skipping the cliff check leaves a nearby edge unwarned on 107 of 200 households (53.5% [46.6, 60.3]); more than 50 pounds a month on 42 of them | 200 households; Wilson 95% | synthetic | `evals/cases/skip_consequences.json` |
| Stuck model: log loss 0.436 [0.422, 0.451] against 0.509; its edge over time-since-progress falls to 0.008 to 0.015 nats on harder generators (one of nine diagonals not clearly above zero; per-cell intervals in evals/realism/REPORT.md). Quote both | 4 people, leave one out; 120 people per harder cell | synthetic | `evals/report.md (Stuck hazard, Findings)` |
| Ski rental with predictions: regret 1.332 [1.322, 1.342] against 1.776 [1.765, 1.786] at break-even; building at once 1.273 [1.257, 1.290]. Quote all three | 4,000 simulated routines | synthetic | `evals/report.md (Ski-rental build timing)` |
| Routine proposals after the value gate: 6 of 6 planted [61.0, 100.0]; the raw finder is 22% [12.9, 34.4] (12 of 55 clusters). Quote both | 4 personas | synthetic | `evals/report.md (Routine finder)` |
| Real model on the sandbox: clean 18 of 20 [0.70, 0.97]; layout change 20 of 20 [0.84, 1.00]; one-off error page 0 of 20 [0.00, 0.16] with 20 false claims, all caught by the code check. Quote all three | 20 households per condition | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| Scripted red team: attack success 0.0% [0.0, 8.4] with every layer on, 100.0% [91.6, 100.0] with all off. Real model: 0 of 126 against 5 of 126 with the intervals overlapping | 42 attacks, 31 clean pages; real model 42 cases x 3 repeats | synthetic; real model | `evals/report.md (Red team)` |
| Computer use held-out: clean 1 of 4 completed (Wilson [0.05, 0.70]); injected 20 of 20 paused at step 0 (Wilson [0.84, 1.00]; text-only pages) | 4 and 20 households, seeds used up | real model (OpenAI), our sandbox | `evals/report.md (Agentic evaluation)` |
| 0 of 11,456 planted canary tokens reached the model port; 0 of 88 runs; one-sided 95% upper bound 3.35% per run | 88 runs of 11 flows, 8 seeds each | synthetic, offline | `evals/report.md (Privacy layer)` |
| Git habits: 116 of 116 flagged habits were planted (100% [96.8, 100.0]); 116 of 120 planted habits found (97% [91.7, 98.7]); placebo false flags 1% [0.4, 2.4] | 120 scripted developers, fresh seeds | synthetic | `evals/report.md (Git habits)` |
| Local model: commit category 91.8% [84.7, 95.8] against 77.5% [68.3, 84.7] for rules | 98 held-out items | synthetic | `evals/report.md (Local model digests)` |
| Pointing by description: Gemini flash-lite 95% [90, 98] (140 of 147), median 0.93 s | 147 positives, 43 negatives | synthetic sandbox screenshots | `evals/modelbench/REPORT.md` |
| Cue (simulated): false nudges 0.73 an hour [0.64, 0.83], target met; faster-to-resume median 0.0 s [-9.5, 0.0], target not met. Quote both | 40 simulated personas, 481.5 hours | synthetic | `evals/cue/held_out.json` |
| Attention router: 0.150 [0.141, 0.159] against 1.512 [1.447, 1.582] non-safety interruptions per flow hour; 11 of 12 criteria met | 200 simulated workers, 2,000 worker-days | synthetic | `evals/attention/report_held_out.json` |
| Insights on null data: 0.0037 false pointers per worker-week [0.0027, 0.0047]; admin 0 of 160 admin-weeks | 2,400 synthetic people; 40 synthetic firms | synthetic | `evals/insights/results/heldout.json` |
| Stop reaches a running helper in a median 33 ms; 8 of 8 within 1 s (Wilson [0.68, 1.00]) | 8 trials on a busy laptop | synthetic | `evals/report.json (runtime, stop)` |
| Simulated study at the floor: 30 of 32 post-tests scored 0; difference +0.094 [-0.051, 0.239], exact p = 0.5 | 16 coached and 8 sham participants | simulated participants (language model), not people | `evals/study_sim/REPORT.md` |

## Things we do not claim

- That novices become experts. We claim only that the system lifts novices and shows its limits; Growth measures help needed, not expertise.
- That coaching helps a person, or that anything is validated, proven or works on real users. The live study with four teammates has not been run and the simulated study sat at the floor.
- That the stuck model or the work genome hold up on harder synthetic data. They mostly do not; say so beside any number from the first generator.
- That nothing leaves the laptop. Say instead: every call from our services is listed, in mock mode none left, an allowed frame is raw pixels, and older desktop paths are off by default but not independently re-reviewed.
- That the agent 'works' without its conditions: our sandbox sites, small n, one model family at the time, and code decides done.
- That computer use is reliable, or that Knack has clicked on a real desktop through an agent. One supervised click passed; the agent's own actuator then failed its first check; held-out completion was 1 of 4.
- That the gate resists hostile pages. The injected condition carries text only, so it shows the detector pauses.
- Any Gemini result beyond the sandbox bake-off, or that the earlier OpenAI numbers describe the Gemini configuration.
- That the synthetic firm, the admin comparisons or any calendar or commit result describe real people or real workplaces.
- That an admin view is lawful out of the box. A real deployment needs a lawful basis and notice to workers.
- That Hey Knack, voice guidance or 'do it for me' have been run with a microphone or a real click. They are built and tested offline.
- That Connections or the deeper roles work; they are landing and not verified.
- That Cue makes people resume faster at the median; the simulated target was not met.
- That the oracle is the law. It agrees with PolicyEngine UK within 1 pound on only 8 of 20 households.

## Where the source documents disagree

Found while writing. Each row names both files; the third column says which one this document follows. Fix the stale one before the freeze, or quote only the followed number.

| Topic | Followed | Disagrees | Used |
|---|---|---|---|
| Privacy canary count | evals/report.md and evals/report.facts.json (generated 7 Nov 21:40 UTC): 0 of 11,456 planted tokens, 88 runs of 11 flows, one-sided bound 3.35% per run | README.md and docs/drafts/CLAIMS.md (C40): 0 of 11,336, 80 runs of 10 flows, 3.7% | the generated report |
| Size of the report and register | evals/report.md: 35 sections (33 with numbers, 2 not run), 206 limitations (67 high, 111 medium, 28 low) | docs/FEATURE_CATALOGUE.md and docs/drafts/DEVPOST.md: 32 sections, a register of 124 (34 high, 69 medium, 21 low); docs/MVP_STATUS.md: 32 sections ok, 1 pending, 2 not run | the generated report |
| Test counts | docs/MVP_STATUS.md (about 21:20): 3,889 + 1,726 + 541 + 2,684 passed across engine and packs, agent, dashboard and desktop; docs/FIRST_LAUNCH.md (23:50): dashboard 741, desktop 3,079 | evals/report.facts.json: 6,156 test functions, a static count with parametrised cases not expanded | quote none as a pass count without saying how and when it was counted; re-run `make test` at the freeze |
| Reviewer reproducers | docs/FIRST_LAUNCH.md (23:50): 185 on the agent branch, not yet merged; docs/MVP_STATUS.md and evals/agentic/ITERATIONS_8.md (branch): 183 of 183 | README.md and docs/FIX_LEDGER.md: 172 of 172 | 183 of 183, the last figure on a merged tree |
| Simulated-study power at n = 16 | evals/report.md (Study power): false positives 4.9%; power 10.2%, 27.3%, 74.8% for small, medium, large | evals/study_sim/REPORT.md and the register entry sim-power: about 6% false positives and 12%, 29%, 76% | the Study power table |
| Always-listening microphone | docs/DECISIONS.md D52 and docs/knack-ux/09-wake-voice.md (branch): 'hey knack' listening is on by default, on-device | docs/FLAGS.md and docs/FEATURE_CATALOGUE.md: hold to talk only, no always-listening microphone | D52 (later); the other two are stale |
| Rung definitions | evals/agentic/REAL_CLICKS.md: R2 a model proposes one step in TextEdit; R3 and R4 are attended sandbox rungs; unattended real-desktop runs are not on the ladder | docs/FLAGS.md and docs/DECISIONS.md D48: the reviewer's no-go for 'model-driven (R2) and unattended (R3, R4)' runs; docs/REQ7_PLAN.md: R2 a click and a typed field on a sandbox page, R3 a full household, R4 a long-horizon run | evals/agentic/REAL_CLICKS.md |
| Cloud wording for 'explain this' | docs/FLAGS.md: the cloud attempt is on by default (D48), routed to Gemini, always behind the number check with a template fallback | README.md and docs/FEATURE_CATALOGUE.md: cloud wording off by default | docs/FLAGS.md (later) |
| Computer-use 'false claims' | docs/reference-notes/cu-failure-diagnosis.md and evals/agentic/ITERATIONS.md (correction): the harness accepted wrong calculator inputs; independent recomputation caught them | evals/report.md (Agentic evaluation): '2 false claim(s)' | the corrected wording; the generated report has not been re-worded |
| Alongside reuse counts | README.md: 182 unchanged, 86 modified, 35 removed of 303; 345 new (about 20:53 UTC) | docs/drafts/CLAIMS.md (C65) and docs/drafts/DEVPOST.md: 205 identical, 70 modified, 28 not carried over; 313 new (about 18:15 UTC) | README.md; the counts move and are recomputed at the freeze |
| Which model provider | docs/FLAGS.md and docs/DECISIONS.md D49: Gemini is the default, the OpenAI key was revoked | docs/drafts/DEVPOST.md and docs/drafts/DEMO_SCRIPT.md: OpenAI primary, Gemini in progress; README.md table: voice 'flagged off' | docs/FLAGS.md; the drafts are stale |
| Cue and Insights status | evals/report.md and evals/cue/held_out.json, evals/insights/results/heldout.json: held-out runs done | docs/FEATURE_CATALOGUE.md and docs/drafts/DEMO_SCRIPT.md: 'building' or 'pending' | the generated results |
| Words after the Knack redesign, Roles | docs/knack-ux/after/after-measurements.json: 35 words | docs/KNACK_UX.md (section 2 table): 36 | the JSON |

## What is landing, and where to look

| Item | Document | State at the time of writing |
|---|---|---|
| Connections: curated MCP plugins and role presets (CONNECTIONS, Track E) | `docs/CONNECTIONS.md` | built overnight per docs/FIRST_LAUNCH.md; not on main; the panel slots exist |
| Deeper programmer and data-analyst roles (ROLE-DEPTH, Track F) | `docs/roles/*.md` | built overnight per docs/FIRST_LAUNCH.md; not on main |
| Demo shot list and spoken lines (DEMO-DIRECTOR) | `docs/KNACK_DEMO.md` | not on main |
| Computer use on Gemini, development results (AGENTIC-3) | `evals/agentic/ITERATIONS_8.md` | on branch worktree-agent-acf889b730112335b; merges after its full suite is green (docs/FIRST_LAUNCH.md) |

When one of these lands, update its page in `docs/features/` and the status in `docs/features/index.md`.

## Sources read

`docs/FEATURE_CATALOGUE.md`, `README.md`, `docs/KNACK_UX.md`, `docs/knack-ux/*`, `docs/FLAGS.md`, `docs/DECISIONS.md` (D41 to D55), `docs/MVP_STATUS.md`, `docs/FIX_LEDGER.md`, `evals/report.md`, `evals/report.json`, `evals/report.facts.json`, `evals/realism/INTERPRETATION.md`, `evals/mlv2/PLAN.md` and `evals/mlv2/results/`, `evals/attention/report_held_out.json`, `evals/insights/results/heldout.json`, `evals/cue/held_out.json`, `evals/agentic/ITERATIONS.md`, `evals/study_sim/REPORT.md`, `evals/modelbench/REPORT.md`, `evals/cases/skip_consequences.json`, `docs/reference-notes/*.md`, `docs/REFERENCES.md`, `docs/INSIGHTS_DESIGN.md`, `docs/ATTENTION_DESIGN.md`, `docs/CONTEXT_ENGINEERING.md`, `docs/REQ5_PLAN.md`, `docs/REQ7_PLAN.md`, `docs/IMPLEMENTATION_SPEC.md`, `docs/SPIKES.md`, `docs/FIRST_LAUNCH.md`, `docs/drafts/*.md`, and a few code headers under `apps/desktop/src/main/wake/` and `apps/dashboard/src/components/home/navModel.ts`.
