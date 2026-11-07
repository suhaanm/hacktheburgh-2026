import { describe, expect, it } from "vitest";
import routinesFx from "../../fixtures/routines.json";
import type { Routine } from "../../types";
import { AWAY_TEXT, CAP_LABEL, CAP_MODE, capOf, needFor, stateLine, stepState, trustWord } from "./consent";
import { runningRoutines, tabOf, touchesSentence, turnedDown } from "../../screens/Routines/model";
import { runModeOf } from "../../screens/Routines/data";

const routines = (routinesFx as unknown as { data: Routine[] }).data;
const r = (over: Partial<Routine>): Routine => ({ ...routines[2], ...over });

describe("how far a routine is trusted, in words", () => {
  it("maps the consent mode to the three steps and back", () => {
    expect(capOf("shadow")).toBe("watching");
    expect(capOf("approval")).toBe("asks");
    expect(capOf("unattended")).toBe("own");
    expect(capOf("proposed")).toBeNull();
    expect(CAP_MODE).toEqual({ watching: "shadow", asks: "approval", own: "unattended" });
    expect(Object.values(CAP_LABEL)).toEqual(["Watching", "Asks first", "Runs on its own"]);
  });
  it("never uses the rung codes or the word rung in the worker's words", () => {
    const words = [...Object.values(CAP_LABEL), trustWord(r({ status: "shadow" })), stateLine(r({ rung: "A1", status: "shadow" })), stateLine(r({ rung: "A2", status: "approval" })), AWAY_TEXT];
    for (const w of words) expect(w).not.toMatch(/\bA[0-3]\b|\brung\b|ledger|shadow run|genome/i);
  });
  it("says where the record stands in one sentence", () => {
    expect(stateLine(r({ rung: "A1", status: "shadow", shadow: { runs: 14, matches: 13, wilson_lower: 0.7 } }))).toBe("Watching: 13 of 14 practice runs match.");
    expect(stateLine(r({ rung: "A1", status: "shadow", shadow: { runs: 0, matches: 0, wilson_lower: 0 } }))).toBe("Watching: no practice runs yet.");
    expect(stateLine(r({ rung: "A2", status: "approval" }))).toBe("Asks before it submits or sends.");
    expect(stateLine(r({ rung: "A2", status: "unattended" }))).toContain("while you are away");
  });
  it("trust word: Watching, Asks first, Runs while away", () => {
    expect(trustWord({ status: "shadow" })).toBe("Watching");
    expect(trustWord({ status: "approval" })).toBe("Asks first");
    expect(trustWord({ status: "unattended" })).toBe("Runs while away");
  });
});

describe("a step up is offered only when the record earned it", () => {
  const shadow = { runs: 12, matches: 12, wilson_lower: 0.7 };
  it("steps at or below what was chosen are always offered", () => {
    expect(stepState({ rung: "A1", status: "approval", shadow }, "asks").enabled).toBe(true);
    expect(stepState({ rung: "A1", status: "approval", shadow }, "watching").enabled).toBe(true);
    expect(stepState({ rung: "A1", status: "shadow", shadow }, "watching")).toEqual({ enabled: true, need: null });
  });
  it("a step above the earned rung is disabled and says what it needs", () => {
    const s = stepState({ rung: "A1", status: "shadow", shadow }, "asks");
    expect(s.enabled).toBe(false);
    expect(s.need).toMatch(/^Needs \d+ more matching practice runs?\.$/);
    expect(stepState({ rung: "A2", status: "approval", shadow }, "own").enabled).toBe(false);
  });
  it("an earned step is offered", () => {
    expect(stepState({ rung: "A2", status: "shadow", shadow }, "asks")).toEqual({ enabled: true, need: null });
    expect(stepState({ rung: "A3", status: "approval", shadow }, "own").enabled).toBe(true);
  });
  it("counts the practice runs still missing, with the 20-run floor for asking first", () => {
    expect(needFor({ shadow: { runs: 12, matches: 12, wilson_lower: 0.7 } }, "asks")).toBe("Needs 8 more matching practice runs.");
    expect(needFor({ shadow: { runs: 20, matches: 20, wilson_lower: 0.84 } }, "asks")).toBe("The record is ready for this step.");
    expect(needFor({ shadow: { runs: 0, matches: 0, wilson_lower: 0 } }, "asks")).toMatch(/Needs 20 more/);
  });
});

describe("the Routines model", () => {
  it("running means switched on, most minutes first; turned down is declined or never", () => {
    const all = routines.map((x, i) => ({ ...x, status: (["shadow", "approval", "unattended", "declined", "never", "proposed"] as const)[i % 6], minutes_per_week: 10 * (i + 1) }));
    const run = runningRoutines(all);
    expect(run.every((x) => ["shadow", "approval", "unattended"].includes(x.status))).toBe(true);
    expect(run.map((x) => x.minutes_per_week)).toEqual([...run.map((x) => x.minutes_per_week)].sort((a, b) => b - a));
    expect(turnedDown(all).every((x) => x.status === "declined" || x.status === "never")).toBe(true);
    expect(runningRoutines(null)).toEqual([]);
  });
  it("the tab comes from the address", () => {
    expect(tabOf("could-automate")).toBe("could-automate");
    expect(tabOf("running")).toBe("running");
    expect(tabOf(null)).toBe("running");
    expect(tabOf("nonsense")).toBe("running");
  });
  it("prints everything a routine touches", () => {
    expect(touchesSentence({ touches: [], proposal: { what: "", how_often: "", touches: ["a", "b", "c", "d"], never: [] } })).toBe("Touches a, b, c and d.");
    expect(touchesSentence({ touches: ["x"], proposal: { what: "", how_often: "", touches: [], never: [] } })).toBe("Touches x.");
  });
  it("starts a routine in the agent's own words for its mode", () => {
    expect(runModeOf("shadow")).toBe("shadow");
    expect(runModeOf("approval")).toBe("approved");
    expect(runModeOf("unattended")).toBe("background");
    expect(runModeOf("proposed")).toBeNull();
  });
});
