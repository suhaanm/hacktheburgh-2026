import { describe, expect, it } from "vitest";
import {
  DEFAULT_SORT, SORT_KEYS, compareShown, crossing, drillTable, effectText, est, filterUsers, fmtCell, fmtNum, fmtShare, groupShown, interval, normaliseDrill,
  normaliseFirm, normaliseOnboarding, normaliseOverview, normaliseRoles, normaliseSharing, normaliseWhy, normaliseWorker, pct, previewLines, roleGapLine,
  personName, smallRoles, sortUsers, spansZero, trendCounts, trimCurve, TREND_LABEL,
} from "./model";
import type { UserRow } from "./wire";
import workerFx from "../../fixtures/home-worker.json";
import workerGoodFx from "../../fixtures/home-worker-good.json";
import whyFx from "../../fixtures/home-why.json";
import sharingFx from "../../fixtures/home-sharing.json";
import overviewFx from "../../fixtures/firm-overview.json";
import rolesFx from "../../fixtures/firm-roles.json";
import firmFx from "../../fixtures/firm-firm.json";
import onboardingFx from "../../fixtures/firm-onboarding.json";
import drillGapFx from "../../fixtures/firm-drill-role-gap.json";
import drillTrendFx from "../../fixtures/firm-drill-cohort-trend.json";

const user = (label: string, over: Partial<UserRow> = {}): UserRow => ({
  id: label, label, name: null, role: "benefits-processor", level: "junior", status: "ok", last_seen_days: 1, skills: [], tenure_band: "1_3m", tenure_weeks: 8, trend: "improving",
  independence: { value: 0.7, ci: [0.6, 0.8] }, assisted_share: { value: 0.2, ci: [0.1, 0.3] }, time_to_independence: { reached: true, value: 40, unit: "occurrences" },
  automations_running: 0, automation: null, n: 50, n_recent: 20, ...over,
});

describe("est and interval", () => {
  it("reads every shape the services use", () => {
    expect(est(0.4)).toEqual({ value: 0.4, ci: null });
    expect(est({ value: 1, ci: [0, 2] })).toEqual({ value: 1, ci: [0, 2] });
    expect(est({ point: 3, lo: 2, hi: 4 })).toEqual({ value: 3, ci: [2, 4] });
    expect(est({ share: 0.5, wilson: [0.4, 0.6] })).toEqual({ value: 0.5, ci: [0.4, 0.6] });
    expect(est({ median: 58, ci: [48, 61] })).toEqual({ value: 58, ci: [48, 61] });
  });
  it("never invents an interval or a value", () => {
    expect(est({ value: 1 })?.ci).toBeNull();
    expect(est({})).toBeNull();
    expect(est(null)).toBeNull();
    expect(est("x")).toBeNull();
    expect(interval([1])).toBeNull();
    expect(interval(["a", "b"])).toBeNull();
  });
  it("puts a reversed interval the right way round", () => {
    expect(interval([5, 2])).toEqual([2, 5]);
  });
});

