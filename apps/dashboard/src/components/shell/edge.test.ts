// Edge cases for the shell (docs/knack-ux/edge-cases.md): the address, the keys, the status line, the menus, the first run and the palette, with unusual,
// missing, hostile and extreme inputs. Each test name is the row's name in that table.
import { describe, expect, it } from "vitest";
import { cardLine, captureRecord, mayAskAgain, readyLines, roleCards, shouldStartFirstRun } from "../../screens/FirstRun/model";
import { SCREENS } from "../../router";
import { hashOf, normalisePath, redirectFor } from "../../routeRedirects";
import { NAV_ENTRIES, canView, clicksFromHome, firmTabOf, labelOf, moreFor, sidebarFor } from "../home/navModel";
import { buildItems, rowsFor, searchItems, tokensOf } from "../home/palette";
import { shellKeyAction, type KeyLike } from "./keys";
import { STARTING_GIVE_UP_MS, statusFor } from "./statusModel";

const q = (s = "") => new URLSearchParams(s);
const key = (k: unknown, over: Partial<KeyLike> = {}): KeyLike => ({ key: k as string, metaKey: true, ctrlKey: false, altKey: false, shiftKey: false, ...over });

describe("the address", () => {
  it("the address is read in lower case, with one leading slash and no trailing slash", () => {
    expect(normalisePath("Needs-You/")).toBe("/needs-you");
    expect(normalisePath("/FIRM/People//")).toBe("/firm/people");
    expect(normalisePath("")).toBe("/");
    expect(normalisePath("///")).toBe("/");
    expect(redirectFor(normalisePath("/Queue"), q())?.path).toBe("/needs-you");
  });
  it("an old route with a trailing slash still redirects", () => { expect(redirectFor("/queue/", q())?.path).toBe("/needs-you"); expect(redirectFor("/privacy//", q())?.path).toBe("/your-data"); });
  it("a route with an empty or malformed query is kept as written, never thrown on", () => {
    expect(hashOf(redirectFor("/queue", q("item=%E0%A4%A"))!)).toContain("item=");
    expect(hashOf(redirectFor("/memory", q("="))!)).toContain("section=remembers");
  });
  it("the Needs you deep link from a corner card carries its item through untouched", () => { expect(redirectFor("/needs-you", q("item=q_9"))).toBeNull(); });
  it("an unknown or empty route is not redirected (the shell lands on Home)", () => { for (const p of ["", "/", "/nope", "/queue-not", "/q"]) expect(redirectFor(p, q()), p).toBeNull(); });
  it("a very long path does not slow or break the redirect", () => { expect(redirectFor(`/${"a".repeat(100_000)}`, q())).toBeNull(); });
  it("the first path segment alone names the screen: every route id is lower-case words and dashes", () => { for (const id of SCREENS) expect(id).toMatch(/^[a-z]+(-[a-z]+)*$/); });
  it("the Firm views are found from both their old and new addresses, and from a nonsense one", () => {
    expect(firmTabOf("/roles")).toBe("roles");
    expect(firmTabOf("/firm/roles")).toBe("roles"); // the old address is redirected before it gets here, and reads right if it is not
    expect(firmTabOf("/firm/people")).toBe("people");
    expect(firmTabOf("")).toBe("overview");
    expect(firmTabOf("/firm/%00")).toBe("overview");
  });
});

describe("the keys", () => {
  it("an event with no key string (autofill, an input method) is not a shortcut and does not throw", () => {
    for (const k of [undefined, null, 0, {}, []]) expect(shellKeyAction(key(k), "worker"), String(k)).toBeNull();
  });
  it("an empty key, a very long key and an unusual key are ignored", () => { for (const k of ["", "Dead", "Unidentified", "x".repeat(10_000), "\u0000"]) expect(shellKeyAction(key(k), "admin"), k.slice(0, 8)).toBeNull(); });
  it("upper-case digits and letters (caps lock) still map the same way", () => { expect(shellKeyAction(key("K", { shiftKey: true }), "worker")?.type).toBe("stop"); expect(shellKeyAction(key("1"), "worker")?.type).toBe("go"); });
  it("a modifier alone is not a shortcut", () => { for (const k of ["Meta", "Control", "Shift", "Alt"]) expect(shellKeyAction(key(k), "worker"), k).toBeNull(); });
});

