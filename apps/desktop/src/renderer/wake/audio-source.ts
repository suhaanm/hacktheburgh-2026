/// <reference lib="dom" />
import { floatToPcm16 } from './preroll'
import type { WakeAudioSource } from './types'

const WORKLET = `
class WakeCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch && ch.length) this.port.postMessage(ch.slice(0))
    return true
  }
}
registerProcessor('wake-capture', WakeCapture)
`

const FRAME_SAMPLES = 1600 // 100 ms at 16 kHz, the chunk size transcribe-live recommends

export function defaultGetStream(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
}

// Opens the mic via getStream, resamples to 16 kHz mono PCM16 in 100 ms frames, and releases every track on stop().
export function createMicAudioSource(getStream: () => Promise<MediaStream> = defaultGetStream): WakeAudioSource {
  let stream: MediaStream | null = null
  let ctx: AudioContext | null = null
  let stopped = false

  return {
    async start(onPcm) {
      stopped = false
      const s = await getStream()
      if (stopped) {
        s.getTracks().forEach((t) => t.stop())
        return
      }
      stream = s
      ctx = new AudioContext({ sampleRate: 16000 })
      const source = ctx.createMediaStreamSource(s)
      let pending = new Int16Array(0)
      const emit = (pcm: Int16Array): void => {
        const merged = new Int16Array(pending.length + pcm.length)
        merged.set(pending)
        merged.set(pcm, pending.length)
        let off = 0
        while (merged.length - off >= FRAME_SAMPLES) {
          onPcm(merged.slice(off, off + FRAME_SAMPLES))
          off += FRAME_SAMPLES
        }
        pending = merged.slice(off)
      }
      try {
        const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
        await ctx.audioWorklet.addModule(url)
        URL.revokeObjectURL(url)
        const node = new AudioWorkletNode(ctx, 'wake-capture')
        node.port.onmessage = (ev: MessageEvent<Float32Array>) => emit(floatToPcm16(ev.data))
        source.connect(node)
        // The node must reach a destination for Chromium to pull audio through it; gain 0 keeps it silent.
        const mute = ctx.createGain()
        mute.gain.value = 0
        node.connect(mute).connect(ctx.destination)
      } catch {
        // Worklet blocked (strict CSP): fall back to the deprecated but universally available ScriptProcessor.
        const proc = ctx.createScriptProcessor(4096, 1, 1)
        proc.onaudioprocess = (ev) => emit(floatToPcm16(ev.inputBuffer.getChannelData(0)))
        source.connect(proc)
        proc.connect(ctx.destination)
      }
    },
    stop() {
      stopped = true
      stream?.getTracks().forEach((t) => t.stop())
      stream = null
      void ctx?.close().catch(() => undefined)
      ctx = null
    },
  }
}
