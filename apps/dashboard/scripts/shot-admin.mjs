// Screenshots and layout checks for the REQ-9 screens: worker home, Firm views, Predictions, palette, tour, brief.
// Usage: node scripts/shot-admin.mjs [base=http://127.0.0.1:5173] [--live] [--only=name1,name2] [--theme=light|dark] [--width=1440|390]
// Demo-data mode by default (engine and agent blocked, so the example data answers and runs are repeatable). --live lets the proxy through.
// Writes apps/dashboard/qa/admin-<name>-<theme>-<width>.png and prints one line per shot, with horizontal overflow and page errors.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const args = process.argv.slice(2);
const base = args.find((a) => a.startsWith("http")) ?? "http://127.0.0.1:5173";
const live = args.includes("--live");
const only = (args.find((a) => a.startsWith("--only=")) ?? "").slice(7).split(",").filter(Boolean);
const themeOnly = (args.find((a) => a.startsWith("--theme=")) ?? "").slice(8);
const widthOnly = Number((args.find((a) => a.startsWith("--width=")) ?? "").slice(8)) || 0;
const qa = join(dirname(fileURLToPath(import.meta.url)), "..", "qa");

const SHOTS = [
  { name: "home", view: "worker", hash: "/home" },
  { name: "home-open", view: "worker", hash: "/home", act: async (p) => { await p.getByText("Why am I seeing this?").first().click(); await p.getByText("What your admin can see").click(); await p.waitForTimeout(500); } },
  { name: "home-quiet", view: "worker", hash: "/home?story=quiet" },
  { name: "predictions", view: "worker", hash: "/predictions" },
  { name: "firm-overview", view: "admin", hash: "/firm" },
  { name: "firm-drill", view: "admin", hash: "/firm", act: async (p) => { await p.locator("#main li button[aria-pressed]").first().click(); await p.waitForTimeout(500); } },
  { name: "firm-roles", view: "admin", hash: "/firm/roles" },
  { name: "firm-people", view: "admin", hash: "/firm/people" },
  { name: "firm-people-open", view: "admin", hash: "/firm/people", act: async (p) => { await p.getByText("See the numbers").first().click(); await p.locator(".firm-role-details summary").first().click(); await p.locator(".firm-person__btn").first().click(); await p.waitForTimeout(300); } },
  { name: "firm-onboarding", view: "admin", hash: "/firm/onboarding" },
  { name: "firm-automation", view: "admin", hash: "/firm/automation" },
  { name: "firm-risk", view: "admin", hash: "/firm/risk" },
  { name: "firm-forecasts", view: "admin", hash: "/firm/forecasts" },
  { name: "firm-brief", view: "admin", hash: "/firm/brief" },
  { name: "gate", view: "worker", hash: "/firm" },
  { name: "details-note", view: "worker", hash: "/genome" },
  { name: "palette", view: "admin", hash: "/home", act: async (p) => { await p.keyboard.press("Control+k"); await p.waitForTimeout(500); } },
  { name: "palette-query", view: "admin", hash: "/home", act: async (p) => { await p.keyboard.press("Control+k"); await p.waitForTimeout(300); await p.keyboard.type("onb"); await p.waitForTimeout(400); } },
  { name: "tour", view: "worker", hash: "/home", act: async (p) => { await p.keyboard.press("Control+k"); await p.waitForTimeout(300); await p.keyboard.type("tour"); await p.waitForTimeout(200); await p.keyboard.press("Enter"); await p.waitForTimeout(700); } },
];

const browser = await chromium.launch();
let bad = 0;
for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }].filter((v) => !widthOnly || v.width === widthOnly)) {
  for (const theme of ["light", "dark"].filter((t) => !themeOnly || t === themeOnly)) {
    const ctx = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "no-preference" });
    if (!live) await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error" && !/ERR_CONNECTION_REFUSED|Failed to load resource|ERR_FAILED/.test(m.text())) errors.push(`console: ${m.text()}`); });
    for (const s of SHOTS) {
      if (only.length && !only.includes(s.name)) continue;
      errors.length = 0;
      // A fresh document each time: the demo role is held in memory, so a reload is what puts it back to Worker.
      await page.goto("about:blank");
      await page.goto(`${base}/#/home`);
      await page.waitForTimeout(350);
      const mobile = viewport.width < 600;
      const menuBtn = page.locator("button[aria-controls='nav']");
      const setMenu = async (open) => {
        if (!mobile) return;
        const now = (await menuBtn.getAttribute("aria-expanded")) === "true";
        if (now !== open) await menuBtn.click();
      };
      if (s.view === "admin") {
        await setMenu(true);
        await page.locator(".viewas .segmented button", { hasText: "Admin" }).click();
        await setMenu(false);
      }
      await page.evaluate((h) => { window.location.hash = h; }, s.hash);
      await page.waitForTimeout(900);
      if (s.act) { try { await s.act(page); } catch (e) { errors.push(`act: ${e.message.split("\n")[0]}`); } }
      const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, title: document.title }));
      const overflow = m.sw - m.iw;
      const file = `admin-${s.name}-${theme}-${viewport.width}.png`;
      await page.screenshot({ path: join(qa, file), fullPage: s.name.startsWith("palette") || s.name === "tour" ? false : true });
      const ok = overflow <= 0 && errors.length === 0;
      if (!ok) bad++;
      console.log(`${ok ? "OK  " : "FAIL"} ${file}  overflow ${overflow}px${errors.length ? "  " + errors.slice(0, 2).join(" | ") : ""}`);
    }
    await ctx.close();
  }
}
await browser.close();
process.exit(bad ? 1 : 0);
