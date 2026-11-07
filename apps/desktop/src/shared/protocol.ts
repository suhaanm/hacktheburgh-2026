// Shared domain types. Zod schemas exist wherever data crosses a model boundary
// (structured output from Gemini, tool args from Live). Coordinates everywhere are
// normalised 0-1000, origin top-left of the target display, x right, y down.
import { z } from 'zod'
import type { FilesSearchResult, FilesStatus } from './files'
import type { Settings } from './settings'

// ---------- ids ----------
export const PERSONA_IDS = ['marcus', 'amelia'] as const
export const PersonaIdSchema = z.enum(PERSONA_IDS)
export type PersonaId = z.infer<typeof PersonaIdSchema>

export const HelpLevelSchema = z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)])
export type HelpLevel = z.infer<typeof HelpLevelSchema>

export const HELP_LEVEL_LABELS: Record<HelpLevel, string> = {
  1: 'Watch me',
  2: 'Walk with me',
  3: 'Nudge me',
  4: 'On my own',
}

// 'custom' is one generic skill for goals outside the three built-in lessons (Argon plans those from the live screen).
export const SKILL_IDS = ['video_call', 'spot_scam', 'bigger_text', 'custom'] as const
export const BUILTIN_SKILL_IDS = ['video_call', 'spot_scam', 'bigger_text'] as const
export type BuiltinSkillId = (typeof BUILTIN_SKILL_IDS)[number]
export const SkillIdSchema = z.enum(SKILL_IDS)
export type SkillId = z.infer<typeof SkillIdSchema>

// ---------- geometry (normalised 0-1000) ----------
export const NormPointSchema = z.object({ x: z.number().min(0).max(1000), y: z.number().min(0).max(1000) })
export type NormPoint = z.infer<typeof NormPointSchema>

export const NormBoxSchema = z.object({
  xmin: z.number().min(0).max(1000),
  ymin: z.number().min(0).max(1000),
  xmax: z.number().min(0).max(1000),
  ymax: z.number().min(0).max(1000),
})
export type NormBox = z.infer<typeof NormBoxSchema>

// ---------- screen capture ----------
// 'live': <=1280px wide, q~0.6, overlay may be visible. 'ground'|'verify': up to 1920 wide, overlay hidden during capture.
export type ShotPurpose = 'live' | 'ground' | 'verify'

export interface Shot {
  id: string
  displayId: number
  widthPx: number
  heightPx: number
  scaleFactor: number
  jpegBase64: string
  takenAt: number
  overlayHidden: boolean
}

// ---------- grounding ----------
export const GroundResultSchema = z.object({
  found: z.boolean(),
  box: NormBoxSchema.optional(),
  point: NormPointSchema.optional(),
  confidence: z.number().min(0).max(1),
  label: z.string().optional(),
  reason: z.string().optional(),
  latencyMs: z.number(),
  model: z.string(),
})
export type GroundResult = z.infer<typeof GroundResultSchema>

// ---------- lessons ----------
export const INSTRUCTION_MAX_WORDS = 20

export const LessonStepSchema = z.object({
  id: z.string(),
  index: z.number().int().min(0),
  // Spoken/shown instruction; keep to <= INSTRUCTION_MAX_WORDS words (enforced by prompts + truncateWords, not by rejecting).
  instruction: z.string().min(1).max(200),
  // Purely visual description for the grounder ("blue round button labelled Start call, bottom centre").
  targetDescription: z.string().min(1),
  // What the screen looks like once the step is done; consumed by the verifier.
  expectedOutcome: z.string().min(1),
  hints: z.object({
    l1: z.string(), // demo narration for the ghost cursor
    l2: z.string(), // walk-with-me line
    l3: z.string(), // nudge clue
  }),
  safetyCritical: z.boolean(),
  analogy: z.string().optional(),
})
export type LessonStep = z.infer<typeof LessonStepSchema>

export const LessonPlanSchema = z.object({
  lessonId: z.string(),
  skillId: SkillIdSchema,
  goal: z.string(),
  steps: z.array(LessonStepSchema).min(1).max(12),
})
export type LessonPlan = z.infer<typeof LessonPlanSchema>

export const VerdictSchema = z.object({
  completed: z.boolean(),
  confidence: z.number().min(0).max(1),
  evidence: z.string(),
  uncertain: z.boolean(),
  learnerMisstep: z.string().optional(),
  nextHint: z.string().optional(),
})
export type Verdict = z.infer<typeof VerdictSchema>

export const RouteDecisionSchema = z.object({
  intent: z.enum(['lesson', 'point', 'scam_check', 'settings', 'stop', 'chitchat', 'unknown']),
  skillId: SkillIdSchema.optional(),
  goal: z.string().optional(),
  confidence: z.number().min(0).max(1),
})
export type RouteDecision = z.infer<typeof RouteDecisionSchema>

