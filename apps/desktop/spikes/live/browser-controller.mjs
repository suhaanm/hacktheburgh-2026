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

const wav = process.argv[2] ?? path.join(OUT, 'wake_full.wav')
const runMs = Number(process.argv[3] ?? 40_000)
await build({
  entryPoints: [path.join(REPO, 'src/renderer/dock/controller.ts')], bundle: true, format: 'iife', globalName: 'DockController', platform: 'browser',
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
const ctx = await browser.newContext({ permissions: ['microphone'] })
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

await page.goto(`http://127.0.0.1:${server.address().port}/`)
await page.addScriptTag({ url: '/c.js' })
await page.evaluate(() => window.DockController.startController())
log('controller started; fake mic plays the wake phrase after 7 s of silence')
await sleep(runMs)
const final = await page.evaluate(() => window.__alongsideTest.getState())
log('FINAL state phase', final.phase, 'lastError', final.lastError ?? '-')
const tr = events.filter((e) => e.k === 'transcript' && e.v.final)
console.log(JSON.stringify({
  wake: events.find((e) => e.k === 'wakeDetected')?.v ?? null,
  statuses: events.filter((e) => e.k === 'status').map((e) => `${((e.t - events[0].t) / 1000).toFixed(1)}s ${e.v.phase}`),
  tools: events.filter((e) => e.k === 'toolCall').map((e) => `${e.v.name} ${JSON.stringify(e.v.args)}`),
  lines: tr.map((e) => `${e.v.role}: ${e.v.text}`),
  ended: events.filter((e) => e.k === 'sessionEnded').map((e) => e.v),
  lastError: final.lastError ?? null,
}, null, 1))
await browser.close()
server.close()
process.exit(0)
