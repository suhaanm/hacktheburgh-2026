#!/usr/bin/env node
// COA-2 calibration: does the ring land on the real element? Opens a real, headed Chromium window with the Understudy extension,
// runs the built desktop app (overlay capturable, engine and agent pointed at dead ports so nothing real is touched), asks for a
// ring on a bright magenta button with POST /coach/ring, grabs ONE screen frame from the app's own capture service, and measures
// in that frame (in memory; nothing is saved) how the ring sits around the magenta element:
//   dx = (left gap - right gap) / 2     dy = (top gap - bottom gap) / 2     in screen points; 0 means perfectly centred.
// Then it scrolls the page programmatically (window.scrollTo inside the test page, no OS input) and measures again.
// Needs: npm run build here, the extension built in ../../extension/dist, Playwright Chromium, and Screen Recording granted to the
// app (checked first; it never prompts). Run: node scripts/calibrate-ring.mjs
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = dirname(fileURLToPath(import.meta.url))
const app = resolve(here, '..')
const dist = resolve(app, '../../extension/dist')
if (!existsSync(join(dist, 'manifest.json'))) throw new Error('build the extension first (extension/dist)')
const EXT_PORT = 7731
const DEBUG_PORT = 7787
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const until = async (cond, ms, label) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) {
    if (await cond()) return
    await sleep(150)
  }
  throw new Error(`timed out waiting for ${label}`)
}

const PAGE = `<!doctype html><meta charset="utf-8"><title>calibration</title>
<body style="margin:0;height:4000px;background:#ffffff;font:16px system-ui">
<button id="target" style="position:absolute;left:260px;top:300px;width:300px;height:110px;background:#ff00ff;border:0;border-radius:0;color:#fff;font-size:20px">Calibrate</button>
<button id="below" style="position:absolute;left:260px;top:1900px;width:300px;height:110px;background:#ff00ff;border:0;border-radius:0;color:#fff;font-size:20px">Far below</button>
</body>`
const pageServer = createServer((_req, res) => res.writeHead(200, { 'content-type': 'text/html' }).end(PAGE))
await new Promise((r) => pageServer.listen(0, '127.0.0.1', r))
const pagePort = pageServer.address().port

const userData = mkdtempSync(join(tmpdir(), 'understudy-calib-app-'))
writeFileSync(join(userData, 'settings.json'), JSON.stringify({ onboardingDone: true, showDock: false }))
const chromeData = mkdtempSync(join(tmpdir(), 'understudy-calib-chrome-'))

const env = {
  ...process.env,
  OPENAI_API_KEY: '', // nothing here talks to a model
  UNDERSTUDY_ENGINE_URL: 'http://127.0.0.1:9',
  UNDERSTUDY_AGENT_URL: 'http://127.0.0.1:9',
  UNDERSTUDY_EXT_PORT: String(EXT_PORT),
  ALONGSIDE_USERDATA: userData,
  ALONGSIDE_OVERLAY_CAPTURABLE: '1',
  ALONGSIDE_ACTUATOR_DRYRUN: '1',
  ALONGSIDE_AGENCY_LOOP: '0',
  ALONGSIDE_DEBUG_PORT: String(DEBUG_PORT),
  ALONGSIDE_LOCK_MAX_SECONDS: '200',
}
delete env.ALONGSIDE_MOCK
delete env.UNDERSTUDY_MOCK
const electron = spawn('bash', ['scripts/electron-lock.sh', 'calibrate', 'node_modules/.bin/electron', '.'], { cwd: app, env, stdio: ['ignore', 'pipe', 'pipe'] })
let electronLog = ''
electron.stdout.on('data', (d) => (electronLog += d))
electron.stderr.on('data', (d) => (electronLog += d))

