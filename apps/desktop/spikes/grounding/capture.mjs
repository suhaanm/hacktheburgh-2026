// Captures benchmark screenshots + ground truth with playwright-core driving the local Google Chrome.
// usage: node capture.mjs [--stage <path-to-stage-index.html>]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';
import { SYNTH_SCREENS as BASE_SCREENS, HARD_SCREENS, REAL_SITES } from './targets.mjs';
const ONLY_HARD = process.argv.includes('--only-hard');
const SYNTH_SCREENS = ONLY_HARD ? HARD_SCREENS : { ...BASE_SCREENS, ...HARD_SCREENS };

const here = path.dirname(fileURLToPath(import.meta.url));
const shotsDir = path.join(here, 'shots');
fs.mkdirSync(shotsDir, { recursive: true });

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SIZES = [
  { w: 1440, h: 900 },
  { w: 1920, h: 1080 },
];

const manifest = []; // { shotId, file, w, h, screen, targets:[{desc, gt:{xmin..}|null, negative}] }
const browser = await chromium.launch({ executablePath: CHROME, headless: true });

async function shoot(page, shotId, w, h) {
  const file = path.join(shotsDir, shotId + '.png');
  await page.screenshot({ path: file, type: 'png' });
  return file;
}

// 1) synthetic screens at both sizes
const synthUrl = pathToFileURL(path.join(here, 'fixtures/synth.html')).href;
for (const size of SIZES) {
  const ctx = await browser.newContext({ viewport: { width: size.w, height: size.h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  for (const [screen, targets] of Object.entries(SYNTH_SCREENS)) {
    await page.goto(`${synthUrl}#${screen}`);
    await page.reload();
    await page.waitForTimeout(150);
    const rects = await page.evaluate(() => window.__rects());
    const shotId = `synth-${screen}@${size.w}x${size.h}`;
    const file = await shoot(page, shotId, size.w, size.h);
    manifest.push({
      shotId, file, w: size.w, h: size.h, screen, kind: 'synthetic',
      targets: targets.map((t) => ({ desc: t.desc, negative: !!t.negative, gt: t.negative ? null : rects[t.gid] ?? null, gid: t.gid ?? null })),
    });
    for (const t of targets) if (!t.negative && !rects[t.gid]) console.warn('missing gid', screen, t.gid);
  }
  await ctx.close();
}

// 2) real sites (1440x900 only)
for (const site of ONLY_HARD ? [] : REAL_SITES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: 'en-GB' });
  const page = await ctx.newPage();
  try {
    await page.goto(site.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2500);
    // dismiss cookie banners by declining where obvious; harmless if absent
    for (const sel of ['button:has-text("Reject additional cookies")', 'button:has-text("Reject all")', 'button:has-text("No, thanks")']) {
      const el = page.locator(sel).first();
      if (await el.count().catch(() => 0)) { await el.click({ timeout: 1500 }).catch(() => {}); await page.waitForTimeout(500); }
    }
    const targets = [];
    for (const t of site.targets) {
      if (t.negative) { targets.push({ desc: t.desc, negative: true, gt: null, gid: null }); continue; }
      const gt = await page.evaluate((sel) => {
        const el = [...document.querySelectorAll(sel)].find((e) => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; });
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { xmin: Math.round(r.left / innerWidth * 1000), ymin: Math.round(r.top / innerHeight * 1000), xmax: Math.round(r.right / innerWidth * 1000), ymax: Math.round(r.bottom / innerHeight * 1000) };
      }, t.selector);
      if (gt) targets.push({ desc: t.desc, negative: false, gt, gid: t.selector });
      else console.warn('no visible element for', site.id, t.selector);
    }
    const shotId = `${site.id}@1440x900`;
    const file = await shoot(page, shotId, 1440, 900);
    manifest.push({ shotId, file, w: 1440, h: 900, screen: site.id, kind: 'real', targets });
  } catch (e) {
    console.warn('skip', site.id, String(e.message).slice(0, 120));
  }
  await ctx.close();
}

await browser.close();
const mf = path.join(shotsDir, ONLY_HARD ? 'manifest-hard.json' : 'manifest.json');
fs.writeFileSync(mf, JSON.stringify(manifest, null, 2));
const n = manifest.reduce((a, m) => a + m.targets.length, 0);
console.log(`shots=${manifest.length} targets=${n} negatives=${manifest.reduce((a, m) => a + m.targets.filter((t) => t.negative).length, 0)}`);
