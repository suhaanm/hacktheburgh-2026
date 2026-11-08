import { describe, expect, it } from "vitest";
import { cogLabel } from "./format";
import { MAX_STEPS, isCoaching, readCoachState, readDecision, readMastery, shortTaskName, stepLabel } from "./coach";

const ids = {
  programmer: "READ_TRACE READ_CODE EDIT_CODE RUN_TESTS REVIEW_DIFF COMMIT SEARCH_DOCS PROBE_EDGE INSPECT_INPUT WRITE_TEST REPRODUCE_LOCALLY BISECT_CHANGE WRITE_COMMIT_MSG OPEN_PR READ_CI ANSWER_REVIEW REVIEW_PEER WATCH_PROD ROLL_BACK ADD_LOGGING PROFILE_HOTPATH WRITE_MIGRATION",
  analyst: "LOAD_DATA PROFILE_DATA WRITE_QUERY RUN_QUERY INSPECT_RESULT PLOT EXPORT_RESULT CLEAN_DATA RECONCILE_CONTROL GROUP_AGG TRACE_SOURCE JOIN_TABLES SET_GRAIN CHECK_MAGNITUDE QUANTIFY_UNCERTAINTY WRITE_FINDING PEER_CHECK MAKE_REPRODUCIBLE PARAMETERISE_REPORT SCHEDULE_REFRESH DOCUMENT_METRIC",
  benefits: "ENTER_HOUSEHOLD OPEN_CALCULATOR READ_RESULT CHECK_CLIFF COPY_TO_NOTE RECONCILE READ SEARCH REFORMULATE NAVIGATE ENTER COPY PASTE COMPARE CHECK DECIDE IDLE REVERT ASK",
};

describe("action labels read as plain words for every role", () => {
  for (const [role, list] of Object.entries(ids)) {
    it(`${role}: no id is shown as a clipped word, a shouted abbreviation or an underscore`, () => {
      for (const id of list.split(" ")) {
        const l = cogLabel(id);
        expect(l, id).not.toBe("");
        expect(l, id).not.toMatch(/_|\b(pr|ci|msg|prod|hotpath|agg)\b/);
        expect(l[0], id).toBe(l[0].toUpperCase());
      }
    });
  }
  it("names the ones that used to read badly", () => {
    expect(cogLabel("OPEN_PR")).toBe("Open a pull request");
    expect(cogLabel("READ_CI")).toBe("Read the CI result");
    expect(cogLabel("WRITE_COMMIT_MSG")).toBe("Write the commit message");
    expect(cogLabel("PROFILE_HOTPATH")).toBe("Profile the slow path");
    expect(cogLabel("WATCH_PROD")).toBe("Watch the release");
    expect(cogLabel("COPY_TO_NOTE")).toBe("Copy to note");
  });
  it("never throws on an id that is not text, and keeps an unknown id readable", () => {
    expect(cogLabel(undefined as never)).toBe("");
    expect(cogLabel(null as never)).toBe("");
    expect(cogLabel(7 as never)).toBe("");
    expect(cogLabel("SOMETHING_NEW")).toBe("Something new");
  });
});

