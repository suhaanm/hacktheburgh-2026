// Adapted from google-gemini/gemini-live-api-examples — gemini-live-ephemeral-tokens-websocket/frontend/mediaUtils.js (AudioStreamer, AudioPlayer) and
// gemini-live-ephemeral-tokens-websocket/frontend/audio-processors/capture.worklet.js, playback.worklet.js
// Browser audio IO for the Live session; worklets are inlined as Blob URLs so no static asset path is needed under electron-vite.
import type { AudioInput, AudioOutput } from './types'
import { base64ToBytes, floatToPcm16Base64 } from './wire'

const CAPTURE_WORKLET = `
class AlongsideCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(512); this.n = 0 }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch) for (let i = 0; i < ch.length; i++) {
      this.buf[this.n++] = ch[i]
      if (this.n >= 512) { this.port.postMessage(this.buf.slice()); this.n = 0 } // 32 ms @ 16 kHz, per Gemini guidance (20-40 ms)
    }
    return true
  }
}
registerProcessor('alongside-capture', AlongsideCapture)
`

// Gapless queue + 1-block fade-out on interrupt (a hard cut clicks) + RMS level and drained notifications.
const PLAYBACK_WORKLET = `
class AlongsidePlayer extends AudioWorkletProcessor {
  constructor() {
    super()
    this.q = []; this.off = 0; this.fade = false; this.sum = 0; this.cnt = 0; this.playing = false
    this.port.onmessage = (e) => {
      if (e.data === 'interrupt') this.fade = true
      else if (e.data instanceof Float32Array) this.q.push(e.data)
    }
  }
  process(inputs, outputs) {
    const out = outputs[0] && outputs[0][0]
    if (!out) return true
    let i = 0
    while (i < out.length && this.q.length) {
      const cur = this.q[0]
      const n = Math.min(out.length - i, cur.length - this.off)
      for (let k = 0; k < n; k++) out[i++] = cur[this.off++]
      if (this.off >= cur.length) { this.q.shift(); this.off = 0 }
    }
    while (i < out.length) out[i++] = 0
    if (this.fade) {
      for (let k = 0; k < out.length; k++) out[k] *= 1 - (k + 1) / out.length
      this.q = []; this.off = 0; this.fade = false
    }
    for (let k = 0; k < out.length; k++) this.sum += out[k] * out[k]
    this.cnt += out.length
    if (this.cnt >= 960) { // every ~40 ms @ 24 kHz
      this.port.postMessage({ rms: Math.sqrt(this.sum / this.cnt) })
      this.sum = 0; this.cnt = 0
    }
    const nowPlaying = this.q.length > 0
    if (this.playing && !nowPlaying) this.port.postMessage({ idle: true })
    this.playing = nowPlaying
    return true
  }
}
registerProcessor('alongside-player', AlongsidePlayer)
`

async function addWorklet(ctx: AudioContext, code: string): Promise<void> {
  const url = URL.createObjectURL(new Blob([code], { type: 'application/javascript' }))
  try {
    await ctx.audioWorklet.addModule(url)
  } finally {
    URL.revokeObjectURL(url)
  }
}

export interface MicCaptureOptions {
  // Inject a stream (tests, or a shared mic); defaults to getUserMedia with AEC/NS/AGC on.
  getStream?: () => Promise<MediaStream>
}

export class MicCapture implements AudioInput {
  private stream: MediaStream | null = null
  private ctx: AudioContext | null = null
  private stopped = false

  constructor(private readonly o: MicCaptureOptions = {}) {}

  async start(onChunk: (base64Pcm16: string, level: number) => void): Promise<void> {
    this.stopped = false
    const stream = await (this.o.getStream?.() ??
      navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }))
    if (this.stopped) {
      stream.getTracks().forEach((t) => t.stop())
      return
    }
    this.stream = stream
    const ctx = new AudioContext({ sampleRate: 16000 })
    this.ctx = ctx
    await addWorklet(ctx, CAPTURE_WORKLET)
    const node = new AudioWorkletNode(ctx, 'alongside-capture')
    node.port.onmessage = (ev: MessageEvent<Float32Array>) => {
      if (this.stopped) return
      const f32 = ev.data
      let sum = 0
      for (let i = 0; i < f32.length; i++) sum += f32[i]! * f32[i]!
      onChunk(floatToPcm16Base64(f32), Math.sqrt(sum / f32.length))
    }
    ctx.createMediaStreamSource(stream).connect(node)
    // Chromium only pulls a worklet that reaches the destination; gain 0 keeps it silent.
    const mute = ctx.createGain()
    mute.gain.value = 0
    node.connect(mute).connect(ctx.destination)
    if (ctx.state === 'suspended') await ctx.resume()
  }

  stop(): void {
    this.stopped = true
    this.stream?.getTracks().forEach((t) => t.stop())
    this.stream = null
    void this.ctx?.close().catch(() => undefined)
    this.ctx = null
  }
}

export class AudioPlayer implements AudioOutput {
  private ctx: AudioContext | null = null
  private node: AudioWorkletNode | null = null
  private ready: Promise<void> | null = null
  private levelValue = 0
  private playing = false
  private idleCbs = new Set<() => void>()

  init(): Promise<void> {
    this.ready ??= (async () => {
      const ctx = new AudioContext({ sampleRate: 24000, latencyHint: 'interactive' })
      this.ctx = ctx
      await addWorklet(ctx, PLAYBACK_WORKLET)
      const node = new AudioWorkletNode(ctx, 'alongside-player', { numberOfInputs: 0, outputChannelCount: [1] })
      node.port.onmessage = (ev: MessageEvent<{ rms?: number; idle?: boolean }>) => {
        if (typeof ev.data.rms === 'number') this.levelValue = Math.max(Math.min(1, ev.data.rms * 4), this.levelValue * 0.8)
        if (ev.data.idle) {
          this.playing = false
          this.levelValue = 0
          for (const cb of this.idleCbs) cb()
        }
      }
      node.connect(ctx.destination)
      this.node = node
      if (ctx.state === 'suspended') await ctx.resume()
    })()
    return this.ready
  }

  play(base64Pcm16: string): void {
    if (!this.node) return
    const bytes = base64ToBytes(base64Pcm16)
    const i16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2))
    const f32 = new Float32Array(i16.length)
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i]! / 32768
    this.playing = true
    this.node.port.postMessage(f32, [f32.buffer])
  }

  flush(): void {
    this.playing = false
    this.levelValue = 0
    this.node?.port.postMessage('interrupt')
    for (const cb of this.idleCbs) cb()
  }

  level(): number {
    // Decay between worklet reports so the orb settles even if the worklet goes quiet.
    this.levelValue *= 0.97
    return this.levelValue
  }

  isPlaying(): boolean {
    return this.playing
  }

  onIdle(cb: () => void): () => void {
    this.idleCbs.add(cb)
    return () => this.idleCbs.delete(cb)
  }

  close(): void {
    this.idleCbs.clear()
    void this.ctx?.close().catch(() => undefined)
    this.ctx = null
    this.node = null
    this.ready = null
  }
}
