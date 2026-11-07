// Feedback to the engine: what the worker did with a cue. Ids and numbers only: never a label, a chip, a box, a title or any text from
// the screen. `sanitizeFeedback` runs on every event right before it leaves, so a bug upstream cannot widen what is sent.
import type { CueDecision, CueKind, CueLevel, CueTier } from './types'

export const FEEDBACK_EVENTS = ['shown', 'accepted', 'dismissed', 'answered', 'resolved', 'abandoned', 'know_this'] as const
export type FeedbackKind = (typeof FEEDBACK_EVENTS)[number]

// Why the cue ended, as a short enum. The engine reads `how` to weigh a label: a timeout is weaker than a press of Escape.
export const FEEDBACK_HOW = ['esc', 'click', 'timeout', 'stale', 'progress', 'late', 'superseded', 'episode_end', 'off', 'quiet', 'declined', 'accepted_offer'] as const
export type FeedbackHow = (typeof FEEDBACK_HOW)[number]

export interface CueFeedbackEvent {
  event: FeedbackKind
  // 'cue' is about the cue that was on screen; 'episode' is about the whole stuck episode (resolved, or ended without progress).
  scope: 'cue' | 'episode'
  episode_id: string
  decision_id: string | null
  kind: CueKind
  tier: CueTier | null
  step_id: string | null
  // The option the worker picked (an `ask`): a pack id, never the label.
  option_id: string | null
  how: FeedbackHow | null
  // Seconds since the cue was shown (cue scope) or since the episode began (episode scope), to a tenth.
  seconds: number
  level: CueLevel | null
}

export interface FeedbackInput {
  event: FeedbackKind
  scope?: 'cue' | 'episode'
  decision: CueDecision
  how?: FeedbackHow | null
  optionId?: string | null
  // Milliseconds; converted to seconds here.
  elapsedMs: number
}

const ID_RE = /^[A-Za-z0-9_.:-]{1,80}$/

export function buildFeedback(i: FeedbackInput): CueFeedbackEvent {
  const d = i.decision
  return {
    event: i.event,
    scope: i.scope ?? 'cue',
    episode_id: d.episode_id,
    decision_id: d.decision_id,
    kind: d.kind,
    tier: d.tier,
    step_id: d.step?.id ?? null,
    option_id: i.optionId ?? null,
    how: i.how ?? null,
    seconds: Math.round(Math.min(86_400, Math.max(0, i.elapsedMs / 1000)) * 10) / 10,
    level: d.why.level,
  }
}

/** The event as it may leave this process, or null when it is not valid. Only the listed fields are copied. */
export function sanitizeFeedback(e: unknown): CueFeedbackEvent | null {
  if (typeof e !== 'object' || e === null) return null
  const o = e as Record<string, unknown>
  const id = (v: unknown): string | null => (typeof v === 'string' && ID_RE.test(v) ? v : null)
  const event = (FEEDBACK_EVENTS as readonly unknown[]).includes(o.event) ? (o.event as FeedbackKind) : null
  const episode = id(o.episode_id)
  const kind = o.kind === 'confirm' || o.kind === 'cue' || o.kind === 'ask' || o.kind === 'offer' ? (o.kind as CueKind) : null
  if (!event || !episode || !kind || typeof o.seconds !== 'number' || !Number.isFinite(o.seconds)) return null
  const tier = o.tier === 1 || o.tier === 2 || o.tier === 3 || o.tier === 4 ? o.tier : null
  const level = o.level === 1 || o.level === 2 || o.level === 3 || o.level === 4 ? o.level : null
  return {
    event,
    scope: o.scope === 'episode' ? 'episode' : 'cue',
    episode_id: episode,
    decision_id: id(o.decision_id),
    kind,
    tier,
    step_id: id(o.step_id),
    option_id: id(o.option_id),
    how: (FEEDBACK_HOW as readonly unknown[]).includes(o.how) ? (o.how as FeedbackHow) : null,
    seconds: Math.round(Math.min(86_400, Math.max(0, o.seconds)) * 10) / 10,
    level,
  }
}