const out = { ok: false }
let context
try {
  await until(async () => (await fetch(`http://127.0.0.1:${DEBUG_PORT}/health`).then((r) => r.ok).catch(() => false)), 40000, 'the app')
  await until(async () => (await fetch(`http://127.0.0.1:${EXT_PORT}/ext/status`).then((r) => r.ok).catch(() => false)), 10000, 'the extension server')

  context = await chromium.launchPersistentContext(chromeData, {
    headless: false,
    viewport: null,
    args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`, '--no-first-run', '--no-default-browser-check', '--window-position=140,90', '--window-size=1000,720'],
  })
  let [sw] = context.serviceWorkers()
  if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 15000 })
  await until(() => sw.evaluate(async () => Boolean((await chrome.storage.local.get('salt')).salt)), 10000, 'extension init')
  await sw.evaluate(async ({ ext }) => {
    await chrome.storage.local.set({ config: { capturing: true, person: 'p_calib001', role: 'benefits-processor', engine_url: 'http://127.0.0.1:9', desktop_url: `http://127.0.0.1:${ext}` } })
  }, { ext: EXT_PORT })
  const page = context.pages()[0] ?? (await context.newPage())
  await page.goto(`http://127.0.0.1:${pagePort}/`)
  await page.bringToFront()
  await sleep(1500)

  const geometry = await page.evaluate(() => ({ screenX, screenY, outerW: outerWidth, outerH: outerHeight, innerW: innerWidth, innerH: innerHeight, dpr: devicePixelRatio, screenW: screen.width, screenH: screen.height }))
  out.window = geometry

  // The pixel analysis runs inside Chromium (it can decode the JPEG); only numbers come back.
  const analyse = async (jpegBase64, displayW) => {
    const dataUrl = `data:image/jpeg;base64,${jpegBase64}`
    return page.evaluate(
      async ({ dataUrl, displayW }) => {
        const img = new Image()
        img.src = dataUrl
        await img.decode()
        const c = document.createElement('canvas')
        c.width = img.naturalWidth
        c.height = img.naturalHeight
        const g = c.getContext('2d', { willReadFrequently: true })
        g.drawImage(img, 0, 0)
        const { data, width, height } = g.getImageData(0, 0, c.width, c.height)
        const box = (pred, within) => {
          let x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1, n = 0
          const [ax, ay, bx, by] = within ?? [0, 0, width, height]
          for (let y = Math.floor(Math.max(0, ay)); y < Math.min(height, Math.ceil(by)); y++)
            for (let x = Math.floor(Math.max(0, ax)); x < Math.min(width, Math.ceil(bx)); x++) {
              const i = (y * width + x) * 4
              if (pred(data[i], data[i + 1], data[i + 2])) {
                n++
                if (x < x0) x0 = x
                if (x > x1) x1 = x
                if (y < y0) y0 = y
                if (y > y1) y1 = y
              }
            }
          return n > 50 ? { x0, y0, x1, y1, n } : null
        }
        const scale = width / displayW // image px per point
        const magenta = box((r, g, b) => r > 215 && g < 70 && b > 215)
        // Only look for the ring close to the element: the rest of the screen has plenty of blue.
        const pad = 45 * scale
        const near = magenta ? [magenta.x0 - pad, magenta.y0 - pad, magenta.x1 + pad, magenta.y1 + pad] : null
        // The ring (dark casing and blue core) is the only thing near the test button that is neither white page nor the magenta element.
        const ring = near ? box((r, g, b) => 0.299 * r + 0.587 * g + 0.114 * b < 200 && !(r > 150 && b > 150 && g < 120), near) : null
        // Optional: a small crop around the element (only the test page, never the rest of the screen) to look at.
        let crop = null
        if (magenta && globalThis.__wantCrop) {
          const cw = Math.round(magenta.x1 - magenta.x0 + 2 * pad)
          const ch = Math.round(magenta.y1 - magenta.y0 + 2 * pad)
          const cc = document.createElement('canvas')
          cc.width = cw
          cc.height = ch
          cc.getContext('2d').drawImage(c, magenta.x0 - pad, magenta.y0 - pad, cw, ch, 0, 0, cw, ch)
          crop = cc.toDataURL('image/png')
        }
        return { scale, width, height, magenta, ring, crop }
      },
      { dataUrl, displayW },
    )
  }
  const predicted = (name) =>
    page.evaluate((name) => {
      const el = [...document.querySelectorAll('button')].find((b) => b.textContent === name)
      const r = el.getBoundingClientRect()
      // The extension's own recipe for where the viewport sits on the screen: screenX/Y plus the browser chrome above the page.
      return { x: screenX + r.left, y: screenY + (outerHeight - innerHeight) + r.top, w: r.width, h: r.height }
    }, name)
  const measure = async (label, name) => {
    const jpeg = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/shot?purpose=live`)).arrayBuffer()
    const display = 1728
    await page.evaluate((v) => (globalThis.__wantCrop = v), Boolean(process.env.CALIB_CROP_DIR))
    const r = await analyse(Buffer.from(jpeg).toString('base64'), display)
    if (r.crop && process.env.CALIB_CROP_DIR) writeFileSync(join(process.env.CALIB_CROP_DIR, `crop-${label.replace(/\W+/g, '-')}.png`), Buffer.from(r.crop.split(',')[1], 'base64'))
    if (!r.magenta) return { label, error: 'the magenta element was not found in the frame (is the window visible and unobstructed?)' }
    if (!r.ring) return { label, error: 'no ring pixels found in the frame', magenta: r.magenta }
    const s = r.scale
    const m = r.magenta
    const k = r.ring
    const gaps = { left: (m.x0 - k.x0) / s, right: (k.x1 - m.x1) / s, top: (m.y0 - k.y0) / s, bottom: (k.y1 - m.y1) / s }
    const want = await predicted(name)
    const cx = (m.x0 + m.x1) / 2 / s
    const cy = (m.y0 + m.y1) / 2 / s
    return {
      label,
      predictedFromDomPoints: { x: +want.x.toFixed(1), y: +want.y.toFixed(1), w: want.w, h: want.h },
      elementCentreErrorPoints: { dx: +(cx - (want.x + want.w / 2)).toFixed(1), dy: +(cy - (want.y + want.h / 2)).toFixed(1) },
      imagePxPerPoint: +s.toFixed(3),
      elementPoints: { x: +(m.x0 / s).toFixed(1), y: +(m.y0 / s).toFixed(1), w: +((m.x1 - m.x0) / s).toFixed(1), h: +((m.y1 - m.y0) / s).toFixed(1) },
      gapsPoints: Object.fromEntries(Object.entries(gaps).map(([a, b]) => [a, +b.toFixed(1)])),
      dxPoints: +((gaps.left - gaps.right) / 2).toFixed(1),
      dyPoints: +((gaps.top - gaps.bottom) / 2).toFixed(1),
    }
  }
  const ring = async (name) => {
    const r = await fetch(`http://127.0.0.1:${EXT_PORT}/coach/ring`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ role: 'button', name }) })
    if (!r.ok) throw new Error(`ring request refused (${r.status})`)
  }
  const dom = async () => (await fetch(`http://127.0.0.1:${DEBUG_PORT}/dom`).then((r) => r.json()))

  await ring('Calibrate')
  await until(async () => (await dom()).ring?.visible === true, 15000, 'the ring to be drawn')
  await sleep(1500) // let the ring finish easing in
  out.top = await measure('element at the top of the page', 'Calibrate')
  out.dom = await dom()

  await page.evaluate(() => window.scrollTo(0, 1700))
  await ring('Far below')
  await until(async () => (await dom()).ring?.visible === true, 15000, 'the ring on the scrolled element')
  await sleep(1500)
  out.scrolled = await measure('after scrolling, a different element', 'Far below')

  // Scroll away again: the ring must follow the page, then hide when the element leaves the viewport.
  await page.evaluate(() => window.scrollTo(0, 0))
  await until(async () => (await dom()).ring?.visible === false, 10000, 'the ring to hide when its element left the view')
  out.hid_when_scrolled_out = (await dom()).ring?.hiddenFor ?? null
  out.ok = !out.top.error && !out.scrolled.error
} catch (e) {
  out.error = String(e?.stack ?? e)
  out.electronLogTail = electronLog.split('\n').slice(-12).join('\n')
} finally {
  await context?.close().catch(() => {})
  await fetch(`http://127.0.0.1:${EXT_PORT}/coach/clear`, { method: 'POST' }).catch(() => {})
  electron.kill('SIGTERM')
  await sleep(500)
  spawn('pkill', ['-f', `${app}/node_modules/electron/dist`], { stdio: 'ignore' })
  pageServer.close()
  rmSync(userData, { recursive: true, force: true })
  rmSync(chromeData, { recursive: true, force: true })
}
console.log(JSON.stringify(out, null, 2))
process.exit(out.ok ? 0 : 1)
