import { describe, expect, it } from "vitest";
import type { AdminInsight, WirePointer } from "../firm/wire";
import { FIRM_TABS, NAV_ENTRIES } from "./navModel";
import {
  DEFAULT_CAP, NO_CAPS, askItem, buildItems, groupRows, insightPath, isNavKey, matchToken, moveIndex, pointerPath, resultsText, rowsFor, scoreItem, searchItems,
  segments, tokensOf, wrapIndex, type PaletteItem,
} from "./palette";

const pointer = (id: string, headline: string, action: WirePointer["action"] = { label: "Open the list", to: "repeats", query: null }): WirePointer => ({
  id, kind: "repeat", headline, detail: null, numbers: {}, origin: "synthetic", n: null, n_unit: null, polarity: "attention", polarity_label: "Worth a look",
  glyph: null, a11y_label: null, badge: "synthetic firm", details_available: true, action,
});
const insight = (id: string, headline: string): AdminInsight => ({
  id, headline, role: "all", effect: null, n: 60, n_unit: "people", origin: "synthetic", drill: id, kind: "gap", polarity: "attention", polarity_label: "Worth a look",
  glyph: null, a11y_label: null, position: 1, text: null, badge: null, split: null, statement: null, action: null,
});
const item = (label: string, over: Partial<PaletteItem> = {}): PaletteItem => ({
  id: `x:${label}`, kind: "screen", label, hint: "", also: "", group: "Screens", target: { type: "route", path: `/${label.toLowerCase()}` }, ...over,
});

describe("matchToken tiers", () => {
  it("ranks whole text, prefix, word start, substring, then letters in order", () => {
    const whole = matchToken("growth", "Growth")!.score;
    const prefix = matchToken("gro", "Growth")!.score;
    const word = matchToken("habits", "Git habits")!.score;
    const sub = matchToken("row", "Growth")!.score;
    const seq = matchToken("grt", "Growth")!.score;
    expect(whole).toBeGreaterThan(prefix);
    expect(prefix).toBeGreaterThan(word);
    expect(word).toBeGreaterThan(sub);
    expect(sub).toBeGreaterThan(seq);
    expect(seq).toBeGreaterThan(0);
  });
  it("is case-insensitive and reports the matched positions", () => {
    expect(matchToken("GRO", "growth")!.positions).toEqual([0, 1, 2]);
    expect(matchToken("hab", "Git habits")!.positions).toEqual([4, 5, 6]);
  });
  it("returns null when letters are missing or out of order, and never matches one stray letter as letters in order", () => {
    expect(matchToken("xyz", "Growth")).toBeNull();
    expect(matchToken("htg", "Growth")).toBeNull();
    expect(matchToken("", "Growth")).toBeNull();
    expect(matchToken("z", "Growth")).toBeNull();
  });
  it("only matches letters in order when the letters are close together", () => {
    expect(matchToken("gro", "You needed fewer cues on the cliff check this fortnight")).toBeNull();
    expect(matchToken("prv", "Privacy")).not.toBeNull();
    expect(matchToken("gh", "Git habits")).not.toBeNull();
  });
  it("can switch letters-in-order off, for hints and keywords", () => {
    expect(matchToken("prv", "Privacy", false)).toBeNull();
    expect(matchToken("priv", "Privacy", false)).not.toBeNull();
  });
  it("prefers a subsequence that lands on word starts", () => {
    const a = matchToken("gh", "Git habits")!.score;
    const b = matchToken("gh", "Graph")!.score;
    expect(a).toBeGreaterThan(b);
  });
});

