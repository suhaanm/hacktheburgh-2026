// The copy and density budgets of docs/KNACK_UX.md section 5, enforced against a running dashboard. Budgets are tests: this exits 1 above any of them.
// Data: qa/knack/budgets.json (the spec's docs/knack-ux/budgets.json plus the address of each screen). Method: the same as
// docs/knack-ux/scripts/measure-clutter.mjs, so numbers compare with the baseline: words in the visible text nodes of #main (SVG text included)
// that sit inside the first viewport height; the sidebar is counted apart; a "long paragraph" is an element with 8 or more words of its own text
// that renders on more than two lines; pills are .pill, *badge* and .chip above the fold; controls are buttons, links, inputs, selects, summaries
// and role button, tab or switch above the fold in #main.
//
// Read-only: every request that is not GET or HEAD is refused, so nothing can change. By default the page talks to whatever is behind the dev
// server; --example blocks /engine and /agent, which makes the checks deterministic (every screen shows its example data).
//
// Usage (from apps/dashboard):  node scripts/check-copy.mjs [base=http://127.0.0.1:5173] [options]
//   --routes=growth,firm        only these route ids (default: every route in the budgets)
//   --view=worker|admin|all     which view to measure (default all; admin needs the view-as switch, found in the account menu or the old sidebar)
//   --viewports=1440x900,1152x735   default from the budgets
//   --narrow                    also read 390x844 (words and paragraphs only)
//   --theme=light|dark          default light
//   --example                   block the engine and the agent (deterministic example data)
//   --out=qa/knack/copy-report.json   write the measurements
//   --report-only               print and write, never exit 1 (for the baseline)
//   --list                      print the routes and their budgets, then stop
import { chromium } from "playwright";
import fs from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const budgets = JSON.parse(fs.readFileSync(join(here, "..", "qa", "knack", "budgets.json"), "utf8"));
const args = process.argv.slice(2);
const flag = (name) => args.find((a) => a === `--${name}` || a.startsWith(`--${name}=`));
const opt = (name, d) => { const a = flag(name); return a && a.includes("=") ? a.slice(name.length + 3) : a ? "1" : d; };
const base = (args.find((a) => /^https?:/.test(a)) ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const only = opt("routes", "") ? new Set(opt("routes", "").split(",").filter(Boolean)) : null;
const viewSel = opt("view", "all");
const theme = opt("theme", "light");
const viewports = opt("viewports", "") ? opt("viewports", "").split(",").map((v) => v.split("x").map(Number)) : budgets.viewports;
const out = opt("out", "");
const reportOnly = Boolean(flag("report-only"));
const example = Boolean(flag("example"));

/** The budget for one route and one metric: the route's own number, else the default of its audience. */
export function budgetFor(route, metric, audience, state = {}) {
  const r = budgets.routes[route] ?? {};
  if (metric === "wordsAbove" && state.empty && r.wordsAboveEmpty != null) return r.wordsAboveEmpty;
  return r[metric] ?? budgets.defaults[audience]?.[metric];
}

if (flag("list")) {
  for (const [id, r] of Object.entries(budgets.routes)) console.log(id.padEnd(16), r.path.padEnd(18), r.audience.padEnd(8), `above ${budgetFor(id, "wordsAbove", r.audience)}  total ${budgetFor(id, "wordsTotal", r.audience)}  pills ${budgetFor(id, "pills", r.audience)}  controls ${budgetFor(id, "controls", r.audience)}`);
  process.exit(0);
}

/** Runs inside the page: everything is read from the rendered DOM. Mirrors measure-clutter.mjs, plus the element rules. */
const measureInPage = () => {
  const FOLD = window.innerHeight;
  const hiddenAncestor = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      if (e.hidden) return true;
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden") return true;
      if (e.classList.contains("u-sr-only")) return true;
      // The body of a closed disclosure is not on the screen, whatever geometry the browser still reports for it. Its summary is.
      if (e.tagName === "DETAILS" && !e.open) { const sm = el.closest("summary"); if (!(sm && sm.parentElement === e)) return true; }
    }
    return false;
  };
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  const wc = (s) => s.split(/\s+/).filter(Boolean).length;
  const words = (root, foldOnly) => {
    let n = 0;
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (tw.nextNode()) {
      const t = tw.currentNode;
      const s = t.textContent.trim();
      if (!s) continue;
      const el = t.parentElement;
      if (!el || hiddenAncestor(el) || ["SCRIPT", "STYLE", "OPTION"].includes(el.tagName)) continue;
      const range = document.createRange();
      range.selectNodeContents(t);
      const r = range.getBoundingClientRect();
      if (r.width <= 1 || r.height <= 1) continue;
      if (foldOnly && (r.top >= FOLD || r.bottom <= 0)) continue;
      n += wc(s);
    }
    return n;
  };
  const main = document.querySelector("#main");
  const side = document.querySelector(".side, aside[aria-label], [data-sidebar]");
  if (!main) return { noMain: true };
  const above = (el) => { const r = el.getBoundingClientRect(); return r.top < FOLD && r.bottom > 0; };
  const sel = (root, q, foldOnly = true) => [...root.querySelectorAll(q)].filter((e) => vis(e) && !hiddenAncestor(e) && (!foldOnly || above(e)));
  const pills = sel(main, ".pill, [class*='badge'], .chip, [class*='pill']").filter((e, i, a) => !a.some((o) => o !== e && o.contains(e)));
  const controls = sel(main, "button, a[href], input, select, textarea, summary, [role='button'], [role='tab'], [role='switch']");
  const narrow = window.innerWidth <= 760;
  const longP = [];
  for (const el of main.querySelectorAll("p, li, dd, span, div, summary, label, h1, h2, h3")) {
    if (!vis(el) || hiddenAncestor(el)) continue;
    if (narrow && el.closest(".hero-insight")) continue; // the one allowed exception: the hero may take three lines at 390
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ").trim();
    if (wc(own) < 8) continue;
    const cs = getComputedStyle(el);
    const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
    const lines = Math.round(el.getBoundingClientRect().height / lh);
    if (lines > 2) longP.push(`${lines} lines: ${own.slice(0, 60)}`);
  }
  // element rules
  const h1 = main.querySelector("h1");
  const h1Words = h1 ? wc(h1.textContent) : 0;
  const h1IsHero = Boolean(h1 && h1.matches(".hero-insight, [data-hero]"));
  const buttonsLong = sel(main, ".btn, button, a.btn", false)
    .filter((b) => !b.closest(".hint, .segmented, .tabs, .details, .listrow"))
    .map((b) => ({ t: b.textContent.trim(), n: wc(b.textContent), primary: b.classList.contains("btn--primary") }))
    .filter((b) => b.n > (b.primary ? 4 : 3))
    .map((b) => b.t.slice(0, 40));
  const rowTitlesLong = sel(main, ".listrow__title", false).filter((e) => wc(e.textContent) > 12).map((e) => e.textContent.trim().slice(0, 50));
  const ledesLong = sel(main, ".t-lede, .screenhead__limit, .page__lede", false).filter((e) => wc(e.textContent) > 10).map((e) => e.textContent.trim().slice(0, 50));
  const eyebrows = h1 ? sel(main, ".page__head .t-label, .eyebrow", false).map((e) => e.textContent.trim().slice(0, 30)) : [];
  const upper = [];
  for (const el of main.querySelectorAll("*")) {
    if (el.closest("svg") || !vis(el) || hiddenAncestor(el)) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ").trim();
    if (!own) continue;
    if (getComputedStyle(el).textTransform === "uppercase") upper.push(own.slice(0, 30));
  }
  const rows = side ? [...side.querySelectorAll("nav a, nav button, .nav a, .nav button")].filter((e) => vis(e) && !hiddenAncestor(e)) : [];
  const hintWords = side ? [...side.querySelectorAll("[class*='hint']")].filter((e) => vis(e)).reduce((n, e) => n + wc(e.textContent), 0) : 0;
  const empty = Boolean(main.querySelector(".state:not(.state--loading), [data-empty]")) && !main.querySelector("svg[role='img'], figure svg");
  const busy = /Loading|Reading|Starting Knack/i.test(main.innerText);
  return {
    title: h1 ? h1.textContent.trim().slice(0, 80) : null,
    h1Words, h1IsHero,
    wordsAbove: words(main, true), wordsTotal: words(main, false),
    sideWords: side ? words(side, true) : 0, sideRows: rows.length, sideHintWords: hintWords, hasSide: Boolean(side && vis(side)),
    longParas: longP.length, longParaEx: longP.slice(0, 3),
    pills: pills.length, pillTexts: pills.slice(0, 6).map((e) => e.textContent.trim().slice(0, 28)),
    controls: controls.length,
    buttonsLong, rowTitlesLong, ledesLong, eyebrows, uppercase: upper.slice(0, 5), uppercaseCount: upper.length,
    empty, busy,
    gate: /part of the Admin view|Admin view only|not in this view/i.test(main.innerText),
  };
};

