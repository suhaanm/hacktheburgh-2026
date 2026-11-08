import { describe, expect, it } from "vitest";
import memoryFx from "../../fixtures/memory.json";
import ledgerFx from "../../fixtures/privacy-ledger.json";
import { captureOn } from "../../lib/memory";
import type { LedgerEntry, Memory } from "../../types";
import { CAPTURE_TEXT, YD_SECTIONS, YD_TITLE, cleanNote, clearItemsMarkdown, deleteAllText, deleteResultText, factLine, memoryItems, plainMemoryLine, sentLine, stepForgetText, ydSectionOf } from "./model";

const mem = (memoryFx as unknown as { data: Memory }).data;
const ledger = (ledgerFx as unknown as { data: LedgerEntry[] }).data;

describe("a memory line's note reads as plain words", () => {
  it("drops the id plumbing and codes, and never prints the seed's own label", () => {
    expect(cleanNote("id:l_ab12 | you said so 2026-11-08")).toBe("you said so 2026-11-08");
    expect(cleanNote("corr:summary_length=detailed")).toBeNull();
    expect(cleanNote("demo seed")).toBe("set up for you");
    expect(cleanNote("onboarding 2026-11-08")).toBeNull();
    expect(cleanNote("from the UK benefits processor pack")).toBe("from the UK benefits processor pack");
    expect(cleanNote(null)).toBeNull();
  });
});

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
  it("lists every line of the example file about the worker (the file's own bracketed comments are not memories)", () => {
    const all = Object.values(mem.sections).flat();
    const comments = all.filter((l) => /^\(.*\)$/.test(l.text.trim())).length;
    expect(memoryItems(mem)).toHaveLength(all.length - comments);
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
    expect(t.consequence).toContain("14 memory lines");
    expect(t.consequence).toContain("120 step counts");
    expect(t.consequence).toContain("6 call records");
    expect(t.consequence).toContain("what it learned about notices");
    expect(t.consequence).toContain("your cursor and app counts");
    expect(t.consequence).toContain("Calls already sent are not recalled.");
    expect(t.consequence.length).toBeLessThanOrEqual(220);          // two lines at the column width
    expect(t.consequence).toContain("Your role, settings and routines stay.");
  });
  it("does not claim the cursor counts when nobody is set up, and says 1 in the singular", () => {
    const t = deleteAllText({ memoryLines: 1, steps: 1, calls: 1, person: false });
    expect(t.consequence).not.toContain("cursor");
    expect(t.consequence).toContain("1 memory line");
    expect(t.consequence).toContain("1 step count,");
    expect(t.consequence).toContain("1 call record");
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
    const t = stepForgetText({ assist: 100, delegated: 12, automation: 8 });
    expect(t.question).toBe("Forget 120 rows?");
    expect(t.consequence).toContain("100 counted, 12 done for you, 8 overnight");
    expect(t.consequence).toContain("Nothing else is touched.");
    expect(t.consequence).not.toMatch(/ledger|Cue\b|occurrence/i);
    expect(stepForgetText({ assist: 1, delegated: 0, automation: 0 }).consequence).not.toMatch(/example|sample|stand[- ]in/i);
  });
});

describe("the capture consent", () => {
  it("says what is recorded, what never is, and where it stays", () => {
    expect(CAPTURE_TEXT).toContain("never what you read");
    expect(CAPTURE_TEXT).toContain("no page text, no URLs, no field values");
    expect(CAPTURE_TEXT).toContain("stays on this laptop");
  });
});

describe("memory lines in sentences (QA Q1-10)", () => {
  it("a routine's record becomes a sentence with no rung, no code and no 'consent:'", () => {
    expect(plainMemoryLine("calc-entry-3x | rung A1 | consent: shadow | unattended: not allowed")).toBe("Calc entry 3x is set to watch first. Away runs are off.");
    expect(plainMemoryLine("benefits-workflow | rung A2 | consent: approval | unattended: not allowed")).toBe("Benefits workflow is set to ask first. Away runs are off.");
    expect(plainMemoryLine("x | rung A3 | consent: unattended | unattended: allowed")).toBe("X is set to run while you are away. Away runs are on.");
  });
  it("a help level line drops the streak and the 'last seen'", () => {
    expect(plainMemoryLine("reads-error-first: L1, streak 0, last seen never")).toBe("Help on reads error first: level 1.");
    expect(plainMemoryLine("reads-error-first: L3, streak 2")).toBe("Help on reads error first: level 3.");
  });
  it("a checklist loses its underscores", () => {
    expect(plainMemoryLine("Checklist: read_case, then calc_a or calc_b")).toBe("Checklist: read case, then calc a or calc b");
  });
  it("the list of steps that always need a click says so, and does not read like a permission", () => {
    const s = plainMemoryLine("Run without my click: submit, close case, approve payment");
    expect(s).toBe("Always asks you first before: submit, close case, approve payment.");
    expect(s).not.toMatch(/^Run without/i);
  });
  it("a line in the worker's own words is left alone, and the file's own text is kept for editing", () => {
    expect(plainMemoryLine("Working hours: Mon to Fri, 09:00 to 17:30.")).toBe("Working hours: Mon to Fri, 09:00 to 17:30.");
    const items = memoryItems({ sections: { Never: [{ id: "n1", text: "Run without my click: submit", note: null }] } });
    expect(items[0].plain).toBe("Always asks you first before: submit.");
    expect(items[0].text).toBe("Run without my click: submit");
    expect(plainMemoryLine(undefined as unknown as string)).toBe("");
  });
});

describe("memory lines: a routine that is not switched on, the Never section, and the file's own comments", () => {
  it("a routine with consent 'none' is 'not switched on', with no away sentence", () => {
    expect(plainMemoryLine("calc-entry-3x | rung A0 | consent: none | unattended: not allowed")).toBe("Calc entry 3x is not switched on.");
  });
  it("a line under Never says it is a Never line, and the click list still says what it is", () => {
    expect(plainMemoryLine("banking sites, password managers", "Never")).toBe("Never: banking sites, password managers");
    expect(plainMemoryLine("Never open banking sites", "Never")).toBe("Never open banking sites");
    expect(plainMemoryLine("Run without my click: submit", "Never")).toBe("Always asks you first before: submit.");
  });
  it("an explanatory line in brackets is the file's comment, not a memory, and is not listed", () => {
    const items = memoryItems({ sections: { Rules: [{ id: "a", text: "(3 consistent corrections become a proposed rule; each rule is versioned)", note: null }, { id: "b", text: "Check child benefits first.", note: null }] } });
    expect(items.map((i) => i.text)).toEqual(["Check child benefits first."]);
  });
});