describe("searchItems", () => {
  const items = buildItems("worker");
  it("puts a prefix match ahead of a looser one", () => {
    expect(searchItems(items, "gro")[0].item.id).toBe("screen:growth");
    expect(searchItems(items, "your d")[0].item.id).toBe("screen:your-data");
    expect(searchItems(items, "priv")[0].item.id).toBe("screen:your-data"); // the old name still finds it
  });
  it("finds a screen by letters in order", () => {
    expect(searchItems(items, "gro").map((s) => s.item.id)).toContain("screen:growth");
    expect(searchItems(items, "cmts").map((s) => s.item.id)).toContain("growth:commits"); // letters in order: c-m-t-s in "commits"
  });
  it("matches words in the hint and in the extra keywords, and needs every word to match", () => {
    expect(searchItems(buildItems("admin"), "stuck forecast").map((s) => s.item.id)).toContain("screen:forecasts");
    expect(searchItems(items, "stuck zzzzqq")).toEqual([]);
    expect(searchItems(items, "hit list").map((s) => s.item.id)).toContain("screen:routines");
  });
  it("counts the label for more than the hint", () => {
    const list = [item("Alpha", { hint: "memory notes" }), item("Memory", { hint: "alpha" })];
    expect(searchItems(list, "memory")[0].item.label).toBe("Memory");
  });
  it("drops matches far weaker than the best one, so a clear hit has no tail of coincidences", () => {
    const hits = searchItems(items, "gro").map((s) => s.item.id);
    expect(hits[0]).toBe("screen:growth");
    const list = [item("Growth"), item("Notes", { hint: "background" })];
    expect(searchItems(list, "gro").map((s) => s.item.label)).toEqual(["Growth"]);
    // with no strong hit, weaker ones stay
    expect(searchItems([item("Notes", { hint: "background" })], "gro").length).toBe(1);
  });
  it("keeps the listed order for equal scores, and gives nothing for an empty query", () => {
    const list = [item("Notes one"), item("Notes two"), item("Notes three")];
    expect(searchItems(list, "notes").map((s) => s.item.label)).toEqual(["Notes one", "Notes two", "Notes three"]);
    expect(searchItems(list, "   ")).toEqual([]);
  });
  it("scoreItem is null for no tokens", () => {
    expect(scoreItem([], item("Growth"))).toBeNull();
    expect(tokensOf("  Stuck   Forecast ")).toEqual(["stuck", "forecast"]);
  });
});

describe("buildItems is role-aware", () => {
  const ids = (v: "worker" | "admin", extra = {}) => buildItems(v, extra).map((i) => i.id);
  it("never lists an admin screen, Firm view or the brief in the Worker view", () => {
    const w = ids("worker");
    for (const id of ["firm", "brief", "forecasts", "roles", "people", "onboarding", "automation", "risk", "models", "evidence", "agents"]) expect(w, id).not.toContain(`screen:${id}`);
    expect(w.some((i) => i.startsWith("tab:"))).toBe(false);
    expect(w).not.toContain("action:brief");
    expect(w).toContain("action:view_admin");
    expect(w).not.toContain("action:view_worker");
    expect(w).toContain("action:tour");
  });
  it("lists the eight Admin destinations, the three behind More and the brief in the Admin view, and none of the worker's five", () => {
    const a = ids("admin");
    for (const t of FIRM_TABS) expect(a, t.id).toContain(`screen:${t.id === "overview" ? "firm" : t.id}`);
    for (const id of ["models", "evidence", "agents"]) expect(a, id).toContain(`screen:${id}`);
    for (const id of ["home", "needs-you", "routines", "growth", "your-data"]) expect(a, id).not.toContain(`screen:${id}`);
    expect(a.some((i) => i.startsWith("growth:"))).toBe(false);
    expect(a).toContain("action:brief");
    expect(a).toContain("action:view_worker");
    expect(a).not.toContain("action:view_admin");
  });
  it("lists every screen the menu lists, in menu order", () => {
    for (const view of ["worker", "admin"] as const) {
      const screens = buildItems(view).filter((i) => i.kind === "screen").map((i) => i.id);
      expect(screens).toEqual(NAV_ENTRIES.filter((e) => e.group !== "hidden" && (view === "admin" ? e.admin : !e.admin)).map((e) => `screen:${e.id}`));
    }
  });
  it("lists the four sections of Growth for a worker, each at its own address, and never for an admin", () => {
    const sections = buildItems("worker").filter((i) => i.kind === "section");
    expect(sections.map((i) => i.target)).toEqual([
      { type: "route", path: "/growth?section=time" }, { type: "route", path: "/growth?section=steps" },
      { type: "route", path: "/growth?section=map" }, { type: "route", path: "/growth?section=commits" },
    ]);
    // The old names find them: Week, Presence, Genome, Graph and Git.
    const hit = (q: string) => searchItems(buildItems("worker"), q).map((s) => s.item.id);
    expect(hit("genome")).toContain("growth:steps");
    expect(hit("presence")).toContain("growth:time");
    expect(hit("week")).toContain("growth:time");
    expect(hit("graph")).toContain("growth:map");
    expect(hit("git")).toContain("growth:commits");
  });
  it("lists worker pointers only in the Worker view and admin insights only in the Admin view", () => {
    const extra = { pointers: [pointer("w1", "You repeated one step nine times")], insights: [insight("a1", "New starters reach independence later")] };
    expect(ids("worker", extra)).toContain("pointer:w1");
    expect(ids("worker", extra)).not.toContain("insight:a1");
    expect(ids("admin", extra)).toContain("insight:a1");
    expect(ids("admin", extra)).not.toContain("pointer:w1");
  });
  it("goes where the pointer's action or the insight says", () => {
    const items = buildItems("worker", { pointers: [pointer("w1", "One", { label: "Open", to: "growth", query: "skill=reconcile" }), pointer("w2", "Two", null)] });
    expect(items.find((i) => i.id === "pointer:w1")!.target).toEqual({ type: "route", path: "/growth?skill=reconcile" });
    expect(items.find((i) => i.id === "pointer:w2")!.target).toEqual({ type: "route", path: "/home" });
    expect(pointerPath({ action: { label: "x", to: "repeats", query: null } })).toBe("/repeats");
    expect(insightPath("ins a/1")).toBe("/firm?insight=ins%20a%2F1");
    const admin = buildItems("admin", { insights: [insight("a1", "A")] });
    expect(admin.find((i) => i.id === "insight:a1")!.target).toEqual({ type: "route", path: "/firm?insight=a1" });
  });
  it("finds an insight by its headline", () => {
    const items = buildItems("admin", { insights: [insight("a1", "Skipping the cliff check explains the largest gap")] });
    expect(searchItems(items, "cliff")[0].item.id).toBe("insight:a1");
  });
});