describe("formatting", () => {
  it("prints shares and numbers with their intervals, in words", () => {
    expect(fmtShare({ value: 0.624, ci: [0.54, 0.7] })).toBe("62% (54% to 70%)");
    expect(fmtShare({ value: 0.5, ci: null })).toBe("50% (no interval yet)");
    expect(fmtShare(null)).toBe("not enough data");
    expect(fmtNum({ value: 15.27, ci: [13.2, 17.52] }, "s")).toBe("15.3 s (13.2 to 17.5)");
    expect(fmtNum({ value: 200.4, ci: [150, 250] })).toBe("200 (150 to 250)");
  });
  it("knows when an interval spans zero", () => {
    expect(spansZero([-1, 2])).toBe(true);
    expect(spansZero([1, 2])).toBe(false);
    expect(spansZero(null)).toBe(false);
  });
  it("says nothing about intervals for an exact count, and names hours without one", () => {
    expect(effectText({ label: "x", unit: "count", value: 1, ci: null })).toBeNull();
    expect(effectText({ label: "x", unit: "hours", value: 72, ci: null })).toBe("72 hours");
    expect(effectText({ label: "x", unit: "seconds", value: 15.27, ci: [13.2, 17.52] })).toBe("15.3 seconds (13.2 to 17.5)");
    expect(effectText({ label: "x", unit: "share", value: 0.14, ci: [0.0686, 0.2115] })).toBe("14% (7% to 21%)");
    expect(effectText({ label: "x", unit: "seconds", value: 3, ci: null })).toBe("3 seconds (no interval yet)");
    expect(effectText(null)).toBeNull();
  });
  it("formats drill cells by unit", () => {
    expect(fmtCell(0.4668, "share")).toBe("47%");
    expect(fmtCell(38.31, "seconds", [35.53, 41.09])).toBe("38.3 s (35.5 s to 41.1 s)");
    expect(fmtCell(null, "share")).toBe("not enough data");
    expect(fmtCell([0.1, 0.2], "share")).toBe("10% to 20%");
  });
});

describe("the worker's answer", () => {
  const w = normaliseWorker(workerFx);
  it("reads the engine's sample: pointers with a word for how they look, no statistics, an origin badge, one action each", () => {
    expect(w.pointers.length).toBeGreaterThanOrEqual(1);
    expect(w.pointers.length).toBeLessThanOrEqual(3);
    expect(w.status).toBe("ok");
    expect(w.week).toEqual({ from: "2026-11-09", to: "2026-11-15" });
    for (const p of w.pointers) {
      expect(p.polarity_label).toBeTruthy();
      expect(p.badge).toBe("synthetic firm");
      expect(p.n).toBeNull();
      expect(p.headline.length).toBeGreaterThan(10);
      expect(p.action?.to).toBeTruthy();
    }
    expect(w.monday_note).toMatch(/pointers? for your week/);
  });
  it("knows when an example week stands in for the profile", () => {
    expect(normaliseWorker(workerFx).stand_in).toBe(false);
    expect(normaliseWorker({ data: { pointers: [], stand_in: true, stand_in_label: "BP-06" } }).stand_in).toBe(true);
  });
  it("reads a week that is going well", () => {
    const g = normaliseWorker(workerGoodFx);
    expect(g.pointers).toHaveLength(3);
    expect(g.pointers.every((p) => p.polarity === "positive" && p.polarity_label === "Going well")).toBe(true);
    expect(g.monday_note).toMatch(/3 pointers/);
  });
  it("never shows more than three pointers", () => {
    const many = { data: { pointers: Array.from({ length: 6 }, (_, i) => ({ id: `i${i}`, headline: `Sentence ${i}.` })) } };
    expect(normaliseWorker(many).pointers).toHaveLength(3);
  });
  it("treats a week with no pointers as nothing standing out", () => {
    const q = normaliseWorker({ data: { pointers: [], status: "nothing_stands_out", message: "Fixed." } });
    expect(q.nothing_stands_out).toBe(true);
    expect(q.message).toBe("Fixed.");
  });
  it("drops a pointer without an id or a sentence, and an action without a place to go", () => {
    const q = normaliseWorker({ data: { pointers: [{ headline: "no id" }, { id: "a" }, { id: "b", headline: "ok", action: { label: "x" } }] } });
    expect(q.pointers.map((p) => p.id)).toEqual(["b"]);
    expect(q.pointers[0].action).toBeNull();
  });
  it("reads the reason and the sharing list", () => {
    const why = normaliseWhy(whyFx);
    expect(why.because.length).toBeGreaterThan(0);
    expect(why.limits.length).toBeGreaterThan(0);
    expect(why.sources[0].n).toBeNull();
    const sh = normaliseSharing(sharingFx);
    expect(sh.items.length).toBeGreaterThan(3);
    expect(sh.never.join(" ")).toMatch(/Screenshots/);
    expect(sh.preview).not.toBeNull();
  });
  it("shows an admin's exact view of the worker as lines, with no score and no rank", () => {
    const lines = previewLines(normaliseSharing(sharingFx).preview);
    const text = lines.map(([k, v]) => `${k}: ${v}`).join("\n");
    expect(lines.length).toBeGreaterThan(6);
    const shown = normaliseSharing(sharingFx).preview as { name?: string; label: string };
    expect(text).toContain(`Shown as: ${shown.name}`);
    expect(shown.name).toBeTruthy();
    expect(text).not.toContain(`Shown as: ${shown.label}`);
    expect(text).toMatch(/Help needed over time: (Improving|Cannot tell yet|Needs attention|Not enough data)/);
    expect(text).not.toMatch(/score|rank|best/i);
    expect(previewLines(null)).toEqual([]);
  });
});

