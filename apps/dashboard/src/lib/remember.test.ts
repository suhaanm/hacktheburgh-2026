// The remembered choices of the insight screens: a fixed list of words, a safe fallback, storage that may be missing or throw.
import { describe, expect, it } from "vitest";
import { REMEMBER_PREFIX, readRemembered, readRememberedFree, writeRemembered, writeRememberedFree, type KeyValueStorage } from "./remember";

const fake = (): KeyValueStorage & { map: Map<string, string> } => {
  const map = new Map<string, string>();
  return { map, getItem: (k) => map.get(k) ?? null, setItem: (k, v) => void map.set(k, v), removeItem: (k) => void map.delete(k) };
};
const broken: KeyValueStorage = {
  getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); },
};
const VIEWS = ["ribbon", "graph"] as const;

describe("remembered choices", () => {
  it("starts from the default and from nothing", () => {
    expect(readRemembered("genome-view", VIEWS, "ribbon", fake())).toBe("ribbon");
    expect(readRemembered("genome-view", VIEWS, "ribbon", null)).toBe("ribbon");
  });

  it("reads back what was written, under a key that keeps the internal prefix", () => {
    const s = fake();
    expect(writeRemembered("genome-view", "graph", "ribbon", s)).toBe(true);
    expect(s.map.get(`${REMEMBER_PREFIX}genome-view`)).toBe("graph");
    expect(readRemembered("genome-view", VIEWS, "ribbon", s)).toBe("graph");
  });

  it("writing the default leaves nothing behind", () => {
    const s = fake();
    writeRemembered("genome-view", "graph", "ribbon", s);
    writeRemembered("genome-view", "ribbon", "ribbon", s);
    expect(s.map.size).toBe(0);
  });

  it("ignores a value that is not in the list (an old or edited value cannot put a screen in a state it cannot draw)", () => {
    const s = fake();
    s.map.set(`${REMEMBER_PREFIX}genome-view`, "<script>");
    expect(readRemembered("genome-view", VIEWS, "ribbon", s)).toBe("ribbon");
  });

  it("falls back when storage throws, and says it could not store", () => {
    expect(readRemembered("genome-view", VIEWS, "ribbon", broken)).toBe("ribbon");
    expect(writeRemembered("genome-view", "graph", "ribbon", broken)).toBe(false);
    expect(readRememberedFree("week-person", broken)).toBeNull();
    expect(writeRememberedFree("week-person", "p_1", broken)).toBe(false);
  });

  it("a free choice (a person, a week) is short and plain: nothing typed by the worker, no markup", () => {
    const s = fake();
    expect(writeRememberedFree("week-person", "p_nov13", s)).toBe(true);
    expect(readRememberedFree("week-person", s)).toBe("p_nov13");
    expect(writeRememberedFree("week-person", "<b>x</b>", s)).toBe(false);
    expect(writeRememberedFree("week-person", "x".repeat(65), s)).toBe(false);
    expect(writeRememberedFree("week-person", null, s)).toBe(true);
    expect(readRememberedFree("week-person", s)).toBeNull();
  });
});
