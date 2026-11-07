import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Switches, APP_ONLY, MIC_TEXT } from "../../components/yourdata/Switches";
import { awarenessBridge, choiceFor, type AwarenessState } from "./awareness";
import { CAPTURE_TEXT } from "./model";

const state = (over: Partial<AwarenessState> = {}): AwarenessState => ({
  available: true, consentText: "Knack can take a quick look at your screen when you seem stuck. Nothing is saved.", consentShort: "Look when I seem stuck.", agreed: true, enabled: true,
  trigger: true, periodic: false, strict: true, intervalSec: 30, dailyUsd: 0.5, callsToday: 0, lastSkip: null, ...over,
});

describe("the glance choices", () => {
  it("agreeing keeps the extras the worker had, and withdrawing withdraws them all", () => {
    expect(choiceFor({ trigger: false, periodic: false, strict: true }, { trigger: true })).toEqual({ trigger: true, periodic: false, strict: true });
    expect(choiceFor({ trigger: true, periodic: true, strict: true }, { trigger: false })).toEqual({ trigger: false });
    expect(choiceFor({ trigger: true, periodic: false, strict: true }, { periodic: true })).toEqual({ trigger: true, periodic: true, strict: true });
    expect(choiceFor({ trigger: false, periodic: true, strict: false }, { periodic: true })).toEqual({ trigger: false });   // the periodic look rides on the triggered one
  });
  it("there is a bridge only when the app gives both calls", () => {
    expect(awarenessBridge({})).toBeNull();
    const ok = { state: async () => state(), setConsent: async () => state() };
    expect(awarenessBridge({ alongside: { awareness: ok } })).toBe(ok);
    expect(awarenessBridge({ alongside: { awareness: { state: ok.state } } })).toBeNull();
  });
});

const html = (p: Partial<Parameters<typeof Switches>[0]> = {}) => renderToStaticMarkup(createElement(Switches, { capture: false, onCapture: () => undefined, busy: false, glance: null, onGlance: () => undefined, desktop: null, onDesktop: () => undefined, error: null, ...p }));
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/\s+/g, " ");

describe("the switches print their consent whole", () => {
  it("capture prints what is recorded, what never is and where it stays, beside its switch", () => {
    const t = text(html());
    expect(t).toContain(CAPTURE_TEXT);
    expect(html()).toMatch(/aria-label="Learn from when I am active"/);
  });
  it("in a browser tab the glance, microphone and folder switches say they are in the app, and no switch is drawn for them", () => {
    const h = html();
    expect((text(h).match(/Available in the Knack app\./g) ?? []).length).toBe(3);
    expect(h).not.toMatch(/aria-label="Look at my screen when I seem stuck"/);
    expect(h).not.toMatch(/aria-label="Listen for its name"/);
  });
  it("with the app the glance consent text is printed as the app wrote it, whole", () => {
    const g = state();
    const t = text(html({ glance: g }));
    expect(t).toContain(g.consentText);
    expect(html({ glance: g })).toMatch(/aria-label="Look at my screen when I seem stuck"/);
  });
  it("the periodic look and strict mode appear only after the triggered look is agreed", () => {
    expect(html({ glance: state({ trigger: false, agreed: false }) })).not.toMatch(/Also look about every/);
    expect(text(html({ glance: state() }))).toContain("Also look about every 30 seconds");
  });
  it("a build without the layer says nothing is looked at", () => {
    expect(text(html({ glance: state({ available: false }) }))).toContain("nothing is looked at");
  });
  it("the microphone consent says audio goes to a cloud model and that it is off until turned on", () => {
    expect(MIC_TEXT).toContain("sends audio to a cloud model");
    expect(MIC_TEXT).toContain("off until you turn it on");
    expect(APP_ONLY).toBe("Available in the Knack app.");
    expect(text(html({ desktop: { wakeEnabled: false, filesEnabled: false, fileFolders: ["a", "b"] } }))).toContain("2 folders chosen");
  });
});
