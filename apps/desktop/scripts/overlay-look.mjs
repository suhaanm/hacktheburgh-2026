#!/usr/bin/env node
// Look at the real overlay without saving anything of the person's screen. Runs the built app (engine and agent pointed at dead
// ports), a headed Chromium with the extension (only for page zoom), and a test page on a local port, light and dark. The ring and
// its note are drawn by the app's real overlay window (POST /overlay on the debug server); the picture is put together from TWO
// captures that contain no desktop at all: the overlay window's own transparent capture (only what the overlay draws) and a
// Playwright screenshot of the test page (only the page). Crops around the element are composited in a headless page and written
// to LOOK_OUT as PNG, for looking at.
//   LOOK_SHAPE=old|new   old: ring + label + step badge + bubble (the first design);  new: ring + note (the Understudy look)
//   LOOK_OUT=<dir>       where the montages go (default: the OS temp dir)
// Run: node scripts/overlay-look.mjs
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { existsSync, mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = dirname(fileURLToPath(import.meta.url))
const app = resolve(here, '..')
const dist = resolve(app, '../../extension/dist')
const shape = process.env.LOOK_SHAPE ?? 'new'
const outDir = process.env.LOOK_OUT ?? tmpdir()
mkdirSync(outDir, { recursive: true })
const DEBUG_PORT = 7789
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const until = async (cond, ms, label) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) {
    if (await cond()) return
    await sleep(150)
  }
  throw new Error(`timed out waiting for ${label}`)
}
const MESSAGE = 'Check cliff edges before you reconcile the results.'

const PAGE = (dark) => `<!doctype html><meta charset="utf-8"><title>look</title>
<body style="margin:0;background:${dark ? '#0e1319' : '#ffffff'};color:${dark ? '#e7ebf1' : '#141922'};font:15px system-ui">
<div style="padding:40px 56px;max-width:760px">
<h1 style="font-size:22px;margin:0 0 8px">Your estimate</h1>
<p style="margin:0 0 16px;color:${dark ? '#9aa6b8' : '#566074'}">Estimated Universal Credit: <strong>£567</strong> a month. Reference GOV-E80161.</p>
<button id="a" style="font:inherit;padding:8px 14px;border:1px solid ${dark ? '#3a4859' : '#b8c1cf'};background:${dark ? '#161d26' : '#f4f6f9'};color:inherit;border-radius:4px">Save figures</button>
<button id="target" data-understudy-zone="cliff_button" style="font:inherit;padding:8px 14px;margin-left:12px;border:0;background:#00703c;color:#fff;border-radius:2px">Check cliff edges</button>
<button id="b" style="font:inherit;padding:8px 14px;margin-left:12px;border:1px solid ${dark ? '#3a4859' : '#b8c1cf'};background:${dark ? '#161d26' : '#f4f6f9'};color:inherit;border-radius:4px">Start again</button>
<p style="margin:28px 0 0;color:${dark ? '#9aa6b8' : '#566074'}">Is any figure close to a limit? What changes if it moves a little? Every household is different, so read each line.</p>
<table style="margin-top:14px;border-collapse:collapse;width:100%"><tr><th style="text-align:left;padding:6px;border-bottom:1px solid ${dark ? '#283341' : '#d8dee8'}">Item</th><th style="text-align:right;padding:6px;border-bottom:1px solid ${dark ? '#283341' : '#d8dee8'}">Monthly</th></tr>
<tr><td style="padding:6px">Standard allowance</td><td style="text-align:right;padding:6px">£368.74</td></tr><tr><td style="padding:6px">Child element</td><td style="text-align:right;padding:6px">£292.81</td></tr></table>
</div></body>`
const pageServer = createServer((req, res) => res.writeHead(200, { 'content-type': 'text/html' }).end(PAGE(req.url?.includes('dark'))))
await new Promise((r) => pageServer.listen(0, '127.0.0.1', r))
const pagePort = pageServer.address().port

