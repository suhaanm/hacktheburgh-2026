import { describe, expect, it } from "vitest";
import overviewFx from "../../fixtures/firm-overview.json";
import rolesFx from "../../fixtures/firm-roles.json";
import firmFx from "../../fixtures/firm-firm.json";
import onboardingFx from "../../fixtures/firm-onboarding.json";
import {
  CONFIDENCE_WORD, automationHeadline, briefHeadline, capFirst, confidence, confidenceApart, firmHeadline, freshness, monthAhead, onboardingHeadline,
  peopleHeadline, plural, riskHeadline, roleWords, rolesHeadline, shortName,
} from "./insights";
import { normaliseFirm, normaliseOnboarding, normaliseOverview, normaliseRoles } from "./model";

const overview = normaliseOverview(overviewFx);
const roles = normaliseRoles(rolesFx);
const firm = normaliseFirm(firmFx);
const onboarding = normaliseOnboarding(onboardingFx);

describe("words", () => {
  it("agrees the unit with the number and never prints NaN", () => {
    expect(plural(1, "person", "people")).toBe("1 person");
    expect(plural(24, "person", "people")).toBe("24 people");
    expect(plural(0, "approval")).toBe("0 approvals");
    expect(plural(Number.NaN, "approval")).toBe("0 approvals");
    expect(plural(-3, "approval")).toBe("0 approvals");
    expect(plural(10000, "time")).toBe("10,000 times");
  });
  it("keeps a very long name to one line and handles unicode by characters", () => {
    expect(shortName("   ")).toBe("this role");
    expect(shortName(null)).toBe("this role");
    expect(shortName("A".repeat(80)).length).toBe(32);
    expect(shortName("A".repeat(80)).endsWith("…")).toBe(true);
    expect([...shortName("数据分析师".repeat(12), 10)].length).toBe(10);
    expect(shortName("Zoë Ångström")).toBe("Zoë Ångström");
  });
  it("makes a role name plural for a sentence", () => {
    expect(roleWords("Programmer")).toBe("programmers");
    expect(roleWords("Benefits processors")).toBe("benefits processors");
    expect(roleWords("QA")).toBe("QAs");
    expect(capFirst(roleWords("Data analyst"))).toBe("Data analysts");
    expect(roleWords("")).toBe("people in this role");
    expect(roleWords("数据分析师")).toBe("数据分析师");
  });
  it("names the month a few weeks ahead, and nothing for a broken clock", () => {
    expect(monthAhead(new Date("2026-02-20T09:00:00Z"))).toBe("March");
    expect(monthAhead(new Date("2026-12-20T09:00:00Z"))).toBe("January");
    expect(monthAhead(new Date("nonsense"))).toBeNull();
  });
});

describe("the confidence word is chosen by code from n and the interval", () => {
  it("is too early under five people, with no interval, or when the interval includes no change", () => {
    expect(confidence({ n: 4, value: 5, ci: [3, 7] })).toBe("too_early");
    expect(confidence({ n: 40, value: 5, ci: null })).toBe("too_early");
    expect(confidence({ n: 40, value: 1, ci: [-2, 3] })).toBe("too_early");
    expect(confidence({ n: 40, value: Number.NaN, ci: [1, 2] })).toBe("too_early");
    expect(confidence({ n: Number.NaN, value: 1, ci: [1, 2] })).toBe("too_early");
    expect(confidence({ n: null, value: 1, ci: [1, 2] })).toBe("too_early");
  });
  it("is possible with fewer than ten people or a wide interval, and likely with ten or more and a clear interval", () => {
    expect(confidence({ n: 7, value: 5, ci: [4, 6] })).toBe("possible");
    expect(confidence({ n: 40, value: 5, ci: [0.5, 12] })).toBe("possible");
    expect(confidence({ n: 40, value: 5, ci: [4, 6] })).toBe("likely");
    expect(confidence({ n: 40, value: -5, ci: [-6, -4] })).toBe("likely");
  });
  it("lets an amount with no meaningful zero be judged on n and width alone", () => {
    expect(confidence({ n: 40, value: 14, ci: [-5, 20], zero: null })).toBe("possible");
    expect(confidence({ n: 40, value: 14, ci: [12, 16], zero: null })).toBe("likely");
  });
  it("reads a difference between two roles only when their intervals do not overlap", () => {
    expect(confidenceApart({ n: 12, value: 27, ci: [20, 34] }, { n: 23, value: 82, ci: [56, 109] })).toBe("likely");
    expect(confidenceApart({ n: 8, value: 45, ci: [39, 50] }, { n: 23, value: 82, ci: [56, 109] })).toBe("possible");
    expect(confidenceApart({ n: 8, value: 54, ci: [39, 62] }, { n: 23, value: 82, ci: [56, 109] })).toBe("too_early");
    expect(confidenceApart({ n: 8, value: 54, ci: [39, 70] }, { n: 23, value: 82, ci: [56, 109] })).toBe("too_early");
    expect(confidenceApart({ n: 12, value: 27, ci: null }, { n: 23, value: 82, ci: [56, 109] })).toBe("too_early");
  });
  it("has a word for each level", () => {
    expect(Object.values(CONFIDENCE_WORD)).toEqual(["Likely", "Possible", "Too early to say"]);
  });
});