describe("rowsFor", () => {
  const items = buildItems("worker", { pointers: [pointer("w1", "P1"), pointer("w2", "P2")] });
  it("an empty query lists the five screens of a worker (not the Growth sections), then a Show all row", () => {
    const r = rowsFor(items, "", false);
    const shown = r.rows.filter((x) => x.type === "item");
    expect(shown.length).toBe(5);
    expect(shown.every((x) => x.type === "item" && x.item.kind === "screen")).toBe(true);
    expect(r.rows[r.rows.length - 1]).toEqual({ type: "more", count: items.length });
    expect(r.capped).toBe(true);
    expect(r.total).toBe(items.length);
    expect(r.rows.length).toBe(6);
  });
  it("an empty query lists at most seven screens in menu order for an admin, who has eleven, then a Show all row", () => {
    const admin = buildItems("admin");
    const r = rowsFor(admin, "", false);
    expect(DEFAULT_CAP).toBe(7);
    const shown = r.rows.filter((x) => x.type === "item");
    expect(shown.length).toBe(7);
    expect(shown.map((x) => (x.type === "item" ? x.item.id : ""))).toEqual(["screen:firm", "screen:brief", "screen:forecasts", "screen:roles", "screen:people", "screen:onboarding", "screen:automation"]);
    expect(r.rows[r.rows.length - 1]).toEqual({ type: "more", count: admin.length });
    expect(r.rows.length).toBe(8);
  });
  it("Show all lists everything: screens, pointers and actions", () => {
    const r = rowsFor(items, "", true);
    expect(r.rows.length).toBe(items.length);
    expect(r.capped).toBe(false);
    expect(r.rows.some((x) => x.type === "item" && x.item.kind === "action")).toBe(true);
  });
  it("a query shows the best seven with Show all, and all once expanded", () => {
    const wide = Array.from({ length: 12 }, (_, i) => item(`Notes ${i}`));
    const r = rowsFor(wide, "notes", false);
    expect(r.rows.length).toBe(8);
    expect(r.rows[7]).toEqual({ type: "more", count: 12 });
    expect(rowsFor(wide, "notes", true).rows.length).toBe(12);
  });
  it("a short list has no Show all row", () => {
    const r = rowsFor(items, "growth", false);
    expect(r.capped).toBe(false);
    expect(r.rows.every((x) => x.type === "item")).toBe(true);
    expect(r.rows[0].type === "item" && r.rows[0].item.id).toBe("screen:growth");
  });
  it("no matches gives no rows", () => {
    const r = rowsFor(items, "qqqqzz", false);
    expect(r.rows).toEqual([]);
    expect(r.total).toBe(0);
  });
});

describe("groupRows", () => {
  it("groups consecutive rows by heading and numbers the options in order", () => {
    const r = rowsFor(buildItems("worker"), "", false);
    const groups = groupRows(r.rows);
    const flat = groups.flatMap((g) => g.rows.map((x) => x.index));
    expect(flat).toEqual(r.rows.map((_, i) => i));
    expect(groups[0].heading).toBe("Go to");
    expect(groups[groups.length - 1].heading).toBeNull();
  });
  it("can leave the headings off", () => {
    expect(groupRows(rowsFor(buildItems("worker"), "gro", false).rows, false).every((g) => g.heading === null)).toBe(true);
  });
});

