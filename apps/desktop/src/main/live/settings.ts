// Live voice settings and consent. Their own small store (`live.json` beside `settings.json`), like awareness.json, because the shell track
// owns shared/settings.ts. To fold them in later: copy LiveSettingsSchema's keys into SettingsSchema (same names) and make the patch drop
// the TRUSTED_ONLY keys for untrusted sources. Until then nothing outside this store can switch voice or frames on: the debug server,
// model tools and /inject all patch the main settings store, which does not know these keys.
//
// Everything is OFF by default. A voice session needs: the flags (flags.ts), liveEnabled, and a consent record for the CURRENT consent
// text. Seeing the screen during a session needs liveFrames on top of that, with its own consent line.
import fs from 'node:fs'
import path from 'node:path'
import { z } from 'zod'

export const LIVE_CONSENT_VERSION = 1

// Plain, short, in this order: what is sent, what is skipped, what is kept, where to look, how to stop.
export const LIVE_CONSENT_TEXT =
  'When you hold the talk key, Understudy can listen and answer out loud. Your voice, and only while you hold the key, is sent to a cloud voice model for that conversation. ' +
  'If you also turn on screen looking, a small reduced picture of your screen is sent about every 5 seconds while the conversation is open. ' +
  'Pictures are held in memory only and never saved; sound and words are never saved by Understudy. ' +
  'Nothing is sent while a password manager or banking app is in front, while a password field has focus, while your screen is locked or shared, or while an agent is working for you. ' +
  'Each conversation stops when you stop talking, after a minute of silence, or after five minutes, and it has a spending limit. ' +
  'Pictures are listed in Privacy with their time, size, model and cost, but never the picture. You can turn this off, or pause it for an hour, at any time.'

export const LIVE_CONSENT_SHORT = 'Hold the talk key to speak with Understudy. Voice is sent only while you hold it. Nothing is saved.'

const VOICE_RE = /^[A-Za-z][A-Za-z0-9_-]{1,30}$/

export const LiveSettingsSchema = z.object({
  // Voice conversation on or off. Off until the worker agrees to LIVE_CONSENT_TEXT.
  liveEnabled: z.boolean().default(false),
  // See the screen during a conversation (low-rate frames). Off by default, separate from voice.
  liveFrames: z.boolean().default(false),
  // Dollar caps (estimates): per conversation and per local day. A conversation that would pass either is ended.
  liveSessionUsd: z.number().min(0).max(20).default(0.15),
  liveDailyUsd: z.number().min(0).max(100).default(0.5),
  // Seconds of quiet after the model stops talking (and the key is up) before the conversation ends. Default 8.
  liveGraceMs: z.number().int().min(2000).max(30_000).default(8000),
  // A held key with no sound for this long ends the conversation. Default 60 s.
  liveIdleMs: z.number().int().min(10_000).max(120_000).default(60_000),
  // The hard cap on one conversation. Never above 5 minutes.
  liveMaxMs: z.number().int().min(30_000).max(300_000).default(300_000),
  // At most one frame per this long. Never under 5 s.
  liveFrameIntervalMs: z.number().int().min(5000).max(60_000).default(5000),
  // The Gemini voice (a prebuilt voice name, not a model id).
  liveVoiceName: z.string().regex(VOICE_RE).default('Sulafat'),
  liveConsentVersion: z.number().int().min(0).max(1000).default(0),
  liveConsentAt: z.string().max(40).default(''),
  // "Pause for an hour": epoch ms until which voice (and frames) stay quiet.
  livePausedUntilMs: z.number().min(0).default(0),
})

export type LiveSettings = z.infer<typeof LiveSettingsSchema>
export type LiveSettingsPatch = Partial<LiveSettings>
export const DEFAULT_LIVE_SETTINGS: LiveSettings = LiveSettingsSchema.parse({})

/** Keys only the trusted settings UI (and setConsent) may turn up. An untrusted source may still turn things down. */
export const TRUSTED_ONLY: readonly (keyof LiveSettings)[] = [
  'liveEnabled',
  'liveFrames',
  'liveSessionUsd',
  'liveDailyUsd',
  'liveGraceMs',
  'liveIdleMs',
  'liveMaxMs',
  'liveFrameIntervalMs',
  'liveVoiceName',
  'liveConsentVersion',
  'liveConsentAt',
]

