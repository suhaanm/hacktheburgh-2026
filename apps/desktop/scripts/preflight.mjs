#!/usr/bin/env node
// Stage-day preflight: a green/red table of everything that has gone wrong in past demos (key, network, Live, wake token,
// macOS permissions, screen grab, hotkeys, stage server, seed). Exits non-zero on any red. Never prints the API key.
//
// IMPORTANT: run this from the SAME terminal/launcher you will use on stage. macOS grants Microphone and Screen Recording
// to the "responsible app" that started the process (your Terminal, iTerm, VS Code...), so a preflight run from a different
// app proves nothing about the demo. The Electron probe below is started from this process, so it inherits that app.
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'
import { GoogleGenAI, Modality } from '@google/genai'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BASE = 'https://generativelanguage.googleapis.com/v1beta'
const started = Date.now()
const color = process.stdout.isTTY && !process.env.NO_COLOR
const paint = (code, s) => (color ? `\x1b[${code}m${s}\x1b[0m` : s)
const TAGS = { ok: paint('32;1', ' OK   '), warn: paint('33;1', ' WARN '), fail: paint('31;1', ' FAIL '), info: paint('36', ' INFO ') }

// The SDK prints experimental-feature notices for ephemeral tokens on every mint; they are noise in this table.
const warn = console.warn
console.warn = (...args) => {
  if (!/ephemeral token support/i.test(String(args[0]))) warn(...args)
}

const rows = []
const add = (name, status, detail, fix) => rows.push({ name, status, detail, fix })
const read = (rel) => (existsSync(join(root, rel)) ? readFileSync(join(root, rel), 'utf8') : '')
const ms = (n) => `${Math.round(n)} ms`
const sleep = (n) => new Promise((r) => setTimeout(r, n))

// ---------- environment ----------
const envFile = process.env.PREFLIGHT_ENV_FILE || join(root, '.env') // override is for testing the failure rows
const dotenvVars = existsSync(envFile) ? dotenv.parse(readFileSync(envFile)) : {}
const key = dotenvVars.GEMINI_API_KEY || ''
const scrub = (s) => (key ? String(s).split(key).join('***') : String(s))
// Plain text for the table: unwrap Google's JSON error body when there is one, never echo the key.
const errText = (e) => {
  const raw = scrub(e instanceof Error ? e.message : String(e))
  const brace = raw.indexOf('{')
  if (brace >= 0) {
    try {
      const msg = JSON.parse(raw.slice(brace))?.error?.message
      if (msg) return String(msg).replace(/\s+/g, ' ').slice(0, 160)
    } catch {
      // not JSON
    }
  }
  return raw.replace(/\s+/g, ' ').slice(0, 160)
}
const stagePort = Number(process.env.STAGE_PORT || dotenvVars.STAGE_PORT || 5180)
const debugPort = Number(process.env.ALONGSIDE_DEBUG_PORT || dotenvVars.ALONGSIDE_DEBUG_PORT || 7777)
const userData = process.env.ALONGSIDE_USERDATA || dotenvVars.ALONGSIDE_USERDATA || join(homedir(), '.alongside-demo')

// Model ids exactly as src/shared/models.ts resolves them (defaults, overridable by MODEL_* in .env).
function requiredModels() {
  const out = []
  for (const m of read('src/shared/models.ts').matchAll(/(\w+):\s*env\.(MODEL_\w+)\s*\|\|\s*'([^']+)'/g)) {
    out.push({ role: m[1], id: process.env[m[2]] || dotenvVars[m[2]] || m[3] })
  }
  return out
}
const OPTIONAL_MODELS = ['gemini-3.8-live-extended-thinking', 'gemini-3.8-flash-tts']
const apiVersion = read('src/main/live-auth.ts').match(/apiVersion:\s*'(\w+)'/)?.[1] || 'v1beta'

