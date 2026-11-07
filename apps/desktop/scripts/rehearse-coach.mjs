#!/usr/bin/env node
// Rehearsal of the demo's COACH step, end to end on this machine, with NO operating-system input.
//
//   throwaway engine (own UNDERSTUDY_HOME and UNDERSTUDY_DATA_DIR, a copy of the learners' synthetic data, onboarding p_learn01 with
//   capture on) + the real extension in a real, headed Chromium pointed at it + the real sandbox sites on :7801-7803 (this script
//   holds sandbox_lock("desktop-rehearsal") the whole time) + this desktop app (UNDERSTUDY_ENGINE_URL = the throwaway engine, real
//   input disabled, actuator in dry-run) + Playwright over CDP playing the worker (trusted events inside the browser; no OS clicks
//   or keys, no clipboard).
//
// The worker opens calculator A, enters a household, reads the first result, glances at the case note (a second tab) and comes
// back WITHOUT opening "Check cliff edges". From the screen this checks, with frame grabs analysed in memory (nothing is saved):
// when the coach decision arrives and when the ring is on screen, where the ring sits around the real button, what the bubble says,
// that the ring leaves with the tab and comes back with it, and what happens when the worker presses the button (ring clears, the
// response goes to /coach/feedback and is recorded). Later cases: a quicker follow, lighter help (a nudge: text, no ring) and a
// post-test block (nothing fires).
//
// Needs: npm run build here, the extension in ../../extension/dist, Playwright Chromium, the sandbox sites running, Screen Recording
// granted to the app (it never prompts; if macOS asks for anything, stop and ask the person).
// Run: REHEARSE_TMP=<scratch dir> node scripts/rehearse-coach.mjs     (prints one JSON report; exit code 0 when every check passed)
import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = dirname(fileURLToPath(import.meta.url))
const app = resolve(here, '..')
const repo = resolve(app, '../..')
const dist = join(repo, 'extension/dist')
const venv = join(repo, '.venv/bin')
if (!existsSync(join(dist, 'manifest.json'))) throw new Error('build the extension first (extension/dist)')
if (!existsSync(join(repo, 'data/synthetic/learners'))) throw new Error('data/synthetic/learners is missing')

const PERSON = 'p_learn01'
const SITE = 'http://127.0.0.1:7801'
const SITES = [7801, 7802, 7803]
const EXT_PORT = Number(process.env.REHEARSE_EXT_PORT ?? 7732)
const DEBUG_PORT = Number(process.env.REHEARSE_DEBUG_PORT ?? 7788)
const COOLDOWN_MS = 125_000 // the engine's dignity gate: 120 s of quiet after the coach speaks
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const until = async (cond, ms, label, every = 100) => {
  const t0 = Date.now()
  for (;;) {
    const v = await cond()
    if (v) return v
    if (Date.now() - t0 > ms) throw new Error(`timed out waiting for ${label}`)
    await sleep(every)
  }
}
const freePort = () =>
  new Promise((res, rej) => {
    const s = createServer()
    s.once('error', rej)
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port
      s.close(() => res(p))
    })
  })
const getJson = async (url, init) => {
  const r = await fetch(url, init)
  const text = await r.text()
  let body = null
  try {
    body = JSON.parse(text)
  } catch {
    /* not JSON */
  }
  return { status: r.status, body }
}
const postJson = (url, body) => getJson(url, { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: JSON.stringify(body) })

// ---------------------------------------------------------------------------------------------- what to clean up
const root = mkdtempSync(join(process.env.REHEARSE_TMP ?? tmpdir(), 'understudy-rehearsal-'))
const children = new Map() // name -> ChildProcess (only processes this script started)
let context = null
let analysisBrowser = null
const start = (name, cmd, args, opts = {}) => {
  const p = spawn(cmd, args, { stdio: ['pipe', 'pipe', 'pipe'], ...opts })
  p.logTail = ''
  const keep = (d) => (p.logTail = (p.logTail + d).slice(-4000))
  p.stdout.on('data', keep)
  p.stderr.on('data', keep)
  children.set(name, p)
  return p
}
const alive = (p) => p.exitCode === null && p.signalCode === null
const stop = async (name, signal = 'SIGTERM') => {
  const p = children.get(name)
  if (!p || !alive(p)) return
  p.kill(signal)
  await Promise.race([new Promise((r) => p.once('exit', r)), sleep(6000)])
  if (alive(p)) {
    p.kill('SIGKILL')
    await Promise.race([new Promise((r) => p.once('exit', r)), sleep(2000)])
  }
}

const out = { ok: false, checks: {}, cases: [], notes: [] }
const check = (name, pass, detail) => {
  out.checks[name] = { pass: Boolean(pass), ...(detail === undefined ? {} : { detail }) }
  return Boolean(pass)
}

// ---------------------------------------------------------------------------------------------- the timeline
const T0 = Date.now()
const timeline = []
const mark = (kind, extra = {}) => {
  const t = Date.now()
  timeline.push({ t, at: t - T0, kind, ...extra })
  return t
}
const first = (kind, after = 0, pred = () => true) => timeline.find((e) => e.kind === kind && e.t >= after && pred(e))

const dom = () => getJson(`http://127.0.0.1:${DEBUG_PORT}/dom`).then((r) => r.body).catch(() => null)
const overlayText = () => getJson(`http://127.0.0.1:${DEBUG_PORT}/overlay/text`).then((r) => r.body?.text ?? null).catch(() => null)