describe("the admin's answers", () => {
  it("reads the overview: seven insights, coverage, risk, what was left out", () => {
    const o = normaliseOverview(overviewFx);
    expect(o.top).toHaveLength(7);
    expect(o.top.every((i) => i.drill && i.headline)).toBe(true);
    expect(o.coverage.users).toBe(60);
    expect(o.coverage.enough_data).toBe(57);
    expect(o.coverage.roles).toHaveLength(3);
    expect(o.risk?.open_approvals).toBe(3);
    expect(o.suppressed?.count).toBe(23);
    expect(o.role_comparison).toHaveLength(3);
    expect(o.top.find((i) => i.action?.to === "firm")?.action?.query).toBe("roles");
  });
  it("caps the overview at seven even when sent more", () => {
    const extra = { data: { top: Array.from({ length: 12 }, (_, i) => ({ id: `i${i}`, headline: `H${i}` })) } };
    expect(normaliseOverview(extra).top).toHaveLength(7);
  });
  it("reads role comparisons with intervals and the same scale", () => {
    const r = normaliseRoles(rolesFx);
    expect(r.roles.map((x) => x.role)).toEqual(["benefits-processor", "data-analyst", "programmer"]);
    expect(r.same_scale).toEqual({ min: 0, max: 1 });
    const bp = r.roles[0];
    const ind = bp.measures.find((m) => m.key === "independence");
    expect(ind?.expert?.ci).not.toBeNull();
    expect(bp.habits.length).toBeGreaterThan(2);
    expect(bp.habits[0].explains_s?.ci).not.toBeNull();
    expect(r.roles[2].enough).toBe(false);
  });
  it("reads the firm: sixty people in three roles, sorted by label by the engine, none with a score", () => {
    const f = normaliseFirm(firmFx);
    expect(f.roles.map((r) => r.users.length)).toEqual([30, 18, 12]);
    expect(f.privacy.min_group).toBe(5);
    expect(f.totals).toEqual({ users: 60, enough_data: 57 });
    const all = f.roles.flatMap((r) => r.users);
    expect(all).toHaveLength(60);
    expect(JSON.stringify(all)).not.toMatch(/"score"|"rank"/);
    expect(f.roles[0].trend?.cls).toBe("improving");
    expect(f.roles[0].users[0].skills.length).toBeGreaterThan(0);
  });
  it("reads the onboarding curves and the design target", () => {
    const o = normaliseOnboarding(onboardingFx);
    expect(o.target).toMatchObject({ value: 0.8, label: "design target" });
    expect(o.roles).toHaveLength(3);
    expect(o.roles[0].curve.length).toBeGreaterThan(5);
    expect(o.roles[0].km[0].n).not.toBeNull();
    expect(o.roles[0].median_to_target?.ci).not.toBeNull();
  });
  it("reads a drill-down, and folds the interval column into its figure", () => {
    const d = normaliseDrill(drillGapFx);
    expect(d.tables).toHaveLength(1);
    const t = drillTable(d.columns, d.rows);
    expect(t.heads.map((h) => h.key)).not.toContain("gap_ci");
    const gapCol = t.heads.findIndex((h) => h.key === "gap");
    expect(t.rows[0].cells[gapCol]).toMatch(/^\d+(\.\d)? s \(\d+(\.\d)? s to \d+(\.\d)? s\)$/);
    const tenure = drillTable(d.tables[0].columns, d.tables[0].rows);
    expect(tenure.heads.map((h) => h.key)).toEqual(["gap"]);
    expect(tenure.rows[0].cells[0]).toMatch(/\(.* to .*\)/);
    const s = normaliseDrill(drillTrendFx);
    expect(s.series[0].points.length).toBeGreaterThan(5);
    expect(s.series[0].points[0].lo).not.toBeNull();
  });
  it("turns unknown trend words into 'not enough data' and reads the older 'steady' as 'cannot tell yet'", () => {
    const f = (t: string) => normaliseFirm({ roles: [{ role: "r", users: [{ id: "u", trend: t }] }] }).roles[0].users[0].trend;
    expect(f("improving")).toBe("improving");
    expect(f("steady")).toBe("cannot_tell_yet");
    expect(f("cannot_tell_yet")).toBe("cannot_tell_yet");
    expect(f("weird")).toBe("not_enough_data");
    expect(TREND_LABEL.cannot_tell_yet).toBe("Cannot tell yet");
  });
});

