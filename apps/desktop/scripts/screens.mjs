#!/usr/bin/env node
// Looks at the desktop's own screens (the panel in each tab, the pill, the confirmation toast) rendered, light and dark, at 1440x900
// and 390x844. A Vite dev server serves src/renderer/design/shots.html (the harness with the app's real components and canned state),
// Playwright takes the screenshots into SCREENS_OUT. Nothing here touches the desktop or the real app.
//   SCREENS_TAG=before|after   file name prefix       SCREENS_OUT=<dir>
import { mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { chromium } from 'playwright'
import { createServer } from 'vite'

const here = dirname(fileURLToPath(import.meta.url))
const app = resolve(here, '..')
const out = process.env.SCREENS_OUT ?? tmpdir()
const tag = process.env.SCREENS_TAG ?? 'screens'
mkdirSync(out, { recursive: true })

const server = await createServer({ root: join(app, 'src/renderer'), configFile: false, plugins: [react()], logLevel: 'error', server: { port: 5188, strictPort: false, fs: { strict: false } } })
await server.listen()
const base = server.resolvedUrls?.local[0] ?? 'http://localhost:5188/'
const browser = await chromium.launch({ headless: true })
const files = []
try {
  for (const theme of ['light', 'dark']) {
    for (const [w, h] of [[1440, 900], [390, 844]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, colorScheme: theme })
      const page = await ctx.newPage()
      const errors = []
      page.on('pageerror', (e) => errors.push(String(e)))
      await page.goto(`${base}design/shots.html?theme=${theme}&glass=0`)
      await page.waitForSelector('#shots .al-dock')
      await page.waitForTimeout(900)
      const file = join(out, `${tag}-${theme}-${w}x${h}.png`)
      await page.locator('#shots').screenshot({ path: file })
      files.push(file)
      if (errors.length) console.log(`page errors (${theme} ${w}x${h}):`, errors.slice(0, 3))
      await ctx.close()
    }
  }
} finally {
  await browser.close()
  await server.close()
}
console.log(JSON.stringify(files, null, 2))
