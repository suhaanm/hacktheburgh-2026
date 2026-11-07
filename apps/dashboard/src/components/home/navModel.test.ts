import { beforeEach, describe, expect, it } from "vitest";
import { SCREENS } from "../../router";
import { OLD_ROUTES, SETUP_PATH, hashOf, redirectFor } from "../../routeRedirects";
import {
  ADMIN_ONLY, DEFAULT_SCREEN, DETAIL_SCREENS, FIRM_TABS, MORE_MAX, NAV_ENTRIES, PINNED_VIEWS, REVIEWER_SCREENS,
  canView, clicksFromHome, entriesFor, firmTabOf, groupOf, labelOf, moreFor, sidebarFor,
} from "./navModel";
import { ADMIN_MARKER, VIEW_STORAGE_KEY, getViewRole, resetViewRole, setViewRole, VIEW_LABEL } from "./viewAs";

describe("the menu data", () => {
  it("lists every screen in the app exactly once, so nothing is hidden from the menu", () => {
    const ids = NAV_ENTRIES.map((e) => e.id).sort();
    expect(ids).toEqual([...SCREENS].sort());
    expect(new Set(ids).size).toBe(ids.length);
  });
  it("has exactly 5 worker and 3 admin primary entries, in the order the spec gives", () => {
    expect(groupOf("worker", "primary").map((e) => e.label)).toEqual(["Home", "Needs you", "Routines", "Growth", "Your data"]);
    expect(groupOf("worker", "primary").map((e) => e.id)).toEqual(["home", "needs-you", "routines", "growth", "your-data"]);
    expect(groupOf("worker", "admin")).toEqual([]);
    expect(groupOf("admin", "admin").map((e) => e.label)).toEqual(["Firm", "Roles", "Onboarding"]);
    expect(groupOf("admin", "primary")).toHaveLength(5);
  });
  it("keeps the sidebar to 6 rows for a worker and 9 for an admin, with no hint words on a row", () => {
    expect(sidebarFor("worker").rows).toBe(6);
    expect(sidebarFor("admin").rows).toBe(9);
    // Pinned views add a group of three and nothing else: 9 rows for a worker, 12 for an admin.
    expect(sidebarFor("worker", true).rows).toBe(9);
    expect(sidebarFor("worker", true).pinned.map((e) => e.id)).toEqual(PINNED_VIEWS);
    for (const e of [...sidebarFor("admin").primary, ...sidebarFor("admin").admin]) expect(e.label.split(/\s+/).length, e.id).toBeLessThanOrEqual(2);
  });
  it("opens on Home by default, and Pinned views are the three signature screens", () => {
    expect(DEFAULT_SCREEN).toBe("home");
    expect(PINNED_VIEWS).toEqual(["genome", "graph", "presence"]);
  });
  it("keeps More to at most ten one-line rows in both views, without repeating a row", () => {
    for (const view of ["worker", "admin"] as const) for (const pinned of [false, true]) {
      const rows = moreFor(view, pinned);
      expect(rows.length, `${view} pinned=${pinned}`).toBeLessThanOrEqual(MORE_MAX);
      expect(new Set(rows.map((r) => r.path)).size).toBe(rows.length);
      for (const r of rows) expect(r.label.split(/\s+/).length, r.label).toBeLessThanOrEqual(4);
    }
    expect(moreFor("worker")).toHaveLength(10);
    expect(moreFor("worker").map((r) => r.label)).toEqual(["Where time goes", "Your hours", "How work connects", "Calendar", "Git habits", "Forecasts", "Background runs", "Models and cost", "Live coach", "Evidence"]);
    expect(moreFor("worker", true).map((r) => r.id)).not.toEqual(expect.arrayContaining(["genome"]));
    expect(moreFor("admin").map((r) => r.label)).toEqual(expect.arrayContaining(["People", "Automation", "Risk and coverage", "Forecasts", "Firm brief", "Evidence"]));
  });
  it("puts Evidence under For reviewers and the detail screens under More, none of them in the sidebar", () => {
    expect(REVIEWER_SCREENS).toEqual(["evidence"]);
    expect([...DETAIL_SCREENS].sort()).toEqual(["agents", "forecasts", "genome", "git", "graph", "models", "presence", "today", "week"]);
    expect(labelOf("evidence")).toBe("Evidence");
    expect(NAV_ENTRIES.find((e) => e.id === "evidence")?.hint).toBe("For reviewers");
  });
  it("names no screen with the jargon the copy rules ban", () => {
    for (const e of entriesFor("admin")) expect(e.label, e.id).not.toMatch(/genome|ledger|rung|occurrence|shadow|demo/i);
  });
  it("still finds a screen by its old name in the palette", () => {
    const also = (id: string) => NAV_ENTRIES.find((e) => e.id === id)?.also ?? "";
    expect(also("needs-you")).toMatch(/queue/);
    expect(also("needs-you")).toMatch(/briefing/);
    expect(also("routines")).toMatch(/repeats/);
    expect(also("your-data")).toMatch(/memory/);
    expect(also("your-data")).toMatch(/privacy/);
    expect(also("genome")).toMatch(/genome/);
    expect(also("forecasts")).toMatch(/predictions/);
  });
});

