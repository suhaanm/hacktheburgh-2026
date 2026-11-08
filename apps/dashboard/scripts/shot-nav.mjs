// Pictures of the navigation and the account menu: node scripts/shot-nav.mjs [base=http://127.0.0.1:5191] [outDir=qa/knack]
// The worker sidebar (five rows), the Admin sidebar (eight and More), the Admin gate sentence a worker sees, the Growth sections, and the account menu with
// its profile form, in light and dark at 1440 by 900, 1152 by 735 and 390 by 844. The engine and agent are blocked (example data); nothing is written.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://127.0.0.1:5191";
const out = process.argv[3] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");
mkdirSync(out, { recursive: true });
const SIZES = [["1440", 1440, 900], ["win", 1152, 735], ["m390", 390, 844]];

const browser = await chromium.launch();
for (const theme of ["light", "dark"]) for (const [tag, width, height] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.addInitScript((t) => { try { localStorage.setItem("understudy-theme", t); localStorage.setItem("understudy-first-run-done", new Date().toISOString()); localStorage.removeItem("understudy-view-as"); localStorage.removeItem("understudy-display-name"); } catch { /* */ } }, theme);
  const shot = async (name) => { await page.waitForTimeout(500); await page.screenshot({ path: join(out, `nav-${name}-${theme}-${tag}.png`) }); console.log(`nav-${name}-${theme}-${tag}.png`); };
  const account = page.locator("[data-account]:visible").first();

  await page.goto(`${base}/#/home`); await page.waitForTimeout(900);
  await shot("worker-home");
  await page.goto(`${base}/#/forecasts`); await page.waitForTimeout(500);
  await shot("worker-gate");
  await page.goto(`${base}/#/genome`); await page.waitForTimeout(1200);
  await shot("growth-steps");
  await page.goto(`${base}/#/home`); await page.waitForTimeout(600);
  await account.click();
  await shot("account-menu");
  await page.getByRole("menuitem", { name: "Change profile" }).click();
  await page.locator(".profile input[type=text]").fill("Amara Okafor");
  await shot("profile-form");
  await page.keyboard.press("Escape");

  await page.evaluate(() => localStorage.setItem("understudy-view-as", "admin"));
  await page.goto(`${base}/#/firm`); await page.reload(); await page.waitForTimeout(1000);
  await shot("admin-firm");
  const more = page.getByRole("button", { name: "More" }).first();
  if (await more.isVisible()) { await more.click(); await shot("admin-more"); }
  await ctx.close();
}
await browser.close();
