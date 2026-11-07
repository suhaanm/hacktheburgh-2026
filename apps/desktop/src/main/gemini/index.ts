// Public surface of the Gemini-backed services. Each factory takes { ai, models, log } (+ optional capture so a
// service can grab its own 'ground'/'verify' shot). In the app, services.ts builds deps once via geminiDeps(ctx, s).
import type { Capture } from '../../shared/contracts'
import { createGeminiDeps, type GeminiDeps } from './client'

export { createGeminiDeps, createAi, latencySummary, resetLatency, GeminiError } from './client'
export type { GeminiDeps, AiLike, Models, Log } from './client'
export { createGrounder, groundingPresetFromEnv, normaliseTarget, shortLabel } from './grounder'
export type { GroundConfig, GroundPreset, GrounderWithPreset } from './grounder'
export { createVerifier } from './verifier'
export type { VerifierConfig } from './verifier'
export { createLessonArchitect } from './lesson-architect'
export type { ArchitectConfig } from './lesson-architect'
export { createScamAnalyst } from './scam-analyst'
export type { ScamConfig } from './scam-analyst'
export { createRouter } from './router'
export type { RouterConfig } from './router'
export * as groundingUtils from './grounding-utils'

const memo = new WeakMap<object, GeminiDeps>()

/**
 * Shared deps for the app's service bag: one SDK client, ctx.log for logging, and a lazy capture handle
 * (`s.capture` is read inside the call, never at construction time).
 */
export function geminiDeps(ctx: { log: (scope: string, ...args: unknown[]) => void }, s: { capture: Capture }): GeminiDeps {
  let deps = memo.get(ctx)
  if (!deps) {
    deps = createGeminiDeps({ log: ctx.log, capture: { grab: (purpose) => s.capture.grab(purpose) } })
    memo.set(ctx, deps)
  }
  return deps
}