// ---------- Electron probe (started first, runs while the network checks run) ----------
function startProbe() {
  const electron = join(root, 'node_modules', '.bin', 'electron')
  if (!existsSync(electron)) return Promise.resolve({ error: 'node_modules/.bin/electron is missing (run npm install)' })
  const lock = join(root, 'scripts', 'electron-lock.sh')
  const env = { ...process.env, ALONGSIDE_LOCK_WAIT: process.env.ALONGSIDE_LOCK_WAIT || '30', ALONGSIDE_LOCK_MAX_SECONDS: '120' }
  const child = spawn('bash', [lock, 'PREFLIGHT', electron, join(root, 'scripts', 'preflight-probe.cjs')], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] })
  let out = ''
  let err = ''
  child.stdout.on('data', (d) => (out += d))
  child.stderr.on('data', (d) => (err += d))
  return new Promise((resolveProbe) => {
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
      resolveProbe({ error: 'the Electron probe did not finish in 90 s' })
    }, 90_000)
    child.on('close', () => {
      clearTimeout(timer)
      const line = out.split('\n').find((l) => l.startsWith('PREFLIGHT_PROBE '))
      if (line) return resolveProbe(JSON.parse(line.slice('PREFLIGHT_PROBE '.length)))
      resolveProbe({ error: /held by role/.test(err) ? 'another Electron instance holds the lock (scripts/electron-lock.sh); retry in a minute' : `the Electron probe printed nothing (${err.trim().split('\n').pop() || 'no stderr'})` })
    })
  })
}
const probeP = startProbe()

// ---------- local checks ----------
function localChecks() {
  const hasKey = key.length > 0
  add('.env with GEMINI_API_KEY', hasKey ? 'ok' : 'fail', hasKey ? 'present (value not shown)' : existsSync(envFile) ? '.env exists but GEMINI_API_KEY is empty' : '.env is missing', 'Create .env in the repo root with a line GEMINI_API_KEY=<your key> (type it in by hand; never paste it into chat or commit it).')

  const ignored = spawnSync('git', ['check-ignore', '-q', '.env'], { cwd: root })
  const tracked = spawnSync('git', ['ls-files', '--error-unmatch', '.env'], { cwd: root, stdio: 'ignore' })
  if (tracked.status === 0) add('.env is git-ignored', 'fail', '.env is TRACKED by git', 'Run: git rm --cached .env  (then commit). The key must never be in the repo.')
  else if (ignored.status === 0) add('.env is git-ignored', 'ok', 'ignored and untracked')
  else add('.env is git-ignored', 'fail', ignored.status === 1 ? 'git does NOT ignore .env' : 'could not run git check-ignore', 'Add a line ".env" to .gitignore, then run: git status  to confirm .env is not listed.')

  const personas = read('src/shared/personas.ts')
  const ids = [...personas.matchAll(/\bid:\s*'(\w+)'/g)].map((m) => m[1])
  const voices = [...personas.matchAll(/voiceName:\s*'([^']*)'/g)].map((m) => m[1])
  const tbd = ids.filter((_, i) => voices[i] === 'TBD')
  add('Persona voices chosen', tbd.length ? 'warn' : 'ok', tbd.length ? `still 'TBD' for ${tbd.join(', ')} (the app falls back to a default voice)` : ids.map((id, i) => `${id}=${voices[i]}`).join(', '), 'Optional for the demo: audition Google voices (Puck, Charon, Kore, Sulafat, Vindemiatrix...) and set voiceName in src/shared/personas.ts.')

  const seedPath = join(root, 'src/main/teaching/fixtures/demo-profile.md')
  const seed = existsSync(seedPath) ? readFileSync(seedPath, 'utf8') : null
  const applied = join(userData, 'profile.md')
  if (!seed) add('Demo seed profile', 'fail', 'src/main/teaching/fixtures/demo-profile.md is missing', 'Restore it from git: git checkout -- src/main/teaching/fixtures/demo-profile.md')
  else if (!existsSync(applied)) add('Demo seed profile', 'warn', `seed file present, not applied to ${applied}`, 'Run: npm run demo  (it applies the seed, with a backup of anything it replaces).')
  else if (readFileSync(applied, 'utf8') === seed) add('Demo seed profile', 'ok', `applied at ${applied}`)
  else add('Demo seed profile', 'warn', `${applied} differs from the seed (a previous run or edits)`, 'Fine for a rehearsal; for a clean demo run: npm run demo  (backs the old file up first).')

  if ((process.env.ALONGSIDE_MOCK || dotenvVars.ALONGSIDE_MOCK) === '1') add('Mock mode', 'warn', 'ALONGSIDE_MOCK=1 is set: canned data, no real model calls', 'Unset ALONGSIDE_MOCK for a real demo (or say clearly on stage that it is mock).')
  if (process.env.ALONGSIDE_REPLAY || dotenvVars.ALONGSIDE_REPLAY) add('Replay mode', 'info', `ALONGSIDE_REPLAY=${process.env.ALONGSIDE_REPLAY || dotenvVars.ALONGSIDE_REPLAY} (serves recorded responses)`)
  add('Grounding preset', 'info', process.env.ALONGSIDE_GROUNDING_PRESET || 'fast (default)')
  add('Runtime', 'info', `node ${process.versions.node}, ${process.platform}-${process.arch}`)
}