let watching = true
const seen = { decision: null, ring: null, text: null, feedback: null }
async function watcher() {
  let n = 0
  while (watching) {
    const d = await dom()
    if (d) {
      const ld = d.coach?.lastDecision
      const key = ld ? `${ld.decisionId}|${ld.action}|${ld.at}` : null
      if (key && key !== seen.decision) {
        seen.decision = key
        mark('desktop:decision', { action: ld.action, decisionId: ld.decisionId, zone: ld.zone, message: ld.message, reasons: ld.reasons, level: ld.level })
      }
      const ring = d.ring ? `${d.ring.ref ?? ''}|${d.ring.visible}|${d.ring.hiddenFor ?? ''}` : 'none'
      if (ring !== seen.ring) {
        seen.ring = ring
        mark('desktop:ring', { present: Boolean(d.ring), visible: d.ring?.visible ?? false, hiddenFor: d.ring?.hiddenFor ?? null, ref: d.ring?.ref ?? null, message: d.ring?.message ?? null })
      }
      const fb = d.coach?.lastFeedback
      const fbKey = fb ? `${fb.decisionId}|${fb.outcome}|${fb.at}` : null
      if (fbKey && fbKey !== seen.feedback) {
        seen.feedback = fbKey
        mark('desktop:feedback', { ...fb })
      }
      out.chip = d.chip ?? out.chip
    }
    if (n++ % 3 === 0) {
      const text = await overlayText()
      if (text !== null && text !== seen.text) {
        seen.text = text
        mark('overlay:text', { text: text.replace(/\s+/g, ' ').trim().slice(0, 240) })
      }
    }
    await sleep(80)
  }
}

// ---------------------------------------------------------------------------------------------- in-memory frame analysis
// The screen frame comes from the app's own capture service. It is decoded and analysed inside a separate headless Chromium page
// (no extension, no profile) and only numbers come back: nothing is written to disk.
const ANALYSER = `
window.__slots = {}
window.__load = async (slot, b64) => {
  const img = new Image(); img.src = 'data:image/jpeg;base64,' + b64; await img.decode()
  const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight
  const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(img, 0, 0)
  window.__slots[slot] = g.getImageData(0, 0, c.width, c.height)
  return { width: c.width, height: c.height }
}
// The sandbox button is solid green (#00703c): its bounding box in the frame is the real element.
window.__button = (slot, region) => {
  const { data, width, height } = window.__slots[slot]
  let x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1, n = 0
  const [ax, ay, bx, by] = region.map((v, i) => Math.round(Math.max(0, Math.min(i % 2 ? height : width, v))))
  for (let y = ay; y < by; y++) for (let x = ax; x < bx; x++) {
    const i = (y * width + x) * 4, r = data[i], g = data[i + 1], b = data[i + 2]
    if (r < 45 && g > 85 && g < 145 && b > 35 && b < 100) { n++; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y }
  }
  return n > 150 ? { x0, y0, x1, y1, n } : null
}
// How much of the overlay window's own picture (transparent except for what it draws) is painted inside a region (points).
window.__alpha = async (b64, region, screenW) => {
  const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode()
  const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight
  const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(img, 0, 0)
  const s = img.naturalWidth / screenW
  const [x0, y0, x1, y1] = region.map((v) => Math.max(0, Math.round(v * s)))
  const { data, width } = g.getImageData(0, 0, c.width, c.height)
  let n = 0
  for (let y = y0; y < Math.min(c.height, y1); y++) for (let x = x0; x < Math.min(width, x1); x++) if (data[(y * width + x) * 4 + 3] > 24) n++
  return n
}
// The ring: what changed against the frame taken before, scanned OUTWARD from the middle of each side of the button. The first changed
// pixel is the ring's inner edge on that side, the end of the changed run is its outer edge. (The bubble sits above the ring and can
// touch it, so the top is read at the inner edge only.) Five parallel scan lines are taken and the median used.
window.__edges = (slot, base, btn, region) => {
  const A = window.__slots[slot], B = window.__slots[base]
  if (!A || !B || A.width !== B.width || A.height !== B.height) return { error: 'frames differ in size' }
  const { width, height } = A
  const [ax, ay, bx, by] = region.map((v, i) => Math.round(Math.max(0, Math.min(i % 2 ? height : width, v))))
  const changed = (x, y) => {
    if (x < ax || y < ay || x >= bx || y >= by) return false
    const i = (y * width + x) * 4
    return Math.abs(A.data[i] - B.data[i]) + Math.abs(A.data[i + 1] - B.data[i + 1]) + Math.abs(A.data[i + 2] - B.data[i + 2]) > 90
  }
  let total = 0
  for (let y = ay; y < by; y++) for (let x = ax; x < bx; x++) if (changed(x, y)) total++
  const cx = Math.round((btn.x0 + btn.x1) / 2), cy = Math.round((btn.y0 + btn.y1) / 2)
  const med = (v) => { const w = v.filter((n) => n !== null).sort((p, q) => p - q); return w.length ? w[w.length >> 1] : null }
  const scan = (x0, y0, dx, dy, perp) => {
    const inner = [], outer = []
    for (const off of [-8, -4, 0, 4, 8]) {
      let x = x0 + (perp === 'x' ? off : 0), y = y0 + (perp === 'y' ? off : 0)
      let i = 0, firstHit = null, lastHit = null, quiet = 0
      for (; i < 400; i++) {
        x += dx; y += dy
        if (x < ax || y < ay || x >= bx || y >= by) break
        if (changed(x, y)) { if (firstHit === null) firstHit = i + 1; lastHit = i + 1; quiet = 0 } else if (firstHit !== null && ++quiet > 5) break
      }
      inner.push(firstHit); outer.push(lastHit)
    }
    return { inner: med(inner), outer: med(outer) }
  }
  return {
    changedPixels: total,
    left: scan(btn.x0, cy, -1, 0, 'y'), right: scan(btn.x1, cy, 1, 0, 'y'),
    top: scan(cx, btn.y0, 0, -1, 'x'), bottom: scan(cx, btn.y1, 0, 1, 'x'),
  }
}
`

