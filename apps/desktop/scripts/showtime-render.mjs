#!/usr/bin/env node
// Renders the Showtime narration: assets/showtime/script.json -> assets/showtime/clips/<id>.wav + manifest.json.
// Format and hash must match src/main/showtime/narration.ts (ClipManifest, textHash = sha1(resolved text).slice(0, 16)).
// Usage: npm run showtime:render [-- --force] [-- --only id1,id2] [-- --dry-run] [-- --strict]
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { config as loadEnv } from 'dotenv'
import { GoogleGenAI } from '@google/genai'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SCRIPT = path.join(REPO, 'assets/showtime/script.json')
const CLIPS = path.join(REPO, 'assets/showtime/clips')
const MANIFEST = path.join(CLIPS, 'manifest.json')

// Verified against https://aistudio.google.com/docs/speech-generation.md (Gemini 3.8 TTS runs through the Interactions API).
const MODEL = process.env.MODEL_TTS || 'gemini-3.8-flash-tts'
const SAMPLE_RATE = 24_000
const CONCURRENCY = 3
// Same defaults as the Live controller (src/renderer/dock/controller.ts FALLBACK_VOICE) while personas.ts says 'TBD'.
const FALLBACK_VOICE = { male: 'Charon', female: 'Sulafat' }
// Turn-level delivery for older listeners. The doc advises one short constant style string, not a long persona block.
const STYLE = 'calm and warm, clear and steady, at a natural conversational pace'
const OVER_BUDGET = 1.1

const args = new Set(process.argv.slice(2))
const onlyArg = process.argv.slice(2).find((a) => a.startsWith('--only='))?.slice('--only='.length)
const onlyIdx = process.argv.indexOf('--only')
const only = new Set(
  (onlyArg ?? (onlyIdx >= 0 ? process.argv[onlyIdx + 1] : '') ?? '').split(',').map((s) => s.trim()).filter(Boolean),
)
const force = args.has('--force')
const dryRun = args.has('--dry-run')
const strict = args.has('--strict')

const textHash = (text) => createHash('sha1').update(text).digest('hex').slice(0, 16)

// personas.ts is TypeScript, so read the three fields we need from each persona block.
function readPersonas() {
  const src = readFileSync(path.join(REPO, 'src/shared/personas.ts'), 'utf8')
  const out = {}
  const start = src.indexOf('export const PERSONAS')
  const re = /^ {2}(\w+): \{([\s\S]*?)^ {2}\},?$/gm
  for (const m of src.slice(start).matchAll(re)) {
    const body = m[2]
    const pick = (k) => body.match(new RegExp(`${k}: '([^']*)'`))?.[1]
    const displayName = pick('displayName')
    const gender = pick('gender')
    if (!displayName || !gender) continue
    const configured = pick('voiceName')
    out[m[1]] = {
      displayName,
      voice: configured && configured !== 'TBD' ? configured : (FALLBACK_VOICE[gender] ?? FALLBACK_VOICE.male),
    }
  }
  return out
}

function wav(pcm, rate) {
  const h = Buffer.alloc(44)
  h.write('RIFF', 0)
  h.writeUInt32LE(36 + pcm.length, 4)
  h.write('WAVE', 8)
  h.write('fmt ', 12)
  h.writeUInt32LE(16, 16)
  h.writeUInt16LE(1, 20) // PCM
  h.writeUInt16LE(1, 22) // mono
  h.writeUInt32LE(rate, 24)
  h.writeUInt32LE(rate * 2, 28)
  h.writeUInt16LE(2, 32)
  h.writeUInt16LE(16, 34)
  h.write('data', 36)
  h.writeUInt32LE(pcm.length, 40)
  return Buffer.concat([h, pcm])
}

// The API returns headerless PCM for audio/l16 but a RIFF file for audio/wav; accept both and always re-wrap.
function toPcm(buf) {
  if (buf.length > 44 && buf.toString('ascii', 0, 4) === 'RIFF' && buf.toString('ascii', 8, 12) === 'WAVE') {
    let rate = SAMPLE_RATE
    let channels = 1
    let bits = 16
    for (let o = 12; o + 8 <= buf.length; ) {
      const id = buf.toString('ascii', o, o + 4)
      const size = buf.readUInt32LE(o + 4)
      if (id === 'fmt ') {
        channels = buf.readUInt16LE(o + 10)
        rate = buf.readUInt32LE(o + 12)
        bits = buf.readUInt16LE(o + 22)
      } else if (id === 'data') {
        if (channels !== 1 || bits !== 16) throw new Error(`unexpected WAV format: ${channels} ch, ${bits}-bit`)
        return { pcm: buf.subarray(o + 8, Math.min(buf.length, o + 8 + size)), rate }
      }
      o += 8 + size + (size % 2)
    }
    throw new Error('WAV without a data chunk')
  }
  return { pcm: buf, rate: SAMPLE_RATE }
}

function createClient() {
  if (!process.env.GEMINI_API_KEY) loadEnv({ path: path.join(REPO, '.env'), quiet: true })
  if (!process.env.GEMINI_API_KEY) throw new Error('GEMINI_API_KEY is not set (put it in .env)')
  return new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY })
}

