// Pictures of the graph layer for the look check: the work graph at rest, with a name on hover, with a node opened, with the keyboard on it, with the key open,
// and (--screen=genome) the transition graph. Light and dark at 1440x900, 1152x735 and 390x844, into qa/graph/ (do not commit the PNGs).
// Read-only: every non-GET request is refused, and the engine and agent are blocked so the example data is what is drawn.
// Usage (from apps/dashboard):  node scripts/shot-graph.mjs <base> [--screen=graph|genome] [--states=rest,hover,open,keys,key] [--sizes=1440x900,...] [--themes=light,dark] [--big=1000]
// --n=N (or --big=N) serves a synthetic graph of N nodes in place of the example one: 0 for the empty state, 1 for a lone node, 1000 for a stress picture.
import { chromium } from "playwright";
import fs from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { openAs } from "./lib/knack-page.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const base = (args.find((a) => /^https?:/.test(a)) ?? "http://127.0.0.1:5197").replace(/\/$/, "");
const opt = (n, d) => { const a = args.find((x) => x.startsWith(`--${n}=`)); return a ? a.slice(n.length + 3) : d; };
const screen = opt("screen", "graph");
const states = opt("states", "rest,hover,open,keys,key").split(",");
const sizes = opt("sizes", "1440x900,1152x735,390x844").split(",").map((s) => s.split("x").map(Number));
const themes = opt("themes", "light,dark").split(",");
const nArg = opt("n", opt("big", ""));
const custom = nArg !== "";
const big = custom ? Number(nArg) : 0;
const outDir = join(here, "..", "qa", "graph");
fs.mkdirSync(outDir, { recursive: true });

/** A graph of n nodes with the awkward things a real one has. Deterministic. */
function bigGraph(n) {
  let s = 11;
  const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  const kinds = ["routine", "skill", "memory", "automation"];
  const nodes = Array.from({ length: n }, (_, i) => ({ id: `n${i}`, type: kinds[i % 4], label: `Node number ${i}`, size: kinds[i % 4] === "skill" ? rnd() : 4 + rnd() * 90, strength: rnd(), last_seen: "2026-11-07", why: "Seen often.", editable: false, memory_line_id: null }));
  const links = [];
  for (let i = 1; i < n; i++) links.push({ a: `n${i}`, b: `n${Math.floor(rnd() * i)}`, kind: rnd() < 0.03 ? "combined" : "related", weight: rnd() });
  return { meta: { origin: "synthetic", n, n_unit: "nodes", split: null, interval_level: 0.95, note: "stress", generated_at: "2026-11-08T00:00:00Z" }, data: { nodes, links } };
}

const browser = await chromium.launch();
for (const theme of themes) {
  for (const [w, h] of sizes) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme, reducedMotion: "no-preference" });
    await ctx.route("**/*", (r) => {
      const req = r.request();
      if (!["GET", "HEAD"].includes(req.method())) return r.abort();
      if (/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/.test(req.url())) {
        // A stress picture needs the page to believe the engine is up: serve the graph, say "ok" to the health check, and answer everything else "not found"
        // (the page then draws that screen's example data, as it does for an engine that lacks a route).
        if (custom && /\/graph\/work/.test(req.url())) return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(bigGraph(big)) });
        if (custom && /\/health/.test(req.url())) return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "ok" }) });
        if (custom) return r.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "not_found", message: "not found" } }) });
        return r.abort();
      }
      return r.continue();
    });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    if (!(await openAs(page, base, "worker"))) { console.log(`could not open the worker view at ${w}x${h}`); await ctx.close(); continue; }
    await page.evaluate((x) => { location.hash = x; }, `#/${screen}`);
    await page.waitForTimeout(big > 120 ? 4500 : 2600);
    const file = (s) => join(outDir, `${screen}${custom ? `-n${big}` : ""}-${s}-${theme}-${w}x${h}.png`);
    const shot = async (s) => { await page.screenshot({ path: file(s) }); console.log(file(s)); };

    if (screen === "graph") {
      const node = page.locator(".gnode").first();
      if (states.includes("rest")) await shot("rest");
      if (states.includes("hover") && (await node.count())) {
        const box = await node.boundingBox();
        if (box) { await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.waitForTimeout(450); await shot("hover"); await page.mouse.move(2, 2); }
      }
      if (states.includes("open") && (await node.count())) {
        await page.locator(".gnode[data-kind='routine']").first().click();
        await page.waitForTimeout(700);
        await shot("open");
        const nums = page.locator(".gpanel summary", { hasText: "The numbers" });
        if (await nums.count()) { await nums.click(); await page.waitForTimeout(300); await shot("open-numbers"); }
        await page.keyboard.press("Escape");
        await page.waitForTimeout(300);
      }
      if (states.includes("keys")) {
        await page.evaluate(() => { document.activeElement && document.activeElement.blur && document.activeElement.blur(); window.scrollTo(0, 0); });
        for (let i = 0; i < 40; i++) {
          await page.keyboard.press("Tab");
          if (await page.evaluate(() => document.activeElement && document.activeElement.classList.contains("gcanvas"))) break;
        }
        for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
        await page.waitForTimeout(450);
        await shot("keys");
      }
      if (states.includes("key")) {
        await page.keyboard.press("Escape");
        const sum = page.locator("summary", { hasText: "What are these?" });
        if (await sum.count()) {
          await sum.scrollIntoViewIfNeeded();
          await sum.click();
          await page.waitForTimeout(300);
          const chip = page.locator(".gkey__item").nth(1);
          if (await chip.count()) { await chip.hover(); await page.waitForTimeout(300); }
          await shot("key");
        }
      }
    } else {
      await page.evaluate(() => window.scrollTo(0, 0));
      const tab = page.getByRole("button", { name: "Transition graph" });
      if (await tab.count()) { await tab.click(); await page.waitForTimeout(900); }
      if (states.includes("rest")) await shot("rest");
      const node = page.locator(".tgnode").first();
      if (states.includes("hover") && (await node.count())) {
        const box = await node.boundingBox();
        if (box) { await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.waitForTimeout(450); await shot("hover"); await page.mouse.move(2, 2); }
      }
      if (states.includes("keys")) {
        for (let i = 0; i < 60; i++) {
          await page.keyboard.press("Tab");
          if (await page.evaluate(() => document.activeElement && document.activeElement.classList.contains("tgraph__svg"))) break;
        }
        for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowDown");
        await page.waitForTimeout(450);
        await shot("keys");
      }
      if (states.includes("key")) {
        const sum = page.locator("summary", { hasText: "What are these?" });
        if (await sum.count()) { await sum.scrollIntoViewIfNeeded(); await sum.click(); await page.waitForTimeout(300); await page.locator(".gkey__item").first().hover(); await page.waitForTimeout(300); await shot("key"); }
      }
    }
    if (errors.length) console.log(`page errors at ${theme} ${w}x${h}:`, errors.join(" | "));
    await ctx.close();
  }
}
await browser.close();
