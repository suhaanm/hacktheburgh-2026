// Usage (from apps/dashboard): node ../../docs/knack-ux/scripts/measure-jobs.mjs [outdir]
// Replays the ten jobs in docs/knack-ux/jobs.json by hand-written click lists and prints the click count of each. The last click of a destructive job is COUNTED, NOT EXECUTED.
// Click-path measurement for the ten jobs. Read-only: every non-GET request is refused, and the final destructive click is COUNTED but NOT executed.
import { chromium } from "playwright";
import fs from "node:fs";
const OUT = process.argv[2] ?? "qa/knack";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();

async function fresh() {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route("**/*", (r) => (["GET", "HEAD"].includes(r.request().method()) ? r.continue() : r.abort()));
  const page = await ctx.newPage();
  await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" }).catch(() => undefined);
  await page.waitForTimeout(1500);
  return { ctx, page };
}
const nav = (page, name) => page.locator(".nav a", { hasText: new RegExp(`^${name}`) }).first();

async function run(id, title, steps, finalNote) {
  const { ctx, page } = await fresh();
  let clicks = 0; const log = [];
  const landed = await page.evaluate(() => location.hash);
  log.push(`open app -> ${landed}`);
  for (const s of steps) {
    const loc = s.loc(page);
    try {
      await loc.waitFor({ state: "visible", timeout: 4000 });
    } catch { log.push(`!! not found: ${s.d}`); break; }
    clicks++;
    if (s.skip) { log.push(`${clicks}. ${s.d}  [counted, NOT executed]`); continue; }
    await loc.click({ timeout: 5000 });
    log.push(`${clicks}. ${s.d}`);
    await page.waitForTimeout(s.wait ?? 900);
  }
  await page.screenshot({ path: `${OUT}/job-${id}.png` });
  console.log(`\n${id} ${title}: ${clicks} click(s)${finalNote ? " (" + finalNote + ")" : ""}\n  ` + log.join("\n  "));
  await ctx.close();
}

await run("W1", "see what matters this week", []);
await run("W2", "approve a queued item", [
  { d: 'sidebar "Queue"', loc: (p) => nav(p, "Queue") },
  { d: '"Approve and submit"', loc: (p) => p.getByRole("button", { name: /Approve and submit/ }).first(), skip: true },
]);
await run("W3a", "opt into a routine (with approval)", [
  { d: 'sidebar "Routines"', loc: (p) => nav(p, "Routines") },
  { d: '"Run with my approval"', loc: (p) => p.getByRole("button", { name: "Run with my approval" }).first(), skip: true },
]);
await run("W3b", "decline a routine", [
  { d: 'sidebar "Routines"', loc: (p) => nav(p, "Routines") },
  { d: '"Never for this"', loc: (p) => p.getByRole("button", { name: "Never for this" }).first(), skip: true },
]);
await run("W3c", "let a routine run while I am away", [
  { d: 'sidebar "Routines"', loc: (p) => nav(p, "Routines") },
  { d: 'open "Run while I\'m away"', loc: (p) => p.locator("details.away summary").first() },
  { d: "switch it on", loc: (p) => p.locator("details.away .toggle__track").first() },
  { d: '"Allow while I\'m away"', loc: (p) => p.getByRole("button", { name: /Allow while I.m away/ }).first(), skip: true },
]);
await run("W4", "see whether I need less help", [
  { d: 'sidebar "Growth"', loc: (p) => nav(p, "Growth") },
]);
await run("W5a", "check and delete a memory line", [
  { d: 'sidebar "More" fold', loc: (p) => p.locator("button[aria-controls=nav-more]") },
  { d: '"Memory"', loc: (p) => nav(p, "Memory") },
  { d: '"Forget" on a line', loc: (p) => p.getByRole("button", { name: /^Forget line/ }).first() },
  { d: '"Forget it" (confirm)', loc: (p) => p.getByRole("button", { name: "Forget it" }).first(), skip: true },
]);
await run("W5b", "clear what was sent to a model", [
  { d: 'sidebar "Privacy"', loc: (p) => nav(p, "Privacy") },
  { d: '"Clear the ledger"', loc: (p) => p.getByRole("button", { name: "Clear the ledger" }), wait: 500 },
  { d: '"Yes, clear the list"', loc: (p) => p.getByRole("button", { name: "Yes, clear the list" }), skip: true },
]);
await run("W6", "stop everything", [
  { d: 'fixed "Stop everything" pill (or Shift+Esc: 0 clicks)', loc: (p) => p.locator("button.kill--fixed"), skip: true },
]);
await run("W7", "set up as a new worker (role choice to memory file)", [
  { d: 'sidebar "More" fold', loc: (p) => p.locator("button[aria-controls=nav-more]") },
  { d: '"Set up"', loc: (p) => nav(p, "Set up") },
]);
await run("A1", "admin: where the firm loses time", [
  { d: 'View as "Admin"', loc: (p) => p.locator(".viewas .segmented button", { hasText: "Admin" }) },
  { d: 'sidebar "Firm"', loc: (p) => nav(p, "Firm") },
]);
await run("A2", "admin: compare a role", [
  { d: 'View as "Admin"', loc: (p) => p.locator(".viewas .segmented button", { hasText: "Admin" }) },
  { d: 'sidebar "Firm"', loc: (p) => nav(p, "Firm") },
  { d: 'tab "Roles"', loc: (p) => p.getByRole("link", { name: /^Roles/ }).or(p.getByRole("tab", { name: /^Roles/ })).first() },
]);
await run("A3", "admin: onboarding speed", [
  { d: 'View as "Admin"', loc: (p) => p.locator(".viewas .segmented button", { hasText: "Admin" }) },
  { d: 'sidebar "Firm"', loc: (p) => nav(p, "Firm") },
  { d: 'tab "Onboarding"', loc: (p) => p.getByRole("link", { name: /^Onboarding/ }).or(p.getByRole("tab", { name: /^Onboarding/ })).first() },
]);
await browser.close();
