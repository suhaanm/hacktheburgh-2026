import { describe, expect, it } from "vitest";
import { chord, inTextField, shellKeyAction, type KeyLike } from "./keys";

const key = (k: string, over: Partial<KeyLike> = {}): KeyLike => ({ key: k, metaKey: true, ctrlKey: false, altKey: false, shiftKey: false, ...over });

describe("the shell keys", () => {
  it("goes to the five destinations with Cmd-1 to Cmd-5, in the sidebar's order", () => {
    const go = (n: number) => shellKeyAction(key(String(n)), "worker");
    expect(go(1)).toEqual({ type: "go", path: "/home" });
    expect(go(2)).toEqual({ type: "go", path: "/needs-you" });
    expect(go(3)).toEqual({ type: "go", path: "/routines" });
    expect(go(4)).toEqual({ type: "go", path: "/growth" });
    expect(go(5)).toEqual({ type: "go", path: "/your-data" });
  });
  it("goes to the eight Admin rows with Cmd-1 to Cmd-8 in the Admin view, and ignores 0 and 9", () => {
    const ids = ["firm", "brief", "forecasts", "roles", "people", "onboarding", "automation", "risk"];
    ids.forEach((id, i) => expect(shellKeyAction(key(String(i + 1)), "admin"), id).toEqual({ type: "go", path: `/${id}` }));
    for (const k of ["0", "9"]) expect(shellKeyAction(key(k), "admin"), k).toBeNull();
  });
  it("ignores 0 and 6 to 9 for a worker, who has five rows", () => {
    for (const k of ["0", "6", "7", "8", "9"]) expect(shellKeyAction(key(k), "worker"), k).toBeNull();
  });
  it("opens Settings with Cmd-comma and About this screen with Cmd-slash", () => {
    expect(shellKeyAction(key(","), "worker")).toEqual({ type: "settings" });
    expect(shellKeyAction(key("/"), "worker")).toEqual({ type: "about" });
  });
  it("stops everything with Shift-Cmd-K and leaves plain Cmd-K to the palette", () => {
    expect(shellKeyAction(key("K", { shiftKey: true }), "worker")).toEqual({ type: "stop" });
    expect(shellKeyAction(key("k"), "worker")).toBeNull();
  });
  it("uses Control where there is no Command, and needs one of them", () => {
    expect(shellKeyAction(key("2", { metaKey: false, ctrlKey: true }), "worker")).toEqual({ type: "go", path: "/needs-you" });
    expect(shellKeyAction(key("2", { metaKey: false }), "worker")).toBeNull();
    expect(shellKeyAction(key("2", { altKey: true }), "worker")).toBeNull();
  });
  it("never approves anything: no key combination maps to an action other than go, settings, about or stop", () => {
    const seen = new Set<string>();
    for (const k of "abcdefghijklmnopqrstuvwxyz0123456789,./;'[]-=\\`".split("")) for (const shiftKey of [false, true]) for (const meta of [false, true]) {
      const a = shellKeyAction(key(k, { shiftKey, metaKey: meta, ctrlKey: !meta }), "admin");
      if (a) seen.add(a.type);
    }
    expect([...seen].sort()).toEqual(["about", "go", "settings", "stop"]);
    for (const k of ["Enter", " ", "y", "a"]) expect(shellKeyAction(key(k), "worker"), k).toBeNull();
  });
  it("writes the chord for a Mac and for elsewhere", () => {
    expect(chord("1", true)).toBe("⌘1");
    expect(chord(",", false)).toBe("Ctrl ,");
  });
  it("knows a text field when it sees one", () => {
    expect(inTextField({ tagName: "INPUT" } as unknown as EventTarget)).toBe(true);
    expect(inTextField({ tagName: "DIV", isContentEditable: true } as unknown as EventTarget)).toBe(true);
    expect(inTextField({ tagName: "BUTTON" } as unknown as EventTarget)).toBe(false);
    expect(inTextField(null)).toBe(false);
  });
});
