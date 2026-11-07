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
await ctx.route(/127\.0\.0\.1:77\d\d/, (route) => route.abort());
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !/ERR_CONNECTION_REFUSED|Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`); });
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); if (!ok) failed++; };
const go = async (hash, wait = 700) => {
  // Same-hash navigations do not remount, so hop through another route first.
  if (page.url().endsWith(`#${hash}`)) { await page.goto(`${base}/#/today`); await page.waitForTimeout(150); }
  await page.goto(`${base}/#${hash}`); await page.waitForTimeout(wait);
};

// 1. Onboarding, two roles, timed
for (const [role, pack] of [["UK benefits processor", "benefits-processor"], ["Data analyst", "data-analyst"]]) {
  await go("/onboarding");
  const t0 = Date.now();
  await page.locator(".role-card", { hasText: role }).click();
  await page.getByRole("button", { name: "Next" }).click();
  for (let i = 0; i < 5; i++) await page.getByRole("button", { name: "Next" }).click();
  const write = page.getByRole("button", { name: "Write my memory file" });
  check(`onboarding ${pack}: capture is never pre-selected (cannot write before choosing)`, await write.isDisabled());
  await page.locator(".role-card", { hasText: pack === "benefits-processor" ? "Yes, record times" : "Not now" }).click();
  await write.click();
  await page.getByText("Your memory file is written").waitFor();
  const secs = (Date.now() - t0) / 1000;
  const text = await page.locator(".pv").innerText();
  check(`onboarding ${pack}: file written in under 60 s`, secs < 60, `${secs.toFixed(1)} s`);
  check(`onboarding ${pack}: file names the role`, text.includes(`role: ${pack}`));
  check(`onboarding ${pack}: capture line only when the worker said yes`, text.includes("Capture: times only") === (pack === "benefits-processor"));
  if (pack === "benefits-processor") await page.screenshot({ path: join(qa, "onboarding-done-1440.png") });
  globalThis[pack] = text;
}
check("onboarding: two roles give different files", globalThis["benefits-processor"] !== globalThis["data-analyst"]);

// 2. Onboarding mid-flow screenshot (risky question)
await go("/onboarding");
await page.locator(".role-card", { hasText: "Data analyst" }).click();
await page.getByRole("button", { name: "Next" }).click();
await page.locator(".role-card", { hasText: "SQL console" }).click();
await page.getByRole("button", { name: "Next" }).click();
await page.waitForTimeout(300);
await page.screenshot({ path: join(qa, "onboarding-question-1440.png") });

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
await go("/memory");
check("memory: the forgotten line is gone from the file", !(await page.locator(".memfile").innerText()).includes("Summaries: short"));

// 3b. Memory: capture toggle is just a line in the file
await go("/memory");
const wasOn = (await page.locator(".capture").innerText()).includes("Capture is on");
await page.getByRole("button", { name: wasOn ? "Turn off" : "Turn on" }).click();
await page.waitForTimeout(600);
const nowState = await page.locator(".capture").innerText();
check("memory: capture toggle flips and edits the file", wasOn ? nowState.includes("Capture is off") : nowState.includes("Capture is on") && (await page.locator(".memfile").innerText()).includes("Capture: times only"));

// 4. Memory: edit a line, then edit as text
await page.locator(".memfile__line", { hasText: "Working hours" }).hover();
await page.getByRole("button", { name: /Edit line/ }).first().click({ force: true });
await page.waitForTimeout(200);
const input = page.locator(".memline-edit input");
await input.fill("Working hours: Tue to Sat, 10:00 to 18:00.");
await page.getByRole("button", { name: "Save line" }).click();
await page.waitForTimeout(700);
check("memory: line edit saved", (await page.locator(".memfile").innerText()).includes("Tue to Sat, 10:00"));
await page.getByRole("button", { name: "Edit as text" }).click();
const ta = page.locator("#memtext");
const cur = await ta.inputValue();
await ta.fill(cur + "\n");
check("memory: revision bumped after edits", /revision: 1[3-9]/.test(cur));
await page.screenshot({ path: join(qa, "memory-edit-1440.png") });

// 5. Routines: Watch first moves the card into the list
await go("/routines");
await page.locator(".proposal", { hasText: "Enter the household into three calculators" }).getByRole("button", { name: "Watch first" }).click();
await page.waitForTimeout(900);
check("routines: proposal leaves after a choice", (await page.locator(".proposal", { hasText: "Enter the household into three calculators" }).count()) === 0);
check("routines: it now lists as watching first", await page.getByText("Enter the household into three calculators").first().isVisible());

