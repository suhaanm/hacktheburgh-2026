// The renderer's side of the voice bridge, built from an ipcRenderer-like object so the shell's preload can expose it with ONE line:
//
//   import { createLivePreloadApi } from '../main/live/preload-api'
//   contextBridge.exposeInMainWorld('understudyLive', createLivePreloadApi(ipcRenderer))
//
// It carries audio and a few control messages and nothing else: no token, no key, no settings, no way to read the screen.
import { LIVE_IPC, type MicResult } from './ipc-channels'

export interface IpcRendererLike {
  on(channel: string, listener: (event: unknown, ...args: unknown[]) => void): unknown
  off(channel: string, listener: (event: unknown, ...args: unknown[]) => void): unknown
  send(channel: string, ...args: unknown[]): void
}

export interface LiveRendererApi {
  onMicStart(cb: (req: { reqId: number }) => void): () => void
  onMicStop(cb: () => void): () => void
  onPlay(cb: (b64: string) => void): () => void
  onFlush(cb: () => void): () => void
  onClipPlay(cb: (req: { reqId: number; mime: string; bytes: ArrayBuffer }) => void): () => void
  onClipStop(cb: () => void): () => void
  micResult(r: MicResult): void
  micChunk(b64: string, level: number): void
  playbackIdle(): void
  clipDone(r: { reqId: number; ok: boolean }): void
}

export function createLivePreloadApi(ipc: IpcRendererLike): LiveRendererApi {
  const on = <A extends unknown[]>(channel: string, cb: (...a: A) => void): (() => void) => {
    const handler = (_e: unknown, ...args: unknown[]): void => cb(...(args as A))
    ipc.on(channel, handler)
    return () => void ipc.off(channel, handler)
  }
  return {
    onMicStart: (cb) => on<[{ reqId: number }]>(LIVE_IPC.micStart, cb),
    onMicStop: (cb) => on<[]>(LIVE_IPC.micStop, cb),
    onPlay: (cb) => on<[string]>(LIVE_IPC.play, cb),
    onFlush: (cb) => on<[]>(LIVE_IPC.flush, cb),
    onClipPlay: (cb) => on<[{ reqId: number; mime: string; bytes: ArrayBuffer }]>(LIVE_IPC.clipPlay, cb),
    onClipStop: (cb) => on<[]>(LIVE_IPC.clipStop, cb),
    micResult: (r) => ipc.send(LIVE_IPC.micResult, r),
    micChunk: (b64, level) => ipc.send(LIVE_IPC.micChunk, b64, level),
    playbackIdle: () => ipc.send(LIVE_IPC.playbackIdle),
    clipDone: (r) => ipc.send(LIVE_IPC.clipDone, r),
  }
}
