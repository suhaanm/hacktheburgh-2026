import { beforeEach, describe, expect, it } from "vitest";
import { SCREENS } from "../../router";
import { OLD_ROUTES, SETUP_PATH, hashOf, redirectFor } from "../../routeRedirects";
import {
  ADMIN_GATE, ADMIN_ONLY, BAR_MAX, UNDER_HOME, DEFAULT_SCREEN, FIRM_TABS, GROWTH_SECTIONS, MORE_MAX, MORE_SCREENS, NAV_ENTRIES,
  canView, clicksFromHome, compactFor, entriesFor, firmTabOf, growthPath, growthSectionOf, labelOf, landingFor, moreFor, sidebarFor,
} from "./navModel";
import { ADMIN_MARKER, VIEW_STORAGE_KEY, getViewRole, resetViewRole, setViewRole, VIEW_LABEL } from "./viewAs";

const WORKER_FIVE = ["home", "needs-you", "routines", "growth", "your-data"] as const;
const ADMIN_EIGHT = ["firm", "brief", "forecasts", "roles", "people", "onboarding", "automation", "risk"] as const;
const ADMIN_MORE = ["models", "evidence", "agents"] as const;

describe("the menu data", () => {
  it("lists every screen in the app exactly once, so nothing is hidden from the menu", () => {
    const ids = NAV_ENTRIES.map((e) => e.id).sort();
    expect(ids).toEqual([...SCREENS].sort());
    expect(new Set(ids).size).toBe(ids.length);
  });
  it("gives a worker exactly five rows, in the order the views rule gives, and nothing else", () => {
    expect(sidebarFor("worker").main.map((e) => e.label)).toEqual(["Home", "Needs you", "Routines", "Growth", "Your data"]);
    expect(sidebarFor("worker").main.map((e) => e.id)).toEqual([...WORKER_FIVE]);
    expect(sidebarFor("worker").more).toEqual([]);
    expect(sidebarFor("worker").rows).toBe(5);
    expect(moreFor("worker")).toEqual([]);
    expect(entriesFor("worker").map((e) => e.id)).toEqual([...WORKER_FIVE]);
  });
  it("gives an admin eight rows and a More of three, with no worker row among them", () => {
    expect(sidebarFor("admin").main.map((e) => e.label)).toEqual(["Firm", "Brief", "Forecasts", "Roles", "People", "Onboarding", "Automation", "Risk"]);
    expect(sidebarFor("admin").main.map((e) => e.id)).toEqual([...ADMIN_EIGHT]);
    expect(sidebarFor("admin").more.map((e) => e.label)).toEqual(["Models and cost", "Evidence", "Background runs"]);
    expect(sidebarFor("admin").more.map((e) => e.id)).toEqual([...ADMIN_MORE]);
    expect(sidebarFor("admin").rows).toBe(9);
    for (const id of WORKER_FIVE) expect(entriesFor("admin").map((e) => e.id), id).not.toContain(id);
  });
  it("keeps every row label to two words or fewer in the sidebar, with no hint beside it", () => {
    for (const e of sidebarFor("admin").main) expect(e.label.split(/\s+/).length, e.id).toBeLessThanOrEqual(2);
    for (const e of sidebarFor("worker").main) expect(e.label.split(/\s+/).length, e.id).toBeLessThanOrEqual(2);
  });
  it("opens a worker on Home and an admin on Firm", () => {
    expect(DEFAULT_SCREEN).toBe("home");
    expect(landingFor("worker")).toBe("home");
    expect(landingFor("admin")).toBe("firm");
  });
  it("keeps More to at most ten one-line rows in both views, without repeating a row", () => {
    for (const view of ["worker", "admin"] as const) {
      const rows = moreFor(view);
      expect(rows.length, view).toBeLessThanOrEqual(MORE_MAX);
      expect(new Set(rows.map((r) => r.path)).size).toBe(rows.length);
      for (const r of rows) expect(r.label.split(/\s+/).length, r.label).toBeLessThanOrEqual(4);
    }
    expect(moreFor("admin").map((r) => r.path)).toEqual(["/models", "/evidence", "/agents"]);
  });
  it("puts Models and cost, Evidence and Background runs behind the Admin More, each with a way back", () => {
    expect([...MORE_SCREENS]).toEqual([...ADMIN_MORE]);
    expect(labelOf("evidence")).toBe("Evidence");
    expect(NAV_ENTRIES.find((e) => e.id === "evidence")?.hint).toBe("For reviewers");
  });
  it("fits the bottom bar at 390 px: five items, and an admin's other three lead the More sheet", () => {
    expect(BAR_MAX).toBe(5);
    expect(compactFor("worker").bar.map((e) => e.id)).toEqual([...WORKER_FIVE]);
    expect(compactFor("worker").overflow).toEqual([]);
    expect(compactFor("admin").bar.map((e) => e.id)).toEqual(["firm", "brief", "forecasts", "roles", "people"]);
    expect(compactFor("admin").overflow.map((r) => r.id)).toEqual(["onboarding", "automation", "risk"]);
    // Every admin destination is reachable at 390 px: in the bar, in the overflow, or in More.
    const all = new Set([...compactFor("admin").bar.map((e) => e.id), ...compactFor("admin").overflow.map((r) => r.id), ...moreFor("admin").map((r) => r.id)]);
    for (const id of [...ADMIN_EIGHT, ...ADMIN_MORE]) expect(all.has(id), id).toBe(true);
  });
  it("names no screen with the jargon the copy rules ban", () => {
    for (const view of ["worker", "admin"] as const) for (const e of entriesFor(view)) expect(e.label, e.id).not.toMatch(/genome|ledger|rung|occurrence|shadow|demo/i);
  });
  it("still finds a screen by its old name in the palette", () => {
    const also = (id: string) => NAV_ENTRIES.find((e) => e.id === id)?.also ?? "";
    expect(also("needs-you")).toMatch(/queue/);
    expect(also("needs-you")).toMatch(/briefing/);
    expect(also("routines")).toMatch(/repeats/);
    expect(also("routines")).toMatch(/background/);
    expect(also("your-data")).toMatch(/memory/);
    expect(also("your-data")).toMatch(/privacy/);
    expect(also("forecasts")).toMatch(/predictions/);
    expect(also("brief")).toMatch(/firm brief/);
  });
});

