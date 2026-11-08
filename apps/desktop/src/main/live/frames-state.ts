// When a voice conversation is meant to see the screen (the worker said yes to it, frames are on) and cannot, nobody may be left guessing: the worker gets one card per conversation, a closed
// code says why, and the Live model is told once in one short line so it never pretends to see. Pure and closed: every reason is one of the words below, each with its plain sentence, and
// nothing from the screen, a window or a person is ever part of the sentence.
import type { GateReason } from './gates'

/** Why a frame could not be taken or sent right now. `screen_recording_missing` is macOS; the rest are the gates in front of every frame, or a capture that came back empty twice. */
export type FramesReason = 'screen_recording_missing' | 'capture_failed' | Exclude<GateReason, 'killed' | 'unattended' | 'no_consent'>

/** The reasons that end the conversation itself (a kill, an agent acting for the worker) or cannot happen while frames are on (consent): no "cannot see" line for those. */
export const FRAMES_NOT_A_PROBLEM: ReadonlySet<string> = new Set(['killed', 'unattended', 'no_consent', 'ledger_unavailable'])

/** The plain reason, as it is said to the model (after "You cannot see the screen right now: "). */
export const FRAMES_MODEL_REASON: Readonly<Record<FramesReason, string>> = {
  screen_recording_missing: 'Knack does not have permission to record the screen',
  capture_failed: 'the screen could not be captured',
  secure_input: 'a password field is open',
  denylisted_app: 'a private app is in front',
  locked: 'the screen is locked',
  screen_share: 'the screen is being shared',
  stale: 'Knack could not check what is in front',
  paused: 'Knack is paused',
}

export const isFramesReason = (r: string): r is FramesReason => Object.prototype.hasOwnProperty.call(FRAMES_MODEL_REASON, r)

/** The one short line the model is told when it loses the screen. Fixed words, one closed reason. */
export const framesLostLine = (r: FramesReason): string => `You cannot see the screen right now: ${FRAMES_MODEL_REASON[r]}. Say so and give spoken guidance only.`
/** And when it comes back. */
export const FRAMES_BACK_LINE = 'You can see the screen again.'

/** At most this many "cannot see" lines go to the model in one conversation (a flicker between two private apps must not fill its context). */
export const MAX_FRAMES_LINES = 3

/** The closed code of the problem a session notice carries for frames (VoiceProblem in manager.ts), by reason. */
export const FRAMES_PROBLEM: Readonly<Record<FramesReason, string>> = {
  screen_recording_missing: 'screen_missing',
  capture_failed: 'screen_failed',
  secure_input: 'screen_secure_input',
  denylisted_app: 'screen_private_app',
  locked: 'screen_locked',
  screen_share: 'screen_shared',
  stale: 'screen_stale',
  paused: 'screen_paused',
}

export interface FramesTracker {
  /** A frame could not be sent for this reason. Returns what to do now: say it (the first time in the conversation), tell the model (a new reason, within the cap), or nothing. */
  lost(reason: string, grabMisses?: number): { notice: FramesReason | null; tell: string | null }
  /** A frame went out. Returns the line for the model when it had been told it could not see, else null. */
  back(): string | null
  /** Counts a capture that came back empty; a permission refusal counts at once, anything else after two in a row. Returns the reason once it is time to say it. */
  miss(permission: boolean): FramesReason | null
  clearMisses(): void
  unavailable(): FramesReason | null
}

export function createFramesTracker(): FramesTracker {
  let current: FramesReason | null = null
  let announced = false
  let told = 0
  let modelThinksLost = false // the model was told it cannot see, and has not been told it can again
  let misses = 0
  return {
    lost(reason) {
      if (!isFramesReason(reason) || FRAMES_NOT_A_PROBLEM.has(reason)) return { notice: null, tell: null }
      const same = current === reason
      current = reason
      const notice = announced ? null : reason
      announced = true
      let tell: string | null = null
      if (!same && told < MAX_FRAMES_LINES) {
        told += 1
        modelThinksLost = true
        tell = framesLostLine(reason)
      }
      return { notice, tell }
    },
    back() {
      if (!current) return null
      current = null
      misses = 0
      if (!modelThinksLost) return null
      modelThinksLost = false
      return FRAMES_BACK_LINE
    },
    miss(permission) {
      misses += 1
      if (permission) return 'screen_recording_missing'
      return misses >= 2 ? 'capture_failed' : null
    },
    clearMisses() {
      misses = 0
    },
    unavailable: () => current,
  }
}
