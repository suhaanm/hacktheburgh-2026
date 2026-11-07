// Shared fakes for the voice tests. Nothing here touches a real microphone, screen, network host or key: a local websocket server speaks the
// parts of the Live protocol the code uses, the audio bridge is in memory, and the "microphone" is a synthetic tone.
import { createRequire } from 'node:module'
import type { AddressInfo } from 'node:net'
import { pcmBytesToBase64 } from './wire'
import { MicError, type AudioBridge, type LiveCuePort } from './ports'
import type { Timers } from './clock'
import type { GateVerdict } from './gates'

const require = createRequire(import.meta.url)
const { WebSocketServer } = require('ws') as { WebSocketServer: new (o: { port: number; host: string }) => WsServer }

interface WsSocket {
  send(data: string): void
  close(code?: number, reason?: string): void
  terminate(): void
  on(event: 'message', cb: (data: Buffer) => void): void
  on(event: 'close', cb: () => void): void
}
interface WsServer {
  on(event: 'connection', cb: (sock: WsSocket, req: { headers: Record<string, string | string[] | undefined>; url?: string }) => void): void
  on(event: 'listening', cb: () => void): void
  address(): AddressInfo | string | null
  close(cb?: () => void): void
  clients: Set<WsSocket>
}

// ------------------------------------------------------------------------------------------------ signals
/** PCM16 mono little-endian: a sine tone. The "microphone" for the tests. */
export function tonePcm(seconds: number, rate = 16000, hz = 220, amp = 0.3): Int16Array {
  const n = Math.round(seconds * rate)
  const out = new Int16Array(n)
  for (let i = 0; i < n; i++) out[i] = Math.round(Math.sin((2 * Math.PI * hz * i) / rate) * amp * 32767)
  return out
}

/** Split PCM into ~32 ms base64 chunks (512 samples at 16 kHz), as the renderer's capture worklet does. */
export function chunks32ms(pcm: Int16Array, samples = 512): string[] {
  const out: string[] = []
  for (let i = 0; i < pcm.length; i += samples) {
    const part = pcm.subarray(i, Math.min(pcm.length, i + samples))
    out.push(pcmBytesToBase64(new Uint8Array(part.buffer, part.byteOffset, part.byteLength)))
  }
  return out
}

/** A model audio chunk (24 kHz PCM16) of `ms` milliseconds, as base64. */
export const modelAudio = (ms: number): string => pcmBytesToBase64(new Uint8Array(Math.round((ms / 1000) * 24000) * 2))

// ------------------------------------------------------------------------------------------------ fake audio bridge
export interface FakeAudio extends AudioBridge {
  micOpen: boolean
  micStarts: number
  micStops: number
  played: string[]
  flushes: number
  failMic: 'permission' | 'device' | null
  // The renderer takes this long to open the microphone.
  startDelayMs: number
  feed(b64: string, level?: number): void
  idle(): void
}

export function createFakeAudio(): FakeAudio {
  let onChunk: ((b64: string, level: number) => void) | null = null
  const idleCbs = new Set<() => void>()
  const a: FakeAudio = {
    micOpen: false,
    micStarts: 0,
    micStops: 0,
    played: [],
    flushes: 0,
    failMic: null,
    startDelayMs: 0,
    async startMic(cb) {
      if (a.startDelayMs) await new Promise((r) => setTimeout(r, a.startDelayMs))
      if (a.failMic) throw new MicError(a.failMic, 'no mic')
      a.micOpen = true
      a.micStarts += 1
      onChunk = cb
    },
    stopMic() {
      a.micOpen = false
      a.micStops += 1
      onChunk = null
    },
    play(b64) {
      a.played.push(b64)
    },
    flush() {
      a.flushes += 1
    },
    onPlaybackIdle(cb) {
      idleCbs.add(cb)
      return () => void idleCbs.delete(cb)
    },
    isPlaying: () => a.played.length > 0,
    feed(b64, level = 0.3) {
      onChunk?.(b64, level)
    },
    idle() {
      for (const cb of [...idleCbs]) cb()
    },
  }
  return a
}

