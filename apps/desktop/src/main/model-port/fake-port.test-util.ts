// Test double for the model port: records every request, honours the request's own timeout like a real provider.
import type { Shot } from '../../shared/protocol'
import { ModelPortError } from './errors'
import type { ModelDeps } from '../model-services/deps'
import { createModelPort } from './port'
import type { CompletionRequest, CompletionResult, ComputerStepRequest, ComputerStepResult, ModelIds, ModelPort, ModelProvider } from './types'

export const TEST_IDS: ModelIds = { planner: 'test-planner', fast: 'test-fast', computer_use: 'test-cu' }

type Handler = (req: CompletionRequest, n: number) => unknown | Promise<unknown>

/** Wraps a JSON body (or text) the way a model answers. */
export const modelOutput = (body: unknown): string => (typeof body === 'string' ? body : JSON.stringify(body))

export function fakePort(handler: Handler, extra: { computerStep?: (req: ComputerStepRequest) => ComputerStepResult | Promise<ComputerStepResult> } = {}): { port: ModelPort; calls: CompletionRequest[]; steps: ComputerStepRequest[] } {
  const calls: CompletionRequest[] = []
  const steps: ComputerStepRequest[] = []
  const provider: ModelProvider = {
    provider: 'mock',
    models: () => TEST_IDS,
    complete(req) {
      calls.push(req)
      const n = calls.length
      return new Promise<CompletionResult>((resolve, reject) => {
        const timer = setTimeout(() => reject(new ModelPortError('timeout', `${req.name} timed out after ${req.timeoutMs}ms`)), req.timeoutMs)
        Promise.resolve()
          .then(() => handler(req, n))
          .then(
            (out) => {
              clearTimeout(timer)
              resolve({ text: modelOutput(out), model: TEST_IDS[req.tier], ms: 1 })
            },
            (e: unknown) => {
              clearTimeout(timer)
              reject(e)
            },
          )
      })
    },
    async computerStep(req) {
      steps.push(req)
      if (extra.computerStep) return extra.computerStep(req)
      throw new ModelPortError('config', 'no computer step scripted')
    },
    async bootCheck() {
      return { ok: true, provider: 'mock', configured: TEST_IDS, unset: [], missing: [], usable: [], listed: 0 }
    },
  }
  return { port: createModelPort(provider), calls, steps }
}

/** Throws like a failing provider: the status picks the code the way the OpenAI provider does. */
export const apiError = (status: number, message = 'boom'): ModelPortError =>
  new ModelPortError(status === 401 || status === 403 ? 'auth' : status === 429 ? 'rate_limit' : 'api', message, status)

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function testDeps(port: ModelPort, extra: Partial<ModelDeps> = {}): ModelDeps {
  return { port, log: () => undefined, ...extra }
}

let shotCounter = 0
export function testShot(tag = `s${shotCounter++}`): Shot {
  return { id: tag, displayId: 1, widthPx: 1920, heightPx: 1080, scaleFactor: 1, jpegBase64: `QUJD${tag}`, takenAt: 0, overlayHidden: true }
}

// Helpers to read what the service sent.
export const textInput = (req: CompletionRequest): string => `${req.system ?? ''}\n${req.text}`.trim()
export const hasImage = (req: CompletionRequest): boolean => (req.images?.length ?? 0) > 0
