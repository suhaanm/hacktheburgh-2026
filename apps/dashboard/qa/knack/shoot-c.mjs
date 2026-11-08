// Track C screenshots: Needs you, Routines, Your data, Settings, light and dark, at 1440x900, 1152x735 and 390x844.
// Usage (from apps/dashboard, own dev server): node qa/knack/shoot-c.mjs [base=http://127.0.0.1:5192] [outdir=qa/knack] [filter]
// Example data mode on purpose: every engine and agent request is refused, so nothing is read from or written to a live service.
import { chromium } from "playwright";
import fs from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:5192";
const out = process.argv[3] ?? "qa/knack";
const only = process.argv[4];
fs.mkdirSync(out, { recursive: true });
const SHOTS = [
  ["needs-you", "/needs-you"],
  ["needs-you-more", "/needs-you", async (p) => { await p.locator("article[data-kind=proposal]").first().getByRole("button", { name: "Details" }).click(); await p.getByRole("button", { name: "Evidence" }).first().click(); }],
  ["routines", "/routines"],
  ["routines-open", "/routines", async (p) => { await p.locator(".rt-row__open").first().click(); }],
  ["routines-could", "/routines?tab=could-automate"],
  ["your-data", "/your-data"],
  ["your-data-sent", "/your-data?section=sent"],
  ["settings-advanced", "/home?settings=advanced"],
  ["your-data-delete", "/your-data?section=switches", async (p) => { await p.getByRole("button", { name: "Delete everything" }).click(); }],
  ["routines-task-open", "/routines", async (p) => { await mockTasks(p); await p.reload(); await p.waitForTimeout(1800); await p.locator("button.bt-open").first().click(); }],
  ["agents-gate", "/agents"],
  ["agents", "/agents", async (p) => { await asAdmin(p); }],
  ["agents-open", "/agents", async (p) => { await asAdmin(p); await p.locator("summary", { hasText: "Helpers and result" }).first().click(); }],
  ["models", "/models"],
  ["settings", "/home?settings=live-models"],
  ["settings-interruptions", "/home?settings=interruptions"],
];
/** A tasks service that answers (the built-in sample is never a task, so the background tasks list needs a live answer to draw anything). */
async function mockTasks(page) {
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

/** The admin's pages: the view is a remembered choice on this device; set it, reload, and the page opens as the admin sees it. */
async function asAdmin(p) {
  await p.evaluate(() => { try { localStorage.setItem("understudy-view-as", "admin"); } catch { /* blocked */ } });
  await p.reload(); await p.waitForTimeout(900);
}
const SIZES = [["1440", 1440, 900], ["1152", 1152, 735], ["390", 390, 844]].filter(([sz]) => !process.env.SIZES || process.env.SIZES.split(",").includes(sz));
const browser = await chromium.launch();
for (const theme of (process.env.THEMES ?? "light,dark").split(",")) {
  for (const [sz, w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme });
    await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const [name, path, act] of SHOTS) {
      if (only && !name.includes(only)) continue;
      await page.goto(`${base}/#${path}`);
      await page.waitForTimeout(900);
      try { if (act) { await act(page); await page.waitForTimeout(300); } } catch (e) { console.log(`  (${name}: step skipped: ${String(e).slice(0, 80)})`); }
      await page.screenshot({ path: `${out}/${name}-${theme}-${sz}.png` });
      await page.unroute(/^https?:\/\/[^/]+\/agent(\/|$)/).catch(() => undefined);
      if (name.startsWith("agents") && name !== "agents-gate") { await page.evaluate(() => { try { localStorage.removeItem("understudy-view-as"); } catch { /* blocked */ } }); await page.reload(); }
    }
    if (errors.length) console.log(`page errors at ${sz} ${theme}: ${errors.slice(0, 3).join(" | ")}`);
    await ctx.close();
  }
}
await browser.close();
console.log("done");