// ------------------------------------------------------------------------------------------------ fake Live server
export interface Received {
  setup: Record<string, unknown> | null
  audio: number
  audioBytes: number
  video: number
  videoBytes: number
  text: string[]
  streamEnds: number
  activityStarts: number
  activityEnds: number
  toolResponses: Array<Record<string, unknown>>
  authHeader: string | undefined
  url: string | undefined
  connections: number
  raw: string[]
}

export interface FakeLiveServer {
  url: string
  received: Received
  /** Send a server message to the newest client. */
  send(message: object): void
  /** Called when the worker's turn ends (audioStreamEnd or activityEnd). Default: a short spoken reply with usage. */
  onTurnEnd: (server: FakeLiveServer) => void
  /** Called for each toolResponse. */
  onSetup: (server: FakeLiveServer) => void
  /** Drop the newest client abruptly (no close frame). */
  drop(): void
  /** Refuse the websocket upgrade-ish: close right after the open. */
  closeNext: boolean
  // Close every new connection right away (a network that is gone for good).
  refuseAll: boolean
  setupDelayMs: number
  close(): Promise<void>
}

export const replyScript = (server: FakeLiveServer, o: { audioMs?: number; chunks?: number; usage?: boolean } = {}): void => {
  const n = o.chunks ?? 2
  for (let i = 0; i < n; i++) server.send({ serverContent: { modelTurn: { parts: [{ inlineData: { mimeType: 'audio/pcm;rate=24000', data: modelAudio(o.audioMs ?? 400) } }] } } })
  server.send({ serverContent: { outputTranscription: { text: 'Ok.' } } })
  server.send({ serverContent: { generationComplete: true } })
  server.send({
    serverContent: { turnComplete: true },
    ...(o.usage === false
      ? {}
      : { usageMetadata: { promptTokenCount: 600, responseTokenCount: 30, totalTokenCount: 630, promptTokensDetails: [{ modality: 'TEXT', tokenCount: 380 }, { modality: 'AUDIO', tokenCount: 220 }], responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 30 }], thoughtsTokenCount: 40 } }),
  })
}

export async function startFakeLiveServer(): Promise<FakeLiveServer> {
  const wss = new WebSocketServer({ port: 0, host: '127.0.0.1' })
  await new Promise<void>((r) => wss.on('listening', r))
  const port = (wss.address() as AddressInfo).port
  let current: WsSocket | null = null
  const received: Received = { setup: null, audio: 0, audioBytes: 0, video: 0, videoBytes: 0, text: [], streamEnds: 0, activityStarts: 0, activityEnds: 0, toolResponses: [], authHeader: undefined, url: undefined, connections: 0, raw: [] }
  const server: FakeLiveServer = {
    url: `ws://127.0.0.1:${port}/live`,
    received,
    send: (m) => current?.send(JSON.stringify(m)),
    onTurnEnd: (s) => replyScript(s),
    onSetup: () => undefined,
    drop: () => current?.terminate(),
    closeNext: false,
    refuseAll: false,
    setupDelayMs: 0,
    close: () =>
      new Promise<void>((resolve) => {
        for (const c of wss.clients) c.terminate()
        wss.close(() => resolve())
      }),
  }
  wss.on('connection', (sock, req) => {
    current = sock
    received.connections += 1
    const auth = req.headers.authorization
    received.authHeader = Array.isArray(auth) ? auth[0] : auth
    received.url = req.url
    if (server.closeNext || server.refuseAll) {
      server.closeNext = false
      sock.close(1011, 'test close')
      return
    }
    sock.on('message', (data: Buffer) => {
      let m: Record<string, any>
      try {
        m = JSON.parse(data.toString())
      } catch {
        return
      }
      if (m.setup) {
        received.setup = m.setup
        setTimeout(() => {
          sock.send(JSON.stringify({ setupComplete: {} }))
          server.onSetup(server)
        }, server.setupDelayMs)
        return
      }
      const ri = m.realtimeInput
      if (ri) {
        if (ri.audio) {
          received.audio += 1
          received.audioBytes += Math.floor((String(ri.audio.data).length * 3) / 4)
        }
        if (ri.video) {
          received.video += 1
          received.videoBytes += Math.floor((String(ri.video.data).length * 3) / 4)
        }
        if (typeof ri.text === 'string') received.text.push(ri.text)
        if (ri.audioStreamEnd) {
          received.streamEnds += 1
          setTimeout(() => server.onTurnEnd(server), 5)
        }
        if (ri.activityStart) received.activityStarts += 1
        if (ri.activityEnd) {
          received.activityEnds += 1
          setTimeout(() => server.onTurnEnd(server), 5)
        }
      }
      if (m.toolResponse) for (const fr of m.toolResponse.functionResponses ?? []) received.toolResponses.push(fr)
    })
  })
  return server
}

