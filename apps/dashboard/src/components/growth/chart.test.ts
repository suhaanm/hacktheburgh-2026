import { describe, expect, it } from "vitest";
import { Y_TICKS, frameFor, nearestIndex, xScale, xTicks, yScale } from "./chart";

describe("chart scales", () => {
  it("uses one 0 to 100% axis whatever the data", () => {
    const f = frameFor(900);
    const y = yScale(f);
    expect(y(0)).toBe(f.top + f.plotH);
    expect(y(1)).toBe(f.top);
    expect(Y_TICKS[0]).toBe(0);
    expect(Y_TICKS[Y_TICKS.length - 1]).toBe(1);
  });
  it("puts occurrence 0 at the left edge and the last occurrence at the right edge", () => {
    const f = frameFor(900);
    const x = xScale(150, f);
    expect(x(0)).toBe(f.left);
    expect(x(150)).toBe(900 - f.right);
  });
  it("goes compact on a phone and leaves room for the last value", () => {
    expect(frameFor(358).compact).toBe(true);
    expect(frameFor(900).compact).toBe(false);
    expect(frameFor(900).right).toBeGreaterThan(40);
  });
  it("never ticks past the last occurrence", () => {
    const t = xTicks(150, 8);
    expect(Math.max(...t)).toBeLessThanOrEqual(150);
    expect(t[0]).toBe(0);
    expect(xTicks(7, 4).every((v) => v <= 7)).toBe(true);
  });
  it("finds the nearest point", () => {
    const xs = [10, 20, 30, 40];
    expect(nearestIndex(xs, 0)).toBe(0);
    expect(nearestIndex(xs, 24)).toBe(1);
    expect(nearestIndex(xs, 26)).toBe(2);
    expect(nearestIndex(xs, 999)).toBe(3);
    expect(nearestIndex([], 5)).toBe(-1);
  });
});
