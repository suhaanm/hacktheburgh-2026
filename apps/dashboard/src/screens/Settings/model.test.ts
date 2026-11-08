import { describe, expect, it } from "vitest";
import attentionFx from "../../fixtures/attention-settings.json";
import type { AttentionSettings } from "../../types";
import { desktopBridge, liveModelsBridge, wakeBridge } from "./bridge";
import { HELP_LOCKS, LIVE_LINES, depthWords, PRESETS, SECTIONS, STOPS_LINE, WAKE_NOTE, liveModels, lockOf, lockPatch, presetOf, presetPatch, sectionOf, themeOf, wakeLine } from "./model";

const attn = (attentionFx as unknown as { data: AttentionSettings }).data;
const live = { mock: false, key_present: true };
const mock = { mock: true, key_present: true };

describe("the sections", () => {
  it("are the nine of the spec, in order, and an unknown one is ignored", () => {
    expect([...SECTIONS]).toEqual(["live-models", "interruptions", "coaching", "move-aside", "open-at-login", "appearance", "models", "views", "about"]);
    expect(sectionOf("views")).toBe("views");
    expect(sectionOf("connections")).toBe("connections");   // a slot another track fills
    expect(sectionOf("hey-knack")).toBe("hey-knack");
    expect(sectionOf("nonsense")).toBeNull();
    expect(sectionOf(null)).toBeNull();
  });
});

describe("Use live models", () => {
  const base = { health: mock, canSwitch: true, running: false, changing: false };
  it("is on when the engine is live, with the line that says each call is listed", () => {
    const v = liveModels({ ...base, health: live });
    expect(v).toEqual({ checked: true, disabled: false, line: LIVE_LINES.on });
    expect(v.line).toBe("On, because a key is set. Every call is listed under Advanced.");
  });
  it("is off with no live model and says so", () => {
    expect(liveModels(base)).toEqual({ checked: false, disabled: false, line: "Off. Knack does not call a live model." });
  });
  it("is disabled with a printed line when there is no Gemini key", () => {
    const v = liveModels({ ...base, health: { mock: true, key_present: false } });
    expect(v.disabled).toBe(true);
    expect(v.checked).toBe(false);
    expect(v.line).toBe("No key found. Add it to .env and reopen Knack.");
  });
  it("is disabled while a job is running, and says what to do", () => {
    const v = liveModels({ ...base, health: live, running: true });
    expect(v.disabled).toBe(true);
    expect(v.line).toContain("A job is running. Stop it first.");
  });
  it("says the switch restarts the engine while it is changing", () => {
    const v = liveModels({ ...base, changing: true });
    expect(v.disabled).toBe(true);
    expect(v.line).toBe("Switching restarts the engine. About 20 seconds.");
  });
  it("cannot be flipped from a browser tab, and says where it can", () => {
    const v = liveModels({ ...base, canSwitch: false });
    expect(v.disabled).toBe(true);
    expect(v.line).toContain("Switch this in the Knack app.");
  });
  it("when the engine does not answer, nothing is claimed", () => {
    expect(liveModels({ ...base, health: null })).toEqual({ checked: false, disabled: true, line: LIVE_LINES.down });
  });
  it("an unknown key state does not block the switch (the engine did not say)", () => {
    expect(liveModels({ ...base, health: { mock: true } }).disabled).toBe(false);
  });
});

describe("Interruptions: three words over the kinds", () => {
  it("the sentence about stops and blocking approvals is fixed", () => {
    expect(STOPS_LINE).toBe("Stops and blocking approvals always show.");
  });
  it("a word sets every kind that can change and never a safety kind", () => {
    for (const p of PRESETS) {
      const patch = presetPatch(p.id, attn);
      const fixed = attn.types.filter((t) => t.fixed).map((t) => t.type);
      expect(fixed.length).toBeGreaterThan(0);
      for (const f of fixed) expect(patch.modes[f]).toBeUndefined();
      expect(Object.values(patch.modes).every((m) => m === p.mode)).toBe(true);
      expect(Object.keys(patch.modes)).toHaveLength(attn.types.filter((t) => !t.fixed).length);
    }
  });
  it("Rarely is quieter than Balanced is quieter than Often, in the day's budget too", () => {
    const b = PRESETS.map((p) => presetPatch(p.id, attn).budget_per_day);
    expect(b[0]).toBeLessThan(b[1]);
    expect(b[1]).toBeLessThan(b[2]);
  });
  it("reads the word back from the kinds, and says none when they differ", () => {
    const set = (m: string): AttentionSettings => ({ ...attn, types: attn.types.map((t) => (t.fixed ? t : { ...t, mode: m })) });
    expect(presetOf(set("quiet"))).toBe("rarely");
    expect(presetOf(set("normal"))).toBe("balanced");
    expect(presetOf(set("loud"))).toBe("often");
    expect(presetOf(set("digest"))).toBeNull();
    const mixed = { ...attn, types: attn.types.map((t, i) => (t.fixed ? t : { ...t, mode: i % 2 ? "quiet" : "loud" })) };
    expect(presetOf(mixed)).toBeNull();
  });
});

