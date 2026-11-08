// Shapes follow docs/API_CONTRACT.md exactly. Additive fields are allowed by the contract,
// so every consumer must tolerate unknown keys.

export type Interval = [number, number];

export interface AnalyticMeta {
  origin: "real" | "synthetic" | "mixed";
  n: number;
  /** Open: services also send "commits", "decisions", "runs" and others. */
  n_unit: "people" | "personas" | "households" | "episodes" | "days" | (string & {});
  split: string | null;
  interval_level: number;
  note: string | null;
  generated_at: string;
}

export interface Analytic<T> {
  meta: AnalyticMeta;
  data: T;
}

export interface Health {
  ok: boolean;
  version: string;
  mock: boolean;
  models?: { planner?: string; fast?: string; computer_use?: string };
  services?: { engine: boolean; agent: boolean };
  /** Which REQ-2 layers are switched on. Absent means none. */
  extensions?: Partial<Record<ExtensionName, boolean>>;
}
/** Agent service health. Its own `extensions` map carries the `agents` flag. */
export interface AgentHealth { ok: boolean; mock?: boolean; extensions?: Partial<Record<ExtensionName, boolean>> }

/* -- Genome ---------------------------------------------------------------- */
export interface CogSegment {
  cog: string;
  t0: number;
  t1: number;
}
export type AlignOp = "match" | "mismatch" | "gap_expert" | "gap_novice";
export interface AlignCol {
  i: number | null;
  j: number | null;
  op: AlignOp;
  seconds: number;
}
export interface WaterfallStep {
  label: string;
  seconds: number;
  ci: Interval;
}
export interface Genome {
  task: string;
  person: string;
  expert_person: string;
  expert: { segments: CogSegment[] };
  novice: { segments: CogSegment[] };
  alignment: AlignCol[];
  waterfall: WaterfallStep[];
  /** Group figure: mean seconds lost per case across all novices. The ribbon shows one case. */
  total_gap_s: number;
  /** additive, optional: seconds lost in the single case shown in the ribbon, and its episode id */
  person_gap_s?: number;
  episode?: string;
  /** additive, optional: what skipping a step costs in wrong answers, from the sandbox oracle */
  consequences?: { step: string; p_error: number; mean_error_gbp: number; n: number; source?: string }[];
  total_gap_ci: Interval;
  controls: {
    placebo: { gap_s: number; ci: Interval };
    null: { gap_s: number; ci: Interval };
  };
}

export interface TransitionNode {
  id: string;
  cog: string;
  expert_dwell_s: number;
  novice_dwell_s: number;
}
export interface TransitionEdge {
  from: string;
  to: string;
  expert_freq: number;
  novice_freq: number;
  missing_for_novice: boolean;
  /** additive, optional: only the novice takes this move */
  extra_for_novice?: boolean;
  planted: boolean | null;
}
export interface Transitions {
  nodes: TransitionNode[];
  edges: TransitionEdge[];
}

export interface ReplayFrame {
  t_replay: number;
  event: { type: string; t: string; target?: { role?: string } };
  /** `task` and `last_cog` may be null; show a dash. */
  state: { task: string | null; last_cog: string | null; counts: Record<string, number> };
}
export interface Replay {
  duration_s: number;
  frames: ReplayFrame[];
}

/* -- Work graph ------------------------------------------------------------- */
export type WorkNodeType = "routine" | "skill" | "memory" | "automation";
export interface WorkNode {
  id: string;
  type: WorkNodeType;
  label: string;
  size: number;
  strength: number;
  last_seen: string;
  why: string;
  editable: boolean;
  memory_line_id: string | null;
}
export interface WorkLink {
  a: string;
  b: string;
  kind: "related" | "combined";
  weight: number;
}
export interface WorkGraph {
  nodes: WorkNode[];
  links: WorkLink[];
}

