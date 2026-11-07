// Awareness layer (REQ-5, AWR-1 to AWR-6): shared types and the closed enums. The enums mirror packages/schema/awareness.schema.json
// (a test compares them with the file), which is the one source of truth that the engine, the glance model and this code share.
// Nothing here carries free text, a coordinate or a title.

export const APP_KINDS = ['browser', 'spreadsheet', 'email', 'code_editor', 'terminal', 'chat', 'other'] as const
export type AppKind = (typeof APP_KINDS)[number]
export type AppKindOrUnknown = AppKind | 'unknown'

export const TASK_PHASES = ['idle', 'reading', 'searching', 'entering', 'comparing', 'reviewing', 'submitting', 'waiting', 'unknown'] as const
export type TaskPhase = (typeof TASK_PHASES)[number]

export const BLOCKERS = ['none', 'unclear_next_step', 'cannot_find_control', 'error_message', 'unexpected_state', 'waiting_for_load', 'needs_information', 'permission_prompt', 'unknown'] as const
export type Blocker = (typeof BLOCKERS)[number]

export const TRIGGER_REASONS = ['stuck', 'loop', 'hotkey', 'periodic'] as const
export type TriggerReason = (typeof TRIGGER_REASONS)[number]

// Why a glance did NOT happen. All decided by code; the order of this list is the order the checks run in.
export const SKIP_REASONS = [
  'layer_off', // UNDERSTUDY_X_AWARENESS (or UNDERSTUDY_X) is not set, or awarenessEnabled is false
  'no_consent', // the matching consent has not been given, or is for an older consent text
  'killed', // the kill switch is on
  'paused', // the worker paused the layer ("pause for an hour")
  'locked',
  'asleep',
  'idle', // no keyboard or pointer input for a while: nobody is there to be helped
  'screen_share', // a screen-sharing helper process is running (heuristic)
  'thermal', // the Mac is under serious thermal pressure; background work stops
  'secure_input', // macOS secure event input is on (a password field has focus somewhere)
  'secure_input_unknown', // the check could not run and the worker chose strict mode
  'app_denied', // the frontmost app is on the denylist (default categories or the worker's own)
  'app_unknown', // the frontmost app could not be read and the worker chose strict mode
  'no_work_session', // periodic glances only run while a work session is on
  'too_soon', // at most one glance every 10 s
  'hourly_cap',
  'daily_cap', // the dollar cap for the day
  'ledger_unavailable', // the call could not be recorded, so nothing is sent
  'capture_failed',
  'port_blocked', // the service refused (its own gate, or no model configured)
  'port_failed',
] as const
export type SkipReason = (typeof SKIP_REASONS)[number]

export type Tri<T extends string> = T | 'unknown'
export type SecureInputState = 'on' | 'off' | 'unknown'

// ------------------------------------------------------------------------------------------------ cursor features
export interface CursorSample {
  // Milliseconds on any monotonic or wall clock, only differences are used.
  t: number
  x: number
  y: number
}

export interface CursorWindowFeatures {
  window_s: number
  dwell_s: number
  dwell_zone: string | null
  wander: number
  back_forth: number
  zone_a: string | null
  zone_b: string | null
  speed_bursts: number
  idle_gap_s: number
  // null: no permission-free click source (clicks need Accessibility, which is not requested).
  clicks: number | null
  // Where the longest dwell sat, as an opaque short hash for loop detection only (never sent, never stored): null when there was no dwell.
  // Kept off the wire: see toWindowEvent in events.ts.
  dwell_anchor: { bx: number; by: number } | null
}

// ------------------------------------------------------------------------------------------------ glance
export interface GlanceResult {
  app_kind: AppKind | null
  task_phase: TaskPhase | null
  blocker: Blocker | null
  confidence: number
  box_2d?: [number, number, number, number]
}

// The frame lives in memory for one call and is zeroed after it. `jpeg` is never written anywhere.
export interface Frame {
  jpeg: Buffer
  width: number
  height: number
  bytes: number
  // First 12 hex characters of the SHA-256 of the JPEG (identifies the call in the ledger without being the image).
  sha256_prefix: string
}

export interface Gates {
  consent: boolean
  denylisted_app: boolean
  secure_input: boolean
  unattended: boolean
}

export interface GlancePortRequest {
  frame: Frame
  // The on-device guess of the app's kind, sent beside the frame as a hint.
  appKind: AppKindOrUnknown
  gates: Gates
  trigger: TriggerReason
}

export interface GlancePortResponse {
  ok: boolean
  blocked_reason?: string
  // The model's raw closed-schema object. Parsed again by parseGlanceResult; never trusted.
  result?: unknown
  model?: string
  latency_ms?: number
  cost_usd_est?: number
}

export interface GlancePort {
  glance(req: GlancePortRequest): Promise<GlancePortResponse>
}

export type Clock = () => number
export type TimerHandle = unknown
export interface Timers {
  setInterval(fn: () => void, ms: number): TimerHandle
  clearInterval(h: TimerHandle): void
}

export const realTimers: Timers = {
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (h) => clearInterval(h as ReturnType<typeof setInterval>),
}

export const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
export const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
export const inList = <T extends string>(list: readonly T[], v: unknown): v is T => typeof v === 'string' && (list as readonly string[]).includes(v)

export const ZONE_RE = /^[a-z][a-z0-9_]{1,30}$/ // the pattern of ext_rect.schema.json and awareness.schema.json
