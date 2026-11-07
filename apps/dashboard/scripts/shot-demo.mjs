// Screenshot a dashboard screen in demo-fixture mode: the engine and agent are blocked, so the fixtures answer.
// Usage: node scripts/shot-demo.mjs <url> <out.png> [--w 1440] [--h 900] [--dark] [--full] [--wait 1500] [--click "text"]
import { chromium } from "playwright";
const [url, out, ...rest] = process.argv.slice(2);
const arg = (k, d) => { const i = rest.indexOf(k); return i >= 0 && rest[i + 1] ? rest[i + 1] : d; };
const w = Number(arg("--w", 1440)), h = Number(arg("--h", 900)), wait = Number(arg("--wait", 1500));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: rest.includes("--dark") ? "dark" : "light" });
await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
const page = await ctx.newPage();
page.on("pageerror", (e) => console.error("pageerror:", e.message));
page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && console.error("console.error:", m.text()));
await page.goto(url, { waitUntil: "networkidle" }).catch(() => undefined);
await page.waitForTimeout(wait);
const click = arg("--click", "");
if (click) { await page.getByText(click, { exact: false }).first().click(); await page.waitForTimeout(500); }
await page.screenshot({ path: out, fullPage: rest.includes("--full") });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
console.log(`saved ${out}${overflow ? "  WARNING: horizontal overflow" : ""}`);
await browser.close();