async function settle(page) {
  let m = await page.evaluate(measureInPage);
  let prev = -1;
  for (let i = 0; i < 16 && !m.noMain && (m.wordsTotal !== prev || m.busy); i++) {
    prev = m.wordsTotal;
    await page.waitForTimeout(500);
    m = await page.evaluate(measureInPage);
  }
  return m;
}

/** The view-as switch moved from the sidebar into the account menu; try both. The role is held in memory only, so navigate by hash afterwards. */
async function becomeAdmin(page) {
  const old = page.locator(".viewas .segmented button", { hasText: "Admin" });
  if (await old.count()) { await old.first().click(); await page.waitForTimeout(300); return true; }
  const acct = page.locator("[data-account], .acct, button[aria-label*='ccount' i], .side button[aria-haspopup='menu']").first();
  if (!(await acct.count())) return false;
  await acct.click();
  await page.waitForTimeout(250);
  const item = page.getByRole("menuitemradio", { name: /admin/i }).or(page.getByRole("menuitem", { name: /admin/i })).or(page.getByRole("radio", { name: /admin/i })).or(page.getByRole("option", { name: /admin/i })).or(page.getByRole("button", { name: /view as admin|^admin$/i }));
  if (!(await item.count())) return false;
  await item.first().click();
  await page.waitForTimeout(300);
  await page.keyboard.press("Escape").catch(() => undefined);
  return true;
}

