// Runs the REAL dock controller (wake spotter + Live session + mic arbitration) in headless Chrome with a fake window.alongside
// (token minting + canned tool results done here in Node), a fake microphone WAV and the real Gemini APIs. Same code path as the
// Electron dock minus main/IPC, with full console visibility. Output audio is muted.
import http from 'node:http'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { build } from 'esbuild'
import { chromium } from 'playwright-core'
import { GoogleGenAI, Modality } from '@google/genai'
import { OUT, REPO, log, mintAuth, sleep } from './harness.mjs'

const scenario = process.argv[2] ?? 'text'  // text = chat in text mode, no mic permission needed | voice-denied = voice mode but microphone permission denied
const wav = path.join(OUT, 'q1_full.wav')
await build({
  entryPoints: [path.join(REPO, 'spikes/live/dock-entry.mts')], bundle: true, format: 'iife', globalName: 'Dock', platform: 'browser',
  outfile: path.join(OUT, 'controller.iife.js'), logLevel: 'error', define: { 'process.env.NODE_ENV': '"production"' },
  nodePaths: [path.join(REPO, 'node_modules')],
})
const js = readFileSync(path.join(OUT, 'controller.iife.js'))
const server = http.createServer((req, res) => {
  if (req.url === '/c.js') { res.setHeader('content-type', 'text/javascript'); res.end(js) } else { res.setHeader('content-type', 'text/html'); res.end('<!doctype html><meta charset=utf-8><body>dock</body>') }
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${wav}%noloop`, '--autoplay-policy=no-user-gesture-required', '--mute-audio', '--no-sandbox'],
})
const ctx = await browser.newContext({ permissions: scenario === 'voice-denied' ? [] : ['microphone'] })
const page = await ctx.newPage()
page.on('console', (m) => { const t = m.text(); if (!/DevTools|Ephemeral token support/.test(t)) log('  [page]', t.slice(0, 260)) })
page.on('pageerror', (e) => log('  [pageerror]', e.message))

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY, httpOptions: { apiVersion: 'v1beta' } })
const mintWake = async () => {
  const now = Date.now()
  const t = await ai.authTokens.create({ config: { uses: 1, expireTime: new Date(now + 10 * 60_000).toISOString(), newSessionExpireTime: new Date(now + 60_000).toISOString(), liveConnectConstraints: { model: 'gemini-3.5-transcribe-live', config: { responseModalities: [Modality.TEXT], inputAudioTranscription: {} } }, httpOptions: { apiVersion: 'v1beta' } } })
  return { token: t.name, model: 'gemini-3.5-transcribe-live', expiresAt: now + 600_000 }
}
import { fakeDesktopJpeg } from './harness.mjs'
const TINY = process.env.FRAME === 'real' ? fakeDesktopJpeg(0) : readFileSync(path.join(REPO, 'src/main/mocks.ts'), 'utf8').match(/TINY_JPEG\s*=\s*\n?\s*['"`]([A-Za-z0-9+/=]+)['"`]/)[1]
const events = []
const note = (k, v) => { events.push({ t: Date.now(), k, v }); log('  [alongside]', k, JSON.stringify(v).slice(0, 200)) }
await page.exposeFunction('nodeLiveToken', async () => ({ token: (await mintAuth('token')).value, model: 'gemini-3.8-live', expiresAt: Date.now() + 1_800_000 }))
await page.exposeFunction('nodeWakeToken', mintWake)
await page.exposeFunction('nodeNote', note)

await page.addInitScript(() => {
  // Wire tap: summarise every Live WebSocket message (never the audio payload itself).
  const OrigWS = window.WebSocket
  const sum = (raw) => {
    try {
      const m = JSON.parse(typeof raw === 'string' ? raw : new TextDecoder().decode(raw))
      const k = Object.keys(m)[0]
      if (k === 'realtimeInput') { const r = m.realtimeInput; const kk = Object.keys(r)[0]; return `realtimeInput.${kk}${kk === 'audio' ? '(' + r.audio.data.length + 'b64)' : kk === 'video' ? '(' + r.video.data.length + 'b64)' : ':' + JSON.stringify(r[kk]).slice(0, 80)}` }
      if (k === 'serverContent') { const c = m.serverContent; return 'serverContent:' + Object.keys(c).join(',') }
      if (k === 'setup') return 'setup tools=' + (m.setup.tools?.[0]?.functionDeclarations?.length ?? 0) + ' resumption=' + JSON.stringify(m.setup.sessionResumption) + ' model=' + m.setup.model
      return k + ' ' + JSON.stringify(m[k]).slice(0, 100)
    } catch { return '(unparsed)' }
  }
  let seq = 0
  window.WebSocket = class extends OrigWS {
    constructor(url, ...rest) {
      super(url, ...rest)
      const id = ++seq
      if (!String(url).includes('transcribe') && String(url).includes('Constrained')) {
        const tag = `ws${id}`
        let lastAudio = 0, audioN = 0, videoN = 0
        const send = this.send.bind(this)
        this.send = (d) => { const t = sum(d); if (/audio/.test(t)) audioN++; else if (/video/.test(t)) videoN++; else window.nodeNote(tag + ' ->', t + ` [audio sent so far ${audioN}, video ${videoN}]`); return send(d) }
        this.addEventListener('message', async (e) => { const raw = e.data instanceof ArrayBuffer ? e.data : e.data; const t = sum(raw); if (!/serverContent:(modelTurn|outputTranscription)/.test(t) || Date.now() - lastAudio > 1500) { lastAudio = Date.now(); window.nodeNote(tag + ' <-', t) } })
        this.addEventListener('close', (e) => window.nodeNote(tag + ' CLOSE', { code: e.code, reason: e.reason }))
      }
    }
  }
})
await page.addInitScript(({ tiny }) => {
  const stateCbs = [], startCbs = [], stopCbs = [], injectCbs = []
  let state = { persona: null, phase: 'listening_for_name', micMuted: false, level: 2, levelLocked: false, captions: [], agents: [], lastError: undefined,
    settings: { wakeEnabled: true, pushToTalkOnly: false, captions: true, demoMode: true } }
  const push = () => stateCbs.forEach((cb) => cb(structuredClone(state)))
  const patch = (p) => { state = { ...state, ...p }; push() }
  window.__alongsideTest = { startCbs, stopCbs, injectCbs, getState: () => state }
  window.alongside = {
    getState: async () => structuredClone(state), onState: (cb) => { stateCbs.push(cb); return () => {} },
    patchState: async (p) => { window.nodeNote('patchState', p); patch(p) },
    getSettings: async () => state.settings, patchSettings: async () => state.settings,
    wakeDetected: (req) => { window.nodeNote('wakeDetected', req); patch({ persona: req.personaId, phase: 'connecting' }); setTimeout(() => startCbs.forEach((cb) => cb(req)), 30) },
    onSessionStart: (cb) => { startCbs.push(cb); return () => {} }, onSessionStop: (cb) => { stopCbs.push(cb); return () => {} },
    sessionEnded: (r) => { window.nodeNote('sessionEnded', r); patch({ phase: 'listening_for_name' }) }, pressStop: () => {},
    live: {
      getToken: () => window.nodeLiveToken(), systemInstruction: async (id) => `MOCK system instruction for ${id}. Speak plainly in one or two short sentences. You are an AI.`,
      toolCall: async (c) => { window.nodeNote('toolCall', c); return c.name === 'point_at' ? { found: true, confidence: 0.92, note: c.args.target } : { ok: true } },
      onInject: (cb) => { injectCbs.push(cb); return () => {} },
      transcript: (t) => window.nodeNote('transcript', t), status: (s) => { window.nodeNote('status', s); if (s.connected || s.phase === 'error') patch({ phase: s.phase }) },
      liveFrame: async () => ({ jpegBase64: tiny, changeScore: 0 }),
    },
    wake: { getToken: () => window.nodeWakeToken() },
  }
}, { tiny: TINY })

if (scenario === 'voice-denied') await page.addInitScript(() => {
  navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('Permission denied', 'NotAllowedError'))
})
await page.goto(`http://127.0.0.1:${server.address().port}/`)
await page.addScriptTag({ url: '/c.js' })
await page.evaluate(() => {
  window.__msgs = []
  window.Dock.chatBus.subscribe((m) => (window.__msgs = m))
  window.Dock.startController({ wake: false })
})
const send = scenario === 'text' ? 'Hi! In one short sentence, how do I make the text bigger on my computer?' : 'Hello, are you there? Answer in one short sentence.'
if (scenario === 'text') await page.evaluate(() => window.Dock.chatBus.setMode('text'))
log('scenario', scenario, '| typing:', send)
const t0 = Date.now()
await page.evaluate((t) => window.Dock.chatBus.send(t), send)
let reply = null
for (let i = 0; i < 40 && !reply; i++) {
  await sleep(500)
  const msgs = await page.evaluate(() => window.__msgs)
  reply = msgs.find((m) => m.role === 'assistant' && m.final) ?? null
}
const msgs = await page.evaluate(() => window.__msgs)
const mode = await page.evaluate(() => window.Dock.chatBus.mode())
const state = await page.evaluate(() => window.__alongsideTest.getState())
const sockets = events.filter((e) => /^ws\d+ CLOSE|ws\d+ ->/.test(e.k + ' ' + (typeof e.v === 'string' ? e.v : ''))).length
const audioSent = events.some((e) => typeof e.v === 'string' && /audio sent so far [1-9]/.test(e.v))
console.log(JSON.stringify({ replyMs: reply ? Date.now() - t0 : null, msgs: msgs.map((m) => `${m.via}/${m.role}${m.final ? '' : '~'}: ${m.text.slice(0, 90)}`), mode, wake: events.find((e) => e.k === 'wakeDetected')?.v ?? null, micAudioUploaded: audioSent, lastError: state.lastError ?? null }, null, 1))
const checks = [
  ['typed message with no session started one (wakeDetected via button)', !!events.find((e) => e.k === 'wakeDetected')],
  ['assistant reply arrived in the chat bus', !!reply],
  ['reply is a voice-via assistant bubble, typed bubble kept as typed', msgs.some((m) => m.via === 'typed' && m.role === 'user') && !!reply],
  ['no microphone audio uploaded in this scenario', !audioSent],
  ...(scenario === 'voice-denied' ? [['mic denied: chat switched to text mode and a plain-English banner is set', mode === 'text' && /microphone/i.test(state.lastError ?? '')]] : []),
]
let bad = 0
for (const [n, ok] of checks) { log(ok ? 'PASS' : 'FAIL', n); if (!ok) bad++ }
await browser.close()
server.close()
process.exit(bad ? 1 : 0)
