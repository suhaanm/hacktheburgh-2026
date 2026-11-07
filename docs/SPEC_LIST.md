# Spec list

The full list of requirements for Understudy. Each row has an ID, a priority, the tracks it serves, and a one-line acceptance test. The how is in [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md).

**Priority.** P0 = the demo fails without it. P1 = should ship. P2 = stretch, cut first.
**Tracks.** H = HRT (predictions and decisions), G = G-Research (make the invisible visible), W = Wordsmith (complicated browser-use workflow).

## 0. Locked decisions

These come from the project owner. Do not reopen them. If one looks wrong, build it anyway and note the concern in `docs/DECISIONS.md`.

| # | Decision |
|---|---|
| D1 | Product: **Understudy**, generalised across job roles (data analysts, processors, programmers, sales, accounting, outreach, audit and others), with onboarding and adaptive customisation per role and per person. |
| D2 | Tracks to target: **HRT + G-Research + Wordsmith**. |
| D3 | Base code: the owner's **local copy of Alongside** (their own code, on the build laptop, path in `ALONGSIDE_PATH`). Keep the third-party notices that travel with it. |
| D4 | Role packs: **one deep** (UK benefits processor, validated) and **two thin** (data analyst, programmer: onboarding, customisation and a sample routine only). |
| D5 | Onboarding: **pick a role plus a short interview** (about five questions). Role packs give priors; the person's own traces take over. |
| D6 | Marketplace plugins (Apache-2.0, `anthropics/knowledge-work-plugins`): **design the pack format to accept them, integrate later**. |
| D7 | Handoff (automation of repetitive tasks): **the full slice is built early**, right after the thinnest base loop. |
| D8 | Off-hours (unattended) desktop runs: **a core feature**, not a stretch. |
| D9 | Graphs: the **work graph** (routines, skills, memory, automations) **and the genome graph** (expert versus novice cog transitions). |
| D10 | History for presence and routine models: **synthetic labelled persona and real machine timestamps** (times only, consent, on device). |
| D11 | Irreversible actions during unattended runs: **per-routine opt-in** by the worker. |
| D12 | **No allowlists.** The agent may go anywhere. The worker keeps an optional **denylist** of sites and apps. Anti-prompt-injection defences are mandatory. |
| D13 | Every detected automation is **opt-in**. |
| D14 | Models: the owner has an **OpenAI API key**. Use OpenAI as the primary provider. Gemini is optional if a key exists. Never hard-code model names. |
| D15 | Live study: **teammates only (n = 4)**. Report every result with its n and an interval. |
| D16 | The build is carried out **on one laptop** (one agent, subagents allowed). |
| D17 | Unlicensed reference repos: **re-implement from the idea only**. Do not copy their code. Do not contact their authors. |
| D18 | UI: **our own good-looking, uncluttered, standout interface**. See [UI_DIRECTION.md](UI_DIRECTION.md). |

## 1. Principles

| ID | Principle |
|---|---|
| PR1 | **The model proposes, code decides.** Levels, permissions, promotion, routing and gates are deterministic code. |
| PR2 | **Worker-owned, on-device.** Raw content never leaves the machine except to the model provider for a step the worker asked for. No employer view. |
| PR3 | **Opt-in everywhere.** Capture, each automation, unattended runs and memory writes. Revocable. |
| PR4 | **Honest evaluation.** Every number has a baseline, a split and an interval. Synthetic results are labelled synthetic. |
| PR5 | **Uncluttered UI.** One main idea per screen. Fewer elements, better made. |

