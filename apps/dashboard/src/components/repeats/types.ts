/** Wire types for the Repeats page (the engine's GET /hitlist and GET /hitlist/firm). Ids, numbers and enums beside pack words. */

export type Family = "open" | "read" | "enter" | "copy" | "check" | "run" | "search" | "step";
export type HitStatus = "candidate" | "proposed" | "learning" | "running" | "automated";
export type Stops = "none" | "submit" | "payment" | "message" | "delete" | "share" | "release";
export type HitState = "ok" | "new_user" | "too_little_data" | "nothing_repeats" | "all_handled" | "counting_again" | "capture_off";
export type HeldReason = "irreversible_first_step" | "judgement" | "unstable" | "denylist";

/** An estimate with its 95% interval. Minutes a week on the worker's list, hours a week on the firm's. */
export interface Est { point: number; lo: number; hi: number }

export interface HitRow {
  id: string;
  /** The action in plain words, in the role pack's vocabulary. */
  label: string;
  /** The part of `label` printed in bold. Always a piece of the label, or null. */
  key: string | null;
  family: Family;
  /** Times done in the window. */
  count: number;
  /** Minutes a week the worker could save, with a 95% interval. */
  minutes_per_week: Est;
  judgement_share: number;
  status: HitStatus;
  stops_before: Stops;
  variation: number;
  /** How many look-alike variants (other tools, small slips) were merged into this row. */
  variants: number;
  overlaps: { id: string; label: string; relation: "includes" | "inside" }[];
  seconds_per_time: number;
  /** Unix seconds of the newest run. */
  t: number;
  actions: { routine_id: string | null; can_automate: boolean; card_id: string };
  what: string;
  touches: string[];
  never: string[];
}

export interface HitlistWire {
  state: HitState;
  message: string;
  window_days: 7 | 30;
  window_from: string;
  window_to: string;
  counting_since: string | null;
  episodes_in_window: number;
  rows: HitRow[];
  automated: HitRow[];
  hidden: { id: string; label: string; count: number; returns_at: number }[];
  held_back: { reason: HeldReason; count: number }[];
  not_shown: number;
  total: { actions: number; repeats: number; minutes_per_week: Est; hours_per_week: Est } | null;
}

/** One action in one role across the synthetic firm: people are counted, never listed. */
export interface FirmRow {
  id: string;
  label: string;
  key: string | null;
  family: Family;
  role: string;
  people: number;
  count: number;
  minutes_per_week: Est;
  hours_per_week: Est;
  stops_before: Stops;
}

export interface FirmWire {
  window_days: 7 | 30;
  people: number;
  min_group: number;
  suppressed: number;
  not_shown: number;
  total: { actions: number; people: number; hours_per_week: Est };
  rows: FirmRow[];
}

export type Audience = "worker" | "admin";
