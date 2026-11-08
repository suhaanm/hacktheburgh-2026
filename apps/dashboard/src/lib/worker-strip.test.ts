import { describe, expect, it } from "vitest";
import { aboutPeople, ownMeta } from "./ownMeta";
import { oneExpert } from "./voice";
import { caseSecondsLost, stepsHeadline, topLosses } from "./steps";
import { describeColumn, type RibbonColumn } from "./ribbon";
import { commitsHeadline } from "../components/growth/CommitsSection";
import type { AnalyticMeta, GitHabit } from "../types";

// The worker's screens draw the worker's own data and ONE experienced worker's way of doing the task (docs/knack-ux/views.md).
// These tests pin the pure words and numbers behind that: no count of people, no group of experts, no non-finite number on screen.

const col = (over: Partial<RibbonColumn> = {}): RibbonColumn => ({
  index: 0, x: 0, w: 10, span: 10, saved: 0, lost: 0, missing: null,
  expert: { cog: "OPEN_CASE", x: 0, w: 10, seconds: 20 }, novice: { cog: "OPEN_CASE", x: 0, w: 10, seconds: 20 }, ...over,
} as RibbonColumn);

describe("ownMeta: the n of a group is swapped for what the screen draws", () => {
  const m = (unit: string, extra: Partial<AnalyticMeta> = {}): AnalyticMeta => ({ origin: "real", n: 24, n_unit: unit, split: null, interval_level: 0.95, note: null, generated_at: "", ...extra });
  it("a unit about people becomes one case and the split is dropped", () => {
    const r = ownMeta(m("people", { split: "held-out people" }), { n: 1, unit: "case" })!;
    expect(r.n).toBe(1);
    expect(r.n_unit).toBe("case");
    expect(r.split).toBeNull();
  });
  it("covers learners, workers, experts, novices, personas and colleagues", () => {
    for (const u of ["learners", "workers", "experts", "novices", "personas", "colleagues", "participants"]) expect(aboutPeople(u)).toBe(true);
  });
  it("a unit that is not about people passes through unchanged", () => {
    const a = m("weeks");
    expect(ownMeta(a, { n: 1, unit: "week" })).toBe(a);
  });
  it("a split that names people is dropped even when the unit is fine", () => {
    expect(ownMeta(m("commits", { split: "people held out" }), { n: 5, unit: "commit" })!.split).toBeNull();
  });
  it("a note that describes the group is dropped; a note that does not stays", () => {
    expect(ownMeta(m("days", { note: "1 expert reference, 4 novices, 9 episodes each. The mean over all novice cases." }), { n: 1, unit: "week" })!.note).toBeNull();
    expect(ownMeta(m("people", { note: "The mean over all novices." }), { n: 1, unit: "case" })!.note).toBeNull();
    expect(ownMeta(m("days", { note: "Times are in London." }), { n: 1, unit: "week" })!.note).toBe("Times are in London.");
  });
  it("null stays null; several own units are plural", () => {
    expect(ownMeta(null, { n: 1, unit: "case" })).toBeNull();
    expect(ownMeta(m("people"), { n: 3, unit: "week" })!.n_unit).toBe("weeks");
  });
});

describe("oneExpert: the group of experts becomes one experienced worker", () => {
  it("turns the plural into the singular baseline, keeping a capital at a sentence start", () => {
    expect(oneExpert("more often than the experts")).toBe("more often than an experienced worker");
    expect(oneExpert("The experts' share is 3%.")).toBe("An experienced worker's share is 3%.");
    expect(oneExpert("the reference experts' share is 3%")).toBe("an experienced worker's share is 3%");
    expect(oneExpert("Experts commit smaller changes.")).toBe("An experienced worker commit smaller changes.");
  });
  it("is idempotent and leaves other text alone", () => {
    const t = "about the same as an experienced worker";
    expect(oneExpert(t)).toBe(t);
    expect(oneExpert(oneExpert("than the experts"))).toBe("than an experienced worker");
    expect(oneExpert("12 of 40 commits")).toBe("12 of 40 commits");
  });
});

