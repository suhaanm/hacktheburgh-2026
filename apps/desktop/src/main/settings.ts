import fs from 'node:fs'
import path from 'node:path'
import { coerceSettings, DEFAULT_SETTINGS, reconcileAgency, SettingsSchema } from '../shared/settings'
import type { Settings, SettingsPatch } from '../shared/settings'

type Listener = (settings: Settings, patch: SettingsPatch) => void

export class SettingsStore {
  private current: Settings
  private readonly file: string | null
  private readonly listeners = new Set<Listener>()
  private saveTimer: NodeJS.Timeout | null = null

  // dir === null keeps everything in memory (tests).
  constructor(dir: string | null) {
    this.file = dir ? path.join(dir, 'settings.json') : null
    this.current = this.load()
  }

  private load(): Settings {
    if (!this.file) return { ...DEFAULT_SETTINGS }
    try {
      const loaded = coerceSettings(JSON.parse(fs.readFileSync(this.file, 'utf8')))
      // Profiles that never chose a level (agencyChosen false) carry 'off' (saved before the assistant could act) or 'ask_each'
      // (the previous default): move them to the current default, ask_per_task (confirm the plan once; risky steps still ask).
      return !loaded.agencyChosen && (loaded.agency === 'off' || loaded.agency === 'ask_each') ? { ...loaded, agency: 'ask_per_task', doItForMeAllowed: true } : loaded
    } catch {
      return { ...DEFAULT_SETTINGS }
    }
  }

  get(): Settings {
    return this.current
  }

  // Invalid values are dropped key by key; the rest of the patch still applies.
  // `trusted` is true ONLY for the dock Settings UI (IPC settings:patch from the renderer). Autonomous agency and its away
  // threshold are dropped from every other source (model tools, /inject, lesson prompts, the debug server, the demo driver).
  patch(raw: unknown, opts: { trusted?: boolean } = {}): Settings {
    if (!opts.trusted && typeof raw === 'object' && raw !== null) {
      const { awaySeconds: _a, ...rest } = raw as Record<string, unknown>
      raw = rest.agency === 'autonomous' ? (({ agency: _g, ...r }) => r)(rest) : rest
    }
    const accepted: Record<string, unknown> = {}
    if (typeof raw === 'object' && raw !== null) {
      for (const key of Object.keys(SettingsSchema.shape) as (keyof Settings)[]) {
        if (!(key in raw)) continue
        const parsed = SettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
        if (parsed.success) accepted[key] = parsed.data
      }
    }
    if (Object.keys(accepted).length === 0) return this.current
    if (opts.trusted && 'agency' in accepted) accepted.agencyChosen = true
    const patch = reconcileAgency(this.current, accepted as SettingsPatch)
    this.current = { ...this.current, ...patch }
    this.scheduleSave()
    for (const listener of this.listeners) listener(this.current, patch)
    return this.current
  }

  onChange(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  flush(): void {
    if (this.saveTimer) clearTimeout(this.saveTimer)
    this.saveTimer = null
    if (!this.file) return
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true })
      fs.writeFileSync(this.file, JSON.stringify(this.current, null, 2))
    } catch (err) {
      console.error('[settings] save failed:', err)
    }
  }

  private scheduleSave(): void {
    if (!this.file) return
    if (this.saveTimer) clearTimeout(this.saveTimer)
    this.saveTimer = setTimeout(() => this.flush(), 300)
  }
}