## 2. Capture and event store (CAP)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| CAP-1 | P0 | G H | Chrome MV3 extension logs navigation, click target (role and hashed label), scroll depth bins, focus, tab switches, copy and paste flags, search events (hashed, length only) to the engine | A 5-minute browse yields a valid event file |
| CAP-2 | P0 | all | Event schema v1 with `origin` (`real` or `synthetic`) and `actor` (`human` or `agent`) | JSON Schema validates every event; invalid rows are rejected |
| CAP-3 | P0 | G | Append-only JSONL store, partitioned `real/` and `synthetic/`, with a pure reducer and replay (1x to 200x, idle gaps squeezed) | Replaying a file reproduces the same state twice |
| CAP-4 | P0 | PR2 | On-device redaction: no page text or field values stored; identifiers hashed with a per-install salt | Grep of a captured file finds no page text |
| CAP-5 | P1 | H | Idle, lock, sleep and resume events from Electron `powerMonitor` plus Alongside's screen-change score | Events appear when the screen locks and unlocks |
| CAP-6 | P0 | W | Agent actions run in a separate browser profile and never enter the human trace | Running an agent task adds zero `actor: human` events |
| CAP-7 | P2 | H | Hotkey or shake gesture creates a labelled `stuck` event | Pressing it writes one event |
| CAP-8 | P1 | H | Importer for real machine timestamps (git commits, timestamped shell history, browser visit times): times only, consent prompt, local | Importer output contains no URLs or text |
| CAP-9 | P0 | H G | Synthetic persona generator: 4 personas (nine-to-five, night owl, shift worker, irregular), 21 days, with a separate `truth.json` | Files exist, tagged synthetic, truth recoverable |

## 3. Analytics (ANA)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| ANA-1 | P0 | G | Cog mapper (about 15 base cogs plus role cogs) and episode segmentation | Unit tests on hand-made traces |
| ANA-2 | P0 | G | Work genome: Needleman-Wunsch alignment with a cog cost matrix, gaps priced in seconds, nearest-expert or consensus reference | Planted gaps recovered in tests |
| ANA-3 | P0 | G | Controls: shuffled-label null and expert-versus-expert placebo show near-zero gap | Both reported on the Evidence page |
| ANA-4 | P1 | G H | Gap decomposition (Oaxaca-Blinder) with cluster bootstrap by person | Waterfall with intervals |
| ANA-5 | P0 | H | Stuck hazard: discrete-time model, leave-one-person-out, log loss, Brier, calibration, versus a time-since-progress baseline | Calibration plot generated |
| ANA-6 | P1 | H | Intervention policy: rule baseline, contextual bandit with logged propensities, doubly robust off-policy estimate | Estimator recovers true value in the simulator |
| ANA-7 | P1 | H | Simulator with known ground truth for policy evaluation | Naive average is shown biased, DR is not |
| ANA-8 | P0 | H | Review routing: calibrated error probability, fixed expert-review budget, risk-coverage curve, bounded error on auto-approved cases | Curve plotted; bound holds on held-out cases |
| ANA-9 | P1 | H | Role-level priors with partial pooling for new people | Cold-start error lower than no pooling on held-out personas |
| ANA-10 | P0 | G W | Routine finder: cluster episodes by alignment distance; score count, time per run, variability, judgement content | Planted routines found with precision and recall reported |
| ANA-11 | P0 | H | Recurrence forecast, value model, and build timing by ski rental with predictions | Regret versus hindsight reported |
| ANA-12 | P0 | H G | Presence model: weekly 15-minute map with intervals; return-time hazard; window forecast | Calibration on held-out days |
| ANA-13 | P1 | H | Skill tracing with forgetting feeding the level engine | Mastery decays with absence |
| ANA-14 | P1 | H W | Agent trust calibration: predict "this success claim is false" from trace features | Calibration plot |
| ANA-15 | P0 | H | Eval harness: answer-key cases, false alarms per hour, limitations register | `make eval` runs end to end |

