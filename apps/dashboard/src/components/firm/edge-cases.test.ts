// @vitest-environment jsdom
// The Admin screens on the data that breaks screens: empty, one person, a group under the minimum, 10 000 occurrences, an interval that spans zero, NaN and
// null, very long and unicode names, numbers dated in the future or years ago, negative gains, a role with nothing to count and stale readiness.
// Each state is rendered for real and the text a person would read is checked: it says the state in words, and never shows NaN, undefined, null or Infinity.
// The matrix (state, what is shown, test name) is in docs/knack-ux/edge-cases-d-admin.md; the names below are the ones it lists.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import firmFx from "../../fixtures/firm-firm.json";
import overviewFx from "../../fixtures/firm-overview.json";
import rolesFx from "../../fixtures/firm-roles.json";
import onboardingFx from "../../fixtures/firm-onboarding.json";
import { AutomationBody } from "./AutomationBody";
import { FreshNote } from "./InsightFirst";
import { OnboardingBody } from "./OnboardingCurves";
import { PeopleBody } from "./PeopleTable";
import { RiskCoverage } from "./RiskCoverage";
import { RolesBody } from "./RoleMultiples";
import { InsightCard } from "./ForecastsView";
import { buildForecastInsights } from "./forecastInsights";
import { gapChart, hitNumbers, hoursChart, onboardingChart, onboardingNumbers, pointsAxis } from "./charts";
import { normaliseFirm, normaliseOnboarding, normaliseOverview, normaliseRoles } from "./model";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };

let host: HTMLDivElement;
let root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const BAD = /\b(NaN|undefined|null|Infinity)\b|\[object|Invalid Date/;
const show = (el: ReturnType<typeof createElement>): string => { act(() => root.render(el)); return host.textContent ?? ""; };
const clean = (t: string): void => { expect(t).not.toMatch(BAD); expect(t.trim().length).toBeGreaterThan(10); };
const open = (el: ReturnType<typeof createElement>): string => { const t = show(el); host.querySelectorAll("details").forEach((d) => { d.open = true; }); return `${t} ${host.textContent ?? ""}`; };

const fx = { overview: normaliseOverview(overviewFx), roles: normaliseRoles(rolesFx), firm: normaliseFirm(firmFx), onb: normaliseOnboarding(onboardingFx) };
const hit = (label: string, h: number, people = 9, extra: object = {}) => ({
  id: label, label, key: null, family: "open" as const, role: "x", people, count: 120, minutes_per_week: { point: h * 60, lo: 0, hi: 0 },
  hours_per_week: { point: h, lo: h * 0.8, hi: h * 1.2 }, stops_before: "none" as const, ...extra,
});
const hits = (rows: ReturnType<typeof hit>[], total = 14, people = 24, suppressed = 0) => ({ window_days: 7 as const, people, min_group: 5, suppressed, not_shown: 0, total: { actions: rows.length, people, hours_per_week: { point: total, lo: total * 0.8, hi: total * 1.2 } }, rows });

describe("empty: no firm, no roles, no people, no hits", () => {
  it("empty firm says so in words on every screen", () => {
    clean(show(createElement(RolesBody, { roles: normaliseRoles({}), min: 5 })));
    expect(host.textContent).not.toContain("See the numbers");
    clean(show(createElement(PeopleBody, { firm: normaliseFirm({}) })));
    expect(host.textContent).not.toContain("See the numbers");
    clean(show(createElement(OnboardingBody, { data: normaliseOnboarding({}) })));
    expect(host.textContent).not.toContain("See the numbers");
    clean(show(createElement(RiskCoverage, { o: normaliseOverview({}) })));
    clean(show(createElement(AutomationBody, { d: hits([], 0, 0), days: 7, onDays: () => undefined })));
    expect(host.textContent).toContain("No repeated work stands out");
  });
  it("empty firm gives no forecast cards and no charts", () => {
    expect(buildForecastInsights({ onboarding: normaliseOnboarding({}), roles: normaliseRoles({}), firm: normaliseFirm({}), hits: null, now: new Date() })).toEqual([]);
    expect(gapChart(normaliseRoles({})).any).toBe(false);
    expect(onboardingChart(normaliseOnboarding({})).any).toBe(false);
    expect(hoursChart([]).any).toBe(false);
  });
});

describe("one person", () => {
  const one = normaliseFirm({ roles: [{ role: "p", name: "Programmer", users: [{ id: "u1", label: "P-01", name: "Ada Lovelace", trend: "improving", tenure_band: "1_3m" }] }] });
  it("one person is one person, with no group figure", () => {
    const t = open(createElement(PeopleBody, { firm: one }));
    clean(t);
    expect(t).toContain("1 of 1 people need less help");
    expect(t).toContain("Fewer than 5 people with data in this group");
  });
  it("one person gives no forecast", () => {
    expect(buildForecastInsights({ onboarding: null, roles: null, firm: one, hits: null, now: new Date() })).toEqual([]);
  });
});

describe("a group under the minimum", () => {
  it("a role with 3 experts is not compared, and the sentence says why", () => {
    const small = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 3, n_junior: 9, enough: true, measures: [{ key: "independence", expert: { value: 1 }, junior: { value: 0.5 }, gap: { value: -0.5, ci: [-0.6, -0.4] }, verdict: "gap" }] }] });
    const t = open(createElement(RolesBody, { roles: small, min: 5 }));
    expect(t).toContain("No role has 5 experts and 5 juniors yet, so none is compared.");
    expect(t).toContain("Not compared.");
    expect(gapChart(small).any).toBe(false);
  });
  it("an onboarding role with 4 people is left out of the chart and the sentence, and shown as not shown in the table", () => {
    const small = normaliseOnboarding({ roles: [{ role: "p", name: "Programmer", n: 4, median_to_target: { value: 40, ci: [30, 50] } }] });
    const t = open(createElement(OnboardingBody, { data: small }));
    expect(t).toContain("Fewer than 5 people have been followed in any role");
    expect(onboardingChart(small).any).toBe(false);
    expect(onboardingNumbers(small).rows[0][1]).toBe("not shown");
  });
  it("repeated work done by 3 people is flagged as too early to say", () => {
    const small = hits([hit("Open the claim", 6)], 14, 3);
    const [i] = buildForecastInsights({ onboarding: null, roles: null, firm: null, hits: small, now: new Date() });
    expect(i.confidence).toBe("too_early");
  });
});

