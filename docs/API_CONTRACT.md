# API contract (engine :7700, agent :7710)

Written by the lead on Sat 7 Nov 2026. **This is the sync point between the dashboard, the engine and the agent service.** The dashboard builds against fixtures that match these shapes; the engine and agent implement them. To change a shape, message the lead with `CONTRACT-CHANGE:`; the lead edits this file and tells the affected agents. Additive fields are fine without asking.

## Conventions

- JSON over HTTP on localhost. CORS: allow `http://localhost:5173` and `http://127.0.0.1:5173`.
- **Every analytic GET returns `{ "meta": AnalyticMeta, "data": ... }`.** `AnalyticMeta` = `{ origin: "real"|"synthetic"|"mixed", n: int, n_unit: "people"|"personas"|"households"|"episodes"|"days"|"decisions"|"runs", split: string|null, interval_level: 0.95, note: string|null, generated_at: ISO }`. The dashboard shows a `synthetic` badge when `origin != "real"`, and prints `n` and `split` on every chart. Intervals are `[lo, hi]`.
- Errors: HTTP 4xx/5xx with `{ "error": { "code": string, "message": string } }`. Plain, specific messages.
- IDs: person `p_<slug>`, task `t_<slug>`, routine `calc-entry-3x` style slugs, queue item `q_<ulid-ish>`.
- Time: ISO-8601 UTC strings; durations in seconds unless the key ends `_min` / `_h`.
- Mock mode (`UNDERSTUDY_MOCK=1`) must return deterministic data for every endpoint, from `data/synthetic/**` and `evals/report.json`. No endpoint may require a model call to answer.
- Files shared between engine and agent (both read/write; atomic writes; JSON): `data/queue/<id>.json` (approval queue), `data/audit.jsonl` (append-only, redacted), `data/KILL` (kill flag; presence = stop everything), `data/runs/<run_id>/` (agent run evidence).

## Engine API (port 7700)

