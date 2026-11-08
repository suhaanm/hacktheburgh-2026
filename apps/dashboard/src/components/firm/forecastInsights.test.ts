import { describe, expect, it } from "vitest";
import firmFx from "../../fixtures/firm-firm.json";
import onboardingFx from "../../fixtures/firm-onboarding.json";
import rolesFx from "../../fixtures/firm-roles.json";
import { buildForecastInsights, niceTop, wilson, type ForecastInput } from "./forecastInsights";
import { normaliseFirm, normaliseOnboarding, normaliseRoles } from "./model";

const NOW = new Date("2026-11-09T12:00:00Z");
const onboarding = normaliseOnboarding(onboardingFx);
const roles = normaliseRoles(rolesFx);
const firm = normaliseFirm(firmFx);
const row = (id: string, label: string, h: number, people = 9) => ({
  id, label, key: null, family: "open" as const, role: "x", people, count: 120, minutes_per_week: { point: h * 60, lo: 0, hi: 0 },
  hours_per_week: { point: h, lo: h * 0.8, hi: h * 1.2 }, stops_before: "none" as const,
});
const hits = { total: { actions: 5, people: 24, hours_per_week: { point: 14, lo: 11, hi: 17 } }, rows: [row("a", "Open the claim record", 6), row("b", "Copy the reference", 5), row("c", "Check the address", 3)], min_group: 5 };
const full: ForecastInput = { onboarding, roles, firm, hits, now: NOW };
const none: ForecastInput = { onboarding: null, roles: null, firm: null, hits: null, now: NOW };

