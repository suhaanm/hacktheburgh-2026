// Screenshots of the Growth page and its sections, as a worker, with the example data (the engine and the agent are blocked, so the picture is repeatable),
// in light and dark at 1440 by 900 and 390 by 844. Writes apps/dashboard/qa/knack/growth-<name>-<theme>-<width>.png (git-ignored) and prints one line per
// shot with horizontal overflow, page errors and any NaN or undefined in the visible text.
// Usage: node scripts/shot-growth.mjs [base=http://127.0.0.1:5193] [--only=top,steps] [--theme=light|dark] [--width=1440|390] [--role=programmer]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { openAs } from "./lib/knack-page.mjs";

const args = process.argv.slice(2);
const base = args.find((a) => a.startsWith("http")) ?? "http://127.0.0.1:5193";
const only = (args.find((a) => a.startsWith("--only=")) ?? "").slice(7).split(",").filter(Boolean);
const themeOnly = (args.find((a) => a.startsWith("--theme=")) ?? "").slice(8);
const widthOnly = Number((args.find((a) => a.startsWith("--width=")) ?? "").slice(8)) || 0;
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack");

const SECTIONS = ["time", "steps", "map", "commits"];
const SHOTS = [
  { name: "top", hash: "/growth", full: true },
  ...SECTIONS.map((s) => ({ name: s, hash: `/growth?section=${s}`, full: false, wait: 1400 })),
  ...SECTIONS.map((s) => ({ name: `${s}-open`, hash: `/growth?section=${s}`, full: true, wait: 1400 })),
];

const browser = await chromium.launch();
let bad = 0;
for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }].filter((v) => !widthOnly || v.width === widthOnly)) {
  for (const theme of ["light", "dark"].filter((t) => !themeOnly || t === themeOnly)) {
    const ctx = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "no-preference" });
    await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error" && !/ERR_CONNECTION_REFUSED|Failed to load resource|ERR_FAILED/.test(m.text())) errors.push(`console: ${m.text()}`); });
    for (const s of SHOTS) {
      if (only.length && !only.includes(s.name)) continue;
      errors.length = 0;
      await openAs(page, base, "worker");
      await page.addInitScript?.(() => {});
      await page.goto(`${base}/#${s.hash}`);
      await page.waitForTimeout(s.wait ?? 900);
      const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const text = await page.evaluate(() => document.querySelector("#main")?.innerText ?? "");
      const junk = /\b(NaN|undefined|null|Infinity)\b|\[object/.test(text);
      const file = join(out, `growth-${s.name}-${theme}-${viewport.width}.png`);
      await page.screenshot({ path: file, fullPage: s.full });
      const flag = wide > 1 || junk || errors.length ? "BAD" : "ok ";
      if (flag === "BAD") bad += 1;
      console.log(`${flag} ${s.name.padEnd(14)} ${theme.padEnd(5)} ${viewport.width}  overflow ${wide}px${junk ? "  NaN or undefined in the text" : ""}${errors.length ? `  ${errors[0].slice(0, 100)}` : ""}`);
    }
    await ctx.close();
  }
}
await browser.close();
console.log(bad ? `${bad} bad` : "all fine");
