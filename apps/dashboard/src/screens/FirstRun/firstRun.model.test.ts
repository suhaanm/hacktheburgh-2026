import { describe, expect, it } from "vitest";
import onboardingFx from "../../fixtures/onboarding.json";
import packsFx from "../../fixtures/packs.json";
import type { OnboardingQuestions, Pack } from "../../types";
import {
  ASK_AGAIN_AFTER_DAYS, CHOICES, NO_ROLE, START, STEPS, captureRecord, cardLine, clicksToHome, defaultAnswers, heyKnackRow, kindsFor, mayAskAgain, nextUnanswered, parseProgress, permsToShow,
  progressRecord, readyLines, reduce, roleCards, shouldStartFirstRun, type FirstRunAction, type FirstRunState,
} from "./model";

const fx = <T,>(x: unknown): T => ((x as { data?: T }).data ?? x) as T;
const questions = fx<Record<string, OnboardingQuestions>>(onboardingFx)["benefits-processor"];
const packs = fx<Pack[]>(packsFx);
const run = (actions: FirstRunAction[], from: FirstRunState = START) => actions.reduce(reduce, from);
const desktop = { glance: true, voice: true };
const browser = { glance: false, voice: false };

describe("first run is three screens, each with a Skip", () => {
  it("has exactly three screens", () => { expect(STEPS).toEqual(["role", "may", "check"]); });
  it("starts on the role screen with nothing chosen, and a role card advances at once", () => {
    expect(START).toMatchObject({ step: "role", role: null, answers: {} });
    expect(run([{ type: "choose-role", role: "benefits-processor" }])).toMatchObject({ step: "may", role: "benefits-processor" });
  });
  it("Not sure yet picks nothing: the role is none, nothing is written, and the worker moves on", () => {
    const s = run([{ type: "choose-role", role: NO_ROLE }, { type: "advance" }]);
    expect(s).toMatchObject({ step: "check", role: NO_ROLE, writing: false });
  });
  it("Skip on the role screen is Not sure yet; Skip on the consent screen leaves every card unanswered and goes on", () => {
    const a = run([{ type: "skip" }]);
    expect(a).toMatchObject({ step: "may", role: NO_ROLE });
    const b = run([{ type: "choose-role", role: "programmer" }, { type: "skip" }]);
    expect(b).toMatchObject({ step: "check", answers: {}, writing: true });
  });
  it("answering a card records it and nothing else: no card is ever answered for the worker", () => {
    const s = run([{ type: "choose-role", role: "programmer" }, { type: "answer", kind: "capture", choice: "not-now" }]);
    expect(s.answers).toEqual({ capture: "not-now" });
    expect(run([{ type: "choose-role", role: "programmer" }]).answers).toEqual({});
  });
  it("Yes, Not now and Never are the same three choices on every card, in one order, none first-class", () => {
    expect(CHOICES).toEqual(["yes", "not-now", "never"]);
    for (const choice of CHOICES) {
      const s = run([{ type: "choose-role", role: "programmer" }, { type: "answer", kind: "capture", choice }]);
      expect(s.step, choice).toBe("may");
      expect(s.answers.capture, choice).toBe(choice);
    }
  });
  it("the last answer is the one that advances: the next unanswered card is found, in order, and null when none is left", () => {
    expect(kindsFor(desktop)).toEqual(["capture", "glance", "voice"]);
    expect(kindsFor(browser)).toEqual(["capture"]);
    let s = run([{ type: "choose-role", role: "programmer" }]);
    expect(nextUnanswered(s, desktop)).toBe("capture");
    s = reduce(s, { type: "answer", kind: "capture", choice: "yes" });
    expect(nextUnanswered(s, desktop)).toBe("glance");
    s = reduce(reduce(s, { type: "answer", kind: "glance", choice: "never" }), { type: "answer", kind: "voice", choice: "not-now" });
    expect(nextUnanswered(s, desktop)).toBeNull();
    expect(nextUnanswered(s, browser)).toBeNull();
  });
  it("the write starts when the consent screen is left with a role, once", () => {
    const s = run([{ type: "choose-role", role: "data-analyst" }, { type: "answer", kind: "capture", choice: "yes" }, { type: "advance" }]);
    expect(s).toMatchObject({ step: "check", writing: true, written: false });
    const done = reduce(s, { type: "written" });
    expect(done).toMatchObject({ writing: false, written: true });
    expect(reduce(reduce(done, { type: "back" }), { type: "advance" }).writing).toBe(false); // going back and on does not write it twice
  });
  it("a failed write goes back to the cards with the message, nothing recorded as written, and Skip is still there", () => {
    const s = run([{ type: "choose-role", role: "programmer" }, { type: "advance" }, { type: "failed", message: "Could not switch your role. Nothing was changed." }]);
    expect(s).toMatchObject({ step: "may", writing: false, written: false, error: "Could not switch your role. Nothing was changed." });
    expect(reduce(s, { type: "skip" }).step).toBe("check");
  });
  it("ignores clicks that do not belong to the screen, and nothing moves while the file is being written", () => {
    expect(run([{ type: "answer", kind: "capture", choice: "yes" }])).toEqual(START);
    expect(run([{ type: "advance" }])).toEqual(START);
    expect(run([{ type: "written" }])).toEqual(START);
    const writing = run([{ type: "choose-role", role: "a" }, { type: "advance" }]);
    for (const a of [{ type: "back" }, { type: "skip" }, { type: "answer", kind: "capture", choice: "yes" }, { type: "advance" }] as FirstRunAction[]) expect(reduce(writing, a)).toBe(writing);
  });
  it("Back goes one screen at a time and keeps the role and the answers", () => {
    const s = run([{ type: "choose-role", role: "programmer" }, { type: "answer", kind: "capture", choice: "yes" }, { type: "advance" }, { type: "written" }, { type: "back" }]);
    expect(s).toMatchObject({ step: "may", role: "programmer", answers: { capture: "yes" } });
    expect(reduce(s, { type: "back" })).toMatchObject({ step: "role", role: "programmer" });
    expect(reduce(START, { type: "back" })).toEqual(START);
  });
});

