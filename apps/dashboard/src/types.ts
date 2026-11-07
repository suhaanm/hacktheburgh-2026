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
  total_gap_s: number;
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
  planted: boolean | null;
}
export interface Transitions {
  nodes: TransitionNode[];
  edges: TransitionEdge[];
}

export interface ReplayFrame {
  t_replay: number;
  event: { type: string; t: string; target?: { role?: string } };
  state: { task: string; last_cog: string; counts: Record<string, number> };
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
  forecast: { d_min: number; survival: number }[];
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
  value: { hours_saved: Interval; net_gbp: Interval; confidence: number };
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
  options: { value: string; label: string }[];
}
export interface OnboardingQuestions {
  role: string;
  pack: {
    name: string;
    summary: string;
    extra_cogs: string[];
    risk_classes: { irreversible: string[] };
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
  task: { id: string; name: string; step: number; steps_total: number };
  level: "L1" | "L2" | "L3" | "L4";
  chip: "full" | "small" | "dot" | "gone";
  message: string;
  why: string;
  mastery: Record<string, number>;
}

/* -- Evidence --------------------------------------------------------------- */
export interface Hazard {
  series: { t: number; p: number }[];
  model: { log_loss: number; brier: number; ece: number; ci_log_loss: Interval };
  baselines: {
    base_rate: { log_loss: number; brier: number; ece: number };
    time_since_progress: { log_loss: number; brier: number; ece: number };
  };
  calibration: { p_mean: number; freq: number; n: number }[];
  false_alarms_per_hour: number;
  split: string;
}

export interface Limitation {
  id: string;
  text: string;
  severity: "high" | "medium" | "low" | string;
}

/** Evidence report sections. The contract fixes the section names; their inner shapes are
 *  owned by the eval track, so the dashboard reads them defensively. */
export interface EvalReport {
  generated_at: string;
  mock: boolean;
  sections: {
    deficit_recovery?: EvalSection<Record<string, unknown>>;
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
