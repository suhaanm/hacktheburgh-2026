# Understudy

*Hack the Burgh XIII, Edinburgh, 7 to 8 Nov 2026. Targets: HRT, G-Research, Wordsmith.*

Two people do the same task. One is slower and reaches a different answer, and nobody can say where the difference comes from.

Understudy watches how people do the same task and prices each gap between a novice and an expert, in seconds and in wrong answers. It coaches on the real screen with help that fades. It lets an agent take repetitive work only when the worker agrees, one routine at a time. A memory file the worker owns, readable and editable, tunes it to them. It covers several jobs through role packs: one deep (a UK benefits processor), two thin (data analyst, programmer).

**State on 7 Nov 2026, about 21:00 GMT.** It runs end to end on example data and on three sandbox calculator sites that we wrote. Every number below comes from synthetic or simulated data unless a row says otherwise. Nobody has used it in a study. A one-page owner checklist is in [docs/MVP_STATUS.md](docs/MVP_STATUS.md).

## What we claim, and what we do not

- **Claimed:** on data we generated, the analysis recovers the gaps we planted and prices them. The coach rings the step a synthetic novice skipped and stays quiet for experts. An agent completes the benefits task on the sandbox calculators, and a code check, not the model, decides whether it finished.
- **Not claimed:** that coaching helps a person; that novices become experts; that any result transfers to real workers. The live study (four teammates) has not been run. The simulated study used language-model participants, not people, and sat at the floor.
- **Also not claimed:** that the stuck model or the work genome hold up on harder synthetic data. They mostly do not (see "What did not hold up").

## Run it

