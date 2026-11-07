// Awareness settings and consent (REQ-5, AWR-1 to AWR-6).
//
// MERGE NOTE: these keys live here, with their own small store (`awareness.json` beside `settings.json`), because the shell
// track owns shared/settings.ts and SettingsStore. To fold them in later: copy AwarenessSettingsSchema's keys into
// SettingsSchema (same names), and make SettingsStore.patch drop the TRUSTED_ONLY keys for untrusted sources the way it
// already does for `awaySeconds`. Until then nothing outside this store can switch a glance on: the debug server, model tools
// and /inject all patch the main settings store, which does not know these keys.
//
// Everything is OFF by default. A glance needs: the layer flag, awarenessEnabled, the matching consent (glanceOnTrigger or
// glancePeriodic) AND a consent record for the current consent text (glanceConsentVersion). All of it is checked in code.
import fs from 'node:fs'
import path from 'node:path'
import { z } from 'zod'
import { APP_NAME } from '../../shared/brand'

export const CONSENT_VERSION = 1

// Plain, short, in this order: what is sent, what is skipped, what is kept, where to look, how to stop.
export const CONSENT_TEXT =
  `${APP_NAME} can take a quick look at your screen when you seem stuck, when you press its shortcut and, only if you turn it on, about every 30 seconds. ` +
  'Each look sends one small, reduced picture of your screen to a cloud vision model, which tells it what kind of app you are in and what seems to be in the way. ' +
  `The picture leaves this Mac for that one call, is held in memory only, and is never saved by ${APP_NAME}; what comes back is a few fixed labels, not text. ` +
  'Nothing is sent while a password manager or banking app is in front, while a password field has focus, while your screen is locked or shared, or while you are away. ' +
  'Messaging and mail apps are skipped too unless you switch strict mode off. ' +
  'Every call is listed in Privacy with its time, size, model and cost, but never the picture. ' +
  'You can turn this off, pause it for an hour, or add apps to skip, at any time.'

export const CONSENT_SHORT = 'Look at my screen when I seem stuck. Nothing is saved. See every call in Privacy.'

const BUNDLE_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{1,120}(\.\*)?$/ // a bundle id, or a prefix ending in ".*"

export const AwarenessSettingsSchema = z.object({
  // Master switch for the always-on layer (cursor features, app kind). Nothing leaves the Mac from this layer alone.
  awarenessEnabled: z.boolean().default(false),
  // Consent for triggered glances (stuck, loop, hotkey). Off until the worker agrees to CONSENT_TEXT.
  glanceOnTrigger: z.boolean().default(false),
  // Consent for the periodic glance. Off by default, separate from the triggered one.
  glancePeriodic: z.boolean().default(false),
  // Periodic spacing in seconds: default 30, never below 15.
  glanceIntervalSec: z.number().int().min(15).max(600).default(30),
  // Strict: unknown app or unknown secure-input state means no glance; messaging and mail apps are skipped.
  glanceStrict: z.boolean().default(true),
  // The worker's own bundle ids to skip (exact, or a prefix ending in ".*"). Added to the default categories, never replacing them.
  glanceDenylist: z.array(z.string().regex(BUNDLE_RE)).max(200).default([]),
  // Dollar cap per local day for glances; the call that would pass it is not made.
  glanceDailyUsd: z.number().min(0).max(100).default(0.5),
  // Calls per rolling hour.
  glanceMaxPerHour: z.number().int().min(1).max(600).default(60),
  // Which consent text the worker agreed to; 0 = none. A glance setting is ignored unless this equals CONSENT_VERSION.
  glanceConsentVersion: z.number().int().min(0).max(1000).default(0),
  glanceConsentAt: z.string().max(40).default(''),
  // "Pause for an hour": epoch ms until which everything in this layer that looks at the screen stays quiet.
  glancePausedUntilMs: z.number().min(0).default(0),
})

export type AwarenessSettings = z.infer<typeof AwarenessSettingsSchema>
export type AwarenessSettingsPatch = Partial<AwarenessSettings>
export const DEFAULT_AWARENESS_SETTINGS: AwarenessSettings = AwarenessSettingsSchema.parse({})

/** Keys only the trusted settings UI (and setConsent) may turn up. An untrusted source may still turn things down. */
export const TRUSTED_ONLY: readonly (keyof AwarenessSettings)[] = [
  'awarenessEnabled',
  'glanceOnTrigger',
  'glancePeriodic',
  'glanceIntervalSec',
  'glanceStrict',
  'glanceDenylist',
  'glanceDailyUsd',
  'glanceMaxPerHour',
  'glanceConsentVersion',
  'glanceConsentAt',
]

export function normaliseDenylist(list: readonly string[]): string[] {
  const out = new Set<string>()
  for (const raw of list) {
    const s = raw.trim().toLowerCase()
    if (BUNDLE_RE.test(s)) out.add(s)
    if (out.size >= 200) break
  }
  return [...out].sort()
}

export function coerceAwarenessSettings(raw: unknown): AwarenessSettings {
  if (typeof raw !== 'object' || raw === null) return { ...DEFAULT_AWARENESS_SETTINGS }
  const out: Record<string, unknown> = { ...DEFAULT_AWARENESS_SETTINGS }
  for (const key of Object.keys(AwarenessSettingsSchema.shape) as (keyof AwarenessSettings)[]) {
    if (!(key in raw)) continue
    let value = (raw as Record<string, unknown>)[key]
    // A saved file is read leniently: one bad bundle id costs that entry, not the whole list.
    if (key === 'glanceDenylist' && Array.isArray(value)) value = normaliseDenylist(value.filter((v): v is string => typeof v === 'string'))
    const parsed = AwarenessSettingsSchema.shape[key].safeParse(value)
    if (parsed.success) out[key] = parsed.data
  }
  out.glanceDenylist = normaliseDenylist(out.glanceDenylist as string[])
  return out as AwarenessSettings
}

