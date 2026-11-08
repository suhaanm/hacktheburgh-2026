// The shell's small pure pieces: the breadcrumb, the desktop bridge capabilities, and the sidebar and bottom-bar contract that the jobs rely on.
import { describe, expect, it } from "vitest";
import { breadcrumb } from "../home/ScreenFrame";
import { NAV_ENTRIES, groupOf, moreFor, sidebarFor } from "../home/navModel";
import { capsOf, type KnackShellBridge } from "./bridge";

describe("the breadcrumb", () => {
  it("says where a screen under More sits, with the way back to Home", () => {
    expect(breadcrumb("genome")).toEqual([{ label: "Home", href: "#/home" }, { label: "Where time goes" }]);
    expect(breadcrumb("evidence")).toEqual([{ label: "Home", href: "#/home" }, { label: "Evidence" }]);
  });
  it("is absent on the five destinations, the Admin screens and the bare screens", () => {
    for (const id of ["home", "needs-you", "routines", "growth", "your-data", "firm", "roles", "onboarding", "first-run", "setup"] as const) expect(breadcrumb(id), id).toBeNull();
    expect(breadcrumb("unknown")).toBeNull();
  });
  it("covers every screen of the More sheet", () => {
    for (const r of moreFor("worker")) expect(breadcrumb(r.id as never), r.id).not.toBeNull();
  });
});

describe("the desktop bridge", () => {
  it("offers a desktop-only command only when the app exposes it", () => {
    expect(capsOf({})).toEqual({ ask: false, pause: false, accessibility: false });
    const b: KnackShellBridge = { ask: () => undefined, pause: () => undefined };
    expect(capsOf(b)).toEqual({ ask: true, pause: true, accessibility: false });
    expect(capsOf({ openSystemSettings: () => undefined }).accessibility).toBe(true);
  });
});

describe("the sidebar contract", () => {
  it("draws 6 rows for a worker and 9 for an admin, with no hint words and at most 16 words in all rows", () => {
    const worker = sidebarFor("worker");
    const admin = sidebarFor("admin");
    expect(worker.rows).toBe(6);
    expect(admin.rows).toBe(9);
    const words = (v: "worker" | "admin") => [...sidebarFor(v).primary, ...sidebarFor(v).admin].map((e) => e.label).join(" ").split(/\s+/).length;
    expect(words("worker")).toBeLessThanOrEqual(8);
    expect(words("admin")).toBeLessThanOrEqual(11);
  });
  it("has an icon for every sidebar row and none of them is a More screen", () => {
    for (const v of ["worker", "admin"] as const) for (const e of [...sidebarFor(v).primary, ...sidebarFor(v).admin]) expect(e.icon, e.id).toBeTruthy();
    const more = new Set(moreFor("worker").map((r) => r.id));
    for (const e of groupOf("worker", "primary")) expect(more.has(e.id)).toBe(false);
  });
  it("keeps the bottom bar to the five worker destinations", () => {
    expect(groupOf("worker", "primary")).toHaveLength(5);
    expect(NAV_ENTRIES.filter((e) => e.group === "primary")).toHaveLength(5);
  });
});