describe("clicks to Home, nothing skipped", () => {
  it("is 3 in a browser tab, 5 in the desktop app, one more with the connection chips", () => {
    expect(clicksToHome(browser)).toBe(3);
    expect(clicksToHome(desktop)).toBe(5);
    expect(clicksToHome(desktop, true)).toBe(6);
    expect(clicksToHome({ glance: true, voice: false })).toBe(4);
  });
});

describe("the role cards", () => {
  it("shows at most four packs and then Not sure yet, which is never a pack", () => {
    const cards = roleCards([...packs, ...packs, ...packs]);
    expect(cards).toHaveLength(5);
    expect(cards[cards.length - 1]).toEqual({ id: NO_ROLE, name: "Not sure yet", line: "Choose later" });
    for (const c of cards) expect(c.line.split(/\s+/).filter(Boolean).length).toBeLessThanOrEqual(4);
  });
  it("with no packs there is still Not sure yet, so the worker is never stuck", () => { expect(roleCards([]).map((c) => c.id)).toEqual([NO_ROLE]); });
  it("cuts a pack summary to a short noun phrase of at most four words, never ending in a comma", () => {
    expect(cardLine("Runs entitlement checks for households and writes the case note.")).toBe("Runs entitlement checks");
    for (const p of packs) { const l = cardLine(p.summary); expect(l.split(" ").length, p.id).toBeLessThanOrEqual(4); expect(l, p.id).not.toMatch(/[,;:]$/); }
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
  it("writes four plain lines for Your data, with no Markdown, file path or revision number", () => {
    const lines = readyLines(questions, defaultAnswers(questions, true));
    expect(lines).toHaveLength(4);
    for (const l of lines) expect(l).not.toMatch(/[#*`|]|---|revision|\.md/i);
  });
});

describe("the check screen", () => {
  it("asks about a permission only for something the worker said Yes to, plus screen recording when Show me can draw the ring", () => {
    expect(permsToShow({}, { ring: false })).toEqual([]);
    expect(permsToShow({ capture: "yes" }, { ring: false })).toEqual([]);
    expect(permsToShow({ voice: "yes" }, { ring: false })).toEqual(["microphone", "speech"]);
    expect(permsToShow({ glance: "yes" }, { ring: false })).toEqual(["screen"]);
    expect(permsToShow({ voice: "not-now", glance: "never" }, { ring: false })).toEqual([]);
    expect(permsToShow({ voice: "yes", glance: "yes" }, { ring: true })).toEqual(["microphone", "speech", "screen"]);
    expect(permsToShow({}, { ring: true })).toEqual(["screen"]);
  });
  it("Hey Knack: absent in a browser tab, and in the app it says listening, on but not listening (with the shell's own reason), or off", () => {
    expect(heyKnackRow(null)).toBeNull();
    expect(heyKnackRow({ switchOn: true, listening: true, line: "" })).toEqual({ title: "Hey Knack", line: "Listening. Say Hey Knack.", on: true });
    expect(heyKnackRow({ switchOn: true, listening: false, line: "Hey Knack needs the microphone. Turn it on in System Settings." })!.line).toContain("Hey Knack needs the microphone.");
    expect(heyKnackRow({ switchOn: false, listening: false, line: "" })).toEqual({ title: "Hey Knack", line: "Off. Turn it on in Settings.", on: false });
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
    for (const s of ["never", "yes", null]) expect(mayAskAgain(s, new Date("2030-01-01"))).toBe(false);
  });
});

describe("an unfinished first run is resumed, strictly", () => {
  it("keeps the screen, the role and the answers, and reads them back", () => {
    const s = run([{ type: "choose-role", role: "programmer" }, { type: "answer", kind: "capture", choice: "yes" }]);
    expect(parseProgress(progressRecord(s))).toMatchObject({ step: "may", role: "programmer", answers: { capture: "yes" }, writing: false });
  });
  it("a saved check screen resumes on the consent screen (nothing is half-written), and a saved role screen resumes on the role screen", () => {
    expect(parseProgress(JSON.stringify({ step: "check", role: "programmer", answers: {}, written: true }))?.step).toBe("may");
    expect(parseProgress(JSON.stringify({ step: "role", role: null, answers: {}, written: false }))?.step).toBe("role");
  });
  it("anything that is not exactly that shape starts again from the top", () => {
    for (const bad of [null, "", "not json", "[]", "{}", JSON.stringify({ step: "done", role: null, answers: {} }), JSON.stringify({ step: "may", role: null, answers: {} }), JSON.stringify({ step: "may", role: 7, answers: {} }), JSON.stringify({ step: "may", role: "x", answers: { capture: "maybe" } })]) {
      expect(parseProgress(bad as string | null), String(bad)).toBeNull();
    }
  });
});

describe("when first run opens by itself", () => {
  const base = { engineUp: true, extReady: true, role: null, person: null, done: false, path: "/home", hash: "" };
  it("in a browser tab: when the engine answered, knows nobody, and the address names nothing or Home", () => {
    expect(shouldStartFirstRun(base)).toBe(true);
    expect(shouldStartFirstRun({ ...base, hash: "#/home" })).toBe(true);
  });
  it("in a browser tab: never when set-up was done, the engine knows the worker, or the engine cannot be reached", () => {
    expect(shouldStartFirstRun({ ...base, done: true })).toBe(false);
    expect(shouldStartFirstRun({ ...base, role: "benefits-processor" })).toBe(false);
    expect(shouldStartFirstRun({ ...base, person: "p_1" })).toBe(false);
    expect(shouldStartFirstRun({ ...base, engineUp: false })).toBe(false);
    expect(shouldStartFirstRun({ ...base, engineUp: null })).toBe(false);
    expect(shouldStartFirstRun({ ...base, extReady: false })).toBe(false);
  });
  it("in the Knack app: on the first launch on this Mac, whatever identity the engine already has (a seeded example worker must not skip the role choice)", () => {
    const app = { ...base, inApp: true };
    expect(shouldStartFirstRun({ ...app, role: "benefits-processor", person: "p_learn01" })).toBe(true);
    expect(shouldStartFirstRun({ ...app, engineUp: false, extReady: false })).toBe(true); // it does not wait for the engine
    expect(shouldStartFirstRun({ ...app, engineUp: null, extReady: false, role: "x" })).toBe(true);
  });
  it("in the Knack app: a returning worker (the flag is present) lands on Home", () => { expect(shouldStartFirstRun({ ...base, inApp: true, done: true })).toBe(false); });
  it("never for a deep link, a link with a query, or the first-run and set-up screens themselves; and not again in a session that showed it (Back is not a trap)", () => {
    for (const inApp of [false, true]) {
      expect(shouldStartFirstRun({ ...base, inApp, path: "/growth", hash: "#/growth" })).toBe(false);
      expect(shouldStartFirstRun({ ...base, inApp, hash: "#/home", query: "settings=interruptions" })).toBe(false);
      expect(shouldStartFirstRun({ ...base, inApp, path: "/first-run", hash: "#/first-run" })).toBe(false);
      expect(shouldStartFirstRun({ ...base, inApp, path: "/setup", hash: "#/setup" })).toBe(false);
      expect(shouldStartFirstRun({ ...base, inApp, seen: true })).toBe(false);
    }
  });
});
