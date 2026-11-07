// The onboarding state machine and the pure mappings from answers to settings and profile lines.
// No React, no IPC: everything here is unit-tested. Screens call `reduce`; persistence lives in persist.ts.
import type { PersonaId } from '../../../shared/protocol'
import type { Settings, SettingsPatch } from '../../../shared/settings'

export type Agency = Settings['agency']
export type Theme = Settings['theme']
export type Pacing = Settings['pacing']

export type OnboardingSettingsPatch = SettingsPatch
export type OnboardingSettingsView = Partial<{
  userName: string
  pacing: Pacing
  textScale: number
  dyslexiaFont: boolean
  highContrast: boolean
  textOnly: boolean
  voiceSpeed: number
  theme: Theme
  glass: boolean
  glassOpacity: number
  persona: PersonaId | null
  agency: Agency
  filesEnabled: boolean
}>

export const STEP_IDS = ['hello', 'about', 'style', 'comfort', 'look', 'helper', 'permissions', 'hands', 'ready'] as const
export type StepId = (typeof STEP_IDS)[number]

export const STEP_TITLES: Readonly<Record<StepId, string>> = {
  hello: 'Hello',
  about: 'About you',
  style: 'How you like to learn',
  comfort: 'Make it comfortable',
  look: 'Look and feel',
  helper: 'Choose your helper',
  permissions: 'Allow what I need',
  hands: 'Helping hands',
  ready: 'All set',
}

export const TOPICS = [
  { id: 'calls', label: 'Video calls', phrase: 'video calls' },
  { id: 'messages', label: 'Messages and email', phrase: 'messages and email' },
  { id: 'photos', label: 'Photos', phrase: 'photos' },
  { id: 'scams', label: 'Staying safe from scams', phrase: 'staying safe from scams' },
  { id: 'health', label: 'Health and NHS apps', phrase: 'health and NHS apps' },
  { id: 'shopping', label: 'Shopping', phrase: 'shopping' },
  { id: 'other', label: 'Something else', phrase: 'something else' },
] as const
export type TopicId = (typeof TOPICS)[number]['id']

export const COMFORT_LEVELS = [
  { value: 1, label: 'Just starting out' },
  { value: 2, label: 'A little' },
  { value: 3, label: 'Getting by' },
  { value: 4, label: 'Fairly good' },
  { value: 5, label: 'Very comfortable' },
] as const
export type Comfort = (typeof COMFORT_LEVELS)[number]['value']

export const TEXT_SIZES = [
  { value: 1, label: 'Standard' },
  { value: 1.15, label: 'Large' },
  { value: 1.3, label: 'Larger' },
  { value: 1.5, label: 'Largest' },
] as const

export const VOICE_SPEEDS = [
  { value: 0.85, label: 'Slower' },
  { value: 1, label: 'Normal' },
  { value: 1.15, label: 'Faster' },
] as const

export const AGENCY_CHOICES: readonly { value: Agency; title: string; line?: string }[] = [
  { value: 'off', title: 'Just teach me', line: 'I show you where to click. You do it.' },
  { value: 'ask_each', title: 'Do things when I ask, and always ask me first' },
  { value: 'ask_per_task', title: 'Do things when I ask, and ask me once for each job' },
]

export interface Answers {
  userName: string
  topics: TopicId[]
  comfort: Comfort | null
  pacing: Pacing
  textScale: number
  dyslexiaFont: boolean
  highContrast: boolean
  textOnly: boolean
  voiceSpeed: number
  theme: Theme
  glass: boolean
  glassOpacity: number
  persona: PersonaId
  agency: Agency
  filesEnabled: boolean
}

export const GLASS_MIN = 0.35
export const GLASS_MAX = 1