export function coerceLiveSettings(raw: unknown): LiveSettings {
  if (typeof raw !== 'object' || raw === null) return { ...DEFAULT_LIVE_SETTINGS }
  const out: Record<string, unknown> = { ...DEFAULT_LIVE_SETTINGS }
  for (const key of Object.keys(LiveSettingsSchema.shape) as (keyof LiveSettings)[]) {
    if (!(key in raw)) continue
    const parsed = LiveSettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
    if (parsed.success) out[key] = parsed.data
  }
  return out as LiveSettings
}

// True when this key/value only makes voice quieter or cheaper, so an untrusted source may set it.
function isTurningDown(key: keyof LiveSettings, value: unknown, current: LiveSettings): boolean {
  switch (key) {
    case 'liveEnabled':
    case 'liveFrames':
      return value === false
    case 'liveSessionUsd':
    case 'liveDailyUsd':
    case 'liveMaxMs':
    case 'liveIdleMs':
    case 'liveGraceMs':
      return typeof value === 'number' && value <= (current[key] as number)
    case 'liveFrameIntervalMs':
      return typeof value === 'number' && value >= current.liveFrameIntervalMs
    default:
      return false
  }
}

type Listener = (s: LiveSettings, patch: LiveSettingsPatch) => void

export class LiveSettingsStore {
  private current: LiveSettings
  private readonly file: string | null
  private readonly listeners = new Set<Listener>()

  // dir === null keeps everything in memory (tests).
  constructor(dir: string | null, private readonly now: () => number = Date.now) {
    this.file = dir ? path.join(dir, 'live.json') : null
    this.current = this.load()
  }

  private load(): LiveSettings {
    if (!this.file) return { ...DEFAULT_LIVE_SETTINGS }
    try {
      return coerceLiveSettings(JSON.parse(fs.readFileSync(this.file, 'utf8')))
    } catch {
      return { ...DEFAULT_LIVE_SETTINGS }
    }
  }

  get(): LiveSettings {
    return this.current
  }

  /** Invalid values are dropped key by key. `trusted` is true only for the trusted settings UI (the consent card). Others may only turn things down. */
  patch(raw: unknown, opts: { trusted?: boolean } = {}): LiveSettings {
    const accepted: Record<string, unknown> = {}
    if (typeof raw === 'object' && raw !== null) {
      for (const key of Object.keys(LiveSettingsSchema.shape) as (keyof LiveSettings)[]) {
        if (!(key in raw)) continue
        const parsed = LiveSettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
        if (!parsed.success) continue
        if (!opts.trusted && TRUSTED_ONLY.includes(key) && !isTurningDown(key, parsed.data, this.current)) continue
        accepted[key] = parsed.data
      }
    }
    if (Object.keys(accepted).length === 0) return this.current
    this.current = { ...this.current, ...(accepted as LiveSettingsPatch) }
    this.save()
    for (const l of this.listeners) l(this.current, accepted as LiveSettingsPatch)
    return this.current
  }

  pauseFor(ms = 3_600_000): LiveSettings {
    return this.patch({ livePausedUntilMs: this.now() + Math.max(0, ms) })
  }

  resume(): LiveSettings {
    return this.patch({ livePausedUntilMs: 0 })
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
      console.error('[live] settings save failed:', err instanceof Error ? err.message : 'unknown error')
    }
  }
}

/** True when the worker has agreed to the CURRENT consent text and voice is on. */
export function voiceConsent(s: LiveSettings): boolean {
  return s.liveConsentVersion === LIVE_CONSENT_VERSION && s.liveEnabled
}

/** Frames need the voice consent AND their own switch. */
export function frameConsent(s: LiveSettings): boolean {
  return voiceConsent(s) && s.liveFrames
}

export interface LiveConsentChoice {
  voice: boolean
  frames?: boolean
  sessionUsd?: number
  dailyUsd?: number
}

/** The patch the consent card applies (always trusted). Withdrawing (voice false) switches both off and clears the record. */
export function liveConsentPatch(choice: LiveConsentChoice, now: Date = new Date()): LiveSettingsPatch {
  if (!choice.voice) return { liveEnabled: false, liveFrames: false, liveConsentVersion: 0, liveConsentAt: '' }
  return {
    liveEnabled: true,
    liveFrames: choice.frames === true,
    liveConsentVersion: LIVE_CONSENT_VERSION,
    liveConsentAt: now.toISOString(),
    ...(choice.sessionUsd !== undefined ? { liveSessionUsd: Math.max(0, choice.sessionUsd) } : {}),
    ...(choice.dailyUsd !== undefined ? { liveDailyUsd: Math.max(0, choice.dailyUsd) } : {}),
  }
}
