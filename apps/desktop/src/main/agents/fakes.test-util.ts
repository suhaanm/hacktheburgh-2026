// Test doubles for the agents lane. Every port records its calls so tests can assert what an agent touched.
import { DEFAULT_SETTINGS } from '../../shared/settings'
import type { Settings } from '../../shared/settings'
import type { AgentChip, Annotation, GroundResult, LearnerSnapshot, ScamReport, Shot } from '../../shared/protocol'
import type { AgentDeps, GroundedAnswer } from './ports'

export function makeShot(over: Partial<Shot> = {}): Shot {
  return { id: 'shot-1', displayId: 1, widthPx: 1920, heightPx: 1080, scaleFactor: 2, jpegBase64: 'AAAA', takenAt: Date.now(), overlayHidden: true, ...over }
}

export function makeReport(over: Partial<ScamReport> = {}): ScamReport {
  return {
    verdict: 'likely_scam',
    confidence: 0.92,
    redFlags: [
      { phrase: 'Your account will be closed in 24 hours', why: 'Scammers rush you so you do not stop and think.' },
      { phrase: 'verify your PIN', why: 'A real bank never asks for your PIN.' },
    ],
    advice: ['Do not click the link.', 'Do not share your PIN.'],
    humanHelp: 'Call your bank.',
    models: ['gemini-3.8-flash', 'gemini-4-argon'],
    latencyMs: 4200,
    ...over,
  }
}

export function makeLearner(over: Partial<LearnerSnapshot> = {}): LearnerSnapshot {
  const skill = { level: 2 as const, streakClean: 0, lastSeen: null, nextReview: null }
  return {
    skills: { video_call: skill, spot_scam: skill, bigger_text: skill },
    confidenceLog: [],
    attempts: [],
    whatWorks: [],
    avoidJargon: [],
    ...over,
  }
}

export interface Fakes {
  deps: AgentDeps
  calls: string[]
  // Ordered record of what the user would see/hear: 'inject' and 'show:<annotation id>'.
  timeline: string[]
  groundReqs: { target: string; precise?: boolean; shotId?: string; hint?: string }[]
  chipsPatched: AgentChip[][]
  busEvents: AgentChip[]
  injected: { text: string; interrupt?: boolean }[]
  shown: Annotation[][]
  cleared: (string[] | undefined)[]
  files: Map<string, string>
  settings: Settings
  set: {
    analyze?: (req: { text?: string; shot?: Shot; url?: string }, opts?: { onProgress?: (message: string) => void }) => Promise<ScamReport>
    ground?: (target: string) => Promise<GroundResult>
    search?: () => Promise<GroundedAnswer>
    learner?: LearnerSnapshot
  }
}

const NOT_FOUND: GroundResult = { found: false, confidence: 0, latencyMs: 1, model: 'fake' }

export function makeFakes(settingsPatch: Partial<Settings> = {}): Fakes {
  const settings: Settings = { ...DEFAULT_SETTINGS, ...settingsPatch }
  const f: Fakes = {
    calls: [],
    timeline: [],
    groundReqs: [],
    chipsPatched: [],
    busEvents: [],
    injected: [],
    shown: [],
    cleared: [],
    files: new Map(),
    settings,
    set: {},
    deps: undefined as unknown as AgentDeps,
  }
  let boxN = 0
  f.deps = {
    state: { patch: (p) => void f.chipsPatched.push(p.agents) },
    bus: { emit: (_e, payload) => void f.busEvents.push(payload.chip) },
    capture: {
      grab: async (purpose) => {
        f.calls.push(`capture.grab:${purpose}`)
        return makeShot()
      },
    },
    grounder: {
      ground: async ({ target, precise, shot, hint }) => {
        f.calls.push(`grounder.ground:${target}`)
        f.groundReqs.push({ target, precise, shotId: shot?.id, hint })
        if (f.set.ground) return f.set.ground(target)
        boxN += 1
        return { found: true, box: { xmin: 100, ymin: 100 * boxN, xmax: 400, ymax: 100 * boxN + 40 }, confidence: 0.9, latencyMs: 5, model: 'fake' }
      },
    },
    scam: {
      analyze: async (req, opts) => {
        f.calls.push('scam.analyze')
        return f.set.analyze ? f.set.analyze(req, opts) : makeReport()
      },
    },
    overlay: {
      show: (a) => {
        f.shown.push(a)
        for (const annotation of a) f.timeline.push(`show:${annotation.id}`)
      },
      clear: (ids) => void f.cleared.push(ids),
    },
    live: {
      inject: (text, opts) => {
        f.injected.push({ text, interrupt: opts?.interrupt })
        f.timeline.push('inject')
      },
    },
    learner: { snapshot: () => f.set.learner ?? makeLearner() },
    settings: () => f.settings,
    model: {
      searchAnswer: async () => {
        f.calls.push('model.searchAnswer')
        return f.set.search ? f.set.search() : { text: '1. Open Settings.\n2. Tap Display.', sources: ['support.example.com'] }
      },
    },
    exportsDir: '/tmp/alongside-test/exports',
    fs: {
      mkdir: async () => undefined,
      writeFile: async (file, data) => void f.files.set(file, data),
    },
  }
  return f
}

export { NOT_FOUND }

export async function until(cond: () => boolean, timeoutMs = 2000): Promise<void> {
  const start = Date.now()
  while (!cond()) {
    if (Date.now() - start > timeoutMs) throw new Error('until(): condition not met')
    await new Promise((r) => setTimeout(r, 5))
  }
}