describe("readCoachState", () => {
  it("reads the live programmer state", () => {
    const v = readCoachState({ task: { id: "t_task", name: "Read the failing trace before changing code", step: 3, steps_total: 3 }, level: "L1", chip: "full", message: "m", why: "w", mastery: { READ_TRACE: 0.2 }, active: false });
    expect(v).toMatchObject({ person: null, hasTask: true, active: false, level: "L1", chip: "full", message: "m" });
    expect(v.task).toEqual({ id: "t_task", name: "Read the failing trace before changing code", step: 3, total: 3 });
  });
  it("turns anything else into a safe value", () => {
    expect(readCoachState(null).hasTask).toBe(false);
    expect(readCoachState("x").task).toEqual({ id: "", name: "", step: null, total: 0 });
    expect(readCoachState({ message: null, why: 5, mastery: null }).message).toBe("");
    expect(readCoachState({ task: { name: "T", step: 9, steps_total: 3 } }).task).toMatchObject({ step: 3, total: 3 });
    expect(readCoachState({ task: { name: "T", step: 2, steps_total: 0 } }).task).toMatchObject({ step: 2, total: 0 });
    expect(readCoachState({ task: { name: "T", step: 2, steps_total: 1e10 } }).task.total).toBe(MAX_STEPS);
    expect(readCoachState({ task: { name: "T", step: 0, steps_total: 3 } }).task.step).toBeNull();
    expect(readCoachState({ task: { name: "T", step: "2", steps_total: "3" } }).task).toMatchObject({ step: 2, total: 3 });
    expect(readCoachState({ task: { name: { a: 1 } } }).hasTask).toBe(false);
    expect(readCoachState({ level: "L9", chip: "x" })).toMatchObject({ level: "L4", chip: "gone" });
    expect(readCoachState({ person: "p1" }).person).toBe("p1");
    expect(readCoachState({ person: 5 }).person).toBeNull();
  });
  it("keeps only finite mastery numbers, clamped to 0..1", () => {
    expect(readMastery({ A: 0.5, B: null, C: "0.2", D: Number.NaN, E: 3, F: -1 })).toEqual({ A: 0.5, E: 1, F: 0 });
    expect(readMastery(null)).toEqual({});
    expect(readMastery([1, 2])).toEqual({});
  });
});

describe("readDecision and isCoaching", () => {
  const state = readCoachState({ task: { name: "T", step: 2, steps_total: 3 }, message: "Look at the log.", why: "w", level: "L2", chip: "small" });
  it("without a decision it says what the state implies: its message, or silence when no task is open", () => {
    expect(readDecision(null, state)).toMatchObject({ action: "nudge", message: "Look at the log.", level: "L2", reason_codes: [] });
    const idle = readCoachState({ task: { name: "T", step: 2, steps_total: 3 }, message: "Look at the log.", active: false });
    expect(readDecision(null, idle)).toMatchObject({ action: "silent", message: "", reason_codes: ["no_active_task"] });
  });
  it("makes every field safe", () => {
    const d = readDecision({ action: "dance", message: null, reason_codes: null, mastery: null, gate: null, target: "x", candidate: { message: 5 }, step: "enter_household", level: "L9", p_stuck: "1" }, state);
    expect(d).toMatchObject({ action: "silent", message: "", reason_codes: [], mastery: {}, gate: {}, target: null, candidate: null, step: null, level: "L2", p_stuck: null });
  });
  it("a candidate that speaks is kept", () => {
    expect(readDecision({ candidate: { message: "Try the log.", why: "It names the line." } }, state).candidate).toEqual({ message: "Try the log.", why: "It names the line." });
  });
  it("isCoaching: the live decision's reason wins, then the state's flag, then the step", () => {
    expect(isCoaching(state, null)).toBe(true);
    expect(isCoaching(state, { reason_codes: ["no_active_task"] })).toBe(false);
    expect(isCoaching(state, { reason_codes: ["no_events"] })).toBe(false);
    expect(isCoaching(state, { reason_codes: ["on_track"] })).toBe(true);
    expect(isCoaching(readCoachState({ task: { name: "T", step: 2, steps_total: 3 }, active: false }), null)).toBe(false);
    expect(isCoaching(readCoachState({ task: { name: "T", step: 2, steps_total: 3 }, active: true }), null)).toBe(true);
    expect(isCoaching(readCoachState({ task: { name: "", step: 2, steps_total: 3 } }), null)).toBe(false);
    expect(isCoaching(readCoachState({ task: { name: "T", steps_total: 3 } }), null)).toBe(false);
  });
});

describe("stepLabel and shortTaskName", () => {
  it("says the step, with the total when it is known", () => {
    expect(stepLabel(3, 5)).toBe("Step 3 of 5");
    expect(stepLabel(7, 5)).toBe("Step 5 of 5");
    expect(stepLabel(2, 0)).toBe("Step 2");
    expect(stepLabel(null, 5)).toBeNull();
  });
  it("cuts a task name for a one-line row", () => {
    expect(shortTaskName("Entitlement check, household H-9")).toBe("Entitlement check");
    expect(shortTaskName("Read the failing trace before changing code")).toBe("Read the failing trace before changing code");
    expect(shortTaskName("One two three four five six seven eight nine ten")).toBe("One two three four five six seven eight nine…");
    expect(shortTaskName("")).toBe("");
  });
});
