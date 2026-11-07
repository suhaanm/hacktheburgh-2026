// Which (mint version x endpoint version) combinations accept an ephemeral token? Live voice model and the wake transcribe model.
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'
import { GoogleGenAI, Modality } from '@google/genai'
const here = path.dirname(fileURLToPath(import.meta.url))
dotenv.config({ path: path.join(here, '../../.env'), quiet: true })
const KEY = process.env.GEMINI_API_KEY
if (!KEY) { console.error('no key'); process.exit(2) }

async function mint(version, kind) {
  const ai = new GoogleGenAI({ apiKey: KEY, httpOptions: { apiVersion: version } })
  const now = Date.now()
  const config = { uses: 1, expireTime: new Date(now + 10 * 60_000).toISOString(), newSessionExpireTime: new Date(now + 60_000).toISOString(), httpOptions: { apiVersion: version } }
  if (kind === 'wake') config.liveConnectConstraints = { model: 'gemini-3.5-transcribe-live', config: { responseModalities: [Modality.TEXT], inputAudioTranscription: {} } }
  return (await ai.authTokens.create({ config })).name
}

function tryConnect(endpointVersion, token, kind) {
  return new Promise((resolve) => {
    const url = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.${endpointVersion}.GenerativeService.BidiGenerateContentConstrained?access_token=${encodeURIComponent(token)}`
    const ws = new WebSocket(url)
    const done = (r) => { try { ws.close() } catch {} resolve(r) }
    const timer = setTimeout(() => done('timeout'), 8000)
    ws.onopen = () => {
      const setup = kind === 'wake'
        ? { setup: { model: 'models/gemini-3.5-transcribe-live', generationConfig: { responseModalities: ['TEXT'] }, inputAudioTranscription: {} } }
        : { setup: { model: 'models/gemini-3.8-live', generationConfig: { responseModalities: ['AUDIO'] } } }
      ws.send(JSON.stringify(setup))
    }
    ws.onmessage = async (e) => {
      const t = typeof e.data === 'string' ? e.data : Buffer.from(await e.data.arrayBuffer()).toString()
      if (t.includes('setupComplete')) { clearTimeout(timer); done('OK') }
    }
    ws.onclose = (e) => { clearTimeout(timer); done(`closed ${e.code} ${e.reason}`.slice(0, 90)) }
  })
}

for (const kind of ['live', 'wake']) {
  for (const mv of ['v1beta', 'v1alpha']) {
    for (const ev of ['v1beta', 'v1alpha']) {
      let tok
      try { tok = await mint(mv, kind) } catch (e) { console.log(kind, 'mint', mv, 'FAILED', String(e.message).slice(0, 120)); continue }
      console.log(kind.padEnd(5), 'mint', mv.padEnd(7), 'connect', ev.padEnd(7), '->', await tryConnect(ev, tok, kind))
    }
  }
}
