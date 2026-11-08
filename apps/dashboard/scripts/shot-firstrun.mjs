// Pictures of first run, in a browser tab and as the Knack desktop app would show it (a fake window.knackShell and window.alongside.awareness are injected,
// so nothing real is touched): node scripts/shot-firstrun.mjs [base=http://127.0.0.1:5191] [outDir=qa/knack]
// Light and dark at 1440 by 900, 1152 by 735 and 390 by 844. The engine and agent are blocked (example data).
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://127.0.0.1:5191";
const out = process.argv[3] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");
mkdirSync(out, { recursive: true });
const SIZES = [["1440", 1440, 900], ["win", 1152, 735], ["m390", 390, 844]];

const fakeApp = (perm) => {
  const flag = () => { document.documentElement.dataset.knackShell = "mac-inset"; };
  if (document.documentElement) flag(); else document.addEventListener("DOMContentLoaded", flag);
  const wake = { switchOn: true, listening: true, line: "" };
  const perms = { ...perm };
  window.__rings = 0;
  window.knackShell = {
    platform: "darwin",
    wake: { state: async () => ({ ...wake }), set: async (on) => { wake.switchOn = on; wake.listening = on; return { ...wake }; }, context: async () => true },
    models: { get: async () => ({ useLiveModels: true, keyPresent: false, live: false, running: false }), setUseLiveModels: async () => ({ ok: true }) },
    permissions: { state: async () => ({ ...perms }), request: async (k) => { perms[k] = "granted"; return "granted"; }, openSettings: () => undefined },
    tryRing: async () => { window.__rings++; return { ok: true }; },
  };
  const aw = { available: true, consentText: "Knack may send a picture of your screen to a model when you seem stuck. Each picture is held in memory for one call and never stored. Only its size, a hash and the result are kept.", consentShort: "", agreed: false, enabled: false, trigger: false, periodic: false, strict: true, intervalSec: 30, dailyUsd: 0, callsToday: 0, lastSkip: null };
  window.alongside = { awareness: { state: async () => ({ ...aw }), setConsent: async (c) => { aw.trigger = !!c.trigger; aw.agreed = !!c.trigger; return { ...aw }; } } };
};

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
  await shot("2-may");
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
