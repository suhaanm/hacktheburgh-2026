// @vitest-environment jsdom
// The coaching page (Today) draws whatever the engine answers for GET /coach/state and GET /coach/next, and the second answer replaces the first a moment after
// the screen draws. This renders the real screen on the answers a programmer gets from the live engine and on hostile variants of them (nulls, missing keys,
// unknown action names, a step count of 0 or past the end, a decision that flips from a nudge to silence) and proves none of them throws or prints NaN, null or undefined.
// The owner saw "This screen hit a problem" on this page while signed in as the programmer.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setState } from "../store";

const api = vi.hoisted(() => ({ coach: vi.fn(), coachNext: vi.fn(), coachFeedback: vi.fn() }));
vi.mock("../api", () => ({ ApiError: class ApiError extends Error { status = 0; code = ""; }, api }));
import Today from "./Today";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BAD = /\b(NaN|undefined|null|Infinity)\b|\[object|Invalid/;
const PROGRAMMER_ACTIONS = "READ_TRACE READ_CODE EDIT_CODE RUN_TESTS REVIEW_DIFF INSPECT_INPUT WRITE_TEST PROBE_EDGE REPRODUCE_LOCALLY BISECT_CHANGE ADD_LOGGING WRITE_COMMIT_MSG OPEN_PR READ_CI ANSWER_REVIEW REVIEW_PEER WATCH_PROD ROLL_BACK PROFILE_HOTPATH WRITE_MIGRATION".split(" ");
const mastery = (v: number) => Object.fromEntries(PROGRAMMER_ACTIONS.map((k) => [k, v]));

// What the live engine answers for the programmer p_learn01 (8 Nov 2026): the state names a step, the decision says no task is open.
const STATE = { task: { id: "t_task", name: "Read the failing trace before changing code", step: 3, steps_total: 3 }, level: "L1", chip: "full", message: "What is the first line in the log that is actually wrong?", why: "Finds the first real error line before opening any file.", mastery: mastery(0.2), active: false };
const SILENT = { person: "p_learn01", action: "silent", message: "", why: "", target: null, missed: [], confidence: 0, level: "L1", chip: "full", decision_id: null, task_id: null, step: null, trigger: null, reason_codes: ["no_active_task"], gate: {}, p_stuck: null, p_source: null, candidate: null, mastery: { READ_TRACE: 0.15, READ_CODE: 0.15 } };
const NUDGE = { ...SILENT, action: "annotate", message: "What is the first line in the log that is actually wrong?", why: "Finds the first real error line.", decision_id: "d_1", task_id: "t_task", step: "read_trace", trigger: "expert_policy", reason_codes: ["policy_violation", "gate_act"], target: { zone: "log_panel", label_hint: "the first red line", role_hint: "text", site: "ci" }, missed: ["READ_TRACE"], gate: { consecutive: 2, reason: "act" } };

type Obj = Record<string, unknown>;
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
  api.coach.mockReset();
  api.coachNext.mockReset();
  api.coachFeedback.mockReset().mockResolvedValue({ data: { ok: true }, source: "live" });
  setState({ person: "p_learn01", role: "programmer" });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers(); vi.restoreAllMocks(); setState({ person: null, role: null }); });

const live = (data: unknown) => ({ data, meta: null, source: "live", why: null });
const settle = async () => { for (let i = 0; i < 4; i++) await act(async () => { await vi.advanceTimersByTimeAsync(5); }); };
const text = () => (host.textContent ?? "").replace(/\s+/g, " ");

/** Draws the screen on a state and a first decision (null: the engine did not answer the decision), and lets the poll tick `ticks` times with `later` answers. */
async function show(state: unknown, first: unknown, later: unknown[] = []): Promise<string> {
  api.coach.mockResolvedValue(live(state));
  api.coachNext.mockResolvedValueOnce(live(first));
  for (const l of later) api.coachNext.mockResolvedValueOnce(live(l));
  api.coachNext.mockResolvedValue(live(later.length ? later[later.length - 1] : first));
  await act(async () => { root.render(createElement(Today)); });
  await settle();
  for (let i = 0; i < later.length; i++) { await act(async () => { await vi.advanceTimersByTimeAsync(3100); }); await settle(); }
  return text();
}
const noCrash = (t: string): void => { expect(t).not.toMatch(BAD); expect(host.querySelector("h1")).not.toBeNull(); };

