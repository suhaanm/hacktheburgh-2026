// Guards: the hard rules that sit between the engine's decision and the screen. Pure code, no clocks of its own. The engine applies the same
// caps; they are applied again here because the model proposes and code decides, and a bug upstream must not become a nag.
import { z } from 'zod'
import { CUE_TOKENS } from './tokens'
import type { CueDecision } from './types'

export type CueProactivity = 'quiet' | 'balanced' | 'eager'

// The four settings keys Cue owns, read defensively: an older settings file without them means "off, balanced, no voice, not quiet".
export const CueSettingsSchema = z.object({
  cueEnabled: z.boolean().default(false),
  cueProactivity: z.enum(['quiet', 'balanced', 'eager']).default('balanced'),
  cueVoice: z.boolean().default(false),
  cueQuietUntil: z.number().int().nullable().default(null),
})
export type CueSettings = z.infer<typeof CueSettingsSchema>

export function readCueSettings(raw: unknown): CueSettings & { pausedUntil: number | null } {
  const o = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {}
  const pick = <K extends keyof CueSettings>(k: K): unknown => (k in o ? o[k] : undefined)
  const parsed = {
    cueEnabled: CueSettingsSchema.shape.cueEnabled.safeParse(pick('cueEnabled')).data ?? false,
    cueProactivity: CueSettingsSchema.shape.cueProactivity.safeParse(pick('cueProactivity')).data ?? 'balanced',
    cueVoice: CueSettingsSchema.shape.cueVoice.safeParse(pick('cueVoice')).data ?? false,
    cueQuietUntil: CueSettingsSchema.shape.cueQuietUntil.safeParse(pick('cueQuietUntil')).data ?? null,
  }
  // The tray's "Pause for 1 hour" (pausedUntil) silences Cue as well.
  const paused = typeof o.pausedUntil === 'number' && Number.isFinite(o.pausedUntil) ? o.pausedUntil : null
  return { ...parsed, pausedUntil: paused }
}

export interface Policy {
  // The environment flag (UNDERSTUDY_X_CUE=1) AND the worker's own switch.
  enabled: boolean
  proactivity: CueProactivity
  quietUntil: number | null
  pausedUntil: number | null
  // The kill switch is on.
  killed: boolean
  // A source outside Cue says now is no time: the frontmost app is on the denylist, secure input is on. Null when nothing says so.
  suppressed: string | null
}

export interface AdmitContext {
  now: number
  policy: Policy
  // When each cue, question or offer was shown (confirmations do not count), oldest first.
  recent: readonly number[]
  // Questions already asked in this decision's episode.
  episodeQuestions: number
  // The decision is the one already on screen, growing (a higher tier): it is not a new interruption.
  continuing: boolean
}

export type Admission = { ok: true } | { ok: false; reason: 'off' | 'killed' | 'quiet' | 'suppressed' | 'cap' | 'one_question' | 'level4' | 'quiet_tier' | 'quiet_offer' }

export const cueCap = (p: CueProactivity): number => CUE_TOKENS.caps.cuesPerWindow[p]

export function admit(d: CueDecision, c: AdmitContext): Admission {
  const p = c.policy
  if (p.killed) return { ok: false, reason: 'killed' }
  if (!p.enabled) return { ok: false, reason: 'off' }
  if ((p.quietUntil !== null && c.now < p.quietUntil) || (p.pausedUntil !== null && c.now < p.pausedUntil)) return { ok: false, reason: 'quiet' }
  if (p.suppressed) return { ok: false, reason: 'suppressed' }
  const asked = d.trigger === 'asked'
  // A silent confirmation costs nothing: it is the absence of help.
  if (d.kind === 'confirm') return { ok: true }
  if (!asked) {
    // Level 4 ("On my own"): Cue only answers when asked.
    if (d.why.level === 4) return { ok: false, reason: 'level4' }
    if (p.proactivity === 'quiet') {
      if (d.kind === 'offer') return { ok: false, reason: 'quiet_offer' }
      if ((d.tier ?? 1) > CUE_TOKENS.caps.quietMaxTier) return { ok: false, reason: 'quiet_tier' }
    }
    if (d.kind === 'ask' && c.episodeQuestions >= CUE_TOKENS.caps.questionsPerEpisode) return { ok: false, reason: 'one_question' }
    if (!c.continuing) {
      const inWindow = c.recent.filter((t) => c.now - t < CUE_TOKENS.caps.windowMs).length
      if (inWindow >= cueCap(p.proactivity)) return { ok: false, reason: 'cap' }
    }
  }
  return { ok: true }
}

/** Voice: only when the worker turned it on, the build allows it, and the worker used voice or asked. Never while typing or while a card is up. */
export interface SpeakContext {
  cueVoice: boolean
  buildVoiceOn: boolean
  workerUsedVoice: boolean
  asked: boolean
  typingNow: boolean
  cardUp: boolean
}
export function mayWhisper(c: SpeakContext): boolean {
  return c.cueVoice && c.buildVoiceOn && (c.workerUsedVoice || c.asked) && !c.typingNow && !c.cardUp
}