describe("the status line", () => {
  it("an engine that answers without saying whether it is live reads 'Connected', never 'Live models'", () => {
    expect(statusFor({ engineUp: true, mock: undefined, mode: "live" }).text).toBe("Connected");
    expect(statusFor({ engineUp: true, mock: null, mode: "live" }).text).toBe("Connected");
  });
  it("down beats everything, including a stale mock flag and a mixed screen", () => { expect(statusFor({ engineUp: false, mock: false, mode: "mixed" }).kind).toBe("down"); });
  it("starting turns into 'cannot reach' after thirty seconds, exactly at the limit, and a negative wait is still starting", () => {
    expect(statusFor({ engineUp: null, mock: null, mode: "unknown", waitedMs: STARTING_GIVE_UP_MS - 1 }).kind).toBe("starting");
    expect(statusFor({ engineUp: null, mock: null, mode: "unknown", waitedMs: STARTING_GIVE_UP_MS }).kind).toBe("down");
    expect(statusFor({ engineUp: null, mock: null, mode: "unknown", waitedMs: -500 }).kind).toBe("starting");
    expect(statusFor({ engineUp: null, mock: null, mode: "unknown", waitedMs: Number.NaN }).kind).toBe("starting");
  });
  it("every state is words and a dot, at most four words", () => {
    for (const engineUp of [true, false, null]) for (const mock of [true, false, null, undefined]) for (const mode of ["live", "mixed", "demo", "unknown"] as const) {
      const s = statusFor({ engineUp, mock, mode });
      expect(s.text.split(/\s+/).length).toBeLessThanOrEqual(4);
      expect(["solid", "ring"]).toContain(s.dot);
    }
  });
});

describe("the sidebar and the menus", () => {
  it("a screen id nobody knows has the app's own name as its label and can be viewed (the shell then lands on Home)", () => { expect(labelOf("unknown")).toBe("Knack"); expect(labelOf("nope" as never)).toBe("Knack"); expect(canView("unknown", "worker")).toBe(true); });
  it("More never has more than ten rows, in either view, with or without pinned views, and has no empty label", () => {
    for (const v of ["worker", "admin"] as const) for (const p of [false, true]) {
      const rows = moreFor(v, p);
      expect(rows.length).toBeLessThanOrEqual(10);
      for (const r of rows) { expect(r.label.trim().length).toBeGreaterThan(0); expect(r.path.startsWith("/")).toBe(true); }
    }
  });
  it("every sidebar row is one click from Home and the deepest screen is two", () => {
    for (const v of ["worker", "admin"] as const) {
      const s = sidebarFor(v);
      for (const e of [...s.primary, ...s.admin]) expect(clicksFromHome(e.id, v), e.id).toBeLessThanOrEqual(1);
    }
    for (const e of NAV_ENTRIES.filter((x) => x.group !== "hidden" && !x.admin)) expect(clicksFromHome(e.id, "worker"), e.id).toBeLessThanOrEqual(2);
  });
  it("a worker can never reach an admin screen through the menu, the More sheet or the palette", () => {
    const admin = NAV_ENTRIES.filter((e) => e.admin).map((e) => `/${e.id}`);
    for (const r of moreFor("worker")) expect(admin).not.toContain(r.path);
    for (const i of buildItems("worker")) if (i.target.type === "route") expect(admin).not.toContain(i.target.path);
  });
});

