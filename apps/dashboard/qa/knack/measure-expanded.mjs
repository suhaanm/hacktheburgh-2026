// How much is in each EXPANDED block on Track C's screens: words, paragraphs, buttons and links, and rows of actions, read from the rendered page.
// The rule (owner, 8 Nov): an expanded block holds at most one short paragraph and one row of actions; the rest sits behind one closed "More".
// Usage (from apps/dashboard, own dev server): node qa/knack/measure-expanded.mjs [base=http://127.0.0.1:5192] [--json=file]
// Example data on purpose (services refused), so the numbers are the same every run. Read-only.
import { chromium } from "playwright";
import fs from "node:fs";

const base = process.argv[2]?.startsWith("http") ? process.argv[2] : "http://127.0.0.1:5192";
const jsonOut = process.argv.find((a) => a.startsWith("--json="))?.slice(7);

/** name, route, how to open it, the CSS selector of the block that opens (inside the page). */
const BLOCKS = [
  ["needs-you: approval evidence", "/needs-you", async (p) => { await p.locator("article[data-kind=approval] [data-toggle]").first().click(); }, "[data-testid=evidence]"],
  ["needs-you: prepared card details", "/needs-you", async (p) => { await showAll(p); await p.locator("article[data-kind=prepared] [data-toggle]").first().click(); }, "[id^=pv-]"],
  ["needs-you: proposal details", "/needs-you", async (p) => { await p.locator("article[data-kind=proposal]").first().getByRole("button", { name: "Details" }).click(); }, "[data-testid=proposal-details]"],
  ["needs-you: since you left", "/needs-you", async (p) => { await p.getByRole("button", { name: "Since you left" }).click(); }, "#away-details"],
  ["routines: open running row", "/routines", async (p) => { await p.locator(".rt-row__open").first().click(); }, ".rt-panel"],
  ["routines: automate peek", "/routines?tab=could-automate", async (p) => { await p.getByRole("button", { name: "Automate" }).first().click({ force: true }); }, ".hl-peek"],
  ["your-data: what Knack remembers", "/your-data", async () => {}, "#yd-remembers"],
  ["your-data: what it measures", "/your-data?section=measured", async () => {}, "#yd-measured"],
  ["your-data: what it looked at or sent", "/your-data?section=sent", async () => {}, "#yd-sent"],
  ["settings: Advanced (every call)", "/home?settings=advanced", async (p) => { await p.waitForTimeout(600); }, "[data-testid=advanced-calls]"],
  ["routines: background tasks", "/routines", async (p) => { await mockTasks(p); await p.reload(); await p.waitForTimeout(1800); }, "[data-testid=background-tasks]"],
  ["routines: a task opened", "/routines", async (p) => { await mockTasks(p); await p.reload(); await p.waitForTimeout(1800); await p.locator("button.bt-open").first().click(); }, "[data-testid=background-tasks]"],
  ["your-data: what your admin can see", "/your-data?section=admin-sees", async () => {}, "#yd-admin-sees"],
  ["your-data: capture and screen glances", "/your-data?section=switches", async () => {}, "#yd-switches"],
  ["settings: the sheet", "/home?settings=live-models", async () => {}, "[data-testid=settings]"],
  ["settings: interruptions, More", "/home?settings=interruptions", async (p) => { await openDetails(p, "[data-testid=settings]", /^More$/, 1); }, "[data-testid=settings] .details__body"],
  ["settings: each kind", "/home?settings=interruptions", async (p) => { await openDetails(p, "[data-testid=settings]", /^More$/, 1); await openDetails(p, "[data-testid=settings]", /^Each kind$/, 1); }, "[data-testid=settings] .details__body .details__body"],
  ["agents (admin): helpers and result", "/agents", async (p) => { await p.locator("summary", { hasText: "Helpers and result" }).first().click(); }, "article.run .details__body", "admin"],
  ["agents (admin): start a run", "/agents", async (p) => { await p.locator("summary", { hasText: "Start a background run" }).click(); }, ".spawn", "admin"],
];

