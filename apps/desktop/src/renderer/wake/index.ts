// Public surface of the wake spotter. LIVE's controller.ts is the only consumer that owns mic arbitration:
//   spotter.pause('live') when a Live session starts, spotter.resume('live') on session:ended,
//   spotter.pause('tts') / resume('tts') around non-Live TTS, spotter.takePreroll() once Live is connected.
export { createWakeSpotter } from './spotter'
export { createWakeMatcher, normalize, DEFAULT_PREFIXES, DEFAULT_REJECT_WORDS } from './matcher'
export type { WakeMatch, WakeMatcher, WakeMatcherOptions, WakePersona, WakeInspection, WakeMatchContext } from './matcher'
export { createMicAudioSource } from './audio-source'
export { createGeminiEngineFactory, TRANSCRIBE_MODEL } from './engine-gemini'
export { PrerollBuffer } from './preroll'
export type {
  WakeAudioSource,
  WakeEngine,
  WakeEngineFactory,
  WakeEngineHandlers,
  WakeEvent,
  WakePauseReason,
  WakeSettings,
  WakeSpotter,
  WakeSpotterOptions,
  WakeStatus,
  WakeToken,
} from './types'