describe("keyboard index maths", () => {
  it("wraps in both directions", () => {
    expect(wrapIndex(0, -1, 5)).toBe(4);
    expect(wrapIndex(4, 1, 5)).toBe(0);
    expect(wrapIndex(2, 1, 5)).toBe(3);
    expect(wrapIndex(0, 1, 0)).toBe(-1);
  });
  it("moves with the navigation keys", () => {
    expect(moveIndex(0, "ArrowUp", 4)).toBe(3);
    expect(moveIndex(3, "ArrowDown", 4)).toBe(0);
    expect(moveIndex(2, "Home", 4)).toBe(0);
    expect(moveIndex(0, "End", 4)).toBe(3);
    expect(moveIndex(1, "PageDown", 20)).toBe(6);
    expect(moveIndex(18, "PageDown", 20)).toBe(19);
    expect(moveIndex(3, "PageUp", 20)).toBe(0);
    expect(moveIndex(0, "ArrowDown", 0)).toBe(-1);
    expect(isNavKey("ArrowDown")).toBe(true);
    expect(isNavKey("Enter")).toBe(false);
  });
});

describe("display helpers", () => {
  it("splits a label into plain and matched runs", () => {
    expect(segments("Growth", [0, 1, 2])).toEqual([{ text: "Gro", hit: true }, { text: "wth", hit: false }]);
    expect(segments("Git habits", [4, 5])).toEqual([{ text: "Git ", hit: false }, { text: "ha", hit: true }, { text: "bits", hit: false }]);
    expect(segments("Growth", [])).toEqual([{ text: "Growth", hit: false }]);
  });
  it("says how many results", () => {
    expect(resultsText(0)).toBe("No results");
    expect(resultsText(1)).toBe("1 result");
    expect(resultsText(9)).toBe("9 results");
  });
});

describe("the verbs (docs/KNACK_UX.md section 9)", () => {
  const ids = (v: "worker" | "admin", caps = NO_CAPS) => buildItems(v, {}, caps).map((i) => i.id);
  it("lists the verbs the dashboard can do by itself, in both views", () => {
    for (const v of ["worker", "admin"] as const) for (const id of ["action:settings", "action:stop", "action:about", "action:delete", "action:tour"]) expect(ids(v), `${v} ${id}`).toContain(id);
  });
  it("lists the Monday note for a worker only", () => {
    expect(ids("worker")).toContain("action:monday");
    expect(ids("admin")).not.toContain("action:monday");
  });
  it("offers a desktop-only command only when the desktop app can do it, so no row is dead", () => {
    expect(ids("worker")).not.toEqual(expect.arrayContaining(["action:pause"]));
    expect(ids("worker")).not.toContain("action:ask");
    expect(ids("worker")).not.toContain("action:accessibility");
    const on = ids("worker", { ask: true, pause: true, accessibility: true });
    expect(on).toEqual(expect.arrayContaining(["action:pause", "action:ask", "action:accessibility"]));
  });
  it("groups them Go to, Do and Ask", () => {
    const items = buildItems("worker", {}, { ask: true, pause: true, accessibility: true });
    const group = (id: string) => items.find((i) => i.id === id)?.group;
    expect(group("action:settings")).toBe("Go to");
    expect(group("action:stop")).toBe("Do");
    expect(group("action:pause")).toBe("Do");
    expect(group("action:ask")).toBe("Ask");
  });
  it("gives Delete my data no shortcut by design: it opens Your data and nothing is deleted from the palette", () => {
    const d = buildItems("worker").find((i) => i.id === "action:delete")!;
    expect(d.target).toEqual({ type: "route", path: "/your-data" });
  });
  it("finds a verb by the words people use", () => {
    const items = buildItems("worker");
    expect(searchItems(items, "stop")[0].item.id).toBe("action:stop");
    expect(searchItems(items, "monday").map((s) => s.item.id)).toContain("action:monday");
    expect(searchItems(items, "forget").map((s) => s.item.id)).toContain("action:delete");
    expect(searchItems(items, "explain").map((s) => s.item.id)).toContain("action:about");
  });
  it("makes the last row 'Ask Knack: <phrase>' with the phrase carried to the Ask bar", () => {
    const a = askItem("  why was Tuesday slow ");
    expect(a.label).toBe("Ask Knack: why was Tuesday slow");
    expect(a.target).toEqual({ type: "action", action: "ask", phrase: "why was Tuesday slow" });
    expect(a.group).toBe("Ask");
  });
});