// ---------- network checks ----------
const api = (path, init = {}) => fetch(`${BASE}${path}`, { ...init, headers: { 'x-goog-api-key': key, ...(init.headers || {}) }, signal: AbortSignal.timeout(init.timeout ?? 8000) })

async function modelsCheck() {
  const t0 = Date.now()
  const names = new Set()
  try {
    let token = ''
    for (let page = 0; page < 6; page++) {
      const res = await api(`/models?pageSize=1000${token ? `&pageToken=${encodeURIComponent(token)}` : ''}`)
      if (!res.ok) {
        const bad = res.status === 400 || res.status === 401 || res.status === 403
        add('Gemini API key accepted (models.list)', 'fail', `HTTP ${res.status}${bad ? ' (key rejected)' : ''}`, bad ? 'The key is wrong, expired or restricted. Create a new key in Google AI Studio and put it in .env.' : 'Google returned an error; check the network and retry in a minute.')
        return false
      }
      const body = await res.json()
      for (const m of body.models ?? []) names.add(String(m.name).replace(/^models\//, ''))
      token = body.nextPageToken || ''
      if (!token) break
    }
  } catch (e) {
    add('Gemini API key accepted (models.list)', 'fail', `request failed: ${errText(e)}`, 'No route to generativelanguage.googleapis.com. Join the phone hotspot or check the venue Wi-Fi, then retry.')
    return false
  }
  add('Gemini API key accepted (models.list)', 'ok', `HTTP 200 in ${ms(Date.now() - t0)}, ${names.size} models visible`)
  const need = requiredModels()
  const missing = need.filter((m) => !names.has(m.id))
  add('Models the app uses are visible', missing.length ? 'fail' : 'ok', missing.length ? `not visible to this key: ${missing.map((m) => `${m.role}=${m.id}`).join(', ')}` : need.map((m) => m.id).join(', '), 'This key cannot see those models. Use the hackathon key, or override with MODEL_<ROLE> in .env (see src/shared/models.ts).')
  const extras = OPTIONAL_MODELS.map((id) => `${id}: ${names.has(id) ? 'visible' : 'not visible'}`)
  add('Optional models', 'info', extras.join(', '))
  return true
}

async function latencyCheck() {
  const target = requiredModels().find((m) => m.role === 'live')?.id ?? 'gemini-3.8-live'
  const times = []
  try {
    for (let i = 0; i < 3; i++) {
      const t0 = performance.now()
      const res = await api(`/models/${target}`, { timeout: 6000 })
      await res.arrayBuffer()
      times.push(performance.now() - t0)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    }
  } catch (e) {
    add('Network latency to the Gemini API', 'fail', `ping failed: ${errText(e)}`, 'Switch to the phone hotspot, then retry.')
    return
  }
  const sorted = [...times].sort((a, b) => a - b)
  const p50 = sorted[1]
  add('Network latency to the Gemini API', p50 > 800 ? 'warn' : 'ok', `p50 ${ms(p50)} (3 pings: ${times.map(ms).join(', ')})`, 'Above 800 ms the voice will feel laggy. Switch to the phone hotspot or a wired connection.')
}

async function mint(constraints, ttlMinutes) {
  const now = Date.now()
  const token = await new GoogleGenAI({ apiKey: key, httpOptions: { apiVersion } }).authTokens.create({
    config: { uses: 1, expireTime: new Date(now + ttlMinutes * 60_000).toISOString(), newSessionExpireTime: new Date(now + 60_000).toISOString(), ...(constraints ? { liveConnectConstraints: constraints } : {}), httpOptions: { apiVersion } },
  })
  if (!token.name) throw new Error('token service returned no token')
  return token.name
}

// One attempt = { ok, detail, slow }. A transient close from the service happens now and then, so each smoke test gets one retry.
async function liveAttempt() {
  const model = requiredModels().find((m) => m.role === 'live')?.id ?? 'gemini-3.8-live'
  const t0 = Date.now()
  let session
  try {
    const tok = await mint(null, 30)
    let firstAudio = 0
    let bytes = 0
    let finish
    const done = new Promise((r) => (finish = r))
    session = await new GoogleGenAI({ apiKey: tok, httpOptions: { apiVersion } }).live.connect({
      model,
      config: { responseModalities: [Modality.AUDIO] },
      callbacks: {
        onmessage: (m) => {
          for (const p of m.serverContent?.modelTurn?.parts ?? []) {
            if (p.inlineData?.data) {
              if (!firstAudio) firstAudio = Date.now()
              bytes += p.inlineData.data.length * 0.75
            }
          }
          if (m.serverContent?.turnComplete) finish()
        },
        onerror: (e) => finish(String(e?.message ?? e)),
        onclose: (e) => finish(`closed by the service (code ${e?.code ?? '?'}${e?.reason ? `: ${scrub(e.reason)}` : ''})`),
      },
    })
    const connectMs = Date.now() - t0
    session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: 'Say the single word: ready.' }] }], turnComplete: true })
    const sent = Date.now()
    const outcome = await Promise.race([done, sleep(15_000).then(() => 'no audio within 15 s')])
    if (!firstAudio) return { ok: false, detail: `connected in ${ms(connectMs)} but no audio came back (${scrub(outcome ?? 'turn ended without audio')})` }
    const first = firstAudio - sent
    return { ok: true, slow: first > 5000, detail: `${model}: ephemeral token, connected in ${ms(connectMs)}, audio back ${ms(first)} after the text turn (${Math.round(bytes / 1024)} KB)` }
  } catch (e) {
    return { ok: false, detail: errText(e) }
  } finally {
    try {
      session?.close()
    } catch {
      // already closed
    }
  }
}