// ---------- scam shield ----------
export const ScamReportSchema = z.object({
  verdict: z.enum(['likely_scam', 'suspicious', 'likely_genuine', 'cannot_tell']),
  confidence: z.number().min(0).max(1),
  redFlags: z.array(z.object({ phrase: z.string(), why: z.string() })),
  // At most 3 short plain sentences; never says a message is "safe".
  advice: z.array(z.string()).max(3),
  humanHelp: z.string(),
  models: z.array(z.string()),
  latencyMs: z.number(),
})
export type ScamReport = z.infer<typeof ScamReportSchema>

// ---------- agents ----------
export const AGENT_KINDS = ['scam_check', 'lookup', 'lesson_summary'] as const
export const AgentKindSchema = z.enum(AGENT_KINDS)
export type AgentKind = z.infer<typeof AgentKindSchema>

export const AgentPayloadSchema = z.object({
  text: z.string().optional(),
  url: z.string().optional(),
  useScreen: z.boolean().optional(),
})
export type AgentPayload = z.infer<typeof AgentPayloadSchema>

export type AgentResult =
  | { kind: 'scam_check'; report: ScamReport }
  | { kind: 'lookup'; text: string; sources?: string[] }
  | { kind: 'lesson_summary'; text: string }

export interface AgentChip {
  id: string
  kind: AgentKind
  title: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  startedAt: number
  summary?: string
  result?: AgentResult
}

// ---------- learner ----------
export interface SkillState {
  level: HelpLevel
  streakClean: number
  lastSeen: number | null
  nextReview: number | null
}

export interface AttemptRecord {
  id: string
  skillId: SkillId
  lessonId: string
  startedAt: number
  endedAt: number
  levelAtStart: HelpLevel
  levelAtEnd: HelpLevel
  completed: boolean
  hintsUsed: number
  errors: number
  stalls: number
  safetyFlag: boolean
  anxietyPhrase: boolean
  teachBackScore: number | null
  confidence: number | null // 1-5 dial
  clean: boolean
}

export interface ConfidencePoint {
  at: number
  skillId: SkillId
  rating: number
}

export interface LearnerSnapshot {
  // The three built-in skills always exist; `custom` (one generic skill for Argon-planned lessons) appears after first use.
  skills: Record<BuiltinSkillId, SkillState> & { custom?: SkillState }
  confidenceLog: ConfidencePoint[]
  // One entry per finished attempt; drives the hints-per-task chart.
  attempts: AttemptRecord[]
  whatWorks: string[]
  avoidJargon: string[]
  lastSession?: { at: number; skillId?: SkillId; summary: string }
  // AGENCY: how many times the assistant did something FOR the learner, per skill id or goal key; the progress view shows it honestly.
  doneForMe?: Record<string, number>
}

export interface MarkdownEditRequest {
  op: 'read' | 'write'
  content?: string
  // Revision hash from the last read; a write with a stale revision is rejected (no blind overwrite).
  revision?: string
}
export interface MarkdownEditResult {
  ok: boolean
  content: string
  revision: string
  conflict?: boolean
}

// ---------- overlay annotations ----------
export const AnnotationToneSchema = z.enum(['guide', 'success', 'warn', 'danger'])
export type AnnotationTone = z.infer<typeof AnnotationToneSchema>

const AnnotationBaseSchema = z.object({
  id: z.string(),
  tone: AnnotationToneSchema,
  ttlMs: z.number().positive().optional(),
})

export const AnnotationSchema = z.discriminatedUnion('kind', [
  AnnotationBaseSchema.extend({ kind: z.literal('ring'), box: NormBoxSchema, label: z.string().optional(), step: z.number().int().optional() }),
  AnnotationBaseSchema.extend({
    kind: z.literal('arrow'),
    to: z.union([NormPointSchema, NormBoxSchema]),
    from: NormPointSchema.optional(),
  }),
  AnnotationBaseSchema.extend({ kind: z.literal('badge'), at: NormPointSchema, n: z.number().int() }),
  AnnotationBaseSchema.extend({ kind: z.literal('spotlight'), box: NormBoxSchema }),
  // Visual only: the ghost cursor NEVER clicks.
  AnnotationBaseSchema.extend({ kind: z.literal('ghostCursor'), path: z.array(NormPointSchema).min(1), pressAtEnd: z.boolean().optional() }),
  AnnotationBaseSchema.extend({ kind: z.literal('bubble'), at: NormPointSchema, text: z.string() }),
  AnnotationBaseSchema.extend({ kind: z.literal('tick'), box: NormBoxSchema, ok: z.boolean() }),
  AnnotationBaseSchema.extend({ kind: z.literal('highlightText'), boxes: z.array(NormBoxSchema).min(1), note: z.string().optional() }),
])
export type Annotation = z.infer<typeof AnnotationSchema>
export type AnnotationKind = Annotation['kind']