describe("Today on the programmer's live answers", () => {
  it("with no task open it says so calmly: the lesson comes next, no step count, no half-empty page", async () => {
    const t = await show(STATE, SILENT);
    noCrash(t);
    expect(host.querySelector("h1")?.textContent).toBe("Read the failing trace before changing code");
    expect(t).toMatch(/Next lesson/);
    expect(t).toMatch(/No task is open, so I am staying quiet/);
    expect(t).not.toMatch(/Step \d/);
    expect(host.querySelectorAll(".today__steps i").length).toBe(0);
    expect(t).not.toMatch(/Stop coaching/);
  });
  it("follows the live coach with the identity the app knows, because the state names no person", async () => {
    await show(STATE, SILENT);
    expect(api.coachNext).toHaveBeenCalledWith("p_learn01", true);
    expect(api.coach).toHaveBeenCalledWith("p_learn01");
  });
  it("with a task open it shows the step and the message", async () => {
    const t = await show({ ...STATE, active: true }, NUDGE);
    noCrash(t);
    expect(t).toMatch(/Step 3 of 3/);
    expect(host.querySelectorAll(".today__steps i").length).toBe(3);
    expect(t).toMatch(/What is the first line in the log that is actually wrong\?/);
    expect(t).toMatch(/Look for: the first red line \(text\) on ci/);
    expect(t).toMatch(/Steps skipped so far: Read the error log/);
  });
  it("a state that does not say whether a task is open still shows its step (an engine without the flag)", async () => {
    const { active: _gone, ...noFlag } = STATE;
    const t = await show(noFlag, null);
    noCrash(t);
    expect(t).toMatch(/Step 3 of 3/);
    expect(t).toMatch(/What is the first line in the log/);
  });
  it("a decision that flips from a nudge to silence and back never throws and never leaves a stale message", async () => {
    const t = await show({ ...STATE, person: "p_learn01", active: true }, NUDGE, [SILENT, NUDGE, SILENT]);
    noCrash(t);
    expect(t).toMatch(/No task is open/);
    expect(t).not.toMatch(/What is the first line in the log/);
  });
  it("labels every programmer action in plain words", async () => {
    const t = await show(STATE, SILENT);
    for (const bad of ["Open pr", "Read ci", "Write commit msg", "Profile hotpath", "Watch prod"]) expect(t).not.toContain(bad);
    for (const good of ["Open a pull request", "Read the CI result", "Write the commit message", "Profile the slow path", "Watch the release"]) expect(t).toContain(good);
  });
});

