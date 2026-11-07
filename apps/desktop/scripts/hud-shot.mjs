#!/usr/bin/env node
// Looks at the HUD (kill pill, proposal toast, stopped card) in light or dark without Electron or the screen:
// serves out/renderer over loopback, loads hud/index.html in headless Chromium (playwright from the repo root), stubs
// window.understudyHud with a fixed state and saves a PNG. Build first: npm run build.
// Usage: node scripts/hud-shot.mjs <pill|queue|proposal|stopped> <out.png> [--dark] [--scale 2]
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const [which, out, ...rest] = process.argv.slice(2)
if (!which || !out) {
  console.error('usage: hud-shot.mjs <pill|queue|proposal|stopped> <out.png> [--dark] [--scale N]')
  process.exit(2)
}
const dark = rest.includes('--dark')
const scale = Number(rest[rest.indexOf('--scale') + 1]) || 2
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../out/renderer')
const proposal = { id: 'calc-entry-3x', title: 'Enter the household into three calculators', what: 'You type the same household into three calculators, then copy the results into the case note.', howOften: 'about 14 times in 3 weeks', hoursSaved: [3.1, 5.2], horizonWeeks: 4, touches: ['gov.uk check', 'turn2us', 'case note'], never: ['submit'] }
const states = {
  pill: { kill: { killed: false, engine: null, agent: null }, queuePending: null, proposal: null },
  queue: { kill: { killed: false, engine: null, agent: null }, queuePending: 3, proposal: null },
  proposal: { kill: { killed: false, engine: null, agent: null }, queuePending: 2, proposal },
  stopped: { kill: { killed: true, engine: true, agent: false }, queuePending: 2, proposal: null },
}
const state = states[which]
if (!state) throw new Error(`unknown state ${which}`)

const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff' }
const server = http.createServer((req, res) => {
  const file = path.join(root, decodeURIComponent((req.url ?? '/').split('?')[0]))
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return void res.writeHead(404).end()
  res.writeHead(200, { 'content-type': mime[path.extname(file)] ?? 'application/octet-stream' }).end(fs.readFileSync(file))
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const port = server.address().port

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 380, height: 520 }, colorScheme: dark ? 'dark' : 'light', deviceScaleFactor: scale })
const page = await ctx.newPage()
page.on('pageerror', (e) => console.error('pageerror:', e.message))
await page.addInitScript((s) => {
  window.understudyHud = { get: async () => s, onState: () => () => undefined, action: (a) => console.log('action', JSON.stringify(a)) }
}, state)
await page.goto(`http://127.0.0.1:${port}/hud/index.html`, { waitUntil: 'networkidle' })
await page.waitForTimeout(400)
const card = await page.$('[data-hud-card]')
const box = await card.boundingBox()
await page.screenshot({ path: out, clip: { x: 0, y: 0, width: Math.ceil(box.x + box.width + 6), height: Math.ceil(box.y + box.height + 6) }, omitBackground: false })
console.log(`saved ${out} (${which}${dark ? ', dark' : ''}, ${Math.ceil(box.width)}x${Math.ceil(box.height)} css px)`)
await browser.close()
server.close()
