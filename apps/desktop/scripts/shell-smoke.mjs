#!/usr/bin/env node
// Smoke test of the running Knack shell through the debug server (the app must have been started with ALONGSIDE_DEBUG=1 and ALONGSIDE_DEBUG_PORT=<port>; that is a
// human step: this script never launches anything). It drives the corner pill through the shell machine with the dev hook POST /hud/activity, reads GET /state (the
// main window's visibility and bounds) and GET /hud, and checks the rules of docs/knack-ux/08-window-states.md that can be seen from outside: the pill appears bottom-right,
// a card never restores the window, a finished run does not pop the window back, kill wins. It makes no real click, keystroke or capture; the only window it can move is
// Knack's own (the minimise happens to it when a real-screen run starts with it focused).
//   node scripts/shell-smoke.mjs --port 7777 [--real-screen]
const argv = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}
const port = Number(opt('port', process.env.ALONGSIDE_DEBUG_PORT || 7777))
const realScreen = argv.includes('--real-screen')
// --hidden: the app was started with KNACK_HIDDEN=1 (scripts/knack-e2e.mjs), so its windows exist but are never shown: whether the corner window is on screen is not asked.
const hiddenRun = argv.includes('--hidden')
const base = `http://127.0.0.1:${port}`
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const get = async (p) => (await fetch(`${base}${p}`)).json()
const post = async (p, body) => {
  const res = await fetch(`${base}${p}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body ?? {}) })
  return { status: res.status, body: await res.json().catch(() => null) }
}
let failed = 0
const check = (name, ok, detail) => {
  if (!ok) failed += 1
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : ` ${JSON.stringify(detail)}`}`)
}

try {
  const health = await get('/health')
  check('the debug server answers', health.ok === true, health)
  const s0 = await get('/state')
  check('GET /state reports the main window (visibility and bounds)', s0.knack?.window?.exists === true && s0.knack?.window?.bounds !== undefined, s0.knack?.window)
  const windowBefore = s0.knack.window

  // The old side panel's own eight-step set-up never runs in the app: on a fresh profile it is already done, and no patch can bring it back.
  const pinned = await post('/settings', { patch: { onboardingDone: false } })
  check('a fresh profile never starts the old panel set-up, and nothing can switch it back on (Knack has one onboarding, the first run)', pinned.body?.onboardingDone === true, pinned.body?.onboardingDone)

  let r = await post('/hud/activity', { phase: 'working', label: 'Filling in calculator B', step: 3, of: 8, realScreen })
  check('a run starts: the pill shows the words and n of m', r.body?.hud?.activity?.phase === 'working' && r.body.hud.activity.label === 'Filling in calculator B' && r.body.hud.activity.step === 3, r.body?.hud?.activity)
  await sleep(700)
  if (!hiddenRun) {
    const visible = await get('/hud/visible').catch(() => null)
    check('the corner window is on screen', visible?.visible === true, visible)
  }

  r = await post('/shell/event', { event: { type: 'decision_needed', class: 'approval' } })
  const s1 = await get('/state')
  const withCard = await get('/hud')
  check('a blocked run raises one card', withCard.approval !== null && withCard.corner === true, withCard.approval)
  check('and the main window is not restored by it', s1.knack.window.visible === windowBefore.visible && s1.knack.window.minimised === windowBefore.minimised, { before: windowBefore, after: s1.knack.window })

  r = await post('/hud/activity', { phase: 'done' })
  check('a finished run turns the pill into a check', r.body?.hud?.activity?.phase === 'done', r.body?.hud?.activity)
  await sleep(3200)
  check('the check fades by itself', (await get('/hud')).activity === null)
  const s2 = await get('/state')
  check('the window does not pop back when the run finishes', s2.knack.window.minimised === s1.knack.window.minimised && s2.knack.window.visible === s1.knack.window.visible, { s1: s1.knack.window, s2: s2.knack.window })

  r = await post('/hud/activity', { phase: 'working', label: 'Reading', realScreen: false })
  r = await post('/hud/activity', { phase: 'error' })
  check('a failed run turns the pill to the error state and holds it', r.body?.hud?.activity?.phase === 'error', r.body?.hud?.activity)
  await post('/hud/activity', { phase: 'idle' })

  r = await post('/hud/activity', { phase: 'working', label: 'Working on it', realScreen: false })
  r = await post('/hud/activity', { phase: 'stopped' })
  await sleep(300)
  const stopped = await get('/hud')
  check('kill wins: the Stopped card replaces the pill', stopped.kill.killed === true && stopped.activity === null, { kill: stopped.kill, activity: stopped.activity })
  await post('/kill/clear', {})
  await post('/hud/activity', { phase: 'idle' })
  await sleep(300)
  check('Resume leaves it', (await get('/hud')).kill.killed === false)
} catch (err) {
  failed += 1
  console.log(`FAIL the smoke test could not run: ${err instanceof Error ? err.message : String(err)} (is the app running with ALONGSIDE_DEBUG=1 on port ${port}?)`)
}
process.exit(failed === 0 ? 0 : 1)
