// IPC channel names for the voice bridge between main and the dock renderer (which owns the microphone and the speaker). Names only, no
// Electron. They are listed here, not in shared/ipc.ts, because that file belongs to the shell track; if the shell wants them there, move
// this object and nothing else changes. The old Alongside channels (live:token, live:toolCall, live:frame ...) are NOT used by the new path.
export const LIVE_IPC = {
  // main -> renderer
  micStart: 'ulive:mic:start', // { reqId }
  micStop: 'ulive:mic:stop',
  play: 'ulive:audio:play', // base64 PCM16 mono 24 kHz
  flush: 'ulive:audio:flush',
  clipPlay: 'ulive:clip:play', // { reqId, mime, bytes: ArrayBuffer }
  clipStop: 'ulive:clip:stop',
  // renderer -> main
  micResult: 'ulive:mic:result', // { reqId, ok, code? }
  micChunk: 'ulive:mic:chunk', // (base64 PCM16 mono 16 kHz, level 0..1)
  playbackIdle: 'ulive:audio:idle',
  clipDone: 'ulive:clip:done', // { reqId, ok }
} as const

export type LiveIpcChannel = (typeof LIVE_IPC)[keyof typeof LIVE_IPC]

export interface MicResult {
  reqId: number
  ok: boolean
  code?: 'permission' | 'device'
}