describe("clicks over the nav graph", () => {
  it("is 0 for the landing screen, 1 for a sidebar row and 2 through More, so nothing is deeper than 2", () => {
    expect(clicksFromHome("home", "worker")).toBe(0);
    for (const id of WORKER_FIVE.slice(1)) expect(clicksFromHome(id, "worker"), id).toBe(1);
    expect(clicksFromHome("firm", "admin")).toBe(0);
    for (const id of ADMIN_EIGHT.slice(1)) expect(clicksFromHome(id, "admin"), id).toBe(1);
    for (const id of ADMIN_MORE) expect(clicksFromHome(id, "admin"), id).toBe(2);
    // A worker cannot reach an Admin screen at all: the count says so rather than hiding it.
    for (const id of [...ADMIN_EIGHT, ...ADMIN_MORE]) expect(clicksFromHome(id, "worker"), id).toBe(Infinity);
  });
});

describe("the Admin view", () => {
  it("is the only place the Admin screens exist: menu, gate and palette data", () => {
    expect([...ADMIN_ONLY].sort()).toEqual([...ADMIN_EIGHT, ...ADMIN_MORE].sort());
    for (const id of ADMIN_ONLY) {
      expect(entriesFor("worker").map((e) => e.id)).not.toContain(id);
      expect(entriesFor("admin").map((e) => e.id)).toContain(id);
      expect(canView(id, "worker")).toBe(false);
      expect(canView(id, "admin")).toBe(true);
    }
    expect(canView("home", "worker")).toBe(true);
    expect(canView("growth", "worker")).toBe(true);
    expect(canView("unknown", "worker")).toBe(true);
  });
  it("says one sentence to a worker who types an Admin address", () => {
    expect(ADMIN_GATE).toBe("Switch to Admin to see this");
    expect(ADMIN_GATE.split(/\s+/).length).toBeLessThanOrEqual(8);
  });
  it("has one view per idea on the Firm screen and a top-level address for each", () => {
    expect(FIRM_TABS.map((t) => t.id).sort()).toEqual(["automation", "brief", "forecasts", "onboarding", "overview", "people", "risk", "roles"]);
    expect(firmTabOf("/firm")).toBe("overview");
    for (const id of ADMIN_EIGHT.slice(1)) expect(firmTabOf(`/${id}`), id).toBe(id);
    // The old /firm/<view> form reads the same, though the router rewrites it first.
    expect(firmTabOf("/firm/people")).toBe("people");
    expect(firmTabOf("/firm/automation")).toBe("automation");
    expect(firmTabOf("/firm/nonsense")).toBe("overview");
    for (const t of FIRM_TABS) expect(t.path).toBe(t.id === "overview" ? "/firm" : `/${t.id}`);
  });
});