/** Letters, spaces, apostrophes and hyphens only: the name reaches the model's context, so it can never carry instructions. */
export function cleanName(raw: string): string {
  return raw
    .normalize('NFC')
    .replace(/\s+/g, ' ')
    .replace(/[^\p{L}\p{M}' -]/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 40)
}

const clamp = (n: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, n))

export function initialAnswers(current: OnboardingSettingsView, defaultPersona: PersonaId): Answers {
  return {
    userName: current.userName ?? '',
    topics: [],
    comfort: null,
    pacing: current.pacing ?? 'gentle',
    textScale: current.textScale ?? 1,
    dyslexiaFont: current.dyslexiaFont ?? false,
    highContrast: current.highContrast ?? false,
    textOnly: current.textOnly ?? false,
    voiceSpeed: current.voiceSpeed ?? 1,
    theme: current.theme ?? 'system',
    glass: current.glass ?? true,
    glassOpacity: clamp(current.glassOpacity ?? 0.4, GLASS_MIN, GLASS_MAX),
    persona: current.persona ?? defaultPersona,
    agency: current.agency ?? 'off',
    filesEnabled: current.filesEnabled ?? false,
  }
}

/** The settings that an answer change should write straight away, so the dock itself is the live preview. */
export function answersToSettings(patch: Partial<Answers>): OnboardingSettingsPatch {
  const out: OnboardingSettingsPatch = {}
  if (patch.userName !== undefined) out.userName = cleanName(patch.userName)
  if (patch.pacing !== undefined) out.pacing = patch.pacing
  if (patch.textScale !== undefined) out.textScale = clamp(patch.textScale, 0.9, 1.5)
  if (patch.dyslexiaFont !== undefined) out.dyslexiaFont = patch.dyslexiaFont
  if (patch.highContrast !== undefined) out.highContrast = patch.highContrast
  if (patch.textOnly !== undefined) out.textOnly = patch.textOnly
  if (patch.voiceSpeed !== undefined) out.voiceSpeed = clamp(patch.voiceSpeed, 0.75, 1.25)
  if (patch.theme !== undefined) out.theme = patch.theme
  if (patch.glass !== undefined) out.glass = patch.glass
  if (patch.glassOpacity !== undefined) out.glassOpacity = clamp(patch.glassOpacity, GLASS_MIN, GLASS_MAX)
  if (patch.persona !== undefined) out.persona = patch.persona
  if (patch.agency !== undefined) out.agency = patch.agency
  if (patch.filesEnabled !== undefined) out.filesEnabled = patch.filesEnabled
  return out
}

// ---------- state machine ----------
export type Touched = Partial<Record<keyof Answers, true>>

export interface FlowState {
  step: number
  answers: Answers
  /** Which answers the person actually gave; defaults they never touched are not written to their profile. */
  touched: Touched
}

export type FlowAction = { type: 'next' } | { type: 'back' } | { type: 'go'; step: number } | { type: 'set'; patch: Partial<Answers> }

export const LAST_STEP = STEP_IDS.length - 1

export function startFlow(answers: Answers): FlowState {
  return { step: 0, answers, touched: {} }
}

export function reduce(state: FlowState, action: FlowAction): FlowState {
  switch (action.type) {
    case 'next':
      return { ...state, step: Math.min(LAST_STEP, state.step + 1) }
    case 'back':
      return { ...state, step: Math.max(0, state.step - 1) }
    case 'go':
      return { ...state, step: clamp(Math.trunc(action.step), 0, LAST_STEP) }
    case 'set': {
      const touched = { ...state.touched }
      for (const key of Object.keys(action.patch) as (keyof Answers)[]) touched[key] = true
      return { ...state, answers: { ...state.answers, ...action.patch }, touched }
    }
  }
}

export const stepId = (state: FlowState): StepId => STEP_IDS[state.step]!
export const isLastStep = (state: FlowState): boolean => state.step >= LAST_STEP
export const canGoBack = (state: FlowState): boolean => state.step > 0
export const progressLabel = (state: FlowState): string => `Step ${state.step + 1} of ${STEP_IDS.length}`

export function toggleTopic(topics: readonly TopicId[], id: TopicId): TopicId[] {
  return topics.includes(id) ? topics.filter((t) => t !== id) : TOPICS.map((t) => t.id).filter((t) => t === id || topics.includes(t))
}

export function nextLabel(id: StepId): string {
  switch (id) {
    case 'hello':
      return 'Begin'
    case 'ready':
      return 'Start'
    default:
      return 'Next'
  }
}

// ---------- the learner profile ----------
export interface ProfileLines {
  about: string[]
  goals: string[]
  whatWorks: string[]
}

/** Lines the flow owns in profile.md. Re-running replaces exactly these and never touches anything else. */
const OWNED: readonly RegExp[] = [
  /^call me /i,
  /^comfort with computers: /i,
  /^i want help with /i,
  /^i like bigger text/i,
  /^i find a dyslexia-friendly font/i,
  /^i need high contrast/i,
  /^i prefer to read replies/i,
  /^i like a (slower|faster) voice/i,
  /^gentle and slow help works for me/i,
  /^quick, short answers work for me/i,
]

export const isOwnedLine = (text: string): boolean => OWNED.some((re) => re.test(text.trim()))

export function profileLines(answers: Answers, touched: Touched): ProfileLines {
  const about: string[] = []
  const name = cleanName(answers.userName)
  if (name) about.push(`Call me ${name}`)
  if (answers.comfort !== null) about.push(`Comfort with computers: ${COMFORT_LEVELS.find((c) => c.value === answers.comfort)!.label.toLowerCase()}`)
  if (answers.textScale >= 1.15) about.push('I like bigger text')
  if (answers.dyslexiaFont) about.push('I find a dyslexia-friendly font easier to read')
  if (answers.highContrast) about.push('I need high contrast')
  if (answers.textOnly) about.push('I prefer to read replies rather than hear them')
  if (answers.voiceSpeed <= 0.9) about.push('I like a slower voice')
  else if (answers.voiceSpeed >= 1.1) about.push('I like a faster voice')

  const goals = answers.topics.map((id) => `I want help with ${TOPICS.find((t) => t.id === id)!.phrase}`)

  const whatWorks: string[] = []
  if (touched.pacing) whatWorks.push(answers.pacing === 'gentle' ? 'Gentle and slow help works for me' : 'Quick, short answers work for me')
  return { about, goals, whatWorks }
}

export const hasProfileLines = (lines: ProfileLines): boolean => lines.about.length + lines.goals.length + lines.whatWorks.length > 0

// ---------- plain-words hotkey label ----------
// src/main/hotkey.ts owns the real combination (it imports Electron, so a renderer cannot import it); a test keeps this in step.
export const HOTKEY_ACCELERATOR = 'CommandOrControl+Alt+Space'

export function hotkeyLabel(platform: string): string {
  return /mac|iphone|ipad/i.test(platform) ? 'Command + Option + Space' : 'Control + Alt + Space'
}