## 4. Coach (COA)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| COA-1 | P0 | W | Alongside overlay, help ladder, learner store and verifier running in the new app with a model port on OpenAI | Overlay draws a ring on a real element |
| COA-2 | P0 | W | DOM-first grounding for browser tasks (element rects from the extension); vision grounding only for desktop | Ring lands on the right button after scroll |
| COA-3 | P0 | H | Help ladder L1 to L4 with deterministic fading, decay and mastery, cross-checked against a simple spec (3 clean up, 2 errors in last 5 down, assisted neutral) | Tests agree on shared cases |
| COA-4 | P1 | H | Nudges offer a hypothesis or a question, not the answer; dignity gate (act after 2 consecutive signals, then a cooldown; silent when unsure) | False nudges per hour reported |
| COA-5 | P0 | W | Verification after each coached step (DOM check or fresh screenshot); success only when code confirms | A skipped step is not ticked |
| COA-6 | P2 | W | Annotations stamped with source frame and age, hidden when stale | Arrow hides after a scroll until re-resolved |

## 5. Roles and onboarding (ROL)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| ROL-1 | P0 | all | Role pack format (YAML plus schema), loader, validator | `understudy pack validate` passes the three packs |
| ROL-2 | P0 | H G W | Deep pack `benefits-processor`: tasks, cogs, risk classes, expert policy, persona parameters, eval cases | Used by the whole eval |
| ROL-3 | P1 | W | Thin packs `data-analyst` and `programmer`: cogs, risk classes, tone, onboarding questions, one sample routine, persona parameters | Onboarding differs visibly per role |
| ROL-4 | P0 | all | Onboarding flow: pick a role, about five questions, writes preferences, risk classes and a starting memory file | Two roles produce different memory files |
| ROL-5 | P2 | W | Pack format has `plugin_refs` (skills as procedures, MCP servers as tools); loader accepts them but does not call them | Schema accepts a sample reference |
| ROL-6 | P1 | H | Role priors feed partial pooling (ANA-9) | See ANA-9 |

## 6. Agent workflow (AGT)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| AGT-1 | P0 | W | Orchestrator, parallel navigators, verifier, critic, approval gate, scribe | Three navigators run in parallel on a case |
| AGT-2 | P0 | W | Supervisor with task generations, cancel tokens, deadlines, stale-result rejection | Stop wins within 1 second |
| AGT-3 | P0 | W | Three tiers: compiled script, browser agent, computer use; start cheapest, escalate on failed precondition | Tier used is logged per step |
| AGT-4 | P0 | W | Code-checked completion: the final page must contain the requested result | A false "done" is caught in tests |
| AGT-5 | P0 | W H | Benefits workflow on **local sandbox calculator sites**, optionally on public ones: synthetic household in, three calculators, reconcile, case note, stop before submit | End to end run passes on 20 households |
| AGT-6 | P0 | H | Scoring oracle: PolicyEngine UK model on the same households; hand-check about 20 cases | Disagreements listed |
| AGT-7 | P1 | W | Error recovery: alternate route, step cap about 20, escalation | Injected failures are survived |
| AGT-8 | P1 | W | Cached golden run for an offline demo | Demo runs with wifi off |
| AGT-9 | P1 | W | Parallel agent runs use separate browser contexts | No cross-talk in tests |

## 7. Handoff: automating repetitive work (HND)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| HND-1 | P0 | W G | Routine detection raises a **proposal card** (what, how often, hours saved with interval, what it touches, what it never does) | Card appears for a planted routine |
| HND-2 | P0 | W | Per-routine consent: not now, never, shadow mode, enable with approval; revocable; per-routine opt-in for irreversible classes (typed confirmation and warning banner for model-driven routines) | Revoke stops runs at once |
| HND-3 | P0 | W | Compile a recording into a parameterised script with preconditions and code-checked finish | Script replays on a new household |
| HND-4 | P0 | H W | Shadow mode and autonomy ladder A0 to A3 with Wilson lower bounds; demote on failure or undo | Promotion needs the stated bound |
| HND-5 | P0 | W | Background runs in a separate browser context; yield when the human touches input | Human input pauses the run within 1 second |
| HND-6 | P0 | W | Morning queue: batch approvals with evidence bundles | Approve or reject in one tap each |
| HND-7 | P1 | H | Proposal timing at natural breaks with a daily budget; learn acceptance per person | Proposals never fire mid-task in replay |
| HND-8 | P0 | W | Append-only audit log, redacted | Log lines carry no page text |

