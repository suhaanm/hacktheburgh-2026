# References: the ten hackathon projects and other sources

## What to do with these

1. Run `scripts/clone-references.sh`. It makes **shallow, read-only local copies** of every repo below in `references/<slug>/` (gitignored) and writes `references/INDEX.md` with each repo's licence as reported by GitHub today.
2. For each project, read the README and the files listed under "Read first". Write `docs/reference-notes/<slug>.md` (under 300 words): what the project does well, which of our modules it informs, and what we will do differently. Do this before writing the module it informs.
3. **Never run, install, build or import code from `references/`.** It is untrusted. Read it only.
4. **Licence rule.** Only two of the ten can be copied (clickyyy and VisionOS, both MIT). Copy only the named files, into `vendor/`, with a header comment naming source, path and licence, and an entry in `THIRD_PARTY_NOTICES.md`. **For every other project, re-implement from the idea in your own words.** Do not paste or closely transcribe their code. Credit them in the README under "Inspired by". Do not contact their authors.
5. These are hackathon projects and several over-claim. Take their methods, not their claims.

## Where each project lands

Priority 1 is the base. Priority 2 is built next. Priority 3 is nice to have. Spec IDs are in [SPEC_LIST.md](SPEC_LIST.md).

| Project | Pri | What we take | Where it lands |
|---|---|---|---|
| Alongside (the owner's own) | 1 | Overlay, level engine, learner store, verifier, approval policy and audit, agents runtime, mock mode | COA-1 to 5, MEM-1, HND-8 |
| Mark8 | 1 | Event-sourced log, pure reducer, replay with idle gaps squeezed; baseline scoreboard beside every prediction | CAP-3, VIS-5, VIS-6 |
| Pupil | 1 | Implicit reaction labels (followed, dismissed, repeated, undone); code-decides gate; held-out evaluation culture | ANA-6, PR1, ANA-15 |
| Stride | 1 | Event-level false alarms per hour; nested leave-one-person-out with a false-alarm budget; limitations register | ANA-5, ANA-15, EVL-4 |
| Drigil | 2 | Fading ladder spec; dignity gate; teach-by-recording idea | COA-3, COA-4 |
| Rouge | 2 | Code-checked completion; sensitive-fields-as-data; scroll-proof annotation idea | AGT-4, CAP-4, COA-6 |
| VisionOS | 2 | Supervisor with generations, cancel and deadlines; freshness-gated cues | AGT-2, COA-6 |
| clickyyy (Okidoki's author) | 2 | Stuck-loop detector; destructive-label and sensitive-path helpers; shake detector | SEC-7, SEC-4, CAP-7 |
| Okidoki (idea only) | 2 | Record once, replay with preconditions; replay divergence as a feature | HND-3, HND-4 |
| MOA | 2 | Answer-key harness with a simulated human | ANA-15, EVL-1 |
| BandIt | 2 | Precedents become rules (three approved cases, ceiling, separate approval, versioned) | MEM-3 |
| PodsControlMac | 2 | Tag agent input and keep it out of the human trace; yield rules; asymmetric smoothing for fading | CAP-6, HND-5 |
| Pupil (gaze) and PodsControlMac (head pose) | 3 | Optional attention channels | later |

## The ten projects

Devpost URLs have tracking parameters removed. Licences are from the GitHub API on 7 Nov 2026.

### 1. Okidoki and clickyyy
- Devpost: https://devpost.com/software/okidoki
- Okidoki repo: https://github.com/jayamitkatariya/okidoki (returned **404** on 7 Nov 2026, so nothing to inspect)
- clickyyy repo (same author, link to Okidoki is inferred): https://github.com/jayamitkatariya/clickyyy , **MIT**
- Licence: clickyyy MIT, copy allowed with notice. Okidoki unknown.
- Read first: `src/main/agent-loop.ts` (`isStuckLoop`, about line 1022, pure), `src/shared/command-safety.ts` (pure, 159 lines, no imports), `src/main/shake-detector.ts` (112 lines), `src/main/verify.ts` (overlaps Alongside; skip).
- Take: the stuck-loop detector, the destructive-label regex and sensitive-path helpers, the shake gesture as an "I'm stuck" label. Idea from the Devpost text: record a run once, replay it deterministically, call the model only when a precondition fails.
- Note: it began on 3 Jul 2026, before Cal Hacks. Fine for an MIT library; keep the notice.

### 2. Vision OS (VisionOS)
- Devpost: https://devpost.com/software/vision-os-4ckmq3
- Repo: https://github.com/yukevindai/VisionOS , **MIT** (its Core ML weights are AGPL-3.0; **do not take any weights**)
- Read first: `backend/r3_vision/orchestration.py` (Coordinator, TaskContext), `backend/r3_vision/audio_guidance.py` (freshness-gated decisions), `backend/r3_vision/agent_providers.py`.
- Take: the generation, cancel and deadline pattern for the supervisor. The Coordinator is tied to its own tools and a hard 5-second cap, so expect to rewrite the core.

### 3. Bandit, the only band you need (BandIt)
- Devpost: https://devpost.com/software/bandit-the-only-band-you-need
- Repo: https://github.com/viktorinkov/cal-hacks-13 , **no licence**
- Read first: `crates/bandit-insurance/src/rules.rs`, `decision.rs`, `pack.rs`; `crates/bandit-claims/src/scorecard.rs`.
- Take (idea only): the model proposes and a guard clamps to a human-approved ceiling; learned rules need three approved precedents and a separate approval, versioned; a scorecard that plants genuine and fake cases and reports precision, recall and cost.

### 4. MOA
- Devpost: https://devpost.com/software/moa
- Repo: https://github.com/petersenmatthew/moa , **no licence**
- Read first: `src/server/eval/harness.ts`, `src/server/sim/cases.ts`.
- Take (idea only): seeded cases with expected outcomes and a simulated human, with false-positive and recovery metrics. Add the leave-one-person-out split it lacks. Its perfect score is on author-written cases.

### 5. Mark8: go-to-market world model
- Devpost: https://devpost.com/software/mark8-go-to-market-world-model
- Repo: https://github.com/RoboX2020/Mark-Et-GTM , **no licence**
- Read first: `packages/core/src/events.ts`, `packages/core/src/fold.ts`, `apps/portal/src/lib/player.ts`, `apps/engine/src/bus.ts`, `apps/engine/src/sinks/index.ts`, `apps/engine/src/stages/backtest.ts`, `apps/engine/src/connectors/anonymize.ts`, `apps/engine/src/llm/router.ts`.
- Take (idea only): one typed event stream written to JSONL, a pure reducer, replay from 1x to 200x with idle gaps squeezed, a baseline scoreboard beside every prediction. Its headline claim is weak in its own recorded runs; copy the method, not the claim.

### 6. Pupil
- Devpost: https://devpost.com/software/pupil-utzxy2
- Repo: https://github.com/itsmarsss/pupil , **no licence** (its gaze weights are CC BY-NC-SA, non-commercial)
- Read first: `src/pupil/control/episodes.py`, `gate.py`, `evaluate.py`, `heat.py`, `tests/agent_cases*.jsonl`.
- Take (idea only): one episode per command with implicit labels (stopped within 4 s means corrected; the same request within 10 s means repeated; confirm and decline), the code-decides truth-table gate with answers logged and replayable, and a labelled held-out evaluation set. Gaze is optional and macOS-only.

### 7. Drigil
- Devpost: https://devpost.com/software/drigil
- Repo: https://github.com/shraddha11-408/CalHacks-13.0 , **no licence**
- Read first: `spacetime/spacetimedb/src/index.ts` (step outcome ladder, about lines 535 to 580), `edge/stepwise_edge/coach.py`, `edge/stepwise_edge/live_vision.py`, `droid/reteach.mjs`.
- Take (idea only): promote after 3 clean runs, demote on 2 or more errors in the last 5, assisted runs move nothing; the dignity gate (act after 2 consecutive mistake calls, cooldown, silent when unsure); a senior's recorded session becomes the step list. Its evaluation is 30 frames from one task.

### 8. Rouge
- Devpost: https://devpost.com/software/rouge-cm8jig
- Repo: https://github.com/RithikGobinath/rouge , **no licence** (its AGENTS.md says it grants none)
- Read first: `src/ai/agent.js` (`completionEvidence` and related), `src/pointing/track.js`, `src/pointing/sensitive.js`, `src/pointing/private-fields.json`, `src/computer/controller.js`.
- Take (idea only): code checks that the final observation contains the requested result before success is claimed; fields never to read kept as data; re-find the target control each frame so annotations survive a scroll. Windows UI Automation stack: skip.

### 9. PodsControlMac
- Devpost: https://devpost.com/software/podscontrolmac-control-your-mac-with-airpods
- Repo: https://github.com/sumionochi/PodsControlMac , **no licence**
- Read first: `HeadFlow/ScrollEngine.swift`, `ManualScrollMonitor.swift`, `TypingActivityMonitor.swift`, `PointerActivityMonitor.swift`, `MotionEngine.swift`.
- Take (idea only): stamp input the agent synthesises and filter it out of the human trace; ordered yield guards (pointer, typing, manual scroll) decide when automation backs off; fast attack and slow release smoothing as a model for fading help. Head pose from AirPods is an optional channel.

### 10. Stride (repo name walking-beat)
- Devpost: https://devpost.com/software/stride-09alcg
- Repo: https://github.com/dhruvbhavsar0612/walking-beat , **no licence**
- Read first: `research/fogdetect/metrics.py`, `research/evaluate.py`, `research/fogdetect/detector.py`, `research/fogdetect/calibration.py`, and its limitations docs.
- Take (idea only): event-level scoring (episodes detected within a window, false alarms per hour); nested leave-one-subject-out choosing thresholds per false-alarm budget; an honest limitations register as part of the pitch. Its Devpost text claims a Random Forest; the repo has logistic regression.

## Other sources

| Source | Licence | Use |
|---|---|---|
| Alongside, the owner's repo: https://github.com/suhaanm/deepmind-hackathon (the build laptop uses its **local copy** at `ALONGSIDE_PATH`) | MIT (owner's) with third-party notices inside | The base for the desktop app. Keep `THIRD_PARTY_NOTICES.md` and the `Adapted from` headers: they carry the notice for code adapted from farzaa/clicky (MIT) and Google's Gemini Live examples (no licence upstream) |
| farzaa/clicky: https://github.com/farzaa/clicky | MIT | Source of some Alongside overlay algorithms; notice already tracked |
| anthropics/knowledge-work-plugins: https://github.com/anthropics/knowledge-work-plugins | Apache-2.0 | **Later (D6).** Role plugins (sales, finance, data, operations, engineering, marketing, legal, customer-support, product-management, productivity, human-resources). Skills as expert procedures, MCP servers as tools. Keep the licence and notices if copying |
| OpenAdapt: https://github.com/OpenAdaptAI/OpenAdapt | MIT | Optional record, compile and replay. Its replay saves without asking: use only on sandbox pages |
| rrweb: https://github.com/rrweb-io/rrweb | MIT | Optional DOM session record and replay for the side-by-side view |
| Playwright MCP: https://github.com/microsoft/playwright-mcp | Apache-2.0 | Optional browser tool for tier 2 |
| Browser Use: https://github.com/browser-use/browser-use | MIT | Optional tier 2 agent |
| PolicyEngine UK: https://github.com/PolicyEngine/policyengine-uk | check the repo (related repos are AGPL-3.0) | Scoring oracle for the benefits pack, after spike S4 |

## Marketplace plugin mapping (for the later integration)

| Role | Plugin | Connectors named in the plugin |
|---|---|---|
| Data analyst | `data` | Snowflake, Databricks, BigQuery, Hex, Amplitude |
| Programmer | `engineering` | check the plugin |
| Sales and outreach | `sales`, `marketing` | HubSpot, Close, Clay, ZoomInfo, Outreach, Klaviyo and others |
| Accounting and audit | `finance` | Snowflake, Databricks, BigQuery |
| Processor, operations | `operations`, `productivity` | Asana, Atlassian, Notion, Slack |

The pack format reserves `plugin_refs`. The connectors need real accounts, so they are out of scope for the demo.