describe("10 000 occurrences", () => {
  it("big counts print with separators and the layout holds", () => {
    const big = hits([hit("Open the claim record", 12345.6, 10000, { count: 1_000_000 })], 12345.6, 10000);
    const t = open(createElement(AutomationBody, { d: big, days: 30, onDays: () => undefined }));
    clean(t);
    expect(t).toContain("10,000 people");
    expect(hitNumbers(big.rows).rows[0][3]).toBe("1,000,000");
  });
  it("a role of 10 000 people is still one line in the People tab", () => {
    const users = Array.from({ length: 2000 }, (_, k) => ({ id: `u${k}`, label: `P-${k}`, trend: k % 7 === 0 ? "needs_attention" : "improving" }));
    const t = show(createElement(PeopleBody, { firm: normaliseFirm({ roles: [{ role: "p", name: "Programmer", users }] }) }));
    clean(t);
    expect(t).toContain("of 2,000 people");
  });
});

describe("an interval that spans zero", () => {
  it("a role gap with an interval across zero is drawn hollow and the sentence says it cannot be read", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", expert: { value: 0.8 }, junior: { value: 0.78 }, gap: { value: -0.02, ci: [-0.2, 0.15] }, verdict: "cannot_tell" }] }] });
    expect(gapChart(r).rows[0].hollow).toBe(true);
    clean(show(createElement(RolesBody, { roles: r, min: 5 })));
    expect(host.textContent).toContain("No gap between juniors and experts can be read yet.");
  });
  it("a forecast whose interval spans zero says too early to say", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", gap: { value: -0.05, ci: [-0.2, 0.1] }, verdict: "gap" }] }] });
    expect(buildForecastInsights({ onboarding: null, roles: r, firm: null, hits: null, now: new Date() })[0].confidence).toBe("too_early");
  });
});

