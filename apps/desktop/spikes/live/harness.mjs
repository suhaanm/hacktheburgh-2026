// Shared helpers for the Live smoke tests: bundles the real renderer LiveSession for Node, fakes the browser audio IO
// (real-time paced), mints auth, generates speech with macOS say/afconvert. Never prints the API key.
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { deflateSync } from 'node:zlib'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'
import { build } from 'esbuild'
import { GoogleGenAI } from '@google/genai'

const here = path.dirname(fileURLToPath(import.meta.url))
export const REPO = path.resolve(here, '../..')
export const OUT = path.join(here, 'out')
mkdirSync(OUT, { recursive: true })

dotenv.config({ path: path.join(REPO, '.env'), quiet: true })
const KEY = process.env.GEMINI_API_KEY
if (!KEY) {
  console.error('GEMINI_API_KEY missing in REPO/.env (live tests blocked)')
  process.exit(2)
}

export const t0 = Date.now()
export const stamp = () => `${((Date.now() - t0) / 1000).toFixed(2).padStart(7)}s`
export const log = (...a) => console.log(stamp(), ...a)
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ---------- bundle the real module ----------
export async function loadLive() {
  const outfile = path.join(OUT, 'live.bundle.mjs')
  await build({
    entryPoints: [path.join(REPO, 'src/renderer/live/index.ts')],
    bundle: true,
    format: 'esm',
    platform: 'node',
    outfile,
    logLevel: 'error',
    external: [],
  })
  return import(`${outfile}?t=${Date.now()}`)
}

// The real TEACH system instruction (so behaviour tests see what the app sends).
export async function realSystemInstruction(persona = 'marcus') {
  const outfile = path.join(OUT, 'prompt.bundle.mjs')
  await build({ entryPoints: [path.join(here, 'prompt-entry.mts')], bundle: true, format: 'esm', platform: 'node', outfile, logLevel: 'error', nodePaths: [path.join(REPO, 'node_modules')] })
  const mod = await import(`${outfile}?t=${Date.now()}`)
  return mod.realSystemInstruction(persona)
}

// ---------- auth ----------
export async function mintAuth(mode = 'token') {
  if (mode === 'key') return { kind: 'key', value: KEY }
  const ai = new GoogleGenAI({ apiKey: KEY, httpOptions: { apiVersion: 'v1beta' } })
  const tok = await ai.authTokens.create({
    config: {
      uses: 1,
      expireTime: new Date(Date.now() + 30 * 60_000).toISOString(),
      newSessionExpireTime: new Date(Date.now() + 2 * 60_000).toISOString(),
      httpOptions: { apiVersion: 'v1beta' },
    },
  })
  return { kind: 'token', value: tok.name }
}

// ---------- speech ----------
export function speech(name, text, voice = 'Samantha') {
  const aiff = path.join(OUT, `${name}.aiff`)
  const wav = path.join(OUT, `${name}.wav`)
  if (!existsSync(wav)) {
    execFileSync('say', ['-v', voice, '-o', aiff, text])
    execFileSync('afconvert', ['-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', aiff, wav])
  }
  return wavToPcm(readFileSync(wav))
}

function wavToPcm(buf) {
  let off = 12
  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4)
    const size = buf.readUInt32LE(off + 4)
    if (id === 'data') return buf.subarray(off + 8, Math.min(buf.length, off + 8 + size))
    off += 8 + size + (size % 2)
  }
  throw new Error('no data chunk')
}

// ---------- synthetic screen frames (PNG -> JPEG via sips; never touches the real screen) ----------
function crc32(b) {
  let c, crc = ~0
  for (let i = 0; i < b.length; i++) {
    c = (crc ^ b[i]) & 0xff
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    crc = (crc >>> 8) ^ c
  }
  return ~crc >>> 0
}
function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const td = Buffer.concat([Buffer.from(type), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(td))
  return Buffer.concat([len, td, crc])
}
export function fakeDesktopJpeg(variant = 0) {
  const W = 1280, H = 720
  const raw = Buffer.alloc((W * 3 + 1) * H)
  const fill = (x0, y0, x1, y1, [r, g, b]) => {
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
      const o = y * (W * 3 + 1) + 1 + x * 3
      raw[o] = r; raw[o + 1] = g; raw[o + 2] = b
    }
  }
  for (let y = 0; y < H; y++) raw[y * (W * 3 + 1)] = 0
  fill(0, 0, W, H, [236, 240, 245]) // desktop
  fill(180, 90, 1100, 640, [255, 255, 255]) // window
  fill(180, 90, 1100, 140, [60, 90, 160]) // title bar
  fill(300, 200, 700, 520, [30, 35, 45]) // video area
  fill(740, 220, 1060, 300, [225, 230, 240]) // sidebar rows
  fill(740, 320, 1060, 400, [225, 230, 240])
  fill(430 + variant * 6, 560, 570 + variant * 6, 615, [30, 150, 80]) // green "start call" button (moves a little per variant)
  fill(600, 560, 700, 615, [200, 60, 60]) // red end button
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4); ihdr[8] = 8; ihdr[9] = 2
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
  const p = path.join(OUT, `frame${variant}.png`)
  const j = path.join(OUT, `frame${variant}.jpg`)
  writeFileSync(p, png)
  execFileSync('sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '60', p, '--out', j], { stdio: 'ignore' })
  return readFileSync(j).toString('base64')
}

