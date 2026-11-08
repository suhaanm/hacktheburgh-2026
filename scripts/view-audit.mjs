#!/usr/bin/env node
// View separation audit: does the Worker view show only the worker's own work, and does every Admin screen show something?
// The rule is docs/knack-ux/views.md; the owner's words (8 Nov 2026, 00:50): "when I have set myself to worker, why is it showing me the stuff
// that would show the admin ... when I change onto admin mode ... everything is blanked out".
//
//   node scripts/view-audit.mjs [--dashboard URL --engine URL] [--seed-firm] [--mock] [--json FILE] [--only worker|admin] [--routes a,b] [--keep] [--verbose]
//
// Default: a PRIVATE stack, never the owner's. It makes a throwaway data directory and home, seeds them like the live stack (the demo seed, which
// also seeds the made-up firm once that seed exists), starts an engine (python from the repo's .venv, or KNACK_PYTHON, with PYTHONPATH on THIS
// checkout so the code under test is this checkout's) on a free port with AGENT_PORT=1 (so nothing can reach a live agent) and no model keys, and
// a dashboard dev server on a free port. No agent service is started: /agent calls fail and the screens use their own fallbacks, which is also
// what the worker sees when the agent is down. Every request that is not a GET to /engine or /agent is refused by the browser context.
// With --dashboard and --engine it audits a stack you already run (the engine URL is used only to read the firm's names; GETs only).
//
// WORKER view (View as = Worker), every worker route and every retired route that redirects, at 1440 x 900:
//   FAIL if the page's text or the API responses it drew from hold: another person's name, id or label; a cohort or firm figure ("average over
//   all", "across the firm", "colleagues", a count of people); a model or provider name; a cost; a run id; "ledger"; a hash; "evidence";
//   "limitations"; diagnostics. Firm rules read the FULL text (a closed disclosure counts); internals rules read what is drawn and skip a
//   disclosure headed "Advanced". A worker page that calls an admin or firm endpoint FAILS. A retired route that still renders its old screen
//   FAILS ("should redirect"). Calls to internals endpoints are listed as WARN (a screen may fetch and not draw).
// WORKER view, each admin route: FAIL unless the page is only the gate sentence ("Switch to Admin to see this") and fires no admin call.
// ADMIN view (View as = Admin), every admin route: FAIL when the page is blank (no text beyond its header, or "0 people" and empty tables) or
//   when the engine's answer for it is empty. Cross-screen consistency: the same people numbers must add up on every admin screen.
//
// Output: one PASS or FAIL line per route with the offending snippet; exit code 1 on any FAIL. Never prints a key or a token.
import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { Procs, freePort, getJson, removeTree, repoRootFrom, sleep, until } from "./lib/private-stack.mjs";
import { GATE, apiIdentityViolations, isFirmEndpoint, isInternalEndpoint, summarise, workerTextViolations } from "./lib/view-rules.mjs";

