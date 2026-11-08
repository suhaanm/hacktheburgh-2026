// Interaction smoke test against the running dev server (demo-data mode, no engine needed).
// Usage: node scripts/smoke.mjs [http://127.0.0.1:5173]   Screenshots go to qa/.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const qa = join(dirname(fileURLToPath(import.meta.url)), "..", "qa");
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
// Demo-data mode on purpose: block the engine and agent so the checks are deterministic and never write to a live memory file.
// The page reaches the services only through its own origin: /engine/* and /agent/* (the Vite server forwards them).
const ANY_SERVICE = /^https?:\/\/[^/]+\/(engine|agent)(\/|$)/;
const ENGINE = /^https?:\/\/[^/]+\/engine(\/|$)/;
await ctx.route(ANY_SERVICE, (route) => route.abort());
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !/ERR_CONNECTION_REFUSED|Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`); });
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); if (!ok) failed++; };
// A Hint opens on click and its note is the button's description: read it from there, then close it. A closed Details is opened before its text is read.
const hintText = async (scope, name) => {
  const b = scope.getByRole("button", { name }).first();
  await b.click();
  const id = await b.getAttribute("aria-describedby");
  const t = id ? await page.locator(`[id="${id}"]`).innerText() : "";
  await page.keyboard.press("Escape");
  return t;
};
// The question box of Explain is one closed row, "Ask about this case": open it when it is shut.
const openAsk = async (scope) => { const d = scope.locator("details").filter({ has: page.locator("summary", { hasText: "Ask about this case" }) }).first(); if (!(await d.evaluate((e) => e.open))) await d.locator("summary").first().click(); };
const openAll = (scope) => scope.locator("details").evaluateAll((els) => els.forEach((e) => { e.open = true; }));
const go = async (hash, wait = 700) => {
  // Same-hash navigations do not remount, so hop through another route first.
  if (page.url().endsWith(`#${hash}`)) { await page.goto(`${base}/#/today`); await page.waitForTimeout(150); }
  await page.goto(`${base}/#${hash}`); await page.waitForTimeout(wait);
};

// The view role is remembered on this device and read when the page loads, so changing it is a write and a reload. A worker has five screens; the screens that
// belong to the firm (Evidence, Models and cost, Background runs, the Firm views) and the older work views that Growth now bridges are measured as an admin, where
// they are not behind the gate or the cohort guard.
const asView = async (v) => {
  await page.evaluate((role) => { try { if (role === "admin") localStorage.setItem("understudy-view-as", "admin"); else localStorage.removeItem("understudy-view-as"); } catch { /* */ } }, v);
  await page.reload();
  await page.waitForTimeout(600);
};

// 1. First run (the old Onboarding): two roles, timed. Set up again reruns the same three screens in a browser tab: role, what Knack may do, then Show my week.
// A role card opens its connection chips with a Continue button (owner choice D55, components/connections/ConnectionChips): one more click, then the consent screen.
// "Not sure yet" has no chips and goes straight on.
const pickRole = async (label) => {
  await page.locator(".rolecard__btn", { hasText: label }).click();
  await page.waitForTimeout(250);
  const cont = page.getByRole("button", { name: "Continue" });
  if (await cont.isVisible().catch(() => false)) await cont.click();
};

// With no engine the write cannot reach a memory file, so this section reads what the page SENDS: the request to /engine/onboarding is answered here (and recorded),
// and the file the engine writes from it is the engine's own test (services/engine/tests). What is checked is the contract: the role, the capture answer as a boolean
// the worker's click decided, sent as the worker, once per first run.
// (The services are answered with a 503 here rather than refused: a refused connection makes the page skip that service for six seconds, and the write would never be sent.)
const onboarded = [];
const SERVICES_HERE = ANY_SERVICE;
await page.route(SERVICES_HERE, async (route) => {
  const req = route.request();
  if (!(req.method() === "POST" && /^https?:\/\/[^/]+\/engine\/onboarding$/.test(req.url()))) {
    return route.fulfill({ status: 503, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ error: { code: "unavailable", message: "Not running." } }) });
  }
  const body = JSON.parse(req.postData() ?? "{}");
  onboarded.push({ body, actor: req.headers()["x-understudy-actor"], type: req.headers()["content-type"] });
  return route.fulfill({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ data: { person: "p_you", role: body.role, revision: 1, memory_markdown: "", risk_classes: { irreversible: [] }, tone: { length: "short", voice: "plain" }, pace: "gradual" } }) });
});
for (const [role, pack] of [["UK benefits processor", "benefits-processor"], ["Data analyst", "data-analyst"]]) {
  await go("/setup");
  const t0 = Date.now();
  const before = onboarded.length;
  await pickRole(role);
  const cards = page.locator(".consent");
  check(`first run ${pack}: capture is never pre-selected (nothing is answered until a real click)`, (await page.getByRole("heading", { name: "What may Knack do?" }).count()) === 1 && (await cards.locator("button[aria-pressed=true]").count()) === 0);
  check(`first run ${pack}: nothing is written before the worker answers`, onboarded.length === before);
  await cards.first().getByRole("button", { name: pack === "benefits-processor" ? "Yes" : "Not now" }).click();
  await page.getByRole("button", { name: "Show my week" }).waitFor();
  const secs = (Date.now() - t0) / 1000;
  const sent = onboarded[onboarded.length - 1];
  check(`first run ${pack}: written once, in under 60 s`, onboarded.length === before + 1 && secs < 60, `${secs.toFixed(1)} s, ${onboarded.length - before} write(s)`);
  check(`first run ${pack}: the role is sent, as the worker, as JSON`, sent?.body.role === pack && sent?.actor === "worker" && /application\/json/.test(sent?.type ?? ""), JSON.stringify(sent?.body.role));
  check(`first run ${pack}: capture is on only when the worker said yes (a boolean, never a default)`, sent?.body.answers?.capture === (pack === "benefits-processor"), JSON.stringify(sent?.body.answers?.capture));
  await page.getByRole("button", { name: "Show my week" }).click();
  await page.waitForTimeout(400);
  if (pack === "benefits-processor") await page.screenshot({ path: join(qa, "onboarding-done-1440.png") });
}
check("first run: two roles send different files", onboarded.length === 2 && onboarded[0].body.role !== onboarded[1].body.role);
await page.unroute(SERVICES_HERE);

// 2. First run mid-flow screenshot (the consent screen), and Not sure yet writes nothing
await go("/setup");
await pickRole("Data analyst");
await page.waitForTimeout(300);
await page.screenshot({ path: join(qa, "onboarding-question-1440.png") });
await go("/setup");
await pickRole("Not sure yet");
check("first run: Not sure yet picks nothing and still reaches the consent screen", (await page.getByRole("heading", { name: "What may Knack do?" }).count()) === 1);

// 3. Graph: open a node, panel shows why
await go("/graph", 2600);
await page.locator(".gnode").first().click();
await page.waitForTimeout(500);
check("graph: panel shows why the node exists", await page.getByText("Why it exists", { exact: true }).isVisible());
await page.screenshot({ path: join(qa, "graph-panel-1440.png") });
// delete a memory node (forget)
await page.locator(".gnode[aria-label^='Memory: Short summaries']").click();
await page.getByRole("button", { name: "Forget this line" }).click();
await page.getByRole("button", { name: "Yes, remove" }).click();
await page.waitForTimeout(900);
check("graph: forgetting a memory node removes it", (await page.locator(".gnode[aria-label^='Memory: Short summaries']").count()) === 0);
// Your data: what Knack remembers is the first section and is open by default; every edit and delete here is a line in the file.
const showAll = async (scope = page) => { const all = scope.getByRole("button", { name: /^Show all \d+$/ }); if (await all.count()) await all.first().click(); };
const remembered = async () => { await openAll(page.locator("[data-testid=remembers]")); return page.locator("[data-testid=remembers]").innerText(); };   // the lines past the first three sit behind More
await go("/your-data");
check("your data: the forgotten line is gone from the file", !(await remembered()).includes("Summaries: short"));
const yd = await page.locator("main").innerText();
check("your data: no file path and none of the old name is on the screen by default", !/(\.understudy|\/Users\/|\/home\/|demo-home|\.md\b)/i.test(yd) && !/\bunderstudy\b/i.test(yd));

