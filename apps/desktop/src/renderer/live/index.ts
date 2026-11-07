// The renderer's part in voice: the microphone and the speaker, driven by main (bridge.ts). The old renderer-side session, its stub and the
// wake-word spotter are removed: no renderer holds a key or a token or opens a socket.
export { startLiveBridge } from './bridge'
export * from './types'
export { AudioPlayer, MicCapture, pcm16ToBase64Chunks } from './audio'
