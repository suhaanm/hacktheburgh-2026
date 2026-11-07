// Wire shapes for the REQ-9 insight routes (`/insights/*`), as proposed to the INSIGHTS track on 7 Nov 2026.
// Every answer is `{ meta, data }`. Admin routes need the demo role header (see net.ts). Additive keys are tolerated and every
// consumer reads through the normalisers in model.ts, so a missing optional key never breaks a screen.
//
// What an admin sees about a person is numbers and enums only (D41): no raw events, screens, text, memory contents.

import type { AnalyticMeta } from "../../types";

export type Interval = [number, number];
export type Origin = "synthetic" | "real" | "mixed";

/** An estimate with an optional interval. `ci` is null when the engine could not compute one: the screen then says so. */
export interface Est { value: number; ci: Interval | null }

export interface Envelope<T> { meta: AnalyticMeta | null; data: T }

/**
 * The four trend classes (INSIGHTS spelling, 7 Nov). "cannot_tell_yet" means the interval on the slope includes zero: it is not "no change".
 * An older "steady" is read as the same class, and the screen always says "Cannot tell yet".
 */
export type Trend = "improving" | "cannot_tell_yet" | "needs_attention" | "not_enough_data";
export const TRENDS: Trend[] = ["improving", "cannot_tell_yet", "needs_attention", "not_enough_data"];

export type TenureBand = "lt_4w" | "1_3m" | "3_6m" | "6_12m" | "12m_plus";
export const TENURE_BANDS: TenureBand[] = ["lt_4w", "1_3m", "3_6m", "6_12m", "12m_plus"];

export type Verdict = "gap" | "cannot_tell";

/* -- Worker ------------------------------------------------------------------------------------ */
export type PointerTarget = "repeats" | "growth" | "routines" | "genome" | "queue" | "privacy" | "presence" | "week" | "git" | "briefing" | "predictions" | "memory" | "today";

export interface WirePointer {
  id: string;
  kind: string;
  /** Fixed-template, one line. The page never writes a number into it. */
  headline: string;
  detail: string | null;
  numbers: Record<string, number | string>;
  origin: Origin;
  /** Workers get no statistics, so these are absent for them. Admin cards keep them. */
  n: number | null;
  n_unit: string | null;
  /** "Going well", "Worth a look", "Trade-off", "Note". A word, never colour alone. */
  polarity: "positive" | "attention" | "tradeoff" | "note";
  polarity_label: string | null;
  glyph: string | null;
  a11y_label: string | null;
  /** "synthetic firm", "live", ... */
  badge: string | null;
  details_available: boolean;
  /** One action each. Null when there is nothing to open. */
  action: { label: string; to: PointerTarget; query: string | null } | null;
}

export interface WireWorker {
  person: string | null;
  role: string | null;
  week: { from: string; to: string } | null;
  nothing_stands_out: boolean;
  /** "ok" | "nothing_stands_out" | "onboarding" | "stale" | "no_data" | "role_changed", with a fixed message for the states that are not "ok". */
  status: string;
  message: string | null;
  pointers: WirePointer[];
  /** One number to try this week, from the same fixed templates. */
  try: { label: string; value: number; unit: string } | null;
  /** Ready text from the engine, when it sends one. Otherwise the page builds it from the fixed words (monday.ts). */
  monday_note: string | null;
}

export interface WireWhy {
  id: string;
  headline: string;
  because: string[];
  sources: { label: string; n: number | null; n_unit: string | null; origin: Origin }[];
  limits: string[];
  /** "selected" | "suppressed" | "unknown", with the engine's fixed reason in words. */
  state: string | null;
  reason_text: string | null;
}

export interface WireSharing {
  items: { id: string; label: string; kind: "number" | "enum" | "count"; note: string | null }[];
  never: string[];
  notice: string | null;
  /** The exact per-user row an admin sees for this worker (numbers and enums), read-only. */
  preview: Record<string, unknown> | null;
  visible_since: string | null;
  visible_to: string | null;
  legal_note: string | null;
}

/* -- Admin ------------------------------------------------------------------------------------- */
export interface AdminInsight {
  id: string;
  headline: string;
  role: string;
  effect: { label: string; unit: string; value: number; ci: Interval | null } | null;
  n: number;
  n_unit: string;
  origin: Origin;
  drill: string;
  kind: string | null;
  polarity: "positive" | "attention" | "tradeoff" | "note";
  polarity_label: string | null;
  glyph: string | null;
  a11y_label: string | null;
  /** 1 to 7: the position of the insight in the list, never a rank of a person. */
  position: number | null;
  /** The full sentence behind the short headline. */
  text: string | null;
  badge: string | null;
  split: string | null;
  statement: string | null;
  /** One action to open the place the insight points at: `to` is a screen id, `query` may carry `roles` or `onboarding` for the Firm screen. */
  action: { id: string; label: string; to: string; query: string | null } | null;
}