// ---------------------------------------------------------------------------------------------- arguments
const argv = process.argv.slice(2);
const flag = (n, d) => { const i = argv.indexOf(`--${n}`); return i < 0 ? d : (argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : true); };
if (argv.includes("--help") || argv.includes("-h")) {
  console.log(readFileSync(new URL(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).slice(0, 28).map((l) => l.replace(/^\/\/ ?/, "")).join("\n"));
  process.exit(0);
}
const repo = repoRootFrom(import.meta.url);
const VERBOSE = argv.includes("--verbose");
const ONLY = flag("only", "all");
const ROUTES = flag("routes", null)?.split(",") ?? null;
const OWN_ID = "p_learn01";

// ---------------------------------------------------------------------------------------------- the routes
/** Worker destinations (views.md): five rows, plus Settings (a sheet opened from the account menu). */
const WORKER_ROUTES = [
  { id: "home", hash: "/home" },
  { id: "needs-you", hash: "/needs-you" },
  { id: "routines", hash: "/routines" },
  { id: "growth", hash: "/growth" },
  { id: "your-data", hash: "/your-data" },
  { id: "settings", hash: "/home?settings=live-models", sheet: true },
];
/** Retired as worker destinations: the route must redirect to a worker destination (or, for admin-only content, show the gate). */
const RETIRED = [
  { id: "queue", to: "worker" }, { id: "briefing", to: "worker" }, { id: "repeats", to: "worker" }, { id: "privacy", to: "worker" }, { id: "memory", to: "worker" },
  { id: "notices", to: "worker" }, { id: "settings-old", hash: "/settings", to: "worker" },
  { id: "genome", to: "worker" }, { id: "presence", to: "worker" }, { id: "week", to: "worker" }, { id: "graph", to: "worker" }, { id: "today", to: "worker" }, { id: "git", to: "worker" },
  { id: "agents", to: "worker" },
  { id: "models", to: "gate" }, { id: "evidence", to: "gate" }, { id: "forecasts", to: "gate" }, { id: "predictions", to: "gate" },
];
const WORKER_LANDINGS = ["home", "needs-you", "routines", "growth", "your-data", "setup", "first-run"];
/** Admin screens. `content` says what the engine must have answered for the screen to count as showing something. */
const ADMIN_ROUTES = [
  { id: "firm", hash: "/firm", content: "overview" },
  { id: "roles", hash: "/roles", content: "roles" },
  { id: "firm/people", hash: "/firm/people", content: "people" },
  { id: "onboarding", hash: "/onboarding", content: "onboarding" },
  { id: "firm/automation", hash: "/firm/automation", content: "automation" },
  { id: "firm/risk", hash: "/firm/risk", content: "overview" },
  { id: "firm/forecasts", hash: "/firm/forecasts", content: "text" },
  { id: "firm/brief", hash: "/firm/brief", content: "overview" },
  { id: "models", hash: "/models", content: "text" },
  { id: "evidence", hash: "/evidence", content: "text" },
  { id: "agents", hash: "/agents", content: "text" },
];
/** Admin routes the worker view must gate. `onboarding` is the worker's own set-up in the Worker view (routeRedirects.ts), so it is judged as a redirect. */
const GATED_FOR_WORKER = ADMIN_ROUTES.filter((r) => !["onboarding"].includes(r.id));
const MIN_PEOPLE = 5;

// ---------------------------------------------------------------------------------------------- a private stack
function findMainCheckout() {
  const r = spawnSync("git", ["rev-parse", "--git-common-dir"], { cwd: repo, encoding: "utf8" });
  const g = r.status === 0 ? r.stdout.trim() : "";
  return g ? dirname(resolve(repo, g)) : repo;
}
const mainRoot = findMainCheckout();
const firstExisting = (...c) => c.find((p) => p && existsSync(p));
const PYTHON = firstExisting(process.env.KNACK_PYTHON, join(repo, ".venv/bin/python"), join(mainRoot, ".venv/bin/python"));
const DASH_DIR = join(repo, "apps/dashboard");
const SYNTH_SRC = firstExisting(process.env.KNACK_SYNTHETIC, join(repo, "data"), join(mainRoot, "data"));

function playwrightFrom() {
  for (const base of [DASH_DIR, join(mainRoot, "apps/dashboard"), repo]) {
    try { return createRequire(join(base, "package.json"))("playwright"); } catch { /* try the next */ }
  }
  throw new Error("playwright is not installed (cd apps/dashboard && npm install)");
}

async function startStack(procs) {
  if (!PYTHON) throw new Error("no python: run `uv sync --all-packages` (or set KNACK_PYTHON)");
  if (!existsSync(join(DASH_DIR, "node_modules/.bin/vite"))) throw new Error(`no ${DASH_DIR}/node_modules: run npm install in apps/dashboard (or symlink the main checkout's node_modules)`);
  if (!SYNTH_SRC || !existsSync(join(SYNTH_SRC, "synthetic/learners/events.jsonl"))) throw new Error("data/synthetic/learners is missing (uv run understudy synth --all), or set KNACK_SYNTHETIC to a data directory that holds it");
  const root = mkdtempSync(join(process.env.KNACK_TMP ?? tmpdir(), "knack-view-audit-"));
  const dataParent = join(root, "data");
  const data = join(dataParent, "live-data");
  const home = join(root, "home");
  mkdirSync(data, { recursive: true });
  mkdirSync(home);
  for (const n of ["synthetic", "golden", "voice_cache", "eval"]) if (existsSync(join(SYNTH_SRC, n))) symlinkSync(join(SYNTH_SRC, n), join(dataParent, n));
  writeFileSync(join(data, ".understudy-demo-data"), "view-audit throwaway\n");
  const mock = argv.includes("--mock") ? "1" : "0";
  const env = {
    PATH: process.env.PATH, HOME: process.env.HOME, PYTHONPATH: [join(repo, "services/engine"), join(repo, "services/agent")].join(":"),
    UNDERSTUDY_HOME: home, UNDERSTUDY_DATA_DIR: data, UNDERSTUDY_MOCK: mock, AGENT_PORT: "1",
  };
  const seed = spawnSync(PYTHON, ["-m", "understudy_engine.demo", "seed", "--no-bundle"], { cwd: root, env, encoding: "utf8", timeout: 240_000 });
  if (seed.status !== 0) throw new Error(`the seed failed (exit ${seed.status}): ${(seed.stderr || seed.stdout).slice(-600)}`);
  if (VERBOSE) console.log(seed.stdout.split("\n").map((l) => "  seed: " + l).join("\n"));
  const ePort = await freePort();
  procs.start("engine", PYTHON, ["-m", "understudy_engine.cli", "serve", "--port", String(ePort)], { cwd: root, env: { ...env, ENGINE_PORT: String(ePort) } });
  const engine = `http://127.0.0.1:${ePort}`;
  await until(() => getJson(`${engine}/health`, {}, 2000).then((r) => r.status === 200).catch(() => false), 120_000, "the private engine", 400);
  const dPort = await freePort();
  procs.start("dashboard", join(DASH_DIR, "node_modules/.bin/vite"), ["--config", "scripts/vite.qa.config.ts"], {
    cwd: DASH_DIR, env: { PATH: process.env.PATH, HOME: process.env.HOME, QA_PORT: String(dPort), ENGINE_PORT: String(ePort), AGENT_PORT: "1", UNDERSTUDY_DATA_DIR: data },
  });
  const dashboard = `http://127.0.0.1:${dPort}`;
  await until(() => getJson(dashboard, {}, 2000).then((r) => r.status === 200).catch(() => false), 120_000, "the private dashboard", 400);
  return { root, engine, dashboard, data };
}

// ---------------------------------------------------------------------------------------------- reading a page
/** Text of the page: `full` (every text node, closed disclosures included), `visible` (what is drawn), both without any "Advanced" disclosure. */
const PAGE_TEXT = (sheet) => {
  const root = (sheet ? document.querySelector('[role="dialog"]') : null) ?? document.querySelector('#main') ?? document.body;
  const advanced = [...document.querySelectorAll('details')].filter((d) => /^\s*advanced\b/i.test(d.querySelector('summary')?.textContent ?? ''));
  const inAdvanced = (n) => advanced.some((a) => a.contains(n));
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const p = n.parentElement;
    if (!p || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(p.tagName) || inAdvanced(n)) continue;
    parts.push(n.textContent);
  }
  const saved = advanced.map((a) => [a, a.style.display]);
  advanced.forEach((a) => { a.style.display = 'none'; });
  const visible = root.innerText ?? '';
  saved.forEach(([a, d]) => { a.style.display = d; });
  return { full: parts.join(' ').replace(/\s+/g, ' ').trim(), visible: visible.replace(/\s+/g, ' ').trim(), advancedClosed: advanced.length };
};