async function wakeAttempt() {
  const model = requiredModels().find((m) => m.role === 'transcribe')?.id ?? 'gemini-3.5-transcribe-live'
  const t0 = Date.now()
  let session
  try {
    const tok = await mint({ model, config: { responseModalities: [Modality.TEXT], inputAudioTranscription: {} } }, 10)
    let finish
    const opened = new Promise((r) => (finish = r))
    session = await new GoogleGenAI({ apiKey: tok, httpOptions: { apiVersion } }).live.connect({
      model,
      config: { responseModalities: [Modality.TEXT], inputAudioTranscription: { languageCodes: ['en-GB', 'en-US'] } },
      callbacks: { onmessage: () => undefined, onopen: () => finish('open'), onerror: (e) => finish(`error: ${e?.message ?? e}`), onclose: () => finish('closed') },
    })
    const state = await Promise.race([opened, sleep(8000).then(() => 'timeout')])
    return state === 'open' ? { ok: true, detail: `${model}: constrained token minted and stream opened in ${ms(Date.now() - t0)}` } : { ok: false, detail: `stream did not open (${scrub(state)})` }
  } catch (e) {
    return { ok: false, detail: errText(e) }
  } finally {
    try {
      session?.close()
    } catch {
      // already closed
    }
  }
}

async function withRetry(name, attempt, failFix, slowFix) {
  let r = await attempt()
  if (r.ok) return add(name, r.slow ? 'warn' : 'ok', r.detail, slowFix)
  const first = r.detail
  await sleep(1000)
  r = await attempt()
  if (r.ok) return add(name, 'warn', `${r.detail}. The first attempt failed (${first}); it passed on retry, so the connection is flaky.`, 'Run preflight once more. If it fails again, switch to the phone hotspot.')
  add(name, 'fail', r.detail, failFix)
}

const liveSmoke = () =>
  withRetry('Live voice smoke test', liveAttempt, 'Live is not answering. Check the key/quota and the network, then retry. `ALONGSIDE_MOCK=1` shows the flow with canned data (say so on stage).', 'Audio took over 5 s to start; the network or the service is slow right now.')
const wakeTokenCheck = () =>
  withRetry('Wake-word token + stream', wakeAttempt, 'The wake word will not work. The hotkey (Cmd+Alt+Space) and the button still do; check the key and the network.', '')

async function stageCheck() {
  try {
    const res = await fetch(`http://127.0.0.1:${stagePort}/`, { signal: AbortSignal.timeout(2500) })
    add(`Practice desktop on port ${stagePort}`, res.ok ? 'ok' : 'fail', res.ok ? `http://127.0.0.1:${stagePort}/ answers 200` : `HTTP ${res.status}`, 'Run: npm run stage')
  } catch {
    add(`Practice desktop on port ${stagePort}`, 'fail', `nothing is listening on 127.0.0.1:${stagePort}`, 'Run: npm run stage  (npm run demo starts it for you).')
  }
}