describe("the live coach page", () => {
  it("is a screen with no row in the sidebar, the More sheet or the palette, and a way back to Home", () => {
    expect((SCREENS as readonly string[]).includes("today")).toBe(true);
    for (const view of ["worker", "admin"] as const) {
      expect(entriesFor(view).map((e) => e.id), view).not.toContain("today");
      expect(sidebarFor(view).main.map((e) => e.id), view).not.toContain("today");
      expect(moreFor(view).map((r) => r.id), view).not.toContain("today");
    }
    expect(NAV_ENTRIES.find((e) => e.id === "today")?.group).toBe("hidden");
    expect(canView("today", "worker")).toBe(true);
    expect(UNDER_HOME).toEqual(["today"]);
    expect(labelOf("today")).toBe("Coaching");
  });
});

describe("Growth sections", () => {
  it("has five, in the order the views rule gives, each with an address and a safe default", () => {
    expect([...GROWTH_SECTIONS]).toEqual(["progress", "time", "steps", "map", "commits"]);
    expect(growthPath("progress")).toBe("/growth");
    expect(growthPath("steps")).toBe("/growth?section=steps");
    expect(growthSectionOf("map")).toBe("map");
    for (const bad of [null, undefined, "", "genome", "TIME", "../etc"]) expect(growthSectionOf(bad as never), String(bad)).toBe("progress");
  });
});