const root = mkdtempSync(join(tmpdir(), 'understudy-look-'))
writeFileSync(join(root, 'settings.json'), JSON.stringify({ onboardingDone: true, showDock: false }))
const env = {
  ...process.env,
  OPENAI_API_KEY: '',
  UNDERSTUDY_ENGINE_URL: 'http://127.0.0.1:9',
  UNDERSTUDY_AGENT_URL: 'http://127.0.0.1:9',
  UNDERSTUDY_EXT_PORT: '7733',
  ALONGSIDE_USERDATA: root,
  ALONGSIDE_OVERLAY_CAPTURABLE: '1',
  ALONGSIDE_ACTUATOR_DRYRUN: '1',
  ALONGSIDE_AGENCY_LOOP: '0',
  ALONGSIDE_DEBUG_PORT: String(DEBUG_PORT),
  ALONGSIDE_LOCK_MAX_SECONDS: '400',
}
delete env.ALONGSIDE_MOCK
delete env.UNDERSTUDY_MOCK
delete env.UNDERSTUDY_REAL_ACTUATOR
const electron = spawn('bash', ['scripts/electron-lock.sh', 'look', 'node_modules/.bin/electron', '.'], { cwd: app, env, stdio: ['ignore', 'pipe', 'pipe'] })
let log = ''
electron.stdout.on('data', (d) => (log += d))
electron.stderr.on('data', (d) => (log += d))
const api = (path, init) => fetch(`http://127.0.0.1:${DEBUG_PORT}${path}`, init)
const post = (path, body) => api(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })

