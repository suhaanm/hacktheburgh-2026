#!/usr/bin/env node
// A teammate working a case, for the demo video: Playwright drives a real Chromium that has the built capture extension, at a human pace,
// on the sandbox calculators, with NO operating-system click or keystroke and NO screen capture or frame analysis. Every event is a
// trusted event inside the browser (Chrome DevTools Protocol), the way scripts/rehearse-coach.mjs plays the worker. The Knack app (which
// the owner has open) does the rest: it reads the coach decision from the engine and draws the ring on the button.
//
//   node scripts/demo-worker.mjs [--scene coach|stuck|both] [--pace slow|normal|fast|<number>] [--headless]
//        [--engine URL] [--private] [--desktop-ext URL] [--sites URL] [--person ID] [--no-study-mode] [--no-reset]
//        [--position X,Y] [--size WxH] [--cursor|--no-cursor] [--extension DIR] [--gap SECONDS] [--stuck-seconds N]
//        [--lock-data-dir DIR] [--lock-wait SECONDS] [--json] [--cue-sheet FILE]
//
// What it plays (default: both):
//   coach  Case CASE-1005 on calculator A (one adult, 36, earns 250 a month, rent 480, one bedroom, savings 12,000): four question pages,
//          the result, then the worker goes to the case note tab WITHOUT opening "Check cliff edges" and comes back. The coach (at the first
//          help level) rings that button. The worker reads the ring, presses the button, and saves the case note as a draft.
//   stuck  A second case (CASE-1006): the household goes in quickly, the result appears, and then the worker stalls on it for about a minute
//          (small scrolls, hovering, looking away and back, no progress). Cue sees the stall and shows its one question or cue. The worker
//          follows it, and saves the note.
//
// Where it runs: the shared sandbox sites (7801 to 7803) while it holds the sandbox lock (a second runner waits or stops), against the engine
// given by --engine (default the live stack at 7700; the Knack app's own extension server is --desktop-ext, default 7720). --private starts a
// THROWAWAY engine (its own home and data directory, mock mode, a copy of the learners' synthetic data, AGENT_PORT=1 so a stop call can never
// reach the live agent) and no desktop app: the ring is then not drawn, but every engine decision is still checked (a rehearsal of the script).
//
// The coach reads its help level from the worker's history, and the demo person is already past the first level, so by default the script asks
// the engine's STUDY MODE for the first level on the cliff skill for the length of the run (POST /study/mode) and clears it at the end, even
// after a crash or Ctrl-C. That is a switch of the pre-registered study design, not a fake: say so in the voiceover ("coach set to full help
// for a first-week stand-in"). --no-study-mode leaves the coach as it is.
//
// What it writes: the worker's own capture events (hashed, no text, as always) into the engine, a draft case note in the sandbox, and nothing
// else. It never presses "Submit to claimant record", never calls /kill, never reads or writes data/ of the checkout, never prints a key.
// Output: one line per moment with a time since the start (the editor's cue sheet), then a summary. Exit code 0 when the script ran to the end
// and the engine decided to ring (coach scene) in time; 1 otherwise.
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { Procs, extensionDist, getJson, postJson, pythonOf, refuseLiveAgent, removeTree, repoRootFrom, sleep, startPrivateEngine, until } from '../../../scripts/lib/private-stack.mjs'