## 8. Memory (MEM)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| MEM-1 | P0 | all | One Markdown memory file owned by the worker (extend Alongside's learner store): preferences, procedure, routines, corrections, skill state, never list | File round-trips edits |
| MEM-2 | P0 | W | Writes only from the worker's own actions and approvals, never from page or tool text | Injection test cannot write memory |
| MEM-3 | P1 | H W | Three consistent corrections propose a personal rule; separate approval; versioned | Rule v2 appears after approval |
| MEM-4 | P1 | H | A personal procedure is adopted only if it matches expert-policy outcomes in shadow mode | Mismatching procedure is rejected |
| MEM-5 | P1 | PR2 | Decay, "forget that", export | Deleting a line removes it from behaviour |

## 9. Off-hours (OFF)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| OFF-1 | P0 | H G | Presence map and window forecast (ANA-12) | See ANA-12 |
| OFF-2 | P0 | W | Editable quiet-hours window; "run while I'm away" is a separate opt-in per routine | Disabled by default |
| OFF-3 | P0 | H | Start-or-wait rule: run only if P(window long enough) beats L / (G + L); checkpointed steps; yield at first input | Replay shows no start in short windows |
| OFF-4 | P0 | W | Desktop computer-use runner with the OpenAI computer tool and a macOS actuator. **First pass a real-click spike on a harmless app** | Spike passes on TextEdit or Calculator |
| OFF-5 | P0 | W | Refuse to start when the screen is locked or asleep; keep-awake while a run is active | Refusal reason is shown |
| OFF-6 | P0 | W | Global kill switch (hotkey and button), time budget, action budget | Kill stops within 1 second |
| OFF-7 | P1 | W | Morning report of what ran, what is queued, what failed | Report renders from the audit log |

## 10. Security (SEC)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| SEC-1 | P0 | W | Untrusted text is wrapped as data and cleaned (invisible characters removed, brackets neutralised) | Tests with hostile strings |
| SEC-2 | P0 | W | Quarantined reader: a model reads untrusted content and returns schema-checked fields only; the planner never sees raw text | Planner prompt contains no raw page text |
| SEC-3 | P0 | W | Typed one-step actions with validated arguments, fresh observation each step, step and time budgets | Invalid action is rejected |
| SEC-4 | P0 | W | Action-class gate: irreversible or outward-facing actions need a human click unless the worker opted that routine in (D11) | Gate blocks by default |
| SEC-5 | P0 | W | Data-flow rules: data from files, memory or logged-in pages cannot be typed or uploaded to a site the routine did not record without a queued approval | Exfiltration test fails safely |
| SEC-6 | P0 | W | Injection detector over page text, hidden elements, alt text and OCR; a hit pauses the run, logs it and lowers the autonomy rung | Red-team pages trigger it |
| SEC-7 | P1 | W | Goal-drift check on each proposed step; stuck-loop detector | Off-goal step pauses the run |
| SEC-8 | P0 | W | Protected settings: page content cannot change memory, denylist, consent, quiet hours or the kill switch; the agent cannot click them | Tests cover each setting |
| SEC-9 | P1 | W | Optional worker-editable denylist; optional starter list (password managers, system security settings) offered at opt-in | Denylisted site is never visited |
| SEC-10 | P0 | W | No allowlist anywhere | Grep finds no allowlist logic |
| SEC-11 | P0 | W | No stored credentials; demo uses sandbox sites and synthetic data | `.env` holds only the model key |
| SEC-12 | P0 | H W | Red-team suite with ablations: attack success rate and task success under attack, each layer off in turn, plus false-pause rate on clean pages | Table on the Evidence page |

