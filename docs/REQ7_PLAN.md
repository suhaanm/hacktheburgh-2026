# REQ-7 plan: Cue (stuck rescue), independence score, agentic reliability, realistic data, role studies

Owner request, Sat 7 Nov 2026 (about 17:30 GMT). Status: BUILDING (decisions D32 onward in `docs/DECISIONS.md`). Everything here is flagged off by default and the lead turns a flag on only after seeing it work end to end. Every item is also listed in `docs/FEATURE_CATALOGUE.md` (the presentation list) and `docs/IDEA_BOARD.md` (the request log).

Five workstreams:
1. **AGT**: computer use and every other agentic path made reliable over long horizons; real desktop clicks, supervised, end to end.
2. **DAT**: why the data looks planted, and a much more realistic generator (still labelled synthetic).
3. **STU**: the simulated study extended to the programmer and data-analyst roles, with depth.
4. **CUE**: the stuck-rescue feature: sees the screen, finds the next step, guides, asks a multiple-choice question when unsure, teaches, fades.
5. **GRO**: the assist ledger and the independence score, with a Growth screen.

## 1. AGT: computer use and long-horizon agents

**Why computer use gave up (agent-core's finding, n = 3).** Tier-3 goals carry no household values by design, so the model had nothing to type and said it could not finish at step 1, taking no action. That is an honest refusal caused by our design, not a model failure.

**Fix: fact handles.** The model never sees real values. The goal carries typed handles (`{household.income}`, `{household.children}`) and the model emits `type_fact(handle)`; code resolves the value and the actuator types it. Screens still show what was typed (unavoidable); prompts and logs hold handles only. The same idea keeps real case data out of cloud prompts later.

**Iteration protocol (pre-registered before the first run).** `evals/agentic/PLAN.md` states success criteria before any live run: tier-3 benefits task, n at least 20 per condition (clean, layout v2, 503 glitch, injected page which must pause), success with Wilson lower bound at least 0.8, zero false claims, injected pages paused 100%, every irreversible action gated. Loop: run, read every failed trace, change one thing (prompt, state summary, tool, retry, memory of steps done, verification), re-run on fresh households, log each iteration in `evals/agentic/ITERATIONS.md` (what changed, why, before and after with n, cost). In-sample fixes are marked in-sample; a fix is confirmed only on fresh households. Spend is capped by the owner (D32).

**Long-horizon suite `LH`.**
- LH-1: 10 households in sequence across the three sites with case notes (150+ steps).
- LH-2: human input mid-run (yield, resume from a step-level checkpoint, not a restart).
- LH-3: error injection (503s, layout change, a popup, expiring session) with recovery.
- LH-4: mixed tools (browser, local file, the Python child agent).
- LH-5: an overnight batch with the morning report.
Metrics: completion, false claims (must be 0), recoveries, steps, wall time, cost, safety stops. The programming and data agents (runtime track) get their own long-horizon tasks (fix failing tests across 10+ steps; clean, join and aggregate larger data with sanity checks).

**Known flaws to fix:** resume restarts the whole run; tier-2 cap of 20 actions per navigator; no checkpoint granularity; `QuartzBackend` has no key chords or drag.

**Alternative actuator experiment.** The key lists `gemini-2.5-computer-use-preview-10-2025`. Compare it with OpenAI computer use on the same suite behind the same SafetyPipeline; keep whichever is better per tier; report both.

**Real desktop clicks: a ladder, owner present, kill hotkey (option-shift-command-K).** Each rung needs the owner's go in chat and stops for a report; never a real purchase, never a real account.
- R0: dry run, overlay only, on the real screen (draw where it would click, click nothing).
- R1: TextEdit, type a word (the check that failed on 7 Nov; fixes are tested only with a fake backend so far).
- R2: one click and one typed field on a sandbox page in a dedicated browser window.
- R3: a full household on the sandbox sites with real clicks.
- R4: a short long-horizon run with real clicks.
The actuator hit-tests the target window and checks display scale before every action, as now.

## 2. DAT: realistic data

**What is causing it.** The people are written by us: planted deficits injected as discrete events, scripted apprentices, clean timing distributions, little person-to-person variation, no fatigue, learning or interruptions, labels read from our own `progress` events, and four people. The pipeline can only be shown to recover what we planted.

**What I will and will not do.** I will make the synthetic data far more realistic and test the pipeline against generators it was not built on. I will NOT make synthetic data pass as real: it keeps its badge ("synthetic, realism-calibrated"). Real validation is the live study with the teammates (n = 4) and, if the owner is willing, a short pilot on the sandbox sites by the owner (n = 1, labelled).

**Persona generator v2** (`understudy_engine/personas_v2/`, new): person-level random effects (speed, carefulness, caution), lognormal dwell times with heavy-tailed hesitation pauses, power-law practice curves within and across sessions, fatigue, Poisson interruptions with task resumption cost, strategy mixtures over several valid paths (not one script), error bursts, mis-click and double-fire noise, dropped and jittered events, and between-role differences. Timing ranges are checked against published regularities (keystroke-level model operator times, Fitts' law for pointing, power law of practice, lognormal task times), reported as "within published ranges", never as "matches real users".
**Several structurally different generator families** (domain randomisation) plus a **generator-mismatch evaluation**: train the analytics on family A, test on B and C, and on the language-model participants' traces from the simulated study (which no generator wrote). Report how much each result degrades. The analytics' numbers (stuck model, genome recovery, routines) are re-run on v2 data with n well above 4 (target 40 or more people per role) and compared with v1.

## 3. STU: simulated study across roles

Extend `evals/study_sim` ideas to the programmer and data-analyst roles, labelled everywhere "simulated participants (language model), not people".
- **Programmer sandbox** (browser, our own site): a small editor, file tree, run-tests and console, with at least 6 tasks across 3 skills (off-by-one and boundary errors, null and missing-value handling, test-before-fix discipline) plus commit-hygiene habits via a simulated git panel; variants so post-tests are not memorised.
- **Data-analyst sandbox** (browser, our own site): a CSV table, filter, pivot and chart workbench with planted data issues (duplicates, unit mismatch, outliers, join-key mismatch, a total that does not reconcile), at least 6 tasks across 3 skills (sanity check before trusting a total is the analogue of the cliff check).
- Oracles score outcomes in code; cog mappings and packs are extended (8 to 10 cogs each); the design mirrors the benefits study (coach versus no coach, skill blocks, pre and post, held-out variants), pre-registered in a `PLAN.md` committed before the first model-driven run; same cost ledger and budget guard; prompt-sensitivity check (a weaker "novice" prompt versus the default).
- Later arm: **Cue versus no Cue** over several simulated sessions to measure stuck time saved and the independence trajectory (section 5).

## 4. CUE: the stuck-rescue feature (the "prompter in the wings")

The story: an understudy knows everyone's lines. When the actor goes blank, the prompter whispers the next line, and over time stops needing to. Cue does that for work: it notices you are stuck, finds the most likely next step from what experts do and what is on your screen, guides you least-intrusively, asks one clear question when it is unsure, teaches the reason, and then fades.

**Pipeline (all decisions in code; models propose).**
1. **State.** On-device signals (input rhythm, cursor dwell, app kind, hashed browser events), the latest glance (enums, every ~30 s when the worker opted in), the stuck probability from the hazard model, and where the worker is on the expert path.
2. **Candidates (the ML layer).** From the expert transition graph (`genome/graph.py`) and the pack's required-order rules: the top 3 next steps given the last k cogs, with probabilities. This is a path prior, not a guess by a language model.
3. **Grounding (Gemini or DOM).** In a browser, ground from the DOM first (exact, free, instant; `apps/desktop/src/main/dom-ground`). Elsewhere, take a fresh frame at decision time and ask Gemini flash-lite, escalating to flash: given the frame and the candidate menu (ids and pack labels, no free text), return a closed answer `{available: [ids on screen], chosen: id, box_2d?, confidence}`. A box is accepted only if it passes sanity checks (size, on-screen, not over a denylisted region).
4. **Decision (pure code).** Inputs: stuck probability, top-1 probability and margin over the runner-up, grounding confidence, skill mastery, cooldowns, the daily attention budget, flow state (never during a typing burst; wait for 2 s of quiet), consent. Outcomes: `none` (the default), `confirm` (silent, only if asked), `cue` at a tier, `ask`, or `offer` (a small "want a hand?" chip, only after a long stall).
5. **Ask (one multiple-choice question).** When the top two candidates are within the margin or the screen is unclear: a compact card, 2 to 4 options drawn from the candidate steps' pack labels plus "something else". Answer by click, by key 1 to 4, or by voice ("the second one"). One question per stuck episode, never open-ended by default. The answer is a strong label for intent and feeds mastery and the path prior. "Something else" opens a voice conversation only when the worker chooses it (Live, opt-in).
6. **Guide, least-intrusive adequate, escalate only if still stuck, de-escalate on progress.** Tier 1: a ring on the target (REQ-4 look). Tier 2: ring plus one chip, 40 characters or fewer. Tier 3: add the ghost-cursor demonstration of the expert's move (on request or on the second stall). Tier 4: voice whisper, 8 words or fewer (ElevenLabs cached lines for pack steps; Gemini Live for conversation). The help level per skill (L1 to L4 from the level engine) sets the starting tier: at L4 Cue stays silent and only answers when asked; at L1 it narrates.
7. **Walk-through.** Verify each step by a progress event or the next glance, then advance; stop guiding the moment the worker moves on independently.
8. **Teach and fade.** After the step: the "why" in 12 words or fewer, once, with "Why this?" always one tap away. Mastery (knowledge tracing with forgetting) schedules retrieval practice: the next time the situation occurs, Cue withholds help and only confirms afterwards. Cues visibly get lighter as mastery rises.
9. **Log and score** (section 5).

**Anti-spam rules (hard caps, plus tuning).** At most 3 cues in 10 minutes, at most 1 question per episode, at least 90 s between cues for the same skill unless asked, never in a denylisted app, never over secure input, "I know this" dismissal counts as mastery evidence only if the step then completes correctly, quiet-for-1-hour hotkey, no persistent on-screen chip. The tier policy is a bandit with logged propensities and implicit labels (followed within 10 s, dismissed within 4 s, Pupil idea); change it only after off-policy evaluation. Targets (design choices, not measured tolerances): false nudges at most 1 per hour, median time to progress after a cue measurably below the no-cue baseline on simulated users.
**Latency.** A speculative next-step guess is refreshed on every glance, so when the decision fires the cue appears in under about 300 ms; the on-demand frame is only for confirming.
**Privacy.** Frames follow the screen-frame rule in `CLAUDE.md` (never stored, ledger, opt-in, denylist, never unattended).
**Overnight automations are unrelated.** They run for experts and novices alike, never appear in assist counts and never change the independence score.

## 5. GRO: assist ledger and independence score

**Assist ledger** (`understudy_engine/cue/ledger`): append-only, local, worker-owned (view, export, delete). One row per assist episode, enums and numbers only: id, time bucket, role, skill id, trigger (auto, asked), stuck bucket, tier reached, options shown, answer id, accepted or dismissed, seconds to progress, outcome (clean, assisted, error, abandoned), level before and after. No text, no screenshots. A summary line is also written into the worker's memory file.
**Streams are separate:** `assist` (during work), `delegated` (the worker asked the agent to do it now), `automation` (overnight or background). Only `assist` and the skill-occurrence stream feed the score; delegated and automation runs are shown as "offloaded work" and never move it.
**Independence score (self-sufficiency index), per skill and overall, deterministic and shown with components.**
- Unit: a skill occurrence (the worker needed that step in real work, observed by its cog).
- Independence: share completed with no accepted cue over a sliding window of 20 occurrences, reported with the Wilson lower bound.
- Help-need trend: Theil-Sen slope of the assisted share over windows with a bootstrap interval.
- Gap closure: seconds lost versus the expert (genome price) now versus the first 5 occurrences.
- Retention: unaided success on the first occurrence 3 or more days after being taught; mastery from the tracing model with decay.
- Composite 0 to 100: 0.4 independence lower bound + 0.3 decay-adjusted mastery + 0.2 gap closure + 0.1 retention. The weights are stated assumptions; the headline is the trend with n and an interval, never the composite alone.
- Guards: dismissing a cue without completing the step is not independence; an error is penalised; a step that did not occur is not counted.
- Claim: "needs less help", never "became an expert". Validated on simulated learners with planted learning curves (bias, interval coverage, false-rise rate), labelled simulated.
**Growth screen ("Curtain")** on the dashboard: the independence curve per skill with intervals and n, the help level over time, assisted versus unaided occurrences, time-to-progress after cues, retention, the offloaded-work list, and delete and export controls.

## 6. Tracks and file ownership

| Track | Owns | Notes |
|---|---|---|
| AGENTIC (agent-core, resumed) | `services/agent/understudy_agent/{tiers,orchestrator,navigator,supervisor,sandbox_sites}`, `evals/agentic/**`, fact handles | needs MODELS for the Gemini actuator experiment |
| REALISM (new) | `services/engine/understudy_engine/personas_v2/**`, `services/engine/tests/personas_v2/**` | ML-V2 consumes it for the generator-mismatch test |
| STUDY-ROLES (new) | `services/agent/understudy_agent/sandbox_roles/**` (new), `evals/study_roles/**`, role packs extensions in `packages/packs/{programmer,data_analyst}` | private port worlds, never the shared sites |
| CUE-ENGINE (new) | `services/engine/understudy_engine/cue/**`, `services/engine/tests/cue/**` | ledger, score, candidates, decision, question builder, evaluation |
| CUE-UX (new) | `apps/desktop/src/renderer/cue/**`, `apps/desktop/src/main/cue/**` | question card, tiers, ghost run, voice hooks; overlay primitives come from DESKTOP |
| GROWTH dashboard (new, after the CUE contract) | `apps/dashboard/src/screens/Growth*` | on fixtures first |

## 7. Honesty

No claim that the score measures expertise or that Cue works on real people. Every Cue and score number is simulated or synthetic until the live study says otherwise, with n and an interval. Data realism is a robustness test, not a substitute for people.