describe("clicks over the nav graph", () => {
  it("is 0 for Home, 1 for a sidebar row and 2 through More, so nothing is deeper than 2 from Home", () => {
    expect(clicksFromHome("home", "worker")).toBe(0);
    for (const id of ["needs-you", "routines", "growth", "your-data"] as const) expect(clicksFromHome(id, "worker"), id).toBe(1);
    for (const id of ["genome", "presence", "graph", "week", "git", "forecasts", "agents", "models", "today", "evidence"] as const) expect(clicksFromHome(id, "worker"), id).toBe(2);
    expect(clicksFromHome("genome", "worker", true)).toBe(1);
    for (const id of ["firm", "roles", "onboarding"] as const) expect(clicksFromHome(id, "admin"), id).toBe(1);
  });
});

describe("the Admin view", () => {
  it("is the only place the three Admin screens exist: menu, gate and palette data", () => {
    expect(ADMIN_ONLY).toEqual(["firm", "roles", "onboarding"]);
    for (const id of ADMIN_ONLY) {
      expect(entriesFor("worker").map((e) => e.id)).not.toContain(id);
      expect(entriesFor("admin").map((e) => e.id)).toContain(id);
      expect(canView(id, "worker")).toBe(false);
      expect(canView(id, "admin")).toBe(true);
    }
    expect(canView("home", "worker")).toBe(true);
    expect(canView("unknown", "worker")).toBe(true);
  });
  it("has one view per idea on the Firm screen and an address for each", () => {
    expect(FIRM_TABS.map((t) => t.id)).toEqual(["overview", "roles", "people", "onboarding", "automation", "risk", "forecasts", "brief"]);
    expect(firmTabOf("/firm")).toBe("overview");
    expect(firmTabOf("/roles")).toBe("roles");
    expect(firmTabOf("/onboarding")).toBe("onboarding");
    expect(firmTabOf("/firm/people")).toBe("people");
    expect(firmTabOf("/firm/automation")).toBe("automation");
    expect(firmTabOf("/firm/nonsense")).toBe("overview");
    for (const t of FIRM_TABS) expect(["/firm", "/roles", "/onboarding"].some((p) => t.path === p || t.path.startsWith("/firm/"))).toBe(true);
  });
});

describe("old routes", () => {
  const q = () => new URLSearchParams();
  it("sends every old route somewhere that exists, so no deep link breaks", () => {
    for (const old of OLD_ROUTES) {
      const t = redirectFor(`/${old}`, q(), "worker");
      const landing = t ? t.path.split("/")[1] : old;
      expect((SCREENS as readonly string[]).includes(landing), `${old} lands on ${landing}`).toBe(true);
    }
    // Every old screen that is no longer a screen redirects (it does not just fall through to Home).
    for (const gone of ["queue", "briefing", "repeats", "privacy", "memory", "notices", "predictions"]) expect(redirectFor(`/${gone}`, q()), gone).not.toBeNull();
    // The old Firm views that became destinations.
    expect(redirectFor("/firm/roles", q())?.path).toBe("/roles");
    expect(redirectFor("/firm/onboarding", q())?.path).toBe("/onboarding");
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
  it("keeps the old query on top of the new one", () => {
    const t = redirectFor("/predictions", new URLSearchParams("person=p_f_bp05"))!;
    expect(hashOf(t)).toBe("/forecasts?person=p_f_bp05");
    expect(hashOf(redirectFor("/privacy", new URLSearchParams("section=hours"))!)).toBe("/your-data?section=hours");
  });
  it("sends the firm Repeats (as=admin) to the Firm automation view", () => {
    expect(hashOf(redirectFor("/repeats", new URLSearchParams("as=admin"))!)).toBe("/firm/automation");
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
    expect(redirectFor("/firm/people", q())).toBeNull();
    expect(redirectFor("/firm/risk", q())).toBeNull();
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
