// Pictures of Home with the task box and the background tasks list, and of the account menu with a name and a role:
//   node scripts/shot-home-tasks.mjs [base=http://127.0.0.1:5191] [outDir=qa/knack]
// Light and dark at 1440 by 900, 1152 by 735 and 390 by 844. Nothing is written anywhere: the engine and agent are answered from here (a made-up worker, one running
// task, one consent card) and every other request to them is refused, so the screens use their example data. The file names start with home-tasks- and menu-account-.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://127.0.0.1:5191";
const out = process.argv[3] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");
mkdirSync(out, { recursive: true });
const SIZES = [["1440", 1440, 900], ["win", 1152, 735], ["m390", 390, 844]];
const cors = { "access-control-allow-origin": "*" };
const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: cors, body: JSON.stringify(body) });
const ROLES = [
  { id: "benefits-processor", name: "UK benefits processor", summary: "Runs entitlement checks.", depth: "deep" },
  { id: "data-analyst", name: "Data analyst", summary: "Pulls data.", depth: "standard" },
  { id: "programmer", name: "Programmer", summary: "Reads code.", depth: "standard" },
];
const RUNNING = { task_id: "tk_run", title: "Tidy the invoices folder", route: "claude_agent", source: "typed", state: "running", attended: true, latest: "Reading invoices.pdf", steps_done: 2, result: null, reason: null, started: new Date(Date.now() - 90_000).toISOString(), finished: null, open: null, needs_consent: null, question: null };
const CONSENT = { task_id: "tk_c", route: "claude_agent", summary: "I need your OK first.", question: null, needs_consent: { kind: "claude_agent", scope_text: "Knack will run a Claude agent in your Downloads folder.", can: ["Read files in Downloads", "Move files into folders"], cannot: ["Delete anything", "Reach the network"], folder: "/Users/you/Downloads", command_hash: null, cost_note: "Uses your Claude plan.", max_minutes: 30, buttons: { allow: "Allow for this task", decline: "Not now", more: [{ id: "everything", label: "Allow everything for this task" }] } } };

const browser = await chromium.launch();
for (const theme of ["light", "dark"]) for (const [tag, width, height] of SIZES) {
  for (const mode of ["none", "running"]) {
    const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme });
    await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, async (route) => {
      const req = route.request(), u = new URL(req.url());
      const path = u.pathname.replace(/^\/(engine|agent)/, "");
      const agent = /^\/agent\//.test(u.pathname);
      if (req.method() !== "GET" && !(agent && req.method() === "POST" && path === "/tasks")) return route.abort();
      if (!agent && path === "/health") return json(route, { ok: true, version: "x", mock: true, extensions: {} });
      if (!agent && path === "/identity") return json(route, { person: "p_you", role: "programmer", name: "Amara Okafor" });
      if (!agent && path === "/profile") return json(route, { person: "p_you", role: "programmer", name: "Amara Okafor", since: "2026-11-01", history: [], roles: ROLES });
      if (agent && path === "/tasks" && req.method() === "POST") return json(route, CONSENT, 201);
      if (agent && path === "/tasks/events") return route.fulfill({ status: 404, body: "" });
      if (agent && path === "/tasks") return json(route, mode === "running" ? [RUNNING] : []);
      if (agent && path === "/health") return json(route, { ok: true, extensions: {} });
      return json(route, { error: { code: "unavailable", message: "Not running." } }, 503);
    });
    const page = await ctx.newPage();
    await page.addInitScript((t) => { try { localStorage.setItem("understudy-theme", t); localStorage.setItem("understudy-first-run-done", new Date().toISOString()); localStorage.removeItem("understudy-view-as"); localStorage.setItem("understudy-display-name", "Amara Okafor"); } catch { /* */ } }, theme);
    const shot = async (name) => { await page.waitForTimeout(600); await page.screenshot({ path: join(out, `${name}-${theme}-${tag}.png`) }); console.log(`${name}-${theme}-${tag}.png`); };
    await page.goto(`${base}/#/home`);
    await page.waitForTimeout(2200);
    await shot(`home-tasks-${mode}`);
    if (mode === "running") {
      await page.locator("[data-testid=task-box] input[type=text]").fill("Tidy my downloads");
      await page.keyboard.press("Enter");
      await page.waitForTimeout(900);
      await shot("home-tasks-consent");
      await page.locator("[data-testid=task-consent]").getByRole("button", { name: "More" }).click();
      await shot("home-tasks-consent-more");
      const acct = page.locator("[data-account]:visible").first();
      await page.goto(`${base}/#/home`);
      await page.waitForTimeout(1200);
      await acct.click();
      await page.getByRole("menuitem", { name: "Change profile" }).waitFor();
      await shot("menu-account");
      await page.getByRole("menuitem", { name: "Change profile" }).click();
      await page.waitForTimeout(500);
      await shot("menu-account-profile");
    }
    await ctx.close();
  }
}
await browser.close();
