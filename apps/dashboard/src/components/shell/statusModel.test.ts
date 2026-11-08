import { describe, expect, it } from "vitest";
import { STARTING_GIVE_UP_MS, statusFor, wordsOf } from "./statusModel";

describe("the status line", () => {
  it("says Live models when the engine answered and is not in mock mode", () => {
    expect(statusFor({ engineUp: true, mock: false, mode: "live" })).toEqual({ kind: "live", text: "Live models", dot: "solid", tone: "good" });
    expect(statusFor({ engineUp: true, mock: false, mode: "unknown" }).kind).toBe("live");
  });
  it("says only Connected when the engine runs without a key, and never what kind of data is drawn", () => {
    const s = statusFor({ engineUp: true, mock: true, mode: "live" });
    expect(s.text).toBe("Connected");
    expect(s.dot).toBe("ring");
    expect(statusFor({ engineUp: true, mock: true, mode: "demo" }).kind).toBe("connected");
  });
  it("says Connected, not a word about example rows, when some sources did not answer", () => {
    expect(statusFor({ engineUp: true, mock: false, mode: "mixed" })).toMatchObject({ kind: "connected", text: "Connected", dot: "ring" });
  });
  it("never says example, sample or stand-in in any state", () => {
    for (const engineUp of [true, false, null]) for (const mock of [true, false, null]) for (const mode of ["live", "mixed", "demo", "unknown"] as const) {
      expect(statusFor({ engineUp, mock, mode, waitedMs: 40_000 }).text).not.toMatch(/example|sample|stand[- ]in|made[- ]up/i);
    }
  });
  it("says Cannot reach the engine in red when /health failed", () => {
    expect(statusFor({ engineUp: false, mock: null, mode: "demo" })).toEqual({ kind: "down", text: "Cannot reach the engine", dot: "solid", tone: "bad" });
  });
  it("says Starting until the first answer, then gives up after 30 seconds and says what is wrong", () => {
    expect(statusFor({ engineUp: null, mock: null, mode: "unknown", waitedMs: 5000 }).kind).toBe("starting");
    expect(statusFor({ engineUp: null, mock: null, mode: "unknown", waitedMs: STARTING_GIVE_UP_MS }).kind).toBe("down");
  });
  it("never uses colour alone: every state has words and a ring or a solid dot, in at most four words", () => {
    for (const engineUp of [true, false, null]) for (const mock of [true, false, null]) for (const mode of ["live", "mixed", "demo", "unknown"] as const) {
      const s = statusFor({ engineUp, mock, mode });
      expect(s.text.length).toBeGreaterThan(0);
      expect(["solid", "ring"]).toContain(s.dot);
      expect(wordsOf(s.text), s.text).toBeLessThanOrEqual(4);
    }
  });
});
