import { describe, expect, it } from "vitest";
import onboardingFx from "../../fixtures/onboarding.json";
import packsFx from "../../fixtures/packs.json";
import type { OnboardingQuestions, Pack } from "../../types";
import { ASK_AGAIN_AFTER_DAYS, cardLine, CLICKS_TO_HOME, START, STEPS, captureRecord, defaultAnswers, mayAskAgain, readyLines, reduce, roleCards, shouldStartFirstRun, type FirstRunAction, type FirstRunState } from "./model";

const fx = <T,>(x: unknown): T => ((x as { data?: T }).data ?? x) as T;
const questions = fx<Record<string, OnboardingQuestions>>(onboardingFx)["benefits-processor"];
const packs = fx<Pack[]>(packsFx);

const run = (actions: FirstRunAction[], from: FirstRunState = START) => actions.reduce(reduce, from);

describe("first run is three screens, one click each", () => {
  it("has exactly three states and three clicks to Home", () => {
    expect(STEPS).toEqual(["role", "capture", "ready"]);
    expect(CLICKS_TO_HOME).toBe(3);
  });
  it("starts on the role screen with nothing chosen, and a role card advances at once", () => {
    expect(START).toMatchObject({ step: "role", role: null, capture: null });
    expect(run([{ type: "choose-role", role: "benefits-processor" }])).toMatchObject({ step: "capture", role: "benefits-processor" });
  });
  it("the one consent advances to the third screen once the file is written, and needs no typing", () => {
    const s1 = run([{ type: "choose-role", role: "data-analyst" }, { type: "choose-capture", choice: "not-now" }]);
    expect(s1).toMatchObject({ step: "capture", writing: true, capture: "not-now" });
    expect(run([{ type: "written" }], s1)).toMatchObject({ step: "ready", writing: false });
  });
  it("Yes, Not now and Never each reach the same screen (equal weight: no choice is pre-selected or skipped)", () => {
    for (const choice of ["yes", "not-now", "never"] as const) {
      const s = run([{ type: "choose-role", role: "programmer" }, { type: "choose-capture", choice }, { type: "written" }]);
      expect(s.step, choice).toBe("ready");
      expect(s.capture, choice).toBe(choice);
    }
  });
  it("never chooses a capture answer for the worker: the state before a click has none", () => {
    expect(run([{ type: "choose-role", role: "programmer" }]).capture).toBeNull();
  });
  it("a failed write stays on the consent screen with a message and no answer recorded", () => {
    const s = run([{ type: "choose-role", role: "programmer" }, { type: "choose-capture", choice: "yes" }, { type: "failed", message: "Nothing was written." }]);
    expect(s).toMatchObject({ step: "capture", writing: false, capture: null, error: "Nothing was written." });
  });
  it("ignores clicks that do not belong to the screen, and Back returns to the first screen only from the consent", () => {
    expect(run([{ type: "choose-capture", choice: "yes" }])).toEqual(START);
    expect(run([{ type: "written" }])).toEqual(START);
    expect(run([{ type: "choose-role", role: "a" }, { type: "back" }])).toEqual(START);
    const writing = run([{ type: "choose-role", role: "a" }, { type: "choose-capture", choice: "yes" }]);
    expect(reduce(writing, { type: "back" })).toBe(writing);
  });
});

