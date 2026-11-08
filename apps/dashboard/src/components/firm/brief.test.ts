import { describe, expect, it } from "vitest";
import { BRIEF_LIMITS, BRIEF_STATEMENT, buildBrief } from "./brief";
import { normaliseOnboarding, normaliseOverview, normaliseRoles } from "./model";
import overviewFx from "../../fixtures/firm-overview.json";
import rolesFx from "../../fixtures/firm-roles.json";
import onboardingFx from "../../fixtures/firm-onboarding.json";

const o = normaliseOverview(overviewFx);
const r = normaliseRoles(rolesFx);
const w = normaliseOnboarding(onboardingFx);

describe("buildBrief", () => {
  const b = buildBrief(o, r, w, "2026-11-09");
  it("carries the coaching statement and names the made-up firm", () => {
    expect(b.statement).toBe(BRIEF_STATEMENT);
    expect(b.label).toBe("made-up firm");
  });
  it("shows at most seven insights, each with its n", () => {
    expect(b.insights.length).toBeLessThanOrEqual(7);
    expect(b.insights.length).toBe(o.top.length);
    for (const i of b.insights) expect(i.n).toMatch(/^\d/);
  });
  it("has a row for every role in both tables, taken from the data", () => {
    expect(b.roles.map((x) => x.role)).toEqual(r.roles.map((x) => x.role));
    expect(b.onboarding.map((x) => x.role)).toEqual(w.roles.map((x) => x.role));
  });
  it("prints intervals beside the onboarding figures", () => {
    expect(b.onboarding[0].median).toMatch(/\(.* to .*\)/);
    expect(b.onboarding[0].reached).toMatch(/%/);
  });
  it("names the target as a design target", () => {
    expect(b.target).toMatch(/design target/);
  });
  it("lists the limits, and none of them ranks anyone", () => {
    expect(b.limits).toBe(BRIEF_LIMITS);
    expect(b.limits.join(" ")).toMatch(/synthetic/);
    expect(JSON.stringify(b)).not.toMatch(/best performer|top performer|league|ranking of/i);
  });
  it("does not compare a role whose groups are under the minimum", () => {
    const small = { ...r, roles: r.roles.map((x, i) => (i === 0 ? { ...x, n_expert: 2 } : x)) };
    const bs = buildBrief(o, small, w, null);
    expect(bs.roles[0].compared).toBe(false);
    expect(bs.roles[0].gap).toMatch(/Not compared/);
    expect(bs.roles[0].independence).toBe("");
  });
});

import { longDate } from "./brief";
describe("longDate", () => {
  it("writes a date out in words", () => {
    expect(longDate("2026-11-09T09:00:00Z")).toBe("9 November 2026");
    expect(longDate("2026-01-02")).toBe("2 January 2026");
  });
  it("is null when there is nothing to read", () => {
    expect(longDate(null)).toBeNull();
    expect(longDate("later")).toBeNull();
  });
});
