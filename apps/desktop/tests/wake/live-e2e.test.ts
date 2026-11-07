// Opt-in (WAKE_LIVE=1): the real spotter + real gemini-3.5-transcribe-live + a production-style ephemeral token,
// fed by `say`-generated audio from spikes/wake/audio (run `node spikes/wake/gen-audio.mjs` first). Costs a few API calls.
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import dotenv from 'dotenv'
import { describe, expect, it } from 'vitest'
import { PERSONA_LIST } from '../../src/shared/personas'
import { mintWakeToken } from '../../src/main/live-auth'
import { createWakeSpotter, type WakeAudioSource, type WakeEvent } from '../../src/renderer/wake'

dotenv.config({ path: join(__dirname, '..', '..', '.env'), quiet: true })
const enabled = process.env.WAKE_LIVE === '1' && !!process.env.GEMINI_API_KEY
const audioDir = join(__dirname, '..', '..', 'spikes', 'wake', 'audio')

function wavPcm(id: string): Int16Array {
  const buf = readFileSync(join(audioDir, `${id}.wav`))
  const start = buf.indexOf(Buffer.from('data')) + 8
  return new Int16Array(buf.buffer.slice(buf.byteOffset + start, buf.byteOffset + buf.byteLength - ((buf.byteLength - start) % 2)))
}

// A microphone stand-in: 1 s of room tone, then the clip, then endless quiet noise, all paced at real time.
class WavMic implements WakeAudioSource {
  speechEndedAt = 0
  private timer: ReturnType<typeof setInterval> | null = null
  constructor(private readonly pcm: Int16Array) {}
  async start(onPcm: (p: Int16Array) => void): Promise<void> {
    const frame = 1600
    let i = -10
    this.timer = setInterval(() => {
      const out = new Int16Array(frame)
      if (i < 0 || i * frame >= this.pcm.length) for (let k = 0; k < frame; k++) out[k] = Math.round((Math.random() - 0.5) * 60)
      else out.set(this.pcm.subarray(i * frame, (i + 1) * frame))
      if (i >= 0 && (i + 1) * frame >= this.pcm.length && !this.speechEndedAt) this.speechEndedAt = Date.now()
      i++
      onPcm(out)
    }, 100)
  }
  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }
}

async function run(id: string, listenMs: number): Promise<{ wakes: WakeEvent[]; latencyMs: number | null; heard: string[] }> {
  const mic = new WavMic(wavPcm(id))
  const wakes: WakeEvent[] = []
  let wokeAt = 0
  const heard: string[] = []
  const spotter = createWakeSpotter({
    personas: PERSONA_LIST,
    getToken: () => mintWakeToken(),
    createAudioSource: () => mic,
    onDebug: (text, final) => heard.push(`${final ? 'F' : 'i'}:${text}`),
    onWake: (e) => {
      wokeAt = Date.now()
      wakes.push(e)
    },
  })
  await spotter.start()
  await new Promise((r) => setTimeout(r, listenMs))
  spotter.dispose()
  return { wakes, latencyMs: wokeAt && mic.speechEndedAt ? wokeAt - mic.speechEndedAt : null, heard }
}

describe.skipIf(!enabled || !existsSync(audioDir))('wake spotter end-to-end through gemini-3.5-transcribe-live', () => {
  const positives: [string, string][] = [
    ['marcus.daniel', 'marcus'],
    ['amelia.karen', 'amelia'],
    ['marcus-q.samantha', 'marcus'],
    ['amelia-q.tara', 'amelia'],
    ['marcus.rishi', 'marcus'],
    ['marcus.fred', 'marcus'],
    ['amelia.flous', 'amelia'],
  ]
  const latencies: number[] = []
  it.each(positives)('wakes on %s -> %s', async (id, persona) => {
    const { wakes, latencyMs, heard } = await run(id, 9000)
    expect(wakes.map((w) => w.personaId), `recogniser said: ${JSON.stringify(heard)}`).toEqual([persona])
    if (latencyMs !== null) latencies.push(latencyMs)
    console.log(`[wake-e2e] ${id} -> ${wakes[0]!.personaId} heard=${JSON.stringify(wakes[0]!.heard)} score=${wakes[0]!.score.toFixed(2)} latency-after-end-of-speech=${latencyMs}ms`)
  }, 20_000)

  const negatives = ['neg-google.daniel', 'neg-alexa.samantha', 'neg-aurelius.samantha', 'neg-mark.rishi', 'neg-america.daniel', 'neg-emily.rishi', 'neg-musicus.daniel', 'neg-help.samantha', 'neg-chat.daniel', 'neg-amelia-past.rishi']
  it.each(negatives)('does NOT wake on %s', async (id) => {
    const { wakes, heard } = await run(id, 10_000)
    expect(wakes, `recogniser said: ${JSON.stringify(heard)}`).toEqual([])
  }, 25_000)
})
