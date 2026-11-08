// The rendered side of the "no visible banned word" rules ("demo" since 7 Nov; "synthetic", "synthetically" and "simulated" since owner decision D57, 8 Nov;
// "example data", "example week", "sample data", "stand-in", "stand in", "not real workers", "for this build" and "fixture" since the owner's rule of 8 Nov, 05:00,
// with one exemption: the Evidence page, whose Measured on column and limitations say how each result was obtained):
// opens every screen in both views (the routes of qa/knack/budgets.json, the same ones check-copy.mjs reads), the command palette with every row shown and every
// step of the tour, and looks for the banned words in what a person sees (page text, document title) and what a screen reader reads (aria-label, title, alt,
// placeholder, aria-description, visually hidden text). The static scan in src/lib/words.test.ts covers the source and the fixtures.
// Usage: node scripts/check-words.mjs [base=http://127.0.0.1:5173] [--word=demo,synthetic,...]   Engine blocked, so the shell's own fallbacks are drawn. Exits 1 on any hit.
import { chromium } from "playwright";
import fs from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { openAs } from "./lib/knack-page.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const EXAMPLE_FAMILY = /^(made[- ]up|example data|example week|sample data|stand[- ]in|not real workers|for this build|fixture)$/i;
const DEFAULT_WORDS = "demo,synthetic,synthetically,simulated,made-up,made up,example data,example week,sample data,stand-in,stand in,not real workers,for this build,fixture";
const budgets = JSON.parse(fs.readFileSync(join(here, "..", "qa", "knack", "budgets.json"), "utf8"));
const args = process.argv.slice(2);
const base = (args.find((a) => a.startsWith("http")) ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const word = (args.find((a) => a.startsWith("--word=")) ?? `--word=${DEFAULT_WORDS}`).slice(7);
const words = word.split(",").filter(Boolean);
const re = new RegExp(`\\b(?:${words.join("|")})\\b`, "i");
/** On the Evidence page the example family is allowed (it states how each evaluation result was obtained); everything else is not. */
const reEvidence = new RegExp(`\\b(?:${words.filter((w) => !EXAMPLE_FAMILY.test(w)).join("|")})\\b`, "i");
const routesOf = (view) => Object.entries({ ...budgets.routes, ...(budgets.exempt ?? {}) }).filter(([, r]) => (view === "admin" ? r.audience === "admin" : r.audience !== "admin"));

const browser = await chromium.launch();
const hits = [];
const notes = [];
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
async function look(where, evidence = false) {
  looked++;
  for (const t of await seen()) {
    const m = (evidence ? reEvidence : re).exec(t);
    if (m) { hits.push(`${where}: …${t.slice(Math.max(0, m.index - 40), m.index + 50).replace(/\s+/g, " ")}…`); break; }
  }
}

for (const view of ["worker", "admin"]) {
  const ok = await openAs(page, base, view);
  if (!ok) { notes.push(`${view} view could not be reached (first run, or the account menu changed): its routes were skipped`); continue; }
  for (const [id, spec] of routesOf(view)) {
    await page.evaluate((h) => { location.hash = h; }, `#${spec.path}`);
    await page.waitForTimeout(id === "graph" ? 2200 : 800);
    await look(`${view} #${spec.path}`, id === "evidence");
  }
  // The week switch on the home screen shows more states.
  if (view === "worker") for (const story of ["good", "quiet", "onboarding"]) { await page.evaluate((h) => { location.hash = h; }, `#/home?story=${story}`); await page.waitForTimeout(500); await look(`worker #/home?story=${story}`); }
  // The command palette, with every row shown.
  try {
    await page.evaluate(() => { location.hash = "#/home"; });
    await page.keyboard.press("Control+k");
    await page.waitForTimeout(400);
    await look(`${view} palette`);
    const showAll = page.getByRole("option", { name: /Show all/ });
    if (await showAll.count()) { await showAll.first().click(); await page.waitForTimeout(300); await look(`${view} palette, all rows`); }
    await page.keyboard.press("Escape");
    // The tour, step by step, when the palette offers it.
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
  } catch (e) {
    notes.push(`${view}: the palette or the tour could not be read (${String(e.message ?? e).split("\n")[0]})`);
  }
}
await browser.close();
for (const n of notes) console.log(`NOTE ${n}`);
console.log(hits.length ? hits.map((h) => `FAIL ${h}`).join("\n") : `OK  ${looked} views read (every screen in both views, the palette, every tour step): no visible "${word}"`);
process.exit(hits.length ? 1 : 0);
