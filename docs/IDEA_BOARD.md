# Idea board

A living board of every idea so far, by status. The build agent may add ideas at the bottom of a column and move cards between columns, but should not remove a card without a reason noted in `docs/DECISIONS.md`. Track tags: **H** HRT, **G** G-Research, **W** Wordsmith.

## Now: committed core (P0)

| Idea | Tracks | Why it is here | Spec |
|---|---|---|---|
| **Understudy engine**: capture, event store, replay | G H | Everything reads from one typed, replayable event stream | CAP-* |
| **Work genome**: aligned expert and novice traces, gap waterfall, null and placebo controls | G | The invisible policy made visible, with controls so it cannot be an artefact | ANA-1 to 3, VIS-1 |
| **Stuck hazard with baselines** | H | Calibrated prediction, held-out people, honest comparison | ANA-5 |
| **Review routing under a budget** | H | YC's "$15-an-hour expert" needs a licensed reviewer in the loop; the question is which cases go to them | ANA-8 |
| **Coach with fading help** (from Alongside) | W H | Deterministic ladder, overlay on the real screen, verification | COA-* |
| **Role packs and onboarding** | all | Generalises the product across job roles; one deep pack, two thin | ROL-* |
| **Agent workflow on sandbox calculators** | W | Parallel navigators, verifier, critic, approval gate, recovery | AGT-* |
| **Security layers and red-team ablation** | W H | Open web with no allowlist, so injection defence is measured | SEC-* |
| **Handoff**: routine finder, opt-in proposal cards, shadow mode, trust ladder, background runs, morning queue | W H G | "Coach what you have not mastered, automate what you have" | HND-* |
| **Memory file the worker owns** | all | Adaptive customisation that the worker can read, edit and delete | MEM-* |
| **Off-hours live run** with presence model and start-or-wait rule | H W G | Solves the one-cursor problem; the rule is a critical-fractile decision | OFF-*, ANA-12 |
| **Work graph and genome graph** | G | Link, combine and fade; expert versus novice transitions | VIS-2, VIS-3 |
| **Presence heatmap** | G H | A working rhythm the worker has never seen | VIS-4 |
| **Synthetic persona history plus real timestamps** | H | Lets every model run end to end with labelled truth | CAP-8, CAP-9 |
| **Evidence page and limitations register** | H | Honesty as a feature | VIS-6, EVL-4 |

## Next: build if the core is healthy (P1)

| Idea | Tracks | Notes |
|---|---|---|
| Gap decomposition (Oaxaca-Blinder) with cluster bootstrap | G H | Waterfall with intervals |
| Contextual bandit with doubly robust evaluation in a simulator | H | Fall back to rule plus expected-value table |
| Role-level priors and partial pooling for cold start | H | New person inherits the role's estimates, shrinks toward their own |
| Skill tracing with forgetting | H | Feeds the level engine |
| Agent-claim calibration | H W | Predict "this success claim is false" |
| Personal rules from three corrections | H W | Precedent to rule, versioned, separate approval |
| Preference versus procedure gate | H | Adapt style freely; adopt a method only if it matches expert outcomes |
| Dignity gate and hypothesis-style nudges | H | Fewer false nudges per hour |
| Side-by-side replay | G | Scrub two traces together |
| Cached golden run for an offline demo | W | Survives bad wifi |

## Cool to have (P2)

| Idea | Source of inspiration | Notes |
|---|---|---|
| Gaze channel: dwell on the error before the first edit | Pupil | macOS-only, weights non-commercial; rebuild the idea |
| Head-pose ribbon from AirPods | PodsControlMac | Swift, needs AirPods |
| Freshness-gated and scroll-proof annotations | VisionOS, Rouge | No stale arrows |
| "I'm stuck" shake or hotkey as ground-truth label | clickyyy, Stride | Zero-false-positive labels |
| "What did I miss?" recall with cited frame ids | VisionOS | For juniors after an error flood |
| Sandboxed re-teach agent with an independent validator | Drigil | Approval pattern |
| Leak-safe backtest harness (cutoff filter, anonymiser) | Mark8 | Only for a memorisation-test module |
| Replay-divergence map | Okidoki | Where a replayed expert run breaks on a novice's screen |
| Calibrated replay-or-model router | Okidoki | Choose tier by expected cost |
| Narrated coach nudges and a spoken morning briefing | ElevenLabs (MLH category) | Owner-approved 7 Nov (D19). Flag off by default; cached audio for the offline demo |
| DEV Writing Challenge post | MLH category | Owner-approved 7 Nov (D20). Lead drafts after the freeze |
| Auth0 sign-in (Google) plus step-up approval for irreversible actions | Auth0 (MLH category) | Approved thin version 7 Nov (D22). Optional adapter with a local fallback only; never on the demo's critical path; dashboard builds it after the core screens |

## Later: the marketplace addition (D6)

Role packs accept `plugin_refs`: skills from Apache-2.0 plugins as expert procedures, and MCP servers as tools. Candidate mapping is in [REFERENCES.md](REFERENCES.md). Out of scope for the demo because connectors need real accounts. What to try after the demo: turn a plugin's skill file into a lesson plan for the coach; add one connector (for example data or sales) to a thin pack.

## Parked alternatives (not building, kept for reference)

