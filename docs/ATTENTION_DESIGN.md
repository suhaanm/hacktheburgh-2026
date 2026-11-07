# Attention layer design (REQ-8)

Owner's ask: the whole product should feel natural and human to use. Notifications must not be spammed, and must not be too passive either. Today the parts that can interrupt a worker (Cue cues, questions and offers; briefing cards; approval items; agent results and the morning report; needs-human pauses; the 2 s help-level toast; tray badges; the Stop all pill; voice; dashboard banners) decide independently. Nobody owns the ensemble.

This document is the design for ONE attention layer. It decides, in deterministic code, **whether, where, when and how loudly** the worker is told anything. It does not decide what is true (producers do) and it never writes text with a model. Status: PROPOSED by the ATTENTION track, 7 Nov 2026. Flag: `UNDERSTUDY_X_ATTENTION` (or the master `UNDERSTUDY_X`), off by default, never on the P0 demo path.

Files: pure engine package `services/engine/understudy_engine/attention/**`, tests `services/engine/tests/attention/**`, schema `packages/schema/attention_event.schema.json`, desktop adapter `apps/desktop/src/main/attention/**`, plan `evals/attention/PLAN.md`.

## 0. Principles (the product's voice rules, in code)

1. **Silence is the default.** An interruption needs a reason in a table, not an absence of a reason not to.
2. **Safety is never suppressed, never batched, never repeated.** It is shown once, calmly, and then lives as a passive marker until resolved.
3. **A decision is shown at most once, reminded at most once, and then never nagged.** Reminder caps are hard constants.
4. **One voice at a time.** While a cue, a question card or a toast is up, nothing else interrupts (safety preempts; that is the only exception).
5. **Nothing important sits unseen.** Every item that needs the worker has a passive marker the moment it exists, even while it is held.
6. **Learning can only quiet.** Reactions can lower the loudness of low-value types. Nothing learned can raise a type above its table value or lower it below its floor.
7. **The worker can always see why.** Every held, shown or dropped item has a one-line fixed reason.
8. **Metadata only.** Events carry ids and enums. No screen, file, model or page text passes through the router, its store or its log.

## 1. Inventory of interrupting events

Urgency classes: **safety** (safety-critical), **time** (time-sensitive), **now** (helpful-now), **wait** (can-wait), **info** (informational). `Decision` column: a needs-you item is something the worker must decide or act on, so it counts in the tray badge. Expiry is how long the item stays relevant when the producer does not say; the producer may shorten it (never lengthen past the table maximum). Flow column says what the router does while the worker is in flow (typing burst, deep work), on a call or screen sharing, away or locked: **S** shown anyway, **H** held for the next natural break, **HH** held until the hard-quiet state ends, **D** dropped (its moment passed), **L** silent log.

| Event type | Produced by | Class | Reversible | Needs you | Expiry | Flow | Hard quiet | Away |
|---|---|---|---|---|---|---|---|---|
| `kill_engaged` | desktop kill switch (HUD, hotkey, tray) | safety | yes (Resume) | yes | until cleared | S | S | marker, shown on return |
| `kill_cleared` | desktop kill switch | info | n/a | no | 60 s | L | L | L |
| `injection_pause` | agent runtime (child paused by the detector), queue kind `injection_pause` | safety | yes (run paused, nothing changed) | yes | until decided | S | S (content-free wording) | marker, shown on return |
| `irreversible_decision` | agent runtime / approval queue: an unattended run needs a decision about something irreversible (queue risk class `irreversible`) | safety | no | yes | queue max age | S | S | marker, shown on return |
| `run_blocked_target` | agent runtime (needs-human: target not resolved) | time | yes | yes | 30 min | H (cap 10 min) | HH | marker, on return |
| `run_blocked_error` | agent runtime (needs-human: error page) | time | yes | yes | 30 min | H (cap 10 min) | HH | marker, on return |
| `approval_blocking` | approval queue / desktop confirm toast: an approval a running job waits on | time | no (the action is gated) | yes | queue max age | H (cap 10 min) | HH | marker, on return |
| `calendar_deadline` | calendar layer: a deadline derived from the calendar | time | n/a | yes | the deadline | H | HH | marker, on return |
| `cue_cue` | Cue (tier 1 ring, tier 2 chip, tier 3 ghost run) | now | n/a | no | `expires_in_s` (12 s) | D | D | D |
| `cue_ask` | Cue question card (one per episode) | now | n/a | yes (a click) | `expires_in_s` (12 s) | D | D | D |
| `cue_offer` | Cue "want a hand?" chip | now | n/a | no | `expires_in_s` | D | D | D |
| `voice_line` | Cue tier 4 whisper, spoken briefing | now | n/a | no | 10 s | D | D | D |
| `help_level_changed` | coach chip driver (the 2 s level toast) | info (glanceable) | n/a | no | 60 s | L | L | L |
| `routine_proposal` | handoff routines (proposals.ts) | wait | n/a (opt-in) | yes | 72 h | H | HH | digest |
| `briefing_ready` | proactive briefing (cards) | wait | n/a | no | 24 h to 72 h by card | H | HH | digest |
| `approval_waiting` | approval queue, an item nothing waits on | wait | no | yes | queue max age | H | HH | digest |
| `run_finished` | agent runtime (foreground or background result), offhours run end | wait | n/a | no | 24 h | H | HH | digest |
| `morning_report` | agent offhours report, `GET /agents/morning` | wait | n/a | no | 24 h | H | HH | digest |
| `service_degraded` | engine or agent health, model boot check | wait | n/a | no | until recovered | H (banner only) | L | banner |
| `attention_digest` | the router itself (section 5) | wait | n/a | yes if it lists a needs-you item | 12 h | H | HH | on return |

