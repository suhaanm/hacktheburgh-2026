// Mock implementations of every service: realistic canned data so the whole pipeline runs with no key, no screen, no voice.
// Real implementations replace these one line at a time in services.ts. Each factory is lazy about `s` (the service bag).
import { randomUUID } from 'node:crypto'
import type {
  AgentRuntime,
  Capture,
  Grounder,
  LearnerStore,
  LessonArchitect,
  LessonRunner,
  LevelDecision,
  LevelEngine,
  LiveBridge,
  OverlayController,
  Router,
  ScamAnalyst,
  Services,
  Teaching,
  Verifier,
} from '../shared/contracts'
import { HELP_LEVEL_LABELS } from '../shared/protocol'
import type {
  AgentChip,
  AttemptRecord,
  HelpLevel,
  LearnerSnapshot,
  LessonPlan,
  LessonStep,
  MarkdownEditResult,
  NormBox,
  SkillId,
  SkillState,
  Verdict,
} from '../shared/protocol'
import { SKILL_IDS } from '../shared/protocol'
import type { ServiceContext } from './context'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

// 1x1 grey JPEG; mocks never send it anywhere.
const TINY_JPEG =
  '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA='

// ---- Capture (owner: OVERLAY) ----
export function mockCapture(): Capture {
  return {
    async grab(purpose) {
      return {
        id: randomUUID(),
        displayId: 1,
        widthPx: purpose === 'live' ? 1280 : 1920,
        heightPx: purpose === 'live' ? 720 : 1080,
        scaleFactor: 2,
        jpegBase64: TINY_JPEG,
        takenAt: Date.now(),
        overlayHidden: purpose !== 'live',
      }
    },
    async liveFrame() {
      return { jpegBase64: TINY_JPEG, changeScore: 0 }
    },
    watch() {
      return () => undefined
    },
  }
}

// ---- Grounder (owner: SERVICES) ----
const CANNED_BOXES: [RegExp, NormBox][] = [
  [/start call|join call|call button/i, { xmin: 420, ymin: 800, xmax: 580, ymax: 880 }],
  [/mute|microphone/i, { xmin: 300, ymin: 800, xmax: 380, ymax: 880 }],
  [/camera|video button/i, { xmin: 620, ymin: 800, xmax: 700, ymax: 880 }],
  [/text size|bigger|larger|font/i, { xmin: 560, ymin: 300, xmax: 860, ymax: 380 }],
  [/message|text from|scam|bank/i, { xmin: 120, ymin: 260, xmax: 520, ymax: 360 }],
]
export function mockGrounder(): Grounder {
  return {
    async ground({ target }) {
      const started = Date.now()
      await sleep(180)
      if (/nonexistent|not here|unicorn/i.test(target)) {
        return { found: false, confidence: 0.1, reason: 'mock: target not on screen', latencyMs: Date.now() - started, model: 'mock' }
      }
      const box = CANNED_BOXES.find(([re]) => re.test(target))?.[1] ?? { xmin: 430, ymin: 430, xmax: 570, ymax: 520 }
      return {
        found: true,
        box,
        point: { x: (box.xmin + box.xmax) / 2, y: (box.ymin + box.ymax) / 2 },
        confidence: 0.92,
        label: target,
        latencyMs: Date.now() - started,
        model: 'mock',
      }
    },
    prefetch() {},
    invalidate() {},
  }
}

// ---- Verifier (owner: SERVICES) ----
export function mockVerifier(): Verifier {
  return {
    async verify() {
      await sleep(150)
      const verdict: Verdict = { completed: true, confidence: 0.9, evidence: 'mock: the expected change is visible', uncertain: false }
      return verdict
    },
  }
}

// ---- LessonArchitect (owner: SERVICES) ----
function step(index: number, instruction: string, target: string, expected: string, l1: string, l2: string, l3: string, safetyCritical = false): LessonStep {
  return {
    id: `step-${index + 1}`,
    index,
    instruction,
    targetDescription: target,
    expectedOutcome: expected,
    hints: { l1, l2, l3 },
    safetyCritical,
  }
}