/* -- Presence --------------------------------------------------------------- */
export interface PresenceBin {
  dow: number;
  slot: number;
  p: number;
  lo: number;
  hi: number;
}
export interface QuietHours {
  start: string;
  end: string;
  days: number[];
}
export interface Presence {
  bins: PresenceBin[];
  idle_capacity_h: { mean: number; lo: number; hi: number };
  quiet_hours: QuietHours;
  /** `lo` and `hi` are additive and optional: a 95% band on the survival estimate. */
  forecast: { d_min: number; survival: number; lo?: number; hi?: number }[];
  decision_threshold: number;
}

/* -- Routines and queue ------------------------------------------------------ */
export type RoutineStatus = "proposed" | "declined" | "never" | "shadow" | "approval" | "unattended";
export type Rung = "A0" | "A1" | "A2" | "A3";
export type ConsentMode = "not_now" | "never" | "shadow" | "approval" | "unattended";
export interface Routine {
  id: string;
  role: string;
  title: string;
  status: RoutineStatus;
  episodes: number;
  minutes_per_week: number;
  cv: number;
  judgement_share: number;
  value: { hours_saved: Interval; net_gbp: Interval; confidence: number; /** additive, optional: the forecast period behind hours_saved */ horizon_weeks?: number };
  touches: string[];
  never: string[];
  consent: { mode: string; irreversible_unattended: string[]; typed_confirm: boolean | string };
  rung: Rung;
  shadow: { runs: number; matches: number; wilson_lower: number };
  build_timing: { rule: string; buy_after_runs: number; regret_vs_hindsight: number };
  skill_gate: { eligible: boolean; reason: string };
  proposal: { what: string; how_often: string; touches: string[]; never: string[] };
  bundle: string;
  /** Additive, optional: how the routine is driven; model-driven routines need typed confirmation. */
  driver?: "compiled" | "model";
  /** Additive, optional: action classes in this routine that cannot be undone. */
  irreversible_classes?: string[];
}

export interface QueueItem {
  id: string;
  created_at: string;
  routine_id: string | null;
  run_id: string;
  kind: "irreversible_step" | "outward_step" | "batch_result" | "injection_pause" | "shadow_mismatch";
  title: string;
  summary: string;
  risk_class: "irreversible" | "outward" | "normal";
  evidence: {
    screenshots: string[];
    extracted: Record<string, unknown>;
    expected: Record<string, unknown>;
    diff: { field: string; expected: string; got: string }[] | unknown[];
    tier_log: { step: number; tier: number }[];
  };
  status: "pending" | "approved" | "rejected" | "expired";
  decided_at: string | null;
  decided_by: string | null;
}

export interface OffhoursReport {
  since: string;
  ran: { routine: string; run_id: string; outcome: string; minutes: number; tier: number }[];
  queued: string[];
  failed: { routine: string; reason: string }[];
  yielded: { routine: string; at: string }[];
}

export interface AuditLine {
  t: string;
  actor: "human" | "agent" | "system";
  kind: string;
  routine: string | null;
  run_id: string | null;
  tier: number | null;
  outcome: string;
  note: string;
}

export interface KillState {
  killed: boolean;
  at: string | null;
}

/* -- Memory, onboarding, coach ------------------------------------------------ */
export interface MemoryLine {
  id: string;
  text: string;
  note: string | null;
}
export type MemorySectionName = "Preferences" | "Procedure" | "Routines" | "Corrections" | "Skill state" | "Never";
export interface Memory {
  path: string;
  revision: number;
  markdown: string;
  sections: Record<string, MemoryLine[]>;
}
export interface RuleProposal {
  id: string;
  rule: string;
  kind: "preference" | "procedure";
  evidence_count: number;
  shadow_match: number | null;
  status: "proposed" | "active" | "rejected";
  version: number;
}

