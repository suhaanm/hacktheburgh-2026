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
const openAll = (scope) => scope.locator("details").evaluateAll((els) => els.forEach((e) => { e.open = true; }));
const go = async (hash, wait = 700) => {
  // Same-hash navigations do not remount, so hop through another route first.
  if (page.url().endsWith(`#${hash}`)) { await page.goto(`${base}/#/today`); await page.waitForTimeout(150); }
  await page.goto(`${base}/#${hash}`); await page.waitForTimeout(wait);
};

// 1. Onboarding, two roles, timed
for (const [role, pack] of [["UK benefits processor", "benefits-processor"], ["Data analyst", "data-analyst"]]) {
  await go("/setup");
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
await go("/setup");
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
check("evidence: pooling appears", /Partial pooling/.test(ev));
check("evidence: the map lists every section with origin, n and status, and names simulated participants as not people", (await page.locator(".ev-map__table tbody tr").count()) >= 20 && /Every part of the report/.test(ev) && /SYNTHETIC/i.test(ev) && (/Simulated participants are language models playing workers\. They are not people/.test(ev) || (await page.locator(".ev-map__table", { hasText: /simulated participants/i }).count()) === 0));
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
  check("evidence: the real-model block keeps its origin badge and says evidence, not proof", (await liveBlock.locator(".pill--origin").count()) >= 1 && /evidence from a small run, not proof/.test(lv));
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
const weekText = await page.locator("main").innerText();
check("week: the ribbon, the gap table with intervals and 3 to 5 suggestion cards", (await page.locator(".weekribbon svg").count()) === 2 && /95% interval/i.test(weekText) && (await page.locator(".sug").count()) >= 3 && (await page.locator(".sug").count()) <= 5);
check("week: every suggestion says that nothing is sent, booked or changed", (await page.locator(".sug", { hasText: /Nothing is sent, booked or changed\./ }).count()) === (await page.locator(".sug").count()));
check("week: no titles or names anywhere on the screen", !/(standup|1:1|review with|@[a-z]+\.)/i.test(weekText));

await go("/briefing", 900);
const cardsBefore = await page.locator("article.proposal").count();
check("briefing: at most three cards", cardsBefore > 0 && cardsBefore <= 3);
const first = page.locator("article.proposal").first();
check("briefing: editing is one click away, not in the way", (await first.locator("textarea").count()) === 0);
await first.getByRole("button", { name: "Edit what will happen" }).click();
await first.locator("textarea").first().fill("Hold Wednesday 10:00 to 12:00 for focus. Edited by me.");
await first.getByRole("button", { name: "Save my edit" }).click();
await page.waitForTimeout(500);
await go("/briefing", 700);
check("briefing: the edit to the prepared block is kept", (await page.locator("article.proposal").first().innerText()).includes("Edited by me."));
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
await openAll(live); // budget, lease and tools sit in a closed "Budget, lease and tools" disclosure; the check below is unchanged
check("agents: each helper shows budgets spent against allowed and its lease", /7 of 20 steps/.test(await live.innerText()) && /LEASE/i.test(await live.innerText()) && /git_log/.test(await live.innerText()));
await live.getByRole("button", { name: "Revoke the lease of habit counter" }).click();
await page.waitForTimeout(700);
await openAll(live);
check("agents: revoking a lease ends that helper and says so", /revoked, no tools in scope/.test(await live.innerText()));
await page.locator("article.run", { hasText: "Data profile" }).locator("summary", { hasText: "Artifacts and result" }).click();
await page.waitForTimeout(500);
const detail = await page.locator("article.run", { hasText: "Data profile" }).innerText();
check("agents: result steps carry a check with a glyph and a word", /verified/.test(detail) && /uncertain/.test(detail) && (await page.locator(".pill--check .pill__glyph-char").count()) >= 3);

await go("/privacy", 900);
check("privacy: the ledger lists each call with its fields and the payload as sent", (await page.locator(".ledger__row").count()) >= 6 && /Payload, exactly as sent/.test(await page.locator("main").innerText()) && (await page.locator("pre.payload").first().innerText()).includes("card_kind"));
const priv = await page.locator("main").innerText();
check("privacy: it never claims that nothing leaves the laptop, and the canary reads as evidence not proof", !/nothing (ever )?leaves/i.test(priv) && /evidence from a test, not a proof/i.test(priv) && /Calls for steps you asked for are listed too/i.test(priv));
await page.getByRole("button", { name: "Clear the ledger" }).click();
await page.getByRole("button", { name: "Yes, clear the list" }).click();
await page.waitForTimeout(600);
check("privacy: clearing empties the list and says so", (await page.locator(".ledger__row").count()) === 0 && (await page.getByText("The ledger is empty").count()) >= 1);

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
  // Knack: five destinations in the sidebar and the rest in the More sheet (the old fold lists became the sheet; Briefing and Privacy became Needs you and Your data).
  await page.locator("nav#nav").getByRole("button", { name: "More" }).click();
  const nav = `${await page.locator("nav#nav").textContent()} ${await page.getByRole("menu", { name: "More" }).textContent()}`;
  await page.keyboard.press("Escape");
  check("layers off: nothing is hidden from the menu", /Calendar/.test(nav) && /Your data/.test(nav) && /Background runs/.test(nav) && /Needs you/.test(nav) && /Git habits/.test(nav) && /Models and cost/.test(nav));
  await page.goto(`${base}/#/privacy`); await page.waitForTimeout(700);
  const off = await page.locator("main").innerText();
  // One plain line is on the page; the engine's sentence with the flag name sits in a closed "Details" disclosure under it (D45). Open it, then assert the text.
  check("layers off: one plain line says example data and that the feature is switched off", /Showing example data: this feature is switched off in the engine\./.test(off) && /example data/i.test(off));
  await page.locator("main .sourcenote summary", { hasText: "Details" }).first().click();
  const offDetail = await page.locator("main [data-testid=source-detail]").first().innerText();
  check("layers off: its Details says how to switch the layer on, and the engine is asked for nothing", /switched off/.test(offDetail) && /UNDERSTUDY_X_PRIVACY=1/.test(offDetail) && privacyAsked === 0, `asked ${privacyAsked} times`);
  await page.unroute(ENGINE);
}

