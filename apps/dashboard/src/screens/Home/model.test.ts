import { describe, expect, it } from "vitest";
import { homeTitle, quietBody, repeatsLine, weekLabel } from "./model";

describe("homeTitle", () => {
  it("counts the pointers in words and never more than three", () => {
    expect(homeTitle("ok", 3)).toBe("Three things from your week");
    expect(homeTitle("ok", 2)).toBe("Two things from your week");
    expect(homeTitle("ok", 1)).toBe("One thing from your week");
    expect(homeTitle("ok", 9)).toBe("Three things from your week");
  });
  it("says plainly when nothing stands out", () => {
    expect(homeTitle("nothing_stands_out", 0)).toBe("Nothing stands out this week");
    expect(homeTitle("ok", 0)).toBe("Nothing stands out this week");
  });
  it("explains the states that are not a normal week", () => {
    expect(homeTitle("onboarding", 0)).toMatch(/getting to know/);
    expect(homeTitle("no_data", 0)).toMatch(/nothing to show/);
    expect(homeTitle("stale", 0)).toMatch(/not fresh/);
    expect(homeTitle("role_changed", 0)).toMatch(/role changed/);
  });
  it("has a fixed body for every quiet state, without exclamation marks or guilt", () => {
    for (const s of ["nothing_stands_out", "onboarding", "no_data", "stale", "role_changed"]) {
      const t = quietBody(s);
      expect(t.length).toBeGreaterThan(20);
      expect(t).not.toMatch(/!|you missed|overdue|behind/i);
    }
  });
});

describe("weekLabel", () => {
  it("joins a week inside one month", () => {
    expect(weekLabel({ from: "2026-11-09", to: "2026-11-15" })).toBe("9 to 15 November");
  });
  it("names both months when the week crosses one", () => {
    expect(weekLabel({ from: "2026-11-30", to: "2026-12-06" })).toBe("30 November to 6 December");
  });
  it("is null when the dates cannot be read", () => {
    expect(weekLabel(null)).toBeNull();
    expect(weekLabel({ from: "soon", to: "later" })).toBeNull();
  });
});

describe("repeatsLine", () => {
  it("is null with nothing repeated", () => {
    expect(repeatsLine(null)).toBeNull();
    expect(repeatsLine({ actions: 0, hours_per_week: { point: 1, lo: 1, hi: 1 } })).toBeNull();
  });
  it("speaks in hours with the interval in the hint", () => {
    const r = repeatsLine({ actions: 6, hours_per_week: { point: 3.44, lo: 2.4, hi: 4.46 } });
    expect(r?.line).toBe("6 repeated actions, about 3.4 hours a week");
    expect(r?.hint).toContain("2.4 to 4.5 hours a week");
  });
  it("speaks in minutes under an hour and keeps the singular", () => {
    const r = repeatsLine({ actions: 1, hours_per_week: { point: 0.5, lo: 0.25, hi: 0.75 } });
    expect(r?.line).toBe("1 repeated action, about 30 minutes a week");
    expect(r?.hint).toContain("15 to 45 minutes a week");
  });
  it("says one hour in the singular", () => {
    expect(repeatsLine({ actions: 2, hours_per_week: { point: 1, lo: 0.8, hi: 1.2 } })?.line).toBe("2 repeated actions, about 1 hour a week");
  });
});
