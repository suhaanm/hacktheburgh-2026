import { describe, expect, it } from "vitest";
import genomeFx from "../fixtures/genome.json";
import type { Genome } from "../types";
import { layoutWaterfall } from "./waterfall";

const g = (genomeFx as unknown as { data: Genome }).data;

describe("layoutWaterfall", () => {
  const { rows, total, max } = layoutWaterfall(g.waterfall, g.total_gap_ci);
  it("orders biggest first and puts the catch-all last before the total", () => {
    const steps = rows.slice(0, -1);
    expect(steps[0].label).toMatch(/cliff/i);
    expect(steps[steps.length - 1].label).toMatch(/small/i);
    for (let i = 1; i < steps.length - 1; i++) expect(steps[i - 1].seconds).toBeGreaterThanOrEqual(steps[i].seconds);
  });
  it("floats each bar from where the last one ended and ends at the total", () => {
    const steps = rows.slice(0, -1);
    for (let i = 1; i < steps.length; i++) expect(steps[i].start).toBeCloseTo(steps[i - 1].end, 6);
    expect(steps[steps.length - 1].end).toBeCloseTo(total, 6);
    expect(total).toBe(g.total_gap_s);
  });
  it("puts the whisker around the end of the bar, using the step's own interval", () => {
    const first = rows[0];
    expect(first.whisker[0]).toBeCloseTo(first.end - (first.seconds - first.ci[0]), 6);
    expect(first.whisker[1]).toBeCloseTo(first.end + (first.ci[1] - first.seconds), 6);
  });
  it("closes with a total row that carries the total interval and sets the scale", () => {
    const last = rows[rows.length - 1];
    expect(last.total).toBe(true);
    expect(last.ci).toEqual(g.total_gap_ci);
    expect(max).toBeGreaterThanOrEqual(g.total_gap_ci[1]);
  });
});