// ---------------------------------------------------------------------------------------------- arguments
const argv = process.argv.slice(2)
const flag = (name, dflt) => {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 ? (argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : true) : dflt
}
if (argv.includes('--help') || argv.includes('-h')) {
  const src = (await import('node:fs')).readFileSync(fileURLToPath(import.meta.url), 'utf8')
  console.log(src.split('\n').filter((l) => l.startsWith('//')).slice(0, 38).map((l) => l.replace(/^\/\/ ?/, '')).join('\n'))
  process.exit(0)
}
const strip = (u) => String(u).replace(/\/+$/, '')
const SCENE = String(flag('scene', 'both'))
const PACE_NAME = String(flag('pace', 'normal'))
const PACE = { slow: 1.7, normal: 1, fast: 0.35 }[PACE_NAME] ?? Number(PACE_NAME)
const HEADLESS = argv.includes('--headless')
const PRIVATE = argv.includes('--private')
const SITE = strip(flag('sites', 'http://127.0.0.1:7801'))
const SITE_PORT = Number(new URL(SITE).port || 7801)
const SITES = [SITE_PORT, SITE_PORT + 1, SITE_PORT + 2]
const DESKTOP_EXT = strip(flag('desktop-ext', 'http://127.0.0.1:7720'))
const PERSON_FLAG = flag('person', null)
const STUDY = !argv.includes('--no-study-mode')
const RESET = !argv.includes('--no-reset')
const CURSOR = argv.includes('--cursor') || (!argv.includes('--no-cursor') && !HEADLESS) // the visible teammate cursor: on when headed
const AS_JSON = argv.includes('--json')
const DEBUG = argv.includes('--debug')
const GAP_S = Number(flag('gap', 125)) // the engine's quiet period after the coach speaks is 120 s
const STUCK_S = Number(flag('stuck-seconds', 75)) // the longest the stall lasts; it ends as soon as Cue speaks (rehearsal: about 50 s)
const LOCK_WAIT_S = Number(flag('lock-wait', 60))
const [WX, WY] = String(flag('position', '60,60')).split(',').map(Number)
const [WW, WH] = String(flag('size', '1180x760')).split('x').map(Number)
const CUE_SHEET = flag('cue-sheet', null)
if (!['coach', 'stuck', 'both'].includes(SCENE)) fail('--scene must be coach, stuck or both')
if (!Number.isFinite(PACE) || PACE <= 0 || PACE > 5) fail('--pace must be slow, normal, fast or a number from 0.1 to 5')
if (PRIVATE && flag('engine', null)) fail('use either --private or --engine, not both')
function fail(m) {
  console.error(`demo-worker: ${m}`)
  process.exit(2)
}
refuseLiveAgent()

const repo = repoRootFrom(import.meta.url)
const procs = new Procs()
const wait = (ms) => sleep(Math.round(ms * PACE))
const jitter = (a, b) => a + Math.random() * (b - a)

// ---------------------------------------------------------------------------------------------- the cue sheet
const T0 = Date.now()
const sheet = []
const stamp = () => {
  const s = Math.round((Date.now() - T0) / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}
function log(kind, msg) {
  sheet.push({ at_s: +((Date.now() - T0) / 1000).toFixed(1), kind, msg })
  if (!AS_JSON) console.log(`[${stamp()}] ${kind.padEnd(8)} ${msg}`)
}

// ---------------------------------------------------------------------------------------------- state to clean up
let engine = null
let person = null
let priv = null
let context = null
let studyOn = false
let lockHeld = false
let resetSites = false
let userData = null
let cleaned = false
const out = { ok: false, scene: SCENE, pace: PACE_NAME, mode: PRIVATE ? 'private engine' : 'named engine', checks: {} }
const check = (name, pass, detail) => {
  out.checks[name] = { pass: Boolean(pass), ...(detail === undefined ? {} : { detail }) }
  log(pass ? 'ok' : 'WARN', `${name}${detail ? `: ${detail}` : ''}`)
  return Boolean(pass)
}

async function cleanup() {
  if (cleaned) return
  cleaned = true
  try {
    if (studyOn && engine) {
      const r = await postJson(`${engine}/study/mode/clear`, {}).catch(() => null)
      log('clean', `study mode ${r?.status === 200 ? 'cleared' : 'NOT cleared (POST /study/mode/clear by hand)'}`)
    }
    await context?.close().catch(() => undefined)
    if (resetSites) for (const p of SITES) await getJson(`http://127.0.0.1:${p}/__reset`, { method: 'POST' }, 4000).catch(() => undefined)
    const h = procs.children.get('sandbox-lock')
    if (h && procs.alive(h)) {
      h.stdin.end()
      await Promise.race([new Promise((r) => h.once('exit', r)), sleep(3000)])
    }
    await procs.stopAll()
  } finally {
    if (priv?.root) removeTree(priv.root)
    if (userData) removeTree(userData)
  }
}
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, async () => {
    log('stop', `${sig}: cleaning up`)
    await cleanup()
    process.exit(130)
  })
}

