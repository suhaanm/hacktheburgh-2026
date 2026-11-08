// The firm brief as the printer sees it: print media emulated, the screen part hidden, the one A4 page shown. Writes qa/knack/admin-brief-print.png (git-ignored)
// and fails when the screen headline is still visible or the A4 page is not.
// Usage: node scripts/shot-brief-print.mjs [base=http://127.0.0.1:5193]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { openAs } from "./lib/knack-page.mjs";

const base = process.argv.slice(2).find((a) => a.startsWith("http")) ?? "http://127.0.0.1:5193";
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "qa", "knack", "admin-brief-print.png");
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 900, height: 1200 }, colorScheme: "dark" });
await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
const page = await ctx.newPage();
await openAs(page, base, "admin");
await page.goto(`${base}/#/firm/brief`);
await page.waitForTimeout(700);
const onScreen = await page.evaluate(() => ({ page: getComputedStyle(document.querySelector(".brief-print-only")).display, head: getComputedStyle(document.querySelector(".brief-screen")).display }));
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(200);
const inPrint = await page.evaluate(() => ({ page: getComputedStyle(document.querySelector(".brief-print-only")).display, head: getComputedStyle(document.querySelector(".brief-screen")).display, bg: getComputedStyle(document.body).backgroundColor }));
await page.screenshot({ path: out, fullPage: true });
await browser.close();
const ok = onScreen.page === "none" && onScreen.head !== "none" && inPrint.page !== "none" && inPrint.head === "none";
console.log(`${ok ? "ok " : "BAD"} on screen: A4 page ${onScreen.page}, headline ${onScreen.head}. In print: A4 page ${inPrint.page}, headline ${inPrint.head}, background ${inPrint.bg}`);
if (!ok) process.exit(1);
