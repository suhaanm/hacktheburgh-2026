import { describe, expect, it } from "vitest";
import { DAY_KEYS, dayKeys, normDays } from "./days";

describe("day keys", () => {
  it("reads the engine's strings and the screens' numbers alike", () => {
    expect(normDays(["mon", "tue", "sun"])).toEqual([0, 1, 6]);
    expect(normDays([6, 0, 0, 3])).toEqual([0, 3, 6]);
    expect(normDays(["Monday", "FRI"])).toEqual([0, 4]);
  });
  it("drops what it cannot read and survives missing input", () => {
    expect(normDays(["xyz", 9, -1])).toEqual([]);
    expect(normDays(undefined)).toEqual([]);
  });
  it("writes the engine's keys, in week order", () => {
    expect(dayKeys([4, 0, 1])).toEqual(["mon", "tue", "fri"]);
    expect(DAY_KEYS).toHaveLength(7);
  });
});
