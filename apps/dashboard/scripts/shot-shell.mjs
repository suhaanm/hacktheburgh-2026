// Screenshots of the Knack shell for the QA folder: node scripts/shot-knack.mjs [base=http://127.0.0.1:5191] [outDir=qa/knack] [--live] [--queue-empty] [--routes=home,needs-you,...] [--admin]
// Light and dark at 1440 by 900, 1152 by 735 and 390 by 844. By default the engine and agent are blocked (example data, deterministic).
// With --live the page talks to the engine through the dev server, but every request that is not a GET is refused, so nothing can change.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n, d) => args.find((a) => a.startsWith(`--${n}=`))?.split("=")[1] ?? d;
const pos = args.filter((a) => !a.startsWith("--"));
const base = pos[0] ?? "http://127.0.0.1:5191";
const out = pos[1] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");
const routes = opt("routes", "home").split(",");
const live = flag("live");
const admin = flag("admin");
const noQueue = flag("queue-empty");
const SIZES = [["1440", 1440, 900], ["win", 1152, 735], ["m390", 390, 844]];
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
for (const theme of ["light", "dark"]) for (const [tag, width, height] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme, deviceScaleFactor: 1 });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => {
    const u = r.request().url();
    if (noQueue && /\/engine\/queue\?status=(pending|all)/.test(u)) return r.fulfill({ contentType: "application/json", body: JSON.stringify({ meta: { origin: "synthetic", n: 0, n_unit: "episodes", note: "" }, data: [] }) });
    return live && r.request().method() === "GET" ? r.continue() : r.abort();
  });
  const page = await ctx.newPage();
  await page.addInitScript(([t, a]) => { try { localStorage.setItem("understudy-theme", t); localStorage.setItem("understudy-first-run-done", new Date().toISOString()); if (a) localStorage.setItem("understudy-view-as", "admin"); } catch { /* */ } }, [theme, admin]);
  for (const r of routes) {
    await page.goto(`${base}/#/${r}`);
    await page.waitForTimeout(1100);
    const name = `${admin ? "admin-" : ""}${r.replace(/[/?=&]/g, "-")}${noQueue ? "-quiet" : ""}-${live ? "live-" : ""}${theme}-${tag}.png`;
    await page.screenshot({ path: join(out, name) });
    console.log(name);
  }
  await ctx.close();
}
await browser.close();