// 3b. Capture and screen glances: capture is just a line in the file
await go("/your-data?section=switches");
const capSw = page.getByRole("switch", { name: "Learn from when I am active" });
const wasOn = await capSw.isChecked();
check("your data: the capture consent is printed whole beside its switch", /never what you read: no page text, no URLs, no field values/.test(await page.locator("[data-testid=switch-capture]").innerText()));
await page.locator("[data-testid=switch-capture] .toggle").click();
await page.waitForTimeout(600);
check("your data: the capture switch flips", (await capSw.isChecked()) === !wasOn);
await go("/your-data");
check("your data: the file holds the capture line only when capture is on", wasOn ? !/Capture: times only/.test(await remembered()) : /Capture: times only/.test(await remembered()));

// 4. Your data: edit a line, then edit as text
await remembered();
await page.locator(".yd-line", { hasText: "Working hours" }).hover();
await page.getByRole("button", { name: /^Edit: Working hours/ }).click({ force: true });
await page.waitForTimeout(200);
await page.locator(".yd-line--edit input").fill("Working hours: Tue to Sat, 10:00 to 18:00.");
await page.getByRole("button", { name: "Save line" }).click();
await page.waitForTimeout(700);
check("your data: line edit saved", (await remembered()).includes("Tue to Sat, 10:00"));
await openAll(page.locator("[data-testid=remembers]"));
await page.getByRole("button", { name: "Edit as text" }).click();
const ta = page.locator("#memtext");
const cur = await ta.inputValue();
await ta.fill(cur + "\n");
check("your data: revision bumped after edits", /revision: 1[3-9]/.test(cur));
await page.screenshot({ path: join(qa, "memory-edit-1440.png") });

// 5. Needs you: Watch first moves a proposal into Routines, Running
await go("/needs-you");
const proposalRow = (title) => page.locator("article[data-kind=proposal]", { hasText: title });
check("needs you: a routine proposal is on screen without opening the rest, so Watch first is two clicks from Home", (await proposalRow("Enter the household into three calculators").count()) === 1);
await proposalRow("Enter the household into three calculators").getByRole("button", { name: "Watch first" }).click();
await page.waitForTimeout(900);
check("needs you: a proposal leaves the list after a choice", (await proposalRow("Enter the household into three calculators").count()) === 0);
await go("/routines");
check("routines: it now lists as running, watching first", await page.getByText("Enter the household into three calculators").first().isVisible());

// 5b. Needs you: the skill gate refuses, and "I already know this one" re-sends with the override
await go("/needs-you");
await showAll();
await proposalRow("Reconcile the three results").getByRole("button", { name: "Watch first" }).click();
await page.waitForTimeout(400);
check("needs you: skill gate explains itself in plain words", await page.getByText("would rather coach you on this one first").isVisible());
await page.getByRole("button", { name: "I already know this one" }).click();
await page.waitForTimeout(900);
check("needs you: the override goes through and the proposal leaves", (await proposalRow("Reconcile the three results").count()) === 0);

// 5c. Routines: Run now is on the closed row (two clicks from Home); with no agent service it says so and starts nothing
await go("/routines");
const copyRow = page.locator("article.rt-row", { hasText: "Copy the three results" });
check("routines: Run now is on the closed row", await copyRow.getByRole("button", { name: "Run now" }).isVisible());
await copyRow.getByRole("button", { name: "Run now" }).click();
await page.waitForTimeout(500);
check("routines: with no agent service Run now says nothing started", /nothing started/.test(await copyRow.locator("[data-testid=ran]").innerText()));

// 6. Routines: typed confirmation required for model-driven irreversible opt-in
await go("/routines");
const cliffs = page.locator("article.rt-row", { hasText: "Re-check benefit cliffs" });
await cliffs.locator(".rt-row__open").click();
await cliffs.getByRole("button", { name: "Run while I'm away" }).click();   // one click reveals the irreversible choices; nothing is saved yet
await cliffs.getByText("Allow “submit” without asking me").click();
const away = cliffs.getByRole("button", { name: "Allow while I'm away" });
check("routines: irreversible away opt-in blocked without typed confirmation", await away.isDisabled());
await cliffs.locator("input.input").fill("monday-cliff-check");
check("routines: allowed once the id is typed", await away.isEnabled());
await cliffs.scrollIntoViewIfNeeded(); await page.screenshot({ path: join(qa, "routines-away-1440.png") });

// 7. Needs you: a key never approves, then a real click does
await go("/needs-you");
const submitHead = page.getByRole("heading", { name: "Submit case note CN-2041" });
const submitRow = page.locator("li", { has: submitHead }).first();
await submitRow.focus();
await page.keyboard.press("Space"); await page.keyboard.press("Enter"); await page.keyboard.press("ArrowDown");
await page.waitForTimeout(300);
check("needs you: no key approves or rejects (the item is still waiting)", (await submitHead.count()) === 1);
check("needs you: the consequence is printed as plain text next to the buttons", /Cannot be undone\./.test(await page.locator("article[data-kind=approval][data-risk=irreversible]").first().innerText()));
await page.getByRole("button", { name: "Approve and submit" }).click();
await page.waitForTimeout(700);
check("needs you: approving decides the item", (await submitHead.count()) === 0);

// 8. Presence: quiet hours save changes idle capacity (Growth, section time: /presence redirects there; the hours sit in closed disclosures, so they are opened first)
await go("/presence", 1200);
await openAll(page.locator("main"));
const idleStat = page.locator("section[aria-labelledby=idle-h] .stat__value");
const idle0 = await idleStat.first().innerText();
await page.locator("#qs").fill("01:00");
await page.locator("#qe").fill("11:00");
await page.getByRole("button", { name: "Save quiet hours" }).click();
await page.waitForTimeout(900);
await openAll(page.locator("main"));
const idle1 = await idleStat.first().innerText();
check("presence: saving quiet hours recomputes idle capacity", idle0 !== idle1, `${idle0.replace(/\n/g, " ")} -> ${idle1.replace(/\n/g, " ")}`);
await page.locator("#gr-time svg[role='application']").first().focus();   // the weekly map (the progress chart above it has the same role)
await page.keyboard.press("ArrowRight");
await page.waitForTimeout(150);
check("presence: arrow keys read a cell with its interval", (await page.locator("#gr-time p[aria-live]").allInnerTexts()).some((t) => /95% interval/.test(t)));

