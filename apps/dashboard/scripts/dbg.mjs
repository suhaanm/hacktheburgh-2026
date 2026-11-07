import { chromium } from "playwright";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, (r) => r.abort());
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("pageerror", e.message));
await page.goto("http://127.0.0.1:5191/#/week"); await page.waitForTimeout(800);
await page.goto("http://127.0.0.1:5191/#/notices");
for (let i = 0; i < 25; i++) {
  await page.waitForTimeout(200);
  console.log(i * 200, await page.evaluate(() => location.hash), "sheet:", await page.locator("[data-testid=settings-sheet]").count(), "groups:", await page.locator("details.notices__group").count());
}
await browser.close();
