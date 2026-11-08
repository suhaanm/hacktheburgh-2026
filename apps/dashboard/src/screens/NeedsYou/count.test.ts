// The sidebar badge counts the worker's OWN briefing and runs: when the shell has not read the identity yet, the count asks the engine who the worker is
// before it reads anything (QA-worker defect Q1-03: it read the sample person's briefing, so the badge said 7 while Needs you listed 2).
import { beforeEach, describe, expect, it, vi } from "vitest";

const calls: string[] = [];
let state: { person: string | null } = { person: null };
let identity: { person: string } | null = { person: "p_me" };

vi.mock("../../store", () => ({ getState: () => state, setState: (p: Partial<typeof state>) => { state = { ...state, ...p }; } }));
vi.mock("../../api", () => {
  const ok = (data: unknown) => Promise.resolve({ data, meta: null, source: "live" as const });
  return {
    api: {
      identity: () => (identity ? Promise.resolve(identity) : Promise.reject(new Error("offline"))),
      queue: () => ok([]),
      routines: () => ok([]),
      briefing: (person: string) => { calls.push(`briefing:${person}`); return ok({ generated_at: "2026-11-08T00:00:00Z", cards: [] }); },
      agentsRuns: (person?: string) => { calls.push(`runs:${person}`); return ok([]); },
      tasks: () => ok([]),
    },
  };
});

import { loadNeedsCount } from "./count";

beforeEach(() => { calls.length = 0; state = { person: null }; identity = { person: "p_me" }; });

describe("whose briefing the badge counts", () => {
  it("asks the engine who the worker is when the shell has not read it yet, and never reads the sample person's briefing", async () => {
    await loadNeedsCount();
    expect(calls).toContain("briefing:p_me");
    expect(calls).toContain("runs:p_me");
    expect(calls.some((c) => c.includes("p_ninetofive"))).toBe(false);
  });

  it("uses the person the shell already read, without asking again", async () => {
    state = { person: "p_known" };
    identity = null; // would reject: the shell's own copy must be enough
    await loadNeedsCount();
    expect(calls).toContain("briefing:p_known");
  });

  it("falls back to the sample person only when the engine names nobody", async () => {
    identity = null;
    await loadNeedsCount();
    expect(calls).toContain("briefing:p_ninetofive");
  });
});
