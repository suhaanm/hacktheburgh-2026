// Renders the audition sentence in every prebuilt voice through the REAL Live model (so you hear exactly what a session will
// sound like) into tools/voice-audition/<Voice>.wav + manifest.json. Run: node voices.mjs [Voice ...]
import { mkdirSync, writeFileSync, existsSync } from 'node:fs'
import path from 'node:path'
import { loadLive, mintAuth, log, REPO } from './harness.mjs'

const SENTENCE = "Hello, I'm your helper. I'll sit alongside you while you learn."
// Descriptors are from the speech-generation docs; the docs do not state gender (see the page).
const VOICES = {
  Zephyr: 'Bright', Puck: 'Upbeat', Charon: 'Informative', Kore: 'Firm', Fenrir: 'Excitable', Leda: 'Youthful', Orus: 'Firm',
  Aoede: 'Breezy', Callirrhoe: 'Easy-going', Autonoe: 'Bright', Enceladus: 'Breathy', Iapetus: 'Clear', Umbriel: 'Easy-going',
  Algieba: 'Smooth', Despina: 'Smooth', Erinome: 'Clear', Algenib: 'Gravelly', Rasalgethi: 'Informative', Laomedeia: 'Upbeat',
  Achernar: 'Soft', Alnilam: 'Firm', Schedar: 'Even', Gacrux: 'Mature', Pulcherrima: 'Forward', Achird: 'Friendly',
  Zubenelgenubi: 'Casual', Vindemiatrix: 'Gentle', Sadachbia: 'Lively', Sadaltager: 'Knowledgeable', Sulafat: 'Warm',
}
const only = process.argv.slice(2)
const outDir = path.join(REPO, 'tools/voice-audition')
mkdirSync(outDir, { recursive: true })

function wav(pcm, rate = 24000) {
  const h = Buffer.alloc(44)
  h.write('RIFF', 0); h.writeUInt32LE(36 + pcm.length, 4); h.write('WAVEfmt ', 8)
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(rate, 24)
  h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(pcm.length, 40)
  return Buffer.concat([h, pcm])
}

const live = await loadLive()
const manifest = []
for (const [name, descriptor] of Object.entries(VOICES)) {
  if (only.length && !only.includes(name)) continue
  const file = path.join(outDir, `${name}.wav`)
  const chunks = []
  let transcript = ''
  let done
  const finished = new Promise((r) => (done = r))
  const conn = new live.LiveConnection({
    getAuth: () => mintAuth('token'),
    buildSetup: (h) =>
      live.buildSetup({
        model: 'gemini-3.8-live',
        voiceName: name,
        systemInstruction: `You read out the sentence the user sends, word for word, in a calm, warm, unhurried voice. You never add anything before or after it.`,
        tools: [],
        resumptionHandle: h,
      }),
    onEvent: (e) => {
      if (e.type === 'audio') chunks.push(Buffer.from(e.base64, 'base64'))
      if (e.type === 'outputTranscription') transcript += e.text
      if (e.type === 'turnComplete' || e.type === 'generationComplete') done()
    },
    onClosed: () => done(),
  })
  try {
    await conn.connect()
    conn.send(live.msg.text(`Read this sentence out loud exactly: "${SENTENCE}"`))
    await Promise.race([finished, new Promise((r) => setTimeout(r, 15000))])
    await new Promise((r) => setTimeout(r, 400))
    const pcm = Buffer.concat(chunks)
    writeFileSync(file, wav(pcm))
    manifest.push({ name, descriptor, seconds: +(pcm.length / 48000).toFixed(1), transcript: transcript.trim() })
    log(name.padEnd(14), descriptor.padEnd(14), `${(pcm.length / 48000).toFixed(1)}s`, JSON.stringify(transcript.trim()).slice(0, 80))
  } catch (err) {
    log(name, 'FAILED', err.message)
  } finally {
    conn.close()
  }
}
if (!only.length) writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({ sentence: SENTENCE, voices: manifest }, null, 2))
process.exit(0)
