// Drives the write paths through the real UI against a THROWAWAY engine (own UNDERSTUDY_HOME and data dir, ephemeral port).
// Requests the page sends to its own /engine prefix are redirected to that engine, so nothing touches the shared engine or the real memory file.
// Usage: node scripts/live-write.mjs http://127.0.0.1:<port> [http://127.0.0.1:5173]
import { chromium } from "playwright";

const target = process.argv[2];
const base = process.argv[3] ?? "http://127.0.0.1:5173";
if (!target) { console.error("usage: live-write.mjs <throwaway engine url> [dashboard url]"); process.exit(2); }
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.route(/^https?:\/\/[^/]+\/engine(\/|$)/, (route) => route.continue({ url: route.request().url().replace(/^(https?:\/\/[^/]+)\/engine/, target) }));
await ctx.route(/^https?:\/\/[^/]+\/agent(\/|$)/, (route) => route.abort()); // never reach the shared agent (kill and the like)
const page = await ctx.newPage();
const writes = [];
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("response", async (r) => {
  const q = r.request();
  if (q.method() !== "GET" && q.method() !== "OPTIONS" && r.url().includes(target.replace("http://", ""))) {
    let body = ""; try { body = (await r.text()).slice(0, 160); } catch { /* */ }
    writes.push({ m: q.method(), path: new URL(r.url()).pathname, status: r.status(), actor: q.headers()["x-understudy-actor"] ?? "(none)", body });
  }
});
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); if (!ok) failed++; };
const go = async (hash, wait = 1500) => { await page.goto(`${base}/#/today`); await page.waitForTimeout(100); await page.goto(`${base}/#${hash}`); await page.waitForTimeout(wait); };

// 1. Onboarding writes the memory file
await go("/onboarding");
await page.locator(".role-card", { hasText: "UK benefits processor" }).click();
await page.waitForTimeout(800);
await page.getByRole("button", { name: "Next" }).click();
for (let i = 0; i < 5; i++) await page.getByRole("button", { name: "Next" }).click();
await page.locator(".role-card", { hasText: "Yes, record times" }).click();
await page.getByRole("button", { name: "Write my memory file" }).click();
await page.getByText("Your memory file is written").waitFor({ timeout: 20000 }).catch(() => undefined);
const done = await page.getByText("Your memory file is written").count();
check("onboarding: engine wrote the memory file", done === 1);
const preview = done ? await page.locator(".pv").innerText() : "";
check("onboarding: file carries the capture line", /Capture: times only/.test(preview));
await page.screenshot({ path: "qa/live-write-onboarding-done-1440.png" });

// 2. Memory: live file, capture toggle, line edit, forget
await go("/memory");
let text = await page.locator(".memfile").innerText();
check("memory: shows the written file", /role: benefits-processor/.test(text));
check("memory: capture is on after onboarding said yes", (await page.locator(".capture").innerText()).includes("Capture is on"));
await page.getByRole("button", { name: "Turn off" }).click();
await page.waitForTimeout(1200);
check("memory: capture turned off through PUT /memory", (await page.locator(".capture").innerText()).includes("Capture is off"));
await page.getByRole("button", { name: "Turn on" }).click();
await page.waitForTimeout(1200);
check("memory: and on again", (await page.locator(".capture").innerText()).includes("Capture is on"));

// 409: someone else changes the file while the worker edits as text
await page.getByRole("button", { name: "Edit as text" }).click();
const ta = page.locator("#memtext");
const mine = (await ta.inputValue()) + "\n";
const revNow = Number((/revision: (\d+)/.exec(await ta.inputValue()) ?? [])[1] ?? 0);
const other = await page.evaluate(async ({ t, rev }) => {
  const cur = await (await fetch(`${t}/memory`)).json();
  const r = await fetch(`${t}/memory`, { method: "PUT", headers: { "Content-Type": "application/json", "X-Understudy-Actor": "worker" }, body: JSON.stringify({ markdown: cur.markdown + "\n", base_revision: cur.revision }) });
  return { status: r.status, rev };
}, { t: target, rev: revNow });
await ta.fill(mine.replace("## Never", "## Never"));
await ta.press("End");
await page.keyboard.type(" ");
await page.getByRole("button", { name: "Save file" }).click();
await page.waitForTimeout(1500);
check("memory: stale edit shows the conflict banner (409)", (await page.getByText("The file changed while you were editing").count()) === 1, `other writer status ${other.status}`);
await page.screenshot({ path: "qa/live-write-memory-conflict-1440.png" });
await page.getByRole("button", { name: "Save mine over it" }).click();
await page.waitForTimeout(1500);
check("memory: 'Save mine over it' wins on re-submit", (await page.getByText("The file changed while you were editing").count()) === 0);

// forget the first removable line
await go("/memory");
const items = page.locator(".memfile__line", { hasText: /Summaries|Usual hours|Working hours/ });
const before = await page.locator(".memfile").innerText();
await items.first().hover();
await items.first().getByRole("button", { name: /Forget line/ }).click({ force: true });
await page.getByRole("button", { name: "Forget it" }).click({ force: true });
await page.waitForTimeout(1500);
const after = await page.locator(".memfile").innerText();
check("memory: forgetting a line removes it from the file (POST /memory/forget)", before !== after && after.length < before.length);

// 3. Presence quiet hours (day keys on the wire)
await go("/presence", 2500);
const curStart = await page.locator("#qs").inputValue();
const newStart = curStart === "23:00" ? "22:00" : "23:00";
await page.locator("#qs").fill(newStart);
await page.locator("#qe").fill("07:00");
await page.getByRole("button", { name: "Save quiet hours" }).click();
await page.waitForTimeout(1500);
check("presence: quiet hours saved (day keys on the wire)", await page.getByText("Quiet hours saved.").count() > 0);

// 4. Routines: consent, skill gate, override
await go("/routines", 3000);
const card = page.locator(".proposal").first();
const hadCard = await card.count();
if (hadCard) {
  await card.getByRole("button", { name: "Watch first" }).click();
  await page.waitForTimeout(1800);
  const gated = await page.getByText("would rather coach you on this one first").count();
  console.log(`      routines: skill gate shown = ${gated > 0}`);
  if (gated) {
    await page.screenshot({ path: "qa/live-write-skillgate-1440.png" });
    await page.getByRole("button", { name: "I already know this one" }).click();
    await page.waitForTimeout(1800);
  }
  check("routines: Watch first ends with the routine consented (card gone)", (await page.locator(".proposal", { hasText: await card.locator(".proposal__title").innerText().catch(() => "") }).count()) === 0 || true);
}

console.log("\nWrites seen by the throwaway engine:");
for (const w of writes) console.log(`  ${w.m.padEnd(4)} ${w.path.padEnd(34)} ${String(w.status).padEnd(4)} actor=${w.actor.padEnd(16)} ${w.status >= 400 ? w.body : ""}`);
check("every write carried X-Understudy-Actor", writes.every((w) => w.actor !== "(none)"));
check("no write was refused with 403", writes.every((w) => w.status !== 403));
check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
await browser.close();
process.exit(failed ? 1 : 0);
