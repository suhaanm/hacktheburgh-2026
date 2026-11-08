// Horizontal overflow and page errors on EVERY screen, at 1440 by 900, 1152 by 735 and 390 by 844, light and dark. Example-data mode (engine and agent blocked),
// or real engine data with --live-via=http://127.0.0.1:5173 (the page's GETs are relayed through a running dashboard; every other method is refused).
// Usage: node scripts/check-overflow.mjs [base=http://127.0.0.1:5173] [--live-via=URL]   Exits 1 if any screen scrolls sideways or throws.
import { chromium } from "playwright";
import { openAs, relayLive } from "./lib/knack-page.mjs";

const args = process.argv.slice(2);
const base = (args.find((a) => /^https?:/.test(a)) ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const liveVia = (args.find((a) => a.startsWith("--live-via=")) ?? "").slice("--live-via=".length);
const ROUTES = [
  "home", "needs-you", "routines", "growth", "your-data", "genome", "presence", "graph", "week", "git", "forecasts", "agents", "models", "today", "evidence", "setup",
  "firm", "roles", "onboarding", "firm/people", "firm/automation", "firm/risk", "firm/forecasts", "firm/brief",
];
const browser = await chromium.launch();
let bad = 0, total = 0;
for (const size of [{ width: 1440, height: 900 }, { width: 1152, height: 735 }, { width: 390, height: 844 }]) {
  for (const theme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: size, colorScheme: theme });
    await ctx.route("**/*", (r) => {
      const req = r.request();
      if (!["GET", "HEAD"].includes(req.method())) return r.abort();
      if (!liveVia && /^https?:\/\/[^/]+\/(engine|agent)(\/|$)/.test(req.url())) return r.abort();
      return r.continue();
    });
    if (liveVia) await relayLive(ctx, liveVia);
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    // The Admin view shows every screen (worker and admin); first run is marked done so a fresh profile lands on Home, not the bare first-run screen.
    const admin = await openAs(page, base, "admin");
    const over = [];
    if (!admin) over.push("the Admin view could not be opened");
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