// 8b. Evidence: honest states (a reviewer's screen, behind the gate for a worker: read as an admin)
await asView("admin");
await go("/evidence", 1200);
check("evidence: high limits are open, medium and low are folded, and there is a sticky jump list", (await page.locator("#limits .limit:visible").count()) > 0 && (await page.locator("details.limits-fold:not([open])").count()) === 2 && (await page.locator("nav.ev-jump a").count()) >= 10 && (await page.locator("nav.ev-jump").evaluate((el) => getComputedStyle(el).position)) === "sticky");
await page.locator("main details").evaluateAll((els) => els.forEach((e) => (e.open = true)));
const ev = await page.locator("main").innerText();
check("evidence: a not-run study says so and prints no defaults", /has not run yet/.test(ev) && !/changed by [+\u2212-]?0 s/.test(ev));
const pres = await page.locator("#presence").innerText();
check("evidence: presence baselines show interruption and idle time, never a 0.000 Brier", /Fixed overnight window/.test(pres) && !/0\.000/.test(pres));
check("evidence: ski rental and off-policy show the engine's labels", /Ski rental with predictions/.test(ev) && /Doubly robust/.test(ev));
check("evidence: pooling appears", /Partial pooling/.test(ev));
const mapText = await page.locator(".ev-map").innerText();
check("evidence: the map lists every section with its Measured on words, n and status, and names language-model participants as not people", (await page.locator(".ev-map__table tbody tr").count()) >= 20 && /Every part of the report/.test(ev) && /Measured on/.test(mapText) && /generators we wrote/.test(mapText) && !/synthetic|simulated/i.test(mapText) && (/Language-model participants are language models playing workers\. They are not people/.test(mapText) || (await page.locator(".ev-map__table", { hasText: /language-model participants/i }).count()) === 0));
check("evidence: the privacy block states planted strings, leaks and which layers have a real-code check", /planted test strings/.test(ev) && (await page.locator("[data-testid=ev-layers] tbody tr").count()) >= 5 && /evidence from planted strings, not a proof/i.test(ev));
check("evidence: limitations carry their source", /From: engine-eval · null placebo/.test(ev));
{
  // The real-model block: every count is printed with its condition, and the fix is marked in-sample. No bare totals.
  const liveBlock = page.locator("[data-testid=live-runs]");
  const lv = await liveBlock.innerText();
  const clean = await liveBlock.locator("[data-testid=live-clean]").innerText();
  const glitch = await liveBlock.locator("[data-testid=live-glitch]").innerText();
  const injected = await liveBlock.locator("[data-testid=live-injected]").innerText();
  check("evidence: real-model block prints each count with its condition (clean 18 of 20, a 503 error 0 of 20 with 20 false claims)", /Clean pages: 18 of 20 passed/.test(clean) && /A 503 error mid-run: 0 of 20 passed, and 20 false claims/.test(glitch) && /Layout change: 20 of 20 passed/.test(lv));
  check("evidence: an injected-instruction row counts the pause, not a pass", /paused on 20 of 20 runs/.test(injected) && /not a pass/.test(injected));
  check("evidence: the fix is labelled in-sample and shows the result it replaces", /in-sample/i.test(await liveBlock.locator("[data-testid=live-fix]").innerText()) && /Before the fix, the same condition: 0 of 20 passed, 20 false claims/.test(lv));
  check("evidence: the real-model block says what it was run on (a real model, generated households, sandbox calculators; no origin tag for generated data) and says evidence, not proof", /real model/i.test(lv) && /generated households/.test(lv) && !/synthetic|simulated/i.test(lv) && (await liveBlock.locator(".pill--origin[data-origin=synthetic]").count()) === 0 && /evidence from a small run, not proof/.test(lv));
}
await page.screenshot({ path: join(qa, "evidence-1440.png") });
// A report full of stubs: reasons, not empty charts.
await page.route("**/eval/report", (route) => route.fulfill({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ generated_at: "2026-11-07T15:00:00Z", mock: true, sections: {
  hazard: { status: "pending", reason: "The hazard model is still being scored.", meta: { origin: "synthetic", n: 0, n_unit: "episodes", split: null, interval_level: 0.95, note: null, generated_at: "" } },
  deficit_recovery: { status: "failed", reason: "The apprentice traces could not be read.", meta: { origin: "synthetic", n: 0, n_unit: "personas", split: null, interval_level: 0.95, note: null, generated_at: "" } },
  study: { n: 4, meta: { origin: "real", n: 4, n_unit: "people", split: "within-subject, counterbalanced", interval_level: 0.95, note: null, generated_at: "" },
    headline: { mean_difference: 0.15, ci95: [-0.02, 0.31], per_participant_difference: [0.2, 0.1, 0.25, 0.05], sign_flip_p_two_sided: 0.125, smallest_possible_p: 0.125, ci_method: "t interval, n = 4" },
    rows: [{ participant: "Teammate A", unassisted_before_s: 410, unassisted_after_s: 380 }, { participant: "Teammate B", unassisted_before_s: 455, unassisted_after_s: 430 }, { participant: "Teammate C", unassisted_before_s: 398, unassisted_after_s: 351 }, { participant: "Teammate D", unassisted_before_s: 470, unassisted_after_s: 462 }],
    assisted_speed: { coached_mean_s: 301, uncoached_mean_s: 342 }, coach_use: { nudges_followed: 0.62 } },
  limitations: [{ id: "L1", text: "Only a stub report.", severity: "high", source: "all" }] } }) }));
// The API layer skips a service for 6 s after a refused connection; wait that out so this one request goes through the mock.
await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(6800); await page.goto(`${base}/#/evidence`); await page.waitForTimeout(1500);
const stubText = await page.locator("main").innerText();
check("evidence: pending and failed sections give their reason", /still being scored/.test(stubText) && /could not be read/.test(stubText));
check("evidence: a stub report still shows the limitations register", /Only a stub report/.test(stubText));
const studyText = await page.locator("#study").innerText();
check("study: headline is the skill difference with n, exact sign-flip p and the smallest possible p", /Coached minus uncoached unassisted skill: \+?0\.15/.test(studyText) && /p = 0\.125/.test(studyText) && /smallest p that is possible is 0\.125/.test(studyText) && /n = 4/.test(studyText));
check("study: time columns say uncoached and coached, never before and after", /Uncoached block, time/i.test(studyText) && /\bCoached block, time/i.test(studyText) && !/\bbefore\b|\bafter\b/i.test(await page.locator("#study table thead").innerText()));
check("study: assisted speed is reported separately", /Assisted speed, reported separately/i.test(studyText));
await page.unroute("**/eval/report");

await asView("worker");
// 8c. Today and the live coach brain (mocked engine so the checks are exact)
{
  let scenario = "nudge";
  const nextCalls = [];
  const feedback = [];
  const meta = { origin: "synthetic", n: 1, n_unit: "episodes", split: null, interval_level: 0.95, note: null, generated_at: "" };
  const baseDecision = { person: "p_t", action: "nudge", message: "Check the benefit cliff before you copy across.", why: "You skipped it on the last two cases.", target: { zone: "calc", label_hint: "Check cliff", role_hint: "button", site: "GovCalc" }, missed: ["CHECK_CLIFF"], confidence: 0.8, level: "L2", chip: "small", decision_id: "d1", task_id: "t1", step: 5, trigger: "skipped_check", reason_codes: ["rule_baseline"], gate: { consecutive: 2, reason: "two stuck signals" }, p_stuck: 0.62, p_source: "hazard model", candidate: null, mastery: { CHECK_CLIFF: 0.4 } };
  const scenarios = {
    nudge: baseDecision,
    silent: { ...baseDecision, action: "silent", message: "", why: "", decision_id: null, chip: "gone", reason_codes: ["gate_not_open"], candidate: { action: "nudge", message: "Compare all three results first.", why: "That is the order the expert uses.", target: null, trigger: "order", step: 5 } },
    study: { ...baseDecision, reason_codes: ["study_mode"], candidate: { action: "nudge", message: "SHOULD NOT SHOW", why: "x", target: null } },
  };
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }, body: JSON.stringify(body) });
  await page.route(ENGINE, async (route) => {
    const req = route.request(), u = new URL(req.url());
    u.pathname = u.pathname.replace(/^\/engine/, "");
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.pathname === "/coach/state") return json(route, { person: "p_t", task: { id: "t1", name: "Entitlement check, household H-9", step: 5, steps_total: 9 }, level: "L2", chip: "small", message: "state message", why: "state why", mastery: { READ: 0.9 }, case: 3 });
    if (u.pathname === "/coach/next") { nextCalls.push(u.search); return json(route, { meta, data: scenarios[scenario] }); }
    if (u.pathname === "/coach/feedback") { feedback.push({ body: JSON.parse(req.postData() ?? "{}"), actor: req.headers()["x-understudy-actor"] }); return json(route, { ok: true }); }
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  const hop = async () => { await page.goto(`${base}/#/genome`); await page.reload(); await page.waitForTimeout(200); await page.goto(`${base}/#/today`); };
  // nudge: message, why, follow, feedback body and actor header, steady polling
  await hop(); await page.waitForTimeout(7200);
  check("today: the coach's message is shown with the level chip and a why link", (await page.getByText("Check the benefit cliff before you copy across.").count()) > 0 && (await page.getByText("L2").count()) > 0 && (await page.getByText("Why this").count()) > 0);
  check("today: the first look is passive (dry=1), then it polls without it at a steady pace", /dry=1/.test(nextCalls[0] ?? "") && nextCalls.slice(1).every((q) => !/dry=1/.test(q)) && nextCalls.length >= 3 && nextCalls.length <= 5, `${nextCalls.length} calls: ${nextCalls.map((q) => (/dry/.test(q) ? "dry" : "live")).join(",")}`);
  check("today: the target hint is shown", await page.getByText("Check cliff").first().isVisible());
  await page.getByRole("button", { name: "I did that" }).click();
  await page.waitForTimeout(400);
  check("today: following sends feedback {decision_id, outcome} as the worker", feedback.length === 1 && feedback[0].body.decision_id === "d1" && feedback[0].body.outcome === "followed" && feedback[0].actor === "worker", JSON.stringify(feedback[0] ?? {}));
  // silent with a candidate: nothing in the chip, a quiet "What I would say"
  scenario = "silent"; await hop(); await page.waitForTimeout(600);
  check("today: silent shows the candidate as a quiet 'What I would say'", (await page.getByText("What I would say", { exact: false }).count()) > 0 && (await page.getByText("Compare all three results first.").count()) > 0 && (await page.getByRole("button", { name: "I did that" }).count()) === 0);
  // study mode: nothing, not even a hint
  scenario = "study"; await hop(); await page.waitForTimeout(600);
  const todayText = await page.locator("main").innerText();
  check("today: in study mode the coach shows nothing, not even a hint", !/SHOULD NOT SHOW|benefit cliff|What I would say|Stop coaching|Preview how help fades/i.test(todayText));
  await page.unroute(ENGINE);
}