describe("people are sorted by name or tenure, never ranked", () => {
  const people = [user("BP-10", { tenure_weeks: 3, trend: "needs_attention" }), user("BP-02", { tenure_weeks: 90, trend: "improving" }), user("BP-09", { tenure_weeks: 30, trend: "cannot_tell_yet" })];
  it("has only two sort keys and starts with name", () => {
    expect(SORT_KEYS).toEqual(["name", "tenure"]);
    expect(DEFAULT_SORT).toBe("name");
  });
  it("sorts by name in natural order, so BP-09 comes before BP-10", () => {
    expect(sortUsers(people).map((u) => u.label)).toEqual(["BP-02", "BP-09", "BP-10"]);
  });
  it("sorts by time in role, longest first", () => {
    expect(sortUsers(people, "tenure").map((u) => u.label)).toEqual(["BP-02", "BP-09", "BP-10"]);
    expect(sortUsers([user("A", { tenure_weeks: 5 }), user("B", { tenure_weeks: 5 })], "tenure").map((u) => u.label)).toEqual(["A", "B"]);
  });
  it("does not change the list it was given", () => {
    const before = people.map((u) => u.label);
    sortUsers(people, "tenure");
    expect(people.map((u) => u.label)).toEqual(before);
  });
  it("filters by a class of trend and counts classes", () => {
    expect(filterUsers(people, "needs_attention").map((u) => u.label)).toEqual(["BP-10"]);
    expect(filterUsers(people, null)).toHaveLength(3);
    expect(trendCounts(people)).toEqual({ improving: 1, cannot_tell_yet: 1, needs_attention: 1, not_enough_data: 0 });
  });
  it("sorts the real fixture's thirty benefits processors by the name shown, A to Z, without ranking by anything", () => {
    const bp = normaliseFirm(firmFx).roles[0].users;
    const sorted = sortUsers(bp);
    const shown = bp.map((u) => personName(u));
    expect(sorted.map((u) => personName(u))).toEqual([...shown].sort((a, b) => a.localeCompare(b, "en", { numeric: true, sensitivity: "base" })));
    expect(new Set(sorted.map((u) => u.label)).size).toBe(30);
  });
  it("shows a made-up name, keeps the label as the key, and falls back to the label when there is no name", () => {
    const all = normaliseFirm(firmFx).roles.flatMap((r) => r.users);
    expect(all.every((u) => !!u.name && u.name !== u.label)).toBe(true);
    expect(new Set(all.map((u) => u.name)).size).toBe(all.length);
    expect(new Set(all.map((u) => u.label)).size).toBe(all.length);
    expect(personName({ name: "Mei Tan", label: "BP-07" })).toBe("Mei Tan");
    expect(personName({ name: null, label: "BP-07" })).toBe("BP-07");
    expect(personName({ name: "  ", label: "BP-07" })).toBe("BP-07");
    expect(personName(null)).toBe("");
  });
  it("sorts by name when names are shown, and by label when they are not", () => {
    const named = [user("BP-01", { name: "Zofia Adler" }), user("BP-02", { name: "Amara Okafor" })];
    expect(sortUsers(named).map((u) => u.label)).toEqual(["BP-02", "BP-01"]);
    expect(sortUsers([user("BP-10"), user("BP-02")]).map((u) => u.label)).toEqual(["BP-02", "BP-10"]);
  });
});