// ---------------------------------------------------------------------------------------------- the run
let holderLocked = false
try {
  // ---- 1. the sandbox lock (default data dir, shared with the other agents), then the throwaway engine
  const holderEnv = { ...process.env }
  delete holderEnv.UNDERSTUDY_DATA_DIR
  delete holderEnv.UNDERSTUDY_HOME
  const lockCode = 'import sys\nfrom understudy_agent.sandbox_sites.lock import sandbox_lock\nwith sandbox_lock("desktop-rehearsal", timeout_s=900):\n    print("LOCKED", flush=True)\n    sys.stdin.read()\n'
  const holder = start('sandbox-lock', join(venv, 'python'), ['-I', '-c', lockCode], { env: holderEnv, cwd: root })
  await until(() => holder.logTail.includes('LOCKED') || holder.exitCode !== null, 910_000, 'the sandbox lock', 250)
  if (!holder.logTail.includes('LOCKED')) throw new Error(`could not take the sandbox lock: ${holder.logTail.trim().slice(-300)}`)
  holderLocked = true
  mark('sandbox:locked')

  const home = join(root, 'home')
  const data = join(root, 'data')
  mkdirSync(home)
  mkdirSync(join(data, 'synthetic'), { recursive: true })
  cpSync(join(repo, 'data/synthetic/learners'), join(data, 'synthetic/learners'), { recursive: true }) // a copy: nothing here can write to the shared data
  const enginePort = await freePort()
  const engine = `http://127.0.0.1:${enginePort}`
  start('engine', join(venv, 'understudy'), ['serve', '--port', String(enginePort)], {
    cwd: root,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, UNDERSTUDY_HOME: home, UNDERSTUDY_DATA_DIR: data, UNDERSTUDY_MOCK: '1', ENGINE_PORT: String(enginePort) },
  })
  await until(() => fetch(`${engine}/health`).then((r) => r.ok).catch(() => false), 60_000, 'the throwaway engine', 300)
  const onboard = await postJson(`${engine}/onboarding`, { role: 'benefits-processor', answers: { capture: true }, person: PERSON })
  const identity = (await getJson(`${engine}/identity`)).body
  const memory = (await getJson(`${engine}/memory`)).body
  const captureLine = /Capture: times only/.test(JSON.stringify(memory))
  out.setup = { engine: `127.0.0.1:${enginePort} (own home and data dir, learners' synthetic data copied in)`, onboarding: onboard.status, identity, captureLine }
  check('throwaway engine onboarded with capture on', onboard.status === 200 && identity?.person === PERSON && captureLine)
  const natural = (await getJson(`${engine}/coach/next?person=${PERSON}&dry=1`)).body?.data
  out.setup.naturalState = { level: natural?.level, chip: natural?.chip, mastery: natural?.mastery, reasons: natural?.reason_codes }
  const stateBody = (await getJson(`${engine}/coach/state?person=${PERSON}`)).body
  out.setup.coachState = { level: stateBody?.level, chip: stateBody?.chip, case: stateBody?.case, task: stateBody?.task?.name }

  // ---- 2. the sandbox sites start clean
  for (const p of SITES) await getJson(`http://127.0.0.1:${p}/__reset`, { method: 'POST' })
  const siteState = async () => (await getJson(`${SITE}/__state`)).body
  const st0 = await siteState()
  check('sandbox sites reset', st0 && Object.keys(st0.notes ?? {}).length === 0 && (st0.cliff_opens ?? []).length === 0)

  // ---- 3. this desktop app, pointed at the throwaway engine
  const userData = mkdtempSync(join(root, 'app-'))
  writeFileSync(join(userData, 'settings.json'), JSON.stringify({ onboardingDone: true, showDock: false }))
  const env = {
    ...process.env,
    OPENAI_API_KEY: '', // nothing here talks to a model
    UNDERSTUDY_ENGINE_URL: engine,
    UNDERSTUDY_AGENT_URL: 'http://127.0.0.1:9',
    UNDERSTUDY_EXT_PORT: String(EXT_PORT),
    ALONGSIDE_USERDATA: userData,
    ALONGSIDE_OVERLAY_CAPTURABLE: '1',
    ALONGSIDE_ACTUATOR_DRYRUN: '1',
    ALONGSIDE_AGENCY_LOOP: '0',
    ALONGSIDE_DEBUG_PORT: String(DEBUG_PORT),
    ALONGSIDE_LOCK_MAX_SECONDS: '1500',
  }
  delete env.ALONGSIDE_MOCK
  delete env.UNDERSTUDY_MOCK
  delete env.UNDERSTUDY_REAL_ACTUATOR
  delete env.UNDERSTUDY_PERSON
  start('electron', 'bash', ['scripts/electron-lock.sh', 'rehearse', 'node_modules/.bin/electron', '.'], { cwd: app, env })
  await until(() => fetch(`http://127.0.0.1:${DEBUG_PORT}/health`).then((r) => r.ok).catch(() => false), 120_000, 'the app', 300)
  await until(() => fetch(`http://127.0.0.1:${EXT_PORT}/ext/status`).then((r) => r.ok).catch(() => false), 15_000, 'the extension server')
  const d0 = await until(async () => {
    const d = await dom()
    return d?.capture ? d : null
  }, 20_000, 'the app to report its capture mode')
  out.setup.appCapture = d0.capture
  void watcher()
  // The app reads the engine (identity, capture line) at start; give it a moment, then check what it adopted.
  await sleep(3000)

  // ---- 4. real Chromium with the real extension, aimed at the throwaway engine and this app
  context = await chromium.launchPersistentContext(join(root, 'chrome'), {
    headless: false,
    viewport: null,
    args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`, '--no-first-run', '--no-default-browser-check', '--window-position=140,90', '--window-size=1000,720'],
  })
  let [sw] = context.serviceWorkers()
  if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 20_000 })
  await until(() => sw.evaluate(async () => Boolean((await chrome.storage.local.get('salt')).salt)), 15_000, 'extension init')
  await sw.evaluate(async ({ ext, engine, person }) => {
    await chrome.storage.local.set({ config: { capturing: true, person, role: 'benefits-processor', engine_url: engine, desktop_url: `http://127.0.0.1:${ext}` } })
  }, { ext: EXT_PORT, engine, person: PERSON })
  const tab1 = context.pages()[0] ?? (await context.newPage())
  const tab2 = await context.newPage()
  analysisBrowser = await chromium.launch({ headless: true })
  const analyser = await analysisBrowser.newPage()
  await analyser.goto('about:blank')
  await analyser.evaluate(ANALYSER)

  // ---- helpers over the screen
  const noteUrl = (ref) => `${SITE}/casenote?case=${ref}`
  await tab1.goto(`${SITE}/`)
  await tab1.bringToFront()
  const geo = await tab1.evaluate(() => ({ dpr: devicePixelRatio, screenW: screen.width, screenH: screen.height }))
  const backing = geo.dpr
  const predicted = (selector) =>
    tab1.evaluate(
      ({ selector, backing }) => {
        const el = document.querySelector(selector)
        if (!el) return null
        const r = el.getBoundingClientRect()
        const z = devicePixelRatio / backing
        const side = Math.max(0, (outerWidth - innerWidth * z) / 2)
        const chrome = Math.max(0, outerHeight - innerHeight * z - side)
        return { x: screenX + side + r.left * z, y: screenY + chrome + r.top * z, w: r.width * z, h: r.height * z }
      },
      { selector, backing },
    )
  const ownerAt = (x, y) =>
    new Promise((res) => {
      const jxa = `ObjC.import('CoreGraphics'); function run(a){var x=+a[0],y=+a[1];var l=ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly|$.kCGWindowListExcludeDesktopElements,$.kCGNullWindowID)));for(var i=0;i<l.length;i++){var w=l[i],b=w.kCGWindowBounds;if(!b||x<b.X||x>=b.X+b.Width||y<b.Y||y>=b.Y+b.Height)continue;var n=String(w.kCGWindowOwnerName);if(n==='Dock'||n==='Window Server'||w.kCGWindowLayer>0&&b.Width>=1700)continue;return n}return 'none'}`
      const p = spawn('osascript', ['-l', 'JavaScript', '-e', jxa, '--', String(Math.round(x)), String(Math.round(y))])
      let o = ''
      p.stdout.on('data', (d) => (o += d))
      p.on('close', () => res(o.trim() || 'unknown'))
    })
  const raise = async (page, selector) => {
    for (let i = 0; i < 5; i++) {
      await page.bringToFront().catch(() => undefined)
      await sleep(500)
      const r = await predicted(selector)
      if (!r) return 'no element'
      const owner = await ownerAt(r.x + r.w / 2, r.y + r.h / 2)
      if (/chrom/i.test(owner)) return 'chromium'
      await sleep(800)
    }
    return 'covered by another window'
  }
  const grab = async (slot) => {
    const t0 = Date.now()
    const res = await fetch(`http://127.0.0.1:${DEBUG_PORT}/shot?purpose=live`)
    const buf = Buffer.from(await res.arrayBuffer())
    const t1 = Date.now()
    const dim = await analyser.evaluate(([s, b]) => window.__load(s, b), [slot, buf.toString('base64')])
    return { t0, t1, ...dim, scale: dim.width / geo.screenW }
  }
  let baseBtn = null
  const overlayPaintNear = async () => {
    const want = await predicted('#cliff-btn')
    const png = await fetch(`http://127.0.0.1:${DEBUG_PORT}/overlay.png`).then(async (r) => (r.ok ? Buffer.from(await r.arrayBuffer()) : null))
    if (!want || !png) return null
    return analyser.evaluate(([b, region, w]) => window.__alpha(b, region, w), [png.toString('base64'), [want.x - 40, want.y - 70, want.x + want.w + 40, want.y + want.h + 40], geo.screenW])
  }
  const regionFor = (r, scale, pad) => [(r.x - pad) * scale, (r.y - pad) * scale, (r.x + r.w + pad) * scale, (r.y + r.h + pad) * scale]
  // Where is the real button in a frame, and where is the ring around it (points)?
  const measure = async (slot, base, f) => {
    const want = await predicted('#cliff-btn')
    if (!want) return { error: 'no button on the page' }
    const region = regionFor(want, f.scale, 90)
    let btn = slot === base ? null : baseBtn // the button does not move: after the first frame use where it was before the ring
    if (!btn) btn = await analyser.evaluate(([s, r]) => window.__button(s, r), [slot, region])
    if (slot === base && btn) baseBtn = btn
    if (!btn) return { error: 'the green button is not visible in the frame (covered?)', topmostAtButton: await ownerAt(want.x + want.w / 2, want.y + want.h / 2) }
    const s = f.scale
    const edges = await analyser.evaluate(([a, b, bt, r]) => window.__edges(a, b, bt, r), [slot, base, btn, region])
    const buttonPts = { x: btn.x0 / s, y: btn.y0 / s, w: (btn.x1 - btn.x0) / s, h: (btn.y1 - btn.y0) / s }
    const res = { buttonPts: Object.fromEntries(Object.entries(buttonPts).map(([k, v]) => [k, +v.toFixed(1)])), predictedByDom: { x: +want.x.toFixed(1), y: +want.y.toFixed(1) }, domVsPixelsPts: { dx: +(buttonPts.x - want.x).toFixed(1), dy: +(buttonPts.y - want.y).toFixed(1) } }
    const sides = ['left', 'right', 'top', 'bottom']
    if (edges.error || !sides.every((k) => edges[k].inner !== null)) return { ...res, ring: null, changedPixels: edges.changedPixels ?? 0 }
    const inner = Object.fromEntries(sides.map((k) => [k, +(edges[k].inner / s).toFixed(1)]))
    const outer = Object.fromEntries(['left', 'right', 'bottom'].map((k) => [k, +(edges[k].outer / s).toFixed(1)]))
    return {
      ...res,
      ring: true,
      innerGapsPts: inner, // button edge to the ring's inner edge, per side
      outerGapsPts: outer, // ... to the ring's outer edge (top left out: the bubble can touch it)
      centreErrorPts: { dx: +((inner.left - inner.right) / 2).toFixed(1), dy: +((inner.top - inner.bottom) / 2).toFixed(1) },
    }
  }

  // ---- the worker
  const WORDS = [
    [/how many adults/i, 'select', '1'],
    [/your age/i, 'fill', '34'],
    [/partner.s age/i, 'skip'],
    [/children/i, 'fill', '4, 7'],
    [/your monthly take-home/i, 'fill', '1400'],
    [/partner.s monthly/i, 'skip'],
    [/health condition/i, 'select', 'no'],
    [/rent or own/i, 'select', 'rent'],
    [/monthly rent/i, 'fill', '650'],
    [/bedrooms/i, 'select', '2'],
    [/savings/i, 'fill', '1200'],
    [/childcare/i, 'fill', '150'],
  ]
  const fillStep = async (page) => {
    const labels = await page.$$eval('main label', (ls) => ls.map((l) => ({ id: l.htmlFor, text: (l.textContent ?? '').trim() })))
    for (const l of labels) {
      const rule = WORDS.find(([re]) => re.test(l.text))
      if (!rule || rule[1] === 'skip') continue
      if (rule[1] === 'select') await page.selectOption(`#${l.id}`, rule[2])
      else await page.fill(`#${l.id}`, rule[2])
      await sleep(120)
    }
  }
  const calculatorA = async () => {
    await tab1.bringToFront()
    await tab1.goto(`${SITE}/`)
    await sleep(500)
    await tab1.getByRole('link', { name: 'Start now' }).click()
    for (let step = 1; step <= 4; step++) {
      await tab1.waitForSelector('main form')
      await fillStep(tab1)
      await tab1.click('main form button[type=submit]')
      await sleep(350)
    }
    await tab1.waitForSelector('#cliff-btn')
    await sleep(1200) // reads the result
  }
  const glanceAtNote = async (ref) => {
    // The "miss": the worker goes to the case note (a second tab) without having checked the cliff edges, then comes back.
    await tab2.goto(noteUrl(ref))
    await tab1.bringToFront()
    await sleep(700)
    const t = mark('worker:miss', { what: 'switches to the case note tab' })
    await tab2.bringToFront()
    await sleep(1100)
    await tab1.bringToFront()
    mark('worker:back', { what: 'back on the result page' })
    return t
  }
  const saveNote = async (ref, text) => {
    await tab2.bringToFront()
    await tab2.goto(noteUrl(ref))
    await tab2.fill('[name=case_ref]', ref)
    await tab2.fill('[name=result_a]', 'a')
    await tab2.fill('[name=result_b]', 'b')
    await tab2.fill('[name=result_c]', 'n/a')
    await tab2.fill('[name=note_text]', text)
    await tab2.click('button[type=submit]')
    await tab2.waitForSelector('#note-status, #cn-state')
    await sleep(2500) // the extension's last batch (task_end) leaves
  }
  const coachNext = async () => (await getJson(`${engine}/coach/next?person=${PERSON}&dry=1`)).body?.data
  const engineEvents = () => {
    const rows = []
    const realDir = join(data, 'real')
    const walk = (dir) => {
      for (const e of existsSync(dir) ? readdirSync(dir, { withFileTypes: true }) : []) {
        if (e.isDirectory()) walk(join(dir, e.name))
        else if (e.name.endsWith('.jsonl')) for (const line of readFileSync(join(dir, e.name), 'utf8').split('\n')) if (line.trim()) rows.push(JSON.parse(line))
      }
    }
    walk(realDir)
    return rows
  }
  const label = (e) => `${e.type} (${e.source}/${e.actor})${e.meta?.implicit ? ' implicit' : ''}${e.meta?.how ? ` how=${e.meta.how}` : ''}${e.meta?.outcome ? ` outcome=${e.meta.outcome}` : ''}`
  const lastActAt = () => [...timeline].reverse().find((e) => e.kind === 'desktop:decision' && e.action !== 'silent')?.t ?? 0
  const waitCooldown = async () => {
    const wait = lastActAt() + COOLDOWN_MS - Date.now()
    if (wait > 0) {
      out.notes.push(`waited ${Math.round(wait / 1000)} s for the engine's 120 s quiet period after the last prompt`)
      await sleep(wait)
    }
  }
  const setStudy = (body) => postJson(`${engine}/study/mode`, { person: PERSON, ...body })

  // A case from the first calculator to the miss; returns a clean baseline frame (no ring).
  const startCase = async (ref) => {
    mark('case:start', { ref })
    await calculatorA()
    const covered = await raise(tab1, '#cliff-btn')
    const baseFrame = await grab('base')
    const base = await measure('base', 'base', baseFrame)
    if (base.error) throw new Error(`cannot see the button before the miss: ${base.error} (${covered})`)
    return { covered, base, baseFrame }
  }

  // Wait for a ring to show on screen (frames against the baseline).
  const watchForRing = async (maxMs) => {
    const t0 = Date.now()
    let frames = 0
    while (Date.now() - t0 < maxMs) {
      const f = await grab('cur')
      frames++
      const m = await measure('cur', 'base', f)
      if (m.ring) return { t: f.t1, tBefore: f.t0, measure: m, frames }
    }
    return null
  }

  const ms = (a, b) => (a && b ? Math.round(b - a) : null)
  // What the overlay keeps of a message on the ring (the same rule as src/renderer/overlay/note-text.ts): one short line, 40 characters.
  const compactNote = (text, max = 40) => {
    const plain = (x) => x.replace(/[\s.,;:]+$/, '')
    const t = text.replace(/\s+/g, ' ').trim()
    if (plain(t).length <= max) return plain(t)
    const head = plain(t.split(/\s+(?:before|after|because|so that|while|when|until|and then)\s+/i)[0] ?? t)
    if (head.length >= 6 && head.length <= max) return head
    const sentence = plain(t.split(/(?<=[.?!])\s/)[0] ?? t)
    if (sentence.length <= max) return sentence
    const room = t.slice(0, max - 1)
    const sp = room.lastIndexOf(' ')
    return `${plain(sp >= 12 ? room.slice(0, sp) : room)}…`
  }

  // =========================================================================================== case 0: the learner is already at L4
  {
    const c = { name: 'case 0: no study mode, the learner is at their natural level' }
    const { covered } = await startCase('CASE-RH-0')
    const tMiss = await glanceAtNote('CASE-RH-0')
    await sleep(14_000) // two polls to see the miss, the gate, and then some
    const d = await dom()
    const decisions = timeline.filter((e) => e.kind === 'desktop:decision' && e.t >= tMiss)
    c.levelSeen = decisions.at(-1)?.level ?? null
    c.actions = [...new Set(decisions.map((e) => e.action))]
    c.reasons = decisions.at(-1)?.reasons ?? null
    c.ring = Boolean(d?.ring)
    c.chip = d?.chip
    check('natural state (learner at L4): the coach stays silent and no ring is drawn', decisions.length > 0 && !c.ring && c.actions.every((a) => a === 'silent'), c)
    out.cases.push({ ...c, windowOnTop: covered })
    await saveNote('CASE-RH-0', 'case 0')
  }

  // =========================================================================================== case 1: study mode L1, a slow follow
  {
    const c = { name: 'case 1: coach at L1 (study mode train, skill cliff), the worker reads the ring and follows after about 35 s' }
    const study = await setStudy({ block: 'train', skill_on: 'cliff', level: 'L1' })
    check('study mode train L1 accepted by the throwaway engine', study.status === 200, study.body?.mode)
    await sleep(2500)
    const { covered, base } = await startCase('CASE-RH-1')
    c.windowOnTop = covered
    c.buttonBeforeMiss = base.buttonPts
    const tMiss = await glanceAtNote('CASE-RH-1')
    const hit = await watchForRing(30_000)
    const dec = first('desktop:decision', tMiss, (e) => e.action === 'annotate')
    const ringState = first('desktop:ring', tMiss, (e) => e.visible === true)
    const wantNote = dec?.message ? compactNote(dec.message) : null
    const bubbleStart = first('overlay:text', tMiss, (e) => /cliff/i.test(e.text))
    const bubble = await until(() => (wantNote ? first('overlay:text', tMiss, (e) => e.text.includes(wantNote)) : null), 8000, 'the note on the ring').catch(() => null)
    c.timingMs = {
      missToDecisionArrivedAtApp: ms(tMiss, dec?.t),
      decisionToRingVisibleInApp: ms(dec?.t, ringState?.t),
      decisionToRingOnScreenFrame: ms(dec?.t, hit?.t),
      missToRingOnScreenFrame: ms(tMiss, hit?.t),
      decisionToNoteOnOverlay: ms(dec?.t, bubble?.t),
      frameGrabsUsed: hit?.frames ?? null,
      note: 'ring-on-screen is the end of the first frame grab that shows it (about 0.3 to 0.5 s per grab), so it is an upper bound',
    }
    c.decision = dec ? { action: dec.action, zone: dec.zone, level: dec.level, message: dec.message, reasons: dec.reasons } : null
    c.bubbleOnOverlay = bubble?.text ?? bubbleStart?.text ?? null
    check('/coach/next annotate with zone cliff_button reached the app', dec?.action === 'annotate' && dec?.zone === 'cliff_button', c.decision)
    check('the ring carries the coach message as one short note (about 40 characters, the full sentence is not on the screen)', wantNote && bubble?.text?.includes(wantNote) && !bubble.text.includes(dec.message) && wantNote.length <= 40, { message: dec?.message, shownOnScreen: wantNote, overlay: c.bubbleOnOverlay })
    check('the ring is on screen', Boolean(hit), c.timingMs)
    if (hit) {
      await sleep(1800) // let the ring finish easing in
      const f = await grab('cur')
      const m = await measure('cur', 'base', f)
      c.accuracy = m
      const g = m.innerGapsPts
      check('the ring surrounds the real "Check cliff edges" button (centre error within 3 pt each way, every gap positive)', m.ring && g && Math.abs(m.centreErrorPts.dx) <= 3 && Math.abs(m.centreErrorPts.dy) <= 3 && Object.values(g).every((v) => v > 0), m)
    }
    const ringShownAt = ringState?.t ?? Date.now()
    // The ring belongs to the tab with the button: it goes with the tab and comes back with it.
    const tAway = mark('worker:away', { what: 'looks at the case note tab again' })
    await tab2.bringToFront()
    const hid = await until(() => first('desktop:ring', tAway, (e) => e.visible === false), 6000, 'the ring to hide when the button leaves the screen').catch(() => null)
    await sleep(500)
    const paintAway = await overlayPaintNear() // the overlay's own picture: nothing may be drawn where the button was
    const tBack = mark('worker:return', { what: 'returns to the result page' })
    await tab1.bringToFront()
    const back = await until(() => first('desktop:ring', tBack, (e) => e.visible === true), 8000, 'the ring to return').catch(() => null)
    await sleep(1800)
    const fBack = await grab('cur')
    const mBack = await measure('cur', 'base', fBack)
    c.tabAway = { hiddenAfterMs: ms(tAway, hid?.t), hiddenReason: hid?.hiddenFor ?? null, overlayPaintedPixelsWhileAway: paintAway, returnedAfterMs: ms(tBack, back?.t), ringBackOnScreen: Boolean(mBack.ring), accuracyAfterReturn: mBack.centreErrorPts ?? null }
    check('the ring is hidden while the button is on another tab (state and pixels), and back when the worker returns', Boolean(hid) && paintAway === 0 && Boolean(back) && Boolean(mBack.ring), c.tabAway)
    // Reads the message for a while, then presses the button (33 s after the ring first showed, past the engine's own 30 s follow window).
    await sleep(Math.max(0, ringShownAt + 33_000 - Date.now()))
    await raise(tab1, '#cliff-btn')
    const tClick = mark('worker:click', { what: 'presses Check cliff edges' })
    await tab1.click('#cliff-btn')
    const cleared = await until(() => first('desktop:ring', tClick, (e) => e.present === false), 12_000, 'the ring to clear after the click').catch(() => null)
    const fb = await until(() => first('desktop:feedback', tClick), 12_000, 'the feedback to be posted').catch(() => null)
    await sleep(900)
    const paintAfter = await overlayPaintNear()
    const sandbox = await siteState()
    const evs = engineEvents().filter((e) => e.type.startsWith('coach_'))
    c.afterClick = {
      ringClearedAfterMs: ms(tClick, cleared?.t),
      feedbackPostedAfterMs: ms(tClick, fb?.t),
      feedback: fb ? { outcome: fb.outcome, ok: fb.ok, recorded: fb.recorded, note: fb.note } : null,
      overlayPaintedPixelsNearButtonAfter: paintAfter,
      sandboxCliffOpens: (sandbox?.cliff_opens ?? []).length,
      coachEventsInEngine: evs.map(label),
    }
    check('pressing the button opened the cliff panel (sandbox state)', (sandbox?.cliff_opens ?? []).length === 1)
    check('the ring clears after the button press (state and pixels: the overlay paints nothing near the button)', Boolean(cleared) && paintAfter === 0, c.afterClick)
    check('followed went to /coach/feedback and was recorded', fb?.outcome === 'followed' && fb.ok === true && fb.recorded === true, c.afterClick.feedback)
    check("coach_followed reached the engine (the engine's own and the desktop's)", evs.some((e) => e.type === 'coach_followed'), c.afterClick.coachEventsInEngine)
    out.cases.push(c)
    await saveNote('CASE-RH-1', 'case 1, cliff edges checked after the prompt')
    c.levelAfter = await coachNext().then((d) => ({ level: d?.level, chip: d?.chip, mastery: d?.mastery, reasons: d?.reason_codes }))
  }

  // =========================================================================================== case 2: study mode L1 again, a quick follow
  {
    const c = { name: 'case 2: the same miss in the next case, the worker follows within a few seconds' }
    await waitCooldown()
    const { covered } = await startCase('CASE-RH-2')
    c.windowOnTop = covered
    const tMiss = await glanceAtNote('CASE-RH-2')
    const hit = await watchForRing(30_000)
    const dec = first('desktop:decision', tMiss, (e) => e.action === 'annotate')
    c.timingMs = { missToDecisionArrivedAtApp: ms(tMiss, dec?.t), missToRingOnScreenFrame: ms(tMiss, hit?.t) }
    check('case 2: the ring comes up again in the next case', dec?.action === 'annotate' && Boolean(hit), c.timingMs)
    await sleep(3500)
    await raise(tab1, '#cliff-btn')
    const tClick = mark('worker:click', { what: 'presses Check cliff edges quickly' })
    await tab1.click('#cliff-btn')
    const cleared = await until(() => first('desktop:ring', tClick, (e) => e.present === false), 12_000, 'the ring to clear').catch(() => null)
    const fb = await until(() => first('desktop:feedback', tClick), 12_000, 'the feedback').catch(() => null)
    c.afterClick = { ringClearedAfterMs: ms(tClick, cleared?.t), feedback: fb ? { outcome: fb.outcome, ok: fb.ok, recorded: fb.recorded, note: fb.note } : null }
    check('case 2: a quick follow clears the ring and is posted (the engine may already have labelled it itself: recorded false, already recorded)', Boolean(cleared) && fb?.outcome === 'followed' && fb.ok === true, c.afterClick)
    out.cases.push(c)
    await saveNote('CASE-RH-2', 'case 2')
    c.levelAfter = await coachNext().then((d) => ({ level: d?.level, chip: d?.chip, mastery: d?.mastery }))
  }

  // =========================================================================================== case 3: lighter help (L2): a nudge, text only
  {
    const c = { name: 'case 3: lighter help (study mode level L2): a question as text, no ring' }
    const study = await setStudy({ block: 'train', skill_on: 'cliff', level: 'L2' })
    check('study mode train L2 accepted', study.status === 200)
    await waitCooldown()
    await sleep(2500)
    const { covered } = await startCase('CASE-RH-3')
    c.windowOnTop = covered
    const tMiss = await glanceAtNote('CASE-RH-3')
    const dec = await until(() => first('desktop:decision', tMiss, (e) => e.action === 'nudge'), 30_000, 'a nudge decision').catch(() => null)
    const text = await until(() => (dec?.message ? first('overlay:text', tMiss, (e) => e.text.includes(dec.message.slice(0, 18))) : null), 8000, 'the nudge text on the overlay').catch(() => null)
    await sleep(1500)
    const d = await dom()
    c.decision = dec ? { action: dec.action, level: dec.level, message: dec.message, zone: dec.zone } : null
    c.textOnOverlay = text?.text ?? null
    c.ringDrawn = Boolean(d?.ring)
    c.chip = d?.chip
    check('L2 gives a nudge as text, and no ring', dec?.action === 'nudge' && Boolean(text) && !d?.ring, c)
    out.cases.push(c)
    await saveNote('CASE-RH-3', 'case 3')
  }

  // =========================================================================================== case 4: post-test block: nothing fires
  {
    const c = { name: 'case 4: study mode post_test: the coach is silent' }
    const study = await setStudy({ block: 'post_test' })
    check('study mode post_test accepted', study.status === 200)
    await sleep(2500)
    const { covered } = await startCase('CASE-RH-4')
    c.windowOnTop = covered
    const tMiss = await glanceAtNote('CASE-RH-4')
    await sleep(16_000)
    const decisions = timeline.filter((e) => e.kind === 'desktop:decision' && e.t >= tMiss)
    const d = await dom()
    const shown = engineEvents().filter((e) => e.type === 'coach_shown' && Date.parse(e.t) >= tMiss)
    c.actions = [...new Set(decisions.map((e) => e.action))]
    c.reasons = decisions.at(-1)?.reasons ?? null
    c.ringDrawn = Boolean(d?.ring)
    c.overlayText = (await overlayText())?.replace(/\s+/g, ' ').trim().slice(0, 120) ?? null
    c.coachShownEventsSinceMiss = shown.length
    check('post_test: no decision, no ring, no coach_shown', decisions.length > 0 && c.actions.every((a) => a === 'silent') && !c.ringDrawn && shown.length === 0, c)
    out.cases.push(c)
    await saveNote('CASE-RH-4', 'case 4')
    await postJson(`${engine}/study/mode/clear`, {})
  }

  // ---- what the engine recorded of all this
  const byType = {}
  for (const e of engineEvents()) {
    const k = `${e.type}${e.type.startsWith('coach_') ? ` (${e.source}/${e.actor})` : ''}`
    byType[k] = (byType[k] ?? 0) + 1
  }
  out.engineStore = byType
  const chipWords = timeline.filter((e) => e.kind === 'overlay:text' && /Watch me|Walk with me|Nudge me|On my own/i.test(e.text))
  check('no persistent coach chip: nothing on the overlay ever said "Watch me" or any other help-level name', chipWords.length === 0, chipWords.slice(0, 2).map((e) => e.text))
  out.ok = Object.values(out.checks).every((x) => x.pass)
} catch (e) {
  out.error = String(e?.stack ?? e)
  out.dom = await dom().catch(() => null)
  out.logs = Object.fromEntries([...children].map(([n, p]) => [n, (p.logTail ?? '').split('\n').slice(-8).join('\n')]))
} finally {
  watching = false
  let prev = ''
  out.timeline = timeline
    .filter((e) => ['worker:miss', 'worker:away', 'worker:return', 'worker:click', 'desktop:decision', 'desktop:ring', 'desktop:feedback', 'overlay:text'].includes(e.kind))
    .filter((e) => {
      // consecutive identical decisions (the brain polls every 2 s) are listed once
      const sig = e.kind === 'desktop:decision' ? `${e.action}|${e.decisionId}|${(e.reasons ?? []).join()}` : null
      if (sig === null) return true
      const same = sig === prev
      prev = sig
      return !same
    })
    .map((e) => ({ at: +(e.at / 1000).toFixed(2), kind: e.kind, ...Object.fromEntries(Object.entries(e).filter(([k, v]) => !['t', 'at', 'kind'].includes(k) && v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0))) }))
  // ---- clean up every process this script started, and every throwaway directory
  try {
    await getJson(`http://127.0.0.1:${EXT_PORT}/coach/clear`, { method: 'POST' }).catch(() => undefined)
    await context?.close().catch(() => undefined)
    await analysisBrowser?.close().catch(() => undefined)
    await stop('electron')
    // The app was started through electron-lock.sh; make sure no Electron of this checkout is left (the lock is ours while we run).
    await new Promise((r) => spawn('pkill', ['-f', `${app}/node_modules/electron/dist`], { stdio: 'ignore' }).on('close', r))
    await stop('engine')
    if (holderLocked) for (const p of SITES) await getJson(`http://127.0.0.1:${p}/__reset`, { method: 'POST' }).catch(() => undefined)
    const h = children.get('sandbox-lock')
    if (h && alive(h)) {
      h.stdin.end()
      await Promise.race([new Promise((r) => h.once('exit', r)), sleep(3000)])
      await stop('sandbox-lock')
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
    out.cleanup = { throwawayDirRemoved: !existsSync(root), processesLeft: [...children].filter(([, p]) => alive(p)).map(([n]) => n) }
  }
}
console.log(JSON.stringify(out, null, 2))
process.exit(out.ok ? 0 : 1)
