// The shell's small pure pieces: the breadcrumb, the desktop bridge capabilities, and the sidebar and bottom-bar contract that the jobs rely on.
import { describe, expect, it } from "vitest";
import { breadcrumb } from "../home/ScreenFrame";
import { NAV_ENTRIES, groupOf, moreFor, sidebarFor } from "../home/navModel";
import { capsOf, permState, permStates, permissionsAvailable, type KnackShellBridge } from "./bridge";

describe("the breadcrumb", () => {
  it("says where a screen behind the Admin More sits, with the way back to Firm", () => {
    expect(breadcrumb("evidence")).toEqual([{ label: "Firm", href: "#/firm" }, { label: "Evidence" }]);
    expect(breadcrumb("models")).toEqual([{ label: "Firm", href: "#/firm" }, { label: "Models and cost" }]);
    expect(breadcrumb("agents")).toEqual([{ label: "Firm", href: "#/firm" }, { label: "Background runs" }]);
  });
  it("is absent on the five destinations, the eight Admin destinations and the bare screens", () => {
    for (const id of ["home", "needs-you", "routines", "growth", "your-data", "firm", "brief", "forecasts", "roles", "people", "onboarding", "automation", "risk", "first-run", "setup"] as const) expect(breadcrumb(id), id).toBeNull();
    expect(breadcrumb("unknown")).toBeNull();
  });
  it("covers every screen of the More sheet", () => {
    for (const r of moreFor("admin")) expect(breadcrumb(r.id as never), r.id).not.toBeNull();
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

describe("macOS permissions as the first run reads them", () => {
  it("reads any reasonable answer as allowed, turned off, or not asked yet; an unknown answer is never read as allowed", () => {
    for (const v of ["granted", "authorized", "Authorised", "allowed", true]) expect(permState(v), String(v)).toBe("granted");
    for (const v of ["denied", "restricted", "off", "turned-off", "Turned off", false]) expect(permState(v), String(v)).toBe("off");
    for (const v of ["not-determined", "not_determined", "undetermined", "", "granted?", null, undefined, 7, {}]) expect(permState(v), String(v)).toBe("not-asked");
  });
  it("reads the three permissions by their usual names, and a missing answer or key as not asked yet", () => {
    expect(permStates({ microphone: "granted", speech: "denied", screen: "not-determined" })).toEqual({ microphone: "granted", speech: "off", screen: "not-asked" });
    expect(permStates({ mic: true, speechRecognition: false, screenRecording: "authorized" })).toEqual({ microphone: "granted", speech: "off", screen: "granted" });
    expect(permStates(null)).toEqual({ microphone: "not-asked", speech: "not-asked", screen: "not-asked" });
    expect(permStates({})).toEqual({ microphone: "not-asked", speech: "not-asked", screen: "not-asked" });
  });
  it("the permissions are offered only when the shell exposes them", () => {
    expect(permissionsAvailable({})).toBe(false);
    expect(permissionsAvailable({ permissions: { state: async () => ({}), request: async () => "granted", openSettings: () => undefined } })).toBe(true);
  });
});

describe("the sidebar contract", () => {
  it("draws 5 rows for a worker and 9 for an admin (eight and More), with no hint words and a small word count", () => {
    const worker = sidebarFor("worker");
    const admin = sidebarFor("admin");
    expect(worker.rows).toBe(5);
    expect(admin.rows).toBe(9);
    const words = (v: "worker" | "admin") => sidebarFor(v).main.map((e) => e.label).join(" ").split(/\s+/).length;
    expect(words("worker")).toBeLessThanOrEqual(8);
    expect(words("admin")).toBeLessThanOrEqual(10);
  });
  it("has an icon for every sidebar row and none of them is a More screen", () => {
    for (const v of ["worker", "admin"] as const) for (const e of sidebarFor(v).main) expect(e.icon, e.id).toBeTruthy();
    const more = new Set(moreFor("admin").map((r) => r.id));
    for (const e of groupOf("admin", "admin")) expect(more.has(e.id)).toBe(false);
  });
  it("keeps the bottom bar to the five worker destinations", () => {
    expect(groupOf("worker", "primary")).toHaveLength(5);
    expect(NAV_ENTRIES.filter((e) => e.group === "primary")).toHaveLength(5);
  });
});