const BAD = /NaN|undefined|null|Infinity|\[object/;

describe("forecast insights from the example firm", () => {
  const out = buildForecastInsights(full);
  it("gives at most three, each with an expect line, a do line, a confidence word, n and a chart", () => {
    expect(out.length).toBe(3);
    for (const i of out) {
      expect(i.expect.length).toBeGreaterThan(20);
      expect(i.todo.length).toBeGreaterThan(10);
      expect(["likely", "possible", "too_early"]).toContain(i.confidence);
      expect(i.n).toMatch(/^n = /);
      expect(i.numbers.rows.length).toBeGreaterThan(0);
      expect(JSON.stringify(i)).not.toMatch(BAD);
    }
  });
  it("puts the surest insight first and keeps one sentence per line", () => {
    const rank = { likely: 0, possible: 1, too_early: 2 };
    for (let k = 1; k < out.length; k++) expect(rank[out[k].confidence]).toBeGreaterThanOrEqual(rank[out[k - 1].confidence]);
    for (const i of out) {
      expect(i.expect.match(/[.!?](\s|$)/g)?.length ?? 0).toBe(1);
      expect(i.todo.match(/[.!?](\s|$)/g)?.length ?? 0).toBeLessThanOrEqual(2);
    }
  });
  it("names roles, habits and counts, never a person", () => {
    const names = firm.roles.flatMap((r) => r.users.map((u) => u.name ?? "")).filter(Boolean);
    const text = JSON.stringify(out);
    for (const n of names) expect(text).not.toContain(n);
  });
  it("onboarding is hedged when one median has no interval (the example data's data analysts)", () => {
    const o = buildForecastInsights({ ...none, onboarding, firm }).find((i) => i.id === "onboarding");
    expect(o?.confidence).toBe("too_early");
    expect(o?.expect).toBe("Benefits processors may take longer than data analysts, but the gap is not clear yet.");
    expect(o?.detail).toBe("Median step: data analysts 27, benefits processors 82. One has no interval yet.");
  });
  it("onboarding says how many steps sooner and how many new starters, with the month ahead", () => {
    const withCi = normaliseOnboarding({ ...onboardingFx, data: { ...onboardingFx.data, roles: onboardingFx.data.roles.map((r) => (r.role === "data-analyst" ? { ...r, median_to_target: { value: 27, ci: [20, 34] } } : r)) } });
    const o = buildForecastInsights({ ...none, onboarding: withCi, firm }).find((i) => i.id === "onboarding");
    expect(o?.confidence).toBe("likely");
    expect(o?.expect).toMatch(/^Expect \d+ new starters? to need coaching through December\.$/);
    expect(o?.todo).toBe("Start coaching with the newest benefits processors.");
    expect(o?.chart.kind).toBe("interval");
    expect(o?.detail).toMatch(/^Benefits processors take about 55 more steps\. Interval -?\d+ to -?\d+\.$/);
    expect(o?.n).toBe("n = 12 and 23 people");
  });
  it("the gap insight names the habit that explains most of the gap", () => {
    const g = buildForecastInsights({ ...none, roles }).find((i) => i.id === "gap");
    expect(g?.expect).toBe("Expect junior data analysts to finish 37 points fewer of their steps without help than experts.");
    expect(g?.todo).toMatch(/^Practise “.+” first\.$/);
    expect(g?.detail).toMatch(/^Gap -37 points, mostly on “.+”\. Interval -40 to -35\.$/);
    expect(g?.chart).toMatchObject({ kind: "interval", unit: "share" });
  });
  it("repeated work gives the hours with their interval and a three-row chart", () => {
    const r = buildForecastInsights({ ...none, hits }).find((i) => i.id === "repeated");
    expect(r?.expect).toBe("Expect about 14 hours a week to free up with routines.");
    expect(r?.todo).toBe("Offer routines for “Open the claim record” first.");
    expect(r?.detail).toBe("The biggest piece is done by 9 people. Interval 11 to 17 hours.");
    expect(r?.chart.kind === "interval" && r.chart.rows.length).toBe(3);
  });
  it("the trend insight counts people by class", () => {
    const t = buildForecastInsights({ ...none, firm }).find((i) => i.id === "trend");
    expect(t?.chart.kind).toBe("mix");
    expect(t?.chart.kind === "mix" && t.chart.parts.reduce((a, p) => a + p.count, 0)).toBe(60);
  });
});

describe("forecast insights on thin data", () => {
  it("nothing in, nothing out", () => {
    expect(buildForecastInsights(none)).toEqual([]);
    expect(buildForecastInsights({ ...none, onboarding: normaliseOnboarding({}), roles: normaliseRoles({}), firm: normaliseFirm({}) })).toEqual([]);
  });
  it("one group is not a comparison, so there is no onboarding insight", () => {
    const one = normaliseOnboarding({ roles: [{ role: "p", name: "Programmer", n: 12, median_to_target: { value: 40, ci: [30, 50] } }] });
    expect(buildForecastInsights({ ...none, onboarding: one })).toEqual([]);
  });
  it("a role under five people is left out", () => {
    const two = normaliseOnboarding({ roles: [
      { role: "p", name: "Programmer", n: 12, median_to_target: { value: 40, ci: [30, 50] } },
      { role: "q", name: "Analyst", n: 4, median_to_target: { value: 90, ci: [60, 120] } },
    ] });
    expect(buildForecastInsights({ ...none, onboarding: two })).toEqual([]);
  });
  it("overlapping intervals are said in words, not as a direction we cannot read", () => {
    const o = normaliseOnboarding({ roles: [
      { role: "p", name: "Programmer", n: 12, median_to_target: { value: 54, ci: [39, 80] } },
      { role: "q", name: "Analyst", n: 14, median_to_target: { value: 70, ci: [56, 109] } },
    ] });
    const [i] = buildForecastInsights({ ...none, onboarding: o });
    expect(i.confidence).toBe("too_early");
    expect(i.expect).toBe("Analysts may take longer than programmers, but the gap is not clear yet.");
    expect(i.todo).toBe("Wait for more people before planning around it.");
  });
  it("a median with no interval is too early to say", () => {
    const o = normaliseOnboarding({ roles: [
      { role: "p", name: "Programmer", n: 12, median_to_target: { value: 27 } },
      { role: "q", name: "Analyst", n: 14, median_to_target: { value: 90, ci: [56, 109] } },
    ] });
    expect(buildForecastInsights({ ...none, onboarding: o })[0].confidence).toBe("too_early");
  });
  it("a gap whose interval spans zero is too early to say, and a verdict of cannot tell never reads as a gap", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", gap: { value: -0.05, ci: [-0.2, 0.1] }, verdict: "cannot_tell" }], habits: [] }] });
    const [i] = buildForecastInsights({ ...none, roles: r });
    expect(i.confidence).toBe("too_early");
    expect(i.expect).toBe("Junior programmers may finish fewer of their steps without help than experts, but it is not clear yet.");
  });
  it("a negative gain (juniors ahead of experts) says more, not fewer", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 20, enough: true, measures: [{ key: "independence", gap: { value: 0.12, ci: [0.05, 0.2] }, verdict: "gap" }], habits: [] }] });
    expect(buildForecastInsights({ ...none, roles: r })[0].expect).toBe("Expect junior programmers to finish 12 points more of their steps without help than experts.");
  });
  it("a role with no habits still gets a do line", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 20, enough: true, measures: [{ key: "independence", gap: { value: -0.3, ci: [-0.4, -0.2] }, verdict: "gap" }] }] });
    expect(buildForecastInsights({ ...none, roles: r })[0].todo).toBe("Look at the steps where juniors ask for help most.");
  });
  it("repeated work with no hours, NaN hours or no rows gives nothing", () => {
    expect(buildForecastInsights({ ...none, hits: { ...hits, rows: [] } })).toEqual([]);
    expect(buildForecastInsights({ ...none, hits: { ...hits, total: { ...hits.total, hours_per_week: { point: Number.NaN, lo: 0, hi: 0 } } } })).toEqual([]);
    expect(buildForecastInsights({ ...none, hits: { ...hits, total: { ...hits.total, hours_per_week: { point: 0, lo: 0, hi: 0 } } } })).toEqual([]);
  });
  it("repeated work done by fewer than five people is too early to say", () => {
    const small = { ...hits, total: { ...hits.total, people: 3 } };
    const [i] = buildForecastInsights({ ...none, hits: small });
    expect(i.confidence).toBe("too_early");
    expect(i.expect).toBe("Repeated work may add up to about 14 hours a week.");
    expect(i.todo).toBe("Wait for more people before planning around it.");
  });
  it("10 000 occurrences and a very long action label stay in one short phrase", () => {
    const big = { ...hits, total: { actions: 9, people: 10000, hours_per_week: { point: 12345.6, lo: 12000, hi: 13000 } }, rows: [{ ...row("a", "Open ".repeat(40), 6000), count: 10000 }] };
    const [i] = buildForecastInsights({ ...none, hits: big });
    expect(i.expect).toContain("12,346 hours a week");
    expect(i.expect.length).toBeLessThan(160);
    expect(i.numbers.rows[0][3]).toBe("10,000");
  });
  it("fewer than five people in the whole firm gives no trend insight", () => {
    const tiny = normaliseFirm({ roles: [{ role: "p", name: "P", users: [1, 2, 3].map((k) => ({ id: `u${k}`, label: `P-0${k}`, trend: "improving" })) }] });
    expect(buildForecastInsights({ ...none, firm: tiny })).toEqual([]);
  });
  it("a firm where no one needs attention says most people are on track", () => {
    const calm = normaliseFirm({ roles: [{ role: "p", name: "P", users: Array.from({ length: 24 }, (_, k) => ({ id: `u${k}`, label: `P-${k}`, trend: "improving" })) }] });
    const [i] = buildForecastInsights({ ...none, firm: calm });
    expect(i.expect).toBe("Most people are on track: 24 of 24 need less help.");
    expect(i.confidence).not.toBe("too_early");
  });
  it("a broken clock drops the month, not the sentence", () => {
    const [i] = buildForecastInsights({ ...full, now: new Date("nonsense") });
    expect(i.expect).not.toMatch(/through/);
    expect(i.expect).not.toMatch(BAD);
  });
  it("NaN and null in the wire never reach a card", () => {
    const o = normaliseOnboarding({ roles: [
      { role: "p", name: "Programmer", n: Number.NaN, median_to_target: { value: Number.NaN, ci: [Number.NaN, 5] } },
      { role: "q", name: "Analyst", n: null, median_to_target: null },
    ] });
    const r = normaliseRoles({ roles: [{ role: "p", name: null, n_expert: null, n_junior: Number.NaN, measures: [{ key: "independence", gap: { value: Number.NaN } }] }] });
    expect(buildForecastInsights({ ...none, onboarding: o, roles: r })).toEqual([]);
  });
});

describe("axis helpers", () => {
  it("niceTop rounds up and never returns NaN", () => {
    expect(niceTop(109).top).toBeGreaterThanOrEqual(109);
    expect(niceTop(109).ticks[0]).toBe(0);
    expect(niceTop(0).top).toBeGreaterThan(0);
    expect(niceTop(Number.NaN).top).toBeGreaterThan(0);
    expect(niceTop(-4).top).toBeGreaterThan(0);
    expect(niceTop(0.9).ticks.every(Number.isFinite)).toBe(true);
  });
  it("wilson is a proper interval, and null when the counts do not make sense", () => {
    const w = wilson(3, 60);
    expect(w?.[0]).toBeGreaterThan(0);
    expect(w?.[1]).toBeLessThan(0.2);
    expect(wilson(0, 60)?.[0]).toBe(0);
    expect(wilson(5, 0)).toBeNull();
    expect(wilson(7, 5)).toBeNull();
    expect(wilson(Number.NaN, 5)).toBeNull();
  });
});
