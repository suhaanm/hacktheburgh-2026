import { describe, expect, it } from "vitest";
import presenceFx from "../fixtures/presence.json";
import type { Presence } from "../types";
import { busiestWrap, idleCapacity, inQuiet, isWide, meanRow, parseClock, quantize, quietSegments, slotLabel, toGrid } from "./heatmap";

const p = (presenceFx as unknown as { data: Presence }).data;

describe("presence helpers", () => {
  it("quantizes into the five token classes", () => {
    expect([0.02, 0.1, 0.29, 0.3, 0.6, 0.75, 1].map(quantize)).toEqual([0, 1, 1, 2, 3, 4, 4]);
  });
  it("builds a 7 by 96 grid with every bin", () => {
    const grid = toGrid(p.bins);
    expect(grid).toHaveLength(7);
    expect(grid.every((row) => row.length === 96 && row.every(Boolean))).toBe(true);
  });
  it("flags wide intervals", () => {
    expect(isWide({ lo: 0.1, hi: 0.6 })).toBe(true);
    expect(isWide({ lo: 0.4, hi: 0.7 })).toBe(false);
  });
  it("parses clock times", () => {
    expect(parseClock("06:30")).toBe(26);
    expect(Number.isNaN(parseClock("25:00"))).toBe(true);
    expect(Number.isNaN(parseClock("nope"))).toBe(true);
  });
  it("splits a quiet window that crosses midnight into two segments", () => {
    expect(quietSegments({ start: "22:00", end: "06:00", days: [0] }, 0)).toEqual([[88, 96], [0, 24]]);
    expect(quietSegments({ start: "22:00", end: "06:00", days: [0] }, 1)).toEqual([]);
    expect(quietSegments({ start: "03:00", end: "10:00", days: [2] }, 2)).toEqual([[12, 40]]);
    expect(inQuiet({ start: "22:00", end: "06:00", days: [0] }, 0, 2)).toBe(true);
    expect(inQuiet({ start: "22:00", end: "06:00", days: [0] }, 0, 50)).toBe(false);
  });
  it("finds the night owl's busiest stretch across midnight, ending after 24:00", () => {
    const [a, b] = busiestWrap(meanRow(toGrid(p.bins)), 0.5)!;
    expect(a / 4).toBeGreaterThan(18);
    expect(a / 4).toBeLessThan(22);
    expect(b).toBeGreaterThan(96);
    expect(slotLabel(b)).toMatch(/^0[0-3]:/);
  });
  it("matches the planted schedule: busy late evening, empty small hours of the morning", () => {
    const grid = toGrid(p.bins);
    expect(grid[1][88]!.p).toBeGreaterThan(0.6);
    expect(grid[1][24]!.p).toBeLessThan(0.15);
  });
  it("recomputes idle capacity when quiet hours change, with a positive interval", () => {
    const base = idleCapacity(p.bins, p.quiet_hours);
    const none = idleCapacity(p.bins, { start: "00:00", end: "01:00", days: [] });
    expect(none.mean).toBeGreaterThan(base.mean);
    expect(base.lo).toBeLessThan(base.mean);
    expect(base.hi).toBeGreaterThan(base.mean);
  });
});
