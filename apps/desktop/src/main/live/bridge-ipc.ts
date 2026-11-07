// The main side of the voice bridge: an AudioBridge and a ClipPlayer (two objects) built on injected IPC functions (so tests drive it with a fake and
// electron.ts wires ipcMain and the dock window). Every message from the renderer is validated here, and only the dock may send them.
//
//   mic       main asks the renderer to open the microphone (which needs macOS permission the worker has ALREADY granted; the renderer never
//             prompts from here) and gets back ok or a code. Chunks that arrive while the mic is not meant to be open are dropped.
//   playback  base64 PCM16 24 kHz goes to the renderer's player; the renderer says when its queue drains.
//   clips     a short fixed pack line (mp3 or wav) for the speaker; resolves when it ended.
import { LIVE_IPC, type MicResult } from './ipc-channels'
import { MicError, type AudioBridge, type ClipPlayer } from './ports'

export interface BridgeIpc {
  /** Send to the dock renderer. */
  send(channel: string, ...args: unknown[]): void
  /** Subscribe to a renderer message; `senderOk(event)` already ran. Returns the unsubscribe. */
  on(channel: string, listener: (...args: unknown[]) => void): () => void
}

const MAX_CHUNK_CHARS = 16_384 // a 32 ms chunk is about 1.4 KB of base64; far more is not a microphone chunk
const MAX_CLIP_BYTES = 2_000_000
const B64 = /^[A-Za-z0-9+/]*={0,2}$/

export interface BridgeOptions {
  micTimeoutMs?: number
  clipTimeoutMs?: number
}

export interface Bridge {
  audio: AudioBridge
  clips: ClipPlayer
  dispose(): void
}

export function createBridgeIpc(ipc: BridgeIpc, o: BridgeOptions = {}): Bridge {
  let reqId = 0
  let micWanted = false
  let onChunk: ((b64: string, level: number) => void) | null = null
  let playing = false
  const idleCbs = new Set<() => void>()
  const waiting = new Map<number, (r: { ok: boolean; code?: string }) => void>()
  const clipWaiting = new Map<number, (ok: boolean) => void>()

  const offs = [
    ipc.on(LIVE_IPC.micChunk, (...args) => {
      const [b64, level] = args
      if (!micWanted || !onChunk) return
      if (typeof b64 !== 'string' || b64.length === 0 || b64.length > MAX_CHUNK_CHARS || !B64.test(b64)) return
      onChunk(b64, typeof level === 'number' && Number.isFinite(level) ? Math.min(1, Math.max(0, level)) : 0)
    }),
    ipc.on(LIVE_IPC.micResult, (...args) => {
      const r = args[0] as Partial<MicResult> | undefined
      if (!r || typeof r.reqId !== 'number') return
      const w = waiting.get(r.reqId)
      if (!w) return
      waiting.delete(r.reqId)
      w({ ok: r.ok === true, code: r.code === 'permission' ? 'permission' : 'device' })
    }),
    ipc.on(LIVE_IPC.playbackIdle, () => {
      playing = false
      for (const cb of [...idleCbs]) cb()
    }),
    ipc.on(LIVE_IPC.clipDone, (...args) => {
      const r = args[0] as { reqId?: unknown; ok?: unknown } | undefined
      if (!r || typeof r.reqId !== 'number') return
      const w = clipWaiting.get(r.reqId)
      if (!w) return
      clipWaiting.delete(r.reqId)
      w(r.ok === true)
    }),
  ]

  const audio: AudioBridge = {
    async startMic(cb) {
      const id = ++reqId
      onChunk = cb
      micWanted = true
      const result = await new Promise<{ ok: boolean; code?: string }>((resolve) => {
        const timer = setTimeout(() => {
          waiting.delete(id)
          resolve({ ok: false, code: 'device' })
        }, o.micTimeoutMs ?? 5000)
        waiting.set(id, (r) => {
          clearTimeout(timer)
          resolve(r)
        })
        ipc.send(LIVE_IPC.micStart, { reqId: id })
      })
      if (!result.ok) {
        micWanted = false
        onChunk = null
        throw new MicError(result.code === 'permission' ? 'permission' : 'device', 'the microphone could not be opened')
      }
    },
    stopMic() {
      micWanted = false
      onChunk = null
      ipc.send(LIVE_IPC.micStop)
    },
    play(b64) {
      if (typeof b64 !== 'string' || b64.length === 0) return
      playing = true
      ipc.send(LIVE_IPC.play, b64)
    },
    flush() {
      playing = false
      ipc.send(LIVE_IPC.flush)
    },
    onPlaybackIdle(cb) {
      idleCbs.add(cb)
      return () => void idleCbs.delete(cb)
    },
    isPlaying: () => playing,
  }

  const clips: ClipPlayer = {
    play(bytes, mime) {
      if (bytes.length === 0 || bytes.length > MAX_CLIP_BYTES || !/^audio\/[a-z0-9.+-]{2,30}$/.test(mime)) return Promise.resolve()
      const id = ++reqId
      return new Promise<void>((resolve) => {
        const timer = setTimeout(() => {
          clipWaiting.delete(id)
          resolve()
        }, o.clipTimeoutMs ?? 15_000)
        clipWaiting.set(id, () => {
          clearTimeout(timer)
          resolve()
        })
        // A copy as an ArrayBuffer: structured clone across IPC.
        const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
        ipc.send(LIVE_IPC.clipPlay, { reqId: id, mime, bytes: copy })
      })
    },
    stop() {
      for (const [id, w] of clipWaiting) {
        clipWaiting.delete(id)
        w(false)
      }
      ipc.send(LIVE_IPC.clipStop)
    },
  }

  return {
    audio,
    clips,
    dispose() {
      for (const off of offs) off()
      waiting.clear()
      clipWaiting.clear()
      idleCbs.clear()
    },
  }
}