describe("old routes", () => {
  const q = () => new URLSearchParams();
  it("sends every old route somewhere that exists, in both views, so no deep link breaks", () => {
    for (const view of ["worker", "admin"] as const) for (const old of OLD_ROUTES) {
      const t = redirectFor(`/${old}`, q(), view);
      const landing = t ? t.path.split("/")[1] : old;
      expect((SCREENS as readonly string[]).includes(landing), `${view}: ${old} lands on ${landing}`).toBe(true);
    }
    // Every old screen that is no longer a screen redirects (it does not just fall through to Home).
    for (const gone of ["queue", "briefing", "repeats", "privacy", "memory", "notices", "predictions", "week", "presence", "genome", "graph", "git"]) expect(redirectFor(`/${gone}`, q()), gone).not.toBeNull();
  });
  it("lands the common deep links where the owner's scripts expect", () => {
    expect(redirectFor("/queue", q())?.path).toBe("/needs-you");
    expect(redirectFor("/briefing", q())?.path).toBe("/needs-you");
    expect(hashOf(redirectFor("/repeats", q())!)).toBe("/routines?tab=could-automate");
    expect(hashOf(redirectFor("/privacy", q())!)).toBe("/your-data?section=sent");
    expect(hashOf(redirectFor("/memory", q())!)).toBe("/your-data?section=remembers");
    expect(hashOf(redirectFor("/notices", q())!)).toBe("/home?settings=interruptions");
    expect(redirectFor("/predictions", q())?.path).toBe("/forecasts");
  });
  it("folds the work views into the sections of Growth, and leaves the live coach where it is", () => {
    // Today is the one old screen that stays a screen: unlisted, no redirect, opened from Home while a coach step is active.
    expect(redirectFor("/today", q(), "worker")).toBeNull();
    expect(redirectFor("/today", q(), "admin")).toBeNull();
    expect(hashOf(redirectFor("/week", q())!)).toBe("/growth?section=time");
    expect(hashOf(redirectFor("/presence", q())!)).toBe("/growth?section=time");
    expect(hashOf(redirectFor("/genome", q())!)).toBe("/growth?section=steps");
    expect(hashOf(redirectFor("/graph", q())!)).toBe("/growth?section=map");
    expect(hashOf(redirectFor("/git", q())!)).toBe("/growth?section=commits");
    // Every section a redirect names is one Growth draws.
    for (const old of ["week", "presence", "genome", "graph", "git"]) {
      const s = redirectFor(`/${old}`, q())!.query.get("section");
      expect((GROWTH_SECTIONS as readonly string[]).includes(s ?? ""), old).toBe(true);
    }
  });
  it("sends the old Firm sub-addresses to their own top-level addresses", () => {
    for (const t of ["roles", "onboarding", "people", "automation", "risk", "forecasts", "brief"]) expect(redirectFor(`/firm/${t}`, q())?.path, t).toBe(`/${t}`);
    expect(redirectFor("/firm/nonsense", q())?.path).toBe("/firm");
    expect(redirectFor("/firm", q())).toBeNull();
  });
  it("sends Agents to Routines for a worker (its background tasks) and leaves it as Background runs for an admin", () => {
    expect(redirectFor("/agents", q(), "worker")?.path).toBe("/routines");
    expect(redirectFor("/agents", q(), "admin")).toBeNull();
  });
  it("keeps the old query on top of the new one", () => {
    const t = redirectFor("/predictions", new URLSearchParams("person=p_f_bp05"))!;
    expect(hashOf(t)).toBe("/forecasts?person=p_f_bp05");
    expect(hashOf(redirectFor("/privacy", new URLSearchParams("section=hours"))!)).toBe("/your-data?section=hours");
    expect(hashOf(redirectFor("/genome", new URLSearchParams("person=p_f_bp05"))!)).toBe("/growth?section=steps&person=p_f_bp05");
  });
  it("sends the firm Repeats (as=admin) to the Firm automation view", () => {
    expect(hashOf(redirectFor("/repeats", new URLSearchParams("as=admin"))!)).toBe("/automation");
  });
  it("reads /onboarding as the old set-up in the Worker view and as the Admin Onboarding screen in the Admin view", () => {
    expect(redirectFor("/onboarding", q(), "worker")?.path).toBe(SETUP_PATH);
    expect(redirectFor("/onboarding", q(), "admin")).toBeNull();
  });
  it("leaves every current route alone", () => {
    for (const id of SCREENS) {
      if (id === "onboarding") continue;
      expect(redirectFor(`/${id}`, q(), "admin"), id).toBeNull();
    }
    for (const id of SCREENS) {
      if (id === "onboarding" || id === "agents") continue;
      expect(redirectFor(`/${id}`, q(), "worker"), id).toBeNull();
    }
  });
  it("is a pure function: the same address gives the same answer twice, and it never changes the query it was given", () => {
    const query = new URLSearchParams("person=x");
    const a = hashOf(redirectFor("/genome", query)!);
    const b = hashOf(redirectFor("/genome", query)!);
    expect(a).toBe(b);
    expect(query.toString()).toBe("person=x");
  });
});

describe("the view role", () => {
  beforeEach(() => resetViewRole());
  it("starts as Worker", () => {
    expect(getViewRole()).toBe("worker");
    setViewRole("admin");
    expect(getViewRole()).toBe("admin");
    setViewRole("worker");
    expect(getViewRole()).toBe("worker");
  });
  it("ignores anything that is not a role", () => {
    setViewRole("root" as never);
    expect(getViewRole()).toBe("worker");
  });
  it("remembers Admin on this device, as the word admin and nothing else, and forgets it on Worker", () => {
    const store = new Map<string, string>();
    const ls = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) };
    (globalThis as unknown as { window: unknown }).window = { localStorage: ls };
    try {
      setViewRole("admin");
      expect(store.get(VIEW_STORAGE_KEY)).toBe("admin");
      setViewRole("worker");
      expect(store.has(VIEW_STORAGE_KEY)).toBe(false);
    } finally { delete (globalThis as unknown as { window?: unknown }).window; }
  });
  it("names the Admin view plainly", () => {
    expect(ADMIN_MARKER).toBe("Admin view");
    expect(VIEW_LABEL).toEqual({ worker: "Worker", admin: "Admin" });
  });
});
