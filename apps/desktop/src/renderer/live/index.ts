// The renderer's part in voice: the microphone and the speaker, driven by main (bridge.ts). The old renderer-side session is removed
// (legacy.ts is a stub that cannot be constructed, kept only so the old dock controller still compiles).
export { startLiveBridge } from './bridge'
export { LiveSession } from './legacy'
export * from './types'
export { AudioPlayer, MicCapture, pcm16ToBase64Chunks } from './audio'
