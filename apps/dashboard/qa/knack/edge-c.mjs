// Page-level states of Track C's screens in a real browser (docs/knack-ux/edge-cases-c.md, last table): loading, the services down, partial answers, empty.
// Read-only: every service request is answered by this script (nothing reaches a real service, nothing is written). Usage:
//   node qa/knack/edge-c.mjs http://127.0.0.1:5192
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://127.0.0.1:5192";
const browser = await chromium.launch();
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); if (!ok) failed++; };
const SERVICE = /^https?:\/\/[^/]+\/(engine|agent)(\/|$)/;
const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

async function open(handler, hash, wait = 1200) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route(SERVICE, handler);
  const page = await ctx.newPage();
  await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(500);
  await page.goto(`${base}/#${hash}`); await page.waitForTimeout(wait);
  return { ctx, page };
}
const path = (route) => new URL(route.request().url()).pathname.replace(/^\/(engine|agent)/, "");
const ALL_ON = { privacy: true, localmodel: true, calendar: true, git: true, proactive: true, agents: true, evidence: true, attention: true };
const identity = (p) => (p === "/identity" ? { person: "p_demo01", role: "benefits-processor" } : null);

// Loading: the queue is slow, so the page says so in one line.
{
  const { ctx, page } = await open(async (route) => {
    const p = path(route);
    if (p === "/queue") { await new Promise((r) => setTimeout(r, 2500)); return json(route, [], 200); }
    if (identity(p)) return json(route, identity(p));
    if (p === "/health") return json(route, { ok: true, version: "x", mock: true, extensions: {} });
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  }, "/needs-you", 600);
  const t = await page.locator("main").innerText();
  check("loading: Needs you says it is loading, in one line", /Loading what needs you/.test(t) && t.length < 400);
  await ctx.close();
}

// Down: no service answers at all.
{
  const { ctx, page } = await open((route) => route.abort(), "/needs-you", 1500);
  const t = await page.locator("main").innerText();
  const why = await page.locator("main [data-testid=source-detail]").first().textContent();
  check("down: Needs you shows the built-in sample badged as example data, its reason in the badge's hint (the shell's banner says it in words)", /Example data/.test(t) && /Knack cannot reach its engine\./.test(await page.locator("body").innerText()) && /example data/i.test(why ?? ""));
  check("down: the sample still has its decisions", (await page.locator("article[data-kind]").count()) >= 1);
  await ctx.close();
}

// Partial: the queue answers (one real approval), routines do not.
{
  const item = { id: "q_edge1", run_id: "r_edge1", kind: "approval", risk_class: "normal", title: "Check the calculator result", summary: "The result differs from the benefit table.", status: "pending", created_at: new Date().toISOString(), routine_id: null, evidence: { screenshots: [], extracted: {}, expected: {}, diff: [], tier_log: [] } };
  const { ctx, page } = await open((route) => {
    const p = path(route);
    if (identity(p)) return json(route, identity(p));
    if (p === "/health") return json(route, { ok: true, version: "x", mock: false, extensions: {} });
    if (p.startsWith("/queue")) return json(route, [item]);
    if (p === "/routines") return json(route, { error: { code: "boom", message: "routines failed" } }, 500);
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  }, "/needs-you", 1800);
  const t = await page.locator("main").innerText();
  check("partial: the live approval is shown", /Check the calculator result/.test(t));
  check("partial: the screen says some of it is example data", /Some example data/.test(t));
  await ctx.close();
}

// Empty: every source is empty.
{
  const { ctx, page } = await open((route) => {
    const p = path(route);
    if (identity(p)) return json(route, identity(p));
    if (p === "/health") return json(route, { ok: true, version: "x", mock: false, extensions: ALL_ON });
    if (p.startsWith("/queue")) return json(route, []);
    if (p === "/routines") return json(route, []);
    if (p.startsWith("/briefing")) return json(route, { cards: [], generated_at: new Date().toISOString() });
    if (p.startsWith("/agents/runs")) return json(route, []);
    if (p === "/tasks") return json(route, []);
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  }, "/needs-you", 1800);
  const t = await page.locator("main").innerText();
  check("empty: Needs you says nothing needs you", /Nothing needs you\./.test(t) && (await page.locator("article[data-kind]").count()) === 0);
  await page.goto(`${base}/#/routines`); await page.waitForTimeout(1500);
  const r = await page.locator("main").innerText();
  check("empty: Routines says nothing runs yet and draws no background tasks", /Nothing runs yet\./.test(r) && (await page.locator("[data-testid=background-tasks]").count()) === 0);
  await ctx.close();
}

await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall edge-state checks passed");
process.exit(failed ? 1 : 0);
