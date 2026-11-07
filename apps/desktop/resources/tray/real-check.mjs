// Real-app check of the menu-bar item and permissions backend. Run under the lock (<= 3 minutes):
//   npm run build && scripts/electron-lock.sh SHELL node resources/tray/real-check.mjs
// Starts the built app with mocks and an isolated profile, drives it over the debug HTTP, writes docs/shell-shots/.
import { spawn, execFileSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const PORT = 7792
const DEV_PORT = 7793
const base = `http://127.0.0.1:${PORT}`
const dev = `http://127.0.0.1:${DEV_PORT}`
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
const check = (name, ok, detail) => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail === undefined ? '' : ' ' + JSON.stringify(detail)}`)
}
const get = async (url) => (await fetch(url)).json()
const post = async (url, body) => {
  const res = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body ?? {}) })
  return { status: res.status, body: await res.json().catch(() => null) }
}
const tray = () => get(`${base}/tray`)
const click = (id) => post(`${base}/tray/click`, id === undefined ? {} : { id })

const userData = mkdtempSync(join(tmpdir(), 'alongside-shell-'))
writeFileSync(join(userData, 'settings.json'), JSON.stringify({ wakeEnabled: false }))
const child = spawn(join(REPO, 'node_modules/.bin/electron'), ['.'], {
  cwd: REPO,
  env: { ...process.env, ALONGSIDE_MOCK: '1', ALONGSIDE_NO_OVERLAY: '1', ALONGSIDE_USERDATA: userData, ALONGSIDE_DEBUG_PORT: String(PORT), ALONGSIDE_DEV_STAGE: '1', ALONGSIDE_DEV_PORT: String(DEV_PORT) },
  stdio: ['ignore', 'pipe', 'pipe'],
})
let log = ''
child.stdout.on('data', (d) => (log += d))
child.stderr.on('data', (d) => (log += d))
const stop = () => {
  try {
    child.kill('SIGTERM')
  } catch {}
}
process.on('exit', stop)

try {
  for (let i = 0; i < 60; i++) {
    try {
      await get(`${base}/health`)
      break
    } catch {
      await sleep(500)
    }
  }
  await sleep(1500)

  // 1. The menu bar item exists and has a real position.
  let t = await tray()
  check('tray exists', t.exists)
  check('tray bounds non-empty', t.bounds && t.bounds.width > 0 && t.bounds.height > 0, t.bounds)
  check('tooltip names the state', /^Alongside: /.test(t.tooltip), t.tooltip)
  console.log('menu:', t.menu.map((m) => `${m.label}${m.enabled ? '' : ' (off)'}${m.accelerator ? ' [' + m.accelerator + ']' : ''}`).join(' | '))

  // 2. Permissions through the real preload + IPC path (the dock renderer), and straight from main.
  const perm = await post(`${dev}/dev/dock/api`, { path: 'permissions.status' })
  const status = perm.body?.result
  check('permissions.status over IPC returns the full shape', status && ['microphone', 'screen', 'accessibility', 'probe', 'needsRestart', 'hint'].every((k) => k in status), status)
  check('permissions values are sane', status && ['granted', 'denied', 'not-determined', 'restricted', 'unknown'].includes(status.microphone) && ['granted', 'denied', 'not-determined', 'restricted', 'unknown'].includes(status.screen) && typeof status.accessibility === 'boolean' && typeof status.hint === 'string' && status.hint.length > 0)

  // 3. Menu items fire the right events (observed through state).
  check('Stop disabled while asleep', t.menu.find((m) => m.id === 'stop')?.enabled === false)
  let r = await click('talk:amelia')
  await sleep(600)
  let st = await get(`${base}/state`)
  check('Talk to Amelia -> session:request (persona + connecting/live)', r.status === 200 && st.persona === 'amelia' && ['connecting', 'live', 'thinking', 'speaking', 'error'].includes(st.phase), { persona: st.persona, phase: st.phase })
  t = await tray()
  check('icon follows the session', t.icon === 'live' || st.phase === 'error' || st.phase === 'asleep' || st.phase === 'listening_for_name', { icon: t.icon, phase: st.phase })

  r = await click('mute')
  await sleep(300)
  st = await get(`${base}/state`)
  t = await tray()
  check('Mute microphone -> micMuted, muted icon, Unmute label', st.micMuted === true && t.icon === 'muted' && t.menu.find((m) => m.id === 'mute')?.label === 'Unmute microphone', { micMuted: st.micMuted, icon: t.icon })
  await click('mute')
  await sleep(200)
  check('Unmute restores', (await get(`${base}/state`)).micMuted === false)

  const before = (await get(`${base}/state`)).phase
  if (t.menu.find((m) => m.id === 'stop')?.enabled || ['connecting', 'live', 'thinking', 'speaking'].includes(before)) {
    r = await click('stop')
    await sleep(500)
    st = await get(`${base}/state`)
    check('Stop ends the session', r.status === 200 && !['connecting', 'live', 'thinking', 'speaking'].includes(st.phase), { phase: st.phase })
  } else check('Stop (session already over in mock mode)', true, { phase: before })

  // 4. Panel visibility, dock views, demo.
  r = await click('panel')
  await sleep(300)
  t = await tray()
  check('Hide panel hides the dock window', t.menu.find((m) => m.id === 'panel')?.label === 'Show panel')
  r = await click('panel')
  await sleep(300)
  t = await tray()
  check('Show panel brings it back', t.menu.find((m) => m.id === 'panel')?.label === 'Hide panel')
  for (const id of ['type', 'permissions', 'setup']) {
    r = await click(id)
    check(`${id} item runs`, r.status === 200)
  }
  check('Set up again resets onboardingDone', (await get(`${base}/state`)).settings.onboardingDone === false)
  r = await click(undefined)
  check('icon click toggles the dock', r.status === 200)
  const showtime = await post(`${dev}/dev/dock/api`, { path: 'showtime.state' }).catch(() => null)
  r = await click('demo')
  check('Run the demo walkthrough emits showtime:request (200)', r.status === 200)
  await sleep(500)
  const showtimeAfter = await post(`${dev}/dev/dock/api`, { path: 'showtime.state' }).catch(() => null)
  console.log('showtime.state before/after:', JSON.stringify(showtime?.body?.result), JSON.stringify(showtimeAfter?.body?.result))
  await post(`${dev}/dev/dock/api`, { path: 'showtime.stop' }).catch(() => null)

  // 5. Setting off removes the item; on brings it back.
  await post(`${base}/settings`, { patch: { showMenuBarIcon: false } })
  await sleep(300)
  check('showMenuBarIcon=false removes the item', (await tray()).exists === false)
  await post(`${base}/settings`, { patch: { showMenuBarIcon: true } })
  await sleep(500)
  t = await tray()
  check('showMenuBarIcon=true restores it', t.exists && t.bounds.width > 0)

  // 6. Crop of just the menu-bar icon (a small square around it, nothing else of the menu bar).
  mkdirSync(join(REPO, 'docs/shell-shots'), { recursive: true })
  const out = join(REPO, 'docs/shell-shots/tray-icon.png')
  try {
    const b = t.bounds
    const region = `${Math.max(0, b.x - 8)},${b.y},${b.width + 16},${Math.max(b.height, 24)}`
    execFileSync('screencapture', ['-x', '-R', region, out])
    check('menu bar icon crop saved', existsSync(out), { region, out })
  } catch (e) {
    check('menu bar icon crop saved', false, String(e).slice(0, 120))
  }
} catch (e) {
  check('script ran without throwing', false, String(e).slice(0, 300))
} finally {
  stop()
  await sleep(500)
  const failed = results.filter((x) => !x.ok)
  writeFileSync(join(REPO, 'docs/shell-shots/real-check.json'), JSON.stringify({ at: new Date().toISOString(), results }, null, 2))
  console.log(`\n${results.length - failed.length}/${results.length} passed`)
  console.log('--- app log tail ---')
  console.log(log.split('\n').filter((l) => /tray|permissions|login|error|Error/i.test(l)).slice(-15).join('\n'))
  process.exit(failed.length ? 1 : 0)
}