export interface Pack {
  id: string;
  name: string;
  summary: string;
  /** deep: built and validated (benefits processor); standard: a full pack (data analyst, programmer); thin: a starter. */
  depth: "deep" | "standard" | "thin";
}
export interface OnboardingQuestion {
  id: "tools" | "risky" | "tone" | "pace" | "hours";
  prompt: string;
  kind: "multi" | "single" | "hours";
  /** additive, optional: one plain sentence on why this is asked */
  why?: string;
  /** additive, optional: only for the hours question */
  default_hours?: { start: string; end: string; days: (string | number)[] };
  options: { value: string; label: string; /** additive: pre-selected */ default?: boolean }[];
}
export interface OnboardingQuestions {
  role: string;
  pack: {
    name: string;
    summary: string;
    extra_cogs: string[];
    risk_classes: { irreversible: string[]; outward?: string[] };
    tone_defaults: { length: string; voice: string };
  };
  questions: OnboardingQuestion[];
}
export interface OnboardingAnswers {
  tools: string[];
  risky: string[];
  tone: string;
  pace: string;
  hours: { start: string; end: string; days: number[] };
  /** Optional consent to record when the worker is active (times only). Never pre-selected. */
  capture?: boolean;
}
export interface OnboardingResult {
  person: string;
  role: string;
  revision: number;
  memory_markdown: string;
  risk_classes: string[] | { irreversible: string[] };
  tone: { length: string; voice: string };
  pace: string;
}

export interface CoachState {
  /** additive: the engine's id for the worker, used for GET /coach/next */
  person?: string;
  task: { id: string; name: string; step: number; steps_total: number };
  level: "L1" | "L2" | "L3" | "L4";
  chip: "full" | "small" | "dot" | "gone";
  message: string;
  why: string;
  mastery: Record<string, number>;
}

/* -- Evidence --------------------------------------------------------------- */
export interface Hazard {
  series: { t: number | string; p: number }[];
  model: { log_loss: number; brier: number; ece: number; ci_log_loss: Interval };
  baselines: {
    base_rate: { log_loss: number; brier: number; ece: number };
    time_since_progress: { log_loss: number; brier: number; ece: number };
  };
  calibration: { p_mean: number; freq: number; n: number }[];
  false_alarms_per_hour: number;
  split: string;
  /** additive, optional: plain-language caveats the engine attaches to this result */
  caveats?: string[];
}

export interface Limitation {
  id: string;
  text: string;
  severity: "high" | "medium" | "low" | string;
  /** additive, optional: which section of the report the limit belongs to */
  source?: string;
}

/** Evidence report sections. The contract fixes the section names; their inner shapes are
 *  owned by the eval track, so the dashboard reads them defensively. */
export interface EvalReport {
  generated_at: string;
  mock: boolean;
  /** Additive: one row per section the eval track knows about, with its status and why it has not run. */
  evidence_map?: { section: string; title: string; status: string; origin: string; n: number | null; n_unit: string; label: string | null; reason: string | null }[];
  git_rev?: string;
  sections: {
    deficit_recovery?: EvalSection<Record<string, unknown>>;
    routines?: EvalSection<Record<string, unknown>>;
    null_placebo?: EvalSection<Record<string, unknown>>;
    hazard?: EvalSection<Record<string, unknown>>;
    ope?: EvalSection<Record<string, unknown>>;
    routing?: EvalSection<Record<string, unknown>>;
    ski_rental?: EvalSection<Record<string, unknown>>;
    presence?: EvalSection<Record<string, unknown>>;
    agent_claims?: EvalSection<Record<string, unknown>>;
    redteam?: EvalSection<Record<string, unknown>>;
    study?: EvalSection<Record<string, unknown>>;
    limitations?: Limitation[];
  };
}
export interface EvalSection<T> {
  meta: AnalyticMeta;
  [k: string]: unknown;
  data?: T;
}

/** GET /coach/next: the live coach brain. Rule-based: the dignity gate and the level engine decide. */
export type CoachAction = "silent" | "nudge" | "annotate" | "takeover_offer";
export interface CoachCandidate {
  action: CoachAction;
  message: string;
  why: string;
  target: CoachTarget | null;
  missed?: unknown[];
  trigger?: string | null;
  step?: number | null;
}
export interface CoachTarget {
  zone?: string;
  label_hint?: string;
  role_hint?: string;
  site?: string;
}
export interface CoachDecision {
  person?: string;
  t?: string;
  action: CoachAction;
  /** Empty when silent. At L3 it is the text behind the dot. */
  message: string;
  why: string;
  target: CoachTarget | null;
  missed: unknown[];
  confidence: number;
  level: "L1" | "L2" | "L3" | "L4";
  chip: "full" | "small" | "dot" | "gone";
  decision_id: string | null;
  task_id: string | null;
  step: number | null;
  trigger: string | null;
  reason_codes: string[];
  gate: { consecutive?: number; reason?: string };
  p_stuck: number | null;
  p_source: string | null;
  /** What the coach would say if the gate let it speak. */
  candidate: CoachCandidate | null;
  mastery: Record<string, number>;
}
export type CoachOutcome = "followed" | "dismissed" | "repeated" | "undone";

