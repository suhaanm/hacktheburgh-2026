import { z } from 'zod'
import { HelpLevelSchema, PersonaIdSchema } from './protocol'

export const SettingsSchema = z.object({
  persona: PersonaIdSchema.nullable().default(null),
  helpLevelMode: z.enum(['auto', 'locked']).default('auto'),
  lockedLevel: HelpLevelSchema.default(2),
  pacing: z.enum(['gentle', 'fast']).default('gentle'),
  voiceSpeed: z.number().min(0.75).max(1.25).default(1),
  captions: z.boolean().default(true),
  textOnly: z.boolean().default(false),
  bigAnnotations: z.boolean().default(true),
  highContrast: z.boolean().default(false),
  dyslexiaFont: z.boolean().default(false),
  explainJargon: z.boolean().default(true),
  teachBack: z.boolean().default(true),
  scamShield: z.boolean().default(true),
  // Both OFF unless the user turns them on; "do it for me" additionally needs a real-click confirmation per action.
  doItForMeAllowed: z.boolean().default(true),
  // AGENCY: how much the assistant may DO for the learner. off = teach only; ask_each = a real-click confirmation before
  // every action; ask_per_task (the default) = confirm the plan once, then the steps run; risky steps still ask.
  // Keep doItForMeAllowed = agency !== 'off'.
  agency: z.enum(['off', 'ask_each', 'ask_per_task', 'autonomous']).default('ask_per_task'),
  // true once the user picked a level themselves (dock Settings or onboarding); until then a saved 'off' / 'ask_each' is migrated to ask_per_task.
  agencyChosen: z.boolean().default(false),
  // autonomous = no confirmation click while the user is away (no keyboard/mouse for awaySeconds) AND a lesson step is stalled;
  // the policy floor never changes. Can only be switched on from the dock Settings UI (main drops it from any other source).
  awaySeconds: z.number().min(3).max(3600).default(60),
  carerSharing: z.boolean().default(false),
  pushToTalkOnly: z.boolean().default(false),
  listeningLight: z.boolean().default(true),
  // One clean attempt is enough to step up a level. Default ON for the hackathon demo; say so honestly on stage.
  demoMode: z.boolean().default(true),
  wakeEnabled: z.boolean().default(true),
  // Look and feel (DESIGN). `glass` makes the dock translucent; opacity is clamped so text stays readable.
  theme: z.enum(['system', 'light', 'dark']).default('system'),
  glass: z.boolean().default(true),
  glassOpacity: z.number().min(0.35).max(1).default(0.4),
  textScale: z.number().min(0.9).max(1.5).default(1),
  userName: z.string().max(60).default(''),
  onboardingDone: z.boolean().default(false),
  // Menu bar (SHELL). The icon is always there while on; launching at login only applies to packaged macOS builds.
  showMenuBarIcon: z.boolean().default(true),
  launchAtLogin: z.boolean().default(false),
  // SHELL2: false (the default, also for older saved profiles without the key) keeps the side panel hidden; the menu bar item
  // and Cmd/Ctrl+Alt+P bring it up. First run (onboardingDone false) always shows it so setup is visible.
  showDock: z.boolean().default(false),
  // FILES: the assistant may search an index of folders the user chose. Folders are added only through a native dialog in main.
  filesEnabled: z.boolean().default(false),
  fileFolders: z.array(z.string().max(1024)).max(20).default([]),
  // NOTIFY: where a permission prompt (ask_user_confirm) appears: a small toast at the top of the screen (plus a macOS
  // notification), or only inside the dock as before.
  confirmStyle: z.enum(['toast', 'dock']).default('toast'),
})

export type Settings = z.infer<typeof SettingsSchema>
export const SettingsPatchSchema = SettingsSchema.partial()
export type SettingsPatch = z.infer<typeof SettingsPatchSchema>

export const DEFAULT_SETTINGS: Settings = SettingsSchema.parse({})

// Keeps the legacy boolean and `agency` in step. A patch that sets `agency` decides; a patch that only sets the boolean
// (older UI) maps true -> the current non-off level (default ask_per_task) and false -> off.
export function reconcileAgency(current: Pick<Settings, 'agency'>, patch: SettingsPatch): SettingsPatch {
  if (patch.agency !== undefined) return { ...patch, doItForMeAllowed: patch.agency !== 'off' }
  if (patch.doItForMeAllowed !== undefined) {
    return { ...patch, agency: patch.doItForMeAllowed ? (current.agency === 'off' ? 'ask_per_task' : current.agency) : 'off' }
  }
  return patch
}

// Keeps every valid key from a (possibly corrupt or older) settings file and defaults the rest.
export function coerceSettings(raw: unknown): Settings {
  if (typeof raw !== 'object' || raw === null) return { ...DEFAULT_SETTINGS }
  const out: Record<string, unknown> = { ...DEFAULT_SETTINGS }
  for (const key of Object.keys(SettingsSchema.shape) as (keyof Settings)[]) {
    if (!(key in raw)) continue
    const parsed = SettingsSchema.shape[key].safeParse((raw as Record<string, unknown>)[key])
    if (parsed.success) out[key] = parsed.data
  }
  // An older file has only the boolean: honour it, then keep the pair consistent.
  if (!('agency' in raw) && out.doItForMeAllowed === true) out.agency = 'ask_per_task'
  out.doItForMeAllowed = out.agency !== 'off'
  return out as Settings
}