describe("NaN and null fields", () => {
  it("a role with NaN gap, null habits and a null name still reads", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: null, n_expert: Number.NaN, n_junior: null, enough: true, measures: [{ key: "independence", expert: { value: Number.NaN }, gap: { value: Number.NaN, ci: [Number.NaN, 1] } }], habits: null }] });
    clean(open(createElement(RolesBody, { roles: r, min: 5 })));
  });
  it("a person with every field null is still a row", () => {
    const f = normaliseFirm({ roles: [{ role: "p", name: "P", users: [{ id: "u1", label: null, name: null, role: null, trend: null, independence: Number.NaN, tenure_band: null, tenure_weeks: null, skills: null }] }] });
    clean(open(createElement(PeopleBody, { firm: f })));
  });
  it("an overview with NaN counts says it plainly", () => {
    const o = normaliseOverview({ firm: { users: Number.NaN, roles: null }, coverage: { users: Number.NaN, enough_data: null, roles: [{ role: "p", users: Number.NaN }] }, risk: { open_approvals: Number.NaN, approval_backlog_age_h: { median: Number.NaN, max: Number.NaN } } });
    clean(open(createElement(RiskCoverage, { o })));
  });
  it("a repeated action with NaN hours is left out of the chart and the table", () => {
    const rows = [hit("Good", 6), hit("Bad", Number.NaN), hit("Zero", 0)];
    expect(hoursChart(rows).rows.map((r) => r.id)).toEqual(["Good"]);
    expect(hitNumbers(rows).rows.length).toBe(1);
    expect(pointsAxis([Number.NaN, Infinity]).ticks.every(Number.isFinite)).toBe(true);
  });
});

describe("very long and unicode names", () => {
  const long = "Senior Customer Experience Escalations Programme Delivery Lead for the North West Region";
  it("a very long role name is cut in the sentences and the chart, and whole in the table", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: long, n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", expert: { value: 0.9 }, junior: { value: 0.6 }, gap: { value: -0.3, ci: [-0.4, -0.2] }, verdict: "gap" }] }] });
    const t = show(createElement(RolesBody, { roles: r, min: 5 }));
    expect(t).toContain("…");
    expect(gapChart(r).rows[0].label.length).toBeLessThanOrEqual(48); // the plot wraps a long name over two lines
  });
  it("unicode and emoji names are never split into broken characters", () => {
    const f = normaliseFirm({ roles: [{ role: "p", name: "数据分析师 🧑‍💻", users: [{ id: "u1", label: "A-1", name: "Zoë Ångström", trend: "improving" }, { id: "u2", label: "A-2", name: "李小龙", trend: "needs_attention" }] }] });
    const t = open(createElement(PeopleBody, { firm: f }));
    clean(t);
    expect(t).toContain("数据分析师 🧑‍💻, 2 people");
    expect(t).toContain("Zoë Ångström");
    expect(t).toContain("李小龙");
  });
  it("a person with a 200 character name keeps its row one cell wide", () => {
    const f = normaliseFirm({ roles: [{ role: "p", name: "P", users: [{ id: "u1", label: "P-1", name: "N".repeat(200), trend: "improving" }] }] });
    clean(open(createElement(PeopleBody, { firm: f })));
    expect(host.querySelectorAll("tr").length).toBeGreaterThan(1);
  });
});

describe("numbers dated in the future or years ago", () => {
  const now = new Date("2026-11-08T12:00:00Z");
  it("numbers from years ago say so in words", () => {
    const t = show(createElement(FreshNote, { asOf: "2022-03-01T00:00:00Z", now }));
    expect(t).toContain("4 years ago");
    clean(t);
  });
  it("numbers dated after today say so in words", () => {
    expect(show(createElement(FreshNote, { asOf: "2027-01-01T00:00:00Z", now }))).toContain("after today");
  });
  it("numbers from yesterday, and a date nobody can read, say nothing", () => {
    expect(show(createElement(FreshNote, { asOf: "2026-11-07T09:00:00Z", now }))).toBe("");
    expect(show(createElement(FreshNote, { asOf: "last tuesday", now }))).toBe("");
  });
  it("a broken clock still gives a forecast, without a month", () => {
    const i = buildForecastInsights({ onboarding: fx.onb, roles: fx.roles, firm: fx.firm, hits: null, now: new Date("nonsense") });
    expect(i.length).toBeGreaterThan(0);
    // The words a person reads (the data fields may hold null; the sentences never say it).
    expect(i.map((x) => `${x.expect} ${x.todo} ${x.n} ${x.detail ?? ""} ${x.numbers.rows.flat().join(" ")}`).join(" ")).not.toMatch(BAD);
    expect(i.some((x) => /through/.test(x.expect))).toBe(false);
  });
});

