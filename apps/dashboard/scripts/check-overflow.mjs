// Horizontal overflow and page errors on EVERY screen, at 1440 by 900 and 390 by 844, light and dark. Demo-data mode (engine blocked).
// Usage: node scripts/check-overflow.mjs [base=http://127.0.0.1:5173]   Exits 1 if any screen scrolls sideways or throws.
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const ROUTES = [
  "home", "growth", "repeats", "routines", "queue", "privacy", "genome", "presence", "graph", "week", "git", "predictions",
  "today", "memory", "notices", "onboarding", "briefing", "agents", "models", "evidence",
  "firm", "firm/roles", "firm/people", "firm/onboarding", "firm/automation", "firm/risk", "firm/forecasts", "firm/brief",
];
const browser = await chromium.launch();
let bad = 0, total = 0;
for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  for (const theme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: size, colorScheme: theme });
    await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${base}/#/home`);
    await page.waitForTimeout(400);
    const mobile = size.width < 881;
    const menu = page.locator("button[aria-controls='nav']");
    if (mobile) await menu.click();
    await page.locator(".viewas .segmented button", { hasText: "Admin" }).click();
    if (mobile && (await menu.getAttribute("aria-expanded")) === "true") await menu.click();
    const over = [];
    for (const r of ROUTES) {
      errors.length = 0;
      await page.evaluate((h) => { location.hash = h; }, `#/${r}`);
      await page.waitForTimeout(r === "graph" ? 2400 : 900);
      const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
      total++;
      if (m.sw > m.iw || errors.length) { bad++; over.push(`${r} (${m.sw - m.iw}px${errors.length ? ", " + errors[0].slice(0, 60) : ""})`); }
    }
    console.log(`${over.length ? "FAIL" : "OK  "} ${size.width}x${size.height} ${theme}: ${ROUTES.length} screens${over.length ? "  " + over.join("; ") : ""}`);
    await ctx.close();
  }
}
await browser.close();
console.log(`${total - bad} of ${total} screen checks clean`);
process.exit(bad ? 1 : 0);
