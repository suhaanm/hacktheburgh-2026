#!/usr/bin/env node
// Looks at Cue in light and dark at 1440 by 900 and at 390 by 844, over the stand-in page, without Electron or the real screen.
// Builds nothing: run `node src/renderer/cue/harness/build.mjs` first (shoot.sh does both). Serves out/cue-harness over loopback, drives
// headless Chromium (playwright from the repo root) and writes one PNG per state, theme and size, plus layout checks printed to the console:
// the panel is inside the work area and never over the target.
// Usage: node shoot.mjs [--states a,b] [--themes light,dark] [--sizes 1440x900,390x844] [--out dir]
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '../../../..')
const arg = (k, d) => {
  const i = process.argv.indexOf(k)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d
}
const root = path.join(repo, 'out/cue-harness')
const out = path.resolve(arg('--out', path.join(here, 'shots')))
const themes = arg('--themes', 'light,dark').split(',')
const sizes = arg('--sizes', '1440x900,390x844').split(',').map((s) => s.split('x').map(Number))
fs.mkdirSync(out, { recursive: true })

const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff' }
const server = http.createServer((req, res) => {
  const file = path.join(root, decodeURIComponent((req.url ?? '/').split('?')[0]))
  const target = fs.existsSync(file) && fs.statSync(file).isDirectory() ? path.join(file, 'index.html') : file
  if (!target.startsWith(root) || !fs.existsSync(target)) return void res.writeHead(404).end()
  res.writeHead(200, { 'content-type': mime[path.extname(target)] ?? 'application/octet-stream' }).end(fs.readFileSync(target))
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const base = `http://127.0.0.1:${server.address().port}/index.html`

const browser = await chromium.launch()
let problems = 0
const probe = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
await probe.goto(`${base}?state=idle`)
await probe.waitForFunction(() => window.__cueStates)
const all = await probe.evaluate(() => window.__cueStates)
await probe.close()
const states = arg('--states', all.join(',')).split(',')

for (const [w, h] of sizes) {
  for (const theme of themes) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme, deviceScaleFactor: 1 })
    // The close-ups are taken at twice the pixels.
    const hiCtx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme, deviceScaleFactor: 2 })
    for (const state of states) {
      const page = await ctx.newPage()
      page.on('pageerror', (e) => console.error('pageerror:', e.message))
      page.on('console', (m) => m.type() === 'error' && console.error('console.error:', m.text()))
      await page.goto(`${base}?state=${state}&theme=${theme}&still=1`)
      await page.waitForFunction(() => window.__cueReady === true, null, { timeout: 8000 }).catch(() => console.error(`not ready: ${state} ${theme} ${w}x${h}`))
      const file = path.join(out, `${state}.${theme}.${w}x${h}.png`)
      await page.screenshot({ path: file })
      // A close-up of the ring, the chip or card and the room around them (read this one to judge the details).
      const clip = await page.evaluate(() => {
        const el = document.querySelector('[data-testid="cue-window"] .cue-layer:not([data-exiting="true"]) > *')
        const t = window.__cueDebug?.target
        const rs = []
        if (el) {
          const r = el.getBoundingClientRect()
          rs.push({ x: r.left, y: r.top, w: r.width, h: r.height })
        }
        if (t) rs.push(t)
        if (rs.length === 0) return null
        const x0 = Math.min(...rs.map((r) => r.x)) - 60
        const y0 = Math.min(...rs.map((r) => r.y)) - 50
        const x1 = Math.max(...rs.map((r) => r.x + r.w)) + 60
        const y1 = Math.max(...rs.map((r) => r.y + r.h)) + 50
        const X = Math.max(0, x0)
        const Y = Math.max(0, y0)
        return { x: X, y: Y, width: Math.min(window.innerWidth, x1) - X, height: Math.min(window.innerHeight, y1) - Y }
      })
      if (clip && (w >= 1000 || process.argv.includes('--crop-all'))) {
        const close = await hiCtx.newPage()
        await close.setViewportSize({ width: w, height: h })
        await close.goto(`${base}?state=${state}&theme=${theme}&still=1`)
        await close.waitForFunction(() => window.__cueReady === true, null, { timeout: 8000 }).catch(() => undefined)
        await close.screenshot({ path: path.join(out, `${state}.${theme}.${w}x${h}.crop.png`), clip })
        await close.close()
      }
      // Layout checks: the panel's own box (without its shadow room) is inside the work area and clear of the target.
      const check = await page.evaluate(() => {
        const el = document.querySelector('[data-testid="cue-window"] .cue-layer:not([data-exiting="true"]) > *')
        const dbg = window.__cueDebug
        if (!el) return { shown: false }
        const r = el.getBoundingClientRect()
        const t = dbg?.target
        const overlap = t ? Math.max(0, Math.min(r.right, t.x + t.w) - Math.max(r.left, t.x)) * Math.max(0, Math.min(r.bottom, t.y + t.h) - Math.max(r.top, t.y)) : 0
        const wk = dbg?.work
        const inside = wk ? r.left >= wk.x && r.top >= wk.y && r.right <= wk.x + wk.w && r.bottom <= wk.y + wk.h : true
        return { shown: true, w: Math.round(r.width), h: Math.round(r.height), overlap: Math.round(overlap), inside, hscroll: document.documentElement.scrollWidth > window.innerWidth + 1 }
      })
      const bad = check.shown && (check.overlap > 0 || !check.inside || check.hscroll)
      if (bad) problems += 1
      console.log(`${bad ? 'PROBLEM ' : ''}${path.relative(repo, file)} ${JSON.stringify(check)}`)
      await page.close()
    }
    await ctx.close()
    await hiCtx.close()
  }
}
await browser.close()
server.close()
if (problems) {
  console.error(`${problems} layout problem(s)`)
  process.exitCode = 1
}