async function visit(browser, base, view, route, names) {
  const { openAs } = await import(pathToFileURL(join(DASH_DIR, "scripts/lib/knack-page.mjs")).href);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const calls = [];
  const blocked = [];
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => {
    const m = r.request().method();
    if (m !== "GET" && m !== "HEAD") { blocked.push(`${m} ${new URL(r.request().url()).pathname}`); return r.abort(); }
    return r.continue();
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
  page.on("response", async (res) => {
    const u = new URL(res.url());
    if (!/^\/(engine|agent)\//.test(u.pathname)) return;
    let body = "";
    try { body = (await res.body()).toString("utf8"); } catch { /* aborted */ }
    calls.push({ path: u.pathname.replace(/^\/(engine|agent)/, ""), search: u.search, status: res.status(), size: body.length, body: body.length < 600_000 ? body : "" });
  });
  const ok = await openAs(page, base, view);
  calls.length = 0;
  await page.goto(`${base}/#${route.hash ?? "/" + route.id}`);
  // settle: the first hit of a cold dev server compiles for a while, so wait until the engine calls and the drawn text have both stopped changing
  let lastCalls = -1, lastLen = -1, still = 0;
  for (let i = 0; i < 50 && still < 3; i++) {
    await page.waitForTimeout(600);
    const len = await page.evaluate((sheet) => ((sheet ? document.querySelector('[role="dialog"]') : null) ?? document.querySelector("#main") ?? document.body).innerText.length, !!route.sheet).catch(() => -1);
    still = calls.length === lastCalls && len === lastLen && len > 20 ? still + 1 : 0;
    lastCalls = calls.length;
    lastLen = len;
  }
  if (route.sheet) await page.waitForTimeout(500);
  const landed = new URL(page.url()).hash.replace(/^#/, "");
  const texts = await page.evaluate(PAGE_TEXT, !!route.sheet);
  await ctx.close();
  return { ok, landed, texts, calls, blocked, errors };
}

const landedId = (landed) => (landed.split("?")[0].split("/")[1] ?? "").toLowerCase();

// ---------------------------------------------------------------------------------------------- the audit
function workerChecks(r, route, { names }) {
  const v = workerTextViolations(r.texts, { route: route.id, own: { id: OWN_ID, names: [] }, names });
  const warns = [];
  const seen = new Set();
  for (const c of r.calls) {
    if (isFirmEndpoint(c.path)) v.push({ rule: "firm-endpoint", where: "api", endpoint: c.path, why: "a worker page fetched firm or admin data", match: c.path, snippet: `GET ${c.path}${c.search} -> ${c.status}` });
    if (c.body && c.status < 400) for (const x of apiIdentityViolations(c.body, { own: { id: OWN_ID, names: [] }, names })) v.push({ ...x, endpoint: c.path, snippet: `${c.path}: ${x.snippet}` });
    if (isInternalEndpoint(c.path) && route.id !== "settings" && !seen.has(c.path)) { seen.add(c.path); warns.push(`${c.path} (${c.status})`); }
  }
  return { v: summarise(v), warns };
}

function fmt(v) {
  const n = v.count > 1 ? ` x${v.count}` : "";
  return `      [${v.rule}${n}] ${v.where === "api" ? "api " : ""}${JSON.stringify(v.snippet)}  (${v.why})`;
}

async function main() {
  const procs = new Procs();
  let stack = null;
  const results = [];
  const report = (view, id, status, lines, extra = {}) => {
    results.push({ view, route: id, status, lines, ...extra });
    console.log(`${status}  ${view.padEnd(6)} #/${id}${extra.landed && extra.landed !== `/${id}` ? `  (landed ${extra.landed})` : ""}`);
    for (const l of lines) console.log(l);
  };
  let exit = 0;
  try {
    const pw = playwrightFrom();
    let dashboard = flag("dashboard", null);
    let engine = flag("engine", null);
    if (!dashboard || !engine) {
      console.log("starting a private stack (throwaway data, no keys, no agent) ...");
      stack = await startStack(procs);
      dashboard = stack.dashboard;
      engine = stack.engine;
      console.log(`  engine ${engine}  dashboard ${dashboard}  data ${stack.data}${argv.includes("--mock") ? " (mock on)" : ""}\n`);
    }
    const dash = String(dashboard).replace(/\/$/, "");
    // the firm's own names, labels and ids: the engine's name list, and the roster the engine serves (admin GET through the dashboard's token proxy)
    const nameFile = join(repo, "services/engine/understudy_engine/insights/names.py");
    const names = new Set(existsSync(nameFile) ? [...readFileSync(nameFile, "utf8").matchAll(/"([A-Z][^"]+ [^"]+)"/g)].map((m) => m[1]) : []);
    const adminGet = (path) => getJson(`${dash}/engine${path}`, { headers: { "x-understudy-role": "admin" } }, 30_000).catch(() => ({ status: 0, body: null }));
    const firmApi = await adminGet("/insights/admin/firm");
    for (const g of firmApi.body?.data?.roles ?? []) for (const p of g.people ?? g.users ?? []) if (p.name) names.add(p.name);
    const nameList = [...names];
    const browser = await pw.chromium.launch();
    const want = (view, id) => (ONLY === "all" || ONLY === view) && (!ROUTES || ROUTES.includes(id));

    // ------------------------------------------------------------------ WORKER: own routes
    if (ONLY === "all" || ONLY === "worker") {
      console.log("== WORKER view: worker routes");
      for (const route of WORKER_ROUTES.filter((r) => want("worker", r.id))) {
        const r = await visit(browser, dash, "worker", route, nameList);
        const { v, warns } = workerChecks(r, route, { names: nameList });
        const lines = v.map(fmt).concat(warns.length ? [`      WARN  fetched internals: ${warns.join(", ")}`] : []);
        if (r.texts.full.length < 40) lines.push("      [blank] the page drew almost no text");
        report("worker", route.id, v.length || r.texts.full.length < 40 ? "FAIL" : "PASS", lines, { landed: r.landed, violations: v, warns });
      }
      console.log("\n== WORKER view: retired routes (must redirect to a worker destination, or show the gate)");
      for (const route of RETIRED.filter((r) => want("worker", r.id))) {
        const r = await visit(browser, dash, "worker", { ...route, hash: route.hash ?? `/${route.id}` }, nameList);
        const where = landedId(r.landed);
        const lines = [];
        let fail = false;
        const gate = GATE.re.test(r.texts.visible) && r.texts.visible.length <= GATE.maxChars;
        if (route.to === "gate") {
          if (!gate && !WORKER_LANDINGS.includes(where)) { fail = true; lines.push(`      [not-gated] ${JSON.stringify(r.texts.visible.slice(0, 90))} (an admin-only screen must show only the gate sentence or redirect)`); }
        } else if (!WORKER_LANDINGS.includes(where)) {
          fail = true;
          lines.push(`      [not-redirected] the retired route still renders its own screen at #${r.landed}; views.md says it redirects into a worker destination`);
        }
        const { v, warns } = workerChecks(r, { id: where || route.id }, { names: nameList });
        if (v.length && !gate) { fail = true; lines.push(...v.map(fmt)); }
        if (warns.length) lines.push(`      WARN  fetched internals: ${warns.join(", ")}`);
        report("worker", route.id, fail ? "FAIL" : "PASS", lines, { landed: r.landed, violations: v });
      }
      console.log("\n== WORKER view: admin routes (only the gate sentence, no admin call)");
      for (const route of GATED_FOR_WORKER.filter((r) => want("worker", r.id))) {
        const r = await visit(browser, dash, "worker", route, nameList);
        const lines = [];
        const text = r.texts.visible;
        const gate = GATE.re.test(text);
        const fired = r.calls.filter((c) => isFirmEndpoint(c.path));
        if (!gate) lines.push(`      [no-gate] the page does not say "Switch to Admin": ${JSON.stringify(text.slice(0, 110))}`);
        else if (text.length > GATE.maxChars) lines.push(`      [more-than-gate] the gate sentence is followed by more content (${text.length} characters): ${JSON.stringify(text.slice(0, 110))}`);
        for (const c of fired) lines.push(`      [admin-call] GET ${c.path} -> ${c.status}`);
        if (!(gate && text.length <= GATE.maxChars)) for (const x of summarise(workerTextViolations(r.texts, { route: "gate", own: { id: OWN_ID }, names: nameList }))) lines.push(fmt(x));
        report("worker", route.id, lines.length ? "FAIL" : "PASS", lines, { landed: r.landed });
      }
    }

    // ------------------------------------------------------------------ ADMIN
    if (ONLY === "all" || ONLY === "admin") {
      console.log("\n== ADMIN view: every admin route shows content");
      const api = {};
      for (const [k, p] of Object.entries({ overview: "/insights/admin/overview", roles: "/insights/admin/roles", firm: "/insights/admin/firm", onboarding: "/insights/admin/onboarding", hits: "/hitlist/firm?window=7" })) {
        const x = await adminGet(p);
        api[k] = { status: x.status, body: x.body };
      }
      const d = (k) => api[k].body?.data ?? null;
      const preds = {
        overview: () => {
          const o = d("overview");
          if (!o) return `the engine answered ${api.overview.status} with no data`;
          if ((o.firm?.users ?? 0) < MIN_PEOPLE) return `overview says ${o.firm?.users ?? 0} people (source ${api.overview.body?.meta?.source}); fewer than ${MIN_PEOPLE}, so nothing can be compared`;
          if (!(o.top?.length || o.role_comparison?.length)) return "overview has no insight and no role comparison";
          return null;
        },
        roles: () => {
          const o = d("roles");
          if (!o) return `the engine answered ${api.roles.status} with no data`;
          if (!o.roles?.length) return `roles is empty (source ${api.roles.body?.meta?.source})`;
          if (!o.roles.some((r) => !r.reason && (r.habits?.length || r.gap))) return "no role has a comparison (every role is suppressed)";
          return null;
        },
        people: () => {
          const o = d("firm");
          if (!o) return `the engine answered ${api.firm.status} with no data`;
          if ((o.totals?.users ?? 0) < MIN_PEOPLE) return `people list holds ${o.totals?.users ?? 0} people (source ${api.firm.body?.meta?.source})`;
          return null;
        },
        onboarding: () => {
          const o = d("onboarding");
          if (!o) return `the engine answered ${api.onboarding.status} with no data`;
          if (!o.roles?.length) return `onboarding has no role with a curve (source ${api.onboarding.body?.meta?.source})`;
          return null;
        },
        automation: () => {
          const o = d("hits");
          if (!o) return `the engine answered ${api.hits.status} with no data`;
          if (!o.rows?.length) return "no repeated action is listed for the firm";
          if ((o.total?.people ?? 0) < MIN_PEOPLE) return `automation counts ${o.total?.people ?? 0} people`;
          return null;
        },
        text: () => null,
      };
      for (const route of ADMIN_ROUTES.filter((r) => want("admin", r.id))) {
        const r = await visit(browser, dash, "admin", route, nameList);
        const lines = [];
        const text = r.texts.visible;
        const head = /^(?:Firm\s*›?\s*)?[A-Za-z ]{0,40}?Admin view\b/;
        const body = text.replace(head, "").trim();
        if (!r.ok) lines.push("      [not-admin] the page did not switch to the Admin view");
        if (GATE.re.test(text) && text.length <= GATE.maxChars) lines.push("      [gated] the Admin view shows the gate sentence");
        if (body.length < 250) lines.push(`      [blank] only ${body.length} characters of content: ${JSON.stringify(body.slice(0, 100))}`);
        if (/\b0 people\b|\b0 of 0\b|\(0\)/.test(text)) lines.push(`      [zeros] the screen draws zeros: ${JSON.stringify((text.match(/.{0,30}(?:\b0 people\b|\b0 of 0\b|\(0\)).{0,30}/) ?? [""])[0])}`);
        const miss = preds[route.content]?.();
        if (miss) lines.push(`      [empty-answer] ${miss}`);
        report("admin", route.id, lines.length ? "FAIL" : "PASS", lines, { landed: r.landed });
      }
      if (want("admin", "consistency")) {
        console.log("\n== ADMIN view: the same people numbers add up on every screen");
        const ov = d("overview"), fm = d("firm"), hit = d("hits"), rl = d("roles"), on = d("onboarding");
        const lines = [];
        const people = ov?.firm?.users ?? 0;
        const facts = { "overview users": people, "people list users": fm?.totals?.users, "coverage users": ov?.coverage?.users, "automation people": hit?.total?.people, "roles (experts + juniors)": rl?.roles ? rl.roles.reduce((s, x) => s + (x.n_expert ?? 0) + (x.n_junior ?? 0), 0) : undefined };
        for (const [k, val] of Object.entries(facts)) if (val === undefined || val !== people) lines.push(`      [mismatch] ${k} = ${val}, overview says ${people}`);
        const byRole = Object.fromEntries((ov?.coverage?.roles ?? []).map((x) => [x.role, x.users]));
        for (const g of fm?.roles ?? []) {
          const n = Array.isArray(g.users) ? g.users.length : g.n;
          if (byRole[g.role] !== undefined && n !== byRole[g.role]) lines.push(`      [mismatch] people list role ${g.role} = ${n}, coverage says ${byRole[g.role]}`);
        }
        if (on?.roles && ov?.coverage?.roles) for (const o of on.roles) if ((byRole[o.role] ?? 0) < (o.n ?? 0)) lines.push(`      [mismatch] onboarding counts ${o.n} juniors in ${o.role}, coverage counts ${byRole[o.role]} people`);
        report("admin", "consistency", lines.length ? "FAIL" : "PASS", lines, { facts });
      }
    }
    await browser.close();
  } finally {
    await procs.stopAll();
    if (stack && !argv.includes("--keep")) removeTree(stack.root);
    else if (stack) console.log(`kept ${stack.root}`);
  }
  const fails = results.filter((r) => r.status === "FAIL");
  console.log(`\n${results.length - fails.length} PASS, ${fails.length} FAIL`);
  const out = flag("json", null);
  if (typeof out === "string") { mkdirSync(dirname(resolve(out)), { recursive: true }); writeFileSync(resolve(out), JSON.stringify({ generated: new Date().toISOString(), results }, null, 2)); console.log(`wrote ${out}`); }
  exit = fails.length ? 1 : 0;
  process.exit(exit);
}

main().catch((e) => { console.error(`view-audit could not run: ${e.message}`); process.exit(2); });