const STATIC_STEPS: Record<SkillId, { goal: string; steps: LessonStep[] }> = {
  video_call: {
    goal: 'Join a video call with family',
    steps: [
      step(0, 'Find the green Start call button.', 'big green button labelled Start call, bottom centre', 'The call window is open and shows a waiting screen', 'Watch the arrow: this button starts the call.', 'Click the green Start call button.', 'Look near the bottom of the window.'),
      step(1, 'Allow the camera when asked.', 'dialog button labelled Allow, centre', 'The camera preview shows your face', 'The pop-up wants permission to use the camera.', 'Click Allow in the pop-up.', 'There is a pop-up in the middle.'),
      step(2, 'Check the microphone is not crossed out.', 'round microphone button, bottom left of the call', 'The microphone icon has no red line through it', 'A red line means you are muted.', 'Click the microphone if it has a red line.', 'Look at the round icon on the left.'),
      step(3, 'Press Join now.', 'blue Join now button, right side', 'You can see the other person on screen', 'This puts you in the room with them.', 'Click Join now.', 'It is the blue button on the right.'),
    ],
  },
  spot_scam: {
    goal: 'Check a suspicious text message',
    steps: [
      step(0, 'Open the message from the bank.', 'message row from Bank Alerts in the inbox list', 'The message text is fully visible', 'Open it, but do not tap any link.', 'Click the message in the list.', 'It is the top message.'),
      step(1, 'Find the link in the message.', 'blue underlined link in the message body', 'The link is highlighted', 'Links can hide where they really go.', 'Point at the link without clicking.', 'It is underlined and blue.', true),
      step(2, 'Ask the checker to look at it.', 'Check this message button, top right', 'A checker result card is visible', 'Let me take a careful look for you.', 'Click Check this message.', 'Top right corner.'),
      step(3, 'Decide: ring your bank on the number on your card.', 'the Delete message button', 'The message has been deleted without clicking the link', 'Never use the number in the message.', 'Click Delete, then ring the number on your card.', 'Bottom of the message.', true),
    ],
  },
  custom: {
    goal: 'Work something out together',
    steps: [step(0, 'Look at the highlighted part.', 'the control the learner asked about', 'The learner has found it', 'This is the thing you asked about.', 'Look where the arrow points.', 'Look in the middle of the window.')],
  },
  bigger_text: {
    goal: 'Make the text bigger',
    steps: [
      step(0, 'Open Settings.', 'gear icon labelled Settings in the dock', 'The Settings window is open', 'This is the control room for your computer.', 'Click the gear icon.', 'Bottom left.'),
      step(1, 'Choose Display.', 'sidebar item labelled Display', 'The Display page is showing', 'Display holds anything about the screen.', 'Click Display.', 'In the list on the left.'),
      step(2, 'Drag the Text size slider right.', 'slider labelled Text size', 'The sample text looks larger', 'Right makes words bigger.', 'Drag the slider to the right.', 'The slider near the top.'),
      step(3, 'Press Apply.', 'button labelled Apply, bottom right', 'The whole screen text is now larger', 'This saves your choice.', 'Click Apply.', 'Bottom right.'),
    ],
  },
}

export function pickSkill(goal: string): SkillId {
  if (/scam|suspicious|message|text from|bank|phish/i.test(goal)) return 'spot_scam'
  if (/bigger|larger|text size|font|read|small/i.test(goal)) return 'bigger_text'
  return 'video_call'
}

export function mockArchitect(): LessonArchitect {
  return {
    async plan({ goal }) {
      await sleep(250)
      const skillId = pickSkill(goal)
      const template = STATIC_STEPS[skillId]
      const plan: LessonPlan = { lessonId: `lesson-${randomUUID().slice(0, 8)}`, skillId, goal: goal || template.goal, steps: template.steps }
      return plan
    },
  }
}

// ---- ScamAnalyst (owner: SERVICES) ----
export function mockScam(): ScamAnalyst {
  return {
    async analyze(_req, opts) {
      opts?.onProgress?.('Checking the link…')
      opts?.onProgress?.('Checking the wording…')
      opts?.onProgress?.('Checking who it says it is…')
      await sleep(250)
      opts?.onProgress?.('Putting it together…')
      await sleep(150)
      return {
        verdict: 'likely_scam',
        confidence: 0.86,
        redFlags: [
          { phrase: 'Your account will be closed in 24 hours', why: 'Real banks do not threaten you with a deadline in a text.' },
          { phrase: 'Tap here to verify', why: 'Links in texts can lead to fake sites that steal passwords.' },
        ],
        advice: ['Do not tap the link.', 'Ring the number on the back of your bank card.', 'Ask someone you trust if you are unsure.'],
        humanHelp: 'Ring the number on your bank card, or Age UK on 0800 678 1602.',
        models: ['mock'],
        latencyMs: 400,
      }
    },
  }
}

