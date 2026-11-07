import { describe, expect, it } from "vitest";
import gitFx from "../fixtures/git-habits.json";
import type { GitHabit, GitHabits } from "../types";
import { excludesZero, fmtPoints, fmtPointsInterval, fmtShare, gitHeadline, habitAxis, learnerLabel, readHabit, sortHabits } from "./git";

const habits = (gitFx as unknown as { data: GitHabits }).data.habits;

describe("git habits", () => {
  it("labels learners and leaves other ids alone", () => {
    expect(learnerLabel("p_git_learner_3")).toBe("Learner 3");
    expect(learnerLabel("p_someone")).toBe("p_someone");
  });
  it("prints shares and differences with a real minus sign", () => {
    expect(fmtShare(0.2205)).toBe("22%");
    expect(fmtShare(0.0021)).toBe("0.2%");
    expect(fmtPoints(0.1923)).toBe("+19 pp");
    expect(fmtPoints(-0.5979)).toBe("−60 pp");
    expect(fmtPoints(0.001)).toBe("0 pp");
    expect(fmtPointsInterval([-0.6962, -0.5007])).toBe("[−70, −50] pp");
  });
  it("reads a flagged habit that points the bad way as worse", () => {
    const big = habits.find((h) => h.id === "big_commits")!;
    const r = readHabit(big);
    expect(r.flagged).toBe(true);
    expect(r.direction).toBe("worse");
    expect(r.words).toContain("more often");
    const tests = readHabit(habits.find((h) => h.id === "tests_with_changes")!);
    expect(tests.direction).toBe("worse"); // lower is worse for this one
    expect(tests.words).toContain("less often");
  });
  it("explains why an unflagged habit was left alone", () => {
    const quiet = habits.find((h) => !h.flagged)!;
    const r = readHabit(quiet);
    expect(r.flagged).toBe(false);
    expect(r.state).toMatch(/floor|noise|small/i);
  });
  it("says a difference whose interval spans zero could be noise", () => {
    const h = { delta: 0.02, ci: [-0.03, 0.07] as [number, number], flagged: false, reason: "ci_includes_zero" } as GitHabit;
    expect(excludesZero(h.ci)).toBe(false);
    expect(readHabit(h).state).toBe("Could be noise");
  });
  it("puts flagged habits first and keeps the axis wide enough for every interval", () => {
    const s = sortHabits(habits);
    expect(s[0].flagged).toBe(true);
    expect(s.findIndex((h) => !h.flagged)).toBeGreaterThanOrEqual(s.filter((h) => h.flagged).length - 0);
    const ax = habitAxis(habits);
    for (const h of habits) { expect(Math.abs(h.ci[0])).toBeLessThanOrEqual(ax); expect(Math.abs(h.ci[1])).toBeLessThanOrEqual(ax); }
  });
  it("writes a headline from the flagged count", () => {
    expect(gitHeadline(habits)).toMatch(/differ/);
    expect(gitHeadline([])).toMatch(/No commit habits/);
    expect(gitHeadline(habits.map((h) => ({ ...h, flagged: false })))).toBe("No commit habit stands out from the experts");
  });
});
