// The rendered side of the "no visible 'demo'" rule: opens every screen in both views, the command palette (with every row shown) and every
// step of the tour, and looks for the banned word in what a person sees (page text, document title) and what a screen reader reads
// (aria-label, title, alt, placeholder, aria-description, visually hidden text). The static scan in src/lib/words.test.ts covers the source.
// Usage: node scripts/check-words.mjs [base=http://127.0.0.1:5173] [--word=demo]   Demo-data mode (engine blocked). Exits 1 on any hit.
import { chromium } from "playwright";

const args = process.argv.slice(2);
const base = args.find((a) => a.startsWith("http")) ?? "http://127.0.0.1:5173";
const word = (args.find((a) => a.startsWith("--word=")) ?? "--word=demo").slice(7);
const re = new RegExp(`\\b${word}\\b`, "i");
const ROUTES = [
  "home", "growth", "repeats", "routines", "queue", "privacy", "genome", "presence", "graph", "week", "git", "predictions",
  "today", "memory", "notices", "onboarding", "briefing", "agents", "models", "evidence",
  "firm", "firm/roles", "firm/people", "firm/onboarding", "firm/automation", "firm/risk", "firm/forecasts", "firm/brief",
];

const browser = await chromium.launch();
const hits = [];
let looked = 0;
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
const page = await ctx.newPage();

/** Everything a person or a screen reader gets from the page right now. */
async function seen() {
  return page.evaluate(() => {
    const out = [document.title, document.body.innerText, document.body.textContent ?? ""];
    for (const el of document.querySelectorAll("[aria-label],[title],[alt],[placeholder],[aria-description],[aria-roledescription]")) {
      for (const a of ["aria-label", "title", "alt", "placeholder", "aria-description", "aria-roledescription"]) { const v = el.getAttribute(a); if (v) out.push(v); }
    }
    return out;
  });
}
async function look(where) {
  looked++;
  for (const t of await seen()) {
    const m = re.exec(t);
    if (m) { hits.push(`${where}: …${t.slice(Math.max(0, m.index - 40), m.index + 50).replace(/\s+/g, " ")}…`); break; }
  }
}

for (const view of ["worker", "admin"]) {
  await page.goto("about:blank");
  await page.goto(`${base}/#/home`);
  await page.waitForTimeout(500);
  if (view === "admin") await page.locator(".viewas .segmented button", { hasText: "Admin" }).click();
  for (const folder of ["nav-details", "nav-more"]) { const b = page.locator(`button[aria-controls='${folder}']`); if ((await b.getAttribute("aria-expanded")) !== "true") await b.click(); }
  for (const r of ROUTES) {
    await page.evaluate((h) => { location.hash = h; }, `#/${r}`);
    await page.waitForTimeout(r === "graph" ? 2200 : 800);
    await look(`${view} #/${r}`);
  }
  // The example-week switch on the home screen shows more states.
  if (view === "worker") for (const story of ["good", "quiet", "onboarding"]) { await page.evaluate((h) => { location.hash = h; }, `#/home?story=${story}`); await page.waitForTimeout(500); await look(`worker #/home?story=${story}`); }
  // The command palette, with every row shown.
  await page.evaluate(() => { location.hash = "#/home"; });
  await page.keyboard.press("Control+k");
  await page.waitForTimeout(400);
  await look(`${view} palette`);
  const showAll = page.getByRole("option", { name: /Show all/ });
  if (await showAll.count()) { await showAll.first().click(); await page.waitForTimeout(300); await look(`${view} palette, all rows`); }
  await page.keyboard.press("Escape");
  // The tour, step by step.
  await page.keyboard.press("Control+k");
  await page.keyboard.type("tour");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(700);
  for (let step = 0; step < 10; step++) {
    await look(`${view} tour step ${step + 1}`);
    const next = page.getByRole("button", { name: /^(Next|Done)$/ });
    if (!(await next.count())) break;
    const label = (await next.first().innerText()).trim();
    await next.first().click();
    await page.waitForTimeout(600);
    if (label === "Done") break;
  }
  await page.keyboard.press("Escape");
}
await browser.close();
console.log(hits.length ? hits.map((h) => `FAIL ${h}`).join("\n") : `OK  ${looked} views read (every screen in both views, the palette, every tour step): no visible "${word}"`);
process.exit(hits.length ? 1 : 0);
