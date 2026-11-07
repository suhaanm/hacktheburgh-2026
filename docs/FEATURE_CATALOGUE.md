# Understudy feature catalogue (for the demo, the README and the Devpost)

Numbers in this file are copied from evals/report.md at the time of writing and go stale; the drafts in docs/drafts/CLAIMS.md trace each one. One place for everything the product does, how it ties together, and how sure we are. The lead updates it at every checkpoint. **Status words:** `verified` = the lead saw it work end to end; `built` = built and tested by its track, not yet seen end to end by the lead; `building`; `proposed`. **Evidence** is always labelled: synthetic, simulated participants (language model, not people), or live (n = 4 teammates, not run). Request log: `docs/IDEA_BOARD.md`. Specs: `docs/SPEC_LIST.md`.

## The loop in one line
Watch how people work, show where a novice loses time against an expert, coach on the real screen with help that fades, step in when someone is stuck, let an agent take repetitive work only with opt-in, and prove how much less help the worker needs over time.

## 1. Understand the work (the machine-learning layer)
| Feature | What it does | Status | Evidence |
|---|---|---|---|
| Work genome | Aligns your steps to the nearest expert's and prices every gap in seconds; shows where time went | verified on its own generator; **degrades on harder synthetic data** | synthetic; precision 92%, recall 95% on planted deficits (v1 generator). On three harder generator families (REALISM matrix) precision is 48 to 71% and recall 49 to 68%; thresholds fitted on v1 keep recall (87 to 95%) but precision collapses (33 to 56%), and the reverse; noisy experts raise the thresholds |
| Controls | Placebo (expert vs expert) and shuffled-label null so a gap is not an artifact | verified | synthetic; real gap 229.6 s vs placebo 7.1 s |
| Stuck model | Predicts "no progress in the next minute" from recent steps, dwell, repeats | verified on its own generator; **does not transfer** | synthetic, n = 4; log loss 0.436 vs 0.509 baseline on the v1 generator. On three harder generator families its edge over time-since-progress falls from 0.071 to 0.008 to 0.015 nats per bin and a v1-trained model is worse than that baseline; on the simulated-participant traces both v1 and v2 fail (REALISM matrix and M5 transfer). Held-out mismatch test (ML v2, three roles): the one-feature baseline time-since-progress beats v1's full model under a differently built generator (pooled difference 0.021 to 0.030 nats per bin), so the honest claim is that a simple time-since-progress rule does about as well; v2's gains under mismatch are mostly base-rate adaptation and calibration; the 1.0 per hour alarm budget is broken in many mismatch cells |
| Gap decomposition | Splits the novice-expert gap into explained and unexplained | built | synthetic |
| Fading help levels | L1 watch me to L4 on my own, from code; mastery with forgetting | verified | synthetic |
| Dignity gate and bandit | Decides when to speak; learns from dismissals; off-policy evaluation | built | synthetic |
| Routines finder | Finds repeated work, forecasts, decides when automating pays (ski rental) | built; mixed on harder synthetic data | synthetic; raw cluster precision 22% on v1 (100% after the value gate); on three harder families raw precision 44 to 97%, recall 45 to 92%, proposal precision after the gate 74 to 100% (REALISM matrix; the high precision partly reflects less repeated structure in the generated ad hoc work, not a better finder) |
| Presence model | Weekly map and "will they be away?" for background runs | built | synthetic |
| Review routing and trust ladder | Which agent outputs a human must check; autonomy earned with Wilson bounds | built | synthetic |

## 2. Coach on the screen
| Feature | What it does | Status | Evidence |
|---|---|---|---|
| Live coach brain | One decision at a time from live events | verified | synthetic: 14 of 14 planted rings, 0 expert prompts |
| On-screen annotations (REQ-4) | Thin ring with corner ticks, one small label, no permanent chip, small Stop all | built (lead viewed screenshots) | n/a |
| New logo and menu-bar icon (REQ-5) | Disc plus offset ring | building | n/a |
| Hold-to-talk activation (REQ-5) | Hotkey, menu bar, proactive cards; no always-listening mic | building | n/a |
| **Cue: stuck rescue (REQ-7)** | Sees the screen, finds the next step from the expert path, guides, asks a multiple-choice question when unsure, teaches, fades | building | simulated, pending |
| **Independence score and Growth screen (REQ-7)** | Logs every assist; shows needing less help over time, with intervals; excludes overnight automations | building | simulated, pending |

## 3. Awareness and models (REQ-5)
| Feature | What it does | Status |
|---|---|---|
| On-device awareness | Cursor dwell, rhythm, app kind: nothing leaves the Mac | building |
| Triggered and periodic glances | One downscaled frame to Gemini on a trigger, or every ~30 s if opted in; never stored; denylist; ledger | building |
| Gemini + OpenAI + local + ElevenLabs routing | Each role gets the measured best model; code decides; fallbacks | building (bake-off pending) |
| Independent verifier | A second model family checks agent runs | building |
| Live voice | Hold to talk, sees the screen, points | proposed (phase D) |