## 11. Visuals and UI (VIS)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| VIS-1 | P0 | G | Genome ribbon (aligned expert and novice traces) and gap waterfall with intervals | Renders from synthetic and real traces |
| VIS-2 | P1 | G | Genome graph: cogs as nodes, transitions as edges, expert beside novice, missing edges highlighted | Highlighted edges match planted deficits |
| VIS-3 | P0 | G | Work graph: routines, skills, memory, automations; link, combine, fade; click a node to see why it exists, edit or delete it | Deleting a memory node edits the file |
| VIS-4 | P0 | G H | Presence heatmap (7 by 96) with intervals and idle-capacity hours | Matches planted schedules |
| VIS-5 | P1 | G | Side-by-side replay of two traces | Scrubber works |
| VIS-6 | P0 | H | Evidence page: calibration, risk-coverage, ski-rental regret, off-policy recovery, injection table, limitations register | One page, no clutter |
| VIS-7 | P0 | W | Proposal card, autonomy rung display and morning queue screens | Matches UI direction |
| VIS-8 | P0 | all | Onboarding screens | Two roles, under 60 seconds each |
| VIS-9 | P0 | PR5 | Follow [UI_DIRECTION.md](UI_DIRECTION.md): tokens, type, spacing, motion, light and dark | Visual QA pass at 1440 by 900 and 390 by 844 |

## 12. Evaluation (EVL)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| EVL-1 | P0 | H G | Synthetic apprentices with injected deficits; recovery of which deficit was injected, and its price | Precision and recall reported |
| EVL-2 | P1 | H | Live within-subject study with the four teammates, counterbalanced; **n = 4 stated on every chart** | Study file and results committed |
| EVL-3 | P1 | H | Analysis plan committed **before** the study runs | Commit timestamp precedes data |
| EVL-4 | P0 | H | Limitations register shown in the product | Lists thin data, synthetic origin, n = 4 |
| EVL-5 | P1 | H | Headline learning metric: unassisted performance on a later matched task | Reported separately from assisted speed |

## 13. Non-functional (NFR)

| ID | Pri | Requirement |
|---|---|---|
| NFR-1 | P0 | Demo runs on one macOS laptop with wifi off (mock mode plus cached golden run) |
| NFR-2 | P0 | `UNDERSTUDY_MOCK=1` gives a deterministic, model-free run of every demo path |
| NFR-3 | P0 | Model IDs come from environment variables and are checked at boot |
| NFR-4 | P0 | No secrets in git; `.env` is ignored |
| NFR-5 | P0 | Unit tests for every pure module; a smoke test per milestone |
| NFR-6 | P0 | `THIRD_PARTY_NOTICES.md` kept current; adapted files carry a header naming source and licence |
| NFR-7 | P0 | README discloses that Alongside is the author's earlier open-source library (first commit 31 Oct 2026) and lists what was reused |
| NFR-8 | P1 | First paint of the main screen under 2 seconds; no layout shift |
| NFR-9 | P1 | Accessible: keyboard focus, contrast, reduced motion respected |

## 14. Extensions requested after kickoff (REQ-2, 7 Nov 2026)

**Status: ACCEPTED (7 Nov).** The owner decided D24 (design-only reimplementation of Sentient OS), D25 (Qwen2.5-7B Q4_K_M local model), D26 (synthetic calendars plus one read-only aggregate-only real check) and D27 (all layers in parallel, flags turned on only after the lead verifies each end to end). Everything here is **off by default behind feature flags**, never touches the P0 demo path, runs deterministically in mock mode, and is evaluated on synthetic data with honest labels. Tracks: H = HRT, G = G-Research, W = Wordsmith. Source of ideas: Clicky (MIT, local copy), Sentient OS (AGPL-3.0, local copy; design only unless D24 says otherwise), the owner's request.

