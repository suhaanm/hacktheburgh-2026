// Live sweep: every screen against the RUNNING engine and agent (nothing blocked), light theme, 1440 by 900.
// Reports per screen: page errors, console errors, failed service calls (status 400 or more, path only), and whether the screen fell back
// to example data (the "Showing example data" line or the Example data banner). Never prints response bodies.
// Usage: node scripts/live-sweep.mjs [base=http://127.0.0.1:5173]   Exit 1 if any screen throws.
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const WORKER = ["home", "growth", "repeats", "routines", "queue", "privacy", "genome", "presence", "graph", "week", "git", "predictions",
  "today", "memory", "notices", "onboarding", "briefing", "agents", "models", "evidence"];
const ADMIN = ["firm", "firm/roles", "firm/people", "firm/onboarding", "firm/automation", "firm/risk", "firm/forecasts", "firm/brief"];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
const page = await ctx.newPage();
let errors = [], consoleErrors = [], failed = [];
page.on("pageerror", (e) => errors.push(e.message.slice(0, 160)));
page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) consoleErrors.push(m.text().slice(0, 160)); });
page.on("response", (r) => {
  const u = new URL(r.url());
  if (/^\/(engine|agent)\//.test(u.pathname) && r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${u.pathname}`);
});

const rows = [];
async function visit(route) {
  errors = []; consoleErrors = []; failed = [];
  await page.evaluate((h) => { location.hash = h; }, `#/${route}`);
  await page.waitForTimeout(2200);
  const text = await page.evaluate(() => document.body.innerText);
  const example = /Showing example data|Example data|Some example data/.test(text);
  rows.push({ route, example, errors: [...new Set(errors)], consoleErrors: [...new Set(consoleErrors)], failed: [...new Set(failed)] });
}

await page.goto(`${base}/#/home`);
await page.waitForTimeout(2500);
for (const r of WORKER) await visit(r);
await page.locator(".viewas .segmented button", { hasText: "Admin" }).click();
for (const r of ADMIN) await visit(r);
await browser.close();

let bad = 0;
for (const r of rows) {
  const flags = [r.example ? "EXAMPLE-DATA" : "live", r.errors.length ? `PAGEERROR x${r.errors.length}` : "", r.consoleErrors.length ? `console x${r.consoleErrors.length}` : "", r.failed.length ? `calls: ${r.failed.join(", ")}` : ""].filter(Boolean);
  console.log(`${r.errors.length ? "FAIL" : "ok  "}  /${r.route.padEnd(18)} ${flags.join(" | ")}`);
  for (const e of r.errors) console.log(`        error: ${e}`);
  for (const e of r.consoleErrors.slice(0, 2)) console.log(`        console: ${e}`);
  if (r.errors.length) bad++;
}
console.log(`\n${rows.length} screens, ${rows.filter((r) => r.example).length} on example data, ${bad} with page errors`);
process.exit(bad ? 1 : 0);