// ------------------------------------------------------------------------------------------------ manual clock
export interface ManualClock extends Timers {
  now(): number
  advance(ms: number): void
  active(): number
}

/** Timers and a clock the test moves by hand. `advance` fires everything due, in order. */
export function manualClock(start = 1_000_000): ManualClock {
  let t = start
  let id = 1
  const timers = new Map<number, { fn: () => void; due: number; every: number | null }>()
  return {
    now: () => t,
    setInterval(fn, ms) {
      const h = id++
      timers.set(h, { fn, due: t + ms, every: ms })
      return h
    },
    clearInterval(h) {
      timers.delete(h as number)
    },
    setTimeout(fn, ms) {
      const h = id++
      timers.set(h, { fn, due: t + ms, every: null })
      return h
    },
    clearTimeout(h) {
      timers.delete(h as number)
    },
    active: () => timers.size,
    advance(ms) {
      const end = t + ms
      for (;;) {
        let next: [number, { fn: () => void; due: number; every: number | null }] | null = null
        for (const e of timers) if (e[1].due <= end && (next === null || e[1].due < next[1].due)) next = e
        if (!next) break
        t = next[1].due
        if (next[1].every !== null) next[1].due += next[1].every
        else timers.delete(next[0])
        next[1].fn()
      }
      t = end
    },
  }
}

// ------------------------------------------------------------------------------------------------ misc ports
export const openVerdict = (over: Partial<GateVerdict> = {}): GateVerdict => ({ open: true, reason: null, gate: { consent: true, denylisted_app: false, secure_input: false, unattended: false }, at: Date.now(), ...over })

export function fakeCue(candidates: Array<{ id: string; label: string }> = [{ id: 'read_case', label: 'Read the household record' }, { id: 'calc_a', label: 'Run calculator A' }, { id: 'cliff_a', label: 'Check cliff edges (A)' }]): LiveCuePort & { shown: string[]; asked: string[][]; answer(id: string): void } {
  const cbs = new Set<(id: string) => void>()
  const c = {
    shown: [] as string[],
    asked: [] as string[][],
    candidates: () => candidates,
    showStep(id: string) {
      c.shown.push(id)
      const label = candidates.find((x) => x.id === id)?.label ?? null
      return { ok: label !== null, chip: label ? `Next: ${label}`.slice(0, 40) : null }
    },
    askChoice(ids: string[]) {
      c.asked.push(ids)
      return true
    },
    onAnswer(cb: (id: string) => void) {
      cbs.add(cb)
      return () => void cbs.delete(cb)
    },
    answer(id: string) {
      for (const cb of cbs) cb(id)
    },
  }
  return c
}

export const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

export async function waitFor(cond: () => boolean, ms = 3000, step = 10): Promise<void> {
  const end = Date.now() + ms
  while (!cond()) {
    if (Date.now() > end) throw new Error('waitFor timed out')
    await sleep(step)
  }
}
