import { describe, expect, it } from "vitest";
import {
  NOT_STARTED, PLANNING, SEND_FAILED, TASK_MAX, TOO_LONG, TOO_MANY, checkTask, consentButtons, examplesFor, parseConsent, parseQuestion, parseSubmitted, sendError, summaryLine,
} from "./taskbox";

const consent = {
  kind: "claude_agent", scope_text: "Knack will run a Claude agent in your Downloads folder.", can: ["Read files in Downloads", "Move files into folders"], cannot: ["Delete anything", "Reach the network"],
  folder: "/Users/x/Downloads", command_hash: "abc", cost_note: "Uses your Claude plan.", max_minutes: 30,
  buttons: { allow: "Allow for this task", decline: "Not now", more: [{ id: "everything", label: "Allow everything for this task" }] },
};

describe("what was typed", () => {
  it("is trimmed and flattened to one line", () => {
    expect(checkTask("  Check   this\nhousehold \t today ")).toEqual({ ok: true, text: "Check this household today" });
  });
  it("is not sendable when there is nothing to send, and says nothing about it", () => {
    for (const nothing of ["", "   ", "\n\t", "...", "   !!  ", null, undefined, 4, {}, "‮"]) expect(checkTask(nothing), JSON.stringify(nothing)).toEqual({ ok: false, message: null });
  });
  it("is refused, never cut, when it is longer than the limit", () => {
    expect(checkTask("a".repeat(TASK_MAX))).toEqual({ ok: true, text: "a".repeat(TASK_MAX) });
    expect(checkTask("a".repeat(TASK_MAX + 1))).toEqual({ ok: false, message: TOO_LONG });
    // counted as characters a person sees: an emoji is one, not two
    expect(checkTask("😀".repeat(TASK_MAX) + "a")).toEqual({ ok: false, message: TOO_LONG });
    expect(checkTask("é".repeat(TASK_MAX)).ok).toBe(true);
  });
  it("keeps any language, and drops what could reorder or hide text", () => {
    expect(checkTask("افحص الاستحقاق")).toEqual({ ok: true, text: "افحص الاستحقاق" });
    expect(checkTask("检查家庭资格")).toEqual({ ok: true, text: "检查家庭资格" });
    expect(checkTask("Check‮it")).toEqual({ ok: true, text: "Check it" });
    expect(checkTask("Check\u0000it")).toEqual({ ok: true, text: "Check it" });
  });
  it("is sent as text only: markup and regex characters pass through untouched, for React to print as text", () => {
    expect(checkTask("<b>hi</b> [a-")).toEqual({ ok: true, text: "<b>hi</b> [a-" });
  });
});

