import path from 'node:path'
import { chromium } from 'playwright-core'
import { REPO } from './harness.mjs'
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--mute-audio'] })
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } })
const errs = []
page.on('pageerror', (e) => errs.push(e.message))
await page.goto('file://' + path.join(REPO, 'tools/voice-audition.html'))
const cards = await page.locator('.card').count()
await page.locator('.card', { hasText: 'Charon' }).getByRole('button', { name: 'Play' }).click()
await page.waitForTimeout(1500)
const playing = await page.locator('.card.playing').count()
const missing = await page.locator('.missing').allTextContents()
await page.locator('.card', { hasText: 'Charon' }).getByRole('button', { name: 'Use for Marcus' }).click()
await page.locator('.card', { hasText: 'Sulafat' }).getByRole('button', { name: 'Use for Amelia' }).click()
const picks = [await page.locator('#pickM').textContent(), await page.locator('#pickF').textContent()]
// every wav is reachable and decodes
const durations = await page.evaluate(async () => {
  const names = [...document.querySelectorAll('.card .name span:first-child')].map((n) => n.textContent)
  const out = {}
  await Promise.all(names.map((n) => new Promise((res) => { const a = new Audio('voice-audition/' + n + '.wav'); a.onloadedmetadata = () => { out[n] = +a.duration.toFixed(1); res() }; a.onerror = () => { out[n] = -1; res() } })))
  return out
})
await page.screenshot({ path: path.join(REPO, 'spikes/live/out/audition.png') })
console.log(JSON.stringify({ cards, playing, missing: missing.filter(Boolean), picks, errs, bad: Object.entries(durations).filter(([, d]) => d < 2), min: Math.min(...Object.values(durations)), max: Math.max(...Object.values(durations)) }))
await browser.close()
