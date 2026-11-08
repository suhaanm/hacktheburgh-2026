import { describe, expect, it } from "vitest";
import onboardingFx from "../../fixtures/firm-onboarding.json";
import rolesFx from "../../fixtures/firm-roles.json";
import { gapChart, hitNumbers, hoursChart, niceTop, onboardingChart, onboardingNumbers, pointsAxis, wilson } from "./charts";
import { normaliseOnboarding, normaliseRoles } from "./model";

const row = (label: string, h: number, extra: object = {}) => ({
  id: label, label, key: null, family: "open" as const, role: "x", people: 9, count: 120, minutes_per_week: { point: h * 60, lo: 0, hi: 0 },
  hours_per_week: { point: h, lo: h * 0.8, hi: h * 1.2 }, stops_before: "none" as const, ...extra,
});

describe("pointsAxis", () => {
  it("holds zero and every end, on round steps", () => {
    const a = pointsAxis([-37, -40, -35]);
    expect(a.domain[0]).toBeLessThanOrEqual(-40);
    expect(a.domain[1]).toBeGreaterThanOrEqual(0);
    expect(a.ticks).toContain(0);
    expect(a.ticks.every((t) => t % 10 === 0 || t % 5 === 0)).toBe(true);
  });
  it("is at least two steps wide, with no values, and ignores NaN and infinity", () => {
    const a = pointsAxis([]);
    expect(a.domain[1] - a.domain[0]).toBeGreaterThanOrEqual(10);
    expect(pointsAxis([Number.NaN, Infinity, -Infinity]).ticks.every(Number.isFinite)).toBe(true);
  });
  it("covers a positive gain too", () => {
    const a = pointsAxis([5, 12, 20]);
    expect(a.domain[0]).toBeLessThanOrEqual(0);
    expect(a.domain[1]).toBeGreaterThanOrEqual(20);
  });
});

describe("gapChart", () => {
  const roles = normaliseRoles(rolesFx);
  it("has a row for each role that can be compared, in points, with its interval", () => {
    const g = gapChart(roles);
    expect(g.rows.map((r) => r.id)).toEqual(["benefits-processor", "data-analyst"]);
    expect(g.rows[1].est?.value).toBeCloseTo(-37.49, 1);
    expect(g.rows[1].est?.ci?.[0]).toBeLessThan(g.rows[1].est?.value ?? 0);
    expect(g.rows.every((r) => !r.hollow)).toBe(true);
  });
  it("leaves out a role under the minimum", () => {
    expect(gapChart(roles, 8).rows.length).toBe(0);
  });
});

describe("onboardingChart and its table", () => {
  const onb = normaliseOnboarding(onboardingFx);
  it("charts the readable roles from the fastest to the slowest, on a 0-based axis", () => {
    const c = onboardingChart(onb);
    expect(c.rows.map((r) => r.id)).toEqual(["data-analyst", "programmer", "benefits-processor"]);
    expect(c.domain[0]).toBe(0);
    expect(c.domain[1]).toBeGreaterThanOrEqual(109);
  });
  it("lists every role in the table, and says why a role has no median", () => {
    const t = onboardingNumbers(normaliseOnboarding({ roles: [{ role: "p", name: "P", n: 3, median_to_target: { value: 9, ci: [1, 20] } }, { role: "q", name: "Q", n: 9 }] }));
    expect(t.rows).toEqual([["P", "not shown", "3", "not enough data"], ["Q", "fewer than half so far", "9", "not enough data"]]);
  });
});

describe("hoursChart and hitNumbers", () => {
  it("takes the three biggest, with intervals, and a round axis", () => {
    const rows = [row("a", 3), row("b", 9), row("c", 6), row("d", 1)];
    const c = hoursChart(rows);
    expect(c.rows.map((r) => r.id)).toEqual(["b", "c", "a"]);
    expect(c.domain[1]).toBeGreaterThanOrEqual(9 * 1.2);
  });
  it("prints the table with the interval, the people and the times", () => {
    const t = hitNumbers([row("Open", 6, { count: 12345 })]);
    expect(t.rows[0]).toEqual(["Open", "6 (4.8 to 7.2)", "9", "12,345"]);
  });
  it("leaves out NaN, zero and negative hours", () => {
    expect(hitNumbers([row("a", Number.NaN), row("b", 0), row("c", -2)]).rows).toEqual([]);
  });
  it("an interval that is the wrong way round is not drawn as one", () => {
    const c = hoursChart([row("a", 5, { hours_per_week: { point: 5, lo: 9, hi: 2 } })]);
    expect(c.rows[0].est?.ci).toBeNull();
  });
});

describe("niceTop and wilson", () => {
  it("niceTop gives a round top that holds the maximum", () => {
    for (const m of [0.3, 1, 7, 109, 12345]) expect(niceTop(m).top).toBeGreaterThanOrEqual(m);
  });
  it("wilson stays inside 0 and 1", () => {
    for (const [k, n] of [[0, 5], [5, 5], [2, 60]] as const) {
      const w = wilson(k, n);
      expect(w?.[0]).toBeGreaterThanOrEqual(0);
      expect(w?.[1]).toBeLessThanOrEqual(1);
    }
  });
});