// 8d. Extension screens (REQ-2), demo fixtures
await go("/week", 900);
await openAll(page.locator("main"));
const weekText = await page.locator("#gr-time").innerText();   // Growth draws every section on one page: read this one
check("week: the ribbon, the gap table with intervals and 3 to 5 suggestion cards", (await page.locator("#gr-time .weekribbon svg").count()) === 2 && /95% interval/i.test(weekText) && (await page.locator("#gr-time .sug").count()) >= 3 && (await page.locator("#gr-time .sug").count()) <= 5);
check("week: the suggestions say, once under the list, that nothing is sent, booked or changed", (weekText.match(/Nothing is sent, booked or changed\./g) ?? []).length === 1);
check("week: no titles or names anywhere on the screen", !/(standup|(?<![\d:])1:1(?![\d:])|review with|@[a-z]+\.)/i.test(weekText));

await asView("worker");
await go("/needs-you", 900);
await showAll();
const cardRows = page.locator("article[data-kind=prepared]");
const cardsBefore = await cardRows.count();
check("needs you: at most three prepared actions", cardsBefore > 0 && cardsBefore <= 3);
const first = cardRows.first();
check("needs you: editing is one click away, not in the way", (await first.locator("textarea").count()) === 0);
await first.getByRole("button", { name: "Details" }).click();
await first.getByRole("button", { name: "Edit what will happen" }).click();
await first.locator("textarea").first().fill("Hold Wednesday 10:00 to 12:00 for focus. Edited by me.");
await first.getByRole("button", { name: /^Save/ }).click();
await page.waitForTimeout(500);
await go("/needs-you", 700);
await showAll();
await page.locator("article[data-kind=prepared]").first().getByRole("button", { name: "Details" }).click();
check("needs you: the edit to the prepared block is kept", (await page.locator("article[data-kind=prepared]").first().innerText()).includes("Edited by me."));
await page.locator("article[data-kind=prepared]").first().getByRole("button", { name: "Approve and run" }).click();
await page.waitForTimeout(600);
check("needs you: pressing Approve and run says which thing it created", /Created an item here for your approval/.test(await page.locator("[data-testid=fired]").first().innerText()));
await page.locator("article[data-kind=prepared]").first().getByRole("button", { name: "Not now" }).click();
await page.waitForTimeout(500);
await page.locator("article[data-kind=prepared]").first().getByRole("button", { name: "Never" }).click();
await page.waitForTimeout(500);
check("needs you: with nothing prepared left, none is shown", (await page.locator("article[data-kind=prepared]").count()) === 0);

await go("/agents", 900);
check("agents: a worker who arrives by the address does not see the runs (the gate sentence, or Routines)", (/Switch to Admin to see this\./.test(await page.locator("main").innerText()) || /\/routines/.test(page.url())) && (await page.locator("article.run").count()) === 0);
await go("/home?settings=views", 1200);
await page.locator("[data-testid=settings]").getByRole("button", { name: "Admin", exact: true }).click();
await go("/agents", 900);
await showAll();        // three runs show by default
const runsBefore = await page.locator("article.run").count();
await page.locator("summary", { hasText: "Start a background run" }).click();
await page.locator("#spawn-kind").selectOption("data.chart");
await page.getByRole("button", { name: "Nightly" }).click();
await page.getByRole("button", { name: "Run in background" }).click();
await page.waitForTimeout(700);
await showAll();        // a fourth run folds behind "Show all"
check("agents: spawning adds a run to the tree", (await page.locator("article.run").count()) === runsBefore + 1 && (await page.locator("article.run").first().innerText()).includes("Chart builder"));
await page.locator("article.run").first().getByRole("button", { name: "Stop" }).click();
await page.waitForTimeout(700);
check("agents: Stop ends the run and its helpers", (await page.locator("article.run").first().innerText()).toLowerCase().includes("stopped"));
const live = page.locator("article.run", { hasText: "Commit analyst" });
await openAll(live); // budget, lease and tools sit in a closed "Budget, lease and tools" disclosure; the check below is unchanged
check("agents: each helper shows budgets spent against allowed and its lease", /7 of 20 steps/.test(await live.innerText()) && /LEASE/i.test(await live.innerText()) && /git_log/.test(await live.innerText()));
await live.getByRole("button", { name: "Revoke the lease of habit counter" }).click();
await page.waitForTimeout(700);
await openAll(live);
check("agents: revoking a lease ends that helper and says so", /revoked, no tools in scope/.test(await live.innerText()));
await page.locator("article.run", { hasText: "Data profile" }).locator("summary", { hasText: "Helpers and result" }).click();
await page.waitForTimeout(500);
await openAll(page.locator("article.run", { hasText: "Data profile" }));   // each helper's checks sit behind the one closed "More"
await page.waitForTimeout(200);
const detail = await page.locator("article.run", { hasText: "Data profile" }).innerText();
check("agents: result steps carry a check with a glyph and a word", /verified/.test(detail) && /uncertain/.test(detail) && (await page.locator(".pill--check .pill__glyph-char").count()) >= 3);

