import { describe, expect, it } from "vitest";
import workFx from "../fixtures/workgraph.json";
import transFx from "../fixtures/transitions.json";
import type { Transitions, WorkGraph } from "../types";
import { layoutGraph, nodeOpacity, radiusFn } from "./graph";
import { edgeKind, layers, layoutTransitions } from "./tgraph";

const wg = (workFx as unknown as { data: WorkGraph }).data;
const tr = (transFx as unknown as { data: Transitions }).data;

describe("work graph encodings", () => {
  it("maps strength to opacity with a floor, so faded nodes stay findable", () => {
    expect(nodeOpacity(0)).toBeGreaterThan(0.15);
    expect(nodeOpacity(1)).toBe(1);
    expect(nodeOpacity(0.2)).toBeLessThan(nodeOpacity(0.9));
  });
  it("sizes routines by minutes and skills by mastery", () => {
    const r = radiusFn(wg.nodes);
    const routines = wg.nodes.filter((n) => n.type === "routine").sort((a, b) => a.size - b.size);
    expect(r(routines[0])).toBeLessThan(r(routines[routines.length - 1]));
    const skills = wg.nodes.filter((n) => n.type === "skill").sort((a, b) => a.size - b.size);
    expect(r(skills[0])).toBeLessThan(r(skills[skills.length - 1]));
  });
  it("lays out every node deterministically, inside the canvas", () => {
    const a = layoutGraph(wg, 900, 560, false), b = layoutGraph(wg, 900, 560, false);
    expect(a).toEqual(b);
    expect(a).toHaveLength(wg.nodes.length);
    for (const p of a) { expect(p.x).toBeGreaterThanOrEqual(0); expect(p.x).toBeLessThanOrEqual(900); expect(p.y).toBeGreaterThanOrEqual(0); expect(p.y).toBeLessThanOrEqual(560); }
  });
  it("pulls a combined pair together when combining", () => {
    const link = wg.links.find((l) => l.kind === "combined")!;
    const dist = (ps: ReturnType<typeof layoutGraph>) => { const a = ps.find((p) => p.id === link.a)!, b = ps.find((p) => p.id === link.b)!; return Math.hypot(a.x - b.x, a.y - b.y); };
    expect(dist(layoutGraph(wg, 900, 560, true))).toBeLessThan(dist(layoutGraph(wg, 900, 560, false)));
  });
});

describe("transition graph", () => {
  it("layers the steps in order of the task", () => {
    const L = layers(tr.nodes, tr.edges);
    expect(L.get("read")).toBe(0);
    expect(L.get("copy_to_note")!).toBeGreaterThan(L.get("reconcile")!);
    expect(L.get("check_cliff")!).toBeLessThan(L.get("compare")!);
  });
  it("lays out every node once", () => {
    expect(layoutTransitions(tr.nodes, tr.edges, 400).pos.size).toBe(tr.nodes.length);
  });
  it("marks the planted deficit edges as missing for the novice and nothing else", () => {
    const missing = tr.edges.filter((e) => edgeKind(e, "novice") === "missing");
    expect(missing.every((e) => e.planted)).toBe(true);
    expect(missing.map((e) => `${e.from}>${e.to}`).sort()).toEqual(["check_cliff>compare", "read_result>check_cliff"]);
    expect(tr.edges.filter((e) => edgeKind(e, "novice") === "extra").length).toBeGreaterThan(0);
    expect(tr.edges.filter((e) => edgeKind(e, "expert") === "missing")).toHaveLength(0);
  });
});
