// Shared Gemini plumbing: one Interactions-API call path with hard timeouts, jittered retries,
// per-call latency + model logging, and `store:false` forced (every service may carry a screenshot).
import { GoogleGenAI } from '@google/genai'
import { config as loadEnv } from 'dotenv'
import type { ZodType } from 'zod'
import { MODELS } from '../../shared/models'
import { redactText, redactingLog } from './redact'
import type { Shot, ShotPurpose } from '../../shared/protocol'

export type Models = typeof MODELS
export type Log = (scope: string, ...args: unknown[]) => void

export interface InteractionStep {
  type: string
  content?: Array<{ type: string; text?: string }>
  name?: string
  arguments?: Record<string, unknown>
}
export interface InteractionLike {
  id?: string
  status?: string
  steps?: InteractionStep[]
  usage?: { total_input_tokens?: number; total_output_tokens?: number; total_thought_tokens?: number }
}
export interface AiLike {
  interactions: {
    create(params: Record<string, unknown>, options?: { signal?: AbortSignal }): Promise<InteractionLike>
  }
}

export interface GeminiDeps {
  ai: AiLike
  models: Models
  log: Log
  // Optional: lets services grab their own 'ground'/'verify' shot when the caller passes none.
  capture?: { grab(purpose: ShotPurpose): Promise<Shot> }
}

export type GeminiErrorCode = 'timeout' | 'api' | 'parse' | 'empty' | 'no_input' | 'auth' | 'rate_limit' | 'network'

// What a person should hear for each kind of failure (plain English, no codes, no blame, no guessing).
const PLAIN: Record<GeminiErrorCode, string> = {
  auth: "I can't use my online helper because it isn't set up yet.",
  rate_limit: "I'm getting too many requests right now. Please try again in a moment.",
  network: "I can't reach the internet right now.",
  timeout: 'That is taking too long.',
  parse: 'I got a muddled answer and did not trust it.',
  empty: 'I did not get an answer.',
  no_input: 'There was nothing to look at.',
  api: 'Something went wrong on my side.',
}
export const plainByCode = (code: string): string => PLAIN[code as GeminiErrorCode] ?? PLAIN.api

export class GeminiError extends Error {
  constructor(
    public readonly code: GeminiErrorCode,
    message: string,
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'GeminiError'
  }
  get userMessage(): string {
    return plainByCode(this.code)
  }
}

/** Plain-English line for any thrown value. */
export const plainFailure = (e: unknown): string => (e instanceof GeminiError ? e.userMessage : PLAIN.api)

/** Failures where saying exactly what is wrong helps (and is safe); the rest stay generic. */
export const isEnvironmental = (e: unknown): boolean => e instanceof GeminiError && (e.code === 'auth' || e.code === 'network' || e.code === 'rate_limit')

/**
 * The one place the SDK client is built. The key is read from env (dotenv fallback) and never logged.
 * Without a key this returns a client whose every call fails with a 401-style error, so the app still starts and
 * each service degrades to its honest "could not check" answer instead of crashing.
 */
export function createAi(): AiLike {
  if (!process.env.GEMINI_API_KEY) loadEnv({ path: `${process.cwd()}/.env`, quiet: true })
  const apiKey = process.env.GEMINI_API_KEY
  if (!apiKey) {
    return {
      interactions: {
        create: () => Promise.reject(Object.assign(new Error('GEMINI_API_KEY is not set (put it in .env)'), { status: 401 })),
      },
    }
  }
  const sdk = new GoogleGenAI({ apiKey })
  return {
    interactions: {
      create: (params, options) => sdk.interactions.create(params as never, options) as unknown as Promise<InteractionLike>,
    },
  }
}

export function createGeminiDeps(opts: { log: Log; capture?: GeminiDeps['capture']; ai?: AiLike }): GeminiDeps {
  return { ai: opts.ai ?? createAi(), models: MODELS, log: redactingLog(opts.log), capture: opts.capture }
}

/** Every service factory runs its deps through this, so logging is redacted even when deps were built by hand. */
export function withSafeLog(deps: GeminiDeps): GeminiDeps {
  return { ...deps, log: redactingLog(deps.log) }
}

// ---------- latency stats (for the final report and live tests) ----------
const samples = new Map<string, number[]>()
export function recordLatency(name: string, ms: number): void {
  const list = samples.get(name) ?? []
  list.push(ms)
  samples.set(name, list)
}
export function latencySummary(): Record<string, { n: number; p50: number; p95: number }> {
  const out: Record<string, { n: number; p50: number; p95: number }> = {}
  for (const [name, list] of samples) {
    const s = [...list].sort((a, b) => a - b)
    out[name] = { n: s.length, p50: s[Math.floor(s.length * 0.5)], p95: s[Math.min(s.length - 1, Math.floor(s.length * 0.95))] }
  }
  return out
}
export function resetLatency(): void {
  samples.clear()
}

