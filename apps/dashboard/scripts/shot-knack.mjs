// Screenshots of chosen screens for the Knack look check: light and dark, at 1440x900, 1152x735 and 390x844, into qa/knack/ (do not commit large PNGs).
// Read-only (every non-GET request refused); --example blocks the engine and agent so the shots are deterministic.
// Usage (from apps/dashboard):  node scripts/shot-knack.mjs <base> <route[,route...]> [--view=worker|admin] [--sizes=1440x900,1152x735,390x844] [--themes=light,dark] [--example] [--full] [--open="Details summary text"] [--click="row text"]
import { chromium } from "playwright";
import fs from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { openAs } from "./lib/knack-page.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const base = (args.find((a) => /^https?:/.test(a)) ?? "http://127.0.0.1:5193").replace(/\/$/, "");
const routes = (args.find((a) => !/^https?:/.test(a) && !a.startsWith("--")) ?? "growth").split(",");
const opt = (n, d) => { const a = args.find((x) => x.startsWith(`--${n}=`)); return a ? a.slice(n.length + 3) : d; };
const view = opt("view", "worker");
const sizes = opt("sizes", "1440x900,1152x735,390x844").split(",").map((s) => s.split("x").map(Number));
const themes = opt("themes", "light,dark").split(",");
const example = args.includes("--example");
const full = args.includes("--full");
const open = opt("open", "");
const click = opt("click", "");
const outDir = join(here, "..", "qa", "knack");
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
for (const theme of themes) {
  for (const [w, h] of sizes) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme });
    await ctx.route("**/*", (r) => {
      const req = r.request();
      if (!["GET", "HEAD"].includes(req.method())) return r.abort();
      if (example && /^https?:\/\/[^/]+\/(engine|agent)(\/|$)/.test(req.url())) return r.abort();
      return r.continue();
    });
    const page = await ctx.newPage();
    if (!(await openAs(page, base, view))) { console.log(`could not open the ${view} view at ${w}x${h}`); await ctx.close(); continue; }
    for (const r of routes) {
      await page.evaluate((x) => { location.hash = x; }, `#/${r}`);
      await page.waitForTimeout(r === "graph" ? 2200 : 1400);
      if (open) { for (const t of open.split("|")) { const s = page.locator("summary", { hasText: t }).first(); if (await s.count()) await s.click(); } await page.waitForTimeout(300); }
      if (click) { for (const t of click.split("|")) { const b = page.locator("button.listrow", { hasText: t }).first(); if (await b.count()) await b.click(); } await page.waitForTimeout(500); }
      const file = join(outDir, `${r.replace(/[\/?=]/g, "-")}-${view}-${theme}-${w}x${h}.png`);
      await page.screenshot({ path: file, fullPage: full });
      console.log(file);
    }
    await ctx.close();
  }
}
await browser.close();