// 5b. Routines: the skill gate refuses, and "I already know this one" re-sends with the override
await go("/routines");
await page.locator(".proposal", { hasText: "Reconcile the three results" }).getByRole("button", { name: "Watch first" }).click();
await page.waitForTimeout(400);
check("routines: skill gate explains itself in plain words", await page.getByText("would rather coach you on this one first").isVisible());
await page.getByRole("button", { name: "I already know this one" }).click();
await page.waitForTimeout(900);
check("routines: the override goes through and the card leaves", (await page.locator(".proposal", { hasText: "Reconcile the three results" }).count()) === 0);

// 6. Routines: typed confirmation required for model-driven irreversible opt-in
await page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).locator("summary", { hasText: "Autonomy and record" }).click();
await page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).locator(".away summary").click();
await page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).getByText("Let this routine run while I'm away").click();
await page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).getByText("Allow “submit” without asking me").click();
const away = page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).getByRole("button", { name: "Allow while I'm away" });
check("routines: irreversible away opt-in blocked without typed confirmation", await away.isDisabled());
await page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).locator("input.input").fill("monday-cliff-check");
check("routines: allowed once the id is typed", await away.isEnabled());
await page.locator(".routine-row", { hasText: "Re-check benefit cliffs" }).scrollIntoViewIfNeeded(); await page.screenshot({ path: join(qa, "routines-away-1440.png") });

// 7. Queue: approve one item
await go("/queue");
const before = await page.locator(".queue-item").count();
await page.getByRole("button", { name: "Approve and submit" }).click();
await page.waitForTimeout(700);
check("queue: approving decides the card", (await page.locator(".queue-item[data-status='approved']").count()) === 1 && before === 4);

// 8. Presence: quiet hours save changes idle capacity
await go("/presence");
const idle0 = await page.locator(".stat__value").first().innerText();
await page.locator("#qs").fill("01:00");
await page.locator("#qe").fill("11:00");
await page.getByRole("button", { name: "Save quiet hours" }).click();
await page.waitForTimeout(700);
const idle1 = await page.locator(".stat__value").first().innerText();
check("presence: saving quiet hours recomputes idle capacity", idle0 !== idle1, `${idle0.replace(/\n/g, " ")} -> ${idle1.replace(/\n/g, " ")}`);
await page.locator("svg[role='application']").focus();
await page.keyboard.press("ArrowRight");
await page.waitForTimeout(150);
check("presence: arrow keys read a cell with its interval", /95% interval/.test(await page.locator("p[aria-live]").first().innerText()));

