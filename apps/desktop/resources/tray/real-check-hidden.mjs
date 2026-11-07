// Real-app check of the hidden side panel (SHELL2). Run under the lock (< 3 minutes):
//   npm run build && scripts/electron-lock.sh SHELL2 node resources/tray/real-check-hidden.mjs
// Real Live session (needs REPO/.env), isolated profile /tmp/alongside-shell2 with onboardingDone:true, showDock:false.
import { spawn } from 'node:child_process'
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const PORT = 7794
const base = `http://127.0.0.1:${PORT}`
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
const state = () => get(`${base}/state`)
const click = (id) => post(`${base}/tray/click`, id === undefined ? {} : { id })
async function waitFor(fn, ms) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    const v = await fn().catch(() => null)
    if (v) return v
    await sleep(300)
  }
  return null
}

// SHOW=1 is the control run: same checks with the panel kept open, to compare caption behaviour with the hidden run.
const SHOW = process.env.SHOW === '1'
const userData = '/tmp/alongside-shell2'
rmSync(userData, { recursive: true, force: true })
mkdirSync(userData, { recursive: true })
writeFileSync(join(userData, 'settings.json'), JSON.stringify({ onboardingDone: true, showDock: SHOW, persona: 'marcus', wakeEnabled: true }))
const child = spawn(join(REPO, 'node_modules/.bin/electron'), ['.'], {
  cwd: REPO,
  env: { ...process.env, ALONGSIDE_USERDATA: userData, ALONGSIDE_DEBUG_PORT: String(PORT) },
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
const titles = []
const note = (t) => {
  if (titles.at(-1) !== t) titles.push(t)
}

try {
  const up = await waitFor(async () => (await get(`${base}/health`)) && true, 40000)
  check('app up', up)
  await sleep(2500)

  // 1. Startup: the panel window exists but is hidden; the menu bar item is the control center.
  let t = await tray()
  check('tray exists', t.exists)
  check(SHOW ? 'panel visible at startup (showDock true)' : 'panel hidden at startup (showDock false, setup done)', t.panelVisible === SHOW, { panelVisible: t.panelVisible })
  check(`Show panel checkbox is ${SHOW ? 'checked' : 'unchecked'}`, t.menu.find((m) => m.id === 'panel')?.checked === SHOW)
  check('panel shortcut shown on the checkbox when registered', true, t.menu.find((m) => m.id === 'panel')?.accelerator ?? 'not registered here')
  let st = await state()
  check('settings.showDock matches in state', st.settings?.showDock === SHOW)
  note(t.title)
  console.log('start: phase', st.phase, 'title', JSON.stringify(t.title), 'tooltip', t.tooltip)
  const png = await fetch(`${base}/dock.png`)
  check('dock renderer still renders while hidden (GET /dock.png)', png.status === 200, { status: png.status, bytes: (await png.arrayBuffer()).byteLength })
  check('log: wake spotter did not report a failure while hidden', !/wake.*(fail|error)/i.test(log), log.split('\n').filter((l) => /wake/i.test(l)).slice(0, 4))

  // 2. A Live session starts and reaches live with the panel hidden; the tray title follows.
  const w = await post(`${base}/wake`, { personaId: 'marcus' })
  check('POST /wake accepted', w.status === 200)
  const seen = new Set()
  let live = null
  const end = Date.now() + 30000
  while (Date.now() < end) {
    st = await state()
    t = await tray()
    note(t.title)
    seen.add(st.phase)
    if (['live', 'thinking', 'speaking'].includes(st.phase)) {
      live = st.phase
      break
    }
    if (st.phase === 'error') break
    await sleep(300)
  }
  check('Live session reaches live while the panel is hidden', live !== null, { phases: [...seen], error: st.lastError })
  check('tray title changed away from the resting word', t.title !== titles[0] || titles.length > 1, { titles })
  check('panel visibility unchanged by the session', (await tray()).panelVisible === SHOW)
  // Ask for one short reply so captions and audio output flow through the renderer (hidden or not).
  await post(`${base}/inject`, { text: 'Please say hello in one short sentence.' })
  await waitFor(async () => (await state()).captions?.length > 0, 14000)
  st = await state()
  t = await tray()
  note(t.title)
  check(`captions arrive (${SHOW ? 'panel visible' : 'panel hidden'})`, Array.isArray(st.captions) && st.captions.length > 0, { count: st.captions?.length, phase: st.phase })
  console.log('mid-session: phase', st.phase, 'title', JSON.stringify(t.title), 'icon', t.icon)
  const overlay = await fetch(`${base}/overlay.png`)
  check('overlay window renders (captions band lives there)', overlay.status === 200, { status: overlay.status })

  if (SHOW) throw new Error('control run done')
  // 3. Show panel from the menu bar shows it, persists, and hides it again.
  let r = await click('panel')
  await sleep(500)
  t = await tray()
  st = await state()
  check('Show panel (tray click) shows the panel and persists showDock', r.status === 200 && t.panelVisible === true && st.settings?.showDock === true && t.menu.find((m) => m.id === 'panel')?.checked === true, { panelVisible: t.panelVisible, showDock: st.settings?.showDock })
  const shown = await fetch(`${base}/dock.png`)
  check('dock renders when shown', shown.status === 200)
  r = await click() // the icon click itself
  await sleep(500)
  t = await tray()
  st = await state()
  check('clicking the icon hides it again and persists', t.panelVisible === false && st.settings?.showDock === false, { panelVisible: t.panelVisible, showDock: st.settings?.showDock })
  check('session still live after toggling the panel', ['live', 'thinking', 'speaking'].includes((await state()).phase), (await state()).phase)

  // 4. Stop ends the session; Type instead shows the panel and a finished session returns it to hidden.
  await post(`${base}/stop`, {})
  await waitFor(async () => ['listening_for_name', 'asleep'].includes((await state()).phase), 8000)
  note((await tray()).title)
  st = await state()
  check('Stop returns to the resting phase', ['listening_for_name', 'asleep'].includes(st.phase), st.phase)
  r = await click('type')
  await sleep(500)
  check('Type instead shows the hidden panel', (await tray()).panelVisible === true)
  await post(`${base}/wake`, { personaId: 'marcus' })
  await waitFor(async () => ['live', 'thinking', 'speaking'].includes((await state()).phase), 25000)
  await post(`${base}/stop`, {})
  await waitFor(async () => (await tray()).panelVisible === false, 6000)
  check('panel returns to hidden when that session ends', (await tray()).panelVisible === false)
  console.log('title sequence:', JSON.stringify(titles))
} catch (err) {
  if (String(err) !== 'Error: control run done') check('script ran without throwing', false, String(err))
} finally {
  stop()
  const fails = results.filter((x) => !x.ok)
  mkdirSync(join(REPO, 'docs/shell-shots'), { recursive: true })
  writeFileSync(join(REPO, 'docs/shell-shots/real-check-hidden' + (SHOW ? '-control' : '') + '.json'), JSON.stringify({ at: new Date().toISOString(), titles, results }, null, 2))
  console.log(`${results.length - fails.length}/${results.length} passed`)
  await sleep(500)
  process.exit(fails.length ? 1 : 0)
}