const results = [];
const fails = [];
const notes = [];

function judge(id, spec, vp, m, narrow) {
  const aud = spec.audience;
  const problems = [];
  const tag = `${id} @${vp[0]}x${vp[1]}`;
  const check = (label, got, max) => { if (max != null && got > max) problems.push(`${label} ${got} > ${max}`); };
  const state = { empty: m.empty };
  if (!budgets.exempt[id]) {
    check("words above the fold", m.wordsAbove, budgetFor(id, "wordsAbove", aud, state));
    if (!narrow) check("words on the whole default view", m.wordsTotal, budgetFor(id, "wordsTotal", aud));
    check("paragraphs over two lines", m.longParas, budgetFor(id, "longParas", aud));
    if (!narrow) {
      check("pills and badges above the fold", m.pills, budgetFor(id, "pills", aud));
      check("controls above the fold", m.controls, budgetFor(id, "controls", aud));
    }
  }
  if (!narrow) {
    if (m.h1Words > (m.h1IsHero ? budgets.elements.heroWords : budgets.elements.screenTitleWords)) problems.push(`title is ${m.h1Words} words (limit ${m.h1IsHero ? budgets.elements.heroWords : budgets.elements.screenTitleWords})`);
    if (m.buttonsLong.length) problems.push(`buttons over ${budgets.elements.buttonWords} words: ${m.buttonsLong.join(" | ")}`);
    if (m.rowTitlesLong.length) problems.push(`row titles over ${budgets.elements.rowTitleWords} words: ${m.rowTitlesLong.length}`);
    if (m.ledesLong.length) problems.push(`ledes over ${budgets.elements.ledeWords} words: ${m.ledesLong.join(" | ")}`);
    if (m.eyebrows.length) problems.push(`eyebrow above the title: ${m.eyebrows.join(" | ")}`);
    if (m.uppercaseCount) problems.push(`mono capitals outside axes: ${m.uppercase.join(" | ")}`);
  }
  return { tag, problems };
}

