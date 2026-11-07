// Event schema v1 (packages/schema/event.schema.json), as the extension emits it. L0 only: no free text,
// no URLs, no field values. meta holds numbers, booleans and short enum tokens.

export const EVENT_TYPES = [
  "nav", "click", "scroll", "focus", "tab", "copy", "paste", "search",
  "idle", "lock", "unlock", "sleep", "resume", "stuck",
  "coach_shown", "coach_followed", "coach_dismissed",
  "agent_step", "approval", "undo", "task_start", "task_end", "progress",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export type MetaValue = number | boolean | string;

export interface Target {
  role?: string;
  label_hash?: string;
  domain_hash?: string;
}

/** Task markers found on a page at navigation time (enum tokens only; see pack.schema.json zoneMarkers). */
export interface PageMarkers {
  start?: { idle_s: number };
  progress: string[];
  end?: { reason: string };
}

/** What the content script reports. The service worker wraps it into a full event. */
export interface CaptureRecord {
  type: EventType;
  target?: Target;
  meta?: Record<string, MetaValue>;
  /** Only on nav records of configured sites: the worker turns these into task_start, progress and task_end events. */
  markers?: PageMarkers;
}

export interface L0Event {
  schema: 1;
  id: string;
  t: string;
  origin: "real";
  actor: "human";
  person: string;
  role: string;
  source: "browser";
  type: EventType;
  target?: Target;
  task_id?: string;
  meta?: Record<string, MetaValue>;
}

/** One recorded step of an L1 recording: the step DSL without conditions (compile adds those). */
export interface RecordedStep {
  op: "goto" | "click" | "fill" | "select";
  t_ms: number;
  selector?: string;
  role?: string;
  name?: string;
  param?: string;
  url?: string;
  input_type?: string;
}

export interface InstallConfig {
  capturing: boolean;
  person: string;
  role: string;
  engine_url: string;
  desktop_url: string;
  /** True once the engine's GET /identity answered: person and role then come from onboarding, not from us. */
  identity_adopted: boolean;
}

export const DEFAULT_CONFIG: InstallConfig = {
  capturing: false, // opt-in: nothing is captured until the worker turns it on (PR3)
  person: "",
  role: "benefits-processor",
  engine_url: "http://127.0.0.1:7700",
  desktop_url: "http://127.0.0.1:7720",
  identity_adopted: false,
};

export const STORAGE_KEYS = {
  config: "config",
  salt: "salt",
  queue: "queue",
  task: "task",
  l1Targets: "l1_targets",
  stats: "stats",
} as const;