/* -- Extensions (REQ-2). Everything is flag-gated; GET /health lists which are on. ---------------------------- */
export type ExtensionName = "privacy" | "localmodel" | "calendar" | "git" | "proactive" | "agents" | "evidence" | "attention";

export type BlockKind = "meeting" | "focus" | "break" | "offscreen" | "free";
export interface CalBlock {
  /** "HH:MM", minutes since midnight, or an ISO time: all are read. */
  start: string | number;
  end: string | number;
  kind: BlockKind;
  n_attendees_bucket?: "lt5" | "5to9" | "10plus";
  /** Additive: the same times as minutes since midnight, and whether the block is usable for focus. */
  start_min?: number;
  end_min?: number;
  usable?: boolean;
}
export interface CalDay { dow: number; blocks: CalBlock[]; /** additive: the date, and whether the day was worked */ date?: string; working?: boolean }
export interface WeekFeatures {
  meeting_h?: number; focus_blocks_60?: number; focus_blocks_90?: number; longest_focus_min?: number;
  fragmentation?: number; back_to_back_runs?: number; work_span_h?: number; offscreen_h?: number;
  [k: string]: number | undefined | CalDay[];
}
export interface GapRow {
  feature: string; learner: number; expert: number; delta: number; ci: Interval;
  /** Additive: the range experts themselves span, and the engine's own verdict on the difference. */
  expert_range?: Interval; significant?: boolean;
}
export interface RibbonOp { op: "match" | "mismatch" | "gap_expert" | "gap_novice" | string; expert: string | null; learner: string | null; minutes: number }
export interface WeekRibbonDistance {
  distance: number;
  placebo?: { distance: number; ci: Interval; n_experts?: number };
  nearest_expert?: string;
  alignment?: RibbonOp[];
}
export interface CalendarWeek {
  days: CalDay[];
  features: WeekFeatures;
  /** The expert's features. `days` (the expert's blocks) is additive and optional. */
  expert: WeekFeatures & { days?: CalDay[] };
  gap: { rows: GapRow[]; interval?: string; ribbon?: WeekRibbonDistance };
  /** Additive. */
  person?: string; role?: string; group?: string; week?: string; weeks_available?: string[]; timezone?: string;
  counts?: Record<string, number>;
}
export interface CalPerson { person: string; group: string | null; role: string | null; label: string | null; weeks: string[] }
export interface CalSuggestion {
  id: string;
  template: string;
  /** Additive. */
  title?: string;
  priority?: number;
  week?: string;
  evidence_weeks?: number;
  text: string;
  numbers: Record<string, number | string>;
  expert_ref: Record<string, number | string>;
  risk: string;
  can_draft: boolean;
}

export type BriefingKind = "practice" | "automate" | "focus_block" | "git_habit" | "agent_result";
export interface Prepared { text?: string; steps?: string[]; artifact_ref?: string }
export interface BriefingCard {
  id: string;
  kind: BriefingKind | string;
  title: string;
  why: string;
  prepared: Prepared;
  risk_class: "normal" | "outward" | "irreversible";
  sources: string[];
  expires_at: string;
  status: "ready" | "fired" | "dismissed" | "stale";
  /** What pressing "Approve and run" made, once pressed (the engine also sends at, actor and verdict). */
  fired?: { queue_id?: string; run_id?: string; at?: string; actor?: string; verdict?: string } | null;
  /** Additive, from the engine. */
  dismissed?: { at?: string; mode?: string } | null;
  fire_type?: "queue" | "draft" | "agent" | string;
  verdict?: "confirmed" | "stale" | string;
  verify_note?: string;
  edited?: boolean;
  origin?: string;
  wording?: string;
  score?: number;
  numbers?: Record<string, number | string>;
  ranking?: { score?: number; rank?: number; decision?: string; cap?: number; min_score?: number; parts?: Record<string, { x: number; w: number; contribution: number }> };
}
export interface Briefing { cap: number; generated_at: string; cards: BriefingCard[] }