/** True when this key/value only makes the layer quieter, so an untrusted source may set it. */
function isTurningDown(key: keyof AwarenessSettings, value: unknown, current: AwarenessSettings): boolean {
  switch (key) {
    case 'awarenessEnabled':
    case 'glanceOnTrigger':
    case 'glancePeriodic':
      return value === false
    case 'glanceStrict':
      return value === true
    case 'glanceIntervalSec':
      return typeof value === 'number' && value >= current.glanceIntervalSec
    case 'glanceDailyUsd':
      return typeof value === 'number' && value <= current.glanceDailyUsd
    case 'glanceMaxPerHour':
      return typeof value === 'number' && value <= current.glanceMaxPerHour
    case 'glanceDenylist': {
      if (!Array.isArray(value)) return false
      const next = new Set(normaliseDenylist(value as string[]))
      return current.glanceDenylist.every((b) => next.has(b)) // may only add
    }
    default:
      return false
  }
}

type Listener = (s: AwarenessSettings, patch: AwarenessSettingsPatch) => void

export class AwarenessSettingsStore {
  private current: AwarenessSettings
  private readonly file: string | null
  private readonly listeners = new Set<Listener>()

  // dir === null keeps everything in memory (tests).
  constructor(dir: string | null, private readonly now: () => number = Date.now) {
    this.file = dir ? path.join(dir, 'awareness.json') : null
    this.current = this.load()
  }

  private load(): AwarenessSettings {
    if (!this.file) return { ...DEFAULT_AWARENESS_SETTINGS }
    try {
      return coerceAwarenessSettings(JSON.parse(fs.readFileSync(this.file, 'utf8')))
    } catch {
      return { ...DEFAULT_AWARENESS_SETTINGS }
    }
  }

  get(): AwarenessSettings {
    return this.current
  }

  /**
   * Invalid values are dropped key by key. `trusted` is true only for the trusted settings UI path (the consent card and the
   * Privacy screen). Any other source can pause the layer and turn things down, never up.
   */
  patch(raw: unknown, opts: { trusted?: boolean } = {}): AwarenessSettings {
    const accepted: Record<string, unknown> = {}
    if (typeof raw === 'object' && raw !== null) {
      for (const key of Object.keys(AwarenessSettingsSchema.shape) as (keyof AwarenessSettings)[]) {
        if (!(key in raw)) continue
        const parsed = AwarenessSettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
        if (!parsed.success) continue
        let value: unknown = parsed.data
        if (key === 'glanceDenylist') value = normaliseDenylist(value as string[])
        if (!opts.trusted && TRUSTED_ONLY.includes(key) && !isTurningDown(key, value, this.current)) continue
        accepted[key] = value
      }
    }
    if (Object.keys(accepted).length === 0) return this.current
    this.current = { ...this.current, ...(accepted as AwarenessSettingsPatch) }
    this.save()
    for (const l of this.listeners) l(this.current, accepted as AwarenessSettingsPatch)
    return this.current
  }

  /** Pause the layer for `ms` (an hour by default). Allowed from any source. */
  pauseFor(ms = 3_600_000): AwarenessSettings {
    return this.patch({ glancePausedUntilMs: this.now() + Math.max(0, ms) })
  }

  resume(): AwarenessSettings {
    return this.patch({ glancePausedUntilMs: 0 })
  }

  onChange(l: Listener): () => void {
    this.listeners.add(l)
    return () => this.listeners.delete(l)
  }

  private save(): void {
    if (!this.file) return
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true })
      fs.writeFileSync(this.file, JSON.stringify(this.current, null, 2))
    } catch (err) {
      console.error('[awareness] settings save failed:', err instanceof Error ? err.message : 'unknown error')
    }
  }
}

/** True when the worker has agreed to the CURRENT consent text and the matching consent switch is on. */
export function consentFor(s: AwarenessSettings, kind: 'trigger' | 'periodic'): boolean {
  if (s.glanceConsentVersion !== CONSENT_VERSION) return false
  return kind === 'trigger' ? s.glanceOnTrigger : s.glancePeriodic
}

export interface ConsentChoice {
  // The worker agreed to triggered glances (stuck, loop, hotkey).
  trigger: boolean
  // The worker also agreed to the periodic glance.
  periodic?: boolean
  strict?: boolean
  intervalSec?: number
  dailyUsd?: number
}

/** The patch the consent card applies (always trusted). Withdrawing consent (trigger false) switches both off and clears the record. */
export function consentPatch(choice: ConsentChoice, now: Date = new Date()): AwarenessSettingsPatch {
  if (!choice.trigger) {
    return { glanceOnTrigger: false, glancePeriodic: false, glanceConsentVersion: 0, glanceConsentAt: '' }
  }
  return {
    awarenessEnabled: true,
    glanceOnTrigger: true,
    glancePeriodic: choice.periodic === true,
    glanceConsentVersion: CONSENT_VERSION,
    glanceConsentAt: now.toISOString(),
    ...(choice.strict !== undefined ? { glanceStrict: choice.strict } : {}),
    ...(choice.intervalSec !== undefined ? { glanceIntervalSec: Math.max(15, Math.round(choice.intervalSec)) } : {}),
    ...(choice.dailyUsd !== undefined ? { glanceDailyUsd: Math.max(0, choice.dailyUsd) } : {}),
  }
}
