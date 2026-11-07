// Click budgets of docs/KNACK_UX.md section 1: replays the ten jobs of docs/knack-ux/jobs.json against a running dashboard and fails above budget.
// SKELETON from Track D (SYSTEM): the harness, the budgets and the paths that need nothing but the sidebar (J1, J4, A1, A2, A3) are wired.
// Track B (SHELL-WEB) fills the others (J2, J3, J5, J6, J7 and "launch to Home" for first run) by editing PATHS below: each is a list of steps,
// `{ d: "what is clicked", loc: (page) => locator, skip?: true }`. A step with `skip: true` is COUNTED and NOT EXECUTED (the last click of a
// destructive job). A path that is still `null` is reported as NOT WIRED and fails only with --strict.
//
// Read-only: every request that is not GET or HEAD is refused, so no step can change anything even if it were executed.
// Usage (from apps/dashboard):  node scripts/check-clicks.mjs [base=http://127.0.0.1:5173] [--only=J1,J4] [--example] [--strict] [--viewport=1440x900]
//   --example   block /engine and /agent (deterministic example data)
//   --strict    a job whose path is not wired fails
import { chromium } from "playwright";
import fs from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { openAs } from "./lib/knack-page.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const jobsFile = join(here, "..", "..", "..", "docs", "knack-ux", "jobs.json");
const spec = JSON.parse(fs.readFileSync(jobsFile, "utf8"));
const args = process.argv.slice(2);
const flag = (n) => args.find((a) => a === `--${n}` || a.startsWith(`--${n}=`));
const opt = (n, d) => { const a = flag(n); return a && a.includes("=") ? a.slice(n.length + 3) : d; };
const base = (args.find((a) => /^https?:/.test(a)) ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const only = opt("only", "") ? new Set(opt("only", "").split(",")) : null;
const [VW, VH] = opt("viewport", "1440x900").split("x").map(Number);
const strict = Boolean(flag("strict"));
const example = Boolean(flag("example"));

/** The click budget of a job, from jobs.json. Pointer variants and the Admin view-as switch have their own numbers. Exported for tests. */
export function budgetOf(job) {
  if (job.who === "admin") return job.target_clicks_role_switch ?? job.target_clicks;
  if (job.target_clicks_pointer != null) return job.target_clicks_pointer;
  return job.target_clicks;
}
/** Nothing is deeper than this from Home, and the five most frequent jobs are within `top5_max_from_home`. */
export const DEPTH = spec.budget;

// ---- helpers the paths use -------------------------------------------------------------------------------------------------------
/** A sidebar destination by its label: the new sidebar (nav items) or, until it lands, the old nav links. */
export const nav = (page, label) =>
  page.locator(".side nav a, .side nav button, nav a, nav button, .nav a").filter({ hasText: new RegExp(`^\\s*${label}\\b`) }).first();

/** Setup for an Admin job: first run marked done and the Admin view remembered, as the app does it. Not a counted click (see budgetOf). */
export const becomeAdmin = (page) => openAs(page, base, "admin");

// ---- the paths -------------------------------------------------------------------------------------------------------------------
// `setup` runs before counting starts. `steps: []` means the screen the app opens on is the answer (0 clicks).
// Track B: replace each `null` with { steps: [...] } following jobs.json `target_path`.
export const PATHS = {
  J1: { steps: [], then: (page) => page.locator("#main h1, #main .hero-insight").first() },
  J2: null, // Home hero is the pending item: "Approve and submit" (1); with several, sidebar "Needs you" then the button (2). The click is counted, not executed.
  J3: null, // sidebar "Needs you", then Watch first | Not now | Never (2). Away variant: "More ways to say yes", switch, confirm (3).
  J4: { steps: [{ d: 'sidebar "Growth"', loc: (p) => nav(p, "Growth") }] },
  J5: null, // sidebar "Your data", Forget, "Forget it" (3). The last click is counted, not executed.
  J6: null, // the sidebar Stop button (1). Option-Shift-Command-K is 0 and is a keyboard path the corner and menu bar prove.
  J7: null, // Needs you or Routines, "Run now" (2). Option-Space is 0 and belongs to the desktop shell.
  A1: { setup: becomeAdmin, steps: [{ d: 'sidebar "Firm"', loc: (p) => nav(p, "Firm") }] },
  A2: { setup: becomeAdmin, steps: [{ d: 'sidebar "Roles"', loc: (p) => nav(p, "Roles") }] },
  A3: { setup: becomeAdmin, steps: [{ d: 'sidebar "Onboarding"', loc: (p) => nav(p, "Onboarding") }] },
};

const browser = await chromium.launch();
let failed = 0;
let notWired = 0;
let ran = 0;

async function fresh() {
  const ctx = await browser.newContext({ viewport: { width: VW, height: VH } });
  await ctx.route("**/*", (r) => {
    const req = r.request();
    if (!["GET", "HEAD"].includes(req.method())) return r.abort();
    if (example && /^https?:\/\/[^/]+\/(engine|agent)(\/|$)/.test(req.url())) return r.abort();
    return r.continue();
  });
  const page = await ctx.newPage();
  await page.goto(`${base}/`, { waitUntil: "load" }).catch(() => undefined);
  await page.waitForTimeout(1500);
  return { ctx, page };
}

try {
  for (const job of spec.jobs) {
    if (only && !only.has(job.id)) continue;
    const path = PATHS[job.id];
    const budget = budgetOf(job);
    if (!path) { notWired++; console.log(`NOTE  ${job.id.padEnd(3)} ${job.name}: not wired yet (budget ${budget})`); if (strict) failed++; continue; }
    const { ctx, page } = await fresh();
    ran++;
    try {
      if (path.setup) await path.setup(page);
      let clicks = 0;
      const log = [`open the app -> ${await page.evaluate(() => location.hash)}`];
      let broke = null;
      for (const s of path.steps) {
        const loc = s.loc(page);
        try { await loc.waitFor({ state: "visible", timeout: 4000 }); } catch { broke = `not found: ${s.d}`; break; }
        clicks++;
        if (s.skip) { log.push(`${clicks}. ${s.d}  [counted, NOT executed]`); continue; }
        await loc.click({ timeout: 5000 });
        log.push(`${clicks}. ${s.d}`);
        await page.waitForTimeout(s.wait ?? 700);
      }
      if (!broke && path.then) { try { await path.then(page).waitFor({ state: "visible", timeout: 4000 }); } catch { broke = "the landing screen shows no title"; } }
      const over = clicks > budget || clicks > DEPTH.anything_max_from_home;
      const ok = !broke && !over;
      if (!ok) failed++;
      console.log(`${ok ? "PASS" : "FAIL"}  ${job.id.padEnd(3)} ${job.name}: ${clicks} click${clicks === 1 ? "" : "s"} (budget ${budget})${broke ? `  ${broke}` : ""}`);
      if (!ok) console.log("      " + log.join("\n      "));
    } finally {
      await ctx.close();
    }
  }
} finally {
  await browser.close();
}
console.log(`\n${failed ? "FAIL" : "OK"}  ${ran} job${ran === 1 ? "" : "s"} replayed, ${notWired} not wired${strict ? " (strict)" : ""}`);
process.exit(failed ? 1 : 0);
