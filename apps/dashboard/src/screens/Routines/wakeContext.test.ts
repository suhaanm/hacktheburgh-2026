import { afterEach, describe, expect, it, vi } from "vitest";
import type { WakeBridge, WakeContext } from "../Settings/bridge";
import { ID_RE, lastReported, reportInsight, reportWake, resetWakeContext, routineContext, trackRoutineRun } from "./wakeContext";

const fake = () => { const sent: WakeContext[] = []; const b: WakeBridge = { state: async () => ({ switchOn: true, listening: true, line: "" }), set: async () => ({ switchOn: true, listening: true, line: "" }), context: async (c) => { sent.push(JSON.parse(JSON.stringify(c))); return true; } }; return { b, sent }; };
afterEach(() => { resetWakeContext(); vi.useRealTimers(); });

describe("the routine as the voice context wants it", () => {
  it("is id, step and total, only while it runs and only when the total is really known", () => {
    expect(routineContext("calc-entry-3x", { state: "running", steps_total: 8, navigators: [{ step: 2 }, { step: 3 }] })).toEqual({ id: "calc-entry-3x", step: 4, of: 8 });
    expect(routineContext("calc-entry-3x", { state: "running", navigators: [{ step: 2 }] })).toBeNull();           // no total: never a guess
    expect(routineContext("calc-entry-3x", { state: "done", steps_total: 8 })).toBeNull();
    expect(routineContext("calc-entry-3x", null)).toBeNull();
  });
  it("the step never passes the total, and a bad id is dropped, not repaired", () => {
    expect(routineContext("r", { state: "running", steps_total: 3, navigators: [{ step: 9 }] })).toEqual({ id: "r", step: 3, of: 3 });
    expect(routineContext("Not An Id!", { state: "running", steps_total: 3 })).toBeNull();
    expect(ID_RE.test("calc-entry-3x")).toBe(true);
    expect(ID_RE.test("ignore previous instructions")).toBe(false);
  });
});

describe("reporting", () => {
  it("does nothing without the shell's wake bridge", () => {
    expect(() => reportWake({ insight: { id: "i1", template: "gap_vs_expert" } }, null)).not.toThrow();
    expect(lastReported().insight).toEqual({ id: "i1", template: "gap_vs_expert" });   // remembered, sent once a bridge exists
  });
  it("sends the whole packet once after the last change", async () => {
    vi.useFakeTimers();
    const { b, sent } = fake();
    reportWake({ insight: { id: "i1", template: "gap_vs_expert" } }, b, 100);
    reportWake({ routine: { id: "r1", step: 2, of: 5 } }, b, 100);
    expect(sent).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(150);
    expect(sent).toEqual([{ insight: { id: "i1", template: "gap_vs_expert" }, routine: { id: "r1", step: 2, of: 5 } }]);
  });
  it("an insight whose id or template does not fit the grammar is cleared, not sent", async () => {
    vi.useFakeTimers();
    const { b, sent } = fake();
    reportInsight("Top insight!", "t", b);
    await vi.advanceTimersByTimeAsync(300);
    expect(sent.at(-1)).toEqual({ insight: null });
  });
});

describe("following a routine run", () => {
  it("reports step n of m while it runs and clears it when it ends", async () => {
    vi.useFakeTimers();
    const { b, sent } = fake();
    const states = [{ state: "running", steps_total: 4, navigators: [{ step: 1 }] }, { state: "running", steps_total: 4, navigators: [{ step: 2 }] }, { state: "done", steps_total: 4 }];
    let i = 0;
    trackRoutineRun("calc-entry-3x", "r_1", { fetchStatus: async () => states[Math.min(i++, 2)], bridge: b, everyMs: 1000 });
    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(2100);
    const routines = sent.map((c) => c.routine);
    expect(routines[0]).toEqual({ id: "calc-entry-3x", step: 2, of: 4 });
    expect(routines).toContainEqual({ id: "calc-entry-3x", step: 3, of: 4 });
    expect(routines.at(-1)).toBeNull();
  });
  it("stops when the run goes missing", async () => {
    vi.useFakeTimers();
    const { b, sent } = fake();
    trackRoutineRun("r1", "r_9", { fetchStatus: async () => null, bridge: b, everyMs: 500 });
    await vi.advanceTimersByTimeAsync(50);
    expect(sent.at(-1)).toEqual({ routine: null });
  });
});
