// Public surface of the model-backed services. Each factory takes { port, log } (+ optional capture so a service can grab its
// own 'ground'/'verify' shot). In the app, services.ts builds the deps once via modelDeps(ctx, s).
import type { Capture } from '../../shared/contracts'
import type { ServiceContext } from '../context'
import { createModelPortFromEnv } from '../model-port'
import type { ModelDeps } from './deps'

export type { ModelDeps } from './deps'
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

const memo = new WeakMap<object, ModelDeps>()

/**
 * Shared deps for the app's service bag: one model port (ctx.modelPort when main built it, else from the environment),
 * ctx.log for logging, and a lazy capture handle (`s.capture` is read inside the call, never at construction time).
 */
export function modelDeps(ctx: Pick<ServiceContext, 'log'> & { modelPort?: ServiceContext['modelPort'] }, s: { capture: Capture }): ModelDeps {
  let deps = memo.get(ctx)
  if (!deps) {
    deps = { port: ctx.modelPort ?? createModelPortFromEnv({ log: ctx.log }), log: ctx.log, capture: { grab: (purpose) => s.capture.grab(purpose) } }
    memo.set(ctx, deps)
  }
  return deps
}