/** Open the first `n` disclosures whose summary matches, whatever state they are in (a sheet that stays open between addresses keeps its disclosures as they were). */
async function openDetails(p, scope, re, n) { await p.locator(`${scope} details`).evaluateAll((els, [src, flags, k]) => { let left = k; for (const d of els) { const t = d.querySelector(":scope > summary")?.textContent?.trim() ?? ""; if (left > 0 && new RegExp(src, flags).test(t)) { d.open = true; left--; } } }, [re.source, re.flags, n]); }

/** A tasks service that answers (the built-in sample is never a task, so the background tasks list needs a live answer to draw anything). */
export async function mockTasks(page) {
  const now = Date.now();
  const rows = [
    { task_id: "tk_a", title: "Tidy the invoices folder", state: "running", started: new Date(now - 90_000).toISOString(), latest: "Reading invoices.pdf" },
    { task_id: "tk_c", title: "Summarise last week's notes", state: "done", started: new Date(now - 300_000).toISOString(), finished: new Date(now - 120_000).toISOString(), result: "Wrote a one page summary of 14 notes." },
  ];
  await page.route(/^https?:\/\/[^/]+\/agent(\/|$)/, (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/agent/, "");
    const reply = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/tasks") return reply(rows);
    if (path === "/tasks/events") return route.abort();
    if (path.startsWith("/tasks/")) return reply({ ...rows[0], steps: ["Listed the folder", "Read 12 files"] });
    return reply({ error: { code: "not_found", message: "x" } }, 404);
  });
}

async function showAll(p) { const all = p.getByRole("button", { name: /^Show all/ }); if (await all.count()) await all.first().click(); }

const measure = (sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const vis = (e) => { const cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden") return false; const r = e.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
  const hiddenIn = (e) => { for (let x = e; x && x !== el.parentElement; x = x.parentElement) { if (x.tagName === "DETAILS" && !x.open && x !== el && !e.closest("summary")) return true; } return false; };
  let words = 0;
  const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (tw.nextNode()) { const t = tw.currentNode; const s = t.textContent.trim(); if (!s) continue; const pe = t.parentElement; if (!pe || !vis(pe) || hiddenIn(pe) || pe.closest(".u-sr-only")) continue; words += s.split(/\s+/).length; }
  const paras = [...el.querySelectorAll("p")].filter((p) => vis(p) && !hiddenIn(p) && p.textContent.trim().split(/\s+/).length >= 5 && !p.closest("summary")).length;
  const ctrls = [...el.querySelectorAll("button, a[href], input, select, textarea, summary, [role=switch]")].filter((c) => vis(c) && !hiddenIn(c));
  const bands = new Set(ctrls.filter((c) => c.tagName !== "SUMMARY" && c.tagName !== "INPUT" && c.tagName !== "TEXTAREA" && c.tagName !== "SELECT").map((c) => Math.round(c.getBoundingClientRect().top / 24)));
  return { words, paras, controls: ctrls.length, actionRows: bands.size };
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
const page = await ctx.newPage();
const rows = [];
let role = "worker";
for (const [name, route, open, sel, as = "worker"] of BLOCKS) {
  if (as !== role) {     // the admin's pages: the view is a remembered choice on this device, so set it and reload
    await page.goto(`${base}/#/today`);
    await page.evaluate((r) => { try { if (r === "admin") localStorage.setItem("understudy-view-as", "admin"); else localStorage.removeItem("understudy-view-as"); } catch { /* blocked */ } }, as);
    await page.reload();
    role = as;
  }
  if (page.url().endsWith(`#${route}`)) { await page.goto(`${base}/#/today`); await page.waitForTimeout(150); }   // the same address does not remount: hop through another route first
  await page.goto(`${base}/#${route}`);
  await page.waitForTimeout(1200);
  try { await open(page); await page.waitForTimeout(350); } catch (e) { rows.push({ name, error: String(e).split("\n")[0].slice(0, 80) }); continue; }
  const m = await page.evaluate(measure, sel);
  await page.unroute(/^https?:\/\/[^/]+\/agent(\/|$)/).catch(() => undefined);
  rows.push({ name, ...(m ?? { error: "block not found" }) });
}
await browser.close();
for (const r of rows) console.log(`${r.error ? "ERR " : "    "}${r.name.padEnd(40)} ${r.error ? r.error : `words ${String(r.words).padStart(3)}  paragraphs ${r.paras}  controls ${String(r.controls).padStart(2)}  action rows ${r.actionRows}`}`);
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify(rows, null, 1));
