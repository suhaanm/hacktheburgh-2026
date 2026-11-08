import { describe, expect, it } from "vitest";
import { wrapLabel } from "./DotWhisker";

describe("wrapLabel", () => {
  it("leaves a label that fits alone", () => {
    expect(wrapLabel("Skips the cliff check (injected 66 s)", 40)).toEqual(["Skips the cliff check (injected 66 s)"]);
  });
  it("breaks a long label at the space nearest the middle, losing no word", () => {
    const l = "Reads the result again and again (injected 33 s)";
    const out = wrapLabel(l, 34);
    expect(out).toHaveLength(2);
    expect(out.join(" ")).toBe(l);
    expect(Math.abs(out[0].length - out[1].length)).toBeLessThan(l.length / 2);
  });
  it("does not break a long word with no space", () => {
    expect(wrapLabel("x".repeat(60), 34)).toEqual(["x".repeat(60)]);
  });
});
