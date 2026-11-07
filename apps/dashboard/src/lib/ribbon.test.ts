import { describe, expect, it } from "vitest";
import genomeFx from "../fixtures/genome.json";
import type { Genome } from "../types";
import { connectorPath, describeColumn, layoutRibbon } from "./ribbon";

const genome = (genomeFx as unknown as { data: Genome }).data;

describe("layoutRibbon", () => {
  const layout = layoutRibbon(genome, 1000);
  it("fills the requested width", () => {
    expect(layout.width).toBeCloseTo(1000, 0);
  });
  it("makes a column per alignment entry, in order and without overlap", () => {
    expect(layout.columns).toHaveLength(genome.alignment.length);
    for (let i = 1; i < layout.columns.length; i++) {
      expect(layout.columns[i].x).toBeGreaterThanOrEqual(layout.columns[i - 1].x + layout.columns[i - 1].w);
    }
  });
  it("detects gaps from null indices, not from op names", () => {
    const missing = layout.columns.filter((c) => c.missing === "novice");
    expect(missing).toHaveLength(1);
    expect(missing[0].expert?.cog).toBe("CHECK_CLIFF");
    expect(missing[0].novice).toBeNull();
    const extras = layout.columns.filter((c) => c.missing === "expert").map((c) => c.novice?.cog);
    expect(extras).toEqual(["SEARCH", "IDLE", "REVERT"]);
  });
  it("sums seconds lost to the total in the genome", () => {
    expect(layout.totalLost).toBeCloseTo(genome.total_gap_s, 5);
    expect(layout.maxLost).toBe(58);
  });
  it("sizes the longer block to the whole column and the other in proportion", () => {
    const c = layout.columns.find((x) => x.expert?.cog === "OPEN_CALCULATOR")!;
    expect(c.novice!.w).toBeCloseTo(c.w, 5);
    expect(c.expert!.w / c.w).toBeCloseTo(22 / 31, 5);
  });
  it("keeps short columns at the minimum width", () => {
    const narrow = layoutRibbon(genome, 420, 2, 20);
    expect(Math.min(...narrow.columns.map((c) => c.w))).toBeGreaterThanOrEqual(20 - 1e-9);
    expect(narrow.width).toBeCloseTo(420, 0);
  });
  it("joins matched columns only", () => {
    const matched = layout.columns.find((c) => c.expert && c.novice)!;
    expect(connectorPath(matched, 0, 50)).toMatch(/^M/);
    expect(connectorPath(layout.columns.find((c) => c.missing)!, 0, 50)).toBeNull();
  });
  it("describes a skipped step in plain words", () => {
    const c = layout.columns.find((x) => x.missing === "novice")!;
    expect(describeColumn(c, 7, 12)).toMatch(/novice skipped it/);
  });
});