### 14.1 Privacy and egress (PRV)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| PRV-1 | P0 | H G | **Egress guard.** Every byte sent to a remote model from the new layers passes one function, `egress.send(purpose, payload)`. The payload is a typed `SafePayload` (numbers, booleans, enums, bucketed ranges, ids from fixed vocabularies; no free text from any source). Anything else raises. | Canary test: planted names, emails, meeting titles, file paths and commit messages in the sources never appear in any captured outbound request body, across every insight, briefing and digest flow |
| PRV-2 | P0 | H G | **Egress ledger.** Every outbound call is recorded locally (time, purpose, schema id, field names, the payload as sent) and shown on a Privacy screen; the worker can export or clear it. | One ledger line per call; the screen lists them; clear works |
| PRV-3 | P1 | H | **Generalisation.** Small counts become "fewer than 5", times round to 15 minutes, durations to 5 minutes, ratios to 10% steps, before they enter a payload. | Property tests on the bucketing |
| PRV-4 | P0 | H G | **Local raw data.** Raw calendar and git content stays under `data/` or the worker's home, never in logs, audit lines, queue items or payloads; only digests are retained; delete removes them. | Grep of logs, audit and queue after a run finds no source text |

### 14.2 Local model and digests (LOC)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| LOC-1 | P1 | H G | Local model provider over `llama-server` (llama.cpp, OpenAI-compatible endpoint on localhost), model path from the environment, JSON-schema constrained output, fail-closed to rules when no model is present. | Health check; 20 synthetic commits digested; works offline |
| LOC-2 | P1 | H G | **Digest pipeline.** The local model turns raw items (git diffs and messages, calendar entries) into schema-checked digests (categories from a fixed vocabulary, counts, durations); a no-verbatim-span check (n-gram overlap) and a PII regex backstop run on every digest; the frontier model only ever sees digests, through PRV-1. | Leak test on planted strings; digest accuracy against planted labels with intervals |
| LOC-3 | P2 | H | Fine-tuning: **not planned** (cannot be validated in the time; claims would be unsupported). Constrained decoding and few-shot prompts instead. | Stated in the limitations register |