// ---------------------------------------------------------------------------------------------- the worker's hands (inside the browser only)
let pointer = { x: 120, y: 160 }
const CURSOR_JS = `(() => {
  if (window.__knackCursor) return; window.__knackCursor = true
  const mk = () => {
    const d = document.createElement('div'); d.setAttribute('data-knack-demo-cursor', '')
    d.style.cssText = 'position:fixed;left:0;top:0;width:20px;height:20px;margin:-3px 0 0 -3px;border-radius:50%;border:2px solid #1b1b1b;background:rgba(255,255,255,.88);box-shadow:0 1px 4px rgba(0,0,0,.35);pointer-events:none;z-index:2147483647;transform:translate(-100px,-100px)'
    document.documentElement.appendChild(d)
    addEventListener('mousemove', (e) => { d.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)' }, true)
    addEventListener('mousedown', () => { d.style.background = 'rgba(0,112,60,.55)' }, true)
    addEventListener('mouseup', () => { d.style.background = 'rgba(255,255,255,.88)' }, true)
  }
  if (document.documentElement) mk(); else addEventListener('DOMContentLoaded', mk)
})()`

async function glide(page, x, y, ms = 650) {
  const steps = Math.max(10, Math.round((ms * PACE) / 16))
  await page.mouse.move(x, y, { steps })
  pointer = { x, y }
}
async function centre(page, selector) {
  const box = await page.locator(selector).first().boundingBox()
  if (!box) throw new Error(`no visible element for ${selector}`)
  return { x: box.x + box.width * jitter(0.35, 0.65), y: box.y + box.height * jitter(0.35, 0.65) }
}
async function pointAt(page, selector, ms = 700) {
  await page.locator(selector).first().scrollIntoViewIfNeeded()
  const c = await centre(page, selector)
  await glide(page, c.x, c.y, ms)
  return c
}
async function press(page, selector) {
  const c = await pointAt(page, selector)
  await wait(jitter(220, 420))
  await page.mouse.click(c.x, c.y)
}
async function typeInto(page, selector, text) {
  await press(page, selector)
  await page.fill(selector, '')
  await page.type(selector, text, { delay: Math.max(25, Math.round(jitter(70, 130) * PACE)) })
  await wait(jitter(180, 380))
}
async function choose(page, selector, value) {
  await pointAt(page, selector, 500)
  await wait(jitter(260, 480))
  await page.selectOption(selector, value)
  await wait(jitter(160, 320))
}
async function idleMoves(page, ms) {
  // The look of a person who is reading and not deciding: a slow drift, a small scroll, a hover that goes nowhere.
  const end = Date.now() + ms * PACE
  while (Date.now() < end) {
    const dx = jitter(-90, 90)
    const dy = jitter(-60, 60)
    await glide(page, Math.max(20, Math.min(1100, pointer.x + dx)), Math.max(80, Math.min(640, pointer.y + dy)), 900)
    if (Math.random() < 0.4) await page.mouse.wheel(0, Math.random() < 0.5 ? 60 : -60)
    await sleep(jitter(700, 1500) * PACE)
  }
}

// ---------------------------------------------------------------------------------------------- the households (synthetic; the case cards)
const CASES = {
  coach: {
    ref: 'CASE-1005', // GovCalc 638, Quick Estimator 742.64, EntitledTo 638.24: they disagree; the note says Discrepancy (docs/drafts/DEMO_SCRIPT.md)
    answers: [
      [/how many adults/i, 'select', '1'], [/your age/i, 'fill', '36'], [/partner.s age/i, 'skip'], [/children/i, 'skip'],
      [/your monthly take-home/i, 'fill', '250'], [/partner.s monthly/i, 'skip'], [/health condition/i, 'select', 'no'], [/rent or own/i, 'select', 'rent'],
      [/monthly rent/i, 'fill', '480'], [/bedrooms/i, 'select', '1'], [/savings/i, 'fill', '12000'], [/childcare/i, 'skip'],
    ],
    note: 'The three calculators disagree on this case. Checked the savings against the capital tariff band before writing this.',
    reconciliation: 'discrepancy',
  },
  stuck: {
    ref: 'CASE-1006',
    answers: [
      [/how many adults/i, 'select', '1'], [/your age/i, 'fill', '41'], [/partner.s age/i, 'skip'], [/children/i, 'fill', '5'],
      [/your monthly take-home/i, 'fill', '900'], [/partner.s monthly/i, 'skip'], [/health condition/i, 'select', 'no'], [/rent or own/i, 'select', 'rent'],
      [/monthly rent/i, 'fill', '560'], [/bedrooms/i, 'select', '2'], [/savings/i, 'fill', '800'], [/childcare/i, 'fill', '120'],
    ],
    note: 'Entered once, read the result, checked the cliff edges, wrote the note.',
    reconciliation: 'agree',
  },
}

