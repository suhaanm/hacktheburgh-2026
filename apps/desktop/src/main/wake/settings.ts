// Hey Knack settings, in their own small store (`wake.json` beside `settings.json`), like live.json and awareness.json: the shell track owns
// shared/settings.ts, so nothing here edits it. Plus the first-wake consent steps as pure functions.
//
// "Listen for Hey Knack" is ON by default (owner decision, 7 Nov, D52): no opt-in step for the on-device listener. That listener stores nothing and
// sends nothing. What DOES need the worker's yes is what happens AFTER the words: their voice going to a cloud voice model (the Live consent that
// already exists) and a picture of their screen going with it (the frame consent). Those are asked once, in ONE corner card with two clear lines
// (Yes, allow both / Voice only / Not now / Never, of equal weight), and remembered here. Each line is still its own answer in this file, and the
// click on the card is the only thing that ever writes a yes: no card is pre-answered. When only one of the two is due (the other was answered
// earlier), only that one's card is shown, as before.
import fs from 'node:fs'
import path from 'node:path'
import { z } from 'zod'
import { LIVE_CONSENT_VERSION, liveConsentPatch, type LiveSettings, type LiveSettingsPatch } from '../live/settings'

const Answer = z.enum(['unset', 'yes', 'not_now', 'never'])
export type ConsentAnswer = z.infer<typeof Answer>

export const WakeSettingsSchema = z.object({
  wakeListen: z.boolean().default(true),
  wakeChime: z.boolean().default(true),
  // The first conversation has started once: the welcome line is not said again.
  welcomed: z.boolean().default(false),
  // The yes card has been offered once right after first run (so it is never silently missing, and never shown twice by that path).
  consentOffered: z.boolean().default(false),
  voiceAnswer: Answer.default('unset'),
  voiceAskAfterMs: z.number().min(0).default(0),
  screenAnswer: Answer.default('unset'),
  screenAskAfterMs: z.number().min(0).default(0),
})
export type WakeSettings = z.infer<typeof WakeSettingsSchema>
export type WakeSettingsPatch = Partial<WakeSettings>
export const DEFAULT_WAKE_SETTINGS: WakeSettings = WakeSettingsSchema.parse({})

export const NOT_NOW_VOICE_MS = 24 * 3_600_000
export const NOT_NOW_SCREEN_MS = 7 * 24 * 3_600_000

export function coerceWakeSettings(raw: unknown): WakeSettings {
  if (typeof raw !== 'object' || raw === null) return { ...DEFAULT_WAKE_SETTINGS }
  const out: Record<string, unknown> = { ...DEFAULT_WAKE_SETTINGS }
  for (const key of Object.keys(WakeSettingsSchema.shape) as (keyof WakeSettings)[]) {
    if (!(key in raw)) continue
    const parsed = WakeSettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
    if (parsed.success) out[key] = parsed.data
  }
  return out as WakeSettings
}

type Listener = (s: WakeSettings, patch: WakeSettingsPatch) => void

export class WakeSettingsStore {
  private current: WakeSettings
  private readonly file: string | null
  private readonly listeners = new Set<Listener>()

  /** dir === null keeps everything in memory (tests). */
  constructor(dir: string | null) {
    this.file = dir ? path.join(dir, 'wake.json') : null
    this.current = this.load()
  }

  private load(): WakeSettings {
    if (!this.file) return { ...DEFAULT_WAKE_SETTINGS }
    try {
      return coerceWakeSettings(JSON.parse(fs.readFileSync(this.file, 'utf8')))
    } catch {
      return { ...DEFAULT_WAKE_SETTINGS }
    }
  }

  get(): WakeSettings {
    return this.current
  }

  /** Invalid values are dropped key by key. An untrusted source (the debug server, a model tool) may only turn listening or the chime DOWN. */
  patch(raw: unknown, opts: { trusted?: boolean } = {}): WakeSettings {
    const accepted: Record<string, unknown> = {}
    if (typeof raw === 'object' && raw !== null) {
      for (const key of Object.keys(WakeSettingsSchema.shape) as (keyof WakeSettings)[]) {
        if (!(key in raw)) continue
        const parsed = WakeSettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
        if (!parsed.success) continue
        if (!opts.trusted && !(key === 'wakeListen' || key === 'wakeChime') ) continue // consent answers are the trusted card's alone
        if (!opts.trusted && parsed.data === true) continue // and an untrusted source never turns anything up
        accepted[key] = parsed.data
      }
    }
    if (Object.keys(accepted).length === 0) return this.current
    this.current = { ...this.current, ...(accepted as WakeSettingsPatch) }
    this.save()
    for (const l of this.listeners) l(this.current, accepted as WakeSettingsPatch)
    return this.current
  }

