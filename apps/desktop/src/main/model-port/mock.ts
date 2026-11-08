// Mock provider for the model port: scripted, deterministic, no network, no key. Used when UNDERSTUDY_MOCK=1 or ALONGSIDE_MOCK=1
// (NFR-2: every demo path runs model-free). A responder is chosen by the request `name` prefix, so the real services
// (grounder, verifier, router, architect, scam) run unchanged on top of it and always get a schema-valid answer.
import type { BootReport, CompletionRequest, CompletionResult, ComputerStepRequest, ComputerStepResult, ModelIds, ModelProvider } from './types'

export type MockResponder = (req: CompletionRequest) => unknown

export interface MockOptions {
  ids?: Partial<ModelIds>
  // Per-name-prefix overrides (longest prefix wins), for tests and scripted scenarios.
  responders?: Record<string, MockResponder>
  computerStep?: (req: ComputerStepRequest) => ComputerStepResult
}

export const MOCK_IDS: ModelIds = { planner: 'mock-planner', fast: 'mock-fast', computer_use: 'mock-computer-use' }

const targetOf = (text: string): string => /Find this one element: "([^"]{1,200})"/.exec(text)?.[1] ?? 'the target'

export const DEFAULT_RESPONDERS: Record<string, MockResponder> = {
  'grounder.': (req) => ({
    found: true,
    label: targetOf(req.text).split(/\s+/).slice(0, 4).join(' '),
    box: [420, 380, 580, 440],
    reason: 'mock',
    confidence: 0.9,
  }),
  'verifier.': () => ({
    completed: true,
    confidence: 0.95,
    evidence: 'The screen shows the expected result.',
    uncertain: false,
    learner_misstep: '',
    next_hint: '',
  }),
  'router.': () => ({ intent: 'unknown', confidence: 0.2 }),
  'architect.': () => ({
    skillId: 'custom',
    steps: [
      {
        instruction: 'Open the app you want.',
        targetDescription: 'the app icon in the dock',
        expectedOutcome: 'The app window is open.',
        hints: { l1: 'Watch where I point.', l2: 'Click the icon in the dock.', l3: 'Look along the bottom of the screen.' },
        safetyCritical: false,
      },
      {
        instruction: 'Look at the window that opened.',
        targetDescription: 'the open window',
        expectedOutcome: 'The window is in front.',
        hints: { l1: 'This is the window.', l2: 'Take a look at it.', l3: 'It is the biggest thing on screen.' },
        safetyCritical: false,
      },
    ],
  }),
  'scam.synthesis': () => ({
    verdict: 'suspicious',
    confidence: 0.6,
    message_text: '',
    red_flags: [],
    advice: ['Do not click links or share details.', 'Check with the organisation using a number you already trust.'],
  }),
  'scam.': () => ({ risk: 'medium', summary: 'Example data: nothing was really analysed.', findings: [], message_text: '' }),
}

export function createMockProvider(opts: MockOptions = {}): ModelProvider {
  const ids: ModelIds = { ...MOCK_IDS, ...opts.ids }
  const table = { ...DEFAULT_RESPONDERS, ...(opts.responders ?? {}) }
  const prefixes = Object.keys(table).sort((a, b) => b.length - a.length)

  return {
    provider: 'mock',
    models: () => ids,
    async complete(req: CompletionRequest): Promise<CompletionResult> {
      const key = prefixes.find((p) => req.name.startsWith(p))
      const body = key ? table[key](req) : {}
      const text = typeof body === 'string' ? body : JSON.stringify(body)
      return { text, model: ids[req.tier], ms: 1, usage: { input: 0, output: 0, reasoning: 0 } }
    },
    async computerStep(req: ComputerStepRequest): Promise<ComputerStepResult> {
      if (opts.computerStep) return opts.computerStep(req)
      return { kind: 'done', text: 'Example data: nothing was done.', model: ids.computer_use, ms: 1 }
    },
    async bootCheck(): Promise<BootReport> {
      return { ok: true, provider: 'mock', configured: ids, unset: [], missing: [], usable: Object.values(ids), listed: 3 }
    },
  }
}