const out = { shape, files: [] }
let context
let analysis
try {
  await until(async () => (await api('/health').then((r) => r.ok).catch(() => false)), 60000, 'the app')
  context = await chromium.launchPersistentContext(join(root, 'chrome'), {
    headless: false,
    viewport: null,
    args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`, '--no-first-run', '--no-default-browser-check', '--window-position=140,90', '--window-size=1000,720'],
  })
  let [sw] = context.serviceWorkers()
  if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 20000 })
  const page = context.pages()[0] ?? (await context.newPage())
  analysis = await (await chromium.launch({ headless: true })).newPage()
  await analysis.goto('about:blank')
  const geo = async () => page.evaluate(() => ({ dpr: devicePixelRatio, screenW: screen.width, screenH: screen.height, screenX, screenY, outerW: outerWidth, outerH: outerHeight, innerW: innerWidth, innerH: innerHeight }))
  await page.goto(`http://127.0.0.1:${pagePort}/light`)
  const backing = (await geo()).dpr
  const tiles = []
  for (const zoom of [1, 1.25]) {
    for (const pageTheme of ['light', 'dark']) {
      for (const os of ['light', 'dark']) {
        await post('/theme', { mode: os })
        await page.goto(`http://127.0.0.1:${pagePort}/${pageTheme}`)
        await sw.evaluate(async (z) => {
          const tabs = await chrome.tabs.query({})
          const t = tabs.find((x) => (x.url ?? '').startsWith('http://127.0.0.1')) ?? tabs[0]
          await chrome.tabs.setZoom(t.id, z)
        }, zoom)
        await sleep(900)
        await page.bringToFront()
        const g = await geo()
        const z = g.dpr / backing
        const side = Math.max(0, (g.outerW - g.innerW * z) / 2)
        const chrome = Math.max(0, g.outerH - g.innerH * z - side)
        const r = await page.evaluate(() => {
          const b = document.getElementById('target').getBoundingClientRect()
          return { x: b.left, y: b.top, w: b.width, h: b.height }
        })
        const box = { x: g.screenX + side + r.x * z, y: g.screenY + chrome + r.y * z, w: r.w * z, h: r.h * z }
        const n = (v, total) => Math.round((v / total) * 1000)
        const nb = { xmin: n(box.x, g.screenW), ymin: n(box.y, g.screenH), xmax: n(box.x + box.w, g.screenW), ymax: n(box.y + box.h, g.screenH) }
        await post('/overlay', { cmd: { type: 'clear' } })
        await sleep(400)
        const annotations =
          shape === 'old'
            ? [
                { id: 'look-ring', kind: 'ring', tone: 'guide', box: nb, exact: true, label: 'Check cliff edges', step: 2 },
                { id: 'look-bubble', kind: 'bubble', tone: 'guide', at: { x: (nb.xmin + nb.xmax) / 2, y: nb.ymin }, text: MESSAGE },
              ]
            : [{ id: 'look-ring', kind: 'ring', tone: 'guide', box: nb, exact: true, step: 2, note: 'Check cliff edges' }]
        const res = await post('/overlay', { cmd: { type: 'show', annotations } })
        if (!res.ok) throw new Error(`overlay refused: ${await res.text()}`)
        await sleep(1700) // typed text and the entrance finish
        const overlay = Buffer.from(await (await api('/overlay.png')).arrayBuffer())
        const shot = await page.screenshot({ type: 'png' })
        tiles.push({ label: `page ${pageTheme}, overlay ${os}, zoom ${Math.round(zoom * 100)}%`, overlay: overlay.toString('base64'), shot: shot.toString('base64'), box, origin: { x: g.screenX + side, y: g.screenY + chrome }, screenW: g.screenW, backing })
      }
    }
  }
  await post('/overlay', { cmd: { type: 'clear' } })
  // The overlay's top-right corner (where the coach chip used to be) and the HUD (idle, hovered, stopped), for both themes.
  const extras = []
  for (const os of ['light', 'dark']) {
    await post('/theme', { mode: os })
    await sleep(1200)
    const overlay = Buffer.from(await (await api('/overlay.png')).arrayBuffer())
    const huds = {}
    // idle: the HUD window is hidden (nothing on the screen); an agent acting brings the Stop all pill up
    await post('/hud/preview', { mode: 'none' })
    await post('/hud/acting', { acting: false })
    await sleep(700)
    huds.idleVisible = (await api('/hud/visible').then((r) => r.json()).catch(() => ({}))).visible === true ? 'window visible' : 'window hidden'
    await post('/hud/acting', { acting: true })
    await sleep(900)
    huds.actingVisible = (await api('/hud/visible').then((r) => r.json()).catch(() => ({}))).visible === true ? 'window visible' : 'window hidden'
    huds.idle = Buffer.from(await (await api('/hud.png')).arrayBuffer()).toString('base64')
    await post('/hud/preview', { mode: 'hover' })
    await sleep(600)
    huds.hover = Buffer.from(await (await api('/hud.png')).arrayBuffer()).toString('base64')
    await post('/hud/preview', { mode: 'none' })
    await post('/hud/proposal', { proposal: null })
    await post('/kill', {})
    await sleep(1500)
    huds.stopped = Buffer.from(await (await api('/hud.png')).arrayBuffer()).toString('base64')
    await post('/kill/clear', {})
    await post('/hud/acting', { acting: false })
    await sleep(800)
    // the level-change toast (two seconds): captured while it is up
    await post('/overlay', { cmd: { type: 'chip', level: 2, label: 'Walk with me' } })
    await sleep(1100)
    const toast = Buffer.from(await (await api('/overlay.png')).arrayBuffer()).toString('base64')
    await sleep(2200)
    const toastGone = Buffer.from(await (await api('/overlay.png')).arrayBuffer()).toString('base64')
    extras.push({ os, overlay: overlay.toString('base64'), huds, toast, toastGone })
  }
  await post('/theme', { mode: 'system' })

  // ---- compose in a headless page: nothing but the overlay's own capture over the test page's own screenshot
  const compose = await analysis.evaluate(
    async ({ tiles, extras }) => {
      const load = (b64) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = 'data:image/png;base64,' + b64 })
      const tileCanvases = []
      for (const t of tiles) {
        const [ov, sh] = await Promise.all([load(t.overlay), load(t.shot)])
        const k = ov.naturalWidth / t.screenW // overlay px per point (= the screen's backing scale)
        const w = Math.round(480 * k), h = Math.round(170 * k)
        const cx = t.box.x - 90, cy = t.box.y - 70 // crop origin in points
        const c = document.createElement('canvas'); c.width = w; c.height = h
        const g = c.getContext('2d')
        g.fillStyle = '#888'; g.fillRect(0, 0, w, h)
        // the page screenshot has `backing` px per point and starts at the viewport origin
        g.drawImage(sh, 0, 0, sh.naturalWidth, sh.naturalHeight, (t.origin.x - cx) * k, (t.origin.y - cy) * k, (sh.naturalWidth / t.backing) * k, (sh.naturalHeight / t.backing) * k)
        g.drawImage(ov, cx * k, cy * k, w, h, 0, 0, w, h)
        g.font = `${11 * k}px system-ui`; g.fillStyle = '#c0392b'; g.fillText(t.label, 6 * k, 12 * k)
        tileCanvases.push(c)
      }
      const montage = (cs, cols) => {
        const w = cs[0].width, h = cs[0].height
        const rows = Math.ceil(cs.length / cols)
        const m = document.createElement('canvas'); m.width = w * cols + (cols - 1) * 6; m.height = h * rows + (rows - 1) * 6
        const g = m.getContext('2d'); g.fillStyle = '#444'; g.fillRect(0, 0, m.width, m.height)
        cs.forEach((c, i) => g.drawImage(c, (i % cols) * (w + 6), Math.floor(i / cols) * (h + 6)))
        return m.toDataURL('image/png')
      }
      const out = { zoom100: montage(tileCanvases.slice(0, 4), 2), zoom125: montage(tileCanvases.slice(4), 2) }
      // chip corner: the overlay's top-right region on a light and on a dark synthetic page (no screen content involved)
      const chips = []
      for (const e of extras) {
        const ov = await load(e.overlay)
        const k = ov.naturalWidth / (ov.naturalWidth / (ov.naturalWidth > 3000 ? 2 : 2))
        const w = Math.round(ov.naturalWidth * 0.28), h = Math.round(ov.naturalHeight * 0.1)
        const tw = Math.round(ov.naturalWidth * 0.34), x0 = Math.round((ov.naturalWidth - tw) / 2)
        const tt = await load(e.toast), tg = await load(e.toastGone)
        for (const bg of ['#ffffff', '#0e1319']) {
          for (const [img, tag] of [[ov, 'top-right (the old chip place), no toast'], [tt, 'level toast, 1.1 s after the change'], [tg, 'toast 3.3 s after: gone']]) {
            const c = document.createElement('canvas'); c.width = tw; c.height = h
            const g = c.getContext('2d'); g.fillStyle = bg; g.fillRect(0, 0, tw, h)
            if (img === ov) g.drawImage(img, img.naturalWidth - tw, 0, tw, h, 0, 0, tw, h)
            else g.drawImage(img, x0, 0, tw, h, 0, 0, tw, h)
            g.font = '20px system-ui'; g.fillStyle = '#c0392b'; g.fillText(`${tag}, overlay ${e.os}, page ${bg === '#ffffff' ? 'light' : 'dark'}`, 10, 26)
            chips.push(c)
          }
        }
        void k
      }
      out.chips = montage(chips, 3)
      // the HUD window captures (its own pixels, on a light and on a dark page behind it): rows idle, hover, stopped
      const cells = []
      for (const state of ['idle', 'hover', 'stopped']) {
        for (const e of extras) {
          const hi = await load(e.huds[state])
          for (const bg of ['#ffffff', '#0e1319']) {
            const c = document.createElement('canvas'); c.width = hi.naturalWidth + 24; c.height = hi.naturalHeight + 24
            const g = c.getContext('2d'); g.fillStyle = bg; g.fillRect(0, 0, c.width, c.height); g.drawImage(hi, 12, 12)
            g.font = '18px system-ui'; g.fillStyle = '#c0392b'; g.fillText(`${state}, os ${e.os}`, 8, 20)
            cells.push(c)
          }
        }
      }
      const w = Math.max(...cells.map((c) => c.width)), h = Math.max(...cells.map((c) => c.height))
      const cols = 4, rows = Math.ceil(cells.length / cols)
      const m = document.createElement('canvas'); m.width = w * cols + (cols - 1) * 6; m.height = h * rows + (rows - 1) * 6
      const g = m.getContext('2d'); g.fillStyle = '#444'; g.fillRect(0, 0, m.width, m.height)
      cells.forEach((c, i) => g.drawImage(c, (i % cols) * (w + 6), Math.floor(i / cols) * (h + 6)))
      out.hud = m.toDataURL('image/png')
      return out
    },
    { tiles, extras },
  )
  for (const [name, url] of Object.entries(compose)) {
    if (!url) continue
    const file = join(outDir, `look-${shape}-${name}.png`)
    writeFileSync(file, Buffer.from(url.split(',')[1], 'base64'))
    out.files.push(file)
  }
  out.hudWindowWhenIdle = extras.map((e) => `idle: ${e.huds.idleVisible}; acting: ${e.huds.actingVisible}`)
  out.ok = true
} catch (e) {
  out.error = String(e?.stack ?? e)
  out.logTail = log.split('\n').slice(-10).join('\n')
} finally {
  await context?.close().catch(() => {})
  await analysis?.context().browser()?.close().catch(() => {})
  electron.kill('SIGTERM')
  await sleep(600)
  spawn('pkill', ['-f', `${app}/node_modules/electron/dist`], { stdio: 'ignore' })
  pageServer.close()
  rmSync(root, { recursive: true, force: true })
}
console.log(JSON.stringify(out, null, 2))
process.exit(out.ok ? 0 : 1)