  onChange(l: Listener): () => void {
    this.listeners.add(l)
    return () => this.listeners.delete(l)
  }

  private save(): void {
    if (!this.file) return
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true })
      fs.writeFileSync(this.file, JSON.stringify(this.current, null, 2), { mode: 0o600 })
    } catch (err) {
      console.error('[wake] settings save failed:', err instanceof Error ? err.message : 'unknown error')
    }
  }
}

// ------------------------------------------------------------------------------------------------ the first-wake consent steps
export type ConsentCardId = 'voice' | 'screen' | 'both'
export type ConsentStep = { step: 'go' } | { step: 'ask'; card: ConsentCardId } | { step: 'refused'; reason: 'voice_never' | 'voice_not_now' }

/** The screen question is due: not answered, or put off and the week has passed; never when it was refused or frames are already on. */
const screenDue = (w: WakeSettings, live: Pick<LiveSettings, 'liveFrames'>, now: number): boolean => !live.liveFrames && (w.screenAnswer === 'unset' || (w.screenAnswer === 'not_now' && now >= w.screenAskAfterMs))

/**
 * What happens on a wake, given what is remembered: ask, go, or refuse quietly. When the voice question and the screen question are both due they are ONE card
 * ('both': two clear lines, each its own answer); when only one is due, that one alone.
 */
export function consentStep(w: WakeSettings, live: Pick<LiveSettings, 'liveEnabled' | 'liveConsentVersion' | 'liveFrames'>, now: number): ConsentStep {
  const voiceOk = live.liveEnabled && live.liveConsentVersion === LIVE_CONSENT_VERSION
  if (!voiceOk) {
    if (w.voiceAnswer === 'never') return { step: 'refused', reason: 'voice_never' }
    if (w.voiceAnswer === 'not_now' && now < w.voiceAskAfterMs) return { step: 'refused', reason: 'voice_not_now' }
    return { step: 'ask', card: screenDue(w, live, now) ? 'both' : 'voice' }
  }
  if (live.liveFrames || w.screenAnswer === 'never') return { step: 'go' }
  if (screenDue(w, live, now)) return { step: 'ask', card: 'screen' }
  return { step: 'go' }
}

/** voice_only is a button of the combined card only: yes to the voice line, not now to the screen line. */
export type CardChoice = 'yes' | 'not_now' | 'never' | 'voice_only'
export interface ConsentOutcome {
  wake: WakeSettingsPatch
  live: LiveSettingsPatch
}

/**
 * The patches for one card answer. `liveFrames` is the current frame switch (kept when a single voice card is answered yes). The combined card's Yes is the worker's yes to
 * both lines; Voice only says yes to the first and puts the second off for a week; Not now puts the voice question off a day (the screen question is untouched);
 * Never is never for both and turns the listener off.
 */
export function consentOutcome(card: ConsentCardId, choice: CardChoice, liveFrames: boolean, now: Date): ConsentOutcome {
  if (card === 'both') {
    if (choice === 'yes') return { wake: { voiceAnswer: 'yes', screenAnswer: 'yes' }, live: liveConsentPatch({ voice: true, frames: true }, now) }
    if (choice === 'voice_only') return { wake: { voiceAnswer: 'yes', screenAnswer: 'not_now', screenAskAfterMs: now.getTime() + NOT_NOW_SCREEN_MS }, live: liveConsentPatch({ voice: true, frames: false }, now) }
    if (choice === 'never') return { wake: { voiceAnswer: 'never', wakeListen: false, screenAnswer: 'never' }, live: { liveFrames: false } }
    return { wake: { voiceAnswer: 'not_now', voiceAskAfterMs: now.getTime() + NOT_NOW_VOICE_MS }, live: {} }
  }
  const one: 'yes' | 'not_now' | 'never' = choice === 'voice_only' ? 'not_now' : choice
  if (card === 'voice') {
    if (one === 'yes') return { wake: { voiceAnswer: 'yes' }, live: liveConsentPatch({ voice: true, frames: liveFrames }, now) }
    if (one === 'never') return { wake: { voiceAnswer: 'never', wakeListen: false }, live: {} }
    return { wake: { voiceAnswer: 'not_now', voiceAskAfterMs: now.getTime() + NOT_NOW_VOICE_MS }, live: {} }
  }
  if (one === 'yes') return { wake: { screenAnswer: 'yes' }, live: { liveFrames: true } }
  if (one === 'never') return { wake: { screenAnswer: 'never' }, live: { liveFrames: false } }
  return { wake: { screenAnswer: 'not_now', screenAskAfterMs: now.getTime() + NOT_NOW_SCREEN_MS }, live: {} }
}
