# Attention layer: pre-registered evaluation plan (REQ-8)

Written Sat 7 Nov 2026 by the ATTENTION track, before any simulated workday was run on any seed. Everything here is SIMULATED: synthetic workers, synthetic schedules, synthetic event streams at the typical rates of the real producers. Nothing in this plan, and no result from it, says that real people find Understudy natural to use. It tests that the router behaves as designed under the stated assumptions. The only evidence about people is a live check with the four teammates (n = 4), which is not run here.

What had been run when this was written: the unit tests of the router and service (rule-by-rule, not outcome statistics). No workday simulation of any kind, on any seed.

## 0. What is being evaluated

`understudy_engine/attention/router.py` through `AttentionService` (the same code the routes call), with default `Params` and the balanced default `Settings`, against:

| Condition | Definition |
|---|---|
| **R** | The attention layer: events go through `submit`; Cue events are admitted through `submit` (the adapter's `show` answer); everything else is delivered by `next`, polled as the adapter would (every 2 s while the worker is present, every 15 s while away). The worker reacts to what is displayed; their reactions are sent back as feedback. |
| **R-nolearn** | R with the acceptance estimates frozen at the prior (no learned quieting). Isolates what learning does. |
| **B1** | Show everything immediately: every raise from a producer is displayed at once on its loudest channel (the `loud` row of the type table), with no coalescing, no one-voice rule, no quiet states, no budget, no digest and no reminder cap. Producers re-raise as they really do (see below), so duplicates reach the worker. Needs-you items are re-announced every 5 minutes until resolved, as a naive notifier would. |
| **B2** | One daily digest only: nothing is displayed all day except one summary at the worker's first activity of the day, listing everything open. Safety items wait for it. This is the "too passive" baseline: it shows what silence costs. |

Common random numbers: one worker, one day, one seed produce ONE state timeline and ONE raw event stream, replayed under all four conditions. A worker's reaction draws are keyed by (worker, event index, draw name), so conditions share draws wherever the same thing is displayed. Differences between conditions are therefore paired per worker.

## 1. Seeds, splits, population

| Thing | Dev | Held-out |
|---|---|---|
| Population seeds | 0 to 4 | 1000 to 1004 |
| Workers | 4 archetypes x 10 per population seed (nine-to-five, night-owl, shift-worker, irregular) | the same design, different draws |
| Days | 10 working days per worker | 10 working days per worker |
| Scenario days (section 4) | scripted, fixed | the same scripts, held-out seeds for the background events |

Schedules come from the personas: the planted `daily` windows of `data/synthetic/<persona>/truth.json` when the files exist (the run records `schedule_source: persona_truth`), otherwise a built-in generator with the same four archetypes (`built_in`). Person effects (event-rate multiplier, typing share, acceptance propensity, glance rate) are lognormal with sd 0.25, drawn per worker. The presence model is not fitted here: the router finds absences itself from the polls (its own `away_since` tracking), as it does in the product; the simulated worker's away state comes from the schedule.

Thresholds and parameter choices are made on DEV only. The held-out run happens once, after the lead has committed this file, and its numbers are reported whatever they are. A change after a held-out look is reported as a post-hoc change.

## 2. The simulated worker and the producers (assumptions, all stated in `attention/simulate.py`)

**Worker state** on a 5 s grid inside the day's work windows: alternating typing bursts (mean 4 min, `typing_burst`, quiet under 2 s), short thinking pauses (mean 25 s), reading pauses (mean 60 s), task ends every 5 to 15 minutes (`task_marker_s` resets), coffee gaps (3 to 10 min, away), a lunch absence (30 to 60 min), and `deep_work` when activity has run 25 minutes with no gap of 2 minutes or more. On some days: a meeting block (`in_meeting`), a call (`on_call`), a screen-share block (`screen_sharing`), a quiet hotkey period (`dnd`). Outside the windows the worker is away or locked. The worker's state does not depend on the condition (interruptions cost attention seconds, they do not change the schedule).

**Producer streams** (per working day unless stated; rates are my stated approximations of the real producers, scaled by the person's multiplier):

| Producer | Events | Typical rate and shape |
|---|---|---|
| Cue | `cue_cue` (tier 1, then an escalation of the same episode after 25 s), `cue_ask` (one per episode, 15%), `cue_offer` (after a 90 s stall, 10%) | stuck episodes 1.2 per working hour, plus false nudges 0.5 per hour; Cue's own gate holds it back while the worker types or has been quiet under 2 s, but it knows nothing of meetings, calls or screen sharing. Sensitivity: a 5% gate leak into typing |
| Proactive briefing | `briefing_ready` (1 to 3 cards) | at the first activity of the day and at a 12 h regeneration; re-announced on each regeneration |
| Routines | `routine_proposal` | 0.7 per day, up to 2 re-offers when ignored (proposals.ts `maxIgnores`) |
| Approval queue | `approval_waiting` (overnight runs, 0.8 per night), `approval_blocking` (a running job waits: 0.6 per day), `irreversible_decision` (overnight, 0.15 per day) | the producer re-raises a pending item every 5 minutes until it is resolved or expires (the real polls do) |
| Agent runtime | `run_finished` (overnight 2 per night, background 1.5 per day; 85% done, 10% failed, 5% paused), `morning_report` (1 per day after an overnight run), `run_blocked_target` (0.5 per day), `run_blocked_error` (0.4 per day), `injection_pause` (0.05 per day) | blocked and paused runs are re-raised every 5 minutes while unresolved |
| Calendar layer | `calendar_deadline` | 0.5 per day, 30 to 120 minutes ahead |
| Health | `service_degraded` | 0.2 per day, resolved after 10 to 60 minutes |
| Kill switch | `kill_engaged`, then `kill_cleared` | 0.03 per day (scripted in the scenarios) |
| Coach chip | `help_level_changed` | 0.4 per day |

**Worker reaction to a display** (the attention-cost model, fixed before any run). Each type has a base follow probability (cue_cue 0.55, cue_ask 0.7, cue_offer 0.3, routine_proposal 0.35, briefing_ready 0.4, approval and run items 0.8, deadline 0.7, digest 0.6, level glance 0.2, run_finished 0.3, safety 0.95) times the person's acceptance propensity. In a typing burst or deep work the follow probability is multiplied by 0.4 and a fast dismissal is twice as likely; at a natural break it is multiplied by 1.2 (capped at 0.98). The reaction is `followed` (within 10 s), `dismissed` within 4 s, `dismissed` later, or `ignored`. A passive badge or banner is noticed by a present worker at Poisson rates (tray glance 1 per 8 minutes; dashboard open 3 per day), and a digest is read when it is displayed or the dashboard is opened.

**Attention cost** of an interrupting display, in seconds of lost focus: typing burst or deep work 25 (chip 10); a thinking or reading pause that is not a natural break 8; a natural break 3; a meeting, call or screen share 30 and one exposure event. These are assumptions to make the comparison explicit, not measurements; the sensitivity run doubles and halves them and reports whether any ordering of conditions changes.

**Important items:** all safety items, all time-sensitive items, and `approval_waiting`. The window within which an important item must be seen: safety 60 s of the worker's presence, time-sensitive 15 minutes of presence or its expiry if sooner, `approval_waiting` the first presence plus 30 minutes. "Seen" means: displayed as an interrupting item to a present worker, or noticed as a passive marker, or listed in a digest that was displayed. The clock starts at the arrival, or at the worker's return if they were away.

## 3. Metrics

Each metric is computed per worker, then reported pooled with a **person-level bootstrap** (resample workers with all their days, 1000 draws, 95% percentile interval; 200 draws in fast mode) and with n (workers and worker-days), split (dev or held-out) and the synthetic badge. Paired differences (R minus B1, R minus B2, R minus R-nolearn) are per-worker differences with the same bootstrap.

| Metric | Definition |
|---|---|
| Interruptions per hour in flow | interrupting displays shown while `typing_burst` or `deep_work` is on, per hour of flow; all, and excluding safety |
| Interruptions per working hour | all interrupting displays per hour of presence |
| Hard-quiet breaches | non-safety interrupting displays shown during a meeting, call, screen share or quiet hotkey (count per worker-day) |
| Important seen within window | share of important items seen inside their window |
| Median delay of important items | seconds from arrival (or return) to seen; by class |
| Duplicate rate | displays whose family and subject were already displayed (reminders counted separately) over all displays |
| Missed-urgent | safety items not seen inside 60 s of presence. Must be 0 for the router; reported for every condition |
| Reminders per needs-you item | mean and maximum; the router's maximum is 1 by construction and the result reports it as measured |
| Digest length | lines per digest and items folded per digest |
| Acceptance rate | followed over displayed interrupting items (implicit labels); the fast-dismissal rate beside it |
| Attention cost | seconds of lost focus per worker-day under the stated cost model |
| Learning effect | R minus R-nolearn on interruptions per working hour for the can-wait and helpful-now types, by simulated day |

## 4. Scenario days (scripted; each with explicit assertions as tests and numbers in the report)

| Id | Script | What must hold |
|---|---|---|
| S1 overnight approval | an overnight run finishes three tasks and stops for one approval (`approval_blocking`, `blocks_run`); the nine-to-five worker returns at 08:50 | the approval is the first thing shown on return, once; a badge exists from the moment it arrived; at most one reminder after 20 minutes if untouched; the morning summary is a banner or one toast, not a second announcement of the approval |
| S2 meeting and screen share | a 2 hour meeting with a 40 minute screen share inside; Cue fires three times inside; a blocking approval and an injection pause arrive during the share | no non-safety interruption in the meeting; held items are shown after it, at a break; the injection pause is shown during the share with content-free wording; the held approval is not lost |
| S3 injection pause in a long run | three hours of focused work with a long foreground run; an `injection_pause` arrives in hour two while the worker is typing | shown within 5 s despite typing; exactly one toast; the marker persists until resolved; no reminder; nothing else interrupts in that minute |
| S4 dismisses everything | for 14 simulated days the worker dismisses every non-safety display within 1 s | proposals and briefings quieten (fewer toasts on later days than on the first days, interval reported); approvals and safety do not (still shown, badge present); `missed-urgent` stays 0 |
| S5 kill state | `kill_engaged` during a call, while away, and during typing | the stopped marker is present at the first poll in every case; the notice is shown at once, or first on return when away |

## 5. Tuning (dev only)

Grid, fixed here: `min_gap_s` in {60, 90, 120}; `budget_per_day` in {6, 10, 14}; `break_idle_quiet_s` in {10, 15, 25}; `max_hold_soft_s` in {300, 600, 900}; `quiet_thr1` in {0.20, 0.25, 0.30} (with `quiet_thr2` = half of it); `n_min` in {4, 6, 10}. One factor at a time from the defaults (16 configurations), on dev seeds 0 to 4. Selection rule: among configurations with important-seen at least 95%, missed-urgent 0 and median important delay at most 120 s, the one with the lowest non-safety flow interruptions per hour; ties go to the lowest attention cost, then to the defaults. The hard constants (`max_reminders`, the safety rows of the type table, the floors) are not in the grid. If nothing beats the defaults by more than the dev interval, the defaults stay and the report says so.

## 6. Acceptance (design targets, stated before any run; not measured tolerances)

On the held-out run, pooled, intervals from the person-level bootstrap:

1. Router versus B1: non-safety interruptions per flow hour lower, paired interval excluding 0; hard-quiet breaches 0; duplicate rate lower, interval excluding 0.
2. Important seen within window at least 95% for R, and not more than 3 points below B1.
3. Missed-urgent 0 for R in every worker and every scenario. (B2 is expected not to meet this; it is reported.)
4. Reminders per needs-you item: maximum 1 for R.
5. Router versus B2: important seen higher and missed-urgent lower, paired intervals excluding 0.
6. S1 to S5 assertions hold.
7. Learning: in S4, later-day can-wait toasts below early-day toasts with the interval excluding 0, and approvals unchanged.

Each criterion is reported as met, not met or inconclusive. Failing criteria are reported as failing, with the number, and enter the limitations register.

## 7. What this does not show (goes to the limitations register)

- That real people experience the product as natural, calm or helpful. The reaction model and the cost model are my assumptions; the orderings are checked by halving and doubling the costs, but they remain assumptions.
- That the producers' rates are right. They are stated approximations; the sensitivity sweep scales them by 0.5 and 2.
- That implicit labels measure welcome. A fast dismissal can mean "I already knew"; the simulated worker's labels come from the simulated reaction model, so learning is validated against the model that generated it (its direction, not its calibration).
- Hard quiet states, screen sharing and call detection are inputs the awareness layer must supply in the product; here they are known exactly. If the real probes are wrong, the router is wrong with them. When the state is unknown the router holds everything except safety, and the simulation includes a run with 10% of polls unknown to show the cost.
- The live check with the teammates (n = 4) is the real test of "natural", and is not run.

## 8. Outputs

`evaluate_attention(fast=False, held_out=False)` in `understudy_engine/attention/evaluate.py` returns a JSON-able dict with `meta` (n, split, seeds, schedule source, origin `synthetic`, code hash, the cost model), `conditions` (the metrics above with intervals), `paired` (differences), `scenarios` (S1 to S5 with their assertions and numbers), `tuning` (the dev grid and the selection), `sensitivity`, `acceptance` (criteria with met, not met or inconclusive), `limitations`. Fast mode (a handful of workers, two days, dev seeds only, 200 bootstrap draws) finishes in under 60 seconds. The full dev and held-out runs go through `scripts/heavy.sh`.
