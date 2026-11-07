// One-shot Electron integration run (<= ~100 s, holds the electron lock only while running): real Electron main + dock renderer,
// fake microphone fed from a WAV ("Hey Marcus, can you show me where the start call button is?"), REAL wake spotter + REAL
// Live voice (ephemeral tokens), every other service mocked, audio output muted. Drives and observes through the debug HTTP.
import { spawn, execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { REPO, OUT, log, sleep } from './harness.mjs'

const port = 7855
const wav = path.join(OUT, 'wake_full.wav')
{ // 7 s of silence (spotter connects), the phrase, then silence
  const aiff = path.join(OUT, 'wake.aiff'), w16 = path.join(OUT, 'wake16.wav')
  execFileSync('say', ['-v', 'Samantha', '-o', aiff, 'Hey Marcus, can you show me where the start call button is?'])
  execFileSync('afconvert', ['-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', aiff, w16])
  execFileSync('python3', ['-c', `
import wave
r=wave.open("${w16}"); f=r.readframes(r.getnframes()); r.close()
w=wave.open("${wav}","wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
w.writeframes(b"\\x00\\x00"*16000*7+f+b"\\x00\\x00"*16000*60); w.close()`])
}
const mockAll = Object.fromEntries(['CAPTURE', 'OVERLAY', 'GROUNDER', 'VERIFIER', 'ARCHITECT', 'SCAM', 'ROUTER', 'LEARNER', 'LEVELS', 'RUNNER', 'TEACHING', 'AGENTS'].map((n) => [`ALONGSIDE_MOCK_${n}`, '1']))
const ud = path.join(OUT, 'userdata'); mkdirSync(ud, { recursive: true })
const child = spawn('scripts/electron-lock.sh', ['live', 'npx', 'electron', '.', '--enable-logging', '--no-sandbox', '--mute-audio', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${wav}%noloop`], {
  cwd: REPO, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
  env: { ...process.env, ...mockAll, ELECTRON_ENABLE_LOGGING: '1', ALONGSIDE_HEADLESS: '1', ALONGSIDE_NO_OVERLAY: '1', ALONGSIDE_DEBUG_PORT: String(port), ALONGSIDE_USERDATA: ud, ALONGSIDE_LOCK_WAIT: '0', ALONGSIDE_LOCK_MAX_SECONDS: '110' },
})
let logs = ''
const onData = (d) => { logs += d.toString() }
child.stdout.on('data', onData); child.stderr.on('data', onData)
let exited = false
child.on('exit', (c) => { exited = true; log('electron exited', c) })
const kill = () => { try { process.kill(-child.pid, 'SIGTERM') } catch {} }
process.on('SIGINT', () => { kill(); process.exit(130) })

const get = async (p) => (await fetch(`http://127.0.0.1:${port}${p}`)).json()
const post = async (p, body = {}) => (await fetch(`http://127.0.0.1:${port}${p}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json()

const t0 = Date.now()
await sleep(1800)
if (exited) { log('electron lock busy (child exited early); try again later'); process.exit(75) }
let healthy = false
for (let i = 0; i < 40 && !exited; i++) { try { await get('/health'); healthy = true; break } catch { await sleep(500) } }
if (!healthy) { log('app did not start; log tail:\n' + logs.slice(-600)); kill(); process.exit(75) }
log('app up', ((Date.now() - t0) / 1000).toFixed(1) + 's')

const seen = { phases: [], user: '', assistant: [], liveAt: null, speakingAt: null, error: '' }
let lastPhase = ''
const sample = async () => {
  const s = await get('/state')
  if (s.phase !== lastPhase) { lastPhase = s.phase; seen.phases.push(`${((Date.now() - t0) / 1000).toFixed(1)}s ${s.phase}`); log('phase', s.phase) }
  if (s.phase === 'live' && !seen.liveAt) seen.liveAt = Date.now()
  if (s.phase === 'speaking' && !seen.speakingAt) seen.speakingAt = Date.now()
  const caps = s.captions ?? []
  seen.user = caps.filter((c) => c.speaker === 'user' && c.final).map((c) => c.text).join(' ') || seen.user
  seen.assistant = caps.filter((c) => c.speaker === 'assistant' && c.final).map((c) => c.text)
  if (s.lastError) seen.error = s.lastError
  return s
}
const until = async (pred, ms) => { const end = Date.now() + ms; while (Date.now() < end && !exited) { const s = await sample().catch(() => null); if (s && pred(s)) return s; await sleep(400) } return null }

// 1) wake by voice -> Live -> model answers
await until((s) => seen.assistant.length >= 1, 55_000)
log('after wake: user said', JSON.stringify(seen.user), '| assistant', JSON.stringify(seen.assistant))
// 2) stage-direction injection (main -> dock -> Live)
const before = seen.assistant.length
if (seen.liveAt) {
  await post('/inject', { text: '[RUNNER] Step 1 of 2: tell the learner, in one short sentence, to look at the green button at the bottom of the window.', interrupt: false })
  await until(() => seen.assistant.length > before, 14_000)
  log('after inject: assistant', JSON.stringify(seen.assistant.slice(before)))
}
// 3) Stop returns everything to rest
await post('/stop')
const rested = await until((s) => ['listening_for_name', 'asleep'].includes(s.phase), 8_000)
log('after stop: phase', rested?.phase)
let dockShot = ''
try { const r = await fetch(`http://127.0.0.1:${port}/dock.png`); if (r.ok) { dockShot = path.join(OUT, 'dock-e2e.png'); writeFileSync(dockShot, Buffer.from(await r.arrayBuffer())) } } catch {}
kill()
await sleep(1500)

const liveLogs = logs.split('\n').filter((l) => /\[live\]|ERROR/.test(l)).map((l) => l.slice(0, 220)).slice(0, 20)
console.log(JSON.stringify({ seen, rested: rested?.phase ?? null, wakeToLiveMs: seen.liveAt ? seen.liveAt - t0 : null, dockShot, liveLogs }, null, 1))
const checks = [
  ['voice wake -> session live', !!seen.liveAt],
  ['user speech captioned', /start|call|button/i.test(seen.user)],
  ['assistant replied (captions)', seen.assistant.length >= 1],
  ['phase reached speaking', !!seen.speakingAt],
  ['Stop returns to rest', !!rested],
]
let bad = 0
for (const [n, ok] of checks) { log(ok ? 'PASS' : 'FAIL', n); if (!ok) bad++ }
process.exit(bad ? 1 : 0)
