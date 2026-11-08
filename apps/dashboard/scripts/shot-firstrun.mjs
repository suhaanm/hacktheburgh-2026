// Pictures of first run, in a browser tab and as the Knack desktop app would show it (a fake window.knackShell and window.alongside.awareness are injected,
// so nothing real is touched): node scripts/shot-firstrun.mjs [base=http://127.0.0.1:5191] [outDir=qa/knack]
// Light and dark at 1440 by 900, 1152 by 735 and 390 by 844. The engine and agent are blocked (example data).
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { fakeApp } from "./lib/fake-app.mjs";

const base = process.argv[2] ?? "http://127.0.0.1:5191";
const out = process.argv[3] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");
mkdirSync(out, { recursive: true });
const SIZES = [["1440", 1440, 900], ["win", 1152, 735], ["m390", 390, 844]];

const browser = await chromium.launch();
for (const mode of ["browser", "app"]) for (const theme of ["light", "dark"]) for (const [tag, width, height] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme });
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.addInitScript((t) => { try { localStorage.setItem("understudy-theme", t); localStorage.removeItem("understudy-first-run-done"); localStorage.removeItem("understudy-first-run-progress"); sessionStorage.clear(); } catch { /* */ } }, theme);
  if (mode === "app") await page.addInitScript(fakeApp, { microphone: "granted", speech: "not-determined", screen: "denied" });
  const shot = async (name) => { await page.waitForTimeout(450); await page.screenshot({ path: join(out, `firstrun-${mode}-${name}-${theme}-${tag}.png`) }); };
  await page.goto(`${base}/#/first-run`); await page.waitForTimeout(900);
  await shot("1-role");
  await page.locator(".rolecard__btn").first().click(); await page.waitForTimeout(300);
  // a role with connection chips opens them with a Continue button (D55)
  const cont = page.getByRole("button", { name: "Continue" });
  if (await cont.isVisible().catch(() => false)) { await shot("1b-chips"); await cont.click(); await page.waitForTimeout(300); }
  await shot("2-may");
  // The consent screen against the first-run budget (words and controls above the fold, counted the way check-copy counts them).
  if (tag !== "m390") {
    const m = await page.evaluate((fold) => {
      const wc = (s) => s.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
      const main = document.querySelector("#main") ?? document.body;
      let words = 0;
      const tw = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
      while (tw.nextNode()) {
        const t = tw.currentNode, el = t.parentElement;
        if (!el || !t.textContent.trim()) continue;
        const r = document.createRange(); r.selectNodeContents(t);
        const b = r.getBoundingClientRect();
        if (b.width <= 1 || b.height <= 1 || b.top >= fold || b.bottom <= 0) continue;
        words += wc(t.textContent);
      }
      const controls = [...main.querySelectorAll("button, a[href], input, select, textarea, summary, [role='button']")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2 && r.top < fold && r.bottom > 0; }).length;
      return { words, controls };
    }, height);
    const budget = JSON.parse((await import("node:fs")).readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack", "budgets.json"), "utf8")).routes["first-run"];
    const ok = m.words <= budget.wordsAbove && m.controls <= budget.controls;
    console.log(`${ok ? "PASS" : "FAIL"}  consent screen (${mode}, ${theme}, ${tag}): ${m.words}/${budget.wordsAbove} words, ${m.controls}/${budget.controls} controls`);
    if (!ok) process.exitCode = 1;
  }
  // answer every card with a real click: Yes for capture, then (in the app) Yes for glances and voice
  await page.locator("[data-kind=capture]").getByRole("button", { name: /^Yes/ }).click();
  if (mode === "app") {
    await page.locator("[data-kind=glance]").getByRole("button", { name: /^Yes/ }).click();
    await shot("2-may-answered");
    await page.locator("[data-kind=voice]").getByRole("button", { name: /^Yes/ }).click();
  }
  await page.waitForTimeout(900);
  await shot("3-check");
  await ctx.close();
}
await browser.close();
console.log("done");
