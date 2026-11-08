import { describe, expect, it } from "vitest";
import { PERM_GROUPS, PERM_ORDER, closedState, groupPlan, permRow, permRows } from "./permModel";

describe("permissions as On or Off with one button", () => {
  it("each state has its one word and its one button; only macOS or the worker turns anything on", () => {
    expect(permRow("microphone", "granted")).toMatchObject({ on: true, word: "On", button: null });
    expect(permRow("microphone", "not_asked")).toMatchObject({ on: false, word: "Off", button: "Allow" });
    expect(permRow("speech", "denied")).toMatchObject({ on: false, word: "Off", button: "Open System Settings" });
    expect(permRow("screen", "restricted")).toMatchObject({ on: false, word: "Off", button: null });
    expect(permRow("screen", "restricted").line).toBe("This Mac does not let Knack use it.");
  });
  it("anything unknown is Off with Allow, never On", () => {
    for (const raw of [undefined, null, "", "maybe", 3, {}]) expect(permRow("accessibility", raw)).toMatchObject({ on: false, button: "Allow" });
    expect(closedState("not-asked")).toBe("not_asked");
    expect(closedState("Granted")).toBe("granted");
    expect(closedState(true)).toBe("granted");
  });
  it("the four rows come in order and are all Off when the app did not answer", () => {
    expect(permRows(null).map((r) => r.kind)).toEqual(PERM_ORDER);
    expect(permRows(undefined).every((r) => !r.on)).toBe(true);
    expect(permRows({ microphone: "granted", speech: "granted", accessibility: "not_asked", screen: "denied" }).map((r) => r.word)).toEqual(["On", "On", "Off", "Off"]);
  });
  it("the first run asks in two steps: voice, then clicking and screen help, in the words the owner gave", () => {
    expect(PERM_GROUPS.map((g) => g.button)).toEqual(["Allow voice", "Allow clicking and screen help"]);
    expect(PERM_GROUPS[0].kinds).toEqual(["microphone", "speech"]);
    expect(PERM_GROUPS[1].kinds).toEqual(["accessibility", "screen"]);
  });
  it("a group's button asks for the ones never asked, in order, and sends the ones refused to System Settings", () => {
    const rows = permRows({ microphone: "not_asked", speech: "not_asked", accessibility: "denied", screen: "not_asked" });
    expect(groupPlan(PERM_GROUPS[0], rows)).toEqual({ ask: ["microphone", "speech"], open: [], done: false });
    expect(groupPlan(PERM_GROUPS[1], rows)).toEqual({ ask: ["screen"], open: ["accessibility"], done: false });
    const all = permRows({ microphone: "granted", speech: "granted", accessibility: "granted", screen: "granted" });
    expect(groupPlan(PERM_GROUPS[0], all)).toEqual({ ask: [], open: [], done: true });
  });
});
