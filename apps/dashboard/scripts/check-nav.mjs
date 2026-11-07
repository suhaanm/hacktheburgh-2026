// Is every menu item reachable, uncovered by the sidebar footer? Opens both folds, scrolls each link into view and checks it sits above the footer.
// Usage: node scripts/check-nav.mjs [base=http://127.0.0.1:5173] ; prints one line per window size and exits 1 on any covered item.
import { chromium } from "playwright";
const base = process.argv[2] ?? "http://127.0.0.1:5173";
const SIZES = [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 1024, height: 700 }, { width: 390, height: 844 }];
const browser = await chromium.launch();
let bad = 0;
for (const view of ["worker", "admin"]) for (const size of SIZES) {
  const ctx = await browser.newContext({ viewport: size });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.goto(`${base}/#/home`);
  await page.waitForTimeout(500);
  const mobile = size.width < 881;
  if (mobile) await page.locator("button[aria-controls='nav']").click();
  if (view === "admin") await page.locator(".viewas .segmented button", { hasText: "Admin" }).click();
  for (const id of ["nav-details", "nav-more"]) { const b = page.locator(`button[aria-controls='${id}']`); if ((await b.getAttribute("aria-expanded")) !== "true") await b.click(); }
  const links = page.locator("nav#nav a.nav__link");
  const n = await links.count();
  const covered = [];
  for (let i = 0; i < n; i++) {
    const a = links.nth(i);
    await a.scrollIntoViewIfNeeded();
    const r = await page.evaluate((el) => {
      const link = el.getBoundingClientRect();
      const foot = document.querySelector(".side__foot")?.getBoundingClientRect();
      const kill = document.querySelector(".kill")?.getBoundingClientRect();
      const nav = document.querySelector("nav#nav")?.getBoundingClientRect();
      const outside = window.innerWidth > 880 && nav && (link.top < nav.top - 1 || link.bottom > nav.bottom + 1);
      const hits = (b) => b && link.bottom > b.top && link.top < b.bottom && link.right > b.left && link.left < b.right;
      return { label: el.textContent.trim().slice(0, 24), coveredByFoot: hits(foot) || outside, coveredByKill: hits(kill), top: link.top, bottom: link.bottom };
    }, await a.elementHandle());
    if (r.coveredByFoot || r.coveredByKill) covered.push(r.label);
  }
  const foot = await page.evaluate(() => Math.round(document.querySelector(".side__foot")?.getBoundingClientRect().height ?? 0));
  const ok = covered.length === 0;
  if (!ok) bad++;
  console.log(`${ok ? "OK  " : "FAIL"} ${view} ${size.width}x${size.height}: ${n} menu items, footer ${foot}px${ok ? "" : ", covered: " + covered.join(", ")}`);
  await ctx.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