describe("freshness: numbers that are old, or dated after today", () => {
  const now = new Date("2026-11-09T12:00:00Z");
  it("says nothing for recent numbers and for dates it cannot read", () => {
    expect(freshness("2026-11-09T09:00:00Z", now)).toMatchObject({ state: "fresh", text: null });
    expect(freshness("2026-11-02T09:00:00Z", now).state).toBe("fresh");
    expect(freshness(null, now)).toMatchObject({ state: "unknown", text: null });
    expect(freshness("not a date", now).state).toBe("unknown");
    expect(freshness("2026-11-09T09:00:00Z", new Date("x")).state).toBe("unknown");
  });
  it("says so in words when they are weeks, months or years old", () => {
    expect(freshness("2026-10-01T09:00:00Z", now).text).toBe("These numbers are from 1 October 2026, 39 days ago.");
    expect(freshness("2026-05-01T09:00:00Z", now).text).toContain("6 months ago");
    expect(freshness("2023-05-01T09:00:00Z", now).text).toContain("3 years ago");
  });
  it("says so when they are dated after today", () => {
    const f = freshness("2027-06-01T09:00:00Z", now);
    expect(f.state).toBe("future");
    expect(f.text).toContain("after today");
  });
});

describe("headlines from the example firm", () => {
  it("the firm overview counts what needs a look", () => {
    expect(firmHeadline(overview)).toBe("5 things need a look this week across 60 people in 3 roles.");
  });
  it("roles names the widest readable gap", () => {
    expect(rolesHeadline(roles)).toBe("Juniors in Data analyst finish 37 points fewer of their steps without help than experts, the widest gap of 2.");
  });
  it("people counts who needs less help and who could use a conversation", () => {
    const h = peopleHeadline(firm);
    expect(h).toMatch(/^\d+ of 60 people need less help than before/);
    expect(h.endsWith(".")).toBe(true);
  });
  it("onboarding says the gap is not clear while one median has no interval (the example data's data analysts)", () => {
    expect(onboardingHeadline(onboarding)).toBe("Data analysts may reach the target sooner than benefits processors, but the gap is not clear yet.");
  });
  it("onboarding states the difference once the two intervals do not overlap", () => {
    const withCi = normaliseOnboarding({ ...onboardingFx, data: { ...onboardingFx.data, roles: onboardingFx.data.roles.map((r) => (r.role === "data-analyst" ? { ...r, median_to_target: { value: 27, ci: [20, 34] } } : r)) } });
    expect(onboardingHeadline(withCi)).toBe("Data analysts reach the target about 55 steps sooner than benefits processors.");
  });
  it("a name cut for length ends at a word, not in the middle of one", () => {
    expect(shortName("Enter the household into three calculators", 24)).toBe("Enter the household…");
    expect(shortName("Reconcile with the control figure before release", 30)).toBe("Reconcile with the control…");
  });
  it("risk lists what is waiting and what stopped", () => {
    expect(riskHeadline(overview)).toBe("3 approvals are waiting, the oldest for 72 hours; 2 more things need a look.");
    const one = normaliseOverview({ risk: { open_approvals: 0, injection_pauses_30d: 1, kill_events_30d: 0, approval_backlog_age_h: null } });
    expect(riskHeadline(one)).toBe("1 run was paused by an injected page.");
    const two = normaliseOverview({ risk: { open_approvals: 1, injection_pauses_30d: 0, kill_events_30d: 4, approval_backlog_age_h: { median: 5, max: 5 } } });
    expect(riskHeadline(two)).toBe("1 approval is waiting, the oldest for 5 hours; 1 more thing needs a look.");
  });
  it("the brief says how many people have enough data", () => {
    expect(briefHeadline(overview)).toBe("60 people in 3 roles; 57 have enough data for a trend.");
  });
  it("repeated work names the hours and the biggest piece", () => {
    const row = (label: string, h: number) => ({ id: label, label, key: null, family: "open" as const, role: "x", people: 9, count: 100, minutes_per_week: { point: h * 60, lo: 0, hi: 0 }, hours_per_week: { point: h, lo: h - 1, hi: h + 1 }, stops_before: "none" as const });
    const d = { total: { actions: 5, people: 24, hours_per_week: { point: 14.26, lo: 9, hi: 19 } }, rows: [row("Open the claim", 3), row("Copy the reference", 6)] };
    expect(automationHeadline(d)).toBe("About 14.3 hours a week of repeated work across 24 people, the biggest piece being “Copy the reference”.");
  });
});