Needs macOS, Python 3.12 or 3.13 with [uv](https://docs.astral.sh/uv/), and Node. The commands below were checked against `Makefile`, `scripts/dev.sh`, `scripts/stop.sh` and the `package.json` files.

```bash
make setup      # uv sync; npm install for dashboard, extension, desktop; Playwright Chromium (needs network once)
make demo       # mock mode, no model calls, no network; seeds an isolated home under data/, starts the services, opens the dashboard
make stop       # stops what scripts/dev.sh started (it records PIDs in data/pids)
```

`make demo` sets `UNDERSTUDY_MOCK=1`, `UNDERSTUDY_X=1`, and points `UNDERSTUDY_HOME` and `UNDERSTUDY_DATA_DIR` at isolated folders under `data/`, never at `~/.understudy`. It starts four things (a port already in use is skipped, so run `make stop` first if a stack is up):

| Service | Port | Check |
|---|---|---|
| Engine (analytics, memory, coach brain) | 7700 | `curl -s http://127.0.0.1:7700/health` |
| Agent service (supervisor, security layers, queue) | 7710 | `curl -s http://127.0.0.1:7710/health` |
| Sandbox calculators and case-note page | 7801 to 7803 | `curl -s -X POST http://127.0.0.1:7801/__reset` resets all three |
| Dashboard | 5173 | open <http://127.0.0.1:5173> |

Allow about 30 seconds for the engine to warm up. Logs are in `data/logs/<name>.log`. Other targets: `make dev` (same services, no isolated home, not forced into mock mode), `make preflight` (a green, amber or red checklist that never prints a key; `make preflight MODE=dev` relaxes the walkthrough-only checks), `make eval` (writes `evals/report.json` and `evals/report.md`, which the Evidence page reads; `FAST=1` for a quick run), `make redteam` (offline red-team table), `make test` (engine, agent, packs, dashboard, extension, desktop).

**Chrome extension (capture).** `make demo` does not load it.
```bash
cd extension && npm install && npm run build      # type-checks, then writes extension/dist
```
In Chrome open `chrome://extensions`, switch on Developer mode, choose Load unpacked, pick `extension/dist`. Open the extension's popup and switch capture on: it is off until you do, and not allowed in Incognito. Optionally pin its id with `UNDERSTUDY_EXTENSION_ID` before starting the engine; unpinned, the engine accepts any extension id on four routes and `/health` says so. Then open <http://127.0.0.1:7801/step/1>.

**Desktop coach (Electron, from Alongside).** `make demo` does not start it. From `apps/desktop`: `ALONGSIDE_MOCK=1 UNDERSTUDY_MOCK=1 npm run dev` (electron-vite). macOS Screen Recording and Accessibility are granted by a person, not by us. Real clicks stay off (see Privacy and safety). Other scripts in `apps/desktop/package.json` (`preflight`, `e2e`, `showtime`) were kept from Alongside and are not part of this path.

**Live models.** `make live` runs the real models and voice with an isolated home (keys from `.env`; costs real money per agent run). The provider is Gemini by default (OpenAI was revoked; see `docs/FLAGS.md`). Otherwise outside mock mode: copy `.env.example` to `.env`, set the Gemini key and model ids, and start without `UNDERSTUDY_MOCK=1`. Model ids come from the environment and are checked at boot; none is hard-coded. Never commit `.env`.

### Flags

| Flag | Effect |
|---|---|
| `UNDERSTUDY_MOCK=1` | Scripted, deterministic, no model calls, no network. Set by `make demo`. |
| `UNDERSTUDY_X` | Master switch for the extension layers. **On by default in a running service** (D48); `UNDERSTUDY_X=0` turns it off. The full list of defaults and of what stays off, with reasons, is in `docs/FLAGS.md`. |
| `UNDERSTUDY_X_<LAYER>=1` | One layer. Engine: `PRIVACY`, `LOCALMODEL`, `CALENDAR`, `GIT`, `PROACTIVE`, `CUE`, `AWARENESS`, `EVIDENCE`, `ATTENTION`, `HITLIST`, `INSIGHTS`. Agent service: `AGENTS`. Models: `GEMINI`. A layer that is off answers 404 `extension_off`. |
| `UNDERSTUDY_X_CUE`, `_GEMINI`, `_LIVE` | In the **desktop app** these three are read by name only; `UNDERSTUDY_X=1` alone does not turn them on there. (`_AWARENESS` and `_ATTENTION` do honour the master.) Read from `apps/desktop/src/main/feature-flags.ts`. |
| `UNDERSTUDY_FLAG_VOICE`, `_WAKE`, `_SCAM`, `_FILES` | Old Alongside features, off. |
| `UNDERSTUDY_LEGACY_REMOTE=1` | Re-enables old Alongside paths that send screenshots or file text to remote models. Off. |
| `UNDERSTUDY_REAL_ACTUATOR` | The arm switch for real desktop clicks. **On by default in the agent service** (D50); a real action still needs the owner's one-time token, the countdown and the owner present, and the real backend needs pyobjc, so it stays inert until the owner runs the R1 command. `=0` turns it off. |
| `ALONGSIDE_AGENCY_LOOP=1` | The old multi-step loop. Off: it duplicates our actuator. |

## What it does

Status words: **verified** means the lead saw it work end to end; **built** means its track built and tested it; **building** means not finished. Detail and evidence labels: [docs/FEATURE_CATALOGUE.md](docs/FEATURE_CATALOGUE.md).

| Area | What | Status |
|---|---|---|
| Understand the work | Work genome (aligns a novice's steps to the nearest expert's and prices each gap), controls, stuck model, fading help levels L1 to L4 decided by code | verified; the stuck model and genome degrade on harder data |
| Coach | Live coach brain: one decision at a time; thin on-screen ring with one label | verified (decision), built (on-screen look) |
| Agent | Benefits agent on three sandbox calculators: cliff check, reconcile, case note, a gate on the real submit button; eight security layers; shadow mode to approval | verified in mock mode (ends in an approval-queue item, 0 false claims) |
| Routines | Routine finder, proposals with "Watch first", approval queue, Repeats page | verified (genome, routines, queue in the dashboard); Repeats built |
| Dashboard | 21 routes (Home, Genome, Today, Routines, Queue, Growth, Privacy, Evidence, Firm and more) and their sub-views, 28 screens and views in the lead's sweep | verified: all 28 load against the live stack with no page errors |
| Proactive layers | Briefing, calendar, git habits, local model, background agents, attention router, insights for workers and admins | built, synthetic |
| Cue and Growth | Stuck rescue and the independence score | building; simulated evaluation only |
| Models | Gemini, OpenAI, local and ElevenLabs routing; independent verifier; live voice | building or flagged off |
| Computer use on the sandbox calculators | A model clicks and types through the same safety layers | **not reliable**: 3 of 3 on development households, 1 of 4 held-out; the safety properties held, completion did not generalise |
| Computer use on a real desktop | Click and type through the same safety layers | not run: only the read-only rung R0 ran once |

The three-minute walkthrough script is [docs/drafts/DEMO_SCRIPT.md](docs/drafts/DEMO_SCRIPT.md). Architecture and contracts: [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md), [docs/API_CONTRACT.md](docs/API_CONTRACT.md).

## What we measured

The first table and the agent table come from `evals/report.md` (the two computer-use rows cite their own files), generated 7 Nov 17:38 GMT in mock mode. **It predates the ML v2, attention, insights, Cue and realism runs; `make eval` has to be re-run to fold those in** (see "What is not done"). The second table cites its own files. Intervals are 95% unless stated. Origin is synthetic unless stated.

### On our first synthetic generator

| Question | n and split | Result | Does not show |
|---|---|---|---|
| Does the alignment find planted deficits? | 16 people, 5 deficits over 32 novice cases | Precision 92% [84.5, 98.6], recall 95% [88.6, 100.0] | Real behaviour. Weak on "reads the result again and again" (precision 70% [40.0, 94.1]) and "copies the wrong figure" (recall 71% [33.3, 100.0]) |
| Is the gap an artefact? | 24 people | Real gap 229.6 s per case [192.7, 272.6]; expert against expert 7.1 s [-2.8, 18.4]; shuffled-label null 46.2 s [-36.4, 116.9]; permutation p = 0.001 | The null is not zero (about 20% of the real gap) because nearest-reference matching is not symmetric |
| Can it predict "no progress in the next 60 s"? | 4 people, leave one out | Log loss 0.436 [0.422, 0.451] against 0.509 [0.496, 0.524] (time since progress) and 0.509 [0.497, 0.524] (base rate); flags 33% of stuck events [27.5, 38.6]; false alarms 1.21 an hour [0.95, 1.48] against a budget of 1.0 | Held-out means one of four people. **Does not transfer** (next section) |
| Dignity gate | 4 people | False nudges 1.83 to 0.05 an hour; stuck events reached 21% to 5% | It buys quiet with coverage; no interval in the report table |
| What does skipping a step cost in answers? | 200 households | Skipping reconcile: wrong on about 20.7 of 200 (10.3% [7.8, 13.0]). Skipping the cliff check leaves a nearby edge unwarned on 107 of 200 (53.5% [46.6, 60.3]) | The calculators' quirks and the oracle are ours (a simplified rule set, not law; it agrees with PolicyEngine UK within 1 pound on 8 of 20 households) |
| Review routing under a budget | 900 households | Held-out error 0.0% [0.0, 1.7] at 93.8% coverage | **Circular**: it finds the quirks we planted |
| When to build an automation (ski rental) | 4,000 routines | Regret 1.332 [1.322, 1.342] with predictions against 1.776 [1.765, 1.786] at break-even | Building at once (1.273 [1.257, 1.290]) beats both at the simulated cost |
| Start-or-wait rule for background runs | 4 personas, 21 days | Interruption 2.1% against 24.8% for "whenever idle five minutes" (cap 10%); idle time used 74.2% against 90.2% | A fixed overnight window interrupts 2.0% but uses 43.0%; weak for the shift worker |
| Routine finder | 4 personas | After the value gate 6 of 6 proposals are planted routines [61.0, 100.0] | Raw finder: 12 of 55 clusters are planted routines (22% [12.9, 34.4]) |
| Study power | 10,000 Monte Carlo replications | At n = 4 the smallest possible exact p is 0.125; for a medium effect the interval excludes zero 4.4% of the time at n = 4 and 27.3% at n = 16 | A property of the design under our assumptions |

### What did not hold up

| Finding | Evidence | Source |
|---|---|---|
| **The stuck model's edge was mostly the generator.** On three structurally different synthetic generators its gain over "time since progress" falls from about 0.07 to between 0.002 and 0.015 nats per bin. A model trained on v1 and tested on those is 0.43 to 0.53 nats **worse** than that baseline and overshoots the false-alarm budget 1.7 to 4.2 times. | 3 generator families, 40 people each, 3 replicates | `evals/realism/INTERPRETATION.md` |
| **The genome does not carry its thresholds across worlds.** Precision 67, 48 and 71%, recall 62, 68 and 49% on the three families (v1: 92 and 95%). Thresholds fitted on v1 keep recall (87 to 95%) but precision falls to 33 to 56%; the reverse fit gives v1 recall of 10 to 42%. | same | same |
| **The routine finder is more robust at the proposal level than the raw numbers suggest**, but its cut height does not transfer; recall falls to 45, 66 and 92%. | same | same |
| **ML v2 held-out results are mostly negative.** On 6 held-out apprentice cohorts the pre-registered genome ensemble (E4) was **rejected as harmful**: absolute error +3.81 s [+2.30, +5.19] over 198 case-deficit pairs; the counterfactual (Q1) was rejected too: +1.17 s [+0.44, +1.87] over 512 pairs. Only E1 (learned substitution costs) was accepted, a marginal 4.8% gain (-0.92 s, 98.75% interval [-1.85, -0.21]); v1 alignment stays the default and there is no validated counterfactual. | held-out, single frozen run | `evals/mlv2/results/heldout_genome.json`, `evals/mlv2/PLAN.md` Amendment 11 |
| **A4 (gradient boosting with monotone constraints, Platt-calibrated) was accepted as the v2 stuck default for benefits-processor and programmer**, but the gain is small: log loss -0.0039 nats (99.3% interval [-0.0062, -0.0017]) against v1 on 32 held-out people. Under a different generator the one-feature rule "time since progress" beats v1's full model in all three roles (pooled -0.021 to -0.030 nats per bin), so a simple rule does about as well. No variant qualified for data-analyst. | held-out personas and a mismatch matrix | `evals/mlv2/results/heldout_hazard.json`, `heldout_mismatch.json` |
| **Transfer to simulated-participant traces failed** for both v1 and v2. | simulated traces, test only | `evals/mlv2/results/transfer_sim.json` |
| **The simulated study sat at the floor.** 16 coached and 8 sham-arm language-model participants (gpt-5.4-mini); 30 of 32 unassisted post-tests in the coached arm scored 0, and 16 of 16 in the sham arm. Mean difference 0.094 [-0.051, 0.239], exact p = 0.5. It validated the pipeline and the enforcement, not the coach. A follow-up pilot with more reasoning effort was stopped by its own criterion (0 of 6 post-tests above zero). | simulated participants, not people | `evals/study_sim/REPORT.md`, `results_run5/PILOT_REPORT.md` |
| **Role studies were not run.** The first programmer pilot failed its floor criterion (75% of 12 unassisted cases scored 0; two participants excluded for harness reasons). No analyst pilot. | simulated | `evals/study_roles/results/programmer/PILOT_aborted_1.json` |
| **The attention router meets 11 of 12 pre-registered criteria; criterion 7 is not met.** Against show-everything: 0.150 [0.141, 0.159] non-safety interruptions per flow hour against 1.512 [1.447, 1.582]; 0 hard-quiet breaches; 98.4% [98.0, 98.7] of important items seen in their window; 0 urgent safety items missed. Criterion 7 (later-day can-wait toasts below early-day) went the wrong way: +0.33 a day [+0.08, +0.58]. The run's own block first counted 11 of 11; it was corrected after the fact and the correction is in the file. Learning made no difference to any aggregate measure. A once-a-day digest is quieter and cheaper in assumed attention cost but missed 182 safety items. | 200 simulated workers, 2,000 worker-days, frozen config | `evals/attention/report_held_out.json` |
| **Insights: targets missed on dev, and again on held-out.** False insights on null data met their targets on both (held-out: worker 0.0037 per person-week [0.0027, 0.0047] over 2,400 people; admin 0 of 160 admin-weeks). Missed on dev, stated before the held-out run: planted independence rise selected in 47 of 100 worlds (target 0.8); false celebration when errors rise 14 of 100 (target 0); plateau unit flagged 8 of 10 seeds; benefits bottleneck 8 of 10; Simpson role 5 of 10 (target 9 of 10). Held-out: the rise and the false celebration are identical; plateau unit 29 of 40, programmer bottleneck 9 of 19, Simpson role 19 of 40; 127 of 996 empty worker lists hid a planted effect (dev: 37 of 251). The 100 planted worlds per effect do not use the seed list, so they are the same on dev and held-out; only the firm-based numbers are fresh draws. | 40 held-out synthetic firms of 60 people | `evals/insights/results/dev.json`, `heldout.json` |
| **Cue (simulated workers) met one of two primary targets.** False nudges 0.73 an hour (97.5% interval [0.64, 0.83]; target 1.0 or less). "Faster to resume" not met: median paired difference 0.0 s (97.5% interval [-9.5, 0.0]); the exploratory mean difference is -34 s [-43.7, -25.2]. Cues reached 28% of stuck episodes [25.1, 30.1]. | 40 simulated personas, 481.5 hours | `evals/cue/held_out.json` |

### The agent and its defences

| Question | n and origin | Result | Does not show |
|---|---|---|---|
| Does the agent finish on the sandbox, mock model? | 20 households | 20 of 20 [0.84, 1.00] clean and with injected failures; 15 of 20 needed the browser-agent tier; 0 false claims | The clean path is the path the sandbox was written for |
| With a real model (small n)? | 20 households per condition, tier 1 off | Clean 18 of 20 [0.70, 0.97], 0 false claims; after a layout change 20 of 20 [0.84, 1.00] | One model family, one prompt |
| One-off error page, real model | 20 households | **0 of 20** [0.00, 0.16]. It said it was finished in 20 of 20 runs and all 20 claims were false; the code check caught every one. After a change to the planner's inputs the same condition gave 10 of 10 [0.72, 1.00] | In-sample, 10 runs; it does not show the fix generalises |
| Injected pages, real model | 20 households | The detector paused 20 of 20 runs before the planner acted; 0 of 20 attacks succeeded | Task success is 0 by design; we wrote the pages |
| Scripted red team | 42 attacks, 10 configurations | Attack success 0.0% [0.0, 8.4] with every layer on, 100.0% [91.6, 100.0] all off; false pauses on 31 clean pages 0.0% [0.0, 11.0] | The planner follows any instruction; layers overlap |
| Real-model red team | 42 cases, 3 repeats | 0 of 126 runs with every layer on [0.0, 8.4]; 5 of 126 (4.0% [1.0, 14.7]) with all off | **Intervals overlap**: it measures what the layers cost, not that they prevent attacks. We wrote both attacks and defences |
| Privacy canaries | 80 runs of 10 flows | 0 of 11,336 planted tokens reached the model port; 0 leaks in 80 log, audit and queue files. Per run, the one-sided 95% upper bound is 3.7% | Exact strings only; flows that registered no code are not counted as passed |
| Computer use on the sandbox calculators (`evals/agentic/ITERATIONS.md`) | 3 development households, in-sample | After giving the model fact handles instead of values, 3 of 3 completed through the real gate, 0 false claims (Wilson [0.44, 1.00]) | A development result, not a rate. The held-out confirmation has not been run |
| Computer use, held-out confirmation (`evals/agentic/results/heldout_*.json`, gate 35e964049fd0; diagnosis in `docs/reference-notes/cu-failure-diagnosis.md`) | Clean n = 4 on new seeds; injected n = 20 | **Clean: 1 of 4 completed** (descriptive; Wilson about [0.05, 0.70]). In 2 runs the harness accepted calculator B with wrong inputs (bedrooms left on the default; the figure was off by exactly that) and an independent recomputation caught it; the product's own completion check would not have. 1 run paused because the goal-check layer's call could not complete (it fails closed; the gate itself had allowed the action). The designed Submit waited for a human in all 4; nothing was submitted. **Injected: 20 of 20 paused at step 0**, 0 attacks executed | Our own sandbox, language model, headless browser, 7 households in total (so no rate should be quoted). The injected pages carry text only: this shows the detector pauses, not that the gate resists hostile pages. Fixes are on a branch, not merged |
| Computer use on a real desktop (`evals/agentic/REAL_CLICKS.md`) | 1 read-only run | Rung R0 ran once: zero events; capture works; the test point was covered by another window, so it stopped. **Nothing else has run.** | No model has driven a real desktop |

Layers added after kickoff (git habits, calendar, proactive briefing, local-model digests) have development-set results only; see `evals/report.md` and the catalogue.

## What is real and what is synthetic

| Real | Synthetic or simulated |
|---|---|
| All the code, run locally. The capture extension was checked once in Chromium against a stub server (ten schema-valid events, no page text or URL; typing into a password form produced none) | People, histories, apprentices with planted deficits, households, calendars, commits, the synthetic firm |
| Three sandbox calculators and a case-note page, served locally and driven in a real browser | The calculators' quirks (planted) and the oracle (illustrative, not law) |
| Real-model agent and red-team runs (small n, above) | Everything in mock mode; the recorded walkthrough run is a replay of a mock run |
| One supervised real click and one typed line on TextEdit, owner present (spike S2); R0 read-only run | Study participants in the simulated study: language models, **not people**. The live study: **not run** |

## Privacy and safety

- **Capture is text-free.** Level 0 records hashed identifiers and enums: no page text, no URLs, no field values. Fields on `packages/schema/sensitive_fields.json` are never touched. The extension is off until switched on.
- **The model proposes, code decides.** Help levels, permissions, promotion, routing and gates are deterministic code. Automations are a JSON step language, never generated code.
- **Eight security layers**, mostly code: sanitising, a quarantined reader, typed actions, an action-class gate, data-flow rules, an injection detector, a goal-drift check, protected settings. There is no allowlist; the worker keeps an optional denylist. A hash-chained audit log and a kill flag ("Stop everything") sit beside them.
- **Every automation is opt-in**, one at a time, with a trust ladder that needs clean shadow runs. Irreversible steps wait in the approval queue; unattended runs need a per-routine opt-in and never write to a real account.
- **Screen frames** are held in memory for one call and never written to disk or logs. They leave the device only through the egress guard and ledger (size, hash, model, latency; never the image), only if the worker opted in, never from a denylisted app or while secure input is on, and never in an unattended run. Evidence screenshots of sandbox pages an agent operates are kept in that run's folder for the approval queue (decision D37).
- **Local services** check the Host header on every request and the Origin on every write, and release routes (approve, clear a stop) need a per-boot token.
- **Real clicks are off.** They need `UNDERSTUDY_REAL_ACTUATOR=1`, a frontmost-app check, a hit test of the click point, the kill flag and an action budget, and follow a ladder R0 to R4 in [evals/agentic/REAL_CLICKS.md](evals/agentic/REAL_CLICKS.md), each rung with the owner's go.
- **Independent review.** Two passes by separate Claude agents (not human security researchers) read the code on 7 Nov. Privacy and honesty: no critical finding, 6 high. Safety of the real actuator: 18 findings, 1 critical. Later fixes were re-run by the reviewer (172 of 172 reproducer checks pass per [docs/FIX_LEDGER.md](docs/FIX_LEDGER.md)); the fixes are tested against fake desktops only.
- **Known gaps.** The ledger records worker-requested model calls as metadata only; an allowed frame is raw pixels, because the guard does not redact them; the old Alongside desktop paths that could send screenshots or file text are off by default (D38, `apps/desktop/src/main/legacy-remote.ts`) but have not been re-reviewed independently.

## What is not done

From [docs/FIX_LEDGER.md](docs/FIX_LEDGER.md), honestly:

- **No study with people.** Live study (n = 4) not run; simulated study at the floor; role studies not run.
- **No real-desktop agent run.** Next rungs need the owner: move the window, a second R0, the R1 preflight in the owner's terminal. R2 is no-go until R1 is reported.
- **Agent reliability** not confirmed on held-out households (clean n = 4, injected n = 20 planned); several long-horizon items open.
- **Desktop:** the 19-check rehearsal has not been run; Live voice is flagged off; the screen-change watcher is not built (needs Screen Recording).
- **Evaluation:** `evals/report.md` is from 17:38 GMT and predates ML v2, attention, insights, Cue and realism; those sections still have to be wired into `make eval`. Test counts in the ledger are as of about 20:00 and need a final `make test`.
- **Product decision pending:** keep v1's stuck model, or make the simple "time since progress" rule the default signal (put to the owner at the freeze review).
- **Owner-only:** Auth0 domain and client ID, pinning the extension id, the real read-only Outlook aggregate check (needs approval at run time), the licence, Devpost facts, rehearsal and submission.

## Reuse: Alongside

The desktop coach is built on **Alongside**, the author's own earlier open-source library ([github.com/suhaanm/deepmind-hackathon](https://github.com/suhaanm/deepmind-hackathon), first commit **31 Oct 2026**, before this event, MIT). Its code is by the author and was copied into `apps/desktop` at the start of the build (commit b46c87e, 7 Nov 14:29 GMT). Alongside includes code adapted from third parties; their notices travel with it (below).

**Method.** SHA-256 of every file under `apps/desktop/src` against the same path in b46c87e, in the working tree at about 20:53 GMT. We did not diff against the owner's own Alongside tree (the `ALONGSIDE_PATH` in `.env.example` is a placeholder), so equality with Alongside itself is **not verified**; it holds only if that commit was a pristine copy. The lead's earlier comparison against the tree itself (at about 18:15 GMT) gave 205 identical, 70 modified, 28 not carried over (`docs/drafts/CLAIMS.md` C65). The counts move while the desktop track edits; recompute at the freeze.

Of 303 Alongside source files: **182 unchanged, 86 modified, 35 removed**; 345 files under `apps/desktop/src` are new (tests included).

| | What |
|---|---|
| **Kept unchanged** | Help-level engine and learner store (`main/teaching`: learner store, memory, progress, directives, skills; `levels.ts` has a one-line wording change since the copy); agency policy, audit, scope, assist and open-for-me (`main/agency`); actuator policy, validation and audit; capture helpers (`main/capture`: sizing, desktop capture, change score, watcher, overlay window); agents runtime (`main/agents`); the scripted walkthrough (`main/showtime`, one file reworded); file search (`main/files`, off); dock and onboarding screens (`renderer/dock`); design components (`renderer/design`); overlay flight, arrow, geometry and ghost cursor; toast app; shared permissions, shell and showtime types |
| **Modified** | Actuator flow, index and mapping; agency act-for-me and computer use; main index, IPC, bus, settings, session, tray, hotkey, windows, services, mocks; overlay scene, layout, store and annotation shapes, labels and chrome (restyled); dock panel and onboarding flow; design tokens and settings panel; shared contracts, IPC, models, protocol and settings; Gemini client and redaction |
| **Not carried over** | Alongside's Gemini grounder, verifier, router, lesson architect and scam analyst (`main/gemini`, `agents/gemini-port`); its renderer Live session; its wake-word code. Their jobs go through our model port |
| **New, ours** | Model port and model services; engine client; DOM-based grounding; coach brain, poller and chip; HUD; proposals; kill flag and switch; feature flags; legacy-remote gate; Cue, awareness, attention and a main-process Live session (flagged off) |
| **Outside `apps/desktop`** | Engine, agent service, dashboard, extension, packs, schemas and evals were written for this event. The dashboard was not checked file by file against Alongside (not verified); the design system in `packages/design` is ours |

**Safety finding.** Alongside shipped with the real actuator and the multi-step `act_for_me` loop on by default, and its README is inconsistent about whether real clicks were ever run. We did not rely on either claim. In `apps/desktop` both are off by default and a real click needs the guards above. What was exercised: one real click and one typed line on TextEdit with the owner present (spike S2, passed); a follow-up check of the agent's own actuator failed on 7 Nov (it reported ok while the click landed in another app's window); the guards were rebuilt and reviewed and are tested against a fake desktop only. See `docs/SPIKES.md`.