export interface RoleSummary {
  role: string;
  name: string;
  people: number;
  enough: boolean;
  n_expert: number;
  n_junior: number;
  reason: string | null;
  /** Seconds per case that juniors take beyond experts, with an interval. */
  gap: Est | null;
  trend: { cls: Trend; label: string | null } | null;
}

export interface WireRisk {
  approval_backlog_age_h: { median: number; max: number } | null;
  injection_pauses_30d: number;
  kill_events_30d: number;
  open_approvals: number;
}

export interface WireOverview {
  firm: { users: number; roles: number; label: string };
  top: AdminInsight[];
  coverage: { users: number; enough_data: number; min_occurrences: number; roles: { role: string; name: string; users: number; enough_data: number }[]; by_status: Record<string, number> };
  risk: WireRisk | null;
  role_comparison: RoleSummary[];
  /** How many candidate insights were left out and why (a count and fixed reasons), so a short list is never a hidden one. */
  suppressed: { count: number; by_reason: Record<string, number> } | null;
  statement: string | null;
}

export interface DrillColumn { key: string; label: string; unit: string | null }
export interface DrillRow { label: string; group: string | null; values: Record<string, number | Interval | string | null>; n: number | null }
export interface WireDrill {
  id: string;
  headline: string;
  columns: DrillColumn[];
  rows: DrillRow[];
  series: { label: string; points: { x: number; y: number; lo: number | null; hi: number | null }[] }[];
  notes: string[];
  /** Further tables when one insight needs several. */
  tables: { id: string; title: string; columns: DrillColumn[]; rows: DrillRow[] }[];
  method: string | null;
}

export interface RoleMeasure {
  key: string;
  label: string;
  unit: "share" | "ratio" | string;
  expert: Est | null;
  junior: Est | null;
  gap: Est | null;
  verdict: Verdict;
}

export interface RoleHabit {
  id: string;
  label: string;
  explains_s: Est | null;
  expert_rate: Est | null;
  junior_rate: Est | null;
  n: number;
  verdict: Verdict;
}

export interface RoleCompare {
  role: string;
  name: string;
  n_expert: number;
  n_junior: number;
  enough: boolean;
  /** "no_expert_reference" | "group_too_small" when `enough` is false. */
  reason: string | null;
  measures: RoleMeasure[];
  habits: RoleHabit[];
  /** Names the standardisation behind the per-habit seconds. */
  standard: string | null;
}

export interface WireRoles { roles: RoleCompare[]; same_scale: { min: number; max: number } }

export interface UserRow {
  id: string;
  label: string;
  role: string | null;
  level: "expert" | "junior" | null;
  status: string | null;
  last_seen_days: number | null;
  skills: { skill: string; label: string; n: number; independence_share: number | null; lost_s: Est | null }[];
  tenure_band: TenureBand;
  tenure_weeks: number | null;
  trend: Trend;
  independence: Est | null;
  assisted_share: Est | null;
  time_to_independence: { reached: boolean; value: number | null; unit: string };
  automations_running: number;
  automation: { minutes: number; routines_approved: number; runs_done: number } | null;
  n: number;
  n_recent: number | null;
}

export interface FirmAggregate {
  n_users: number;
  independence: Est | null;
  assisted_share: Est | null;
  time_to_independence: { median: number | null; ci: Interval | null; unit: string; reached_share: Est | null };
}

export interface FirmRole {
  role: string;
  name: string;
  merged: boolean;
  users: UserRow[];
  aggregate: FirmAggregate;
  /** The role's own trend class, with the change in independence per four weeks and its interval. */
  trend: { cls: Trend; label: string | null; n_people: number | null; slope_per_4w: Est | null } | null;
}
export interface WireFirm {
  roles: FirmRole[];
  privacy: { min_group: number; merged_roles: string[]; note: string | null };
  totals: { users: number; enough_data: number };
}

export interface CurvePoint { x: number; y: number; lo: number; hi: number; n: number | null }
export interface OnboardingRole {
  role: string;
  name: string;
  n: number;
  /** The independence learning curve with its interval, and the people still in view at each x. */
  curve: CurvePoint[];
  /** Kaplan-Meier "reached the target by occurrence x", with censoring; `n` here is the number still at risk. */
  km: CurvePoint[];
  censored: number | null;
  median_to_target: Est | null;
  reached_share: Est | null;
  /** Why a role is merged or left out (fewer than 5 people followed). */
  reason: string | null;
  at_risk_at_target: number | null;
}
export interface WireOnboarding {
  target: { value: number; label: string; rule: string | null; note: string | null; occurrences: number | null };
  method: string | null;
  x_unit: string;
  roles: OnboardingRole[];
}