async function runningAppCheck() {
  try {
    const res = await fetch(`http://127.0.0.1:${debugPort}/health`, { signal: AbortSignal.timeout(1000) })
    if (res.ok) add('Alongside already running', 'info', `an instance answers on 127.0.0.1:${debugPort}; a second launch would be refused or fight it for the hotkeys`)
  } catch {
    // not running: expected
  }
}

// ---------- probe results ----------
function probeChecks(p) {
  const launcher = p.bundleId || p.termProgram || 'unknown'
  add('Launcher (responsible app)', 'info', `${launcher}. macOS gives Microphone + Screen Recording to THIS app. Run preflight and the demo from this same terminal window, not from a different app.`)
  if (p.error && !p.grab) {
    for (const name of ['Screen Recording permission', 'Real screen grab', 'Microphone permission', 'Global hotkeys'])
      add(name, 'fail', `not checked: ${p.error}`, 'Retry. If it keeps failing: run npm install, then re-run preflight with no other Electron app running.')
    return
  }
  const fixScreen = 'System Settings > Privacy & Security > Screen & System Audio Recording: switch on the app named above (or node_modules/electron/dist/Electron.app), then FULLY QUIT that app (the terminal too) and reopen it. Never launch with `open -n -a`.'
  if (p.platform === 'darwin') {
    const s = p.screenStatus
    add('Screen Recording permission', s === 'granted' ? 'ok' : s === 'not-determined' ? 'warn' : 'fail', `status: ${s}`, s === 'not-determined' ? `macOS has not asked yet. Launch the app once and click Allow, then fully quit and relaunch. ${fixScreen}` : fixScreen)
    const m = p.micStatus
    add('Microphone permission', m === 'granted' ? 'ok' : m === 'not-determined' ? 'warn' : 'fail', `status: ${m}`, m === 'not-determined' ? 'macOS asks when the app first listens: click Allow, then fully quit and relaunch. The hotkey works without a microphone.' : 'System Settings > Privacy & Security > Microphone: switch on the app named above, then fully quit and reopen it. The hotkey path needs no microphone.')
    add('Accessibility (do-it-for-me only)', 'info', p.accessibilityTrusted ? 'trusted' : 'not trusted; only needed if "do it for me" is ever enabled, which it is not by default')
  }
  const attempts = p.grab ?? []
  const good = attempts.find((a) => !a.error)
  if (good && good.stdLuma >= 3) add('Real screen grab (desktopCapturer)', 'ok', `${good.width}x${good.height} on attempt ${good.attempt} of 3 in ${ms(good.ms)} (contrast ${good.stdLuma}, not blank)`)
  else if (good) add('Real screen grab (desktopCapturer)', 'fail', `grabbed ${good.width}x${good.height} but the image is blank (contrast ${good.stdLuma}); the screen may be asleep or capture is blocked`, `Wake the display and retry. ${fixScreen}`)
  else add('Real screen grab (desktopCapturer)', 'fail', `3 attempts failed: ${attempts.map((a) => a.error).join(' | ') || 'no result'}`, `Usually a missing Screen Recording permission. ${fixScreen}`)
  const h = p.hotkeys
  if (!h) add('Global hotkeys', 'fail', 'not checked', 'Retry.')
  else if (!h.start.length || !h.stop.length) add('Global hotkeys', 'fail', `start: ${h.start.join(', ') || 'NONE'} | stop: ${h.stop.join(', ') || 'NONE'} | taken: ${h.failed.join(', ') || '-'}`, 'Quit the app that owns those shortcuts (Raycast, Alfred, Zoom, a screen recorder) and retry.')
  else add('Global hotkeys', h.failed.length ? 'warn' : 'ok', `start: ${h.start.join(', ')} | stop: ${h.stop.join(', ')}${h.failed.length ? ` | taken by another app: ${h.failed.join(', ')}` : ''}`, 'Some combos are taken; the others work. Write down which start combo you will use. Press it once in the room: macOS can still claim Cmd+Alt+Space for Finder search.')
}