Not events, but **markers** (state with a passive display, never counted against any budget, never take the lock): kill engaged, agent acting (the Stop all pill), a glance in flight, Understudy paused, the tray needs-you count and the dashboard waiting count. The router reports the counts; the owners of the pills and the tray keep drawing them.

Two choices to flag to the owner (both reversible):

- `help_level_changed` is informational, so by principle 1 it would be silent. It is the one place the owner's UI direction says the interface visibly fades, so it is allowed as a 2 s in-context glance **only** when nothing else is up, the worker has been quiet for 2 s and no quiet state holds, at most twice an hour, and it spends no budget. Otherwise it is a silent log line.
- Cue's own gate stays authoritative on whether Cue speaks. The router is a second, stricter gate: it can silence a cue (one voice, quiet states, budget, learned quieting), it can never cause one.

## 2. Channels, ranked by intrusiveness

| Rung | Channel | Passive or interrupting | Used for |
|---|---|---|---|
| 0 | `log` | silent | informational; anything dropped; the reason is still recorded |
| 1 | `badge` | passive | tray count of needs-you items; menu line "2 things need you" |
| 2 | `banner` | passive, seen on return | dashboard banner and digest; service state |
| 3 | `chip` | interrupting (in context) | Cue ring or chip; the 2 s level glance |
| 4 | `toast` | interrupting (compact, top right) | time-sensitive items, safety, the digest when it lists a needs-you item, one proposal |
| 5 | `question_card` | interrupting (needs a decision) | Cue's one question |
| 6 | `voice` | interrupting (audio) | only when the worker asked or a voice session is already open; otherwise it degrades to `chip` |

There is no phone channel. Nothing is ever pushed off the machine. Each type has a **ladder** (its allowed rungs from loudest to quietest) and a **floor** (the quietest rung it may reach). Safety types have the single rung `toast` and a floor of `toast`; `approval_blocking` has floor `badge`; everything else floors at `log`.

## 3. The router

```
AttentionRouter.decide(event, worker_state, history) -> Decision
Decision = {channel, deliver_at, text_id, dedup_key, expires_at, reason_code,
            badge, priority, reminder_due_at, ladder_rung_drop}
deliver_at in {now, next_natural_break, on_return, digest}
```

Pure function of its three arguments and the fixed `Params` (no clock, no randomness, no I/O). It is evaluated twice for an item: on arrival (admission) and at every `GET /attention/next` poll (release), so a held item is simply re-decided with the worker state of the moment. A `Decision` with `channel = log` is a drop, with the reason recorded.

### 3.1 Inputs

