// Test double for the Interactions API: records calls, honours AbortSignal like the real SDK.
import { MODELS } from '../../shared/models'
import type { Shot } from '../../shared/protocol'
import type { AiLike, GeminiDeps, InteractionLike } from './client'

export interface RecordedCall {
  params: Record<string, unknown>
}

type Handler = (params: Record<string, unknown>, n: number) => InteractionLike | Promise<InteractionLike>

export function fakeAi(handler: Handler): { ai: AiLike; calls: RecordedCall[] } {
  const calls: RecordedCall[] = []
  const ai: AiLike = {
    interactions: {
      create(params, options) {
        calls.push({ params })
        const n = calls.length
        return new Promise<InteractionLike>((resolve, reject) => {
          const signal = options?.signal
          const onAbort = () => reject(Object.assign(new Error('aborted'), { name: 'TimeoutError' }))
          if (signal?.aborted) return onAbort()
          signal?.addEventListener('abort', onAbort, { once: true })
          Promise.resolve()
            .then(() => handler(params, n))
            .then(resolve, reject)
        })
      },
    },
  }
  return { ai, calls }
}

export const modelOutput = (body: unknown): InteractionLike => ({
  status: 'completed',
  steps: [
    { type: 'thought' },
    { type: 'model_output', content: [{ type: 'text', text: typeof body === 'string' ? body : JSON.stringify(body) }] },
  ],
  usage: { total_input_tokens: 100, total_output_tokens: 20, total_thought_tokens: 10 },
})

export const functionCall = (name: string, args: Record<string, unknown>): InteractionLike => ({
  status: 'completed',
  steps: [{ type: 'thought' }, { type: 'function_call', name, arguments: args }],
})

export const apiError = (status: number, message = 'boom') => Object.assign(new Error(message), { status })

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function testDeps(ai: AiLike, extra: Partial<GeminiDeps> = {}): GeminiDeps {
  return { ai, models: MODELS, log: () => undefined, ...extra }
}

let shotCounter = 0
export function testShot(tag = `s${shotCounter++}`): Shot {
  return { id: tag, displayId: 1, widthPx: 1920, heightPx: 1080, scaleFactor: 1, jpegBase64: `QUJD${tag}`, takenAt: 0, overlayHidden: true }
}

// Helpers to read what the service sent.
export const textInput = (call: RecordedCall): string => {
  const input = call.params.input as Array<{ type: string; text?: string }>
  return input.filter((p) => p.type === 'text').map((p) => p.text ?? '').join('\n')
}
export const hasImage = (call: RecordedCall): boolean => (call.params.input as Array<{ type: string }>).some((p) => p.type === 'image')