await asView("worker");
// 8c. Your data says one sentence about what leaves; the call list is one closed link away, under Settings, Advanced
await go("/your-data?section=sent", 900);
check("your data: what it looked at or sent is one sentence and one link", /Nothing leaves this Mac without your say\./.test(await page.locator("[data-testid=sent]").innerText()) && (await page.locator("[data-testid=sent] .ledger__row").count()) === 0);
await page.getByRole("button", { name: /Every call Knack makes/ }).click();
await page.waitForTimeout(900);
check("settings: Advanced is the last section, opened by that link, and holds the call list", (await page.locator("[data-testid=settings] details > summary", { hasText: "Advanced" }).count()) === 1 && (await page.locator("[data-testid=advanced-calls]").count()) === 1);
await showAll(page.locator("[data-testid=advanced-calls]"));
await openAll(page.locator("[data-testid=advanced-calls]"));   // each call's payload and the canary sit behind closed disclosures
check("your data: the model-call list shows each call with its fields and the payload as sent", (await page.locator("[data-testid=advanced-calls] .ledger__row").count()) >= 6 && /Payload, exactly as sent/.test(await page.locator("[data-testid=advanced-calls]").innerText()) && (await page.locator("[data-testid=advanced-calls] pre.payload").first().innerText()).includes("card_kind"));
const priv = await page.locator("[data-testid=advanced-calls]").innerText();
check("settings: the call list never claims that nothing leaves the laptop, prints the limit, and the canary reads as evidence not proof", !/nothing (ever )?leaves/i.test(priv) && /cannot show what other software on this computer does/i.test(priv) && /evidence from a test, not a proof/i.test(priv) && /Every call from Knack is listed/i.test(priv));
await page.locator("[data-testid=advanced-calls]").getByRole("button", { name: "Forget", exact: true }).click();
check("settings: forgetting the calls asks once, inline, and says what it does not do", /does not recall anything already sent/.test(await page.locator("[data-testid=advanced-calls]").innerText()));
await page.getByRole("button", { name: "Forget it" }).click();
await page.waitForTimeout(600);
check("settings: forgetting the calls empties the list and says so", (await page.locator(".ledger__row").count()) === 0 && (await page.getByText("Nothing has been sent to a model.").count()) >= 1);
await page.keyboard.press("Escape");   // close the Settings sheet before the next screen

// 8d2. Your data: Delete everything is on the screen, and its confirm names exactly what it clears
await go("/your-data");
await page.getByRole("button", { name: "Delete everything", exact: true }).click();
const delText = await page.locator(".yd-delete").innerText();
check("your data: Delete everything names every part it clears and what stays", /Delete everything Knack holds about you\?/.test(delText) && /lines of your memory file|line of your memory file/.test(delText) && /step count/.test(delText) && /records? of model calls/.test(delText) && /what Knack learned about how loud to speak/.test(delText) && /does not recall anything already sent/.test(delText) && /Your role, settings and routines stay\./.test(delText));
await page.getByRole("button", { name: "Keep", exact: true }).click();
check("your data: Keep leaves everything as it was", (await page.getByRole("button", { name: "Delete everything", exact: true }).count()) === 1);