describe("the first run", () => {
  it("a pack with no summary, a summary with no full stop and a summary of one huge word all give a card line without throwing", () => {
    expect(cardLine("")).toBe("");
    expect(cardLine("Reads code")).toBe("Reads code");
    expect(cardLine("x".repeat(500))).toBe("x".repeat(500));
  });
  it("more than five packs show five cards; none shows none", () => {
    const packs = Array.from({ length: 9 }, (_, i) => ({ id: `p${i}`, name: `Role ${i}`, summary: "Does things for people.", depth: "thin" as const }));
    expect(roleCards(packs)).toHaveLength(5);
    expect(roleCards([])).toEqual([]);
  });
  it("the ready lines cope with a pack that has no tools, no risky actions and no hours days", () => {
    const qn = { role: "x", pack: { name: "X", summary: "", extra_cogs: [], risk_classes: { irreversible: [] }, tone_defaults: { length: "short", voice: "plain" } }, questions: [] } as never;
    const lines = readyLines(qn, { tools: [], risky: [], tone: "short", pace: "gradual", hours: { start: "09:00", end: "17:30", days: [] }, capture: false });
    expect(lines).toHaveLength(4);
    for (const l of lines) expect(l).not.toMatch(/undefined|NaN|null/);
  });
  it("Not now asks again after exactly a week, and not for a stored value that is not ours", () => {
    const at = new Date("2026-11-08T10:00:00Z");
    expect(mayAskAgain(captureRecord("not-now", at), new Date(at.getTime() + 7 * 86_400_000))).toBe(true);
    for (const bad of ["not-now:", "not-now:garbage", "NOT-NOW:2026-01-01", "", "yes", "never"]) expect(mayAskAgain(bad, new Date("2030-01-01")), bad).toBe(false);
  });
  it("first run never opens while the engine is unreachable, starting, or has already named the worker", () => {
    const base = { engineUp: true, extReady: true, role: null, person: null, done: false, path: "/home", hash: "" };
    expect(shouldStartFirstRun({ ...base, engineUp: false })).toBe(false);
    expect(shouldStartFirstRun({ ...base, engineUp: null })).toBe(false);
    expect(shouldStartFirstRun({ ...base, person: "p_1" })).toBe(false);
    expect(shouldStartFirstRun({ ...base, role: "x" })).toBe(false);
  });
});

describe("the palette", () => {
  const items = buildItems("worker");
  it("an empty, blank or one-letter query lists the screens or nothing, never everything", () => {
    expect(rowsFor(items, "   ", false).rows.length).toBeLessThanOrEqual(8);
    expect(searchItems(items, "").length).toBe(0);
  });
  it("a query of thousands of characters, punctuation or regex characters does not throw and matches nothing", () => {
    for (const bad of ["x".repeat(20_000), "((((", "[a-", ".*", "\\", "%00", "<script>"]) expect(() => searchItems(items, bad), bad.slice(0, 8)).not.toThrow();
    expect(searchItems(items, "x".repeat(20_000)).length).toBe(0);
  });
  it("unicode and right-to-left queries are split into words and do not throw", () => { for (const bad of ["استحقاق", "审核", "🧮", "Éligibilité"]) expect(tokensOf(bad).length).toBe(1); expect(() => searchItems(items, "استحقاق")).not.toThrow(); });
  it("a screen can be found by the name it had before Knack", () => {
    for (const [word, id] of [["queue", "screen:needs-you"], ["briefing", "screen:needs-you"], ["repeats", "screen:routines"], ["memory", "screen:your-data"], ["privacy", "screen:your-data"], ["predictions", "screen:forecasts"], ["genome", "screen:genome"]] as const) {
      expect(searchItems(items, word).map((s) => s.item.id), word).toContain(id);
    }
  });
  it("thousands of extra rows (pointers) are capped at seven until asked", () => {
    const pointers = Array.from({ length: 3000 }, (_, i) => ({ id: `p${i}`, kind: "k", headline: `Pointer ${i}`, detail: null, numbers: {}, origin: "synthetic", n: null, n_unit: null, polarity: "note", polarity_label: null, glyph: null, a11y_label: null, badge: null, details_available: false, action: null })) as never;
    const many = buildItems("worker", { pointers });
    const r = rowsFor(many, "pointer", false);
    expect(r.rows.length).toBeLessThanOrEqual(8);
    expect(r.capped).toBe(true);
  });
});