describe("the privacy threshold for comparisons", () => {
  const role = (n: number, merged = false) => ({ role: "r", name: "R", merged, users: Array.from({ length: n }, (_, i) => user(`u${i}`)), aggregate: { n_users: n, independence: null, assisted_share: null, time_to_independence: { median: null, ci: null, unit: "occurrences", reached_share: null } } });
  it("shows a group figure from five people up, and never for a merged or smaller group", () => {
    expect(groupShown(role(5), 5)).toBe(true);
    expect(groupShown(role(4), 5)).toBe(false);
    expect(groupShown(role(30, true), 5)).toBe(false);
    expect(smallRoles([role(3), role(9)], 5)).toEqual(["R"]);
  });
  it("compares experts and juniors only when both groups reach the minimum", () => {
    expect(compareShown({ n_expert: 5, n_junior: 5, enough: true }, 5)).toBe(true);
    expect(compareShown({ n_expert: 4, n_junior: 20, enough: true }, 5)).toBe(false);
    expect(compareShown({ n_expert: 9, n_junior: 20, enough: false }, 5)).toBe(false);
  });
});

describe("curves", () => {
  const pts = [10, 20, 30, 40].map((x, i) => ({ x, y: 0.5 + i * 0.1, lo: 0.4 + i * 0.12, hi: 0.6 + i * 0.1, n: i === 3 ? 3 : 20 }));
  it("cuts points where fewer than five people remain", () => {
    expect(trimCurve(pts, 5).map((p) => p.x)).toEqual([10, 20, 30]);
  });
  it("finds where the lower bound reaches the target and stays there", () => {
    const c = [{ x: 1, y: 0.8, lo: 0.7, hi: 0.9, n: 9 }, { x: 2, y: 0.85, lo: 0.82, hi: 0.9, n: 9 }, { x: 3, y: 0.7, lo: 0.6, hi: 0.8, n: 9 }, { x: 4, y: 0.9, lo: 0.85, hi: 0.95, n: 9 }, { x: 5, y: 0.9, lo: 0.85, hi: 0.95, n: 9 }];
    expect(crossing(c, 0.8)).toBe(4);
    expect(crossing(c.slice(0, 3), 0.8)).toBeNull();
    expect(pct(0.8)).toBe("80%");
  });
});

describe("role gap words", () => {
  it("says it plainly and flags a gap that cannot be read", () => {
    const r = normaliseRoles(rolesFx).roles[0];
    const text = roleGapLine(r.measures.find((m) => m.key === "independence"), r.measures.find((m) => m.key === "time_vs_expert"));
    expect(text).toMatch(/^Juniors finish \d+ points fewer of their steps without help \(-\d+ to -\d+ points\)\./);
    expect(text).toMatch(/They take \d+(\.\d)? s \(\d+(\.\d)? s? ?to \d+(\.\d)?\) more per case\./);
    const vague = roleGapLine({ key: "independence", label: "x", unit: "share", expert: null, junior: null, gap: { value: -0.02, ci: [-0.1, 0.06] }, verdict: "cannot_tell" }, undefined);
    expect(vague).toMatch(/cannot tell yet/i);
    expect(roleGapLine(undefined, undefined)).toBe("");
  });
});