export interface Budget { steps?: number; seconds?: number; tokens?: number; [k: string]: number | undefined }
/** A per-child tool scope with an expiry, a step cap and revocation. It scopes tools only: there is no site or app scope. */
export interface Lease { ttl_s: number; remaining_s: number; steps_left: number; tools: string[]; revoked: boolean; /** additive: why a finished lease ended */ state?: string; stop_reason?: string }
export interface AgentNode { id: string; role: string; state: string; budget: Budget; spent: Budget; result_ref?: string; /** additive, optional */ lease?: Lease }
/** A step in a run's result. `check` is a declarative postcondition run by code after the step. */
export type StepCheck = "verified" | "uncertain" | "failed";
export interface AgentRun {
  run_id: string;
  kind: string;
  mode: "foreground" | "nightly";
  state: string;
  started: string;
  parent: AgentNode;
  children: AgentNode[];
}
/** A job the agent service can run (GET /agents/kinds). */
export interface AgentKind { kind: string; title: string; roles?: string[]; describe?: string }
export interface AgentRunDetail { artifacts: { name: string; kind: string; path_ref: string }[]; result: unknown }
export type SpawnKind = "programming.commit_analyst" | "programming.test_gap" | "programming.refactor_suggest" | "data.profile" | "data.chart" | "creative.weekly_summary" | (string & {});

export type ImageKind = "glance" | "point" | "verify" | "live_frame";
export type ImageBlockReason = "unattended" | "no_consent" | "secure_input" | "denylisted_app";
/** One call to a remote model. Text rows hold their payload exactly as sent; image rows never hold a picture or text. */
export interface LedgerEntry {
  t: string; purpose: string; schema: string | null; fields: string[]; payload: Record<string, unknown> | null; model: string | null; bytes: number;
  /** Additive. Image rows: `kind: "image"`, a `status` and, when blocked, a `reason`. */
  id?: string;
  kind?: string;
  status?: "ok" | "blocked" | "sending" | "failed" | string;
  reason?: ImageBlockReason | string | null;
  source?: "real_screen" | "sandbox" | string | null;
  image?: { sha8?: string; bytes?: number; width?: number; height?: number; kind?: ImageKind | string } | null;
  provider?: string | null;
  mock?: boolean;
  ok?: boolean | null;
  latency_ms?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_estimate_usd?: number | null;
  error?: string | null;
}
export interface PrivacySummary {
  calls: number;
  by_purpose: Record<string, number>;
  /** A time, or (from the engine) the last call itself: `{ t, purpose, model, bytes, mock }`. */
  last_call: string | { t: string; purpose?: string; model?: string | null; bytes?: number; mock?: boolean } | null;
  local_only_note: string;
  canary?: { runs: number; planted: number; leaked: number; last_run?: string | null } | null;
  /** Additive. */
  mock_calls?: number;
  worker_requested_calls?: number;
  blocked_attempts?: number;
  images?: { sent: number; blocked: number; blocked_by_reason: Record<string, number>; sent_by_source: Record<string, number>; bytes_sent: number; note?: string };
  cleared?: { times: number; calls_removed: number; last_cleared_at: string | null };
}
export interface LocalModelStatus {
  enabled: boolean;
  running: boolean;
  /** Size and checksum are null until a model file has been found and checked. */
  model?: { file: string; size_bytes: number | null; sha_ok: boolean | null } | null;
  endpoint?: string;
  tokens_per_s?: number;
  mode: "model" | "rules";
  /** Additive: why it is on rules ("mock_mode", "no_model_file", ...). */
  reason?: string | null;
}