describe("the pack's safe defaults", () => {
  it("pre-selects the pack's tools, sets risky actions to never without me, and takes the pack's tone and hours", () => {
    const a = defaultAnswers(questions, false);
    expect(a.tools.length).toBeGreaterThan(0);
    expect(a.risky.length).toBeGreaterThan(0);
    expect(a.tone).toBe(questions.pack.tone_defaults.length);
    expect(a.hours.days.length).toBeGreaterThan(0);
    expect(a.pace.length).toBeGreaterThan(0);
  });
  it("records capture only when the worker said yes", () => {
    expect(defaultAnswers(questions, false).capture).toBe(false);
    expect(defaultAnswers(questions, true).capture).toBe(true);
  });
  it("writes four plain lines, with no Markdown, file path or revision number", () => {
    const lines = readyLines(questions, defaultAnswers(questions, true));
    expect(lines).toHaveLength(4);
    for (const l of lines) {
      expect(l).not.toMatch(/[#*`|]|---|revision|\.md/i);
      expect(l.split(/\s+/).length).toBeLessThanOrEqual(20);
    }
    expect(lines[1]).toMatch(/^Usual hours \d\d:\d\d to \d\d:\d\d, /);
    expect(lines[2]).toMatch(/^Never without asking: /);
  });
});

describe("the role cards", () => {
  it("shows at most five, one per pack, each with a name and a line of at most four words", () => {
    const cards = roleCards([...packs, ...packs, ...packs]);
    expect(cards.length).toBeLessThanOrEqual(5);
    for (const c of cards) {
      expect(c.name.length).toBeGreaterThan(0);
      expect(c.line.split(/\s+/).filter(Boolean).length).toBeLessThanOrEqual(4);
    }
  });
});

describe("the line under a role", () => {
  it("cuts a pack summary to a short noun phrase of at most four words", () => {
    expect(cardLine("Runs entitlement checks for households and writes the case note.")).toBe("Runs entitlement checks");
    for (const p of packs) expect(cardLine(p.summary).split(" ").length, p.id).toBeLessThanOrEqual(4);
  });
});

describe("the consent is remembered honestly", () => {
  it("stores yes, never, and Not now with its time", () => {
    expect(captureRecord("yes")).toBe("yes");
    expect(captureRecord("never")).toBe("never");
    expect(captureRecord("not-now", new Date("2026-11-08T10:00:00Z"))).toBe("not-now:2026-11-08T10:00:00.000Z");
  });
  it("asks again once, after a week, for Not now only", () => {
    const at = new Date("2026-11-08T10:00:00Z");
    const stored = captureRecord("not-now", at);
    expect(mayAskAgain(stored, new Date(at.getTime() + (ASK_AGAIN_AFTER_DAYS * 86_400_000 - 1000)))).toBe(false);
    expect(mayAskAgain(stored, new Date(at.getTime() + ASK_AGAIN_AFTER_DAYS * 86_400_000))).toBe(true);
    expect(mayAskAgain("never", new Date("2030-01-01"))).toBe(false);
    expect(mayAskAgain("yes", new Date("2030-01-01"))).toBe(false);
    expect(mayAskAgain(null)).toBe(false);
  });
});

describe("when first run opens by itself", () => {
  const base = { engineUp: true, extReady: true, role: null, person: null, done: false, path: "/home", hash: "" };
  it("opens when the engine answered, knows nobody, and the address names nothing or Home", () => {
    expect(shouldStartFirstRun(base)).toBe(true);
    expect(shouldStartFirstRun({ ...base, hash: "#/home" })).toBe(true);
  });
  it("never opens for a deep link, when set-up was done, when the engine knows the worker, or when the engine cannot be reached", () => {
    expect(shouldStartFirstRun({ ...base, path: "/growth", hash: "#/growth" })).toBe(false);
    expect(shouldStartFirstRun({ ...base, done: true })).toBe(false);
    expect(shouldStartFirstRun({ ...base, role: "benefits-processor" })).toBe(false);
    expect(shouldStartFirstRun({ ...base, person: "p_1" })).toBe(false);
    expect(shouldStartFirstRun({ ...base, engineUp: false })).toBe(false);
    expect(shouldStartFirstRun({ ...base, engineUp: null })).toBe(false);
    expect(shouldStartFirstRun({ ...base, extReady: false })).toBe(false);
    expect(shouldStartFirstRun({ ...base, path: "/first-run", hash: "#/first-run" })).toBe(false);
  });
});