// 8e. A layer that /health lists as off: the screen is still there, shows example data and says how to switch the layer on, and asks for nothing
{
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(body) });
  let privacyAsked = 0;
  await page.route(ENGINE, (route) => {
    const u = new URL(route.request().url());
    u.pathname = u.pathname.replace(/^\/engine/, "");
    if (u.pathname === "/health") return json(route, { ok: true, version: "x", mock: true, extensions: { calendar: true, privacy: false, proactive: false, agents: false } });
    if (u.pathname.startsWith("/privacy")) privacyAsked++;
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(600);
  // Knack: a worker has five rows and no More; an admin has eight and a More of three (Briefing and Privacy became Needs you and Your data; Calendar and Git habits became sections of Growth).
  const workerNav = await page.locator("nav#nav").textContent();
  check("layers off: nothing is hidden from the worker's menu", /Home/.test(workerNav) && /Needs you/.test(workerNav) && /Routines/.test(workerNav) && /Growth/.test(workerNav) && /Your data/.test(workerNav) && (await page.locator("nav#nav").getByRole("button", { name: "More" }).count()) === 0);
  await asView("admin");
  await page.locator("nav#nav").getByRole("button", { name: "More" }).click();
  const adminNav = `${await page.locator("nav#nav").textContent()} ${await page.getByRole("menu", { name: "More" }).textContent()}`;
  await page.keyboard.press("Escape");
  check("layers off: nothing is hidden from the admin's menu", /Firm/.test(adminNav) && /Brief/.test(adminNav) && /Forecasts/.test(adminNav) && /Automation/.test(adminNav) && /Risk/.test(adminNav) && /Models and cost/.test(adminNav) && /Evidence/.test(adminNav) && /Background runs/.test(adminNav));
  await asView("worker");
  // The call list lives under Settings, Advanced; Your data links to it. With the privacy layer off the list is the sample, and says so in one plain line.
  await page.goto(`${base}/#/your-data?section=sent`); await page.waitForTimeout(700);
  await page.getByRole("button", { name: /Every call Knack makes/ }).click();
  await page.waitForTimeout(900);
  const off = await page.locator("[data-testid=advanced-calls]").innerText();
  check("layers off: one plain line in the call list says that this feature is off in the engine", /This feature is off in the engine\./.test(off));
  const offDetail = await page.locator("[data-testid=advanced-calls] [data-testid=source-detail]").first().textContent();
  check("layers off: its hint says how to switch the layer on, and the engine is asked for nothing", /switched off/.test(offDetail ?? "") && /UNDERSTUDY_X_PRIVACY=1/.test(offDetail ?? "") && privacyAsked === 0, `asked ${privacyAsked} times`);
  check("layers off: the call list prints its own reason, not another source's", /UNDERSTUDY_X_PRIVACY=1/.test(offDetail ?? "") && !/could not answer yet/.test(off));
  await page.keyboard.press("Escape");
  await page.unroute(ENGINE);
}

// 8f. Explain: "Where did my time go?" in the steps section of Growth
{
  const openExplain = () => page.locator("summary", { hasText: "Explain this case" }).first().evaluate((sm) => { for (let d = sm.parentElement; d; d = d.parentElement) if (d.tagName === "DETAILS") d.open = true; });   // it and every disclosure around it
  // Example answers first (the engine is blocked): the answer, where it came from, the checks, the limits and the footer are all there.
  await go("/genome", 1500);
  await openExplain();   // "Explain this case" is a closed disclosure in the steps section
  const ex = page.locator("#explain");
  const exText = await ex.innerText();
  check("explain: example data is badged and says the answers do not change with the question", /example data/i.test(exText) && /do not change with what you ask/i.test(exText));
  check("explain: the answer comes first, then where the words came from and the check", (await ex.locator("[data-testid=explain-answer]").count()) === 1 && /Written from a fixed template/.test(exText) && /Checked against the data/.test(exText) && /not that the data is right/.test(await hintText(ex, "About this answer")));
  check("explain: the limits and the footer are always shown, with no origin tag", (await ex.locator("[data-testid=explain-limits] li").count()) >= 3 && /Based on n = 24 people; generated data\./.test(await ex.locator("[data-testid=explain-footer]").innerText()) && !/synthetic|simulated/i.test(await ex.locator("[data-testid=explain-footer]").innerText()));
  const usesNote = await hintText(ex, /Where (this number comes|these numbers come) from/);
  check("explain: each sentence has a hint with the packet facts its numbers come from", /gap · case s/.test(usesNote) && /9 min 45 s/.test(usesNote) && /not supplied by the model/.test(usesNote));
  check("explain: five example questions are offered", (await ex.locator("[aria-label='Example questions'] button").count()) === 5);
  await openAsk(ex);
  await ex.getByRole("button", { name: "How sure are you?" }).click();
  await page.waitForTimeout(500);
  check("explain: a chip asks, and the reply is labelled as an answer", /The answer/.test(await ex.innerText()));
  // The question text is never echoed anywhere but the box.
  const secret = "zzqmarker-where-did-the-time-go-today";
  await ex.locator("#ex-q").fill(secret);
  await ex.getByRole("button", { name: "Ask", exact: true }).click();
  await page.waitForTimeout(500);
  check("explain: the question text is only ever in the box", !(await page.locator("body").innerText()).includes(secret) && (await ex.locator("#ex-q").inputValue()) === secret && !page.url().includes("zzqmarker"));

  // A real-engine scenario, mocked: a slow answer shows calm progress; a rejected model answer falls back to the template and says so.
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }, body: JSON.stringify(body) });
  const meta = { origin: "synthetic", n: 24, n_unit: "people", split: "descriptive_nearest_expert", interval_level: 0.95, note: null, generated_at: "" };
  const result = (over = {}) => ({ intent: "where_time_went", source: "template", model: null, footer: "Based on n = 24 people; generated data.", badge: { origin: "synthetic", n: 24, n_unit: "people", split: "descriptive_nearest_expert" },
    check: { ok: true, checked: { sentences: 1, numbers: 2, intervals: 0 } }, attempts: [], fallback_reason: null, question: { asked_s: null, matches_case: null },
    sections: [{ kind: "explanation", sentences: [{ text: "On this case you took 9 minutes 45 seconds.", uses: ["gap.case_s"] }] }, { kind: "coaching", actions: [] }, { kind: "limits", sentences: [{ id: "synthetic_data", text: "Generated data with planted patterns." }, { id: "association_only", text: "An association, not proof of cause." }, { id: "small_n", text: "A small sample." }] }], ...over });
  let delayMs = 0, explainBody = null, scenario = result();
  await page.route(ENGINE, async (route) => {
    const req = route.request(), u = new URL(req.url());
    u.pathname = u.pathname.replace(/^\/engine/, "");
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.pathname === "/health") return json(route, { ok: true, version: "x", mock: false, extensions: { evidence: true } });
    if (u.pathname === "/evidence/packet") return json(route, { meta, data: { person: "p_t", case: "t_t", facts: [{ path: "gap.case_s", value: 585, unit: "s" }], limitations: [] } });
    if (u.pathname === "/evidence/explain") { explainBody = { body: JSON.parse(req.postData() ?? "{}"), actor: req.headers()["x-understudy-actor"], type: req.headers()["content-type"] }; if (delayMs) await new Promise((r) => setTimeout(r, delayMs)); return json(route, { meta, data: scenario }); }
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  const fresh = async () => { await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(6800); await page.goto(`${base}/#/genome`); await page.waitForTimeout(1500); await openExplain(); };
  await fresh();
  const live = page.locator("#explain");
  check("explain: with a real engine and no mock mode, nothing is asked until the worker presses", (await live.getByRole("button", { name: "Explain this case" }).count()) === 1 && explainBody === null && !/example data/i.test(await live.innerText()));
  delayMs = 2500;
  await live.getByRole("button", { name: "Explain this case" }).click();
  await page.waitForTimeout(700);
  check("explain: a slow answer shows a calm progress line, not a blank", /Writing the answer/.test(await live.innerText()));
  await page.waitForTimeout(2600);
  check("explain: the request is JSON from the worker and carries no question when none was typed", explainBody?.actor === "worker" && /application\/json/.test(explainBody?.type ?? "") && explainBody.body.question === undefined, JSON.stringify(explainBody));
  check("explain: a live answer is not badged as an example", (await live.locator("[data-testid=explain-answer]").count()) === 1 && !/example data/i.test(await live.innerText()));
  delayMs = 0;
  scenario = result({ attempts: [{ route: "local", ok: false, reason: "provenance", codes: ["number_not_in_packet"] }], fallback_reason: "provenance" });
  await openAsk(live);
  await live.getByRole("button", { name: "Why was I slow?" }).click();
  await page.waitForTimeout(600);
  check("explain: a rejected model answer says the template was used and why", /fixed template because a number or name in the model's words did not match the data/.test(await live.innerText()));
  scenario = result({ check: { ok: false } });
  await live.getByRole("button", { name: "How sure are you?" }).click();
  await page.waitForTimeout(600);
  check("explain: an answer that failed the check says so and is not called checked", /Did not pass the check/.test(await live.innerText()) && !/Checked against the data/.test(await live.innerText()));
  await page.unroute(ENGINE);
}

await asView("worker");
// 8g. Settings, Interruptions: three words, the kinds behind "Per kind", locked safety kinds, learned quieting and a refused change
{
  // The block before mocked a live engine with nobody set up, which sends the app to the first run: start this one from a clean page.
  await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(600);
  await go("/home?settings=interruptions", 1500);
  const st = page.locator("[data-testid=settings]");
  const stText = await st.innerText();
  check("settings: Interruptions has three words and prints that stops and blocking approvals always show", /Rarely/.test(stText) && /Balanced/.test(stText) && /Often/.test(stText) && /Stops and blocking approvals always show\./.test(stText));
  check("settings: Use live models comes first", stText.indexOf("Use live models") >= 0 && stText.indexOf("Use live models") < stText.indexOf("Interruptions"));
  await st.locator("summary", { hasText: /^More$/ }).first().click();
  const nt = await st.innerText();
  check("settings: the kinds are grouped in plain words, one control per group, behind More", /Needs you/.test(nt) && /Helps in the moment/.test(nt) && /Can wait/.test(nt) && /Information/.test(nt) && (await page.locator("[data-testid^=group-]").count()) === 4);
  await page.locator("[data-testid=group-wait]").getByRole("button", { name: "Digest only" }).click();
  await page.waitForTimeout(400);
  await st.locator("summary", { hasText: "Each kind" }).click();
  check("settings: a group control sets every kind in the group at once", (await page.locator("[data-testid=notice-routine_proposal] button[aria-pressed=true]").innerText()) === "Digest only" && (await page.locator("[data-testid=notice-briefing_ready] button[aria-pressed=true]").innerText()) === "Digest only");
  check("settings: a safety kind is printed as always shown, not offered as a choice", /Always shown:/.test(await page.locator("[data-testid=always-needs]").innerText()) && (await page.locator("[data-testid=notice-kill_engaged]").count()) === 0);
  const rp = page.locator("[data-testid=notice-routine_proposal]");
  await rp.getByRole("button", { name: "Quiet" }).click();
  await page.waitForTimeout(400);
  check("settings: choosing a mode takes effect and the row says what it does", (await rp.locator("button[aria-pressed=true]").innerText()) === "Quiet" && /A summary and a note on the dashboard only/.test(await hintText(rp, /does at this setting/)));
  await st.locator("[data-testid=today-strip] summary", { hasText: "Why each count" }).click();
  const strip = await st.locator("[data-testid=today-strip]").innerText();
  check("settings: the Today strip counts shown, held and dropped, and says why in the engine's words", /Today: 2 shown, 2 held, 4 dropped, 2 left as quiet notes/.test(strip) && /Held because you were typing\. Shown at your next pause\./.test(strip));
  await st.locator("[data-testid=needs-you] summary", { hasText: "Why?" }).first().click();
  await page.waitForTimeout(500);
  check("settings: a Why? on an item that needs you gives the engine's fixed reason, in Knack's name", /Held because Knack could not tell whether you were busy\./.test(await st.locator("[data-testid=needs-you]").innerText()));
  await page.getByRole("button", { name: "Reset what Knack learned" }).click();
  check("settings: reset asks once, inline", (await page.getByRole("button", { name: "Reset it", exact: true }).count()) === 1);
  await page.getByRole("button", { name: "Reset it", exact: true }).click();
  await page.waitForTimeout(400);
  check("settings: after a reset nothing learned is listed", (await page.locator("[data-testid=learned]").count()) === 0);

  // A real-engine scenario, mocked: a refused change reverts and shows the engine's own words.
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" }, body: JSON.stringify(body) });
  const meta = { origin: "real", n: 0, n_unit: "items", split: null, interval_level: 0.95, note: null, generated_at: "" };
  const settings = { modes: {}, budget_per_day: 10, level_glance: true, learned: {}, floors: [{ type: "kill_engaged", floor: "toast", why: "Safety stops are always shown once and stay visible." }],
    types: [{ type: "routine_proposal", class: "wait", mode: "normal", fixed: false }, { type: "kill_engaged", class: "safety", mode: "normal", fixed: true }] };
  let posted = null;
  await page.route(ENGINE, async (route) => {
    const req = route.request(), u = new URL(req.url());
    u.pathname = u.pathname.replace(/^\/engine/, "");
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.pathname === "/health") return json(route, { ok: true, version: "x", mock: false, extensions: { attention: true } });
    if (u.pathname === "/identity") return json(route, { person: "p_demo01", role: "benefits-processor" });          // somebody is set up, so the app opens on Home and not on the first run
    if (u.pathname === "/attention/settings" && req.method() === "GET") return json(route, { meta, data: settings });
    if (u.pathname === "/attention/settings") { posted = { body: JSON.parse(req.postData() ?? "{}"), actor: req.headers()["x-understudy-actor"], type: req.headers()["content-type"] }; return json(route, { error: { code: "unknown_key", message: "That setting is not one the engine knows." } }, 422); }
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(1500); await page.goto(`${base}/#/home?settings=interruptions`); await page.waitForTimeout(1500);
  await page.locator("[data-testid=settings] summary", { hasText: /^More$/ }).first().click();
  await page.locator("[data-testid=settings] summary", { hasText: "Each kind" }).click();
  check("settings: with a real engine the interruption settings are not badged as an example", !/Example settings/i.test(await page.locator("[data-testid=settings]").innerText()));
  const row = page.locator("[data-testid=notice-routine_proposal]");
  await row.getByRole("button", { name: "Digest only" }).click();
  await page.waitForTimeout(500);
  check("settings: a refused change goes back and shows the engine's own words", (await row.locator("button[aria-pressed=true]").innerText()) === "Normal" && /That setting is not one the engine knows\. \(unknown_key\)/.test(await page.locator("[data-testid=settings]").innerText()));
  check("settings: the change was sent as JSON from the worker", posted?.actor === "worker" && /application\/json/.test(posted?.type ?? "") && posted.body.modes?.routine_proposal === "digest", JSON.stringify(posted));
  await page.unroute(ENGINE);
}

// 8h. Growth bridges the older work screens as sections: in the worker view none of them draws another person's figures (docs/knack-ux/views.md), and a
// section that would is not drawn at all ("This section is being rebuilt").
for (const sec of ["time", "steps", "map", "commits"]) {
  await go(`/growth?section=${sec}`, 6500);
  const grown = await page.locator("#main").innerText();
  check(`growth ${sec}: the worker view draws no average over others, count of people or other person's id`, !/average over all|\b\d+ (?:experts|learners|colleagues|people)\b|\bp_[a-z]*\d+/i.test(grown), grown.replace(/\s+/g, " ").slice(0, 90));
}

// 8i. The Home task box (Track T's task API, mocked): Enter sends, examples only fill, a consent is a real click on one of its own buttons, nothing starts without
// the service, and what the service answers is shown in its own words.
{
  const seen = [];
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(body) });
  let reply = { status: 201, body: { task_id: "tk_a", route: "answer", summary: "I will answer that at once.", needs_consent: null, question: null } };
  const TASKS = /^https?:\/\/[^/]+\/agent\/tasks(\/.*)?$/;
  await page.route(TASKS, async (route) => {
    const req = route.request(), u = new URL(req.url());
    const path = u.pathname.replace(/^\/agent/, "");
    if (req.method() === "GET") {
      if (path === "/tasks/events") return route.fulfill({ status: 404, body: "" });
      if (/^\/tasks\/[^/]+$/.test(path)) return json(route, { task_id: "tk_a", state: "done", answer: "Two plus two is four.", result: "Done." });
      return json(route, []);
    }
    seen.push({ path, body: req.postData() ? JSON.parse(req.postData()) : null, actor: req.headers()["x-understudy-actor"], type: req.headers()["content-type"] });
    if (reply.status === 0) return route.abort();
    return json(route, reply.body, reply.status);
  });
  const consentCard = (kind, more) => ({ task_id: "tk_c", route: kind, summary: "I need your OK first.", question: null, needs_consent: { kind, scope_text: "Knack will run a Claude agent in your Downloads folder.", can: ["Read files in Downloads"], cannot: ["Delete anything"], folder: "/Users/me/Downloads", command_hash: null, cost_note: "Uses your Claude plan.", max_minutes: 30, buttons: { allow: "Allow for this task", decline: "Not now", more } } });
  await go("/home", 1500);
  const box = page.locator("[data-testid=task-box]");
  const field = box.locator("input[type=text]");
  check("task box: it is the one text field on Home, with its question printed", (await box.getByRole("heading", { name: "What should Knack do?" }).count()) === 1 && (await field.count()) === 1);
  check("task box: no Send button until there is something to send", (await box.getByRole("button", { name: "Send" }).count()) === 0);
  await field.focus();
  await page.keyboard.press("Enter");
  check("task box: Enter on an empty box sends nothing", seen.length === 0);
  const chip = box.locator(".taskbox__chip").first();
  check("task box: examples appear when the box is focused and empty", (await chip.count()) === 1);
  const chipText = await chip.innerText();
  await chip.click();
  check("task box: an example fills the box and never sends it", (await field.inputValue()) === chipText && seen.length === 0);
  await field.fill("Summarise today's commits");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  check("task box: Enter sends the typed task as the worker, as JSON", seen.length === 1 && seen[0].path === "/tasks" && seen[0].body.text === "Summarise today's commits" && seen[0].body.source === "typed" && seen[0].actor === "worker" && /application\/json/.test(seen[0].type), JSON.stringify(seen[0]));
  check("task box: the service's own line is shown at once, and the box is empty and still has focus", (await box.locator("[data-testid=task-summary]").innerText()) === "I will answer that at once." && (await field.inputValue()) === "" && (await field.evaluate((e) => e === document.activeElement)));
  await page.waitForTimeout(2200);
  check("task box: an inline answer appears under the box once the task is done, as plain text", /Two plus two is four\./.test(await box.locator("[data-testid=task-answer]").innerText().catch(() => "")));
  await box.getByRole("button", { name: "Dismiss" }).click();

  // a consent card: both buttons of one weight, nothing pre-selected, More behind a small link, and no key answers it
  reply = { status: 201, body: consentCard("claude_agent", [{ id: "everything", label: "Allow everything for this task" }]) };
  await field.fill("Tidy my downloads");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  const card = box.locator("[data-testid=task-consent]");
  const cardText = await card.innerText();
  check("task box: a consent card prints its scope, what it can and cannot do, where, the cost and the time cap", /Claude agent in your Downloads folder/.test(cardText) && /Read files in Downloads/.test(cardText) && /Delete anything/.test(cardText) && /\/Users\/me\/Downloads/.test(cardText) && /Uses your Claude plan/.test(cardText) && /30 minutes/.test(cardText));
  check("task box: Allow and Not now are two buttons of one size, none pre-selected, and Allow everything is not shown until More", (await card.getByRole("button", { name: "Allow for this task" }).count()) === 1 && (await card.getByRole("button", { name: "Not now" }).count()) === 1 && (await card.locator("button[aria-pressed=true]").count()) === 0 && (await card.getByRole("button", { name: "Allow everything for this task" }).count()) === 0 && (await card.getByRole("button", { name: "Allow for this task" }).getAttribute("class")) === (await card.getByRole("button", { name: "Not now" }).getAttribute("class")));
  check("task box: focus did not jump to the card, so the Enter that sent the task cannot also answer it", await field.evaluate((e) => e === document.activeElement));
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  check("task box: a key never answers a consent", seen.filter((s) => /consent/.test(s.path)).length === 0);
  await card.getByRole("button", { name: "More" }).click();
  check("task box: More reveals the wider choice", (await card.getByRole("button", { name: "Allow everything for this task" }).count()) === 1);
  await card.getByRole("button", { name: "Not now" }).click();
  await page.waitForTimeout(400);
  const declined = seen.filter((s) => /consent/.test(s.path));
  check("task box: Not now is sent as the approval actor with the closed choice, and says nothing was changed", declined.length === 1 && declined[0].path === "/tasks/tk_c/consent" && declined[0].body.choice === "decline" && declined[0].actor === "worker_approval" && /Not started\. Nothing was changed\./.test(await box.innerText()), JSON.stringify(declined));
  check("task box: a decided card goes away", (await box.locator("[data-testid=task-consent]").count()) === 0);

  // a browser task has no "Allow everything"
  reply = { status: 201, body: consentCard("browser", []) };
  await field.fill("Look something up");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  check("task box: a card with no wider choice has no More", (await box.locator("[data-testid=task-consent]").getByRole("button", { name: "More" }).count()) === 0);
  await box.locator("[data-testid=task-consent]").getByRole("button", { name: "Allow for this task" }).click();
  await page.waitForTimeout(400);
  check("task box: Allow is sent as the approval actor", seen.filter((s) => /consent/.test(s.path)).pop()?.body.choice === "allow" && seen.filter((s) => /consent/.test(s.path)).pop()?.actor === "worker_approval");

  // a question card
  reply = { status: 201, body: { task_id: "tk_q", route: "desktop", summary: "I need to know one thing.", needs_consent: null, question: { text: "Which folder?", options: [{ id: "dl", label: "Downloads" }, { id: "dk", label: "Desktop" }] } } };
  await field.fill("Find my invoice");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  await box.locator("[data-testid=task-question]").getByRole("button", { name: "Desktop" }).click();
  await page.waitForTimeout(400);
  const answered = seen.filter((s) => /answer/.test(s.path));
  check("task box: a question's option is sent as the worker", answered.length === 1 && answered[0].path === "/tasks/tk_q/answer" && answered[0].body.option_id === "dk" && answered[0].actor === "worker", JSON.stringify(answered));

  // the limit of three, and no service
  reply = { status: 429, body: { error: { code: "too_many_tasks", message: "Too many tasks." } } };
  await field.fill("One more thing");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  check("task box: at three running it says so, and keeps what was typed", /Three tasks are already running/.test(await box.innerText()) && (await field.inputValue()) === "One more thing");
  reply = { status: 502, body: { error: { code: "bad_gateway" } } };
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  check("task box: with no task service it says nothing was started, and keeps what was typed", /nothing was started/.test(await box.innerText()) && (await field.inputValue()) === "One more thing");
  const tooLong = "a".repeat(501);
  await field.fill(tooLong);
  await page.waitForTimeout(150);
  const sentBefore = seen.length;
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  check("task box: a task over 500 characters is refused with a sentence, never cut and never sent", /under 500 characters/.test(await box.innerText()) && seen.length === sentBefore);
  await page.unroute(TASKS);
}