| Idea | Tracks | One line |
|---|---|---|
| **Forking Paths** | H G W | A research agent that counts its own failures: mass hypothesis search, a statistical court, a graveyard visual, judges bring a spurious correlation |
| **Grid Heartbeat** | H G | GB half-hourly imbalance price forecasting and battery dispatch; mains hum as a showpiece |
| **Burgh Exchange** | H | A live play-money prediction market with an automated market maker |
| **Memory Premium** | H G | Measure how much LLM forecasting skill is memory; crowded in research |
| **Timetable Lies** | H G | Calibrated bus arrivals and bunching waves; data coverage for Edinburgh unconfirmed |
| Fix-or-Float, Ombudsman Lottery, Paper Win, Entitlement Fuzzer and 20 more track ideas | various | In the Impact Atlas: https://claude.ai/artifact/LR82gq8RHhqZ99ZMik5s7X |

## Rejected

| Idea | Why |
|---|---|
| Allowlist for unattended runs | Owner decision: keep the agent free; denylist only |
| Calling the reference authors | Owner decision: re-implement only |
| Claiming novices perform like experts | Not supported by the evidence; the claim is "lifts novices" |
| Fine-tuning model weights per user | Out of scope; customisation is memory plus a few learned parameters |

## Decision log

| When | Decision | By |
|---|---|---|
| Sat 7 Nov | Understudy, generalised across roles, with onboarding and adaptive customisation | owner |
| Sat 7 Nov | Targets: HRT + G-Research + Wordsmith | owner |
| Sat 7 Nov | Base: the owner's local Alongside copy; all Alongside code is the owner's | owner |
| Sat 7 Nov | One deep pack plus two thin; pick-role onboarding; plugins later | owner |
| Sat 7 Nov | Handoff full slice first; off-hours live run core; work graph plus genome graph | owner |
| Sat 7 Nov | History: synthetic persona plus real machine timestamps; per-routine opt-in for irreversible actions | owner |
| Sat 7 Nov | Live study with teammates only; OpenAI key; one build laptop; re-implement unlicensed repos | owner |

## Open questions for the owner

- Which OpenAI model IDs does the key have, and does it include a computer-use model? (Spike S1.)
- Can the build laptop stay awake and unlocked for the off-hours demo, and is a second machine available?
- Which sites, if any, should be on the starter denylist?
- Does the owner want to ask an organiser about reusing Alongside, or just disclose it in the README?

## Owner requests log

Every request or tweak is logged here first (see SPEC_LIST section 15). Status: PROPOSED, ACCEPTED, BUILDING, BUILT, CUT.

| REQ | Date | Request (short) | Analysis and decision | Spec IDs | Status |
|---|---|---|---|---|---|
| REQ-1 | Sat 7 Nov | Simulate the study instead of running it with teammates | D23: Monte Carlo of the design plus simulated participants (language model), never presented as people | EVL-2 variants | BUILDING |
| REQ-2 | Sat 7 Nov | Study Clicky and Sentient OS (local copies) and lift modules; background agents (parent and child, during requests and overnight, programming, data analysis, creative, via plugins, learned from observation); proactive intelligence; Outlook and Teams plugins and a calendar routine layer with generic suggestions and no data leaks; git analysis and a local model for pre-processing | Analysis in `DECISIONS.md` (REQ-2). Clicky is MIT (lift with notices). Sentient OS is AGPL-3.0 Swift: design-only reimplementation recommended; literal port would make the whole repo AGPL-3.0. Local model feasible (llama.cpp installed, 32 GB). Pending D24 to D27. | PRV, LOC, PLG, CAL, PRO, BGA, GIT, CLK, SOS | ACCEPTED, BUILDING (D24 to D27) |
| REQ-3 | Sat 7 Nov | Update the spec, feature list and idea board for these and any future requests | Done: SPEC_LIST sections 14 and 15, IMPLEMENTATION_SPEC section 14, this log, `AGENTS.md` process | n/a | BUILT |

## Extensions (REQ-2) cards

| Idea | Tracks | Notes | Status |
|---|---|---|---|
| **Egress guard and ledger** | H G | One choke point for anything sent to a remote model; typed payloads only; a Privacy screen that shows exactly what left; canary tests | BUILDING |
| **Local digest model** (llama.cpp, Qwen2.5-7B Q4_K_M) | H G | Turns raw commits and calendar entries into enum and number digests on this Mac; the frontier model sees digests only; rules fallback; no fine-tuning | BUILDING |
| **Calendar routine layer and week ribbon** | G H | Expert against learner at the week level; generic suggestions from a fixed catalogue (focus blocks, batching, review slots, auto-hold, off-computer breaks) | BUILDING |
| **Outlook and Teams adapters** | G | Microsoft Graph, off by default, aggregate-only, fake responses in tests, never run on a real account without the owner's say | BUILDING |
| **Proactive intelligence** (judge, verify, prepare, press to fire; at most 3 cards) | H W | Design from Sentient OS reimplemented; morning briefing; nothing fires unprompted | BUILDING |
| **Parent and child background agents** | W | Typed specs, budgets, isolated workspaces, supervisor and safety pipeline; foreground and nightly modes; programming, data and creative exemplars | BUILDING |
| **Git analysis for the programmer role** | G H | Commit habits, expert against learner on synthetic repos, suggestions through the guard | BUILDING |
| **Clicky reuse** | W | MIT: plugin manifest, scoped autopilot session policy, post-action verification, confirmation state | BUILDING |
| Knowledge-work plugin skills as child playbooks | W | Apache-2.0; two skills (data, engineering) | BUILDING |
| Optional LoRA fine-tune of the local model | H | Not planned: cannot be validated in the time | CUT |