| Method and path | Purpose | Response `data` (or body) |
|---|---|---|
| `GET /health` | liveness | `{ ok, version, mock: bool, models: {planner, fast, computer_use}, services: {engine, agent} }` (no analytic envelope) |
| `POST /events` | ingest `Event[]` (or one) | `{ accepted: int, rejected: [{index, reason}] }` |
| `GET /events?partition=real\|synthetic&person=&since=&limit=` | read | `{ events: Event[] }` |
| `GET /replay?person=&task=&speed=1..200&squeeze_idle_s=30` | replay frames | `{ duration_s, frames: [{ t_replay, event: Event, state: { task, last_cog, counts: {cog: int} } }] }` |
| `GET /packs` | list packs | `[{ id, name, summary, depth: "deep"\|"thin" }]` |
| `GET /onboarding/questions?role=` | questions for a role | `{ role, pack: { name, summary, extra_cogs: [..], risk_classes: {irreversible: [..]}, tone_defaults: {length, voice} }, questions: [{ id: "tools"\|"risky"\|"tone"\|"pace"\|"hours", prompt, kind: "multi"\|"single"\|"hours", options: [{value, label}] }] }` |
| `POST /onboarding` | `{ person?, role, answers: {tools:[..], risky:[..], tone, pace, hours:{start,end,days:[..]}} }` | `{ person, role, revision, memory_markdown, risk_classes, tone: {length, voice}, pace }` (writes the memory file; two roles must give visibly different files) |
| `GET /memory` | memory file | `{ path, revision, markdown, sections: {Preferences: [{id,text,note}], Procedure: [..], Routines: [..], Corrections: [..], "Skill state": [..], Never: [..]} }` |
| `PUT /memory` | `{ markdown, base_revision }` | `{ revision }`; **409** `{error:{code:"stale_revision", ...}}` if `base_revision` is old (the worker's edit wins on re-submit) |
| `POST /memory/forget` | `{ line_id }` | `{ revision }` (deleting a line removes it from behaviour, MEM-5) |
| `GET /memory/proposals` | rule proposals | `[{ id, rule, kind: "preference"\|"procedure", evidence_count, shadow_match: float\|null, status: "proposed"\|"active"\|"rejected", version }]`; `POST /memory/proposals/{id}/approve\|reject` |
| `GET /coach/state?person=` | Today screen | `{ task: {id, name, step: int, steps_total: int}, level: "L1"\|"L2"\|"L3"\|"L4", chip: "full"\|"small"\|"dot"\|"gone", message: string, why: string, mastery: {cog: float} }` |
| `GET /genome/{task}?person=&reference=nearest_expert\|consensus` | **work ribbon** + waterfall | `{ task, person, expert_person, expert: {segments:[{cog,t0,t1}]}, novice: {segments:[..]}, alignment: [{ i: int\|null, j: int\|null, op: "match"\|"mismatch"\|"gap_expert"\|"gap_novice", seconds: float }], waterfall: [{ label, seconds, ci: [lo,hi] }], total_gap_s: float, total_gap_ci: [lo,hi], controls: { placebo: {gap_s, ci}, null: {gap_s, ci} } }` |
| `GET /graph/transitions?task=` | **genome graph** | `{ nodes: [{id, cog, expert_dwell_s, novice_dwell_s}], edges: [{from, to, expert_freq, novice_freq, missing_for_novice: bool, planted: bool\|null}] }` |
| `GET /graph/work?person=` | **work graph** | `{ nodes: [{ id, type: "routine"\|"skill"\|"memory"\|"automation", label, size, strength: 0..1, last_seen, why: string, editable: bool, memory_line_id: string\|null }], links: [{ a, b, kind: "related"\|"combined", weight }] }` |
| `GET /hazard/{person}` | stuck prediction | `{ series: [{t, p}], model: {log_loss, brier, ece, ci_log_loss:[lo,hi]}, baselines: {base_rate: {log_loss, brier, ece}, time_since_progress: {log_loss, brier, ece}}, calibration: [{p_mean, freq, n}], false_alarms_per_hour: float, split: "leave-one-person-out" }` |
| `POST /routines/detect` | run the finder | `{ proposals: int, precision: float\|null, recall: float\|null }` |
| `GET /routines` | proposals and routines | `[Routine]` (below) |
| `POST /routines/{id}/consent` | `{ mode: "not_now"\|"never"\|"shadow"\|"approval"\|"unattended", irreversible_unattended: [..], typed_confirm: string }` | updated `Routine` (model-driven irreversible opt-in needs `typed_confirm` equal to the routine id; otherwise 422) |
| `POST /routines/{id}/shadow` | record or run a shadow comparison | `{ runs, matches, wilson_lower, rung, promoted: bool }` |
| `GET /queue?status=pending\|all` | approvals | `[QueueItem]`; `POST /queue/{id}/approve\|reject` -> `QueueItem` |
| `GET /presence?person=` | **heatmap** | `{ bins: [{ dow: 0..6, slot: 0..95, p, lo, hi }], idle_capacity_h: {mean, lo, hi}, quiet_hours: {start, end, days}, forecast: [{ d_min: int, survival: float }], decision_threshold: float }` |
| `PUT /presence/quiet_hours` | `{ start: "22:00", end: "06:00", days: [..] }` | the new `quiet_hours` |
| `POST /offhours/decide` | `{ person, now?, d_min, gain, loss }` | `{ go: bool, survival, threshold, reason: string, locked: bool }` |
| `GET /offhours/report?since=` | morning report | `{ since, ran: [{routine, run_id, outcome, minutes, tier}], queued: [QueueItem ids], failed: [{routine, reason}], yielded: [{routine, at}] }` |
| `GET /eval/report` | contents of `evals/report.json` | `{ generated_at, mock, sections: { deficit_recovery, null_placebo, hazard, ope, routing, ski_rental, presence, agent_claims, redteam, study, limitations: [{id, text, severity}] } }` (each section carries its own `meta`) |
| `GET /audit?limit=` | redacted audit lines | `[{ t, actor: "human"\|"agent"\|"system", kind, routine, run_id, tier, outcome, note }]` |
| `POST /kill` / `POST /kill/clear` | kill switch | `{ killed: bool, at }` (writes `data/KILL`, and calls the agent service `/kill`) |

### Routine (spec 6.5 plus proposal copy)

```json
{ "id": "calc-entry-3x", "role": "benefits-processor", "title": "Enter the household into three calculators",
  "status": "proposed|declined|never|shadow|approval|unattended",
  "episodes": 14, "minutes_per_week": 96, "cv": 0.18, "judgement_share": 0.07,
  "value": { "hours_saved": [3.1, 5.2], "net_gbp": [41, 90], "confidence": 0.82 },
  "touches": ["gov.uk check", "turn2us", "case note"], "never": ["submit"],
  "consent": { "mode": "shadow", "irreversible_unattended": [], "typed_confirm": false },
  "rung": "A0", "shadow": { "runs": 0, "matches": 0, "wilson_lower": 0.0 },
  "build_timing": { "rule": "ski-rental", "buy_after_runs": 3, "regret_vs_hindsight": 1.2 },
  "skill_gate": { "eligible": true, "reason": "mastery L4 on ENTER_HOUSEHOLD" },
  "proposal": { "what": "...", "how_often": "about 14 times in 3 weeks", "touches": ["..."], "never": ["..."] },
  "bundle": "data/routines/calc-entry-3x/steps.json" }
```

### QueueItem (file `data/queue/<id>.json`)

```json
{ "id": "q_01", "created_at": "ISO", "routine_id": "calc-entry-3x|null", "run_id": "r_01",
  "kind": "irreversible_step|outward_step|batch_result|injection_pause|shadow_mismatch|browser_step",
  "title": "Submit case note CN-2041", "summary": "One line, plain.",
  "risk_class": "irreversible|outward|normal",
  "evidence": { "screenshots": ["data/runs/r_01/s3.png"], "extracted": {}, "expected": {}, "diff": [], "tier_log": [{ "step": 3, "tier": 1 }] },
  "status": "pending|approved|rejected|expired", "decided_at": null, "decided_by": null }
```

## Additions agreed on 7 Nov (dashboard needs; all additive, the dashboard tolerates absence)

- `GET /kill` -> `{ killed: bool, at: ISO|null }` (engine-data; reads `data/KILL`).
- `GET /runs/{run_id}/{file}` serves evidence files from `data/runs/<run_id>/` (png, json only; path traversal refused) so queue screenshots render (engine-data).
- `GET /identity` -> `{ person, role }` (plain JSON; engine-handoff; the engine owns the id, created by onboarding). The desktop app and the browser extension adopt it when it exists (falling back to their own generated id only before onboarding). `GET /memory` also carries `person` and `role`.
- `POST /routines/{id}/recording` accepts a draft step bundle matching `packages/schema/recording.schema.json` (example `packages/schema/examples/recording.example.json`), stores it under `data/routines/<id>/recording.json`, returns `{ steps, accepted }` (engine-handoff). The extension tolerates 404/405 until it exists.
- **Live coach (engine-data, landed 7 Nov).** `GET /coach/next?person=P[&now=ISO][&ask=1][&dry=1][&tone=short|detailed]` -> `{ meta, data: CoachDecision }`; `dry=1` changes nothing (use it for passive refreshes), polling advances the dignity gate so poll at a steady pace (about 2 to 3 s), `now` is for replays. `CoachDecision = { person, t, action: "silent"|"nudge"|"annotate"|"takeover_offer", message (one plain line; empty when silent except at L3 where it is the text behind the dot), why, target: { zone, label_hint, role_hint, site } | null (a ring only for annotate/takeover_offer), missed: [step ids], confidence, level: "L1".."L4", chip: "full"|"small"|"dot"|"gone", decision_id: "d_<12 hex>"|null (set only when the coach acted and it was recorded), task_id, step, trigger: "expert_policy"|"stuck"|"ask"|null, reason_codes: [...], gate: { consecutive, reason }, p_stuck, p_source: "hazard"|"heuristic", candidate: { action, message, why, target, missed, trigger, step } | null (what it WOULD say if the gate opened; for the Today screen), mastery: { COG: 0..1 } }`. Reason codes: acting (policy_violation, critical_step_missed, gate_act, stuck_signal, asked, issue_repeated, worker_asked), silent (on_track, gate_wait_signals, gate_cooldown, gate_unsure, unsure_away, already_prompted, level_3, level_4, no_active_task, no_events, no_pack), context (implicit_task, study_mode, study_post_test, study_off). `POST /coach/feedback { decision_id, outcome: "followed"|"dismissed"|"repeated"|"undone"[, now] }` -> `{ decision_id, outcome, recorded, event_id, implicit, skill: { COG: { level, chip, mastery } } }` (404 `no_such_decision`, 422 `bad_outcome`; actor header `worker`). Study mode: `GET /study/mode`, `POST /study/mode { person, block: "train"|"post_test"|"off", skill_on, level, steps_off?, participant?, block_no? }`, `POST /study/mode/clear` (loopback, actor header `worker`, app origin); in `train` the coach acts only for `skill_on`, in `post_test`/`off` it is silent with chip gone.
- `GET /genome/{task}` also carries `consequences: [{ step, p_error, mean_error_gbp, n, source, ... }]` and `consequences_meta` (read from `evals/cases/skip_consequences.json`; absent when the file is absent). RECONCILE: p_error 0.103 [0.078, 0.13], mean error 291.89 pounds a month when wrong, n 200. CHECK_CLIFF has no p_error (the panel does not change today's figure; the cost is a missed warning), so it carries the file's own fields (households near an edge, share near, material impact) and a plain `note`.
- Genome gaps: the dashboard reads a gap from `alignment[].i` or `.j` being `null`; `seconds` = seconds lost for that column. Op names stay as documented.
- `presence.forecast[]` may carry `lo` and `hi` (interval). `dow` 0 = Monday.
- `Routine.value.horizon_weeks` (int, default 4), `Routine.driver` (`"compiled"` | `"model"`), `Routine.irreversible_classes` (string[]); a model-driven routine with irreversible classes needs the typed confirmation, a compiled one needs one tap (engine-handoff).
- **`GET /eval/report` section shapes** (the eval harness writes these into `evals/report.json`; every section also has `meta: AnalyticMeta`):
  - `deficit_recovery`: `{ rows: [{ deficit, injected_price_s, recovered_price_s, ci: [lo,hi], precision, recall }], overall: { precision, recall } }`
  - `null_placebo`: `{ real: {gap_s, ci}, placebo: {gap_s, ci}, null: {gap_s, ci} }`
  - `hazard`: `{ model: {log_loss, brier, ece, ci_log_loss}, baselines: { base_rate: {...}, time_since_progress: {...} }, calibration: [{p_mean, freq, n}], false_alarms_per_hour, split }`
  - `ope`: `{ true_value, estimators: [{ name: "naive"|"ips"|"snips"|"dr", value, ci: [lo,hi] }] }`
  - `routing`: `{ alpha, curve: [{ coverage, risk, ci }], held_out_error, held_out_ci, bound_held: bool, expert_minutes_per_case }`
  - `ski_rental`: `{ rows: [{ rule: "break-even"|"predictions", lambda?, regret, ci: [lo,hi] }], hindsight_regret: 1.0 }`
  - `presence`: `{ reliability: [{ p_mean, freq, n }], brier, baselines: { fixed_overnight: {...}, idle_5min: {...} }, interruption_rate, cap, idle_time_used }`
  - `agent_claims`: `{ reliability: [{ p_mean, freq, n }], brier, base_rate }`
  - `redteam`: `{ rows: [{ ablation: "all_on"|"no_<layer>"|"all_off", attack_success, attack_ci: [lo,hi], task_success, task_ci: [lo,hi] }], false_pause_rate, false_pause_ci }`
  - `study`: `{ rows: [{ participant, unassisted_before_s, unassisted_after_s }], mean_change_s, mean_change_ci, n: 4 }` (empty until the live study has run; the page says so)
  - `routines`: `{ rows: [{ persona, planted, found, precision, recall }], overall: { precision, recall } }` (meta: origin synthetic, n_unit "personas")
  - `pooling` (ANA-9): `{ rows: [{ n_episodes, no_pooling, partial_pooling, complete_pooling, ci, no_pooling_minus_partial?, complete_pooling_minus_partial? }], note, datasets?, limitations?, caveats? }` (predictive log loss in nats per trial after 0, 1, 3, 10 episodes, leave-one-person-out; `ci` is the interval of the partial-pooling value; `*_minus_partial` is the excess loss of the alternative with its own interval, positive means partial pooling is better). Honest result: on the personas partial and complete pooling are tied; on apprentice deficit presence complete pooling is clearly worse.
  - `routing` is grounded in the sandbox households (headline) with the synthetic generator under `secondary`; `bound_held` means the lower end of the held-out Clopper-Pearson interval does not exceed alpha.
  - `skills` carries `learners` (3 learners x 30 cases) beside the persona result.
  - `policy_gate` and `skills` sections (extras from engine-analytics): free-form with `meta`; the dashboard shows them only if present.
  - `agent_runs` (added 7 Nov): `{ clean: { n, pass, wilson, mean_s, tiers }, robust: { n, pass, wilson, mean_s, tiers, injected: [...] }, discrepancies_flagged: {n, of}, false_claims, live?: { n, pass, wilson, tiers, false_claims, cost_usd_est, note } }` built from `data/eval/agent_benefits_20.json`, `agent_benefits_20_robust.json` and (when it exists) `data/eval/agent_live_runs.json`; the live block is clearly labelled "real model" and small n; origin synthetic, n_unit "runs".
  - `limitations`: `[{ id, text, severity: "low"|"medium"|"high" }]`
- **Envelope policy (decided 7 Nov):** the `{ meta, data }` envelope applies to the analytic GETs: `/genome/{task}`, `/graph/transitions`, `/graph/work`, `/hazard/{person}`, `/presence`, `/routines`, `/eval/report` sections. Control-plane endpoints return plain JSON: `/health`, `/events`, `/replay`, `/packs`, `/onboarding*`, `/memory*`, `/coach/state`, `/offhours/*`, `/queue*`, `/audit`, `/kill*`, and the agent API.
  The dashboard's fixture `apps/dashboard/src/fixtures/eval-report.json` is the reference; the eval harness and the dashboard must stay in step.

## Agent API (port 7710; the dashboard calls it directly for runs)

| Method and path | Purpose | Body / response |
|---|---|---|
| `GET /health` | liveness | `{ ok, mock, supervisor: {generation, state} }` |
| `POST /run/benefits` | start the benefits workflow | `{ household_id?, household?, mode: "live"\|"cached"\|"mock", navigators?: 3 }` -> `{ run_id }` |
| `GET /run/{run_id}` | status | `{ run_id, state: "running"\|"paused"\|"done"\|"failed"\|"stopped", generation, navigators: [{ id, site, step, tier: 1\|2\|3, state }], completion: { ok: bool, missing: [..] }, false_claims: int }` |
| `GET /run/{run_id}/stream` | SSE of step events | `event: step` / `data: {navigator, step, tier, action, ok}` |
| `POST /run/{run_id}/stop` | stop within 1 s | `{ stopped: true, generation }` |
| `POST /kill` | global stop | `{ killed: true }` |
| `POST /routines/{id}/run` | run a compiled routine | `{ mode: "shadow"\|"approved"\|"background" }` -> `{ run_id }` |

## Sandbox sites (ports 7801 to 7803)

Three local calculator sites plus a case-note page, each with a clean variant and an injected-instruction variant (`?variant=injected`). Owned by the agent-core track (`services/agent/understudy_agent/sandbox_sites/`).

## Extensions API (REQ-2, targets agreed 7 Nov; all additive, flag-gated, `{meta, data}` envelope unless noted)

Flags: master `UNDERSTUDY_X=1`, or per layer `UNDERSTUDY_X_PRIVACY`, `_LOCALMODEL`, `_CALENDAR`, `_GIT`, `_PROACTIVE`, `_AGENTS`. A router is included by the engine app (or the agent server) only when importable and its flag is on; `GET /health` lists `extensions: {privacy, localmodel, calendar, git, proactive, agents}` with booleans. Writes need the actor header like all other writes.

| Method and path | Layer | Data |
|---|---|---|
| `GET /privacy/ledger?limit=` | PRV | `[{ t, purpose, schema, fields: [..], payload: {..} (exactly as sent), model, bytes }]` newest first; `POST /privacy/ledger/clear` (worker actor); `GET /privacy/summary` -> `{ calls, by_purpose: {..}, last_call, local_only_note, canary: {runs, planted, leaked} }` |
| `GET /localmodel/status` | LOC | `{ enabled, running, model: {file, size_bytes, sha_ok}, endpoint, tokens_per_s?, mode: "model"\|"rules" }`; `POST /localmodel/digest` (internal use, worker actor): `{ task: "commit_digest"\|"event_digest", items_ref }` -> digests only |
| `GET /calendar/week?person=&week=` | CAL | `{ days: [{ dow, blocks: [{ start, end, kind: "meeting"\|"focus"\|"break"\|"offscreen"\|"free", n_attendees_bucket?: "lt5"\|"5to9"\|"10plus" }] }], features: { meeting_h, focus_blocks_60, focus_blocks_90, longest_focus_min, fragmentation, back_to_back_runs, work_span_h, offscreen_h }, expert: { ...same keys }, gap: { rows: [{ feature, learner, expert, delta, ci }] } }` (no titles, names or free text) |
| `GET /calendar/suggestions?person=` | CAL | `[{ id, template, text, numbers: {..}, expert_ref: {..}, risk: "low", can_draft: bool }]` (text is reworded only from safe aggregates) |
| `GET /git/habits?person=&repo=` | GIT | `{ habits: [{ id, label, learner, expert, delta, ci, suggestion? }], digest_source: "model"\|"rules", n_commits }` |
| `GET /briefing?person=` | PRO | `{ cap: 3, generated_at, cards: [{ id, kind: "practice"\|"automate"\|"focus_block"\|"git_habit"\|"agent_result", title, why, prepared: { text?, steps?: [..], artifact_ref? }, risk_class: "normal"\|"outward"\|"irreversible", sources: [tags], expires_at, status: "ready"\|"fired"\|"dismissed"\|"stale" }] }`; `PUT /briefing/{id}/prepared` (edit; worker actor); `POST /briefing/{id}/fire` (worker only; creates an approval-queue item or an agent run, returns `{ queue_id?, run_id? }`); `POST /briefing/{id}/dismiss` |
| `GET /agents/runs?person=` (agent service :7710) | BGA | `[{ run_id, kind, mode: "foreground"\|"nightly", state, started, parent: { id, role, state, budget, spent }, children: [{ id, role, state, budget, spent, result_ref? }] }]`; `GET /agents/runs/{id}` adds `artifacts: [{ name, kind, path_ref }]` and `result`; `POST /agents/spawn { kind, params, mode }` -> `{ run_id }`; `POST /agents/runs/{id}/stop` |

Spawn kinds (v1): `programming.commit_analyst`, `programming.test_gap`, `programming.refactor_suggest`, `data.profile`, `data.chart`, `creative.weekly_summary`.

Additive fields agreed after the Clicky reuse study (K1): in `GET /agents/runs` and `/agents/runs/{id}` each child carries `lease: { ttl_s, remaining_s, steps_left, tools: [..], revoked: bool }` (a per-child tool scope with expiry, step cap and revocation; a parent revocation cascades; no site or app scope, SEC-10 still holds) and each step in the result carries `check: "verified"|"uncertain"|"failed"` (a declarative postcondition check run by code after the step; blockers beat success; an unreadable field is "uncertain"; no page text is ever echoed). `POST /agents/runs/{id}/children/{child_id}/revoke` (worker actor header) ends one child at once.

Additive details agreed with the dashboard for the extension screens (7 Nov): `GET /calendar/week` returns `expert.days` (the expert's blocks in the same shape as the learner's `days`, so the second ribbon can be drawn) next to `expert`'s feature keys; block `start`/`end` are `"HH:MM"` strings; `PUT /briefing/{id}/prepared` takes the prepared object itself as the body (`{ text?, steps? }`); `POST /briefing/{id}/dismiss` takes an optional body `{ mode: "not_now"|"never" }` and "never" must be recorded and honoured for that card kind and source; `POST /briefing/{id}/fire` is sent with actor header `worker_approval` and returns `{ queue_id?, run_id? }`; agent-service writes (spawn, stop, revoke) take actor header `worker`; agent result steps are `result.steps[].{ step, check }` where `check` is `verified|uncertain|failed`.

## Extensions added for REQ-5, REQ-6 and REQ-7 (7 Nov 2026)

All behind flags (`UNDERSTUDY_X_<LAYER>` or `UNDERSTUDY_X`); handlers answer 404 `extension_off` when off. Responses use the `{meta, data}` envelope unless stated. No route ever carries free text from a screen, a model or a worker, and no frame or audio is ever stored.

### Awareness (engine, :7700; flag `UNDERSTUDY_X_AWARENESS`)
- `POST /awareness/events`: one event or a list of at most 500 (schema `packages/schema/awareness.schema.json`, enums and numbers only). Loopback only; Origin `app://` or localhost if any. Reply `{accepted, duplicates, rejected:[{index, reason}]}` (reason names a rule and path, never a value).
- `GET /awareness/summary?person=&origin=&since=&until=`; `GET /awareness/windows?person=&origin=&since=&until=&limit=` -> `{windows, loose_glances}`; `GET /awareness/columns` -> `{columns, span_s: 30}`; `POST /awareness/clear {person?, origin?}` (worker actor).
- `meta.n_unit` is "windows". Hazard features: `awareness.features.awareness_features`, `features_by_bin`, `AWARENESS_COLUMNS` (25 `aw_*` columns; the stuck trigger is deliberately not a column).

### Glance (agent service, :7710; wraps the awareness handler)
- `POST /glance` request `{frame_b64, gates:{consent, denylisted_app, secure_input, unattended}, trigger: stuck|loop|hotkey|periodic, app_kind?, width, height}`. Source is fixed `real_screen` server-side and never read from the request; any Origin other than `app://` or `file://` is refused.
- Replies: `200 {ok:true, result, model, latency_ms, cost_usd_est?, ledger_id, mock}`; `200 {ok:false, blocked_reason}` for a closed gate (unattended, secure_input, denylisted_app, no_consent) or `output_rejected`; `403` or `422 {error:{code,message}}`; `502 model_failed`; `503 ledger_unavailable`. The route must not log bodies.
- Closed answer (purpose `awareness.glance`): `app_kind` browser|spreadsheet|email|code_editor|terminal|chat|other; `task_phase` idle|reading|searching|entering|comparing|reviewing|submitting|waiting|unknown; `blocker` none|unclear_next_step|cannot_find_control|error_message|unexpected_state|waiting_for_load|needs_information|permission_prompt|unknown; `confidence` 0..1; optional `box_2d` [ymin,xmin,ymax,xmax] on 0..1000.

### Cue grounding and models (agent service; the MODELS track)
- `POST /cue/ground` request `{frame:{mime:"image/jpeg", b64, width, height}, menu:[{id,label}] (2..6), app_kind?, tier_hint?: "lite"|"full", purpose:"cue.ground", gates:{...}}`; response `{available:[ids], chosen: id|null, box_2d:[y0,x0,y1,x1]|null, confidence, source:"vision", model_tier, latency_ms}`. DOM grounding in the desktop returns the same shape with `source:"dom"`.
- `GET /models/status` -> `{roles:[{role, provider, model_id, fallback, health, breaker, last_latency_ms, calls, cost_usd_est}], prices_assumed, ledger_coverage, bakeoff|null}`. Never a key.

### Privacy additions (engine; flag `UNDERSTUDY_X_PRIVACY`)
- Image rows in `GET /privacy/ledger` (merged, one per call): `{kind: glance|point|verify|live_frame, source: real_screen|sandbox, status: ok|blocked, reason?, sha8, bytes, width, height, provider, model, latency_ms, tokens, cost_estimate_usd}`; `payload` is null on blocked rows. Summary gains `images:{sent, blocked, blocked_by_reason, sent_by_source, bytes_sent}`.
- `POST /privacy/ledger/live` (+ `/result`): metadata for Live frame batches from the desktop main process (body at most 4096 bytes; loopback and worker actor; no Origin); gate precedence unattended+real_screen, secure input, denylisted app, no consent.
- Direct (metadata-only) rows are written for every provider call regardless of flags (`record_direct`; no prompt text, page text, images or replies).

### Cue and Growth (engine; flag `UNDERSTUDY_X_CUE`; starting contract, CUE-ENGINE finalises)
- `GET /cue/next?person=&dry=&voice_ok=0|1` -> `{meta, data: CueDecision}` with `kind` none|confirm|cue|ask|offer, `episode_id`, `tier` 1..4|null, `step{id,label,reason_id}`, `target{box_2d,source dom|vision|none,confidence}`, `options[{id,label}]`, `say{chip (<=40 chars), whisper (<=8 words)|null}`, `why{path_prob, margin, p_stuck, mastery, level, reasons[]}`, `budget_left`, `cooldown_s`, `source model|rule`, plus additive `new`, `question{type,text}`, `expires_in_s`, `retrieval`, `ground_wanted`.
- `POST /cue/feedback {episode_id, event: shown|accepted|dismissed|answered|resolved|abandoned|know_this, answer_id?, seconds?}`; `GET /cue/ledger?person=`; `DELETE /cue/ledger` (worker); `POST /cue/quiet {minutes}`; `GET /growth?person=&skill=` (independence score with components, intervals, n, trend, offloaded-work counts; delegated and automation streams never enter the score).
- **`step.target` (CUE-ENGINE-2, 7 Nov).** Every Cue decision that names a step (kinds `confirm`, `cue`, `ask`, `offer`, including the persisting polls of one episode; `step` is null on kind `none`) carries `step = {id, label, reason_id, reason_text, target}`, all five keys always present. `reason_text` is the one-line reason (12 words or fewer) and is non-null for every step of the benefits-processor, programmer and data-analyst packs (a test loops over all of them). `target` is `{zone, label_hint, role_hint}` or `null`: where on the screen the control for the step is, so the desktop's DOM tracker can follow a ring that moved (`CueGrounder.recheck`: ask the extension for `zone`, as `RectWant.zone` in `ext_rect.schema.json`). It comes from the same pack mapping the coach uses for the same step (Cue calls `coach.messages.target_for`; it keeps no rules of its own), so a Cue ring and a coach ring for one step land on the same zone. `zone` is a zone id from the pack's cog mapping (`^[a-z][a-z0-9_]{1,30}$`, never a selector or page text); `label_hint` is the pack's own words for the control (80 characters or fewer); `role_hint` is `button`, `textbox`, `select` or `region` (or the pack's own lowercase role word, pattern `^[a-z][a-z0-9_-]{0,31}$`). `null` means the pack's mapping has no zone for the step: the cue is text only and there is nothing to track. Not to be confused with the decision's own `target` (`{box_2d, source, confidence}`, the box the ring is drawn at), which is unchanged. The coach's `site` and `fallback_zones` are not included. Example for step `cliff_a` of the benefits-processor pack: `{"id": "cliff_a", "label": "Check cliff edges (A)", "reason_id": "why.cliff", "reason_text": "A figure near a limit can flip the answer.", "target": {"zone": "cliff_button", "label_hint": "Check cliff edges", "role_hint": "button"}}`. Closed schema: `packages/schema/cue_step.schema.json` (`additionalProperties: false`); examples: `packages/schema/examples/cue.decisions.example.json`, written by `python -m understudy_engine.cue.make_examples [decisions]`.
- **Closed schemas for the Cue answers (7 Nov).** `packages/schema/cue_decision.schema.json` (`{meta, data: CueDecision}` from `GET /cue/next`: `#/$defs/CueEnvelope`; the example file is a map of fixture walks, each poll a decision plus the fixture clock `t`), `cue_growth.schema.json` (`GET /growth`, also the per-skill example), `cue_ledger.schema.json` (`GET /cue/ledger`; its `LedgerRow` is a copy of `assist_ledger.schema.json`). All objects are closed (`additionalProperties: false`); every enum is the engine's own list (`cue/types.py` KINDS, SOURCES, REASONS; `cue/vocab.py` QUESTIONS; `cue/score.py` weights and variants), and `tests/cue/test_schemas.py` keeps them equal and validates live route output against them. The four `cue.*.example.json` files are registered in `packages/packs/validate.py` `EXAMPLE_SCHEMAS`.

### Evidence (engine; flag `UNDERSTUDY_X_EVIDENCE`; EVIDENCE track finalises)
- `GET /evidence/packet?person=&case=`; `POST /evidence/explain {person, case?, question?}`: a closed-schema packet and an explanation whose every number is verified against the packet, with `source` template|local|cloud and the verdict of the provenance check.

## Tasks API (agent service :7710; Track T, 8 Nov 2026; additive, plain JSON, no envelope)

The dashboard calls it as `/agent/<path>` (the dev proxy strips `/agent` and adds the per-boot token); the desktop calls `http://127.0.0.1:7710/<path>`. Doc: `docs/TASKS.md`. Tests: `services/agent/tests/tasks/`.

**ROW** (list, detail, SSE, POST results): `{ task_id: "tk_8f3a1c2e", title (<=60 chars, the worker's own first words, code-cut and redacted), route: "answer"|"browser"|"desktop"|"claude_agent"|"unclear", source: "typed"|"voice", state: "planning"|"waiting_consent"|"running"|"done"|"stopped"|"failed", attended: bool, latest: string|null, steps_done: int, result: string|null (one line <=140), reason: string|null, cost_usd: number|null (what the Claude CLI reported the task cost, US dollars; null for other routes), started: ISO, finished: ISO|null, open: {kind: "folder"|"file", path}|null, needs_consent: Card|null, question: {text, options: [{id, label}]}|null }`. **Card**: `{ kind: "claude_agent"|"browser", scope_text, can: [..], cannot: [..], folder: string|null, command_hash: string|null (12 hex), cost_note: string|null, max_minutes: int, max_budget_usd: number|null (the spend limit pinned on the card, 0.5 to 20; null on a browser card), buttons: { allow: "Allow for this task", decline: "Not now", more: [{id: "everything", label: "Allow everything for this task"}] } }` (`more` is empty on a browser card).

| Method and path | Who | Result |
|---|---|---|
| `POST /tasks` `{text 1..4000, source: "typed"\|"voice"}` | actor `worker`, `worker_approval` or `voice` | 201 `{task_id, route, summary, needs_consent, question}` |
| `GET /tasks` | any | `ROW[]`, newest first, at most 200 |
| `GET /tasks/{id}` | any | ROW + `steps: string[]` (short plain lines, at most 200) + `answer: string\|null` (inline answer, route answer) |
| `GET /tasks/events` | any | SSE: `snapshot {tasks: ROW[20]}`, then `task_started`, `task_progress`, `task_finished` (data = ROW), `heartbeat {t}` every 10 s |
| `POST /tasks/{id}/consent` `{choice: "allow"\|"everything"\|"decline", max_minutes?: 1..120}` | actor `worker_approval` + per-boot token (release route) | ROW; 409 `not_waiting` / `not_offered` / `command_changed`; 429 `too_many_tasks`; 423 `kill_switch_set` |
| `POST /tasks/{id}/answer` `{option_id}` | `worker`, `worker_approval`, `voice` | ROW (the chosen route still gets its own card) |
| `POST /tasks/{id}/stop` | `worker`, `worker_approval`, `voice`; no token (stop route) | ROW |
| `POST /tasks/{id}/open` | `worker`, `worker_approval` | `{opened: true}`: `open -R` on the task's own recorded path; executes nothing |
| `GET /skills[?refresh=1]` | any | `{use_claude_skills, off, max_minutes, max_budget_usd, skills: [{name, description, source: "claude"\|"plugin"\|"knack", enabled}]}` |
| `POST /skills/settings` `{use_claude_skills?, off?, max_minutes?, max_budget_usd? (0.5 to 20, default 2)}` | `worker`, `worker_approval` | the same listing as `GET /skills` |

Errors `{error:{code,message}}`: `bad_body` 422, `kill_switch_set` 423, `too_many_tasks` 429 (3 running, 20 waiting), `no_such_task` 404, `nothing_to_open` 404, `not_waiting` 409, `write_refused` 403 (a non-worker actor), `token_required` / `token_invalid` 403. Events: a card or a question arrives as `task_progress` with `state: "waiting_consent"`. Python: `understudy_agent.tasks.submit_task(text, source="voice")`.