export type CaptionSpeaker = 'user' | 'assistant' | 'system'

export type OverlayCommand =
  | { type: 'show'; annotations: Annotation[] }
  | { type: 'clear'; ids?: string[] }
  | { type: 'caption'; speaker: CaptionSpeaker; text: string; final: boolean }
  | { type: 'chip'; level: HelpLevel; label: string }

// ---------- companion state (main StateStore, broadcast to dock + overlay) ----------
export type Phase = 'asleep' | 'listening_for_name' | 'connecting' | 'live' | 'thinking' | 'speaking' | 'error'

export interface CaptionLine {
  id: string
  speaker: CaptionSpeaker
  text: string
  final: boolean
  at: number
}

export interface ConfirmRequest {
  id: string
  question: string
  options: [string, string]
}

export interface CompanionState {
  persona: PersonaId | null
  phase: Phase
  micMuted: boolean
  level: HelpLevel
  levelLocked: boolean
  skill?: { id: SkillId; name: string; step: number; stepCount: number }
  captions: CaptionLine[]
  agents: AgentChip[]
  settings: Settings
  lastError?: string
  // Set while ask_user_confirm waits; cleared only by a real click (IPC confirm:answer).
  pendingConfirm?: ConfirmRequest
  // NOTIFY: set (by src/main/toast.ts) only while that pendingConfirm is really on screen in the top-right toast; the dock then
  // shows no second prompt. expiresAt = when the confirm manager auto-declines (null: unknown, so no countdown).
  toastConfirm?: { id: string; expiresAt: number | null }
  // FILES: indexing progress and counts for the "Files I can look at" section.
  files?: FilesStatus
}

// State fields a renderer may patch over IPC (everything else is main-owned).
export type RendererStatePatch = Partial<Pick<CompanionState, 'phase' | 'micMuted' | 'lastError'>>

// ---------- sessions ----------
export type SessionSource = 'wake' | 'hotkey' | 'button'
export interface SessionRequest {
  personaId: PersonaId
  source: SessionSource
}
export type SessionEndReason = 'idle' | 'goodbye' | 'stop' | 'error' | 'replaced'

// ---------- Live (renderer) <-> main ----------
export interface LiveToken {
  // Ephemeral auth token (or, in mock mode, the literal "mock"); the real API key never reaches a renderer.
  token: string
  model: string
  expiresAt: number
}
export interface LiveStatus {
  connected: boolean
  phase: Extract<Phase, 'connecting' | 'live' | 'thinking' | 'speaking' | 'error'>
}
export interface LiveTranscript {
  role: 'user' | 'assistant'
  text: string
  final: boolean
}
export interface LiveInject {
  text: string
  interrupt?: boolean
}
export interface LiveFrame {
  jpegBase64: string
  changeScore: number
}

// ---------- Live tool declarations ----------
export const LIVE_TOOL_NAMES = [
  'point_at',
  'start_lesson',
  'step_done',
  'verify_step',
  'set_help_level',
  'spawn_agent',
  'ask_user_confirm',
  'update_profile',
  'end_lesson',
  'clear_annotations',
  'do_it_for_me',
  'open_for_me',
  'act_for_me',
  'search_files',
] as const
export const LiveToolNameSchema = z.enum(LIVE_TOOL_NAMES)
export type LiveToolName = z.infer<typeof LiveToolNameSchema>

export const ToolArgSchemas = {
  point_at: z.object({ target: z.string().min(1), step: z.number().int().optional() }),
  start_lesson: z.object({ goal: z.string().min(1) }),
  step_done: z.object({ note: z.string().optional() }),
  verify_step: z.object({ expected_outcome: z.string().min(1) }),
  set_help_level: z.object({ level: HelpLevelSchema, reason: z.string().optional() }),
  spawn_agent: z.object({ kind: AgentKindSchema, task: z.string().min(1), payload: AgentPayloadSchema.optional() }),
  ask_user_confirm: z.object({ question: z.string().min(1).max(500), options: z.tuple([z.string(), z.string()]) }),
  update_profile: z.object({ note: z.string().min(1) }),
  end_lesson: z.object({
    summary: z.string(),
    teachBackScore: z.number().min(0).max(1).optional(),
    // The learner's 1-5 confidence dial.
    confidence: z.number().int().min(1).max(5).optional(),
  }),
  clear_annotations: z.object({}),
  // Opt-in (settings.doItForMeAllowed, default off): one real click at one grounded target, after a real-click confirmation.
  do_it_for_me: z.object({ target: z.string().min(1) }),
  // AGENCY (settings.agency, default off): open a website/app/file/settings pane after a real-click confirmation; no screenshot, no Accessibility.
  open_for_me: z.object({ kind: z.enum(['url', 'app', 'file', 'settings']), value: z.string().min(1).max(2000) }),
  // AGENCY: a short multi-step task (<= 8 actions), each shown on screen and confirmed per settings.agency; Stop ends it at once.
  act_for_me: z.object({ goal: z.string().min(1).max(500) }),
  // FILES (settings.filesEnabled, default off): search the local index of folders the learner chose; <= 3 short snippets, never a path to read.
  search_files: z.object({ query: z.string().min(1).max(300), k: z.number().int().min(1).max(3).optional() }),
} as const satisfies Record<LiveToolName, z.ZodType>