## 4. Agents that do the work, safely
| Feature | What it does | Status | Evidence |
|---|---|---|---|
| Benefits-processing agent | Three calculators, cliff check, reconcile, case note, real gate on the real submit button | verified | sandbox; 20 of 20 (mock), live clean 18 of 20, 0 false claims |
| Eight security layers | Injection pause, action classes, approval queue, hash-chained audit, kill flag, no allowlists | verified | red team: 42 attacks plus clean cases (source: evals/report.md, red-team section) |
| Shadow mode to approval | A routine earns autonomy by matching what the worker does | verified | synthetic |
| Computer use on the sandbox calculators | A model clicks and types through the same safety layers, with fact handles instead of values | **works in-sample, not held-out**: 3 of 3 development households; held-out clean n = 4: 1 completed, 2 false claims caught by the code check, 1 false gate stop; injected n = 20: 20 of 20 paused at step 0 (text-only evidence). Designed Submit waited for a human in every run | sandbox we wrote, language model, headless browser; gate 35e964049fd0 |
| Computer use on a real desktop | Same, through real clicks | not run; read-only rung R0 ran once (zero events) | owner present for every rung (`evals/agentic/REAL_CLICKS.md`) |
| Background agents (programming, data, creative) | Parent spawns children in a sandbox, code-verified results | built | synthetic |
| Overnight automations | Run for experts and novices alike; never change the independence score | built | synthetic |

## 5. Proactive layer, routines, privacy
| Feature | What it does | Status | Evidence |
|---|---|---|---|
| Proactive briefing | At most 3 cards; press to fire; learns acceptance | built | synthetic, development set, no held-out data: precision and recall in evals/report.md, proactive section (not quoted here) |
| Calendar routine layer | Meeting load, focus blocks, expert comparison, generic suggestions; Outlook and Teams adapters | building | synthetic; real read-only aggregate check needs the owner's go at run time |
| Git analysis (programmer) | Commit habits vs experts; five generic suggestions | built | synthetic: precision 116 of 116, recall 0.967 |
| Local model | Qwen2.5-7B digests on this Mac, rules fallback | built | n/a |
| Privacy spine | One logged choke point for the new layers (text and images) and a metadata-only ledger row for every Python provider call; canary tests. NOT yet true for the old Alongside desktop code, which still sends some screenshots and file text straight to OpenAI and Gemini behind flags (being gated or disabled; reviewer finding H6) | built, with a known gap | 0 of 11,336 planted tokens leaked in the layers that registered a flow |

## 5b. How it all fits together (REQ-8)
| Feature | What it does | Status |
|---|---|---|
| Context engineering | Every model call gets minimal, typed, fresh context; long runs keep a bounded working memory; trusted and untrusted text never mix | building (audit and shared library in progress) |
| One attention layer | One router decides whether, where and when the worker is told anything; one voice at a time; digests instead of pings; safety items never hidden | built; held-out simulated evaluation 11 of 12 criteria met, **criterion 7 not met** (later-day can-wait toasts rose from 0.92 to 1.25 a day, wrong direction); simulated workers, not people; the n = 4 teammate check was not run. Against show-everything: 0.150 vs 1.512 non-safety interruptions per flow hour, 0 hard-quiet breaches, 98.4% of important items seen in window, median delay 85 s; against one daily digest it is louder but delivers (digest sees 28.3% of important items in window and misses 182 of 528 safety items) |

## 6. Evidence and honesty
| Feature | What it does | Status |
|---|---|---|
| Evidence page and `make eval` | 32 sections and a 124-entry limitations register at the time of writing (source: evals/report.md; the Evidence map is generated from the report); every number has n, split, interval, origin | verified |
| Simulated study | Language-model participants, pre-registered, labelled not people | running (benefits) |
| Role studies (REQ-7) | Same for programmer and data analyst | building |
| Realistic data and generator-mismatch test (REQ-7) | Harder, more human-like synthetic data; still badged synthetic | building |
| LLM explainer with number check (REQ-6) | Plain-English "where your time went"; every number must trace to the data. The shipped wording is a code template that passes its own check; a model's words are used only if they pass the same check; cloud wording is off by default | built (302 tests); synthetic packets; live arms small n: local Qwen reword 24 of 30, Gemini fast 7 of 9, OpenAI fast 0 of 13. The check proves traceability, not truth |
| ML v2 (REQ-6) | Signals, calibrated stuck model, expert envelope, counterfactual seconds | built; **held-out results mostly negative**: the pre-registered genome ensemble (E4) and the counterfactual (Q1) were REJECTED as harmful (+3.81 s [+2.30, +5.19] and +1.17 s [+0.44, +1.87] absolute error); only E1 (learned substitution costs) was accepted, a marginal 5% gain with a biased row, so v1 alignment stays the default and there is no validated counterfactual; M5 transfer to simulated-participant traces failed for v1 and v2. Synthetic data, our generator, fresh seeds |
| Top insights for workers and admins (REQ-9) | A deterministic engine picks at most a few pointers per worker and a firm view for admins; reliability gate, guard metrics, k-anonymity, "nothing stands out" is a valid answer | engine built (144 tests), plan pre-registered (`evals/insights/PLAN.md`), held-out run pending; synthetic firm |
| Repeat list (hit list) | Compact page of actions you repeated that could be automated; ranked by minutes saved; Automate opens a "Watch first" peek, never runs anything | built (engine 124 tests, page seen in a harness; not yet seen in the real shell); synthetic |
| Admin role: Firm screen (REQ-9) | Per-user numbers and enums, expert versus junior, firm by role over time, onboarding-speed curves, Monday note, prediction scorecard | building (UI); synthetic firm, labelled |
| Design system sync | Friend's enhanced design system adopted; Hint pattern; fewer words, details behind tooltips | phase 1 done, phase 2 (screen edits) building |

## Demo moments (candidates)
1. A novice and an expert side by side; the gap in seconds, by habit, with intervals.
2. The ring appears on exactly the right control, once; the worker ignores it and nothing nags.
3. Stuck: Cue asks one question, the worker answers by voice, the next step is shown, a one-line reason, then silence.
4. The Growth screen: help fades, the independence curve rises.
5. Overnight: the morning queue; one tap approves; nothing ran unapproved.
6. The Privacy screen: every logged call that left the Python services and the new layers, no pictures, no text (the legacy desktop vision paths are being brought under the same ledger).
