// Settings contents on their own (settings-preview.html), light and dark, at the sheet's width and at 390 by 844.
// Usage (from apps/dashboard, own dev server): node qa/knack/shoot-settings.mjs [base=http://127.0.0.1:5192] [outdir=qa/knack]
import { chromium } from "playwright";
import fs from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:5192";
const out = process.argv[3] ?? "qa/knack";
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const theme of ["light", "dark"]) {
  for (const [sz, w, h] of [["700", 700, 1100], ["390", 390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme });
    await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
    const page = await ctx.newPage();
    await page.goto(`${base}/settings-preview.html`);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/settings-${theme}-${sz}.png`, fullPage: true });
    await ctx.close();
  }
}
await browser.close();
console.log("done");
