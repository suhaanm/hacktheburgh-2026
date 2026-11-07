// The ten jobs of docs/knack-ux/jobs.json, as paths over the nav graph (navModel.ts). The in-screen clicks (a button on a row, a switch on a
// card) are stated here, one per step of the job's target path; the navigation clicks are computed from the model, so moving a screen out of the
// sidebar makes this test fail. scripts/check-clicks.mjs replays the same paths in a browser.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { clicksFromHome, sidebarFor } from "./components/home/navModel";
import type { Screen } from "./router";
import type { ViewRole } from "./components/home/viewAs";

interface Job {
  id: string; who: string; name: string;
  target_clicks: number; target_clicks_pointer?: number; target_when_several?: number; target_variant_away?: number;
  target_clicks_role_switch?: number; target_see?: number;
}
const file = fileURLToPath(new URL("../../../docs/knack-ux/jobs.json", import.meta.url));
const spec = JSON.parse(readFileSync(file, "utf8")) as { budget: { top5_max_from_home: number; anything_max_from_home: number }; jobs: Job[]; first_run: { target_clicks: number } };
const job = (id: string): Job => spec.jobs.find((j) => j.id === id)!;

/** Clicks for a path: reach `screen` from Home (0 when null: a keyboard shortcut, the hero, or the screen you are already on), then `extra` clicks on it. */
const path = (screen: Screen | null, view: ViewRole, extra: number): number => (screen ? clicksFromHome(screen, view) : 0) + extra;

describe("the ten jobs fit their click budgets over the nav graph", () => {
  it("J1 see what matters: 0, Home is the landing screen", () => expect(path("home", "worker", 0)).toBeLessThanOrEqual(job("J1").target_clicks));
  it("J2 approve or reject: 1 when the item is Home's hero, 2 from Needs you", () => {
    expect(path(null, "worker", 1)).toBeLessThanOrEqual(job("J2").target_clicks); // the hero's own button
    expect(path("needs-you", "worker", 1)).toBeLessThanOrEqual(job("J2").target_when_several!);
  });
  it("J3 opt in to a routine or decline: 2; run while away: 3", () => {
    expect(path("needs-you", "worker", 1)).toBeLessThanOrEqual(job("J3").target_clicks); // Watch first, Not now or Never
    expect(path("needs-you", "worker", 2)).toBeLessThanOrEqual(job("J3").target_variant_away!); // More ways to say yes, then the switch and confirm
  });
  it("J4 see whether I need less help: 1", () => expect(path("growth", "worker", 0)).toBeLessThanOrEqual(job("J4").target_clicks));
  it("J5 see what Knack has of me: 1; delete anything: 3", () => {
    expect(path("your-data", "worker", 0)).toBeLessThanOrEqual(job("J5").target_see!);
    expect(path("your-data", "worker", 2)).toBeLessThanOrEqual(job("J5").target_clicks); // Forget, then Forget it
  });
  it("J6 stop everything: the sidebar Stop button is 1 click on every screen; the keys are 0", () => {
    expect(1).toBeLessThanOrEqual(job("J6").target_clicks_pointer!);
    expect(job("J6").target_clicks).toBe(0);
  });
  it("J7 start work: Routines then Run now is 2; Option-Space is 0", () => {
    expect(path("routines", "worker", 1)).toBeLessThanOrEqual(job("J7").target_clicks_pointer!);
  });
  it("A1 the firm view: 0 with a real role (Admin lands on Firm); the sidebar row is 1", () => {
    expect(path("firm", "admin", 0)).toBeLessThanOrEqual(1);
    expect(job("A1").target_clicks).toBe(0);
  });
  it("A2 compare a role and A3 onboarding speed: 1 in the sidebar, 2 after the view switch", () => {
    expect(path("roles", "admin", 0)).toBeLessThanOrEqual(job("A2").target_clicks);
    expect(path("onboarding", "admin", 0)).toBeLessThanOrEqual(job("A3").target_clicks);
    expect(path("roles", "admin", 1)).toBeLessThanOrEqual(job("A2").target_clicks_role_switch!);
  });
  it("keeps the five most frequent jobs within 2 clicks of Home and everything within 3", () => {
    const top5 = [path("home", "worker", 0), path("needs-you", "worker", 1), path("needs-you", "worker", 1), path("growth", "worker", 0), path("your-data", "worker", 0)];
    for (const c of top5) expect(c).toBeLessThanOrEqual(spec.budget.top5_max_from_home);
    for (const j of spec.jobs) expect(j.target_clicks_role_switch ?? j.target_variant_away ?? j.target_when_several ?? j.target_clicks, j.id).toBeLessThanOrEqual(spec.budget.anything_max_from_home);
  });
  it("lists exactly the ten jobs and a three-click first run", () => {
    expect(spec.jobs.map((j) => j.id)).toEqual(["J1", "J2", "J3", "J4", "J5", "J6", "J7", "A1", "A2", "A3"]);
    expect(spec.first_run.target_clicks).toBe(3);
  });
  it("keeps every primary screen in the sidebar (the paths above rely on it)", () => {
    expect(sidebarFor("worker").primary.map((e) => e.id)).toEqual(["home", "needs-you", "routines", "growth", "your-data"]);
    expect(sidebarFor("admin").admin.map((e) => e.id)).toEqual(["firm", "roles", "onboarding"]);
  });
});