const browser = await chromium.launch();
try {
  const sizes = [...viewports, ...(flag("narrow") ? [budgets.narrow] : [])];
  for (const vp of sizes) {
    const narrow = vp[0] <= 760;
    const ctx = await browser.newContext({ viewport: { width: vp[0], height: vp[1] }, colorScheme: theme });
    await ctx.route("**/*", (r) => {
      const req = r.request();
      if (!["GET", "HEAD"].includes(req.method())) return r.abort();
      if (example && /^https?:\/\/[^/]+\/(engine|agent)(\/|$)/.test(req.url())) return r.abort();
      return r.continue();
    });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => notes.push(`pageerror at ${vp.join("x")}: ${e.message}`));
    for (const view of ["worker", "admin"]) {
      if (viewSel !== "all" && viewSel !== view) continue;
      const ids = Object.entries({ ...budgets.routes, ...Object.fromEntries(Object.entries(budgets.exempt).map(([k, v]) => [k, v])) })
        .filter(([id, r]) => (view === "admin" ? r.audience === "admin" : r.audience !== "admin") && (!only || only.has(id)));
      if (ids.length === 0) continue;
      await page.goto("about:blank");
      await page.goto(`${base}/#/home`, { waitUntil: "load" }).catch(() => undefined);
      await page.waitForTimeout(900);
      if (view === "admin") {
        const ok = await becomeAdmin(page);
        if (!ok) { notes.push(`admin view: could not find the view-as switch at ${vp.join("x")}, Admin routes skipped`); continue; }
      }
      for (const [id, spec] of ids) {
        await page.evaluate((h) => { location.hash = h; }, `#${spec.path}`);
        await page.waitForTimeout(id === "graph" ? 2000 : 700);
        const m = await settle(page);
        const landed = await page.evaluate(() => location.hash);
        const want = spec.path.split("?")[0];
        if (m.noMain) { notes.push(`${id} @${vp.join("x")}: no #main, skipped`); continue; }
        if (!landed.startsWith(`#${want}`)) { notes.push(`${id} @${vp.join("x")}: the address went to ${landed}, skipped`); continue; }
        if (m.gate && view === "admin") { fails.push(`${id} @${vp.join("x")}: the Admin gate is showing, so the view-as switch did not take`); continue; }
        const aud = spec.audience === "admin" ? "admin" : spec.audience;
        const { tag, problems } = judge(id, { ...spec, audience: aud }, vp, m, narrow);
        // The sidebar rule: rows and hint words, once per view and window (not at 390, where it is the bottom bar).
        if (!narrow && spec.sidebar !== false && m.hasSide) {
          const sb = budgets.sidebar;
          const rows = view === "admin" ? sb.adminRows : sb.workerRows;
          if (m.sideRows > rows) problems.push(`sidebar rows ${m.sideRows} > ${rows}`);
          if (m.sideHintWords > sb.hintWords) problems.push(`sidebar hint words ${m.sideHintWords} > ${sb.hintWords}`);
          const sw = view === "admin" ? sb.words.admin : sb.words.worker;
          if (m.sideWords > sw) problems.push(`sidebar words ${m.sideWords} > ${sw}`);
        }
        results.push({ view, route: id, viewport: vp.join("x"), theme, example, ...m, problems });
        const brief = `above ${String(m.wordsAbove).padStart(3)}/${budgetFor(id, "wordsAbove", aud, { empty: m.empty }) ?? "-"}  total ${String(m.wordsTotal).padStart(4)}/${budgetFor(id, "wordsTotal", aud) ?? "-"}  long ${m.longParas}  pills ${m.pills}  ctl ${String(m.controls).padStart(2)}  side ${m.sideRows}r ${m.sideWords}w ${m.sideHintWords}h`;
        console.log(`${problems.length ? "FAIL" : "PASS"}  ${tag.padEnd(24)} ${brief}${problems.length ? "\n      " + problems.join("\n      ") : ""}`);
        for (const p of problems) fails.push(`${tag}: ${p}`);
      }
    }
    await ctx.close();
  }
} finally {
  await browser.close();
}

for (const n of notes) console.log(`NOTE  ${n}`);
if (out) {
  fs.mkdirSync(dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify({ at: new Date().toISOString(), base, mode: example ? "example data, engine blocked" : "as served", theme, results }, null, 1));
  console.log(`wrote ${out}`);
}
const measured = results.length;
console.log(`\n${fails.length ? "FAIL" : "OK"}  ${measured} screen reads, ${fails.length} problem${fails.length === 1 ? "" : "s"}${reportOnly ? " (report only)" : ""}`);
process.exit(fails.length && !reportOnly ? 1 : 0);