export type ToolArgs<N extends LiveToolName> = z.infer<(typeof ToolArgSchemas)[N]>

export interface StepDoneResult {
  ok: boolean
  done: boolean
  step?: { index: number; instruction: string }
}

export type DoItForMeCode =
  | 'setting_off' // the learner has not switched "do it for me" on
  | 'sensitive' // money, passwords, sending, deleting, permissions: always left to the learner
  | 'safety_step' // the current lesson step is safety-critical
  | 'scam_check' // a scam check is running
  | 'not_found'
  | 'accessibility' // macOS Accessibility permission missing: show instead of click
  | 'declined' // the learner said no (or never answered)
  | 'stopped' // Stop was pressed
  | 'click_failed'
  | 'clicked'

// allowed:false = the assistant must not click and should teach / show instead. done = exactly one click was performed
// (or only logged when ALONGSIDE_ACTUATOR_DRYRUN=1).
export interface DoItForMeResult {
  allowed: boolean
  done: boolean
  code: DoItForMeCode
  reason: string
  label?: string
  verified?: boolean
  dryRun?: boolean
}

export type AgencyCode =
  | 'agency_off' // settings.agency is off: teach instead
  | 'blocked' // the policy refused (denylist, URL rules, secure field): show instead
  | 'safety_step' // the current lesson step is safety-critical
  | 'scam_check' // a scam check is running
  | 'invalid' // the value could not be used (bad URL, unknown app)
  | 'not_found'
  | 'accessibility' // click/type/keys need macOS Accessibility: guide instead
  | 'declined' // the learner said no (or never answered)
  | 'stopped' // Stop was pressed
  | 'rate_limited'
  | 'busy' // another act_for_me is running
  | 'failed'
  | 'done'
  | 'gave_up' // the loop could not finish within its limits; nothing was retried
  | 'unavailable' // the agentic loop is not switched on in this build

// allowed:false = the assistant must not act and should teach / show instead. done = the task finished (or, for a dry run, was only logged).
export interface AgencyResult {
  allowed: boolean
  done: boolean
  code: AgencyCode
  reason: string
  label?: string
  steps?: number
  verified?: boolean
  dryRun?: boolean
}

export interface ToolResultMap {
  point_at: { found: boolean; confidence: number; note?: string }
  start_lesson: { lessonId: string; skillId: SkillId; stepCount: number }
  step_done: StepDoneResult
  verify_step: Verdict
  set_help_level: { applied: boolean; level: HelpLevel; note?: string }
  spawn_agent: { agentId: string }
  ask_user_confirm: { choice: string | null }
  update_profile: { ok: boolean }
  end_lesson: { ok: boolean }
  clear_annotations: { ok: boolean }
  do_it_for_me: DoItForMeResult
  open_for_me: AgencyResult
  act_for_me: AgencyResult
  search_files: FilesSearchResult
}

export interface ToolError {
  error: string
}
export type ToolResult<N extends LiveToolName = LiveToolName> = ToolResultMap[N] | ToolError

export interface LiveToolCall {
  id?: string
  name: string
  args: unknown
}

// ---------- bus payloads that are reused outside main ----------
export interface LessonStepEvent {
  lessonId: string
  skillId: SkillId
  stepIndex: number
  stepCount: number
  phase: 'started' | 'verified' | 'repair' | 'done' | 'aborted'
  step?: LessonStep
}
export interface LevelChangedEvent {
  skillId: SkillId
  from: HelpLevel
  to: HelpLevel
  reason: string
  scope: 'attempt' | 'step' | 'skill' | 'manual'
}

// ---------- helpers ----------
export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}
export function truncateWords(text: string, max = INSTRUCTION_MAX_WORDS): string {
  const words = text.trim().split(/\s+/).filter(Boolean)
  return words.length <= max ? text.trim() : words.slice(0, max).join(' ')
}
