// Shapes follow docs/API_CONTRACT.md exactly. Additive fields are allowed by the contract,
// so every consumer must tolerate unknown keys.

export type Interval = [number, number];

export interface AnalyticMeta {
  origin: "real" | "synthetic" | "mixed";
  n: number;
  n_unit: "people" | "personas" | "households" | "episodes" | "days";
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
  depth: "deep" | "thin";
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
export type ExtensionName = "privacy" | "localmodel" | "calendar" | "git" | "proactive" | "agents";

export type BlockKind = "meeting" | "focus" | "break" | "offscreen" | "free";
export interface CalBlock {
  /** "HH:MM", minutes since midnight, or an ISO time: all are read. */
  start: string | number;
  end: string | number;
  kind: BlockKind;
  n_attendees_bucket?: "lt5" | "5to9" | "10plus";
}
export interface CalDay { dow: number; blocks: CalBlock[] }
export interface WeekFeatures {
  meeting_h?: number; focus_blocks_60?: number; focus_blocks_90?: number; longest_focus_min?: number;
  fragmentation?: number; back_to_back_runs?: number; work_span_h?: number; offscreen_h?: number;
  [k: string]: number | undefined | CalDay[];
}
export interface GapRow { feature: string; learner: number; expert: number; delta: number; ci: Interval }
export interface CalendarWeek {
  days: CalDay[];
  features: WeekFeatures;
  /** The expert's features. `days` (the expert's blocks) is additive and optional. */
  expert: WeekFeatures & { days?: CalDay[] };
  gap: { rows: GapRow[] };
}
export interface CalSuggestion {
  id: string;
  template: string;
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
  /** Local only: what pressing "Approve and run" did, so the card can say which. */
  fired?: { queue_id?: string; run_id?: string };
}
export interface Briefing { cap: number; generated_at: string; cards: BriefingCard[] }

export interface Budget { steps?: number; seconds?: number; tokens?: number; [k: string]: number | undefined }
/** A per-child tool scope with an expiry, a step cap and revocation. It scopes tools only: there is no site or app scope. */
export interface Lease { ttl_s: number; remaining_s: number; steps_left: number; tools: string[]; revoked: boolean }
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
export interface AgentRunDetail { artifacts: { name: string; kind: string; path_ref: string }[]; result: unknown }
export type SpawnKind = "programming.commit_analyst" | "programming.test_gap" | "programming.refactor_suggest" | "data.profile" | "data.chart" | "creative.weekly_summary";

export interface LedgerEntry { t: string; purpose: string; schema: string; fields: string[]; payload: Record<string, unknown>; model: string; bytes: number }
export interface PrivacySummary {
  calls: number;
  by_purpose: Record<string, number>;
  last_call: string | null;
  local_only_note: string;
  canary?: { runs: number; planted: number; leaked: number } | null;
}
export interface LocalModelStatus {
  enabled: boolean;
  running: boolean;
  model?: { file: string; size_bytes: number; sha_ok: boolean } | null;
  endpoint?: string;
  tokens_per_s?: number;
  mode: "model" | "rules";
}
