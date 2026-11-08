// Screenshots of the shell's open states: account menu, More, Settings, first run (three screens), the admin gate. Example data only (engine and agent blocked).
// node scripts/shot-shell-states.mjs [base=http://127.0.0.1:5191] [outDir=qa/knack]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://127.0.0.1:5191";
const out = process.argv[3] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const [theme, tag, width, height] of [["light", "win", 1152, 735], ["dark", "win", 1152, 735], ["light", "m390", 390, 844], ["dark", "m390", 390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.addInitScript((t) => { try { localStorage.setItem("understudy-theme", t); localStorage.setItem("understudy-first-run-done", new Date().toISOString()); } catch { /* */ } }, theme);
  const shot = async (name) => { await page.waitForTimeout(500); await page.screenshot({ path: join(out, `${name}-${theme}-${tag}.png`) }); console.log(`${name}-${theme}-${tag}.png`); };
  const mobile = width < 881;
  await page.goto(`${base}/#/home`); await page.waitForTimeout(900);
  // account menu
  await page.getByRole("button", { name: /^Account/ }).first().click(); await shot("menu-account");
  await page.keyboard.press("Escape");
  // More
  await page.getByRole("button", { name: "More" }).first().click(); await shot("menu-more");
  await page.keyboard.press("Escape");
  // Settings sheet
  await page.keyboard.press("Meta+,"); await shot("settings-sheet");
  await page.keyboard.press("Escape");
  // palette, then a phrase, then About this screen, then the tour
  await page.keyboard.press("Meta+k"); await shot("palette");
  await page.keyboard.type("explain"); await shot("palette-query");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Meta+/"); await shot("about-panel");
  await page.keyboard.press("Escape");
  // admin gate (worker view), then admin view
  await page.goto(`${base}/#/roles`); await shot("admin-gate");
  // first run: three screens
  await page.goto(`${base}/#/first-run`); await shot("first-run-1");
  await page.locator(".rolecard").first().click(); await shot("first-run-2");
  await page.getByRole("button", { name: "Not now" }).click(); await shot("first-run-3");
  if (!mobile) {
    for (const r of ["needs-you", "routines", "growth", "your-data", "genome"]) { await page.goto(`${base}/#/${r}`); await shot(r); }
  }
  await ctx.close();
}
await browser.close();