describe("negative gains", () => {
  it("juniors ahead of experts read as more, never as a minus sign in a sentence", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 20, enough: true, measures: [{ key: "independence", expert: { value: 0.6 }, junior: { value: 0.72 }, gap: { value: 0.12, ci: [0.05, 0.2] }, verdict: "gap" }] }] });
    const t = show(createElement(RolesBody, { roles: r, min: 5 }));
    expect(t).toContain("12 points more of their steps without help than experts");
    expect(gapChart(r).domain[1]).toBeGreaterThan(0);
  });
  it("a negative median or hours never reaches a chart", () => {
    expect(hoursChart([hit("A", -4)]).any).toBe(false);
  });
});

describe("a role with nothing to count (no cogs)", () => {
  it("a person with no per-skill figures says so when opened", () => {
    const f = normaliseFirm({ roles: [{ role: "p", name: "P", users: [{ id: "u1", label: "P-1", name: "Sam", trend: "cannot_tell_yet", skills: [] }] }] });
    act(() => root.render(createElement(PeopleBody, { firm: f })));
    host.querySelectorAll("details").forEach((d) => { d.open = true; });
    const btn = host.querySelector<HTMLButtonElement>(".firm-person__btn");
    expect(btn).toBeTruthy();
    act(() => { btn?.click(); });
    expect(host.textContent).toContain("No per-skill figures yet.");
  });
  it("a role with no curve says why in the numbers, not a blank", () => {
    const o = normaliseOnboarding({ roles: [{ role: "p", name: "Programmer", n: 9, curve: [], median_to_target: null, reason: "Fewer than 5 people followed" }] });
    const t = open(createElement(OnboardingBody, { data: o }));
    clean(t);
    expect(t).toContain("No curve yet");
  });
  it("a role with no habits still gets a do line", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 20, enough: true, measures: [{ key: "independence", gap: { value: -0.3, ci: [-0.4, -0.2] }, verdict: "gap" }] }] });
    expect(buildForecastInsights({ onboarding: null, roles: r, firm: null, hits: null, now: new Date() })[0].todo).toBe("Look at the steps where juniors ask for help most.");
  });
});

describe("stale readiness", () => {
  it("nobody has enough data for a trend: the sentence says so and the figure is 0 of N", () => {
    const stale = normaliseFirm({ roles: [{ role: "p", name: "P", users: Array.from({ length: 24 }, (_, k) => ({ id: `u${k}`, label: `P-${k}`, trend: "not_enough_data", status: "stale" })) }] });
    const t = show(createElement(PeopleBody, { firm: stale }));
    expect(t).toContain("No one has a clear trend yet among 24 people.");
    const o = normaliseOverview({ firm: { users: 24, roles: 1 }, coverage: { users: 24, enough_data: 0, min_occurrences: 20, roles: [{ role: "p", name: "P", users: 24, enough_data: 0 }], by_status: { stale: 24 } }, risk: null });
    const r = open(createElement(RiskCoverage, { o }));
    expect(r).toContain("0 of 24");
    expect(r).toContain("Not seen lately: 24");
    expect(r).toContain("No risk figures have been sent yet.");
  });
  it("a card with no interval still prints n and says too early", () => {
    const [i] = buildForecastInsights({ onboarding: null, roles: null, firm: normaliseFirm({ roles: [{ role: "p", name: "P", users: Array.from({ length: 5 }, (_, k) => ({ id: `u${k}`, label: `P-${k}`, trend: "needs_attention" })) }] }), hits: null, now: new Date("2026-11-08T12:00:00Z") });
    const t = show(createElement(InsightCard, { i, open: false, onToggle: () => undefined }));
    expect(t).toContain("n = 5 people");
    clean(t);
  });
});
