import { describe, expect, it } from "vitest";
import { SCREENS } from "../../router";
import { ADMIN_ONLY, NAV_ENTRIES, canView } from "./navModel";
import { anchorSelector, clampStep, progressShare, progressText, ringBox, ringable, stepAfterViewChange, stepCount, tourSteps, wordCount } from "./tour";

describe("tour steps", () => {
  it("has six steps for a worker and eight for an admin, and stays within six to eight", () => {
    expect(stepCount("worker")).toBe(6);
    expect(stepCount("admin")).toBe(8);
    for (const v of ["worker", "admin"] as const) expect(stepCount(v)).toBeGreaterThanOrEqual(6), expect(stepCount(v)).toBeLessThanOrEqual(8);
  });
  it("is one short sentence per step, with no digits typed into the copy", () => {
    for (const s of tourSteps("admin")) {
      expect(wordCount(s.text), s.id).toBeLessThanOrEqual(20);
      expect(wordCount(s.text), s.id).toBeGreaterThanOrEqual(6);
      expect(s.text, s.id).not.toMatch(/\d/);
      expect(s.text.match(/[.!?]/g)?.length, `${s.id} is one sentence`).toBe(1);
      expect(s.text.endsWith("."), s.id).toBe(true);
      expect(s.text, s.id).not.toMatch(/!|\bjust\b|\bsimply\b|\bamazing\b/i);
      expect(s.title.length).toBeGreaterThan(0);
    }
  });
  it("keeps step ids unique and the stop button last", () => {
    for (const v of ["worker", "admin"] as const) {
      const steps = tourSteps(v);
      expect(new Set(steps.map((s) => s.id)).size).toBe(steps.length);
      expect(steps[steps.length - 1].id).toBe("stop");
    }
  });
  it("only visits routes that exist, or stays put for the stop button", () => {
    for (const s of tourSteps("admin")) {
      if (s.route === null) {
        expect(s.selector, s.id).toBe(".stop-button");
        continue;
      }
      const screen = s.route.split("/")[1];
      expect((SCREENS as readonly string[]).includes(screen), `${s.id} -> ${s.route}`).toBe(true);
    }
  });
  it("rings a menu link that the menu really lists", () => {
    for (const s of tourSteps("admin")) {
      if (!s.nav) continue;
      expect(NAV_ENTRIES.some((e) => e.id === s.nav), s.id).toBe(true);
    }
  });
  it("puts the Firm steps in the admin list only, and nothing in the worker list is admin-only", () => {
    const worker = tourSteps("worker");
    const admin = tourSteps("admin");
    expect(worker.some((s) => s.admin)).toBe(false);
    expect(admin.filter((s) => s.admin).map((s) => s.id)).toEqual(["firm", "roles"]);
    for (const s of worker) {
      const screen = s.route ? s.route.split("/")[1] : "home";
      expect(canView(screen as never, "worker"), s.id).toBe(true);
    }
    expect(admin.filter((s) => s.route && ADMIN_ONLY.includes(s.route.split("/")[1] as never)).every((s) => s.admin)).toBe(true);
    expect(worker.map((s) => s.id)).toEqual(admin.filter((s) => !s.admin).map((s) => s.id));
  });
  it("covers the places the brief names", () => {
    expect(tourSteps("worker").map((s) => s.route)).toEqual(["/home", "/needs-you", "/routines", "/growth", "/your-data", null]);
    expect(tourSteps("admin").map((s) => s.route)).toEqual(["/home", "/needs-you", "/routines", "/growth", "/your-data", "/firm", "/roles", null]);
  });
});

describe("anchors", () => {
  it("rings a menu link or the stop button", () => {
    const steps = tourSteps("admin");
    expect(anchorSelector(steps[0])).toBe('nav#nav a[href="#/home"]');
    expect(anchorSelector(steps[5])).toBe('nav#nav a[href="#/firm"]');
    expect(anchorSelector(steps[6])).toBe('nav#nav a[href="#/roles"]');
    expect(anchorSelector(steps[7])).toBe(".stop-button");
  });
});

describe("step maths", () => {
  it("clamps a step into the list", () => {
    expect(clampStep(-3, 6)).toBe(0);
    expect(clampStep(9, 6)).toBe(5);
    expect(clampStep(2.7, 6)).toBe(2);
    expect(clampStep(Number.NaN, 6)).toBe(0);
    expect(clampStep(1, 0)).toBe(0);
  });
  it("says where you are", () => {
    expect(progressText(2, 6)).toBe("Step 3 of 6");
    expect(progressShare(5, 6)).toBe(1);
    expect(progressShare(0, 8)).toBeCloseTo(1 / 8);
    expect(progressShare(0, 0)).toBe(0);
  });
  it("keeps a step by its id when the view changes, and ends the tour when the step is gone", () => {
    // Admin step 4 is Your data (index 4); the worker list has it at 4 too.
    expect(stepAfterViewChange("admin", 4, "worker")).toBe(4);
    // Firm overview (admin index 5) and Roles (6) do not exist for a worker.
    expect(stepAfterViewChange("admin", 5, "worker")).toBeNull();
    expect(stepAfterViewChange("admin", 6, "worker")).toBeNull();
    // The stop button moves from index 7 to 5 and stays the same step.
    expect(stepAfterViewChange("admin", 7, "worker")).toBe(5);
    // Worker -> admin: the stop step moves to the end.
    expect(stepAfterViewChange("worker", 5, "admin")).toBe(7);
    expect(stepAfterViewChange("worker", 99, "admin")).toBeNull();
  });
});

describe("ring geometry", () => {
  const vp = { width: 1440, height: 900 };
  it("rings only what is on screen and has size", () => {
    expect(ringable(null, vp)).toBe(false);
    expect(ringable({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }, vp)).toBe(false);
    expect(ringable({ left: 20, top: 100, right: 200, bottom: 140, width: 180, height: 40 }, vp)).toBe(true);
    // off-canvas menu (moved out of the viewport)
    expect(ringable({ left: -300, top: 100, right: -100, bottom: 140, width: 200, height: 40 }, vp)).toBe(false);
    expect(ringable({ left: 1500, top: 100, right: 1700, bottom: 140, width: 200, height: 40 }, vp)).toBe(false);
  });
  it("grows the box by the padding and keeps it inside the viewport", () => {
    expect(ringBox({ left: 100, top: 100, width: 50, height: 20 }, 4, vp)).toEqual({ left: 96, top: 96, width: 58, height: 28 });
    expect(ringBox({ left: 2, top: 1, width: 50, height: 20 }, 4, vp)).toEqual({ left: 0, top: 0, width: 56, height: 25 });
    expect(ringBox({ left: 1420, top: 880, width: 40, height: 40 }, 4, vp)).toEqual({ left: 1416, top: 876, width: 24, height: 24 });
  });
});