let tab1 = null
let tab2 = null
async function fillQuestionPage(page, answers) {
  const labels = await page.$$eval('main label', (ls) => ls.map((l) => ({ id: l.htmlFor, text: (l.textContent ?? '').trim() })))
  for (const l of labels) {
    const rule = answers.find(([re]) => re.test(l.text))
    if (!rule || rule[1] === 'skip') continue
    if (rule[1] === 'select') await choose(page, `#${l.id}`, rule[2])
    else await typeInto(page, `#${l.id}`, rule[2])
  }
}
async function enterHousehold(c) {
  await tab1.bringToFront()
  await tab1.goto(`${SITE}/`)
  await wait(900)
  await press(tab1, 'a:has-text("Start now")')
  for (let step = 1; step <= 4; step++) {
    await tab1.waitForSelector('main form')
    await fillQuestionPage(tab1, c.answers)
    await wait(jitter(300, 600))
    await press(tab1, 'main form button[type=submit]')
    await tab1.waitForLoadState('domcontentloaded')
    await wait(300)
  }
  await tab1.waitForSelector('#cliff-btn')
  log('worker', `${c.ref}: household entered on calculator A, result on screen`)
}
async function glanceAtNote(c) {
  // The "miss": the worker goes to the case note tab without having checked the cliff edges, then comes back. (Same moves as the rehearsal.)
  await tab2.goto(`${SITE}/casenote?case=${c.ref}`)
  await tab1.bringToFront()
  await wait(700)
  log('worker', 'MISS: switches to the case note without opening "Check cliff edges"')
  await tab2.bringToFront()
  await wait(1300)
  await tab1.bringToFront()
  log('worker', 'back on the result page, the cliff check still unopened')
  await wait(2200)
  await tab2.bringToFront() // a second look at the note: the engine reads two worker events after the skipped step as two signals
  await wait(800)
  await tab1.bringToFront()
}
async function followCue(c) {
  await tab1.bringToFront()
  await press(tab1, '#cliff-btn')
  await tab1.waitForSelector('#cliff-panel li', { timeout: 15000 }).catch(() => undefined)
  log('worker', 'presses "Check cliff edges"; the panel lists the nearby edges')
  await wait(2500)
}
async function fillNote(c) {
  await tab2.bringToFront()
  await tab2.goto(`${SITE}/casenote?case=${c.ref}`)
  await wait(500)
  await typeInto(tab2, '[name=result_a]', c.ref === 'CASE-1005' ? '638' : '812')
  await typeInto(tab2, '[name=result_b]', c.ref === 'CASE-1005' ? '742.64' : '812')
  await typeInto(tab2, '[name=result_c]', c.ref === 'CASE-1005' ? '638.24' : '812.50')
  await choose(tab2, '[name=reconciliation]', c.reconciliation)
  await typeInto(tab2, '[name=note_text]', c.note)
  log('worker', `${c.ref}: case note filled in`)
}
async function saveDraft(c) {
  await press(tab2, 'button[type=submit]') // "Save draft": a draft, never "Submit to claimant record"
  await tab2.waitForSelector('#note-status, #cn-state, [id*=status]')
  log('worker', `${c.ref}: case note saved as a DRAFT (the worker never presses Submit)`)
  await sleep(2600) // the extension's last batch (task_end) leaves
}
async function saveNote(c) {
  await fillNote(c)
  await saveDraft(c)
}

