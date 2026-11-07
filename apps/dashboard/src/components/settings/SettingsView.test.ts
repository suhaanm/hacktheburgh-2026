// Renders the pure view to static markup (node environment, no browser) and asserts what must be printed.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import attentionFx from "../../fixtures/attention-settings.json";
import type { AttentionSettings } from "../../types";
import { liveModels } from "../../screens/Settings/model";
import { SettingsView, type SettingsViewProps } from "./SettingsView";

const attn = (attentionFx as unknown as { data: AttentionSettings }).data;
const noop = () => undefined;
const props = (over: Partial<SettingsViewProps> = {}): SettingsViewProps => ({
  live: liveModels({ health: { mock: true, key_present: true }, canSwitch: true, running: false, changing: false }), onLive: noop,
  attention: attn, attentionExample: false, attentionError: null, onPreset: noop, onMode: noop, onResetLearned: noop, onLevelGlance: noop,
  desktop: null, onDesktop: noop, theme: "auto", onTheme: noop, view: "worker", onView: noop, pinned: false, onPinned: noop, version: "0.1.0", ...over,
});
const html = (over?: Partial<SettingsViewProps>) => renderToStaticMarkup(createElement(SettingsView, props(over)));
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("Settings", () => {
  it("renders 'Stops and blocking approvals always show.' as printed text", () => {
    expect(text(html())).toContain("Stops and blocking approvals always show.");
  });
  it("puts Use live models first, ahead of Interruptions", () => {
    const h = html();
    expect(h.indexOf("Use live models")).toBeGreaterThan(-1);
    expect(h.indexOf("Use live models")).toBeLessThan(h.indexOf("Interruptions"));
    expect(h.indexOf("Interruptions")).toBeLessThan(h.indexOf("Coaching"));
    expect(h.indexOf("Coaching")).toBeLessThan(h.indexOf("Move aside while Knack works"));
    expect(h.indexOf("Open at login")).toBeLessThan(h.indexOf("Appearance"));
    expect(h.indexOf("Appearance")).toBeLessThan(h.indexOf("Views"));
    expect(h.indexOf("Views")).toBeLessThan(h.indexOf(">About<"));
  });
  it("disables the switch and prints its reason when no Gemini key is found", () => {
    const h = html({ live: liveModels({ health: { mock: true, key_present: false }, canSwitch: true, running: false, changing: false }) });
    expect(h).toMatch(/aria-label="Use live models"[^>]*disabled/);
    expect(text(h)).toContain("No Gemini key found. Add it to .env and reopen Knack.");
  });
  it("disables the switch while a job runs and says so in print", () => {
    const h = html({ live: liveModels({ health: { mock: false, key_present: true }, canSwitch: true, running: true, changing: false }) });
    expect(h).toMatch(/aria-label="Use live models"[^>]*disabled/);
    expect(text(h)).toContain("A job is running. Stop it first.");
  });
  it("leaves the switch enabled when it can be switched", () => {
    const h = html();
    expect(h).not.toMatch(/aria-label="Use live models"[^>]*disabled/);
  });
  it("offers three words for interruptions and eighteen kinds behind Per kind", () => {
    const h = html();
    for (const w of ["Rarely", "Balanced", "Often"]) expect(text(h)).toContain(w);
    expect(text(h)).toContain("Per kind");
    expect((h.match(/data-testid="notice-/g) ?? []).length).toBe(attn.types.filter((t) => !t.fixed).length);
    expect(text(h)).toMatch(/Always shown:/);
  });
  it("a desktop-only row says so in a browser tab instead of vanishing", () => {
    const t = text(html());
    expect((t.match(/Available in the Knack app\./g) ?? []).length).toBe(3);
  });
  it("with the app: coaching, move aside and open at login are real switches with their lines", () => {
    const h = html({ desktop: { cueEnabled: true, minimiseWhileWorking: true, launchAtLogin: false } });
    const t = text(h);
    expect(t).toContain("Knack can offer hints while you work.");
    expect(t).toContain("The window minimises while an agent works.");
    expect(t).toContain("Routines only run while Knack is open.");
    expect(t).not.toContain("Available in the Knack app.");
  });
  it("Views holds Pinned views, off by default, and an example week only with example data", () => {
    const t = text(html());
    expect(t).toContain("Pinned views");
    expect(t).toContain("Show Genome, Graph and Presence in the sidebar.");
    expect(t).not.toContain("Example week");
    expect(text(html({ stories: [{ id: "pointers", label: "Worth a look", selected: true }] }))).toContain("Example week");
  });
  it("prints an error from the engine and says nothing changed", () => {
    expect(text(html({ attentionError: "That setting is not one the engine knows. Nothing changed." }))).toContain("Nothing changed.");
  });
  it("uses no banned phrase and never the old name", () => {
    const t = text(html({ desktop: { cueEnabled: false } }));
    expect(t).not.toMatch(/\bUnderstudy\b|\bplease\b|\bsimply\b|\bdemo\b|\boops\b|\binvalid\b/i);
  });
});