describe("headlines never break on thin data", () => {
  it("an empty firm", () => {
    const empty = normaliseOverview({});
    expect(firmHeadline(empty)).toBe("No one is in the firm view yet.");
    expect(briefHeadline(empty)).toBe("There is no one in the firm brief yet.");
    expect(riskHeadline(empty)).toBe("No risk figures have been sent yet.");
    expect(rolesHeadline(normaliseRoles({}))).toBe("No roles to compare yet.");
    expect(peopleHeadline(normaliseFirm({}))).toBe("No one is listed yet.");
    expect(onboardingHeadline(normaliseOnboarding({}))).toBe("No one has been followed through onboarding yet.");
    expect(automationHeadline({ total: { actions: 0, people: 0, hours_per_week: { point: 0, lo: 0, hi: 0 } }, rows: [] })).toBe("No repeated work stands out across 0 people yet.");
  });
  it("a quiet firm says so", () => {
    const quiet = normaliseOverview({ firm: { users: 24, roles: 3 }, top: [], risk: { approval_backlog_age_h: null, injection_pauses_30d: 0, kill_events_30d: 0, open_approvals: 0 } });
    expect(firmHeadline(quiet)).toBe("Nothing stands out this week across 24 people in 3 roles.");
    expect(riskHeadline(quiet)).toBe("Nothing is waiting and nothing was stopped in the last 30 days.");
  });
  it("one person is said as one person", () => {
    expect(firmHeadline(normaliseOverview({ firm: { users: 1, roles: 1 }, top: [{ id: "a", headline: "x", polarity: "attention", n: 1 }] }))).toBe("1 thing needs a look this week across 1 person in 1 role.");
    const one = normaliseFirm({ roles: [{ role: "p", name: "P", users: [{ id: "u1", label: "P-01", trend: "not_enough_data" }] }] });
    expect(peopleHeadline(one)).toBe("Only 1 person so far, too few for a trend.");
  });
  it("a group under the minimum is not compared", () => {
    const small = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 3, n_junior: 9, enough: true, measures: [] }] });
    expect(rolesHeadline(small)).toBe("No role has 5 experts and 5 juniors yet, so none is compared.");
    const onb = normaliseOnboarding({ roles: [{ role: "p", name: "Programmer", n: 3, median_to_target: { value: 40, ci: [30, 50] } }] });
    expect(onboardingHeadline(onb)).toBe("Fewer than 5 people have been followed in any role, so no onboarding speed is shown.");
  });
  it("an interval that spans zero is still a readable sentence, and a verdict of cannot tell is not called a gap", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", gap: { value: -0.02, ci: [-0.2, 0.15] }, verdict: "cannot_tell" }] }] });
    expect(rolesHeadline(r)).toBe("No gap between juniors and experts can be read yet.");
  });
  it("NaN and null fields never reach a sentence", () => {
    const o = normaliseOverview({ firm: { users: Number.NaN, roles: null }, top: [{ id: "a", headline: "x", polarity: "attention", n: Number.NaN }], risk: { open_approvals: Number.NaN, approval_backlog_age_h: { median: Number.NaN, max: Number.NaN } } });
    for (const s of [firmHeadline(o), briefHeadline(o), riskHeadline(o)]) expect(s).not.toMatch(/NaN|undefined|null|Infinity/);
  });
  it("a negative gain reads as 'more', not as a minus sign", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Programmer", n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", gap: { value: 0.12, ci: [0.05, 0.2] }, verdict: "gap" }] }] });
    expect(rolesHeadline(r)).toBe("Juniors in Programmer finish 12 points more of their steps without help than experts.");
  });
  it("a very long role name and a unicode name stay one short phrase", () => {
    const r = normaliseRoles({ roles: [{ role: "p", name: "Senior Customer Experience Escalations Programme Delivery Lead", n_expert: 6, n_junior: 9, enough: true, measures: [{ key: "independence", gap: { value: -0.3, ci: [-0.4, -0.2] }, verdict: "gap" }] }] });
    const h = rolesHeadline(r);
    expect(h).toContain("…");
    expect(h.length).toBeLessThan(140);
    const u = normaliseOnboarding({ roles: [
      { role: "a", name: "数据分析师", n: 9, median_to_target: { value: 20, ci: [15, 25] } },
      { role: "b", name: "Café 🧑‍💻", n: 9, median_to_target: { value: 60, ci: [50, 70] } },
    ] });
    expect(onboardingHeadline(u)).toBe("数据分析师 reach the target about 40 steps sooner than café 🧑‍💻.");
  });
  it("10 000 occurrences print with a thousands separator", () => {
    const d = { total: { actions: 3, people: 10000, hours_per_week: { point: 12345.6, lo: 1, hi: 2 } }, rows: [{ id: "a", label: "Open", key: null, family: "open" as const, role: "x", people: 9, count: 10000, minutes_per_week: { point: 1, lo: 0, hi: 0 }, hours_per_week: { point: 12345.6, lo: 1, hi: 2 }, stops_before: "none" as const }] };
    expect(automationHeadline(d)).toBe("About 12,346 hours a week of repeated work across 10,000 people, the biggest piece being “Open”.");
  });
});
