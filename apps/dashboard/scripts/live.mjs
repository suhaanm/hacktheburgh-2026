// Read-only check of every screen against the live engine (through the dashboard's /engine and /agent proxy). Makes only GET requests.
// Usage: node scripts/live.mjs [http://127.0.0.1:5173]   Screenshots go to qa/live-*.png
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const qa = join(dirname(fileURLToPath(import.meta.url)), "..", "qa");
const screens = ["genome", "presence", "routines", "queue", "graph", "today", "memory", "evidence", "onboarding"];
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errors = [];
const missing = new Map();
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`); });
page.on("response", (r) => { const u = new URL(r.url()); if (/^\/(engine|agent)\//.test(u.pathname) && r.status() >= 400) missing.set(`${r.request().method()} ${u.pathname} ${r.status()}`, 1); });
page.on("request", (r) => { if (/^\/(engine|agent)\//.test(new URL(r.url()).pathname) && r.method() !== "GET") errors.push(`NON-GET to engine: ${r.method()} ${r.url()}`); });
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); if (!ok) failed++; };
for (const s of screens) {
  await page.goto(`${base}/#/${s}`);
  await page.waitForTimeout(s === "genome" ? 5000 : 1800);
  const note = (await page.locator(".datanote").innerText()).replace(/\n/g, " ");
  const empty = await page.locator(".state--error").count();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check(`${s}: renders without an error state`, empty === 0, note);
  check(`${s}: no horizontal overflow`, !overflow);
  await page.screenshot({ path: join(qa, `live-${s}-1440.png`) });
}
check("no page errors or non-GET requests", errors.length === 0, errors.slice(0, 4).join(" | "));
console.log("\nEngine answered with a status the dashboard falls back on:");
for (const k of missing.keys()) console.log("  ", k);
await browser.close();
process.exit(failed ? 1 : 0);
