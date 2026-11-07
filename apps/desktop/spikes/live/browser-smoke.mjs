// Runs the REAL browser audio path (MicCapture + AudioPlayer AudioWorklets) in headless Chrome with a fake microphone fed from
// a WAV file, against the real gemini-3.8-live. Verifies what Node fakes cannot: worklets load from Blob URLs, 16 kHz capture,
// 24 kHz playback, level metering, phase detection. Output audio is muted (--mute-audio); the user's real screen is not touched.
import http from 'node:http'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { build } from 'esbuild'
import { chromium } from 'playwright-core'
import { OUT, REPO, TEST_SYSTEM_INSTRUCTION, log, mintAuth } from './harness.mjs'

await build({ entryPoints: [path.join(REPO, 'src/renderer/live/index.ts')], bundle: true, format: 'iife', globalName: 'AlongsideLive', platform: 'browser', outfile: path.join(OUT, 'live.iife.js'), logLevel: 'error' })
const js = readFileSync(path.join(OUT, 'live.iife.js'))
const html = `<!doctype html><meta charset=utf-8><title>live browser smoke</title><body>ok</body><script src="/live.iife.js"></script>`
const server = http.createServer((req, res) => {
  if (req.url === '/live.iife.js') { res.setHeader('content-type', 'text/javascript'); res.end(js) } else { res.setHeader('content-type', 'text/html'); res.end(html) }
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const url = `http://127.0.0.1:${server.address().port}/`

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${path.join(OUT, 'q1_full.wav')}%noloop`, '--autoplay-policy=no-user-gesture-required', '--mute-audio'],
})
const ctx = await browser.newContext({ permissions: ['microphone'] })
const page = await ctx.newPage()
page.on('console', (m) => { const t = m.text(); if (!/DevTools|Download the React/.test(t)) log('  [page]', t.slice(0, 200)) })
page.on('pageerror', (e) => log('  [pageerror]', e.message))
await page.exposeFunction('mintAuth', () => mintAuth('token'))
await page.goto(url)

const result = await page.evaluate(async ({ si }) => {
  const L = window.AlongsideLive
  const out = { bytes: 0, maxLevel: 0, maxIn: 0, phases: [], transcripts: [], tools: [], metrics: [], errors: [], speakingSeen: false, idleCalls: 0, micTracksEnded: null }
  class CountingPlayer extends L.AudioPlayer {
    play(b) { out.bytes += b.length * 0.75; super.play(b) }
  }
  const t0 = performance.now()
  out.timing = {}
  const mark = (k) => (out.timing[k] = Math.round(performance.now() - t0))
  class TimedMic extends L.MicCapture { async start(cb) { mark('micStart'); await super.start(cb); mark('micReady') } }
  class TimedPlayer extends CountingPlayer { async init() { mark('playerInit'); await super.init(); mark('playerReady') } }
  const player = new TimedPlayer()
  player.onIdle(() => out.idleCalls++)
  const session = new L.LiveSession({
    host: { getAuth: async () => { mark('authStart'); const a = await window.mintAuth(); mark('authReady'); return a }, systemInstruction: async () => si },
    audioIn: new TimedMic(),
    audioOut: player,
    model: 'gemini-3.8-live',
    idleTimeoutMs: 0,
    toolHandler: async (c) => { await new Promise((r) => setTimeout(r, 300)); return c.name === 'point_at' ? { found: true, confidence: 0.9 } : { ok: true } },
  })
  session.on('state', (s) => out.phases.push(s.phase))
  session.on('transcript', (t) => t.final && out.transcripts.push(t.role + ': ' + t.text))
  session.on('toolCall', (c) => out.tools.push(c.name + ' ' + JSON.stringify(c.args)))
  session.on('metrics', (m) => out.metrics.push(m))
  session.on('error', (e) => out.errors.push(e.message))
  const poll = setInterval(() => { out.maxLevel = Math.max(out.maxLevel, session.getOutputLevel()); out.maxIn = Math.max(out.maxIn, session.getInputLevel()) }, 40)
  await session.start({ voiceName: 'Charon' })
  await new Promise((r) => setTimeout(r, 16000))
  out.speakingSeen = out.phases.includes('speaking')
  await session.stop('stop')
  clearInterval(poll)
  out.finalPhase = session.phase
  return out
}, { si: TEST_SYSTEM_INSTRUCTION })

log('RESULT', JSON.stringify(result, null, 1).slice(0, 2500))
const checks = [
  ['worklet capture + token auth: session reached live', result.phases.includes('live')],
  ['user speech transcribed from the fake mic', result.transcripts.some((t) => /^user:.*(start|call|button)/i.test(t))],
  ['model audio received', result.bytes > 20000],
  ['AudioPlayer worklet drained (idle callback)', result.idleCalls > 0],
  ['output level metered (orb) > 0', result.maxLevel > 0.02],
  ['input level metered > 0', result.maxIn > 0.01],
  ['phase went speaking', result.speakingSeen],
  ['point_at tool call emitted', result.tools.some((t) => t.startsWith('point_at'))],
  ['ended cleanly', result.finalPhase === 'ended' && result.errors.length === 0],
]
let bad = 0
for (const [n, ok] of checks) { log(ok ? 'PASS' : 'FAIL', n); if (!ok) bad++ }
await browser.close()
server.close()
process.exit(bad ? 1 : 0)
