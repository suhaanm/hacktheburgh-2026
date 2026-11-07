// The attention layer as the desktop sees it (REQ-8, docs/ATTENTION_DESIGN.md section 8). This mirrors the engine's `GET /attention/next`
// and is the ONLY place that shape lives here: if the engine's JSON differs, adapt `parseNext` and nothing else.
//
// Trust: a response is data from another process, so it is parsed, never cast. Unknown fields are dropped, strings are length-capped, enums
// and ids are validated, numbers are clamped. Anything malformed becomes "nothing to show". The words (title, body) are the engine's fixed
// templates; they are never model text, and this side never builds a notice from anything else.
import { z } from 'zod'

export const CHANNELS = ['log', 'badge', 'banner', 'chip', 'toast', 'question_card', 'voice'] as const
export type Channel = (typeof CHANNELS)[number]

export const EVENT_TYPES = [
  'kill_engaged', 'kill_cleared', 'injection_pause', 'irreversible_decision', 'run_blocked_target', 'run_blocked_error', 'approval_blocking',
  'calendar_deadline', 'cue_cue', 'cue_ask', 'cue_offer', 'voice_line', 'help_level_changed', 'routine_proposal', 'briefing_ready',
  'approval_waiting', 'run_finished', 'morning_report', 'service_degraded', 'attention_digest',
] as const
export type EventType = (typeof EVENT_TYPES)[number]

// What an event may carry: ids and enums only (packages/schema/attention_event.schema.json).
export interface AttentionEvent {
  type: Exclude<EventType, 'attention_digest'>
  subject: string
  op?: 'raise' | 'resolve'
  risk_class?: 'irreversible' | 'outward' | 'normal'
  outcome?: 'done' | 'failed' | 'paused' | 'yielded' | 'stopped'
  run_mode?: 'overnight' | 'background' | 'foreground'
  service?: 'engine' | 'agent' | 'model' | 'calendar'
  count?: number
  minutes?: number
  expires_in_s?: number
  deadline_in_s?: number
  blocks_run?: boolean
  asked?: boolean
  state?: Record<string, boolean | number>
}

export const ACTION_IDS = [
  'open_menu', 'open_run', 'open_queue', 'open_calendar', 'open_routines', 'open_briefing', 'open_report', 'open_settings', 'open_summary',
  'dismiss', 'not_now', 'never',
] as const
export type ActionId = (typeof ACTION_IDS)[number]

const text = (max: number) => z.string().max(max)
const id = z.string().regex(/^[A-Za-z0-9_.:-]{1,80}$/)
const action = z.object({ id: z.enum(ACTION_IDS), label: text(40) })

const ItemSchema = z.object({
  id,
  type: z.enum(EVENT_TYPES),
  channel: z.enum(CHANNELS),
  text_id: text(40),
  title: text(120).nullable(),
  body: text(300).nullable(),
  source: text(40),
  count: z.number().int().min(1).max(999).catch(1),
  actions: z.array(action).max(4).catch([]),
  priority: z.number().int().min(0).max(3).catch(1),
  new: z.boolean().catch(true),
  preempt: z.boolean().catch(false),
  reminder: z.boolean().catch(false),
  display_s: z.number().min(0).max(120).catch(12),
  expires_in_s: z.number().min(0).max(1e9).catch(0),
  reason_code: text(40).catch(''),
})

const BadgesSchema = z.object({
  needs_you: z.number().int().min(0).max(9999).catch(0),
  waiting: z.number().int().min(0).max(9999).catch(0),
  marker: z.enum(['none', 'needs_you', 'stopped']).catch('none'),
  stopped: z.boolean().catch(false),
})

const NextSchema = z.object({
  item: ItemSchema.nullable().catch(null),
  active: z.object({ id, type: z.enum(EVENT_TYPES), until: z.number() }).nullable().catch(null),
  badges: BadgesSchema.catch({ needs_you: 0, waiting: 0, marker: 'none', stopped: false }),
  digest_ready: z.boolean().catch(false),
  poll_after_s: z.number().min(0.5).max(120).catch(2),
})

export type AttentionItem = z.infer<typeof ItemSchema>
export type AttentionBadges = z.infer<typeof BadgesSchema>
export interface AttentionNext {
  item: AttentionItem | null
  active: { id: string; type: EventType; until: number } | null
  badges: AttentionBadges
  digestReady: boolean
  pollAfterS: number
}

export const EMPTY_BADGES: AttentionBadges = { needs_you: 0, waiting: 0, marker: 'none', stopped: false }

/** Parse the `data` of a `GET /attention/next` answer (or the whole body with a `data` field). Malformed means nothing to show. */
export function parseNext(raw: unknown): AttentionNext {
  const data = raw && typeof raw === 'object' && 'data' in (raw as Record<string, unknown>) ? (raw as { data: unknown }).data : raw
  const r = NextSchema.safeParse(data)
  if (!r.success) return { item: null, active: null, badges: EMPTY_BADGES, digestReady: false, pollAfterS: 5 }
  const d = r.data
  return { item: d.item, active: d.active, badges: d.badges, digestReady: d.digest_ready, pollAfterS: d.poll_after_s }
}

/** An opaque subject id the engine accepts (letters, digits and `_ . : -`, at most 64, starting with a letter or digit). */
export function toSubject(raw: string): string {
  const s = String(raw).toLowerCase().replace(/[^a-z0-9_.:-]/g, '_').slice(0, 64)
  return /^[a-z0-9]/.test(s) ? s : `x${s}`.slice(0, 64)
}
