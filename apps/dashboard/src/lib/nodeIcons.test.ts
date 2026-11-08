import { describe, expect, it } from "vitest";
import tr from "../fixtures/transitions.json";
import { GLYPH_MIN_R, NODE_BLURB, NODE_ICON, NODE_KINDS, NODE_NAME, STEP_ICON, STEP_NAME, allPrims, glyphSize, stepKind, type StepKind } from "./nodeIcons";

const cogs = (tr as unknown as { data: { nodes: { cog: string }[] } }).data.nodes.map((n) => n.cog);
/** Every number in a path's data: the 16 px grid holds them all (the repo's icon set draws on 0 to 16). */
const numbers = (d: string) => (d.match(/-?\d*\.?\d+/g) ?? []).map(Number);

describe("node icons", () => {
  it("gives each of the four kinds exactly one icon, and no two are the same drawing", () => {
    expect(NODE_KINDS).toEqual(["routine", "skill", "memory", "automation"]);
    const drawings = NODE_KINDS.map((k) => JSON.stringify(NODE_ICON[k]));
    expect(new Set(drawings).size).toBe(4);
    for (const k of NODE_KINDS) { expect(NODE_ICON[k].length).toBeGreaterThan(0); expect(NODE_NAME[k]).toMatch(/^[A-Z][a-z]+$/); expect(NODE_BLURB[k].split(" ").length).toBeLessThanOrEqual(12); }
  });
  it("draws every icon inside the 16 px grid, with no stray numbers", () => {
    for (const p of allPrims()) {
      if (p.t === "path") for (const n of numbers(p.d)) { expect(Number.isFinite(n)).toBe(true); expect(Math.abs(n)).toBeLessThanOrEqual(16); }
      else { expect(p.cx - p.r).toBeGreaterThanOrEqual(0); expect(p.cx + p.r).toBeLessThanOrEqual(16); expect(p.cy - p.r).toBeGreaterThanOrEqual(0); expect(p.cy + p.r).toBeLessThanOrEqual(16); }
    }
  });
  it("sizes a glyph to about two thirds of its disc, readable and never huge", () => {
    expect(glyphSize(11)).toBeGreaterThanOrEqual(10);
    expect(glyphSize(30)).toBeLessThanOrEqual(22);
    expect(glyphSize(3)).toBe(9);
    expect(GLYPH_MIN_R).toBeGreaterThan(5);
  });
});

describe("step icons for the transition graph", () => {
  it("gives every cog of the example flow a real kind, not the fallback", () => {
    for (const c of cogs) expect(stepKind(c), c).not.toBe("step");
  });
  it("maps the cogs the flow uses to kinds a person would expect", () => {
    const want: Record<string, StepKind> = { READ: "read", READ_RESULT: "read", SEARCH: "search", OPEN_CALCULATOR: "open", ENTER: "enter", ENTER_HOUSEHOLD: "enter", CHECK_CLIFF: "check", COMPARE: "compare", RECONCILE: "compare", COPY_TO_NOTE: "copy", IDLE: "idle", REVERT: "revert" };
    for (const [cog, kind] of Object.entries(want)) expect(stepKind(cog), cog).toBe(kind);
  });
  it("reads a cog in any case, and treats an unknown one as a plain step", () => {
    expect(stepKind("read_result")).toBe("read");
    expect(stepKind("TELEPORT")).toBe("step");
    expect(stepKind("")).toBe("step");
  });
  it("has an icon and a name for every step kind", () => {
    for (const k of Object.keys(STEP_ICON) as StepKind[]) { expect(STEP_ICON[k].length).toBeGreaterThan(0); expect(STEP_NAME[k]).toBeTruthy(); }
    expect(Object.keys(STEP_ICON).sort()).toEqual(Object.keys(STEP_NAME).sort());
  });
});
