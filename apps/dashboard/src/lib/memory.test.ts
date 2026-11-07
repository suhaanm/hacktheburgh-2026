import { describe, expect, it } from "vitest";
import memoryFx from "../fixtures/memory.json";
import type { Memory } from "../types";
import { findLine, parseMemory, removeLineText, replaceLineText, serializeMemory } from "./memory";

const m = (memoryFx as unknown as { data: Memory }).data;

describe("memory file", () => {
  it("round-trips: parse then serialize then parse gives the same lines", () => {
    const a = parseMemory(m.markdown);
    const b = parseMemory(serializeMemory(a.role, a.revision, a.sections));
    expect(Object.keys(b.sections)).toEqual(Object.keys(a.sections));
    for (const k of Object.keys(a.sections)) expect(b.sections[k].map((l) => l.text)).toEqual(a.sections[k].map((l) => l.text));
    expect(a.role).toBe("benefits-processor");
    expect(a.revision).toBe(12);
  });
  it("keeps notes and unknown sections", () => {
    const md = "---\nrole: x\nrevision: 3\n---\n## Preferences\n- Short.   <!-- from setup -->\n## Weird\n- keep me\n";
    const p = parseMemory(md);
    expect(p.sections.Preferences[0]).toMatchObject({ text: "Short.", note: "from setup" });
    expect(p.sections.Weird[0].text).toBe("keep me");
    expect(serializeMemory("x", 3, p.sections)).toContain("## Weird");
  });
  it("keeps ids stable across a re-parse when the text is unchanged", () => {
    const first = parseMemory(m.markdown, m.sections);
    expect(first.sections.Never[0].id).toBe(m.sections.Never[0].id);
  });
  it("replaces and removes one line by its text and leaves the note", () => {
    const edited = replaceLineText(m.markdown, "Usually checks child-related benefits first.", "Checks child benefits first, always.")!;
    expect(edited).toContain("Checks child benefits first, always.");
    expect(edited).toContain("proposed 2026-11-07, accepted");
    expect(edited).not.toContain("Usually checks child-related");
    const removed = removeLineText(m.markdown, "banking sites, password managers")!;
    expect(removed).not.toContain("banking sites");
    expect(replaceLineText(m.markdown, "no such line", "x")).toBeNull();
  });
  it("finds a line by id", () => {
    expect(findLine(m.sections, "mem_never_1")?.section).toBe("Never");
    expect(findLine(m.sections, "nope")).toBeNull();
  });
});