// ---------- fake browser audio IO, paced in real time ----------
export function fakeMic() {
  const CHUNK = 512 // 32 ms @ 16 kHz, same as the capture worklet
  let queue = []
  let timer = null
  let onChunk = null
  const api = {
    sentSamples: 0,
    async start(cb) {
      onChunk = cb
      timer = setInterval(() => {
        const pcm = queue.shift()
        const i16 = new Int16Array(CHUNK)
        if (pcm) i16.set(new Int16Array(pcm.buffer, pcm.byteOffset, CHUNK))
        else for (let i = 0; i < CHUNK; i++) i16[i] = (Math.random() - 0.5) * 20 // faint room noise
        let sum = 0
        for (let i = 0; i < CHUNK; i++) sum += (i16[i] / 32768) ** 2
        api.sentSamples += CHUNK
        onChunk(Buffer.from(i16.buffer).toString('base64'), Math.sqrt(sum / CHUNK))
      }, 32)
    },
    stop() {
      if (timer) clearInterval(timer)
      timer = null
    },
    // Queue 16 kHz PCM16 speech (Buffer); returns a promise that resolves when all of it has been streamed.
    say(pcm, { leadMs = 300, tailMs = 0 } = {}) {
      const bytesPerChunk = CHUNK * 2
      const lead = Buffer.alloc(Math.round((leadMs / 32) * bytesPerChunk))
      const tail = Buffer.alloc(Math.round((tailMs / 32) * bytesPerChunk))
      const all = Buffer.concat([lead, pcm, tail])
      const n = Math.floor(all.length / bytesPerChunk)
      for (let i = 0; i < n; i++) queue.push(all.subarray(i * bytesPerChunk, (i + 1) * bytesPerChunk))
      return new Promise((resolve) => {
        const check = setInterval(() => {
          if (queue.length === 0) {
            clearInterval(check)
            resolve()
          }
        }, 20)
      })
    },
    get queued() {
      return queue.length
    },
  }
  return api
}

export function fakeSpeaker() {
  let playEnd = 0
  let idleTimer = null
  const idleCbs = new Set()
  const api = {
    bytes: 0,
    chunks: 0,
    flushes: [],
    lastPlayAt: 0,
    async init() {},
    play(b64) {
      const n = Buffer.from(b64, 'base64').length
      api.bytes += n
      api.chunks++
      api.lastPlayAt = Date.now()
      const dur = (n / 2 / 24000) * 1000
      playEnd = Math.max(Date.now(), playEnd) + dur
      if (idleTimer) clearTimeout(idleTimer)
      idleTimer = setTimeout(() => {
        for (const cb of idleCbs) cb()
      }, playEnd - Date.now() + 5)
    },
    flush() {
      api.flushes.push(Date.now())
      playEnd = Date.now()
      if (idleTimer) clearTimeout(idleTimer)
      idleTimer = setTimeout(() => {
        for (const cb of idleCbs) cb()
      }, 5)
    },
    level: () => (Date.now() < playEnd ? 0.3 : 0),
    isPlaying: () => Date.now() < playEnd,
    onIdle(cb) {
      idleCbs.add(cb)
      return () => idleCbs.delete(cb)
    },
    close() {
      if (idleTimer) clearTimeout(idleTimer)
    },
    get queuedMs() {
      return Math.max(0, playEnd - Date.now())
    },
  }
  return api
}

export const TEST_SYSTEM_INSTRUCTION = `You are Marcus, an AI helper (never pretend to be human) who sits alongside an older adult and teaches them to use their computer.
Speak plain English in one or two short sentences. Never say "just" or "simply". You can see the learner's screen as small pictures.
When the learner asks where something is on screen, say where to look AND call the point_at tool with a visual description of that element in the same turn; if point_at returns found=false say you cannot see it.
Messages that start with [RUNNER] or [STALL] are stage directions from the app: obey them and speak to the learner naturally.
Answer every utterance addressed to you. If asked to explain steps, give them one at a time but keep going until you have covered them.`

// Records every session event with a timestamp for the final report.
export function recordEvents(session) {
  const rec = { events: [], byType: {} }
  for (const name of ['transcript', 'state', 'toolCall', 'toolDone', 'error', 'ended', 'resumption', 'metrics']) {
    session.on(name, (p) => {
      rec.events.push({ at: Date.now(), name, p })
      rec.byType[name] = (rec.byType[name] ?? 0) + 1
    })
  }
  return rec
}

export function waitFor(session, name, pred = () => true, timeoutMs = 30_000) {
  return new Promise((resolve, reject) => {
    const off = session.on(name, (p) => {
      if (pred(p)) {
        clearTimeout(timer)
        off()
        resolve(p)
      }
    })
    const timer = setTimeout(() => {
      off()
      reject(new Error(`timeout waiting for ${name}`))
    }, timeoutMs)
  })
}
