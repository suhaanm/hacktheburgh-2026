// Dependencies shared by the model-backed services (grounder, verifier, router, architect, scam analyst).
// They talk to a ModelPort (src/main/model-port), never to a vendor SDK, and never name a model: they ask for a tier.
import type { Shot, ShotPurpose } from '../../shared/protocol'
import { redactingLog, type ImageInput, type Log, type ModelPort } from '../model-port'

export type { Log } from '../model-port'

export interface ModelDeps {
  port: ModelPort
  log: Log
  // Optional: lets services grab their own 'ground'/'verify' shot when the caller passes none.
  capture?: { grab(purpose: ShotPurpose): Promise<Shot> }
}

/** Every service factory runs its deps through this, so logging is redacted even when deps were built by hand. */
export function withSafeLog(deps: ModelDeps): ModelDeps {
  return { ...deps, log: redactingLog(deps.log) }
}

export const imageOf = (shot: Shot, detail: ImageInput['detail'] = 'high'): ImageInput => ({ jpegBase64: shot.jpegBase64, detail })