const hostile: [string, Obj, unknown][] = [
  ["message null in the state", { message: null }, SILENT],
  ["message missing from the state", { message: undefined }, SILENT],
  ["why null in the state", { why: null }, SILENT],
  ["mastery null in the state", { mastery: null }, SILENT],
  ["mastery missing from the state", { mastery: undefined }, null],
  ["a mastery value that is null or text", { mastery: { READ_TRACE: null, READ_CODE: "0.2", EDIT_CODE: 0.4 } }, SILENT],
  ["an action nobody has a label for", { mastery: { SOMETHING_NEW_ONE: 0.5, "": 0.1, "  ": 0.2 } }, SILENT],
  ["steps_total missing", { task: { id: "t", name: "Task", step: 3 } }, null],
  ["steps_total 0", { task: { id: "t", name: "Task", step: 3, steps_total: 0 }, active: true }, null],
  ["steps_total as text", { task: { id: "t", name: "Task", step: 2, steps_total: "3" }, active: true }, null],
  ["steps_total negative", { task: { id: "t", name: "Task", step: 3, steps_total: -1 }, active: true }, null],
  ["steps_total not a number", { task: { id: "t", name: "Task", step: 3, steps_total: Number.NaN }, active: true }, null],
  ["steps_total absurdly large", { task: { id: "t", name: "Task", step: 3, steps_total: 1e10 }, active: true }, null],
  ["step past steps_total", { task: { id: "t", name: "Task", step: 9, steps_total: 3 }, active: true }, null],
  ["step 0", { task: { id: "t", name: "Task", step: 0, steps_total: 3 }, active: true }, null],
  ["step missing", { task: { id: "t", name: "Task", steps_total: 3 }, active: true }, null],
  ["the task missing", { task: undefined }, null],
  ["the task null", { task: null }, SILENT],
  ["the task name an object", { task: { id: "t", name: { a: 1 }, step: 1, steps_total: 3 } }, null],
  ["the task name empty", { task: { id: "t", name: "", step: 1, steps_total: 3 } }, null],
  ["level unknown", { level: "L9" }, null],
  ["level null", { level: null }, null],
  ["chip unknown", { chip: "huge" }, null],
  ["the whole state empty", {}, null],
];
const hostileDecisions: [string, unknown][] = [
  ["a decision with message null", { ...NUDGE, message: null }],
  ["a decision with reason_codes null", { ...NUDGE, reason_codes: null }],
  ["a decision with reason_codes missing", { ...NUDGE, reason_codes: undefined }],
  ["a decision with mastery null", { ...NUDGE, mastery: null }],
  ["a decision with mastery values as text", { ...NUDGE, mastery: { READ_TRACE: "0.2", READ_CODE: null } }],
  ["a decision with a step id instead of a number", { ...NUDGE, step: "enter_household_a" }],
  ["a decision with a trigger that is not text", { ...NUDGE, trigger: 5 }],
  ["a decision with gate null", { ...NUDGE, gate: null }],
  ["a decision with a gate reason that is a number", { ...NUDGE, gate: { reason: 5, consecutive: "2" } }],
  ["a decision with missed holding objects and nulls", { ...NUDGE, missed: [{ a: 1 }, null, 5, "READ_TRACE", { label: "OPEN_PR" }] }],
  ["a decision with a target of the wrong shape", { ...NUDGE, target: { zone: 5, label_hint: { a: 1 } } }],
  ["a decision with a candidate whose message is a number", { ...SILENT, candidate: { message: 5 } }],
  ["a decision with a candidate and no message", { ...SILENT, candidate: { action: "nudge" } }],
  ["a decision with a candidate that speaks", { ...SILENT, reason_codes: [], candidate: { action: "nudge", message: "Try the log first.", why: "It names the failing line." } }],
  ["a decision with why null", { ...NUDGE, why: null }],
  ["a decision with p_stuck as text", { ...NUDGE, p_stuck: "0.5" }],
  ["a decision with a level nobody knows", { ...NUDGE, level: "L9" }],
  ["a decision that is null", null],
  ["a decision that is an empty object", {}],
  ["a decision that is a list", []],
  ["a decision that is text", "oops"],
  ["a study block (the coach says nothing)", { ...SILENT, reason_codes: ["study_mode", "study_post_test"] }],
];

describe("Today on hostile answers", () => {
  for (const [name, patch, first] of hostile) {
    it(`draws a calm screen with ${name}`, async () => {
      const t = await show({ ...STATE, ...patch }, first, first ? [first] : []);
      expect(host.querySelector("h1")).not.toBeNull();
      expect(t).not.toMatch(BAD);
    });
  }
  for (const [name, decision] of hostileDecisions) {
    it(`draws a calm screen with ${name}`, async () => {
      const t = await show({ ...STATE, person: "p_learn01", active: true }, decision, [decision, NUDGE, decision]);
      expect(host.querySelector("h1")).not.toBeNull();
      expect(t).not.toMatch(BAD);
    });
  }
  it("a state the engine answered with nothing at all draws the loading line, then a calm page", async () => {
    const t = await show(null, null);
    expect(t).not.toMatch(BAD);
  });
  it("a step count past the end is cut to the end, and an absurd total draws a bounded row of marks", async () => {
    await show({ ...STATE, task: { id: "t", name: "Task", step: 9, steps_total: 3 }, active: true }, null);
    expect(text()).toMatch(/Step 3 of 3/);
    await act(async () => { root.unmount(); });
    root = createRoot(host);
    await show({ ...STATE, task: { id: "t", name: "Task", step: 3, steps_total: 1e10 }, active: true }, null);
    expect(host.querySelectorAll(".today__steps i").length).toBeLessThanOrEqual(40);
  });
});
