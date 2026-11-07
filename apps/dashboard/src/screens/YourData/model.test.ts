import { describe, expect, it } from "vitest";
import memoryFx from "../../fixtures/memory.json";
import ledgerFx from "../../fixtures/privacy-ledger.json";
import { captureOn } from "../../lib/memory";
import type { LedgerEntry, Memory } from "../../types";
import { CAPTURE_TEXT, YD_SECTIONS, YD_TITLE, clearItemsMarkdown, deleteAllText, deleteResultText, factLine, memoryItems, sentLine, stepForgetText, ydSectionOf } from "./model";

const mem = (memoryFx as unknown as { data: Memory }).data;
const ledger = (ledgerFx as unknown as { data: LedgerEntry[] }).data;

describe("sections", () => {
  it("are the five of the shell's contract, each with a title, and an unknown one is ignored", () => {
    expect([...YD_SECTIONS]).toEqual(["remembers", "measured", "sent", "admin-sees", "switches"]);
    for (const s of YD_SECTIONS) expect(YD_TITLE[s].length).toBeGreaterThan(3);
    expect(ydSectionOf("sent")).toBe("sent");
    expect(ydSectionOf("memory")).toBeNull();
    expect(ydSectionOf(null)).toBeNull();
  });
  it("no title uses a banned word", () => {
    for (const s of YD_SECTIONS) expect(YD_TITLE[s]).not.toMatch(/ledger|genome|rung|shadow|occurrence|understudy/i);
  });
});

describe("the memory lines", () => {
  it("come in reading order, with the plumbing id stripped from a note", () => {
    const items = memoryItems({ sections: { Never: [{ id: "n1", text: "x", note: null }], Preferences: [{ id: "p1", text: "Short summaries", note: "id:l_ab12 | You asked for this" }] } });
    expect(items.map((i) => i.id)).toEqual(["p1", "n1"]);
    expect(items[0].note).toBe("You asked for this");
    expect(items[1].note).toBeNull();
  });
  it("lists every line of the example file", () => {
    const n = Object.values(mem.sections).reduce((a, l) => a + l.length, 0);
    expect(memoryItems(mem)).toHaveLength(n);
  });
  it("clearing removes every line and keeps the headings and the role", () => {
    const md = clearItemsMarkdown("---\nrole: benefits-processor\nrevision: 3\n---\n## Preferences\n- Capture: times only\n- Short summaries\n## Never\n- Send anything\n");
    expect(md).toContain("role: benefits-processor");
    expect(md).toContain("## Preferences");
    expect(md).toContain("## Never");
    expect(md).not.toMatch(/^\s*-\s/m);
    expect(captureOn({})).toBe(false);
  });
});

describe("the closed section line is a few words", () => {
  const f = { lines: 9, capture: true as boolean | null, entries: ledger, steps: 12, shared: 6 };
  it("says counts and states, never a sentence", () => {
    expect(factLine("remembers", f)).toBe("9 lines");
    expect(factLine("remembers", { ...f, lines: 1 })).toBe("1 line");
    expect(factLine("remembers", { ...f, rules: 1 })).toBe("9 lines, 1 rule waiting");
    expect(factLine("measured", f)).toBe("Times only");
    expect(factLine("measured", { ...f, capture: false })).toBe("Capture off");
    expect(factLine("admin-sees", f)).toBe("6 summaries");
    expect(factLine("switches", f)).toBe("Capture on");
    for (const id of YD_SECTIONS) expect(factLine(id, f).split(/\s+/).length).toBeLessThanOrEqual(5);
  });
  it("counts model calls and blocked ones", () => {
    expect(sentLine([])).toBe("Nothing sent");
    expect(sentLine([{ status: "ok" }, { status: "blocked" }, { status: "ok" }])).toBe("2 calls, 1 blocked");
    expect(sentLine([{ status: "ok" }])).toBe("1 call");
  });
});

describe("Delete everything states exactly what is cleared", () => {
  it("names each part with its count, and what stays", () => {
    const t = deleteAllText({ memoryLines: 14, steps: 120, calls: 6, person: true });
    expect(t.question).toBe("Delete everything Knack holds about you?");
    expect(t.consequence).toContain("14 lines of your memory file");
    expect(t.consequence).toContain("120 step counts");
    expect(t.consequence).toContain("6 records of model calls");
    expect(t.consequence).toContain("what Knack learned about how loud to speak");
    expect(t.consequence).toContain("the counts of your cursor and apps");
    expect(t.consequence).toContain("It does not recall anything already sent.");
    expect(t.consequence).toContain("Your role, settings and routines stay.");
  });
  it("does not claim the cursor counts when nobody is set up, and says 1 in the singular", () => {
    const t = deleteAllText({ memoryLines: 1, steps: 1, calls: 1, person: false });
    expect(t.consequence).not.toContain("cursor");
    expect(t.consequence).toContain("1 line of your memory file");
    expect(t.consequence).toContain("1 step count,");
    expect(t.consequence).toContain("1 record of model calls");
  });
  it("after a partial failure it says which part was not cleared and claims nothing else", () => {
    expect(deleteResultText([{ part: "memory", ok: true }, { part: "model calls", ok: true }])).toBe("Deleted. Everything listed was cleared.");
    const r = deleteResultText([{ part: "memory", ok: true }, { part: "step counts", ok: false, note: "the engine did not answer" }]);
    expect(r).toContain("Cleared: memory.");
    expect(r).toContain("Not cleared: step counts (the engine did not answer).");
    expect(deleteResultText([{ part: "memory", ok: false }])).toContain("Nothing was cleared.");
  });
});

describe("forgetting the step counts", () => {
  it("says what is deleted in the worker's words, with the counts, and what stays", () => {
    const t = stepForgetText({ assist: 100, delegated: 12, automation: 8 }, false);
    expect(t.question).toBe("Forget 120 rows?");
    expect(t.consequence).toContain("100 counted, 12 done for you, 8 overnight");
    expect(t.consequence).toContain("Nothing else is touched.");
    expect(t.consequence).not.toMatch(/ledger|Cue\b|occurrence/i);
    expect(stepForgetText({ assist: 1, delegated: 0, automation: 0 }, true).consequence).toContain("example data");
  });
});

describe("the capture consent", () => {
  it("says what is recorded, what never is, and where it stays", () => {
    expect(CAPTURE_TEXT).toContain("never what you read");
    expect(CAPTURE_TEXT).toContain("no page text, no URLs, no field values");
    expect(CAPTURE_TEXT).toContain("stays on this laptop");
  });
});