// ---- Router (owner: SERVICES) ----
export function mockRouter(): Router {
  return {
    async classify(utterance) {
      const text = utterance.toLowerCase()
      if (/\b(stop|goodbye|bye)\b/.test(text)) return { intent: 'stop', confidence: 0.9 }
      if (/scam|suspicious|fake|phish/.test(text)) return { intent: 'scam_check', skillId: 'spot_scam', confidence: 0.8 }
      if (/bigger|larger|text size|too small/.test(text)) return { intent: 'lesson', skillId: 'bigger_text', goal: 'Make the text bigger', confidence: 0.8 }
      if (/call|video|zoom|facetime/.test(text)) return { intent: 'lesson', skillId: 'video_call', goal: 'Join a video call', confidence: 0.8 }
      if (/where|which|show me/.test(text)) return { intent: 'point', confidence: 0.6 }
      return { intent: 'unknown', confidence: 0.3 }
    },
  }
}

// ---- OverlayController (owner: OVERLAY). Used only with ALONGSIDE_MOCK_OVERLAY=1; the default is the IPC stub. ----
export function mockOverlay(ctx: ServiceContext): OverlayController {
  return {
    show: (annotations) => ctx.log('mock-overlay', 'show', annotations.map((a) => a.kind).join(',')),
    clear: (ids) => ctx.log('mock-overlay', 'clear', ids?.join(',') ?? 'all'),
    caption: (speaker, text) => ctx.log('mock-overlay', 'caption', speaker, text),
    chip: (level, label) => ctx.log('mock-overlay', 'chip', level, label),
  }
}

// ---- LiveBridge (owner: LIVE). Mock records what would have been injected. ----
export function mockLiveBridge(ctx: ServiceContext): LiveBridge & { sent: { text: string; interrupt?: boolean }[] } {
  const sent: { text: string; interrupt?: boolean }[] = []
  return {
    sent,
    inject(text, opts) {
      sent.push({ text, interrupt: opts?.interrupt })
      ctx.log('mock-live', 'inject', text)
    },
  }
}

// ---- LearnerStore (owner: TEACH) ----
function freshSkills(): Record<SkillId, SkillState> {
  return Object.fromEntries(SKILL_IDS.map((id) => [id, { level: 1 as HelpLevel, streakClean: 0, lastSeen: null, nextReview: null }])) as Record<SkillId, SkillState>
}

export function mockLearner(): LearnerStore {
  let snap: LearnerSnapshot = { skills: freshSkills(), confidenceLog: [], attempts: [], whatWorks: [], avoidJargon: [] }
  let markdown = '# Learner profile\n\n(mock)\n'
  let revision = 'r0'
  return {
    async load() {
      return snap
    },
    async save() {},
    snapshot: () => snap,
    async recordAttempt(attempt: AttemptRecord) {
      snap = { ...snap, attempts: [...snap.attempts, attempt], lastSession: { at: attempt.endedAt, skillId: attempt.skillId, summary: attempt.completed ? 'Finished the lesson.' : 'Did not finish the lesson.' } }
      return snap
    },
    async addNote(note) {
      snap = { ...snap, whatWorks: [...snap.whatWorks, note] }
    },
    async editMarkdown(req): Promise<MarkdownEditResult> {
      if (req.op === 'read') return { ok: true, content: markdown, revision }
      if (req.revision !== revision) return { ok: false, content: markdown, revision, conflict: true }
      markdown = req.content ?? markdown
      revision = `r${Number(revision.slice(1)) + 1}`
      return { ok: true, content: markdown, revision }
    },
  }
}

