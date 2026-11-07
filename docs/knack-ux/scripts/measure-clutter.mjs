// Usage (from apps/dashboard, dashboard running on 5173): node ../../docs/knack-ux/scripts/measure-clutter.mjs [outdir]
// Writes <outdir>/clutter.json and one PNG per screen. Read-only: every non-GET request is refused.
// Read-only clutter measurement of every screen at 1440x900 (light). Non-GET requests are refused.
import { chromium } from "playwright";
import fs from "node:fs";
const OUT = process.argv[2] ?? "qa/knack";
fs.mkdirSync(OUT, { recursive: true });
const ROUTES = {
  worker: ["home", "growth", "repeats", "routines", "queue", "privacy", "genome", "presence", "graph", "week", "git", "predictions", "today", "memory", "notices", "onboarding", "briefing", "agents", "models", "evidence"],
  admin: ["firm", "firm/roles", "firm/people", "firm/onboarding", "firm/automation", "firm/risk", "firm/forecasts", "firm/brief"],
};
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
await ctx.route("**/*", (r) => (["GET", "HEAD"].includes(r.request().method()) ? r.continue() : r.abort()));
const page = await ctx.newPage();

const measure = () => page.evaluate(() => {
  const FOLD = window.innerHeight;
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2) return false;
    return true;
  };
  const hiddenAncestor = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { if (e.hidden || e.getAttribute("aria-hidden") === "true" && false) return true; const cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden") return true; if (e.classList.contains("u-sr-only")) return true; } return false; };
  const words = (root, foldOnly) => {
    let n = 0; const texts = [];
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (tw.nextNode()) {
      const t = tw.currentNode; const s = t.textContent.trim(); if (!s) continue;
      const el = t.parentElement; if (!el || hiddenAncestor(el) || ["SCRIPT", "STYLE", "OPTION"].includes(el.tagName)) continue;
      const range = document.createRange(); range.selectNodeContents(t); const r = range.getBoundingClientRect();
      if (r.width <= 1 || r.height <= 1) continue;
      if (foldOnly && (r.top >= FOLD || r.bottom <= 0)) continue;
      const c = s.split(/\s+/).filter(Boolean).length; n += c; texts.push(s);
    }
    return { n, texts };
  };
  const main = document.querySelector("#main");
  const side = document.querySelector(".side");
  const above = (el) => { const r = el.getBoundingClientRect(); return r.top < FOLD && r.bottom > 0; };
  const sel = (root, q, foldOnly = true) => [...root.querySelectorAll(q)].filter((e) => vis(e) && !hiddenAncestor(e) && (!foldOnly || above(e)));
  const pills = sel(main, ".pill, [class*='badge'], .chip, [class*='pill']").filter((e, i, a) => !a.some((o) => o !== e && o.contains(e)));
  const controls = sel(main, "button, a[href], input, select, textarea, summary, [role='button'], [role='tab'], [role='switch']");
  const hintBtns = controls.filter((e) => e.closest(".hint") || e.matches("[class*='hint']"));
  // paragraphs over two lines: elements with own text of 8+ words whose height is more than 2.5 lines
  const longP = [];
  for (const el of main.querySelectorAll("p, li, dd, span, div, summary, label, h1, h2, h3")) {
    if (!vis(el) || hiddenAncestor(el)) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ").trim();
    const wc = own.split(/\s+/).filter(Boolean).length; if (wc < 8) continue;
    const cs = getComputedStyle(el); const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
    const lines = Math.round(el.getBoundingClientRect().height / lh);
    if (lines > 2) longP.push({ lines, words: wc, text: own.slice(0, 70) });
  }
  const navAll = side ? [...side.querySelectorAll(".nav a, .nav button")].filter((e) => !e.closest("[hidden]")) : [];
  const navVisible = navAll.filter((e) => vis(e) && !hiddenAncestor(e));
  const sidebarControls = side ? [...side.querySelectorAll("button, a[href], input, select")].filter((e) => vis(e) && !hiddenAncestor(e)) : [];
  const sideWords = side ? words(side, true).n : 0;
  const mainAbove = words(main, true), mainAll = words(main, false);
  const h1 = main.querySelector("h1");
  return {
    title: h1 ? h1.textContent.trim() : null,
    wordsAbove: mainAbove.n, wordsTotal: mainAll.n, sideWords,
    longP: longP.length, longPex: longP.slice(0, 3),
    pills: pills.length, pillTexts: pills.slice(0, 8).map((e) => e.textContent.trim().slice(0, 28)),
    controls: controls.length, hints: hintBtns.length,
    navVisible: navVisible.length, navAll: navAll.length, sidebarControls: sidebarControls.length,
    height: Math.round(document.documentElement.scrollHeight),
    titleWords: h1 ? h1.textContent.trim().split(/\s+/).length : 0,
  };
});

const rows = [];
for (const view of ["worker", "admin"]) {
  await page.goto("about:blank");
  await page.goto("http://127.0.0.1:5173/#/home", { waitUntil: "networkidle" }).catch(() => undefined);
  await page.waitForTimeout(800);
  if (view === "admin") await page.locator(".viewas .segmented button", { hasText: "Admin" }).click();
  for (const r of ROUTES[view]) {
    await page.evaluate((h) => { location.hash = h; }, `#/${r}`);
    await page.waitForTimeout(900);
    let m = await measure(); let prev = -1; let tries = 0;
    while ((m.wordsTotal !== prev || /Loading|Reading/i.test(await page.locator("#main").innerText())) && tries < 14) { prev = m.wordsTotal; await page.waitForTimeout(600); m = await measure(); tries++; }
    const safe = r.replace("/", "-");
    await page.screenshot({ path: `${OUT}/m-${view}-${safe}.png` });
    rows.push({ view, route: r, ...m });
    console.log(view, r, JSON.stringify({ t: m.title, wa: m.wordsAbove, wt: m.wordsTotal, lp: m.longP, pill: m.pills, ctl: m.controls, nav: `${m.navVisible}/${m.navAll}`, side: m.sidebarControls, sw: m.sideWords, h: m.height }));
  }
}
fs.writeFileSync(`${OUT}/clutter.json`, JSON.stringify(rows, null, 1));
await browser.close();
