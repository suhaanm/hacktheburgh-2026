// Track C screenshots: Needs you, Routines, Your data, Settings, light and dark, at 1440x900, 1152x735 and 390x844.
// Usage (from apps/dashboard, own dev server): node qa/knack/shoot-c.mjs [base=http://127.0.0.1:5192] [outdir=qa/knack] [filter]
// Example data mode on purpose: every engine and agent request is refused, so nothing is read from or written to a live service.
import { chromium } from "playwright";
import fs from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:5192";
const out = process.argv[3] ?? "qa/knack";
const only = process.argv[4];
fs.mkdirSync(out, { recursive: true });
const SHOTS = [
  ["needs-you", "/needs-you"],
  ["needs-you-more", "/needs-you", async (p) => { await p.getByRole("button", { name: "More ways to say yes" }).first().click(); await p.getByRole("button", { name: "Evidence" }).first().click(); }],
  ["routines", "/routines"],
  ["routines-open", "/routines", async (p) => { await p.locator(".rt-row__open").first().click(); }],
  ["routines-could", "/routines?tab=could-automate"],
  ["your-data", "/your-data"],
  ["your-data-sent", "/your-data?section=sent"],
  ["your-data-delete", "/your-data?section=switches", async (p) => { await p.getByRole("button", { name: "Delete everything" }).click(); }],
  ["agents", "/agents"],
  ["agents-open", "/agents", async (p) => { await p.locator("summary", { hasText: "Helpers and result" }).first().click(); }],
  ["models", "/models"],
  ["settings", "/home?settings=live-models"],
  ["settings-interruptions", "/home?settings=interruptions"],
];
const SIZES = [["1440", 1440, 900], ["1152", 1152, 735], ["390", 390, 844]].filter(([sz]) => !process.env.SIZES || process.env.SIZES.split(",").includes(sz));
const browser = await chromium.launch();
for (const theme of (process.env.THEMES ?? "light,dark").split(",")) {
  for (const [sz, w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme });
    await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const [name, path, act] of SHOTS) {
      if (only && !name.includes(only)) continue;
      await page.goto(`${base}/#${path}`);
      await page.waitForTimeout(900);
      try { if (act) { await act(page); await page.waitForTimeout(300); } } catch (e) { console.log(`  (${name}: step skipped: ${String(e).slice(0, 80)})`); }
      await page.screenshot({ path: `${out}/${name}-${theme}-${sz}.png` });
    }
    if (errors.length) console.log(`page errors at ${sz} ${theme}: ${errors.slice(0, 3).join(" | ")}`);
    await ctx.close();
  }
}
await browser.close();
console.log("done");