// ---- LevelEngine (owner: TEACH). Pure functions. ----
export function mockLevels(): LevelEngine {
  const isClean = (a: AttemptRecord) => a.completed && a.hintsUsed <= 2 && a.errors <= 1 && !a.safetyFlag && (a.teachBackScore === null || a.teachBackScore >= 0.67)
  return {
    initial: () => ({ level: 1, streakClean: 0, lastSeen: null, nextReview: null }),
    isClean,
    evaluateAttempt(attempt, state, opts): LevelDecision {
      const struggled = attempt.hintsUsed >= 2 || attempt.errors >= 2 || attempt.stalls >= 2 || attempt.anxietyPhrase
      if (isClean(attempt)) {
        const streak = state.streakClean + 1
        const needed = opts.demoMode ? 1 : 2
        const level = (streak >= needed && state.level < 4 ? state.level + 1 : state.level) as HelpLevel
        const next: SkillState = { level, streakClean: level === state.level ? streak : 0, lastSeen: opts.now, nextReview: opts.now + 3 * 86_400_000 }
        return { state: next, change: level > state.level ? 'up' : 'hold', reason: 'clean attempt' }
      }
      if (struggled && state.level > 1) {
        return { state: { ...state, level: (state.level - 1) as HelpLevel, streakClean: 0, lastSeen: opts.now }, change: 'down', reason: 'needed more help' }
      }
      return { state: { ...state, streakClean: 0, lastSeen: opts.now }, change: 'hold', reason: 'not clean' }
    },
    decay(state, now) {
      if (state.lastSeen === null) return state
      const days = (now - state.lastSeen) / 86_400_000
      return days >= 3 && state.level > 1 ? { ...state, level: (state.level - 1) as HelpLevel } : state
    },
    stepLevel(state, step, override) {
      const level = override ?? state.level
      return step.safetyCritical && level > 2 ? 2 : level
    },
  }
}

// ---- LessonRunner (owner: TEACH). Mock drives architect -> grounder -> overlay -> verifier through the bag. ----
export function mockRunner(ctx: ServiceContext, s: Services): LessonRunner {
  let plan: LessonPlan | null = null
  let index = 0
  let startedAt = 0
  let hints = 0

  const clearPointer = () => s.overlay.clear(['runner-ring', 'runner-arrow', 'runner-badge', 'runner-tick'])

  async function showStep(): Promise<void> {
    if (!plan) return
    const current = plan.steps[index]
    if (!current) return
    ctx.state.patch({ skill: { id: plan.skillId, name: plan.goal, step: index + 1, stepCount: plan.steps.length } })
    ctx.bus.emit('lesson:step', { lessonId: plan.lessonId, skillId: plan.skillId, stepIndex: index, stepCount: plan.steps.length, phase: 'started', step: current })
    const shot = await s.capture.grab('ground')
    const res = await s.grounder.ground({ target: current.targetDescription, shot })
    clearPointer()
    if (!res.found || !res.box) return
    s.overlay.show([
      { id: 'runner-ring', kind: 'ring', tone: 'guide', box: res.box, label: current.instruction, step: index + 1 },
      { id: 'runner-arrow', kind: 'arrow', tone: 'guide', to: res.box },
    ])
  }

  return {
    async start(goal) {
      plan = await s.architect.plan({ goal, learner: s.learner.snapshot() })
      index = 0
      hints = 0
      startedAt = Date.now()
      await showStep()
      return { lessonId: plan.lessonId, skillId: plan.skillId, stepCount: plan.steps.length }
    },
    async onStepDone() {
      if (!plan) return { ok: false, done: false }
      index += 1
      const next = plan.steps[index]
      if (!next) return { ok: true, done: true }
      await showStep()
      return { ok: true, done: false, step: { index, instruction: next.instruction } }
    },
    async onStall() {
      hints += 1
      const current = plan?.steps[index]
      if (current) s.live.inject(`[STALL] ${current.hints.l3}`)
    },
    async verifyStep(expectedOutcome) {
      const shot = await s.capture.grab('verify')
      const current = plan?.steps[index]
      const verdict = await s.verifier.verify(current ? { step: current, shot } : { expected: expectedOutcome ?? 'the task is complete', shot })
      if (verdict.completed && plan) {
        clearPointer()
        const box = { xmin: 440, ymin: 440, xmax: 560, ymax: 520 }
        s.overlay.show([{ id: 'runner-tick', kind: 'tick', tone: 'success', box, ok: true, ttlMs: 2500 }])
        ctx.bus.emit('lesson:step', { lessonId: plan.lessonId, skillId: plan.skillId, stepIndex: index, stepCount: plan.steps.length, phase: 'verified' })
      }
      return verdict
    },
    async requestLevel(level, reason) {
      const from = ctx.state.get().level
      ctx.state.patch({ level })
      const skillId = plan?.skillId ?? 'video_call'
      ctx.bus.emit('level:changed', { skillId, from, to: level, reason: reason ?? 'requested', scope: 'manual' })
      return { applied: true, level }
    },
    async end(summary, teachBackScore, confidence) {
      if (!plan) return
      const level = ctx.state.get().level
      const attempt: AttemptRecord = {
        id: randomUUID(),
        skillId: plan.skillId,
        lessonId: plan.lessonId,
        startedAt,
        endedAt: Date.now(),
        levelAtStart: level,
        levelAtEnd: level,
        completed: true,
        hintsUsed: hints,
        errors: 0,
        stalls: hints,
        safetyFlag: false,
        anxietyPhrase: false,
        teachBackScore: teachBackScore ?? null,
        confidence: confidence ?? null,
        clean: hints <= 2,
      }
      await s.learner.recordAttempt(attempt)
      ctx.log('mock-runner', 'end', summary)
      plan = null
      clearPointer()
      ctx.state.patch({ skill: undefined })
    },
    async abort(reason) {
      if (!plan) return
      ctx.bus.emit('lesson:step', { lessonId: plan.lessonId, skillId: plan.skillId, stepIndex: index, stepCount: plan.steps.length, phase: 'aborted' })
      ctx.log('mock-runner', 'abort', reason ?? '')
      plan = null
      clearPointer()
      ctx.state.patch({ skill: undefined })
    },
  }
}