describe("stepsHeadline: one sentence about one case against one experienced worker", () => {
  it("no columns: it says so in words", () => {
    expect(stepsHeadline(undefined, [])).toMatch(/appear here once Knack has seen you/);
  });
  it("no time lost: the steps matched", () => {
    expect(stepsHeadline(0, [col()])).toMatch(/matched an experienced worker's/);
    expect(stepsHeadline(-30, [col()])).toMatch(/matched/);
  });
  it("names the biggest loss and never says expert in the plural or counts anybody", () => {
    const cols = [col({ lost: 10 }), col({ index: 1, lost: 58, expert: { cog: "REVERT", x: 0, w: 1, seconds: 5 } as never }), col({ index: 2, lost: 30 })];
    const s = stepsHeadline(undefined, cols);
    expect(s).toBe("You took 1 min 38 s longer than an experienced worker, mostly at revert.");
    expect(s).not.toMatch(/experts|people|learners|\d+ of/);
  });
  it("uses the engine's own figure for the case when it sends one, and ignores NaN", () => {
    expect(caseSecondsLost(120, [col({ lost: 5 })])).toBe(120);
    expect(caseSecondsLost(Number.NaN, [col({ lost: 7 }), col({ lost: Number.NaN })])).toBe(7);
    expect(caseSecondsLost("12", [col({ lost: 4 })])).toBe(4);
  });
  it("lists only columns that lost time, biggest first, at most four", () => {
    const cols = [1, 0, 9, 4, 7, 3].map((l, i) => col({ index: i, lost: l, expert: { cog: `S${i}`, x: 0, w: 1, seconds: 1 } as never }));
    expect(topLosses(cols).map((t) => t.seconds)).toEqual([9, 7, 4, 3]);
    expect(topLosses([col({ lost: Number.NaN })])).toEqual([]);
  });
  it("a step only the worker did is named from the worker's side and counts as lost", () => {
    const only = col({ lost: 40, expert: null, novice: { cog: "SEARCH", x: 0, w: 1, seconds: 40 } as never });
    expect(topLosses([only])[0]).toMatchObject({ cog: "SEARCH", skipped: false });
  });
});

describe("describeColumn in the worker's voice", () => {
  it("says you and the experienced worker, never novice or expert", () => {
    const both = describeColumn(col({ lost: 12, novice: { cog: "SEARCH", x: 0, w: 1, seconds: 32 } as never }), 0, 4, "you");
    expect(both).toMatch(/The experienced worker did open case, you did search/);
    expect(both).not.toMatch(/novice|Expert /);
    const skipped = describeColumn(col({ novice: null, saved: 20 }), 1, 4, "you");
    expect(skipped).toMatch(/Only the experienced worker did this/);
    expect(skipped).toMatch(/You skipped it/);
    const mine = describeColumn(col({ expert: null, lost: 8 }), 2, 4, "you");
    expect(mine).toMatch(/Only you did this/);
  });
  it("the group's wording is unchanged for the places that still use it", () => {
    expect(describeColumn(col({ novice: null, saved: 38, lost: 0 }), 7, 12)).toMatch(/novice skipped it/);
  });
});

describe("commitsHeadline", () => {
  const h = (flagged: boolean): GitHabit => ({ id: String(Math.random()), label: "x", flagged } as unknown as GitHabit);
  it("says nothing to compare yet, none, one and several in the worker's words", () => {
    expect(commitsHeadline([])).toMatch(/appear here once a repository is registered/);
    expect(commitsHeadline([h(false)])).toBe("No commit habit of yours stands out from an experienced worker's.");
    expect(commitsHeadline([h(true), h(false)])).toBe("One of your commit habits differs clearly from an experienced worker's.");
    expect(commitsHeadline([h(true), h(true), h(true)])).toBe("3 of your commit habits differ clearly from an experienced worker's.");
  });
});