// ---------- agency (do-it-for-me) ----------
// Leftover headless Chrome processes (from tests or scripts) can answer `open https://...` and swallow the link: the page
// opens in a browser nobody can see while open_for_me still reports success.
function headlessChromeCount() {
  const r = spawnSync('/usr/bin/pgrep', ['-fl', 'Google Chrome'], { encoding: 'utf8', timeout: 3000 })
  return String(r.stdout || '').split('\n').filter((l) => /--headless/.test(l)).length
}
function agencyChecks(p) {
  const n = process.platform === 'darwin' ? headlessChromeCount() : 0
  if (n > 0) add('Headless Chrome processes', 'warn', `${n} headless Chrome process${n === 1 ? '' : 'es'} found`, `${n} headless Chrome processes may swallow links opened for you; quit them or use Safari.`)
  let agency = 'ask_per_task (default)'
  const dirs = [process.env.ALONGSIDE_USERDATA, join(homedir(), 'Library', 'Application Support', 'alongside'), join(homedir(), 'Library', 'Application Support', 'Alongside')].filter(Boolean)
  for (const d of dirs) {
    const f = join(d, 'settings.json')
    if (!existsSync(f)) continue
    try {
      const j = JSON.parse(readFileSync(f, 'utf8'))
      const chosen = j.agencyChosen === true
      let level = typeof j.agency === 'string' ? j.agency : 'ask_per_task'
      // Mirrors the app's load(): a profile that never chose 'off' / 'ask_each' runs as ask_per_task.
      if (!chosen && (level === 'off' || level === 'ask_each')) level = 'ask_per_task'
      agency = `${level}${chosen ? ' (chosen)' : ' (default)'}`
    } catch {
      // unreadable settings: report the default
    }
    break
  }
  const loop = process.env.ALONGSIDE_AGENCY_LOOP !== '0' ? 'on' : 'OFF (ALONGSIDE_AGENCY_LOOP=0)'
  const ax = p && p.platform === 'darwin' ? (p.accessibilityTrusted ? 'trusted' : 'NOT trusted (it can only point, not click)') : 'n/a'
  add('Agency (do-it-for-me)', ax.startsWith('NOT') || loop.startsWith('OFF') ? 'warn' : 'info', `setting: ${agency} | multi-step loop: ${loop} | Accessibility: ${ax}`, 'To let it click and type: System Settings > Privacy & Security > Accessibility: switch on the app named above, then fully quit and reopen it. Unset ALONGSIDE_AGENCY_LOOP to turn the loop on.')
}

// ---------- run ----------
localChecks()
const SKIPPED = ['Network latency to the Gemini API', 'Live voice smoke test', 'Wake-word token + stream']
if (key && (await modelsCheck())) {
  await latencyCheck()
  await Promise.all([liveSmoke(), wakeTokenCheck(), stageCheck(), runningAppCheck()])
} else {
  if (!key) add('Gemini API key accepted (models.list)', 'fail', 'skipped: no API key', 'Fix the .env line above first.')
  for (const name of SKIPPED) add(name, 'fail', key ? 'skipped: the key or the network failed above' : 'skipped: no API key', 'Fix the row above first, then re-run.')
  await Promise.all([stageCheck(), runningAppCheck()])
}
const probeResult = await probeP
probeChecks(probeResult)
agencyChecks(probeResult)

// ---------- report ----------
const ORDER = ['.env with GEMINI_API_KEY', '.env is git-ignored', 'Gemini API key accepted (models.list)', 'Models the app uses are visible', 'Network latency to the Gemini API', 'Live voice smoke test', 'Wake-word token + stream']
const rank = (r) => {
  const i = ORDER.indexOf(r.name)
  return i === -1 ? ORDER.length : i
}
rows.sort((a, b) => rank(a) - rank(b))
const width = Math.max(...rows.map((r) => r.name.length))
console.log(`\nAlongside preflight  (${new Date().toLocaleTimeString()})\n`)
for (const r of rows) console.log(`${TAGS[r.status]} ${r.name.padEnd(width)}  ${r.detail}`)
const bad = rows.filter((r) => r.status === 'fail' || r.status === 'warn')
if (bad.length) {
  console.log('\nWhat to do:')
  for (const r of bad) console.log(`  ${r.status === 'fail' ? paint('31;1', '[FAIL]') : paint('33;1', '[warn]')} ${r.name}: ${r.fix}`)
}
const count = (s) => rows.filter((r) => r.status === s).length
const secs = ((Date.now() - started) / 1000).toFixed(1)
console.log(`\n${count('ok')} ok, ${count('warn')} warnings, ${count('fail')} failures, ${count('info')} info  (${secs} s)`)
console.log(count('fail') ? paint('31;1', 'NOT READY: fix the FAIL rows above, then run: npm run preflight') : count('warn') ? paint('33;1', 'READY with warnings: read them once, then go.') : paint('32;1', 'READY.'))
process.exit(count('fail') ? 1 : 0)