// 8h. Live: a task that finishes in the background shows as finished with no reload, an open row stays open, and the announcement is one quiet sentence
{
  const AGENT = /^https?:\/\/[^/]+\/agent(\/|$)/;
  const reply = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  let state = "running";
  const row = () => ({ task_id: "tk_live1", title: "Tidy the invoices folder", state, started: new Date(Date.now() - 60000).toISOString(), latest: state === "running" ? "Reading invoices.pdf" : null, result: state === "done" ? "Moved 12 files into Paid and Unpaid." : null, finished: state === "done" ? new Date().toISOString() : null });
  await page.route(AGENT, async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/agent/, "");
    if (path === "/tasks") return reply(route, [row()]);
    if (path === "/tasks/events") return route.abort();                      // polling covers it: the check is that the page updates by itself
    if (path === "/tasks/tk_live1") return reply(route, { ...row(), steps: ["Listed the folder", "Read invoices.pdf"] });
    return reply(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  await go("/routines", 1500);
  // The app skips a service for a few seconds after a refused connection (the blocks before made some), then asks again by itself: wait for the first live answer.
  await page.waitForFunction(() => /Reading invoices\.pdf/.test(document.body.innerText), null, { timeout: 15000 }).catch(() => undefined);
  const bt = page.locator("[data-testid=background-tasks]");
  check("routines: a running task is one line with the current step, and no id", /Tidy the invoices folder/.test(await bt.innerText()) && /Reading invoices\.pdf/.test(await bt.innerText()) && !/tk_live1/.test(await bt.innerText()));
  await bt.locator("button.bt-open").first().click();
  await page.waitForTimeout(500);
  check("routines: a click on the line shows the steps as a plain list", (await bt.locator(".bt-steps li").count()) >= 2);
  const scrollBefore = await page.evaluate(() => window.scrollY);
  state = "done";
  await page.waitForTimeout(3500);                                           // the page polls every 2 s while a task runs
  const after = await bt.innerText();
  check("routines: the task finished and the page says so without leaving it", /Moved 12 files into Paid and Unpaid\./.test(after));
  check("routines: the open row stayed open and the scroll did not move", (await bt.locator("button.bt-open[aria-expanded=true]").count()) === 1 && (await page.evaluate(() => window.scrollY)) === scrollBefore);
  check("routines: the finish is one quiet sentence for a screen reader, not a toast", /Tidy the invoices folder finished\./.test(await page.locator("[data-testid=tasks-live]").first().innerText()) && (await page.locator("[role=alert]").count()) === 0);
  await page.unroute(AGENT);
}

// 9. Kill switch
await go("/growth");
// One red square, once: exactly one Stop button is visible, it holds the word and nothing else, and its only square is the design system's ::before.
const stopFace = await page.evaluate(() => [...document.querySelectorAll(".stop-button")].filter((b) => b.offsetParent !== null).map((b) => ({ kids: b.children.length, svg: b.querySelectorAll("svg").length, text: b.textContent.trim(), before: getComputedStyle(b, "::before").content, after: getComputedStyle(b, "::after").content })));
check("kill switch: one visible Stop button with one red square (the word, no icon of its own)", stopFace.length === 1 && stopFace[0].kids === 1 && stopFace[0].svg === 0 && stopFace[0].text === "Stop" && stopFace[0].before === '""' && stopFace[0].after === "none", JSON.stringify(stopFace));
await page.getByRole("button", { name: "Stop everything now" }).click();
await page.waitForTimeout(600);
check("kill switch: says everything is stopped", await page.getByText("Everything is stopped.").isVisible());
check("kill switch: stopped, the button says Resume in words and the banner carries one alert icon, not a stop square", (await page.locator(".stopped-banner svg").count()) === 1 && (await page.locator(".stop-button:visible").first().innerText()).trim() === "Resume");
await page.screenshot({ path: join(qa, "killed-1440.png") });
await page.getByRole("button", { name: "Resume" }).first().click();
await page.waitForTimeout(500);
check("kill switch: resume clears it", (await page.getByText("Everything is stopped.").count()) === 0);
await page.keyboard.press("Shift+Escape");
await page.waitForTimeout(500);
check("kill switch: Shift Esc stops", await page.getByText("Everything is stopped.").isVisible());
await page.getByRole("button", { name: "Resume" }).first().click();

// 10. Focus visible
await go("/genome");
await page.keyboard.press("Tab");
await page.keyboard.press("Tab");
const outline = await page.evaluate(() => { const e = document.activeElement; const s = e ? getComputedStyle(e) : null; return s ? `${s.outlineStyle} ${s.outlineWidth}` : ""; });
check("keyboard: focus ring is drawn", /solid 2px/.test(outline), outline);

// 11. Reduced motion
const rm = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const rp = await rm.newPage();
await rp.goto(`${base}/#/today`);
await rp.waitForTimeout(500);
const dur = await rp.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--dur-fade").trim());
check("reduced motion: fade duration collapses", dur === "0.01ms", dur);

check("no unexpected console errors", errors.length === 0, errors.slice(0, 3).join(" | "));
await browser.close();
console.log(failed ? `\n${failed} check(s) failed` : "\nall checks passed");
process.exit(failed ? 1 : 0);