// 8f. Explain: "Where did my time go?" on the Genome screen
{
  // Example answers first (the engine is blocked): the answer, where it came from, the checks, the limits and the footer are all there.
  await go("/genome", 1500);
  const ex = page.locator("#explain");
  const exText = await ex.innerText();
  check("explain: example data is badged and says the answers do not change with the question", /example data/i.test(exText) && /do not change with what you ask/i.test(exText));
  check("explain: the answer comes first, then where the words came from and the check", (await ex.locator("[data-testid=explain-answer]").count()) === 1 && /Written from a fixed template/.test(exText) && /Checked against the data/.test(exText) && /not that the data is right/.test(exText));
  check("explain: the limits and the footer are always shown with the badge", (await ex.locator("[data-testid=explain-limits] li").count()) >= 3 && /Based on n = 24 people; synthetic data\./.test(await ex.locator("[data-testid=explain-footer]").innerText()) && /SYNTHETIC/i.test(await ex.locator("[data-testid=explain-footer]").innerText()));
  const usesNote = await hintText(ex, /Where (this number comes|these numbers come) from/);
  check("explain: each sentence has a hint with the packet facts its numbers come from", /gap · case s/.test(usesNote) && /9 min 45 s/.test(usesNote) && /not supplied by the model/.test(usesNote));
  check("explain: five example questions are offered", (await ex.locator("[aria-label='Example questions'] button").count()) === 5);
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
  const result = (over = {}) => ({ intent: "where_time_went", source: "template", model: null, footer: "Based on n = 24 people; synthetic data.", badge: { origin: "synthetic", n: 24, n_unit: "people", split: "descriptive_nearest_expert" },
    check: { ok: true, checked: { sentences: 1, numbers: 2, intervals: 0 } }, attempts: [], fallback_reason: null, question: { asked_s: null, matches_case: null },
    sections: [{ kind: "explanation", sentences: [{ text: "On this case you took 9 minutes 45 seconds.", uses: ["gap.case_s"] }] }, { kind: "coaching", actions: [] }, { kind: "limits", sentences: [{ id: "synthetic_data", text: "Synthetic data with planted patterns." }, { id: "association_only", text: "An association, not proof of cause." }, { id: "small_n", text: "A small sample." }] }], ...over });
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
  const fresh = async () => { await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(6800); await page.goto(`${base}/#/genome`); await page.waitForTimeout(1500); };
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
  await live.getByRole("button", { name: "Why was I slow?" }).click();
  await page.waitForTimeout(600);
  check("explain: a rejected model answer says the template was used and why", /fixed template because a number or name in the model's words did not match the data/.test(await live.innerText()));
  scenario = result({ check: { ok: false } });
  await live.getByRole("button", { name: "How sure are you?" }).click();
  await page.waitForTimeout(600);
  check("explain: an answer that failed the check says so and is not called checked", /Did not pass the check/.test(await live.innerText()) && !/Checked against the data/.test(await live.innerText()));
  await page.unroute(ENGINE);
}

// 8g. Notices: one row per kind of notice, locked safety rows, a Today strip, a passive banner
{
  // Notices became Settings, Interruptions: the old screen is drawn inside the Settings sheet until the new contents land.
  const sheet = page.locator("[data-testid=settings-sheet]");
  await go("/notices", 1500);
  await sheet.locator("details.notices__group").first().waitFor({ timeout: 20000 });
  const openGroups = () => page.evaluate(() => document.querySelectorAll("details.notices__group").forEach((d) => { d.open = true; }));
  check("notices: only the first group is open by default, the others are one click away", (await page.locator("details.notices__group[open]").count()) === 1 && (await page.locator("details.notices__group").count()) === 4);
  await openGroups();
  const nt = await sheet.innerText();
  check("notices: example data is badged and the groups and the floor are in plain words", /example data/i.test(nt) && /Needs you/.test(nt) && /Helps in the moment/.test(nt) && /Can wait/.test(nt) && /Information/.test(nt) && /Safety stops and approvals that block a job always stay visible/.test(nt));
  const kill = page.locator("[data-testid=notice-kill_engaged]");
  await page.getByText("What always shows", { exact: true }).click();
  check("notices: a safety kind is locked, not a choice", (await kill.locator(".segmented").count()) === 0 && /Always shown/.test(await kill.innerText()));
  const rp = page.locator("[data-testid=notice-routine_proposal]");
  await rp.getByRole("button", { name: "Quiet" }).click();
  await page.waitForTimeout(400);
  check("notices: choosing a mode takes effect and the row says what it does", (await rp.locator("button[aria-pressed=true]").innerText()) === "Quiet" && /A summary and a note on the dashboard only/.test(await hintText(rp, /does at this setting/)));
  await page.locator("[data-testid=today-detail] summary").click();
  const strip = await page.locator("[data-testid=today-strip]").innerText();
  check("notices: the Today strip counts shown, held and dropped, and says why in the engine's words", /Today: 2 shown, 2 held, 4 dropped, 2 left as quiet notes/.test(strip) && /Held because you were typing\. Shown at your next pause\./.test(strip));
  await page.locator("[data-testid=needs-you] summary", { hasText: "Why?" }).first().click();
  await page.waitForTimeout(500);
  check("notices: a Why? on an item that needs you gives the engine's fixed reason", /Held because Understudy could not tell whether you were busy\./.test(await page.locator("[data-testid=needs-you]").innerText()));
  await page.getByRole("button", { name: "Reset what Understudy learned" }).click();
  check("notices: reset asks once, inline", (await page.getByRole("button", { name: "Yes, reset what it learned" }).count()) === 1);
  await page.getByRole("button", { name: "Yes, reset what it learned" }).click();
  await page.waitForTimeout(400);
  check("notices: after a reset it says nothing is learned", /Nothing yet\. Every kind of notice is as loud as you set it\./.test(await sheet.innerText()));

  // A real-engine scenario, mocked: a refused change reverts and shows the engine's own words; the banner shows counts and the summary link.
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
    if (u.pathname === "/attention/settings" && req.method() === "GET") return json(route, { meta, data: settings });
    if (u.pathname === "/attention/settings") { posted = { body: JSON.parse(req.postData() ?? "{}"), actor: req.headers()["x-understudy-actor"], type: req.headers()["content-type"] }; return json(route, { error: { code: "unknown_key", message: "That setting is not one the engine knows." } }, 422); }
    if (u.pathname === "/attention/digest") return json(route, { meta, data: { kind: u.searchParams.get("kind"), lines: [], today: {}, budget: { used: 0, per_day: 10 } } });
    if (u.pathname === "/attention/next") return json(route, { meta, data: { item: null, active: null, badges: { needs_you: 1, waiting: 3, marker: "needs_you", stopped: false }, digest_ready: true, poll_after_s: 2 } });
    return json(route, { error: { code: "not_found", message: "not mocked" } }, 404);
  });
  await page.goto(`${base}/#/today`); await page.reload(); await page.waitForTimeout(6800); await page.goto(`${base}/#/notices`); await page.waitForTimeout(1500);
  await sheet.locator("details.notices__group").first().waitFor({ timeout: 20000 });
  await openGroups();
  check("notices: with a real engine the screen is not badged as an example", !/example data/i.test(await sheet.innerText()));
  const row = page.locator("[data-testid=notice-routine_proposal]");
  await row.getByRole("button", { name: "Digest only" }).click();
  await page.waitForTimeout(500);
  check("notices: a refused change goes back and shows the engine's own words", (await row.locator("button[aria-pressed=true]").innerText()) === "Normal" && /That setting is not one the engine knows\. \(unknown_key\)/.test(await sheet.innerText()));
  check("notices: the change was sent as JSON from the worker", posted?.actor === "worker" && /application\/json/.test(posted?.type ?? "") && posted.body.modes?.routine_proposal === "digest", JSON.stringify(posted));
  await page.unroute(ENGINE);
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