describe("Coaching and the desktop bridge", () => {
  it("the help level lock reads and writes the desktop's own keys", () => {
    expect(HELP_LOCKS.map((l) => l.id)).toEqual(["auto", 1, 2, 3, 4]);
    expect(lockOf({ helpLevelMode: "auto", lockedLevel: 3 })).toBe("auto");
    expect(lockOf({ helpLevelMode: "locked", lockedLevel: 3 })).toBe(3);
    expect(lockOf(null)).toBe("auto");
    expect(lockPatch("auto")).toEqual({ helpLevelMode: "auto" });
    expect(lockPatch(2)).toEqual({ helpLevelMode: "locked", lockedLevel: 2 });
  });
  it("there is no bridge in a browser tab and one in the app", () => {
    expect(desktopBridge({})).toBeNull();
    const ok = { getSettings: async () => ({}), patchSettings: async () => undefined };
    expect(desktopBridge({ alongside: ok })).toBe(ok);
    expect(desktopBridge({ knackSettings: ok })).toBe(ok);
    expect(desktopBridge({ alongside: { getSettings: async () => ({}) } })).toBeNull();
  });
  it("the live-models bridge is the shell's models.get and models.setUseLiveModels, and nothing else", () => {
    const m = { get: async () => ({ useLiveModels: true, keyPresent: true, live: true, running: false }), setUseLiveModels: async () => ({ ok: true } as const) };
    expect(liveModelsBridge({})).toBeNull();
    expect(liveModelsBridge({ knackShell: { models: m } })).toBe(m);
    expect(liveModelsBridge({ knackShell: { models: { get: m.get } } })).toBeNull();
  });
  it("Hey Knack's bridge is state and set, and the row prints the note whole", () => {
    const w = { state: async () => ({ switchOn: true, listening: true, line: "" }), set: async () => ({ switchOn: false, listening: false, line: "" }), context: async () => true };
    expect(wakeBridge({})).toBeNull();
    expect(wakeBridge({ knackShell: { wake: w } })).toBe(w);
    expect(wakeBridge({ knackShell: { wake: { state: w.state } } })).toBeNull();
    expect(WAKE_NOTE).toBe("Stays on this Mac. Nothing is stored.");
    expect(wakeLine(null)).toBeNull();
    expect(wakeLine({ switchOn: true, listening: true, line: "Listening" })).toBe(WAKE_NOTE);
    expect(wakeLine({ switchOn: true, listening: false, line: "Not listening while Knack works" })).toBe(`${WAKE_NOTE} Not listening while Knack works`);
    expect(wakeLine({ switchOn: true, listening: false, line: "Hey Knack is off in demo mode" })).toBe(`${WAKE_NOTE} Hey Knack is off in test mode`);   // never the word demo
  });
  it("the theme falls back to auto", () => {
    expect(themeOf("dark")).toBe("dark");
    expect(themeOf("light")).toBe("light");
    expect(themeOf("x")).toBe("auto");
    expect(themeOf(null)).toBe("auto");
  });
});

describe("role pack depth", () => {
  it("a standard pack is called a full pack, not a starter", () => {
    expect(depthWords("deep")).toBe("Fully built and validated");
    expect(depthWords("standard")).toBe("Full pack");
    expect(depthWords("thin")).toBe("Starter");
    expect(depthWords(undefined)).toBe("Starter");
  });
});

describe("the live line says what is true (QA)", () => {
  it("'because a key is set' only when the engine says a key is set; otherwise just 'On.'", () => {
    const base = { canSwitch: true, running: false, changing: false };
    expect(liveModels({ ...base, health: { mock: false, key_present: true } }).line).toBe("On, because a key is set. Every call is listed under Advanced.");
    expect(liveModels({ ...base, health: { mock: false, key_present: false } }).line).toBe("On. Every call is listed under Advanced.");
    expect(liveModels({ ...base, health: { mock: false } }).line).toBe("On. Every call is listed under Advanced.");
    expect(liveModels({ ...base, health: { mock: true, key_present: true } }).line).not.toMatch(/because a key/);
  });
});

