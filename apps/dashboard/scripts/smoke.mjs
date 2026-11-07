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