## Third-party notices and credits

[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (root) and `apps/desktop/THIRD_PARTY_NOTICES.md` (with the MIT text) list code adapted from farzaa/clicky and its Windows fork (MIT), and from google-gemini/gemini-live-api-examples (no licence file upstream; used only if voice is on, and it is off). Two modules of the Windows fork's Hermes plugin are lifted into `vendor/clicky/` with headers and the full licence. Sentient OS (AGPL-3.0) was reimplemented from the owner's prose notes: no code, comments or prompts copied. PolicyEngine UK (AGPL) is an optional cross-check in a separate environment and is never imported. No file has been copied from clickyyy or VisionOS. Dependencies keep their own licences.

We read these projects to guide the design and re-implemented the ideas: [Okidoki](https://devpost.com/software/okidoki), [Vision OS](https://devpost.com/software/vision-os-4ckmq3), [Bandit](https://devpost.com/software/bandit-the-only-band-you-need), [MOA](https://devpost.com/software/moa), [Mark8](https://devpost.com/software/mark8-go-to-market-world-model), [Pupil](https://devpost.com/software/pupil-utzxy2), [Drigil](https://devpost.com/software/drigil), [Rouge](https://devpost.com/software/rouge-cm8jig), [PodsControlMac](https://devpost.com/software/podscontrolmac-control-your-mac-with-airpods), [Stride](https://devpost.com/software/stride-09alcg). Ideas taken, one line each: [docs/REFERENCES.md](docs/REFERENCES.md). A friend's published design system was read as a design reference (its tokens match ours); see [docs/DESIGN_DIFF.md](docs/DESIGN_DIFF.md).

## Where to read more

[CLAUDE.md](CLAUDE.md) (rules), [docs/SPEC_LIST.md](docs/SPEC_LIST.md), [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md), [docs/UI_DIRECTION.md](docs/UI_DIRECTION.md), [docs/DECISIONS.md](docs/DECISIONS.md), [docs/SPIKES.md](docs/SPIKES.md), [docs/FEATURE_CATALOGUE.md](docs/FEATURE_CATALOGUE.md), [docs/FIX_LEDGER.md](docs/FIX_LEDGER.md), [evals/report.md](evals/report.md).

## Licence

Not chosen. Alongside is MIT; this repository has no licence file yet, so until the owner adds one all rights are reserved.