// ---------- the call path ----------
export interface CallOptions {
  name: string // service/operation label for logs and stats, e.g. 'grounder.primary'
  model: string
  // Everything except model/store, which this module owns.
  params: Record<string, unknown>
  timeoutMs: number // hard wall-clock budget across all attempts
  retries?: number // extra attempts after the first (default 1)
}
export interface CallResult {
  interaction: InteractionLike
  text: string
  ms: number
}

const RETRYABLE = new Set([408, 429, 500, 502, 503, 504])
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

function statusOf(e: unknown): number | undefined {
  const s = (e as { status?: unknown } | null)?.status
  return typeof s === 'number' ? s : undefined
}
function isAbort(e: unknown): boolean {
  const n = (e as { name?: string } | null)?.name
  return n === 'AbortError' || n === 'TimeoutError' || n === 'RequestTimeoutError'
}

export function textOf(i: InteractionLike): string {
  const parts: string[] = []
  for (const s of i.steps ?? []) {
    if (s.type !== 'model_output') continue
    for (const c of s.content ?? []) if (c.type === 'text' && typeof c.text === 'string') parts.push(c.text)
  }
  return parts.join('')
}

export function functionCallsOf(i: InteractionLike): Array<{ name: string; args: Record<string, unknown> }> {
  return (i.steps ?? [])
    .filter((s) => s.type === 'function_call' && typeof s.name === 'string')
    .map((s) => ({ name: s.name as string, args: s.arguments ?? {} }))
}

export async function callModel(deps: GeminiDeps, o: CallOptions): Promise<CallResult> {
  const attempts = (o.retries ?? 1) + 1
  const deadline = Date.now() + o.timeoutMs
  let last: unknown
  for (let attempt = 0; attempt < attempts; attempt++) {
    const remaining = deadline - Date.now()
    if (remaining < 400) break
    const t0 = performance.now()
    try {
      // The abort signal is best-effort inside the SDK; the race makes the deadline hard no matter what the transport does.
      const controller = new AbortController()
      let timer: ReturnType<typeof setTimeout> | undefined
      const deadlineHit = new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          controller.abort()
          reject(Object.assign(new Error('deadline'), { name: 'TimeoutError' }))
        }, remaining)
      })
      const request = deps.ai.interactions.create({ ...o.params, model: o.model, store: false }, { signal: controller.signal })
      request.catch(() => undefined) // a request that loses the race must not become an unhandled rejection
      const interaction = await Promise.race([request, deadlineHit]).finally(() => clearTimeout(timer))
      const ms = Math.round(performance.now() - t0)
      recordLatency(o.name, ms)
      const u = interaction.usage ?? {}
      deps.log('gemini', `${o.name} model=${o.model} ${ms}ms in=${u.total_input_tokens ?? '?'} out=${u.total_output_tokens ?? '?'} think=${u.total_thought_tokens ?? '?'}`)
      return { interaction, text: textOf(interaction), ms }
    } catch (e) {
      last = e
      if (isAbort(e)) throw new GeminiError('timeout', `${o.name} timed out after ${o.timeoutMs}ms`)
      const status = statusOf(e)
      const retryable = status === undefined ? true : RETRYABLE.has(status)
      deps.log('gemini', `${o.name} model=${o.model} attempt ${attempt + 1}/${attempts} failed status=${status ?? 'network'}`)
      if (!retryable || attempt === attempts - 1) break
      await sleep(Math.min(remaining / 4, 250 * 2 ** attempt + Math.random() * 300))
    }
  }
  const status = statusOf(last)
  if (Date.now() >= deadline - 400 && last === undefined) throw new GeminiError('timeout', `${o.name} timed out after ${o.timeoutMs}ms`)
  const code: GeminiErrorCode = status === 401 || status === 403 ? 'auth' : status === 429 ? 'rate_limit' : status === undefined ? 'network' : 'api'
  throw new GeminiError(code, `${o.name} failed: ${redactText(String((last as Error | undefined)?.message ?? last)).slice(0, 200)}`, status)
}

// ---------- structured output helpers ----------
/** Parses model JSON (tolerating ``` fences / stray prose) and validates it with zod. */
export function parseModelJson<T>(text: string, schema: ZodType<T>): T {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
  const attempts = [trimmed]
  const first = trimmed.indexOf('{')
  const lastBrace = trimmed.lastIndexOf('}')
  if (first >= 0 && lastBrace > first) attempts.push(trimmed.slice(first, lastBrace + 1))
  let err: unknown
  for (const candidate of attempts) {
    try {
      return schema.parse(JSON.parse(candidate))
    } catch (e) {
      err = e
    }
  }
  throw new GeminiError('parse', `model returned invalid JSON: ${String((err as Error | undefined)?.message ?? err).slice(0, 200)}`)
}

export const jsonFormat = (schema: Record<string, unknown>) => ({ type: 'text', mime_type: 'application/json', schema })

export function imageInput(shot: Shot, resolution: 'low' | 'medium' | 'high' | 'ultra_high' = 'high') {
  return { type: 'image', data: shot.jpegBase64, mime_type: 'image/jpeg', resolution }
}

export const clamp01 = (n: number) => Math.min(1, Math.max(0, n))
