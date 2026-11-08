import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { COHORT_RULES, breaksCohortRule, cohortHits } from "./cohortRules";

describe("the cohort rule", () => {
  it("flags an average over other people, a count of people, a ranking, the firm and another person's id", () => {
    for (const bad of [
      "Novices lose about 4 min per case. Average over all novices.",
      "Median across everyone is 12 s",
      "Typical for your colleagues",
      "12 colleagues finish this without help",
      "57 people have enough data",
      "Across the firm, juniors take longer",
      "Firm-wide, the gap is 20 s",
      "You are in the top 10% of learners",
      "Ranked #3 this week",
      "Better than 80% of staff",
      "BP-07 took 5 min",
      "Compare with p_expert_01",
      "Most learners skip this step",
      "A leaderboard of the week",
      "Ask a teammate",
    ]) expect(breaksCohortRule(bad), bad).toBe(true);
  });

  it("lets through the worker's own work and one experienced worker's way", () => {
    for (const ok of [
      "About 35 seconds longer than an experienced worker.",
      "The cliff check: 3 of 5 cases without help.",
      "Your week of 9 November",
      "Meeting, 5 to 9 people",
      "Call with 6 people on Tuesday",
      "p_stuck is not an id",
      "Steps against one experienced worker's way of doing the task",
      "",
    ]) expect(breaksCohortRule(ok), ok).toBe(false);
  });

  it("never flags the worker's own id, and flags every other", () => {
    expect(breaksCohortRule("Your record p_learn01", "p_learn01")).toBe(false);
    expect(breaksCohortRule("Your record p_learn01", "P_LEARN01")).toBe(false);
    expect(breaksCohortRule("Your record p_learn01 and p_exp06", "p_learn01")).toBe(true);
    expect(cohortHits("p_nightowl p_f_bp03")[0].rule).toBe("person-id");
  });

  it("copes with anything a screen might hold: not a string, empty, very long, regex characters", () => {
    for (const odd of [null, undefined, 5, {}, [], "", "(((", "[a-", "\\", "x".repeat(200_000)]) expect(() => cohortHits(odd as never), String(odd).slice(0, 8)).not.toThrow();
    expect(cohortHits(undefined)).toEqual([]);
    expect(cohortHits("BP-01 ".repeat(500)).length).toBeLessThanOrEqual(20);
  });

  it("names the rule and the reason for each hit, so a hidden section can say what it was", () => {
    const h = cohortHits("Average over all novices.")[0];
    expect(h).toMatchObject({ rule: "cohort-figure", match: "Average over all" });
    expect(h.why).toMatch(/average/);
  });

  it("is the same rule as Track R's view audit, when that file is present in this tree", async () => {
    const file = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..", "scripts", "lib", "view-rules.mjs");
    if (!existsSync(file)) return; // the audit is merged by the lead; until then this tree has no copy to compare with
    const mod = (await import(/* @vite-ignore */ pathToFileURL(file).href)) as { FIRM_RULES: { id: string; re: RegExp }[] };
    const theirs = new Set(mod.FIRM_RULES.map((r) => `${r.id}|${r.re.source}`));
    for (const r of COHORT_RULES) expect(theirs.has(`${r.id}|${r.re.source}`), `${r.id}: ${r.re.source.slice(0, 50)}`).toBe(true);
    for (const r of mod.FIRM_RULES) expect(COHORT_RULES.some((x) => x.id === r.id && x.re.source === r.re.source), `${r.id}: ${r.re.source.slice(0, 50)}`).toBe(true);
  });
});
