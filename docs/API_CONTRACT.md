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
  "kind": "irreversible_step|outward_step|batch_result|injection_pause|shadow_mismatch",
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
  - `pooling` (ANA-9): `{ rows: [{ n_episodes, no_pooling, partial_pooling, complete_pooling, ci }], note }` (error after 0, 1, 3, 10 episodes, leave-one-person-out)
  - `policy_gate` and `skills` sections (extras from engine-analytics): free-form with `meta`; the dashboard shows them only if present.
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
