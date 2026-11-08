// Replays the ten jobs of docs/knack-ux/jobs.json and the three-click first run in a real browser, counts the clicks, and fails above budget.
// Usage: node scripts/check-clicks.mjs [base=http://127.0.0.1:5173]    (engine and agent are blocked: example data, nothing can change)
// A job's controls that another screen owns (Needs you, Routines, Your data) report PENDING until that screen draws them; set STRICT=1 to make PENDING fail.
// Destructive controls (Approve, Stop, Forget) are found and counted, never clicked.
import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const strict = process.env.STRICT === "1";
const spec = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "docs", "knack-ux", "jobs.json"), "utf8"));
const budget = (id, key = "target_clicks") => spec.jobs.find((j) => j.id === id)[key];

const browser = await chromium.launch();
let failed = 0, pending = 0;
const out = (kind, name, detail) => { console.log(`${kind.padEnd(8)} ${name}  ${detail}`); if (kind === "FAIL") failed++; if (kind === "PENDING") { pending++; if (strict) failed++; } };

async function open(role = "worker", route = "/home") {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.addInitScript(([r]) => { try { localStorage.setItem("understudy-first-run-done", "2020-01-01T00:00:00Z"); if (r === "admin") localStorage.setItem("understudy-view-as", "admin"); else localStorage.removeItem("understudy-view-as"); } catch { /* */ } }, [role]);
  await page.goto(`${base}/#${route}`);
  await page.waitForSelector("#main", { timeout: 15000 });
  await page.waitForTimeout(900);
  return { ctx, page };
}
const here = (page) => page.evaluate(() => window.location.hash.replace(/^#/, "").split("?")[0]);
const click = async (page, loc, counter) => { await loc.click(); counter.n++; await page.waitForTimeout(500); };

/** Each job: the clicks it takes, found in the page. `need` is a control another screen owns: PENDING when missing. */
async function job(id, name, role, steps) {
  const { ctx, page } = await open(role);
  const counter = { n: 0 };
  try {
    for (const s of steps) await s({ page, counter });
    return { ctx, page, clicks: counter.n };
  } catch (e) {
    await ctx.close();
    return { error: e instanceof Error ? e.message.split("\n")[0] : String(e), clicks: counter.n };
  }
}
const nav = (label, route) => async ({ page, counter }) => {
  await click(page, page.locator("nav#nav").getByRole("link", { name: new RegExp(`^${label}`) }), counter);
  if ((await here(page)) !== route) throw new Error(`expected ${route}, at ${await here(page)}`);
};
/** The last click of a job, counted and never made: it is a destructive control (approve, forget, stop, run). */
const thenClick = ({ counter }) => { counter.n++; };
const see = (loc, what) => async ({ page }) => { if (!(await loc(page).first().isVisible().catch(() => false))) throw new Error(`missing: ${what}`); };
const seePending = (loc, what) => async ({ page }) => { if (!(await loc(page).first().isVisible().catch(() => false))) { const e = new Error(`PENDING:${what}`); throw e; } };

async function report(id, name, role, steps, max, extra = "") {
  const r = await job(id, name, role, steps);
  if (r.ctx) await r.ctx.close();
  if (r.error?.startsWith("PENDING:")) return out("PENDING", `${id} ${name}`, `${r.clicks} clicks so far, then waiting for ${r.error.slice(8)} (budget ${max})`);
  if (r.error) return out("FAIL", `${id} ${name}`, r.error);
  out(r.clicks <= max ? "PASS" : "FAIL", `${id} ${name}`, `${r.clicks} clicks, budget ${max}${extra}`);
}

// J1: the app opens on Home with the hero visible.
await report("J1", "see what matters this week", "worker", [see((p) => p.locator("#main h1"), "the Home hero")], budget("J1"));
// J2: the approval is the hero, or one click away in Needs you.
await report("J2", "approve or reject (the hero)", "worker", [seePending((p) => p.getByTestId("home-approval").getByRole("button", { name: /^(Approve|Resume)/ }), "an approval in the Home hero"), thenClick], budget("J2"));
await report("J2", "approve or reject (from Needs you)", "worker", [nav("Needs you", "/needs-you"), see((p) => p.locator("#main").getByRole("button", { name: /^(Approve|Resume|Accept)/ }), "a decision button"), thenClick], budget("J2", "target_when_several"));
// J3: Needs you, then Watch first, Not now or Never.
await report("J3", "opt in to a routine", "worker", [nav("Needs you", "/needs-you"), seePending((p) => p.locator("#main").getByRole("button", { name: /^(Watch first|Not now|Never)/ }), "a routine proposal with Watch first, Not now and Never"), thenClick], budget("J3"));
// J4: Growth.
await report("J4", "see whether I need less help", "worker", [nav("Growth", "/growth"), see((p) => p.locator("#main h1"), "the Growth title")], budget("J4"));
// J5: Your data, then Forget (counted, not clicked).
await report("J5", "see what Knack has of me (1) and delete it (3)", "worker", [nav("Your data", "/your-data"), seePending((p) => p.locator("#main").getByRole("button", { name: /^Forget/ }), "a Forget button in Your data"), thenClick, thenClick], budget("J5"));
// J6: Stop is one click on every screen (found, not clicked); the keys are zero.
await report("J6", "stop everything (the Stop button)", "worker", [see((p) => p.getByRole("button", { name: "Stop everything now" }), "the Stop button"), thenClick], budget("J6", "target_clicks_pointer"));
// J7: Routines, then Run now (counted, not clicked).
await report("J7", "start work (Routines, Run now)", "worker", [nav("Routines", "/routines"), seePending((p) => p.locator("#main").getByRole("button", { name: /^Run now/ }), "a Run now button"), thenClick], budget("J7", "target_clicks_pointer"));
// A1 to A3: Admin. A real role lands on Firm (0); the sidebar rows are 1; the first switch is two clicks (the account button, then Admin) and is remembered.
{
  const { ctx, page } = await open("admin", "/");
  const at = await here(page);
  out(at === "/firm" ? "PASS" : "FAIL", "A1 admin lands on Firm (remembered switch)", `0 clicks, at ${at}`);
  await ctx.close();
}
await report("A2", "compare a role (sidebar)", "admin", [nav("Roles", "/roles")], budget("A2"));
await report("A3", "see onboarding speed (sidebar)", "admin", [nav("Onboarding", "/onboarding")], budget("A3"));
{
  // The first time: Account, then Admin. Accepted deviation (lead, 7 Nov 2026): the spec counts the switch as 1; opening the menu is a click, so it is 2 the first time and 0 after.
  const { ctx, page } = await open("worker", "/home");
  const c = { n: 0 };
  await click(page, page.getByRole("button", { name: /^Account/ }), c);
  await click(page, page.getByRole("menuitemradio", { name: "Admin" }), c);
  const at = await here(page);
  const budgetNow = budget("A1", "target_clicks_role_switch");
  out(at === "/firm" && c.n <= budgetNow + 1 ? "ACCEPTED" : "FAIL", "A1 admin switch (first time)", `${c.n} clicks, spec ${budgetNow}, accepted +1 for opening the account menu, lands on ${at}`);
  await ctx.close();
}
// First run: three clicks from launch to Home.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.goto(`${base}/#/first-run`);
  await page.waitForSelector(".rolecard", { timeout: 15000 });
  const c = { n: 0 };
  await click(page, page.locator(".rolecard").first(), c);
  // With the connections slot filled the card opens its chips and needs Continue: one more click, allowed.
  const cont = page.getByRole("button", { name: "Continue" });
  const withChips = await cont.isVisible().catch(() => false);
  if (withChips) await click(page, cont, c);
  await click(page, page.getByRole("button", { name: "Not now" }), c);
  await page.getByRole("button", { name: "Show my week" }).waitFor({ timeout: 15000 });
  await click(page, page.getByRole("button", { name: "Show my week" }), c);
  const at = await here(page);
  const allowed = spec.first_run.target_clicks + (withChips ? 1 : 0);
  out(c.n <= allowed && at === "/home" ? "PASS" : "FAIL", "first run: launch to Home", `${c.n} clicks, budget ${allowed}${withChips ? " (3 plus Continue for the connection chips, owner choice)" : ""}, at ${at}`);
  await ctx.close();
}
await browser.close();
console.log(`\n${failed ? "FAILED" : "OK"}: ${failed} failed, ${pending} pending (screens another track owns)`);
process.exit(failed ? 1 : 0);