### 14.3 Plugins and sources (PLG)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| PLG-1 | P0 | W | Source plugin interface and manifest (pattern from the Clicky Hermes plugin, MIT): id, kind, read-only permissions, egress class, schemas; loader and validator; `plugin_refs` covers sources as well as skills. | `understudy plugin validate` passes the bundled plugins |
| PLG-2 | P1 | G H | Adapters: git (local repos), ICS and JSON calendar (synthetic and a user export), Microsoft Graph Outlook and Teams (**off by default**, the worker's own sign-in, never exercised on a real account in tests, aggregate-only), shell-history times (CAP-8). | Each adapter validated on fixtures; Graph adapter unit-tested against recorded fake responses |
| PLG-3 | P2 | W | Two skills from the Apache-2.0 knowledge-work plugins (data, engineering) as child-agent playbooks, with notices. | Playbook loads and drives a child in mock mode |

### 14.4 Calendar routine layer (CAL)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| CAL-1 | P1 | G H | Weekly calendar features: meeting load, focus blocks, fragmentation, back-to-back runs, recurring series, work-hours span, off-computer blocks. | Recovers planted structure in synthetic calendars |
| CAL-2 | P1 | G | Expert routine templates per role pack and a week-level gap analysis, expert against learner (the "week ribbon"). | Planted gaps recovered; placebo near zero |
| CAL-3 | P1 | H G | **Generic suggestions.** Code picks from a fixed catalogue (protect a focus block, batch similar work, add a review slot, automate scheduling with an auto-hold, schedule an off-computer break or handoff, reduce back-to-back); the model may word them from safe aggregates only; each cites its numbers and the expert reference; opt-in. | Catalogue coverage test; canary test (PRV-1) |
| CAL-4 | P1 | H G | Synthetic calendars with planted structure and truth, for the personas and the experts. | Truth files exist; evaluation reports precision and recall |

### 14.5 Proactive intelligence (PRO)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| PRO-1 | P1 | H W | **Judge, verify, prepare, press to fire** (design from Sentient OS, reimplemented): at most 3 cards; each has editable prepared content, a risk class and source tags; firing creates an approval-queue item or a background agent run; nothing fires unprompted; stale cards are dropped when the situation changed. | Replay over personas: card count cap holds, no card fires, stale card dropped |
| PRO-2 | P1 | H | Morning briefing screen (and a spoken briefing behind the voice flag). | Renders from the seeded demo state |
| PRO-3 | P2 | H | Per-person acceptance learning from accepts and declines (reuse HND-7). | Acceptance rate recorded |

### 14.6 Background agents (BGA)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| BGA-1 | P1 | W | **Agent runtime.** A parent agent plans and spawns child agents from a typed `AgentSpec` (role, tool allowlist per child, budgets for steps, time and tokens, an isolated workspace, an output schema); supervisor generations and cancel; typed results checked by code; every step through the SafetyPipeline. (SEC-10 still holds: the tool list scopes a child's tools; it is not a site allowlist.) | Three children run in parallel; stop wins in 1 s; a child cannot write outside its workspace |
| BGA-2 | P1 | W | Foreground mode: children run while the worker keeps working, yield to input, and report at natural breaks. | Yield within 1 s |
| BGA-3 | P1 | W H | Nightly mode through the off-hours decision; the morning report lists children and outcomes. | Replay with a simulated clock |
| BGA-4 | P1 | W | Programming exemplar: commit analyst, test-gap finder and refactor suggester on a synthetic repo in an isolated worktree; patch drafts are never applied or pushed without approval. | Planted facts found; zero writes outside the worktree |
| BGA-5 | P1 | W | Data-analysis exemplar: profile and chart a sample CSV in a sandbox with no network; summary with numbers and a chart. | Planted facts found; budgets obeyed |
| BGA-6 | P2 | W | Creative exemplar: draft a weekly write-up from digests. | Draft cites digest ids only |

### 14.7 Git analysis (GIT) and reuse (CLK, SOS)

| ID | Pri | Trk | Requirement | Acceptance |
|---|---|---|---|---|
| GIT-1 | P1 | G H | Git analysis for the programmer role: commit events (times, sizes, test-touch, reverts, message class by local digest), programmer pack cogs, expert against learner on synthetic repos, suggestions through CAL-3's guard. | Planted habits recovered with precision and recall |
| CLK-1 | P1 | W | Clicky reuse study (MIT, local copy): a reuse map and, where a gap is filled, lifted modules with an `Adapted from` header and a notices entry (scoped autopilot session policy, post-action verification, confirmation state, plugin manifest). | `docs/reference-notes/clicky-reuse.md`; notices current |
| SOS-1 | P1 | H W | Sentient OS: **design-only** reimplementation unless the owner chooses a literal port under AGPL (D24). | Implementers' notes cite the owner's research notes, not the Swift source |

### 14.8 Non-functional additions

| ID | Pri | Requirement |
|---|---|---|
| NFR-10 | P0 | All section 14 features are off by default behind flags; the three-minute demo path and `make demo` are unaffected when they are off. |
| NFR-11 | P0 | Each feature ships with tests and an honest evaluation (n, split, interval, origin) and enters the limitations register. |

## 15. How owner requests are handled

Every new owner request or tweak gets a row in the **requests log** in `IDEA_BOARD.md` (`REQ-n`, date, request, analysis, status), new IDs in this file with a status (`PROPOSED`, `ACCEPTED`, `BUILDING`, `BUILT`, `CUT`), a decision number in `DECISIONS.md` where the owner chose something, and, if it changes ownership, an update to the roster in `AGENTS.md`. The lead does this before starting the work; locked decisions (section 0) are never reopened without an explicit owner instruction, and a conflict is recorded as a concern.
