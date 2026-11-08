// Renders the pure view to static markup (node environment, no browser) and asserts what must be printed.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import attentionFx from "../../fixtures/attention-settings.json";
import type { AttentionSettings } from "../../types";
import { DEFAULTS, liveModels } from "../../screens/Settings/model";
import { SettingsView, type SettingsViewProps } from "./SettingsView";

const attn = (attentionFx as unknown as { data: AttentionSettings }).data;
const noop = () => undefined;
const props = (over: Partial<SettingsViewProps> = {}): SettingsViewProps => ({
  live: liveModels({ health: { mock: true, key_present: true }, canSwitch: true, running: false, changing: false }), onLive: noop,
  attention: attn, attentionExample: false, attentionError: null, onPreset: noop, onMode: noop, onGroup: noop, onResetLearned: noop, onLevelGlance: noop, wake: null, onWake: noop,
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
    expect(h.indexOf("Views")).toBeLessThan(h.indexOf("Advanced"));
  });
  it("disables the switch and prints its reason when no Gemini key is found", () => {
    const h = html({ live: liveModels({ health: { mock: true, key_present: false }, canSwitch: true, running: false, changing: false }) });
    expect(h).toMatch(/aria-label="Use live models"[^>]*disabled/);
    expect(text(h)).toContain("No key found. Add it to .env and reopen Knack.");
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
  it("offers three words for interruptions, one control per group, and each kind behind its own closed disclosure", () => {
    const h = html();
    for (const w of ["Rarely", "Balanced", "Often"]) expect(text(h)).toContain(w);
    expect(text(h)).toContain("Each kind");
    expect((h.match(/data-testid="group-/g) ?? []).length).toBe(4);
    expect((h.match(/data-testid="notice-/g) ?? []).length).toBe(attn.types.filter((t) => !t.fixed).length);
    expect(text(h)).toMatch(/Always shown:/);
    // closed by default: nothing in the per-kind list is open
    expect(h).not.toMatch(/<details[^>]*open/);
  });
  it("a group's control shows the mode when every kind in it is at the same one, and none when they differ", () => {
    const quiet = { ...attn, types: attn.types.map((t) => (t.class === "wait" ? { ...t, mode: "quiet" } : t)) } as AttentionSettings;
    const h = html({ attention: quiet });
    const wait = h.slice(h.indexOf('data-testid="group-wait"'), h.indexOf('data-testid="group-info"'));
    expect(wait).toMatch(/aria-pressed="true"[^>]*>Quiet</);
    const mixed = { ...attn, types: attn.types.map((t, i) => (t.class === "wait" && i % 2 ? { ...t, mode: "loud" } : t)) } as AttentionSettings;
    const m = html({ attention: mixed });
    const waitMixed = m.slice(m.indexOf('data-testid="group-wait"'), m.indexOf('data-testid="group-info"'));
    expect(waitMixed).not.toMatch(/aria-pressed="true"/);
  });
  it("every setting that has a default prints it, and the doc lists the same ones", () => {
    const h = html({ desktop: { cueEnabled: true, minimiseWhileWorking: true, launchAtLogin: true }, wake: { switchOn: true, listening: true, line: "" }, skills: { use_claude_skills: true, off: [], skills: [] } });
    const doc = readFileSync(resolve(__dirname, "../../../../../docs/knack-ux/defaults.md"), "utf8");
    for (const [id, d] of Object.entries(DEFAULTS)) {
      if (id === "help-level") { expect(text(h)).toContain(`Default: ${d.shown}.`); continue; }
      expect(h).toContain(`data-testid="default-${id}"`);
      expect(text(h)).toContain(`Default: ${d.shown}.`);
    }
    for (const w of ["Use live models", "Interruptions", "Coaching", "Help level", "Hey Knack", "Move aside while Knack works", "Open at login", "Use my skills"]) expect(doc).toContain(w);
    expect(DEFAULTS.interruptions.value).toBe("rarely");
  });
  it("the defaults never switch on a consent, an approval or an unattended run", () => {
    expect(Object.keys(DEFAULTS).join(" ")).not.toMatch(/consent|approv|unattended|away|irreversible|frame|glance/i);
  });
  it("a desktop-only row says so in a browser tab instead of vanishing", () => {
    const t = text(html());
    expect((t.match(/Available in the Knack app\./g) ?? []).length).toBe(4);   // coaching, Hey Knack, move aside, open at login
  });
  it("Hey Knack is a switch with its note printed, and says why when it is on but quiet", () => {
    const on = text(html({ wake: { switchOn: true, listening: true, line: "Listening for Hey Knack. Stays on this Mac, nothing stored." } }));
    expect(on).toContain("Listen for Hey Knack");
    expect(on).toContain("Stays on this Mac. Nothing is stored.");
    expect(html({ wake: { switchOn: true, listening: true, line: "x" } })).toMatch(/aria-label="Listen for Hey Knack"[^>]*checked/);
    const quiet = text(html({ wake: { switchOn: true, listening: false, line: "Not listening while the screen is locked" } }));
    expect(quiet).toContain("Stays on this Mac. Nothing is stored. Not listening while the screen is locked");
    const off = text(html({ wake: { switchOn: false, listening: false, line: "Hey Knack is off" } }));
    expect(off).toContain("Stays on this Mac. Nothing is stored.");
    expect(off).not.toContain("Hey Knack is off");
  });
  it("with the app: coaching, move aside and open at login are real switches with their lines", () => {
    const h = html({ desktop: { cueEnabled: true, minimiseWhileWorking: true, launchAtLogin: false }, wake: { switchOn: true, listening: true, line: "" } });
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
  it("has no skills row until the tasks service answers; then a switch that is on by default, and each skill's name and description behind More", () => {
    expect(text(html())).not.toContain("Use my skills");
    const skills = { use_claude_skills: true, off: ["Beta"], skills: [{ name: "Beta", description: "Second one." }, { name: "Alpha", description: "First one." }, { name: "Alpha" }, { name: "" }, null as never] };
    const h = html({ skills });
    expect(text(h)).toContain("Use my skills");
    expect(text(h)).toContain("Default: on.");
    expect(h).toMatch(/aria-label="Use my skills"[^>]*checked/);
    expect(h.indexOf("Alpha")).toBeLessThan(h.indexOf("Beta"));
    expect(h).toMatch(/aria-label="Use the skill Alpha"[^>]*checked/);
    expect(h).not.toMatch(/aria-label="Use the skill Beta"[^>]*checked/);
    expect((h.match(/aria-label="Use the skill /g) ?? []).length).toBe(2);
    expect(text(h)).toContain("First one.");
  });
  it("the skills switch off turns every skill's own switch off too, and names no provider", () => {
    const h = html({ skills: { use_claude_skills: false, off: [], skills: [{ name: "Alpha" }] } });
    expect(h).toMatch(/aria-label="Use the skill Alpha"[^>]*disabled/);
    expect(text(h)).not.toMatch(/Gemini|Claude|OpenAI|Anthropic/);
  });
  it("names no model or provider anywhere in a worker's Settings", () => {
    expect(text(html({ desktop: { cueEnabled: true }, wake: { switchOn: true, listening: true, line: "" } }))).not.toMatch(/Gemini|Claude|OpenAI|Anthropic|\bmodels? and cost\b/i);
  });
});
