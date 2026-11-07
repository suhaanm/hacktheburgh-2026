import { beforeEach, describe, expect, it } from "vitest";
import { SCREENS } from "../../router";
import { ADMIN_ONLY, DEFAULT_SCREEN, DETAIL_SCREENS, FIRM_TABS, NAV_ENTRIES, REVIEWER_SCREENS, canView, entriesFor, firmTabOf, groupOf, inGroup, labelOf } from "./navModel";
import { ADMIN_MARKER, getViewRole, resetViewRole, setViewRole, VIEW_LABEL } from "./viewAs";

describe("the menu data", () => {
  it("lists every screen in the app exactly once, so nothing is hidden from the menu", () => {
    const ids = NAV_ENTRIES.map((e) => e.id).sort();
    expect(ids).toEqual([...SCREENS].sort());
    expect(new Set(ids).size).toBe(ids.length);
  });
  it("keeps the labels that scripts and people rely on", () => {
    const text = NAV_ENTRIES.map((e) => e.label).join("|");
    for (const label of ["Week", "Privacy", "Agents", "Briefing", "Git habits", "Models", "Notices", "Set up", "Repeats", "Your week", "Firm", "Predictions"]) expect(text).toContain(label);
    expect(labelOf("evidence")).toBe("Evidence");
    expect(NAV_ENTRIES.find((e) => e.id === "evidence")?.hint).toBe("For reviewers");
  });
  it("opens on the worker home by default", () => {
    expect(DEFAULT_SCREEN).toBe("home");
  });
  it("puts the detailed-statistics screens under Details and nothing else", () => {
    expect(DETAIL_SCREENS.sort()).toEqual(["genome", "git", "graph", "predictions", "presence", "week"]);
    expect(REVIEWER_SCREENS).toEqual(["evidence"]);
    expect(inGroup("genome", "details")).toBe(true);
    expect(inGroup("growth", "details")).toBe(false);
  });
  it("shows Growth, Repeats and Privacy up front, not folded away", () => {
    const main = groupOf("worker", "main").map((e) => e.id);
    expect(main).toEqual(expect.arrayContaining(["home", "repeats", "growth", "privacy", "routines", "queue"]));
  });
});

describe("the Admin view", () => {
  it("is the only place the Firm screen exists: menu, gate and palette data", () => {
    expect(ADMIN_ONLY).toEqual(["firm"]);
    expect(entriesFor("worker").map((e) => e.id)).not.toContain("firm");
    expect(entriesFor("admin").map((e) => e.id)).toContain("firm");
    expect(canView("firm", "worker")).toBe(false);
    expect(canView("firm", "admin")).toBe(true);
    expect(canView("home", "worker")).toBe(true);
    expect(canView("unknown", "worker")).toBe(true);
  });
  it("has one view per idea on the Firm screen and a route for each", () => {
    expect(FIRM_TABS.map((t) => t.id)).toEqual(["overview", "roles", "people", "onboarding", "automation", "risk", "forecasts", "brief"]);
    expect(firmTabOf("/firm")).toBe("overview");
    expect(firmTabOf("/firm/roles")).toBe("roles");
    expect(firmTabOf("/firm/people")).toBe("people");
    expect(firmTabOf("/firm/nonsense")).toBe("overview");
    for (const t of FIRM_TABS) expect(t.path.startsWith("/firm")).toBe(true);
  });
});

describe("the demo view role", () => {
  beforeEach(() => resetViewRole());
  it("starts as Worker and holds only in memory", () => {
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
  it("names the Admin view plainly", () => {
    expect(ADMIN_MARKER).toBe("Admin view");
    expect(VIEW_LABEL).toEqual({ worker: "Worker", admin: "Admin" });
  });
});