describe("what the service answers", () => {
  it("places a task, with its one plain line", () => {
    const s = parseSubmitted({ task_id: "tk_8f3a1c2e", route: "answer", summary: "I will answer that at once.", needs_consent: null, question: null })!;
    expect(s).toMatchObject({ id: "tk_8f3a1c2e", route: "answer", summary: "I will answer that at once.", consent: null, question: null });
    expect(summaryLine(s)).toBe("I will answer that at once.");
  });
  it("also reads an answer wrapped as {data}", () => {
    expect(parseSubmitted({ data: { task_id: "tk_1", route: "browser", summary: "x" } })?.id).toBe("tk_1");
  });
  it("says Knack will plan this when the service sent no line, and that it is not sure when the route is unclear", () => {
    expect(summaryLine({ summary: "", route: "browser" })).toBe(PLANNING);
    expect(summaryLine({ summary: "", route: "unclear" })).toMatch(/not sure/);
  });
  it("is nothing when there is no task id, whatever else it says", () => {
    for (const bad of [null, undefined, 5, "x", {}, { summary: "hi" }, { task_id: "" }, { task_id: 7 }]) expect(parseSubmitted(bad), JSON.stringify(bad)).toBeNull();
  });
  it("reads a consent card whole: scope, what it can and cannot do, the folder, the cost, the buttons", () => {
    const c = parseConsent(consent)!;
    expect(c).toMatchObject({ kind: "claude_agent", scope: "Knack will run a Claude agent in your Downloads folder.", folder: "/Users/x/Downloads", cost: "Uses your Claude plan.", maxMinutes: 30, allowLabel: "Allow for this task", declineLabel: "Not now" });
    expect(c.can).toEqual(["Read files in Downloads", "Move files into folders"]);
    expect(c.cannot).toEqual(["Delete anything", "Reach the network"]);
    expect(c.more).toEqual([{ id: "everything", label: "Allow everything for this task" }]);
  });
  it("is not a consent when it carries no scope the worker could read", () => {
    for (const bad of [null, undefined, {}, { scope_text: "" }, { scope_text: "   " }, { scope_text: 4 }, "yes"]) expect(parseConsent(bad), JSON.stringify(bad)).toBeNull();
  });
  it("offers Allow and Not now of equal standing, and More only when the service sent it (a browser task has none)", () => {
    const b = consentButtons(parseConsent(consent)!);
    expect(b.main.map((x) => x.id)).toEqual(["allow", "decline"]);
    expect(b.more.map((x) => x.id)).toEqual(["everything"]);
    expect(consentButtons(parseConsent({ ...consent, kind: "browser", buttons: { allow: "Allow for this task", decline: "Not now", more: [] } })!).more).toEqual([]);
  });
  it("only ever offers the closed choices, whatever ids the service sends", () => {
    const c = parseConsent({ ...consent, buttons: { allow: "Yes", decline: "No", more: [{ id: "delete-everything", label: "Delete it all" }, { id: "everything", label: "More" }, { id: "allow", label: "x" }] } })!;
    expect(c.more.map((m) => m.id)).toEqual(["everything"]);
    expect(consentButtons(c).main.map((x) => x.id)).toEqual(["allow", "decline"]);
  });
  it("falls back to the contract's own labels, clips what is long, keeps at most six lines", () => {
    const c = parseConsent({ scope_text: "x".repeat(900), can: Array.from({ length: 12 }, (_, i) => `can ${i}`), max_minutes: 9999, cost_note: "y".repeat(500) })!;
    expect(c.scope.length).toBe(400);
    expect(c.can).toHaveLength(6);
    expect(c.cost!.length).toBe(120);
    expect(c.maxMinutes).toBeNull();
    expect(c.allowLabel).toBe("Allow for this task");
    expect(c.declineLabel).toBe("Not now");
    expect(c.more).toEqual([]);
  });
  it("reads a question card with its options, and refuses one with none", () => {
    expect(parseQuestion({ text: "Which folder?", options: [{ id: "a", label: "Downloads" }, { id: "b", label: "Desktop" }] })).toEqual({ text: "Which folder?", options: [{ id: "a", label: "Downloads" }, { id: "b", label: "Desktop" }] });
    for (const bad of [null, {}, { text: "Which?" }, { text: "Which?", options: [] }, { text: "", options: [{ id: "a", label: "A" }] }, { text: "Which?", options: [{ id: "", label: "A" }, { id: "b" }] }]) expect(parseQuestion(bad), JSON.stringify(bad)).toBeNull();
  });
});

describe("what is said when it fails", () => {
  it("names the limit of three at a time for 429", () => {
    expect(sendError(429, "too_many_tasks", "x")).toBe(TOO_MANY);
    expect(sendError(200, "too_many_tasks", null)).toBe(TOO_MANY);
  });
  it("shows the service's own short plain message, else one fixed sentence", () => {
    expect(sendError(422, "bad_task", "That task is too vague.")).toBe("That task is too vague.");
    expect(sendError(500, null, null)).toBe(SEND_FAILED);
    expect(sendError(422, "x", "z".repeat(400))).toBe(SEND_FAILED);
    expect(sendError(403, "write_refused", "Origin refused")).toBe(SEND_FAILED);
  });
  it("has a sentence for no service that says nothing was started", () => {
    expect(NOT_STARTED).toMatch(/nothing was started/);
  });
});

describe("the examples", () => {
  it("are at most three short ones, role-aware, general for a role nobody knows", () => {
    for (const role of ["benefits-processor", "data-analyst", "programmer", null, undefined, "unknown-role", ""]) {
      const ex = examplesFor(role as never);
      expect(ex.length, String(role)).toBeLessThanOrEqual(3);
      expect(ex.length, String(role)).toBeGreaterThan(0);
      for (const e of ex) { expect(e.split(/\s+/).length, e).toBeLessThanOrEqual(6); expect(checkTask(e).ok, e).toBe(true); }
    }
    expect(examplesFor("programmer")).not.toEqual(examplesFor("data-analyst"));
  });
});