// ---------------------------------------------------------------------------------------------- what the engine decides (dry polls only)
const decisions = { coach: [], cue: [] }
// On a named engine the Knack app polls it for real every 2 s (that is what advances the coach's quiet-period gate and draws the ring), so this
// script only LOOKS (dry=1: it changes nothing and says "would ring now"). On the throwaway engine nothing else polls, so the script stands in for
// the app and polls for real, which is the faithful rehearsal of what the app will do.
const POLL = PRIVATE ? '' : '&dry=1'
let watching = true
async function watcher() {
  let lastC = ''
  let lastU = ''
  while (watching) {
    const c = await getJson(`${engine}/coach/next?person=${person}${POLL}`, {}, 4000).catch(() => null)
    const cd = c?.body?.data
    if (cd) {
      // A DRY poll never advances the quiet-period gate, so it answers "silent" with the reason code dry_run_would_act when the real poller (the Knack
      // app's, every 2 s) would be allowed to speak: that is the engine having decided. A live annotate (the app's own poll) shows up the same way.
      const codes = cd.reason_codes ?? []
      const would = codes.includes('dry_run_would_act')
      const acts = cd.action !== 'silent'
      const key = `${cd.action}|${would}|${cd.trigger ?? ''}|${codes.slice(0, 3).join(',')}`
      if (key !== lastC) {
        lastC = key
        decisions.coach.push({ at: Date.now(), action: acts ? cd.action : would ? 'annotate' : 'silent', would, level: cd.level, trigger: cd.trigger ?? null, codes: codes.slice(0, 4), zone: cd.target?.zone ?? null })
        if (acts || would) log('engine', `coach ${acts ? `decides ${cd.action}` : 'would ring now (a dry look)'}, level ${cd.level}, trigger ${cd.trigger}${cd.target ? `, zone ${cd.target.zone ?? '?'}` : ''}`)
        else if (DEBUG) log('debug', `coach silent: ${codes.slice(0, 4).join(', ')}${cd.gate?.consecutive !== undefined ? `, consecutive signals ${cd.gate.consecutive}` : ''}`)
      }
    }
    const u = await getJson(`${engine}/cue/next?person=${person}${POLL}`, {}, 4000).catch(() => null)
    const ud = u?.body?.data
    if (ud) {
      const ukey = `${ud.kind}|${(ud.why?.reasons ?? []).slice(0, 2).join(',')}`
      if (ukey !== lastU) {
        lastU = ukey
        decisions.cue.push({ at: Date.now(), kind: ud.kind, step: ud.step?.id ?? null })
        if (ud.kind !== 'none') log('engine', `cue decides ${ud.kind}${ud.step?.id ? ` (step ${ud.step.id})` : ''}`)
        else if (DEBUG) log('debug', `cue none: ${(ud.why?.reasons ?? []).join(', ')}; p_stuck ${ud.why?.p_stuck}, level ${ud.why?.level}, cooldown ${ud.cooldown_s}`)
      }
    }
    await sleep(1500)
  }
}