// ---- AgentRuntime (owner: AGENTS) ----
export function mockAgents(ctx: ServiceContext, s: Services): AgentRuntime {
  const chips = new Map<string, AgentChip>()
  const timers = new Map<string, NodeJS.Timeout>()
  const publish = (chip: AgentChip) => {
    chips.set(chip.id, chip)
    ctx.state.upsertAgent(chip)
    ctx.bus.emit('agent:update', { chip })
  }
  return {
    async spawn(kind, task) {
      const id = `agent-${randomUUID().slice(0, 8)}`
      const title = kind === 'scam_check' ? 'Checking that message' : kind === 'lookup' ? `Looking up: ${task.slice(0, 40)}` : 'Writing your lesson summary'
      publish({ id, kind, title, status: 'running', startedAt: Date.now() })
      timers.set(
        id,
        setTimeout(async () => {
          const base = chips.get(id)
          if (!base || base.status !== 'running') return
          if (kind === 'scam_check') {
            const report = await s.scam.analyze({ text: task })
            publish({ ...base, status: 'done', summary: `Looks like a scam (${report.redFlags.length} warning signs).`, result: { kind, report } })
            s.live.inject(`[AGENT_RESULT] scam_check: ${report.verdict}. ${report.advice.join(' ')}`)
          } else {
            const text = kind === 'lookup' ? 'Mock lookup result.' : 'You finished the lesson and needed little help.'
            publish({ ...base, status: 'done', summary: text, result: { kind, text } })
            s.live.inject(`[AGENT_RESULT] ${kind}: ${text}`)
          }
        }, 800),
      )
      return { agentId: id }
    },
    list: () => [...chips.values()],
    cancel(id) {
      const chip = chips.get(id)
      if (!chip || chip.status !== 'running') return
      const timer = timers.get(id)
      if (timer) clearTimeout(timer)
      publish({ ...chip, status: 'cancelled' })
    },
  }
}

// ---- Teaching (owner: TEACH) ----
export function mockTeaching(ctx: ServiceContext): Teaching {
  return {
    async systemInstruction(personaId) {
      const level = ctx.state.get().level
      return `MOCK system instruction for ${personaId}. Help level ${level} (${HELP_LEVEL_LABELS[level]}). Speak plainly in one or two short sentences. You are an AI.`
    },
  }
}
