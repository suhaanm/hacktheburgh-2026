import { describe, expect, it } from "vitest";
import { cleanRunsNeeded, nextRung, RUNGS, wilsonLower } from "./wilson";
import routinesFx from "../fixtures/routines.json";
import type { Routine } from "../types";

describe("wilsonLower", () => {
  it("matches the spec: 20 clean runs give about 0.84", () => {
    expect(wilsonLower(20, 20)).toBeCloseTo(0.839, 2);
  });
  it("A3 needs about 75 clean runs for 0.95", () => {
    expect(wilsonLower(75, 75)).toBeGreaterThanOrEqual(0.95);
    expect(wilsonLower(70, 70)).toBeLessThan(0.95);
  });
  it("is 0 with no runs and never above the observed rate", () => {
    expect(wilsonLower(0, 0)).toBe(0);
    expect(wilsonLower(13, 14)).toBeLessThan(13 / 14);
  });
  it("agrees with the fixture's reported bounds", () => {
    for (const r of (routinesFx as unknown as { data: Routine[] }).data) {
      if (r.shadow.runs > 0) expect(wilsonLower(r.shadow.matches, r.shadow.runs)).toBeCloseTo(r.shadow.wilson_lower, 1);
    }
  });
});

describe("rung ladder", () => {
  it("has four rungs, with A2 needing 0.80 and A3 0.95", () => {
    expect(RUNGS.map((r) => r.id)).toEqual(["A0", "A1", "A2", "A3"]);
    expect(RUNGS[2].bound).toBe(0.8);
    expect(RUNGS[3].bound).toBe(0.95);
    expect(nextRung("A3")).toBeNull();
    expect(nextRung("A1")?.id).toBe("A2");
  });
  it("counts the extra clean runs needed", () => {
    expect(cleanRunsNeeded(13, 14, 0.8)).toBe(11);
    expect(cleanRunsNeeded(25, 25, 0.8)).toBe(0);
  });
});
