// Voice is OFF unless BOTH the Live experiment (UNDERSTUDY_X_LIVE=1) and the voice feature flag (UNDERSTUDY_FLAG_VOICE=1) are set, and the
// worker has opted in (settings.ts). Spoken pack lines (ElevenLabs) additionally need UNDERSTUDY_VOICE=1. Read on every call, never cached.
// Under vitest the shared flags would be ON by default (feature-flags.ts); the tests of this module pass an explicit env instead, so
// "off by default" is tested for real.
import { experimentOn, featureOn } from '../feature-flags'

const TRUE = new Set(['1', 'true', 'yes', 'on'])
const on = (v: string | undefined): boolean => TRUE.has((v ?? '').trim().toLowerCase())

export type Env = Record<string, string | undefined>

/** The Live conversation may exist at all in this build. */
export function liveFlagOn(env: Env = process.env): boolean {
  return experimentOn('live', env) && featureOn('voice', env)
}

/** Fixed pack lines may be spoken (the agent service's ElevenLabs route is on). */
export function speakerFlagOn(env: Env = process.env): boolean {
  return on(env.UNDERSTUDY_VOICE)
}

/** The Live model id, from the environment only (GEMINI_MODEL_LIVE; MODEL_LIVE is the old Alongside name). Null when none is configured. */
export function liveModelId(env: Env = process.env): string | null {
  const v = (env.GEMINI_MODEL_LIVE ?? env.MODEL_LIVE ?? '').trim()
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(v) ? v : null
}

/** An optional dedicated transcription model for Cue's one-answer listening turn (GEMINI_MODEL_TRANSCRIBE). Null: use the Live model. */
export function transcribeModelId(env: Env = process.env): string | null {
  const v = (env.GEMINI_MODEL_TRANSCRIBE ?? '').trim()
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(v) ? v : null
}
