#!/usr/bin/env node
// Headless screenshot helper so agents can look at their UI without fighting over the shared browser pane.
// Usage: node scripts/shot.mjs <url> <out.png> [--w 1440] [--h 900] [--dark] [--full] [--wait 800]
import { chromium } from "playwright";

const [url, out, ...rest] = process.argv.slice(2);
if (!url || !out) {
  console.error("usage: shot.mjs <url> <out.png> [--w N] [--h N] [--dark] [--full] [--wait ms]");
  process.exit(2);
}
const arg = (k, d) => {
  const i = rest.indexOf(k);
  return i >= 0 && rest[i + 1] ? rest[i + 1] : d;
};
const w = Number(arg("--w", 1440));
const h = Number(arg("--h", 900));
const wait = Number(arg("--wait", 800));
const dark = rest.includes("--dark");
const full = rest.includes("--full");

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: w, height: h },
  colorScheme: dark ? "dark" : "light",
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();
page.on("pageerror", (e) => console.error("pageerror:", e.message));
page.on("console", (m) => m.type() === "error" && console.error("console.error:", m.text()));
await page.goto(url, { waitUntil: "networkidle", timeout: 30000 }).catch((e) => console.error("goto:", e.message));
await page.waitForTimeout(wait);
await page.screenshot({ path: out, fullPage: full });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
console.log(`saved ${out} (${w}x${h}${dark ? ", dark" : ""}${full ? ", full" : ""})${overflow ? "  WARNING: horizontal overflow" : ""}`);
await browser.close();
