// Service interfaces. The DI bag is built in src/main/services.ts; every service has a mock
// (ALONGSIDE_MOCK=1, or ALONGSIDE_MOCK_<NAME>=1 per service) so the pipeline runs from minute one.
import type { FilesService } from './files'
import type {
  AgentChip,
  AgentKind,
  AgentPayload,
  Annotation,
  AttemptRecord,
  CaptionSpeaker,
  GroundResult,
  HelpLevel,
  LearnerSnapshot,
  LessonPlan,
  LessonStep,
  MarkdownEditRequest,
  MarkdownEditResult,
  PersonaId,
  RouteDecision,
  ScamReport,
  Shot,
  ShotPurpose,
  SkillId,
  SkillState,
  StepDoneResult,
  Verdict,
} from './protocol'

export interface Capture {
  grab(purpose: ShotPurpose): Promise<Shot>
  liveFrame(): Promise<{ jpegBase64: string; changeScore: number }>
  // Calls `on(score)` when the primary display changes materially; returns an unsubscribe function.
  watch(on: (score: number) => void): () => void
}

export interface Grounder {
  // One grounding call. Returns found:false when unsure; never fabricates a box. Always sets `label` when found.
  // `precise`: take the slower, more accurate path (flash first). Use it for safetyCritical steps and scam-phrase highlighting.
  ground(req: { target: string; shot?: Shot; hint?: string; precise?: boolean }): Promise<GroundResult>
  // Start grounding in the background (30 s cache) so a later ground({target}) WITHOUT a shot is instant or joins the call.
  // Call it when the screen changes, while the Live model is still narrating. Optional so thin wrappers need not forward it;
  // the real grounder and the mock both implement it: call `grounder.prefetch?.(...)`.
  prefetch?(req: { target: string; shot?: Shot; precise?: boolean }): void
  // The screen changed: drop cached and prefetched results.
  invalidate?(): void
}

export type VerifyRequest = ({ step: LessonStep } | { expected: string }) & { shot?: Shot }
export interface Verifier {
  verify(req: VerifyRequest): Promise<Verdict>
}

export interface LessonArchitect {
  plan(req: { goal: string; learner: LearnerSnapshot; shot?: Shot }): Promise<LessonPlan>
}

export interface ScamAnalyst {
  // `onProgress` gets short plain-English status lines as the check moves through its stages
  // ('Checking the link…', 'Checking the wording…', 'Checking who it says it is…', 'Putting it together…'); show the latest.
  analyze(req: { text?: string; shot?: Shot; url?: string }, opts?: { onProgress?: (message: string) => void }): Promise<ScamReport>
}

export interface Router {
  classify(utterance: string): Promise<RouteDecision>
}

export interface OverlayController {
  show(annotations: Annotation[]): void
  clear(ids?: string[]): void
  caption(speaker: CaptionSpeaker, text: string, final: boolean): void
  chip(level: HelpLevel, label: string): void
}

export interface LiveBridge {
  // Sends text into the active Live session ([RUNNER]/[AGENT_RESULT]/[STALL] stage directions). No-op when not live.
  inject(text: string, opts?: { interrupt?: boolean }): void
}

export interface LearnerStore {
  load(): Promise<LearnerSnapshot>
  save(): Promise<void>
  snapshot(): LearnerSnapshot
  recordAttempt(attempt: AttemptRecord): Promise<LearnerSnapshot>
  addNote(note: string): Promise<void>
  // AGENCY calls this after open_for_me / act_for_me really did something for the learner (never for a dry run). Optional so test bags type-check.
  recordDoneForMe?(key: string): Promise<void>
  // One editable markdown profile; a write needs the revision returned by the last read.
  editMarkdown(req: MarkdownEditRequest): Promise<MarkdownEditResult>
}

export interface LevelDecision {
  state: SkillState
  change: 'up' | 'down' | 'hold'
  reason: string
}

// Pure functions: no I/O, no clocks (time is passed in), no LLM. Deterministic code decides the help level.
export interface LevelEngine {
  initial(now: number): SkillState
  isClean(attempt: AttemptRecord): boolean
  evaluateAttempt(attempt: AttemptRecord, state: SkillState, opts: { demoMode: boolean; now: number }): LevelDecision
  decay(state: SkillState, now: number): SkillState
  // Safety-critical steps never go below L2; `override` is a learner request ("show me again" -> 1, "let me try" -> 4).
  stepLevel(state: SkillState, step: Pick<LessonStep, 'safetyCritical'>, override?: HelpLevel): HelpLevel
}

export interface LessonRunner {
  start(goal: string): Promise<{ lessonId: string; skillId: SkillId; stepCount: number }>
  onStepDone(note?: string): Promise<StepDoneResult>
  onStall(): Promise<void>
  // Grabs a fresh 'verify' shot, calls the Verifier, draws tick/repair, advances or repairs the active step.
  verifyStep(expectedOutcome?: string): Promise<Verdict>
  // Learner asked for a different level, or the model suggested one (advisory; the LevelEngine may overrule).
  requestLevel(level: HelpLevel, reason?: string): Promise<{ applied: boolean; level: HelpLevel; note?: string }>
  end(summary: string, teachBackScore?: number, confidence?: number): Promise<void>
  abort(reason?: string): Promise<void>
}

export interface AgentRuntime {
  spawn(kind: AgentKind, task: string, payload?: AgentPayload): Promise<{ agentId: string }>
  list(): AgentChip[]
  cancel(id: string): void
  // Called once on app quit (cancel running agents, clear timers).
  dispose?(): void
}

export interface Teaching {
  // Builds the Live system instruction: persona x level x settings x learner profile x voice style rules.
  systemInstruction(personaId: PersonaId): Promise<string>
}

export interface Services {
  capture: Capture
  grounder: Grounder
  verifier: Verifier
  architect: LessonArchitect
  scam: ScamAnalyst
  router: Router
  overlay: OverlayController
  live: LiveBridge
  learner: LearnerStore
  levels: LevelEngine
  runner: LessonRunner
  agents: AgentRuntime
  teaching: Teaching
  // FILES (optional so partial test bags still type-check): the local files index. Reveal results via files.resolveIndexedPath.
  files?: FilesService
}

export type ServiceName = keyof Services
