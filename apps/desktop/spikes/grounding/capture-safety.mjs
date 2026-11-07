// Renders fixtures/safety/injection.html screens to JPEGs (+ ground truth for the real buttons). Output: shots/safety/
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, 'shots/safety');
fs.mkdirSync(out, { recursive: true });
const url = pathToFileURL(path.join(here, '../../fixtures/safety/injection.html')).href;
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const manifest = {};
for (const id of ['scam-inject', 'markers', 'hidden', 'hidden-scam', 'lookalike']) {
  await page.goto(`${url}#${id}`); await page.reload(); await page.waitForTimeout(300);
  const png = path.join(out, `${id}.png`);
  await page.screenshot({ path: png });
  execFileSync('sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '80', png, '--out', path.join(out, `${id}.jpg`)], { stdio: 'ignore' });
  manifest[id] = await page.evaluate(() => window.__gt());
}
await browser.close();
fs.writeFileSync(path.join(out, 'manifest.json'), JSON.stringify(manifest, null, 1));
console.log(JSON.stringify(manifest));