// ---------------------------------------------------------------------------------------------- the run
try {
  // ---- 1. the engine
  if (PRIVATE) {
    priv = await startPrivateEngine({ repo, procs, person: 'p_learn01', learners: true, onboard: true })
    engine = priv.engine
    log('setup', `throwaway engine on ${new URL(engine).host} (own home and data directory; no desktop app, so no ring is drawn)`)
  } else {
    engine = strip(flag('engine', 'http://127.0.0.1:7700'))
    const h = await getJson(`${engine}/health`, {}, 5000).catch(() => null)
    if (h?.status !== 200) throw new Error(`no engine answers at ${engine} (start the stack: make live)`)
    log('setup', `engine ${new URL(engine).host}: mock=${h.body.mock}, provider=${h.body.provider}`)
  }
  const ident = (await getJson(`${engine}/identity`, {}, 5000)).body
  person = String(PERSON_FLAG ?? ident?.person ?? 'p_learn01')
  log('setup', `person ${person}, scene ${SCENE}, pace ${PACE_NAME} (x${PACE})${HEADLESS ? ', headless' : ', headed'}`)
  const ext = extensionDist(repo, flag('extension', null))

  // ---- 2. the shared sandbox, under the lock
  const lockData = flag('lock-data-dir', process.env.KNACK_LOCK_DATA_DIR || process.env.UNDERSTUDY_DATA_DIR || (existsSync(join(repo, 'data/live-data')) ? join(repo, 'data/live-data') : join(repo, 'data')))
  const holderEnv = { PATH: process.env.PATH, HOME: process.env.HOME, UNDERSTUDY_DATA_DIR: String(lockData) }
  const lockCode = `import sys\nfrom understudy_agent.sandbox_sites.lock import sandbox_lock\nwith sandbox_lock("demo-worker", timeout_s=${LOCK_WAIT_S}):\n    print("LOCKED", flush=True)\n    sys.stdin.read()\n`
  const holder = procs.start('sandbox-lock', pythonOf(repo), ['-I', '-c', lockCode], { env: holderEnv, cwd: tmpdir() })
  await until(() => holder.logTail.includes('LOCKED') || holder.exitCode !== null, (LOCK_WAIT_S + 10) * 1000, 'the sandbox lock', 250)
  if (!holder.logTail.includes('LOCKED')) throw new Error(`could not take the sandbox lock (${holder.logTail.trim().slice(-200) || 'another run holds it'}); lock directory ${lockData}`)
  lockHeld = true
  log('setup', `sandbox lock held (${String(lockData).replace(process.env.HOME ?? '', '~')}/locks)`)
  for (const p of SITES) {
    const ok = await getJson(`http://127.0.0.1:${p}/healthz`, {}, 3000).catch(() => null)
    if (ok?.status !== 200) throw new Error(`the sandbox site on ${p} is not running (scripts/dev.sh starts 7801 to 7803)`)
  }
  if (RESET) {
    for (const p of SITES) await getJson(`http://127.0.0.1:${p}/__reset`, { method: 'POST' }, 4000)
    resetSites = true
    log('setup', 'sandbox sites reset (notes, submissions and counters cleared)')
  }

  // ---- 3. the coach at the first help level (study mode), if asked
  if (STUDY && SCENE !== 'stuck') {
    const s = await postJson(`${engine}/study/mode`, { person, block: 'train', skill_on: 'cliff', level: 'L1' })
    studyOn = s.status === 200
    check('coach set to the first help level on the cliff skill (study mode, cleared at the end)', studyOn, `status ${s.status}`)
  }

  // ---- 4. a real Chromium with the real extension, aimed at that engine and the Knack app's extension server
  userData = mkdtempSync(join(tmpdir(), 'knack-demo-worker-'))
  context = await chromium.launchPersistentContext(userData, {
    channel: HEADLESS ? 'chromium' : undefined,
    headless: HEADLESS,
    viewport: HEADLESS ? { width: WW, height: WH } : null,
    args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`, '--no-first-run', '--no-default-browser-check', `--window-position=${WX},${WY}`, `--window-size=${WW},${WH}`],
  })
  let [sw] = context.serviceWorkers()
  if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 20000 })
  await until(() => sw.evaluate(async () => Boolean((await chrome.storage.local.get('salt')).salt)), 15000, 'the extension to start')
  await sw.evaluate(
    async ({ engine, desktop, person }) => {
      await chrome.storage.local.set({ config: { capturing: true, person, role: 'benefits-processor', engine_url: engine, desktop_url: desktop } })
    },
    { engine, desktop: PRIVATE ? 'http://127.0.0.1:9' : DESKTOP_EXT, person },
  )
  if (CURSOR) await context.addInitScript(CURSOR_JS)
  tab1 = context.pages()[0] ?? (await context.newPage())
  tab2 = await context.newPage()
  log('setup', `Chromium with the capture extension is up (capture on for ${person}; events go to ${new URL(engine).host}${PRIVATE ? '' : `, element positions to the Knack app at ${new URL(DESKTOP_EXT).host}`})`)
  void watcher()
  await wait(1500)

  // ---- 5. the coach scene
  if (SCENE !== 'stuck') {
    log('scene', 'COACH: a teammate works a case and skips the cliff check')
    const c = CASES.coach
    await enterHousehold(c)
    await wait(2600) // reads the result
    const tMiss = Date.now()
    await glanceAtNote(c)
    const ring = await until(() => decisions.coach.find((d) => d.at >= tMiss && d.action === 'annotate'), 60000, 'the coach to decide on a ring', 400).catch(() => null)
    check('the coach decided to ring the skipped step', Boolean(ring), ring ? `${Math.round((ring.at - tMiss) / 100) / 10} s after the miss` : 'no annotate decision in 60 s (is the coach at the first level? is the extension reaching the engine?)')
    if (ring) log('ring', 'the ring should now be on "Check cliff edges" (drawn by the Knack app, not by this script)')
    await wait(7500) // the worker reads the ring, and the camera has time to hold on it
    await followCue(c)
    await saveNote(c)
    out.coachDecisions = decisions.coach.filter((d) => d.action !== 'silent').length
  }

  // ---- 6. the stuck scene
  if (SCENE !== 'coach') {
    if (SCENE === 'both') {
      log('wait', `${GAP_S} s of quiet, so the engine's cooldown after the coach prompt has passed`)
      await sleep(GAP_S * 1000)
    }
    if (studyOn) {
      // The coach is back at the worker's own level for this scene (a dot, silent): only Cue should speak while the worker hesitates.
      const r = await postJson(`${engine}/study/mode/clear`, {})
      studyOn = r.status !== 200
      log('setup', `study mode ${r.status === 200 ? 'cleared' : 'NOT cleared'} before the stuck scene, so the coach is at the worker's own level`)
    }
    log('scene', 'STUCK: a teammate does the right things, then hesitates over the case note')
    const c = CASES.stuck
    await enterHousehold(c)
    await wait(2400) // reads the result
    await followCue(c) // the cliff check, in the expert's order: nothing for the coach to say
    await fillNote(c) // copies the figures into the case note ...
    const t0 = Date.now()
    log('worker', `STALL: the note is filled in and the worker hovers over it for up to ${STUCK_S} s without saving (Cue's gate wants two quiet stuck readings)`)
    const stallEnd = t0 + STUCK_S * 1000 // real time: Cue's gate and the stuck model run on the engine's clock, not on the pace
    while (Date.now() < stallEnd) {
      await idleMoves(tab2, 5000)
      if (decisions.cue.some((d) => d.at >= t0 && d.kind !== 'none')) break
    }
    const cue = decisions.cue.find((d) => d.at >= t0 && d.kind !== 'none')
    check('Cue decided to speak during the stall', Boolean(cue), cue ? `${cue.kind}${cue.step ? ` on ${cue.step}` : ''}, ${Math.round((cue.at - t0) / 1000)} s into the stall` : `no cue decision in ${STUCK_S} s (Cue is a soft check: its gate wants two stuck readings, a quiet moment and a step the worker is not yet fluent in)`)
    if (cue) log('cue', 'Cue should now be on screen (drawn by the Knack app, not by this script); the worker takes the step it names')
    await wait(6000) // the camera holds on the cue
    await saveDraft(c)
  }

  out.ok = out.checks['the coach decided to ring the skipped step'] ? out.checks['the coach decided to ring the skipped step'].pass : true
  log('done', `the script ran to the end${out.ok ? '' : ', but the coach did not decide to ring'}`)
} catch (e) {
  out.error = String(e?.stack ?? e).split('\n').slice(0, 4).join(' | ')
  log('ERROR', String(e?.message ?? e))
  out.logs = Object.fromEntries([...procs.children].map(([n, p]) => [n, (p.logTail ?? '').split('\n').slice(-4).join(' | ')]))
} finally {
  watching = false
  await cleanup()
  out.cleanup = { throwawayRemoved: priv?.root ? !existsSync(priv.root) : null, processesLeft: procs.left() }
}
out.sheet = sheet
if (CUE_SHEET && typeof CUE_SHEET === 'string') writeFileSync(CUE_SHEET, JSON.stringify(sheet, null, 2))
if (AS_JSON) console.log(JSON.stringify(out, null, 2))
else console.log(`\n${out.ok ? 'OK' : 'NOT OK'}: ${Object.values(out.checks).filter((c) => c.pass).length} of ${Object.keys(out.checks).length} checks passed${out.error ? `; error: ${out.error.slice(0, 160)}` : ''}`)
process.exit(out.ok ? 0 : 1)
