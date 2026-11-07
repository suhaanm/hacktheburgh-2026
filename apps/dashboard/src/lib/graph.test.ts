import { describe, expect, it } from "vitest";
import workFx from "../fixtures/workgraph.json";
import transFx from "../fixtures/transitions.json";
import type { Transitions, WorkGraph } from "../types";
import { layoutGraph, nodeOpacity, placeLabels, radiusFn } from "./graph";
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
  it("keeps skill circles a sane size even when the service sends sizes outside 0 to 1", () => {
    const odd = { nodes: wg.nodes.map((n) => (n.type === "skill" ? { ...n, size: n.size * 60 } : n)), links: wg.links };
    const r = radiusFn(odd.nodes);
    for (const n of odd.nodes.filter((x) => x.type === "skill")) expect(r(n)).toBeLessThanOrEqual(20);
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

describe("label placement", () => {
  const place = (w: number, h: number, forced: string | null = null) => {
    const pts = layoutGraph(wg, w, h, true);
    const items = pts.map((p) => { const n = wg.nodes.find((x) => x.id === p.id)!; return { id: p.id, x: p.x, y: p.y, r: p.r, text: n.label.length > 24 ? n.label.slice(0, 23) + "…" : n.label, priority: n.strength }; });
    return { items, labels: placeLabels(items, w, h, forced) };
  };
  const boxes = (m: ReturnType<typeof place>["labels"]) => [...m.entries()].filter(([, l]) => !l.hidden).map(([id, l]) => ({ id, b: l.box }));
  const overlap = (a: number[], b: number[]) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
  for (const [w, h] of [[358, 720], [1100, 620]] as const) {
    it(`no two visible labels overlap and all stay inside the canvas at ${w} x ${h}`, () => {
      const vis = boxes(place(w, h).labels);
      for (let i = 0; i < vis.length; i++) {
        expect(vis[i].b[0]).toBeGreaterThanOrEqual(0); expect(vis[i].b[2]).toBeLessThanOrEqual(w);
        expect(vis[i].b[1]).toBeGreaterThanOrEqual(0); expect(vis[i].b[3]).toBeLessThanOrEqual(h);
        for (let j = i + 1; j < vis.length; j++) expect(overlap(vis[i].b, vis[j].b)).toBe(false);
      }
    });
  }
  it("keeps most labels on a desktop canvas and always labels the selected node", () => {
    const d = place(1100, 620);
    expect(boxes(d.labels).length).toBeGreaterThanOrEqual(Math.floor(wg.nodes.length * 0.8));
    const f = place(358, 720, "mem-never-bank");
    expect(f.labels.get("mem-never-bank")!.hidden).toBe(false);
  });
});

describe("transition graph", () => {
  it("layers the steps in order of the task", () => {
    const L = layers(tr.nodes, tr.edges);
    expect(L.get("read")).toBe(0);
    expect(L.get("copy_to_note")!).toBeGreaterThan(L.get("reconcile")!);
    expect(L.get("check_cliff")!).toBeLessThan(L.get("compare")!);
  });
  it("survives cycles and self loops: layers stay within the node count and the main route still reads downward", () => {
    const nodes = ["READ", "ENTER", "CHECK", "RECONCILE"].map((c) => ({ id: c, cog: c, expert_dwell_s: 10, novice_dwell_s: 10 }));
    const e = (from: string, to: string, f = 1) => ({ from, to, expert_freq: f, novice_freq: f, missing_for_novice: false, planted: null });
    const L = layers(nodes, [e("READ", "ENTER"), e("ENTER", "CHECK"), e("CHECK", "ENTER", 0.4), e("CHECK", "CHECK", 0.3), e("CHECK", "RECONCILE"), e("RECONCILE", "READ", 0.2)]);
    expect(Math.max(...L.values())).toBeLessThanOrEqual(3);
    expect(L.get("READ")).toBe(0);
    expect(L.get("ENTER")!).toBeLessThan(L.get("CHECK")!);
    expect(L.get("CHECK")!).toBeLessThan(L.get("RECONCILE")!);
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