// 8b. Evidence: honest states
await go("/evidence", 1200);
check("evidence: high limits are open, medium and low are folded, and there is a sticky jump list", (await page.locator("#limits .limit:visible").count()) > 0 && (await page.locator("details.limits-fold:not([open])").count()) === 2 && (await page.locator("nav.ev-jump a").count()) >= 10 && (await page.locator("nav.ev-jump").evaluate((el) => getComputedStyle(el).position)) === "sticky");
await page.locator("main details").evaluateAll((els) => els.forEach((e) => (e.open = true)));
const ev = await page.locator("main").innerText();
check("evidence: a not-run study says so and prints no defaults", /has not run yet/.test(ev) && !/changed by [+\u2212-]?0 s/.test(ev));
const pres = await page.locator("#presence").innerText();
check("evidence: presence baselines show interruption and idle time, never a 0.000 Brier", /Fixed overnight window/.test(pres) && !/0\.000/.test(pres));
check("evidence: ski rental and off-policy show the engine's labels", /Ski rental with predictions/.test(ev) && /Doubly robust/.test(ev));
check("evidence: pooling appears, and a pending real-model run says why", /Partial pooling/.test(ev) && /real-model run is still being worked out/.test(ev));
check("evidence: limitations carry their source", /From: engine-eval · null placebo/.test(ev));
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
  await page.route(/127\.0\.0\.1:7700\//, async (route) => {
    const req = route.request(), u = new URL(req.url());
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
  await page.unroute(/127\.0\.0\.1:7700\//);
}

// 8d. Extension screens (REQ-2), demo fixtures
await go("/week", 900);
const weekText = await page.locator("main").innerText();
check("week: the ribbon, the gap table with intervals and 3 to 5 suggestion cards", (await page.locator(".weekribbon svg").count()) === 2 && /95% interval/i.test(weekText) && (await page.locator(".sug").count()) >= 3 && (await page.locator(".sug").count()) <= 5);
check("week: every suggestion says it is a draft and that nothing is sent", (await page.locator(".sug", { hasText: "Draft only. Nothing is sent, booked or changed." }).count()) === (await page.locator(".sug").count()));
check("week: no titles or names anywhere on the screen", !/(standup|1:1|review with|@[a-z]+\.)/i.test(weekText));

await go("/briefing", 900);
const cardsBefore = await page.locator("article.proposal").count();
check("briefing: at most three cards", cardsBefore > 0 && cardsBefore <= 3);
const first = page.locator("article.proposal").first();
await first.locator("textarea").fill("Hold Wednesday 10:00 to 12:00 for focus. Edited by me.");
await first.getByRole("button", { name: "Save my edit" }).click();
await page.waitForTimeout(500);
await go("/briefing", 700);
check("briefing: the edit to the prepared block is kept", (await page.locator("article.proposal").first().locator("textarea").inputValue()).includes("Edited by me."));
await page.locator("article.proposal").first().getByRole("button", { name: "Approve and run" }).click();
await page.waitForTimeout(600);
check("briefing: pressing Approve and run says which thing it created", /Created approval item q_demo_b_01/.test(await page.locator("[data-testid=fired]").first().innerText()));
await page.locator("article.proposal").first().getByRole("button", { name: "Not now" }).click();
await page.waitForTimeout(500);
await page.locator("article.proposal").first().getByRole("button", { name: "Never for this" }).click();
await page.waitForTimeout(500);
check("briefing: with nothing left it says nothing is worth your time", (await page.getByText("Nothing worth your time today").count()) >= 1 && (await page.locator("article.proposal").count()) === 0);

await go("/agents", 900);
const runsBefore = await page.locator("article.run").count();
await page.locator("#spawn-kind").selectOption("data.chart");
await page.getByRole("button", { name: "Nightly" }).click();
await page.getByRole("button", { name: "Run in background" }).click();
await page.waitForTimeout(700);
check("agents: spawning adds a run to the tree", (await page.locator("article.run").count()) === runsBefore + 1 && (await page.locator("article.run").first().innerText()).includes("Chart builder"));
await page.locator("article.run").first().getByRole("button", { name: "Stop" }).click();
await page.waitForTimeout(700);
check("agents: Stop ends the run and its helpers", (await page.locator("article.run").first().innerText()).toLowerCase().includes("stopped"));
const live = page.locator("article.run", { hasText: "Commit analyst" });
check("agents: each helper shows budgets spent against allowed and its lease", /7 of 20 steps/.test(await live.innerText()) && /LEASE/i.test(await live.innerText()) && /git_log/.test(await live.innerText()));
await live.getByRole("button", { name: "Revoke the lease of habit counter" }).click();
await page.waitForTimeout(700);
check("agents: revoking a lease ends that helper and says so", /revoked, no tools in scope/.test(await live.innerText()));
await page.locator("article.run", { hasText: "Data profile" }).locator("summary", { hasText: "Artifacts and result" }).click();
await page.waitForTimeout(500);
const detail = await page.locator("article.run", { hasText: "Data profile" }).innerText();
check("agents: result steps carry a check with a glyph and a word", /verified/.test(detail) && /uncertain/.test(detail) && (await page.locator(".pill--check .pill__glyph-char").count()) >= 3);

await go("/privacy", 900);
check("privacy: the ledger lists each call with its fields and the payload as sent", (await page.locator(".ledger__row").count()) === 6 && /Payload, exactly as sent/.test(await page.locator("main").innerText()) && (await page.locator("pre.payload").first().innerText()).includes("card_kind"));
const priv = await page.locator("main").innerText();
check("privacy: it never claims that nothing leaves the laptop, and the canary reads as evidence not proof", !/nothing (ever )?leaves/i.test(priv) && /evidence from a test, not a proof/i.test(priv) && /Calls for steps you asked for are listed too/i.test(priv));
await page.getByRole("button", { name: "Clear the ledger" }).click();
await page.getByRole("button", { name: "Yes, clear the list" }).click();
await page.waitForTimeout(600);
check("privacy: clearing empties the list and says so", (await page.locator(".ledger__row").count()) === 0 && (await page.getByText("The ledger is empty").count()) >= 1);

// 8e. Extension gating: a screen shows only when /health lists its layer as true
{
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(body) });
  await page.route(/127\.0\.0\.1:7700\//, (route) => {
    const u = new URL(route.request().url());
    if (u.pathname === "/health") return json(route, { ok: true, version: "x", mock: true, extensions: { calendar: true, privacy: false, proactive: false, agents: false } });
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(600);
  const nav = await page.locator("nav#nav").innerText();
  check("gating: only the layers /health lists as on appear in the menu", /Week/.test(nav) && !/Privacy/.test(nav) && !/Agents/.test(nav) && !/Briefing/.test(nav));
  await page.goto(`${base}/#/privacy`); await page.waitForTimeout(500);
  const off = await page.locator("main").innerText();
  check("gating: a screen that is off says so and how to switch it on, and loads nothing", /Privacy is not switched on/.test(off) && /UNDERSTUDY_X_PRIVACY=1/.test(off));
  await page.unroute(/127\.0\.0\.1:7700\//);
}

// 9. Kill switch
await go("/genome");
await page.getByRole("button", { name: "Stop everything now" }).click();
await page.waitForTimeout(600);
check("kill switch: says everything is stopped", await page.getByText("Everything is stopped.").isVisible());
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
