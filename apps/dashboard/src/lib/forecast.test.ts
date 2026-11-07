import { describe, expect, it } from "vitest";
import presenceFx from "../fixtures/presence.json";
import type { Presence } from "../types";
import { decideLocal, longestWindow, survivalAt, threshold } from "./forecast";

const p = (presenceFx as unknown as { data: Presence }).data;

describe("window forecast", () => {
  it("uses the critical-fractile threshold L / (G + L)", () => {
    expect(threshold(3, 2)).toBeCloseTo(0.4, 6);
  });
  it("is non-increasing in run length", () => {
    for (let i = 1; i < p.forecast.length; i++) expect(p.forecast[i].survival).toBeLessThanOrEqual(p.forecast[i - 1].survival);
  });
  it("interpolates between points", () => {
    const mid = survivalAt(p.forecast, 15);
    expect(mid).toBeLessThan(survivalAt(p.forecast, 10));
    expect(mid).toBeGreaterThan(survivalAt(p.forecast, 20));
  });
  it("goes for short runs and waits for long ones", () => {
    expect(decideLocal(p.forecast, p.decision_threshold, 30).go).toBe(true);
    expect(decideLocal(p.forecast, p.decision_threshold, 300).go).toBe(false);
  });
  it("finds the longest run that clears the threshold, and it is consistent with decide", () => {
    const best = longestWindow(p.forecast, p.decision_threshold);
    expect(decideLocal(p.forecast, p.decision_threshold, best - 3).go).toBe(true);
    expect(decideLocal(p.forecast, p.decision_threshold, best + 12).go).toBe(false);
  });
});