/* -- Git habits (programmer role) --------------------------------------------------------------------------- */
export interface GitSuggestion {
  id: string; template?: string; text: string; wording?: string; habits?: string[]; risk?: string; can_draft?: boolean; primary_habit?: string;
}
export interface GitHabit {
  id: string; label: string; learner: number; expert: number; delta: number; ci: Interval;
  /** Higher is worse (1) or lower is worse (-1). */
  bad?: 1 | -1;
  flagged?: boolean;
  /** Why an unflagged habit was left alone: "below_min_delta" and others. */
  reason?: string;
  min_delta?: number; n_num?: number; n_den?: number; unit?: string;
  suggestion?: GitSuggestion | null;
}
export interface GitHabits {
  person: string; repo: string;
  habits: GitHabit[];
  suggestions?: GitSuggestion[];
  digest_source: "model" | "rules";
  digest_model_share?: number;
  digest_warming?: boolean;
  n_commits: number;
  reference?: { n_experts: number; origin: string; note?: string };
  features?: Record<string, unknown>;
}
export interface GitPeople { learners: { person: string; repo: string }[]; experts: string[]; registered?: unknown[]; default_person?: string }

/* -- Models and cost (agent service, GET /models/status) ------------------------------------------------------ */
export interface ModelStep { provider: string; tier: string; when: "primary" | "escalate" | "fallback" | string; model: string | null }
export interface ModelRole { role: string; steps: ModelStep[]; escalate?: Record<string, unknown>; call_timeout_s?: number; deadline_s?: number }
export interface Breaker { state: string; recent_failures: number; retry_in_s: number; opened_count: number }
export interface ModelProvider {
  name: string; configured: boolean; enabled_by_flag?: boolean | null; models: Record<string, string> | null; breaker: Breaker | null;
  health: "ok" | "degraded" | "down" | "unknown" | string;
}
export interface MeterRow {
  role: string; provider: string; model: string; n: number; ok: number; failed: number; p50_ms: number | null; p95_ms: number | null;
  input_tokens: number; output_tokens: number; cost_usd_est: number | null;
}
export interface PriceAssumption { input_usd_per_million: number; output_usd_per_million: number; source: string }
export interface ModelsStatus {
  generated_at: string;
  mock: boolean;
  roles: ModelRole[];
  providers: ModelProvider[];
  boot: { provider: string; t?: string; ok?: boolean; mock?: boolean; missing?: string[] }[];
  latencies: Record<string, number[]>;
  meter: MeterRow[];
  prices_assumed: Record<string, PriceAssumption>;
  config_error: string | null;
  bakeoff: unknown | null;
}


/* -- Explain: "Where did my time go?" (REQ-6, GET /evidence/packet and POST /evidence/explain) -------------------------------- */
export interface PacketFact { path: string; value: number; unit: string }
export interface EvidencePacket {
  person: string; case: string;
  blocks?: Record<string, string>;
  facts: PacketFact[];
  limitations: { id: string; text: string }[];
}
export interface ExplainSentence { text: string; uses: string[] }
export interface ExplainAction { id: string; text: string; uses: string[]; chosen_by: string }
export type ExplainSection =
  | { kind: "explanation" | "answer"; sentences: ExplainSentence[] }
  | { kind: "coaching"; actions: ExplainAction[] }
  | { kind: "limits"; sentences: { id: string; text: string }[] };
export interface ExplainAttempt { route: string; ok: boolean; reason: string | null; codes?: string[] }
export interface ExplainResult {
  intent: string;
  source: "template" | "local" | "cloud";
  model: string | null;
  sections: ExplainSection[];
  footer: string;
  badge: { origin: string; n: number; n_unit: string; split: string | null };
  check: { ok: boolean; schema_ok?: boolean; checked?: { sentences?: number; numbers?: number; names?: number; intervals?: number }; rejected?: unknown[]; dropped_actions?: unknown[]; subject?: string };
  attempts: ExplainAttempt[];
  fallback_reason: string | null;
  question: { asked_s: number | null; matches_case: boolean | null };
  person?: string; case?: string; blocks?: Record<string, string>;
}