async function synth(client, text, voice) {
  const interaction = await client.interactions.create({
    model: MODEL,
    input: [
      {
        type: 'user_input',
        content: [{ type: 'text', text, annotations: [{ type: 'speech_metadata', style: STYLE }] }],
      },
    ],
    response_format: { type: 'audio', mime_type: 'audio/l16', sample_rate: SAMPLE_RATE },
    generation_config: { speech_config: [{ voice }] },
  })
  const data = interaction.output_audio?.data
  if (!data) throw new Error('response had no audio')
  const { pcm, rate } = toPcm(Buffer.from(data, 'base64'))
  if (pcm.length < rate / 4) throw new Error(`audio too short (${pcm.length} bytes)`)
  return { pcm: pcm.subarray(0, pcm.length - (pcm.length % 2)), rate }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function withRetry(fn) {
  try {
    return await fn()
  } catch (first) {
    await sleep(first?.status === 429 ? 6000 : 1500)
    return await fn().catch((second) => {
      throw new Error(second instanceof Error ? second.message : String(second))
    })
  }
}

function readManifest() {
  try {
    const m = JSON.parse(readFileSync(MANIFEST, 'utf8'))
    return m && typeof m.lines === 'object' ? m : null
  } catch {
    return null
  }
}

function writeManifest(lines) {
  const tmp = `${MANIFEST}.tmp`
  writeFileSync(tmp, `${JSON.stringify({ generatedAt: new Date().toISOString(), model: MODEL, lines }, null, 2)}\n`)
  renameSync(tmp, MANIFEST)
}

async function main() {
  const script = JSON.parse(readFileSync(SCRIPT, 'utf8'))
  const personas = readPersonas()
  const all = script.lines.map((l) => {
    const p = personas[l.persona]
    if (!p) throw new Error(`line ${l.id}: unknown persona ${l.persona}`)
    return { ...l, text: l.text.replace(/\{name\}/g, p.displayName), voice: p.voice }
  })
  const todo = only.size ? all.filter((l) => only.has(l.id)) : all
  mkdirSync(CLIPS, { recursive: true })

  const prev = readManifest()
  const entries = {}
  const queue = []
  for (const l of all) {
    const e = prev?.lines?.[l.id]
    const fresh =
      !force &&
      e &&
      e.textHash === textHash(l.text) &&
      e.voice === l.voice &&
      e.persona === l.persona &&
      prev.model === MODEL &&
      existsSync(path.join(CLIPS, e.file))
    if (fresh) entries[l.id] = e
    else if (todo.includes(l)) queue.push(l)
    else if (e && existsSync(path.join(CLIPS, e.file))) entries[l.id] = e
  }
  console.log(`${all.length} lines, ${all.length - queue.length} up to date, ${queue.length} to render (model ${MODEL})`)
  if (dryRun || queue.length === 0) {
    if (queue.length === 0) report(all, entries, [])
    return
  }

  const client = createClient()
  const failures = []
  let next = 0
  const worker = async () => {
    while (next < queue.length) {
      const l = queue[next++]
      try {
        const { pcm, rate } = await withRetry(() => synth(client, l.text, l.voice))
        const file = `${l.id}.wav`
        writeFileSync(path.join(CLIPS, file), wav(pcm, rate))
        entries[l.id] = {
          file,
          persona: l.persona,
          voice: l.voice,
          textHash: textHash(l.text),
          durationMs: Math.round((pcm.length / 2 / rate) * 1000),
        }
        writeManifest(orderLike(all, entries))
        console.log(`ok   ${l.id} (${l.voice}) ${(entries[l.id].durationMs / 1000).toFixed(1)}s`)
      } catch (err) {
        failures.push({ id: l.id, error: err instanceof Error ? err.message : String(err) })
        console.error(`FAIL ${l.id}: ${failures.at(-1).error}`)
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, worker))
  writeManifest(orderLike(all, entries))
  report(all, entries, failures)
}

const orderLike = (all, entries) => Object.fromEntries(all.filter((l) => entries[l.id]).map((l) => [l.id, entries[l.id]]))

function report(all, entries, failures) {
  const budget = new Map(all.map((l) => [l.id, l.durationMs]))
  const over = []
  let total = 0
  for (const [id, e] of Object.entries(entries)) {
    total += e.durationMs
    const b = budget.get(id)
    if (b && e.durationMs > b * OVER_BUDGET) over.push(`${id} ${e.durationMs}ms > ${b}ms slot`)
  }
  console.log(`${Object.keys(entries).length}/${all.length} clips, ${(total / 1000).toFixed(1)}s audio`)
  if (over.length) console.warn(`OVER-LONG (>${Math.round(OVER_BUDGET * 100)}% of slot):\n  ${over.join('\n  ')}`)
  if (failures.length) console.error(`FAILED: ${failures.map((f) => f.id).join(', ')}`)
  if (failures.length || (strict && over.length)) process.exitCode = 1
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err)
  process.exitCode = 1
})