`worker_state` (all booleans, numbers and enums, built by the desktop adapter from signals the awareness layer already has; nothing is content): `now`, `typing_burst`, `quiet_s` (seconds since last input), `deep_work` (at least 25 minutes of continuous activity without a break), `task_in_progress`, `task_marker_s` (seconds since the last task or episode end), `away`, `away_s`, `locked`, `dnd` (the worker's own quiet hotkey or quiet-until time), `screen_sharing`, `on_call`, `in_meeting` (from the calendar layer when it is on; else false), `voice_session`, `asked` (the worker pressed for help), `dashboard_focused`, `local_hour`.

`history` (read from the store): the daily budget used and day, interruption timestamps (for the 90 s gap), per-type show times, per-item reminders, `lock` (what is on screen and until when), the acceptance estimates, the worker's settings, last digest time, last active time (for "start of day" and "welcome back").

### 3.2 Rules, in order (the first that fires gives the reason code)

1. **Resolved or expired.** A `resolve` op, or `now >= expires_at`, ends the item. `channel = log`, reason `resolved` or `expired`. This is the proactive layer's staleness check applied to everything.
2. **Never for this.** The worker said never for this subject: drop, reason `never_subject`. Safety and `approval_blocking` ignore it (they cannot be hidden by a subject-level "never").
3. **Safety.** `channel = toast`, `deliver_at = now`, regardless of quiet states, budget, mode and learning; if the worker is away or locked, the marker is set at once and `deliver_at = on_return` (nobody is there to be told; the first thing they see on return is this item, ahead of any digest). A safety item preempts the one-voice lock. Reminders: none. The item is shown once; then it is a marker until resolved.
4. **Hard quiet** (`dnd`, `screen_sharing`, `on_call`, `in_meeting`; the worker's quiet-for-an-hour is `dnd`): time and wait items are held (`deliver_at = next_natural_break` once the state ends), `badge = true` for needs-you items; now items are dropped (`quiet_<state>`); info is logged.
5. **Away or locked.** Time items: marker now, `deliver_at = on_return`. Wait items: `deliver_at = digest`. Now items: dropped.
6. **Soft quiet** (`typing_burst`, `deep_work`, or not a natural break): time items are held for the next natural break, but at most `max_hold_soft_s` (600 s); after that they release as soon as the worker is not in a typing burst. Wait items wait for a natural break (or the digest). Now items are dropped as a backstop to Cue's own flow gate.
7. **Mode and learning.** The worker's per-type mode (loud, normal, quiet, digest; section 6) fixes the highest rung the type may use and the reminder count. The acceptance model may then lower the rung by one or two for low-value types (never for safety, never below the floor; section 3.6). The result is the final `channel`.
8. **One voice.** If the lock is held by another item that has not ended: now items are dropped (`lock_held`), time and wait items stay held (`lock_held`) and are re-decided at the next poll. A different item in the same family and subject as the holder supersedes it instead (a newer cue tier replaces an older one).
9. **Spacing and budget.** A new interruption (rung 3 or above, not safety, not a continuation of the family on screen) must be at least `min_gap_s` (90 s) after the last interruption. The shared daily attention budget (default 10 a day) counts now and wait interruptions; when spent, now items are dropped (`budget_spent`) and wait items fall to the digest. Time and safety items are outside the budget and have their own caps.
10. **Deliver.** `deliver_at = now` and the channel from rule 7. If more than one wait item is held when a natural break arrives, they are delivered as ONE digest-lite item, never one after another.

### 3.3 Time-sensitive items: one toast, one badge, one reminder, then nothing

Sequence for `run_blocked_*`, `approval_blocking`, `calendar_deadline`: (1) the passive badge exists from the moment the item exists; (2) ONE toast when soft and hard quiet allow, with the rung and mode rules above; (3) the badge stays; (4) **one** gentle reminder toast after `reminder_after_s` (1200 s; 600 s in loud mode; none in quiet and digest modes) if the item is still unresolved and the worker did not open or dismiss it, delivered at a natural break and subject to the same quiet rules; (5) nothing else, ever. The badge stays until the item is resolved or expires. `max_reminders = 1` is a constant, not a parameter. A calendar deadline gets its reminder only if the deadline is still more than 10 minutes away.

### 3.4 Coalescing, superseding, expiry

- **Dedup key** `family:subject`. The same key within the window becomes one item with `count + 1`; never two items. The window is the item's lifetime.
- **Families.** `kill`; `run` (run_blocked_target, run_blocked_error, injection_pause, irreversible_decision, run_finished; subject = run id); `approval` (approval_waiting, approval_blocking; subject = queue id); `cue` (cue_cue, cue_ask, cue_offer, voice_line; subject = episode id); `briefing`; `proposal` (subject = routine slug); `deadline`; `service`; `level`; `report`; `digest`.
- **Superseding.** A newer item in the same family and subject replaces an older **unseen** one (state held), keeping the older's marker; a newer item never replaces one already shown. An `approval_blocking` supersedes an `approval_waiting` for the same queue item. A `run_blocked_*` supersedes the run's `run_finished` placeholder if there is one.
- **Expiry.** Every item has `expires_at`; a producer may also send `resolve` when the world changed (an approval was decided in the dashboard, a run finished by itself, a card went stale). Expired and resolved items are dropped without bothering anyone and appear in neither digest nor badge.

### 3.5 Natural break

A natural break is the first of: (a) the worker is quiet for at least 3 s and a task or episode ended in the last 90 s; (b) quiet for at least 15 s with no task in progress; (c) quiet for at least 90 s while a task is in progress; (d) the dashboard has focus; (e) the worker has just returned from an absence of at least 15 minutes; (f) the first activity of the local day. The first three are the same numbers `proposals.ts` uses today, so the two layers agree; the adapter replaces that file's own rules by asking the router.

### 3.6 Learning from reactions (Pupil's implicit labels; this can only make the router quieter)

Labels, from the feedback the desktop sends: `followed` (the worker opened or acted within 10 s) is positive; `dismissed_fast` (closed within 4 s: unwelcome) and `never` are strongly negative; `dismissed` (after 4 s) and `ignored` (timed out untouched, weak because it may not have been seen) are mildly negative. These are noisy proxies (a dismissal can mean "I already knew"; the eval says so).

Per person, per type: a Beta(2, 2) prior and weighted counts over the last 60 labels, smoothed across hours (the neighbouring hour counts 0.5, two away 0.25). The estimate is the posterior mean `p`, with `n_eff` the summed weights. The learned drop is: 0 unless `n_eff >= 8`; one rung when `p <= 0.25`; two rungs when `p <= 0.12`. The drop applies to now and wait types only, never below the type's floor, never to safety or `approval_blocking`. It is stored as `learned_drop` per type and hour and is shown in the settings panel and in `why`; the worker can reset it. Nothing the model learns can raise a rung. Three `never` answers on distinct subjects of one type move that type's learned drop to its maximum and say so in the next digest.

### 3.7 Settings, defaults

Per type, one of **loud, normal, quiet, digest**, and a global **attention budget per day** (0 to 40). Defaults ("balanced" for a first-time user): every type `normal`, budget 10. The mode changes the table like this (safety ignores every mode):

| Class | loud | normal | quiet | digest |
|---|---|---|---|---|
| time | toast, reminder at 10 min | toast, reminder at 20 min | badge, one toast at the next natural break only for approvals and deadlines, no reminder | badge and digest line only |
| now | Cue gate as is, budget x1.5 | Cue gate as is | no offers, no questions unless asked, budget x0.5 | silent unless asked |
| wait | roll-up toast at the next break | digest or one roll-up toast at a break if a needs-you item is held | digest and banner only | digest only |
| info | as normal | log (level glance allowed) | log | log |

## 4. Wording

Every text is a template in a fixed table (`attention/texts.py`), filled only with enums and numbers (a count, a duration rounded to 5 minutes, a fixed label from a vocabulary). No model text, no screen text, no names. A test lints every template and every rendered sample against these rules:

- Plain, specific, short. A toast title is at most 8 words and its body at most 22. A digest line is at most 16 words.
- Say what happened, and what the worker can do ("Open the run to decide").
- It names its source, one of a fixed set: "Your overnight run", "Your agent run", "Cue", "Briefing", "Approval queue", "Understudy", "Your calendar".
- No exclamation marks. None of: "just", "simply", "urgent", "hurry", "immediately", "asap", "don't forget", "reminder:", "heads up", "oops", "whoops", "friendly", "great news", "welcome back!", "you missed", "you forgot", "still waiting", "overdue" (on a worker), "last chance", "only today". No guilt, no countdown theatre, no emoji.
- Sentence case, a full stop at the end. Numbers as digits.

Samples (final wording is in the table and is tested, not hand-edited in the UI):

| Text id | Title | Body |
|---|---|---|
| `kill_engaged` | Everything is stopped | Understudy: nothing is running. Resume from the menu bar when you are ready. |
| `injection_pause` | An agent run paused | Your agent run paused because a page tried to give it instructions. It ignored them and changed nothing. Open the run to decide. |
| `irreversible_decision` | A run needs your decision | Your overnight run reached a step that cannot be undone. It has not done it. Open the queue to decide. |
| `run_blocked_target` | A run is waiting for you | Your agent run could not find the right button on the page. Open the run to point it there or stop it. |
| `run_blocked_error` | A run is waiting for you | Your agent run reached an error page. Open the run to retry or stop it. |
| `approval_blocking` | An approval is waiting | Approval queue: a running job is waiting for your decision. |
| `approval_reminder` | One approval is still waiting | Approval queue: the job is paused until you decide. This is the only reminder. |
| `calendar_deadline` | A deadline is coming up | Your calendar: one deadline in 45 minutes. |
| `routine_proposal` | A routine you could hand over | Briefing: you did the same steps 9 times this week. Look at it when you have a moment. |
| `digest_morning` | Good morning | Your overnight runs: 3 finished, 1 needs a decision, 4 can wait. Open the summary. |
| `digest_return` | While you were away | 2 runs finished, 1 approval is waiting. Open the summary. |
| `cue_offer` | (chip) Want a hand? | Cue |
| `level_changed` | (chip, 2 s) Help level 2 | Understudy |

## 5. Digest, morning and welcome-back

One calm summary instead of N pings. Built by code from the held items, never by a model. Triggered when the first of these happens and no digest was built in the last 3 hours: the first activity of the local day after at least 4 hours away ("morning"), or a return after an absence of at least 30 minutes found by the presence model ("while you were away").

Shape: `{kind, window, needs_you: [...], ran: {...}, can_ignore: {...}, lines, counts}`.

- **Needs you** first, ordered safety, then time (deadline soonest first), then decisions the worker opted into (proposals, approvals), at most 5 lines, each a template line with a count and a deep link id.
- **What ran**: one line per outcome with counts (finished, failed, paused, yielded), never per run.
- **You could ignore**: one line with counts by kind (briefing cards, suggestions with no deadline, service notes) so the worker sees what was left out and where it is.
- The digest is delivered as ONE toast if `needs_you` is not empty (the badge counts them from the moment they arrived), else as a banner only. Lines are capped at 7 in total; if more exist, the last says how many more.
- Items folded into a digest are marked `digested` and are not delivered again.

## 6. Transparency and control

- `GET /attention/why?item=` returns the item's type, state, the reason code and its fixed one-line text ("Held because you were typing. Shown at your next pause."), the transitions with reason codes, the mode in force, any learned quieting, and the budget at the time. Metadata only.
- Settings (worker only): per-type mode, daily budget, the reset of learned quieting, and (read-only here) the hard floors that cannot be turned off, said in plain words ("Safety stops and approvals that block a job always stay visible").
- The dashboard panel shows the day so far: shown, held, dropped, with the reason of each and the budget left. DASH-LIVE owns the panel; the contract is in section 8.

## 7. Privacy

- **Events** are closed-schema JSON (`packages/schema/attention_event.schema.json`, `additionalProperties: false`): a type enum, the person slug, an opaque subject id matching `^[a-z0-9][a-z0-9_.:-]{0,63}$`, an op, a risk class enum, an outcome enum, a small count, a duration in minutes, a relative expiry. No free text field exists. A value outside its pattern is refused.
- **The router, the store and the log** hold ids, enums, counts and timestamps. The store file is `<data>/attention/state.json` plus an append-only `log.jsonl` of transitions. Both live on the device, can be exported and deleted, and never reach a model or the network. The package imports no network, model or subprocess module (the `attention` layer is added to the static privacy guard).
- **Rendered text** comes only from the template table; slots are enums and rounded numbers.
- **Screen sharing**: the content-free wording is what makes a safety toast acceptable while sharing: it names no site, file, person or amount.

## 8. Contracts

### 8.1 Engine (all under the flag; plain JSON errors `{"error": {"code", "message"}}`; writes use the shared `http_guard`, worker actor only for settings and feedback; producers are `worker`, `system`, `agent`)

```
POST /attention/events    {type, person, subject, op?, risk_class?, outcome?, count?, minutes?, expires_in_s?, deadline_in_s?, blocks_run?, origin?}
                          -> {item_id, decision: {channel, deliver_at, text_id, dedup_key, expires_at, reason_code, badge}, show: bool, coalesced: bool}
                          For now-class events (cue_*, voice_line) `show` is the admission answer: the caller shows the cue only when true.
GET  /attention/next      ?person=&typing=&quiet_s=&away=&away_s=&locked=&dnd=&screen_sharing=&on_call=&in_meeting=&deep_work=&task_in_progress=&task_marker_s=&voice_session=&dashboard_focused=&local_hour=
                          -> {meta, data: {item: null | Item, active: null | {id, type, until}, badges: {needs_you, waiting, marker}, digest_ready, poll_after_s}}
                          at most ONE item; Item = {id, type, channel, text_id, title, body, source, count, actions[], priority, new, preempt, expires_at, reason_code}
GET  /attention/digest    ?person=&kind=morning|return|now   -> {meta, data: Digest}
POST /attention/feedback  {item_id, event: shown|followed|dismissed|ignored|never|opened, seconds?}   (worker)
GET  /attention/why       ?item=   -> {id, type, state, reason_code, reason_text, transitions[], mode, learned_drop, budget}
GET  /attention/settings  ?person=  -> {modes: {type: mode}, budget_per_day, floors[], learned: {...}}
POST /attention/settings  {modes?: {type: mode}, budget_per_day?, reset_learned?: true|[types]}   (worker only)
```

Module `understudy_engine/attention/routes.py` exports `router` and `enabled()`. **For ENGINE-DATA** (`api/flags.py`, one line): `"attention": "attention.routes"` in `EXTENSIONS`; the flag is then `UNDERSTUDY_X_ATTENTION`, and `api/app.py` needs no other change.

### 8.2 Desktop (`apps/desktop/src/main/attention/**`)

An adapter polls `GET /attention/next` (about every 2 s while active, 15 s while away), renders through injected ports, and holds the local one-voice lock. It never edits `tray.ts`, `toast.ts` or `hud.ts`; the hooks it needs from DESKTOP-2 are listed in the message to the lead.

**One-voice lock protocol (agreed with CUE-UX)**: a `VoiceLock` object owned by the adapter and injected into the Cue controller.
`acquire(owner, priority, ttlMs) -> boolean`, `release(owner)`, `holder()`. Priorities: safety 3, decision (question card, approval toast) 2, cue 1, glance 0. Acquire succeeds when the lock is free, its TTL has run out, or the requester's priority is strictly higher (the holder's `onPreempt` is called and it must hide at once). A TTL is mandatory, so a crash cannot wedge the lock. The Cue controller acquires before it draws a cue or question and releases when it hides; the adapter acquires before it draws any toast. The engine keeps the same facts in the store (an item on screen holds the lock until its display time or its feedback) so both sides agree after a restart.

### 8.3 Dashboard (for DASH-LIVE; no edits to `apps/dashboard` from this track)

A settings panel reading and writing `/attention/settings` (a mode per type in four plain choices, a budget slider, "Reset what Understudy learned"), a "Today" strip from `/attention/digest?kind=now` and per-item "Why?" links to `/attention/why`. Banners come from `badges.waiting` and `digest_ready`.

## 9. Evaluation (plan in `evals/attention/PLAN.md`)

A simulated workday generator (synthetic, badged) over the personas' schedules and the presence model, with event streams at the real producers' typical rates. The router is compared with two baselines: **B1** show everything immediately and **B2** one daily digest only. Metrics each with n, split, person-level bootstrap interval and the synthetic badge: interruptions per hour in flow; share of important items seen within their window; median delay of important items; duplicate rate; missed-urgent count (must be 0 for safety); reminders per item; digest length; acceptance rate. The attention-cost model is stated before any run. Thresholds are tuned on dev seeds only. `evaluate_attention(fast=False)` is exported for the eval harness, fast mode under 60 s.

Honesty: the evaluation shows the policy behaves as designed under stated assumptions. It does not show that real people find the product natural. That test is a live check with the four teammates (n = 4) and is not run.

## 10. What is not covered

- Which window a notification appears in is the desktop's (toast, HUD); this layer decides only whether and when.
- The renderer-level look of a toast is DESKTOP-2's, under `docs/UI_DIRECTION.md`.
- A real "do not disturb" read from macOS Focus is not available to Electron without a native module; the worker's own quiet hotkey (`dnd`) stands in for it.
- Screen sharing and call detection are provided by the awareness layer's probes; if a probe is unknown the router treats the state as **not** sharing (so safety is never held) and the worker's quiet hotkey remains the override.