/* -- Notices (REQ-8, the attention layer; flag UNDERSTUDY_X_ATTENTION) ---------------------------------------------------------- */
export interface AttentionType { type: string; class: "safety" | "time" | "now" | "wait" | "info" | string; mode: string; fixed: boolean }
export interface AttentionLearned { n?: number; never_subjects?: number | unknown[]; drop_hours?: number[]; max_drop?: number }
export interface AttentionSettings {
  /** Only the kinds set away from the default. */
  modes: Record<string, string>;
  budget_per_day: number;
  level_glance: boolean;
  types: AttentionType[];
  /** The hard floors, in plain words, read-only. */
  floors: { type: string; floor: string; why: string }[];
  learned: Record<string, AttentionLearned>;
  defaults?: { modes: Record<string, string>; budget_per_day: number; level_glance: boolean };
}
export interface AttentionDigest {
  kind: string;
  needs_you?: number;
  /** `id` is the first item's id and `ids` up to five: GET /attention/why?item=<id> explains each. */
  needs_you_items?: { type: string; count: number; id?: string; ids?: string[] }[];
  ran?: number;
  can_ignore?: number;
  /** Fixed sentences, at most seven. */
  lines: string[];
  counts?: Record<string, number>;
  /** Counters keyed "shown:toast", "held:held_typing", "dropped:dropped_flow". Older engines send only these. */
  today?: Record<string, number>;
  /** Each count with the engine's own fixed sentence saying why. */
  today_detail?: { state: "shown" | "passive" | "dropped" | "held" | string; code: string; n: number; reason_text: string }[];
  budget?: { used: number; per_day: number };
}
export interface AttentionWhy {
  id: string; type: string; state: string; channel?: string; deliver_at?: string; reason_code?: string;
  /** A fixed line such as "Held because you were typing. Shown at your next pause." */
  reason_text: string;
  mode?: string; learned_drop?: number; count?: number;
  transitions: { t: number; state: string; reason_code: string; reason_text: string }[];
  budget?: { used: number; per_day: number };
}
export interface AttentionBadges { needs_you: number; waiting: number; marker: "none" | "needs_you" | "stopped" | string; stopped: boolean }
export interface AttentionPeek { badges: AttentionBadges; digest_ready: boolean; active?: unknown; poll_after_s?: number }
export interface AttentionPatch { modes?: Record<string, string>; budget_per_day?: number; level_glance?: boolean; reset_learned?: boolean | string[] }

/* -- Open-ended tasks (Track T, contract v1: GET /agent/tasks and its event stream). Unknown fields are ignored; every field may be missing. -- */
export type TaskRowState = "planning" | "waiting_consent" | "running" | "done" | "stopped" | "failed";
export interface TaskConsent {
  kind?: string; scope_text?: string; can?: string[]; cannot?: string[]; folder?: string | null; command_hash?: string | null; cost_note?: string | null; max_minutes?: number;
  buttons?: { allow?: string; decline?: string; more?: { id: string; label: string }[] };
}
export interface TaskRow {
  task_id: string; title: string; route?: string; source?: "typed" | "voice"; state: TaskRowState; attended?: boolean;
  /** The current short step line while it runs. */
  latest?: string | null; steps_done?: number;
  /** ONE line, at most 140 characters, when it is done. */
  result?: string | null; reason?: string | null;
  started?: string; finished?: string | null;
  open?: { kind: "folder" | "file"; path: string } | null;
  needs_consent?: TaskConsent | null;
  question?: { text: string; options: { id: string; label: string }[] } | null;
}
/** The detail of one task: its plain step lines and, for a task that answered a question, the answer in full (up to 1500 characters). */
export interface TaskDetail extends TaskRow { steps?: string[]; answer?: string | null }
export interface SkillsAnswer { use_claude_skills: boolean; off: string[]; /** The time cap a background task starts with, in minutes (1 to 120; the service's default is 30). Absent from an older service. */ max_minutes?: number; /** The most a task may spend, in US dollars (0.5 to 20; the service's default is 2). Absent from an older service. */ max_budget_usd?: number; skills: { name: string; description?: string; source?: "claude" | "plugin" | "knack"; enabled?: boolean }[] }
