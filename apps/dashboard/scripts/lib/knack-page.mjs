// Shared by check-copy.mjs, check-clicks.mjs and shot-knack.mjs: get a fresh browser profile to a usable screen as a worker or an admin.
//
// Two things stood in the way of a fresh profile (found 7 Nov, merged main):
//  1. First run. With the engine answering and no role chosen, the app sends a new profile to the bare #/first-run screen, which has no sidebar, so no
//     account menu and no way to switch view. The app remembers that first run is done under FIRST_RUN_KEY (a localStorage key, the same one the app reads).
//  2. The view role. The app remembers the Admin view under VIEW_STORAGE_KEY, which it reads on load, so setting it is the same as choosing "Admin" in the
//     account menu and does not depend on that menu's markup. The menu stays as the fallback.
// Both keys keep the old product name: they are storage keys (the allow-list of docs/knack-ux/banned-phrases.json).
export const FIRST_RUN_KEY = "understudy-first-run-done";
export const VIEW_STORAGE_KEY = "understudy-view-as";

/** True when the sidebar (or the bottom bar) shows the Admin destinations. */
async function isAdmin(page) {
  return (await page.locator("nav a, nav button").filter({ hasText: /^\s*Firm\s*$/ }).count()) > 0;
}

/** The account menu: the button, then "Admin". Used only when remembering the view did not work. */
async function viaMenu(page) {
  const old = page.locator(".viewas .segmented button", { hasText: "Admin" });
  if (await old.count()) { await old.first().click(); await page.waitForTimeout(300); return; }
  const menuBtn = page.getByRole("button", { name: /^Menu$/ });
  if ((await menuBtn.count()) && (await menuBtn.first().isVisible())) { await menuBtn.first().click(); await page.waitForTimeout(250); }
  await page.locator("[data-account], .account__btn, .acct, button[aria-label*='ccount' i]").first().click();
  await page.waitForTimeout(200);
  await page.getByRole("menuitemradio", { name: /admin/i }).or(page.getByRole("menuitem", { name: /admin/i })).or(page.getByRole("radio", { name: /admin/i })).or(page.getByRole("button", { name: /view as admin|^admin$/i })).first().click();
  await page.waitForTimeout(300);
  await page.keyboard.press("Escape").catch(() => undefined);
}

/**
 * Open the app on Home as `view` ("worker" or "admin") with first run marked done. Returns true when the view is the one asked for.
 * Navigate by hash afterwards (a full reload would read the remembered role again, which is fine, but a hash change is quicker).
 */
export async function openAs(page, base, view = "worker") {
  await page.goto("about:blank");
  await page.goto(`${base}/#/home`, { waitUntil: "load" }).catch(() => undefined);
  await page.evaluate(([first, key, v]) => {
    try {
      window.localStorage.setItem(first, new Date().toISOString());
      if (v === "admin") window.localStorage.setItem(key, "admin"); else window.localStorage.removeItem(key);
    } catch { /* storage blocked: the menu fallback below still works */ }
  }, [FIRST_RUN_KEY, VIEW_STORAGE_KEY, view]);
  await page.goto("about:blank");
  await page.goto(`${base}/#/home`, { waitUntil: "load" }).catch(() => undefined);
  await page.waitForTimeout(900);
  if (view !== "admin") return true;
  if (await isAdmin(page)) return true;
  try { await viaMenu(page); } catch { return false; }
  return isAdmin(page);
}

/**
 * Show the page real engine data without a token of its own: relay its GET requests for /engine and /agent through a running dashboard (the owner's
 * :5173, whose proxy adds the per-boot token). Every other method is refused; nothing here can change anything. Register it AFTER the read-only route
 * of the context so it wins for /engine and /agent.
 */
export async function relayLive(ctx, liveBase) {
  const base = liveBase.replace(/\/$/, "");
  await ctx.route(/^https?:\/\/[^/]+\/(engine|agent)(\/|$)/, async (route) => {
    const req = route.request();
    if (!["GET", "HEAD"].includes(req.method())) return route.abort();
    const u = new URL(req.url());
    let res = null;
    try { res = await fetch(`${base}${u.pathname}${u.search}`); } catch { res = null; }
    if (!res) return route.abort();
    return route.fulfill({ status: res.status, headers: { "content-type": res.headers.get("content-type") ?? "application/json" }, body: Buffer.from(await res.arrayBuffer()) });
  });
}
