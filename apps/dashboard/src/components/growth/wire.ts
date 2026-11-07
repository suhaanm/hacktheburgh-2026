// Wire shapes for the Growth screen. They follow what CUE-ENGINE agreed with GROWTH on 7 Nov 2026
// (`GET /growth`, `GET /cue/ledger`, `DELETE /cue/ledger`, `GET /cue/ledger/export`), behind UNDERSTUDY_X_CUE.
// Fields that cannot be computed are null (never 0). Additive keys are tolerated, so every consumer ignores unknown keys.

export type Interval = [number, number];

/** The engine's trend wording: "steady" is the agreed spelling (not "flat"). */
export type Direction = "less_help" | "steady" | "more_help" | "too_early";

/** Meta of the growth endpoints: AnalyticMeta, with n_unit "occurrences" (a new value). */
export interface GrowthMeta {
  origin: "real" | "synthetic" | "mixed";
  n: number;
  n_unit: string;
  split: string | null;
  interval_level: number;
  note: string | null;
  generated_at: string;
}

export interface Envelope<T> { meta: GrowthMeta | null; data: T }

export type OriginDetail = "synthetic_learner" | "simulated_participants" | "live_worker";

export interface WireWilson { k: number; n: number; share: number; wilson: Interval; lower?: number }

export interface WireCurvePoint {
  /** Occurrence index: the sliding window of `window` occurrences ends here. */
  i: number;
  t_hour: string;
  independence: number;
  lo: number;
  hi: number;
  n: number;
  level: number | null;
  /** Occurrences in the window by the highest cue tier seen: [t0 (no cue), t1, t2, t3, t4]. */
  tiers?: number[];
}

export interface WireMedian { median_s: number | null; ci: Interval | null; n: number }
export interface WireTtp { after_cue: WireMedian | null; no_cue: WireMedian | null }
export interface WireRetention { value: number | null; k: number; n: number; wilson: Interval | null }
export interface WireRecent { n: number; assisted: number }

export interface WireSkill {
  skill: string;
  /** Pack vocabulary: the full label, and a short noun phrase for sentences. */
  label: string;
  name: string;
  n: number;
  independent: number;
  assisted: number;
  independence_lower: number | null;
  mastery: number | null;
  level: number | null;
  direction: Direction;
  first10: WireRecent | null;
  last10: WireRecent | null;
  time_to_progress: WireTtp | null;
  retention: WireRetention | null;
  retrieval_due: boolean;
}

export interface WireGrowth {
  person: string;
  /** null means overall. */
  skill: string | null;
  window: number;
  origin_detail?: OriginDetail;
  readiness: { occurrences: number; needed: number; ready: boolean };
  baseline: WireWilson | null;
  score: {
    composite: number | null;
    composite_ci: Interval | null;
    composite_partial: boolean;
    available_weight: number;
    weights: { independence_lb: number; mastery: number; gap_closure: number; retention: number };
    used_weights?: { independence_lb: number; mastery: number; gap_closure: number; retention: number } | null;
    weights_note: string;
  };
  components: {
    independence: WireWilson | null;
    mastery: { value: number | null; by_skill?: Record<string, number> } | null;
    gap_closure: { value: number | null; first5_lost_s: number | null; last5_lost_s: number | null; ci: Interval | null; n_first: number; n_last: number } | null;
    retention: WireRetention | null;
  };
  trend: {
    /** Change in the assisted share per 10 occurrences. Negative means needs less help. */
    slope_per_10: number | null;
    ci: Interval | null;
    direction: Direction;
    blocks?: { i: number; n: number; assisted_share: number }[];
  };
  curve: WireCurvePoint[];
  occurrences: { total: number; unaided: number; assisted: number; errors: number; abandoned: number };
  time_to_progress: WireTtp | null;
  by_skill: WireSkill[];
  offloaded: { delegated: number; automation: number; by_skill?: Record<string, number>; note?: string };
  claim?: string;
}

/** One ledger row. Enums and numbers only: no text, no screenshots. */
export interface LedgerRow {
  id: string;
  person: string;
  origin: "real" | "synthetic";
  /** Hour bucket only, for example "2026-11-07T17". */
  t_hour: string;
  role: string;
  skill: string;
  step: string;
  stream: "assist" | "delegated" | "automation";
  trigger: "none" | "auto" | "asked";
  stuck_bucket: string | null;
  tier: number;
  options_shown: number;
  answer_id: string | null;
  accepted: boolean;
  dismissed: boolean;
  seconds_to_progress: number | null;
  lost_s: number | null;
  outcome: "clean" | "assisted" | "error" | "abandoned";
  level_before: number | null;
  level_after: number | null;
  taught: boolean;
  retrieval: boolean;
  origin_detail?: OriginDetail;
}

export interface WireLedger {
  rows: LedgerRow[];
  counts?: { assist: number; delegated: number; automation: number };
  offloaded?: { delegated: number; automation: number };
}

export interface WireDeleted { deleted: number | { assist?: number; delegated?: number; automation?: number }; audit_line?: boolean }
