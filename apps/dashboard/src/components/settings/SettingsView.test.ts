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
  attention: attn, attentionError: null, onPreset: noop, onMode: noop, onGroup: noop, onResetLearned: noop, onLevelGlance: noop, wake: null, onWake: noop,
  desktop: null, onDesktop: noop, theme: "auto", onTheme: noop, view: "worker", onView: noop, version: "0.1.0", ...over,
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
  it("no setting prints a default (owner, 8 Nov 2026), the values stay in code, and the doc lists the same settings", () => {
    const h = html({ desktop: { cueEnabled: true, minimiseWhileWorking: true, launchAtLogin: true }, wake: { switchOn: true, listening: true, line: "" }, skills: { use_claude_skills: true, off: [], max_minutes: 30, max_budget_usd: 2, skills: [] } });
    const doc = readFileSync(resolve(__dirname, "../../../../../docs/knack-ux/defaults.md"), "utf8");
    expect(text(h)).not.toMatch(/\bDefault:/i);
    expect(h).not.toMatch(/data-testid="default-|st-default/);
    // The values that apply, and the doc that explains them.
    expect(DEFAULTS).toEqual({
      "live-models": { value: "on" }, interruptions: { value: "balanced" }, coaching: { value: "on" }, "help-level": { value: "auto" }, "hey-knack": { value: "on" },
      "move-aside": { value: "on" }, "open-at-login": { value: "on" }, skills: { value: "on" }, "max-minutes": { value: 30 }, "max-budget": { value: 2 },
    });
    for (const w of ["Use live models", "Interruptions", "Coaching", "Help level", "Hey Knack", "Move aside while Knack works", "Open at login", "Use my skills", "Longest a task runs", "Most a task may spend"]) expect(doc).toContain(w);
    expect(doc).toContain("30 minutes");
    expect(doc).toContain("US$2");
    expect(doc).toMatch(/Interruptions \| Balanced/);
    // The controls apply the same values: the engine's evaluated policy is Balanced, the live default is the 30 minute and US$2 caps.
    expect(h).toMatch(/aria-pressed="true"[^>]*>Balanced</);
    expect(h).toMatch(/<option value="30" selected="">30 minutes<\/option>/);
    expect(h).toMatch(/<option value="2" selected="">US\$2<\/option>/);
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
  it("Views is the one switch between Worker and Admin; an example week only with example data; and no pinned views", () => {
    const t = text(html());
    expect(t).toContain("Views");
    expect(t).not.toContain("Pinned views");
    expect(t).not.toMatch(/Example week|\bexample\b/i);
    // The week picker is still offered when the engine did not answer, with no word about what kind of data it is.
    const picked = text(html({ stories: [{ id: "pointers", label: "Worth a look", selected: true }] }));
    expect(picked).toContain("Week");
    expect(picked).not.toMatch(/Example week|\bexample\b/i);
  });
  it("has no link to Models and cost: that page is the admin's", () => {
    const h = html();
    expect(h).not.toMatch(/href="#\/models"/);
    expect(text(h)).not.toMatch(/Models and cost/);
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
    expect(text(h)).not.toContain("Default:");
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
  it("offers the longest a task may run once the service says it, with the current value chosen and a value off the list still listed", () => {
    expect(text(html({ skills: { use_claude_skills: true, off: [], skills: [] } }))).not.toContain("Longest a task runs");
    const h = html({ skills: { use_claude_skills: true, off: [], max_minutes: 45, skills: [] } });
    expect(text(h)).toContain("Longest a task runs");
    expect(h).toMatch(/<option value="45" selected="">45 minutes<\/option>/);
    expect(h).toMatch(/<option value="30">30 minutes<\/option>/);
    expect(text(h)).not.toContain("Default:");
  });
  it("offers the most a task may spend once the service says it, in US dollars, with a value off the list still listed", () => {
    expect(text(html({ skills: { use_claude_skills: true, off: [], skills: [] } }))).not.toContain("Most a task may spend");
    const h = html({ skills: { use_claude_skills: true, off: [], max_budget_usd: 3, skills: [] } });
    expect(text(h)).toContain("Most a task may spend");
    expect(h).toMatch(/<option value="3" selected="">US\$3<\/option>/);
    expect(h).toMatch(/<option value="0.5">US\$0.50<\/option>/);
    expect(text(html({ skills: { use_claude_skills: true, off: [], max_budget_usd: 2, skills: [] } }))).not.toContain("Default:");
  });
  it("the two limits on a task are inside Advanced (closed), not among the worker's rows (QA Q1-11)", () => {
    const h = html({ skills: { use_claude_skills: true, off: [], max_minutes: 30, max_budget_usd: 2, skills: [] } });
    const adv = h.indexOf(">Advanced<");
    expect(adv).toBeGreaterThan(-1);
    expect(h.indexOf("Longest a task runs")).toBeGreaterThan(adv);
    expect(h.indexOf("Most a task may spend")).toBeGreaterThan(adv);
    expect(h.indexOf("Use my skills")).toBeLessThan(adv);
    expect(h).not.toMatch(/<details[^>]*open/);
  });
});
