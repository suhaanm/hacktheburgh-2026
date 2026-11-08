import { describe, expect, it } from "vitest";
import workFx from "../fixtures/workgraph.json";
import transFx from "../fixtures/transitions.json";
import type { Transitions, WorkGraph, WorkLink, WorkNode, WorkNodeType } from "../types";
import { NODE_COLOUR, NODE_INK, capsule, cleanGraph, densityScale, firstSentence, graphHeadline, isLapsed, layoutGraph, linkBuckets, linkOpacity, nextNode, nodeAria, nodeOpacity, radiusFn, stepNode, tickBudget, tipFor, tipPlace } from "./graph";
import { GLYPH_MIN_R } from "./nodeIcons";
import { edgeKind, layers, layoutTransitions } from "./tgraph";

const wg = (workFx as unknown as { data: WorkGraph }).data;
const tr = (transFx as unknown as { data: Transitions }).data;

const mk = (id: string, type: WorkNodeType = "routine", over: Partial<WorkNode> = {}): WorkNode => ({ id, type, label: id, size: 30, strength: 0.8, last_seen: "2026-11-07", why: "Seen often.", editable: true, memory_line_id: null, ...over });
const lk = (a: string, b: string, kind: "related" | "combined" = "related", weight = 0.5): WorkLink => ({ a, b, kind, weight });
const inside = (ps: ReturnType<typeof layoutGraph>, w: number, h: number) => ps.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y) && p.x - p.r >= -0.5 && p.x + p.r <= w + 0.5 && p.y - p.r >= -0.5 && p.y + p.r <= h + 0.5);
/** A big synthetic graph with the awkward things a real one has: duplicate links, self-loops, links to nothing, a few combined pairs. */
function big(n: number): WorkGraph {
  let s = 11;
  const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  const kinds: WorkNodeType[] = ["routine", "skill", "memory", "automation"];
  const nodes = Array.from({ length: n }, (_, i) => mk(`n${i}`, kinds[i % 4], { size: kinds[i % 4] === "skill" ? rnd() : 4 + rnd() * 90, strength: rnd() }));
  const links: WorkLink[] = [];
  for (let i = 1; i < n; i++) links.push(lk(`n${i}`, `n${Math.floor(rnd() * i)}`, rnd() < 0.03 ? "combined" : "related", rnd()));
  for (let i = 0; i < n / 3; i++) links.push(lk(`n${Math.floor(rnd() * n)}`, `n${Math.floor(rnd() * n)}`));
  links.push(lk("n0", "n0"), lk("n1", "nope"), lk("n1", "n2"), lk("n2", "n1"));
  return { nodes, links };
}

describe("work graph encodings", () => {
  it("maps strength to opacity with a floor, so faded nodes stay findable", () => {
    expect(nodeOpacity(0)).toBeGreaterThan(0.15);
    expect(nodeOpacity(1)).toBe(1);
    expect(nodeOpacity(0.2)).toBeLessThan(nodeOpacity(0.9));
    expect(nodeOpacity(Number.NaN)).toBe(nodeOpacity(0));
  });
  it("sizes routines by minutes and skills by mastery, never below a size a glyph can be read in", () => {
    const r = radiusFn(wg.nodes);
    const routines = wg.nodes.filter((n) => n.type === "routine").sort((a, b) => a.size - b.size);
    expect(r(routines[0])).toBeLessThan(r(routines[routines.length - 1]));
    const skills = wg.nodes.filter((n) => n.type === "skill").sort((a, b) => a.size - b.size);
    expect(r(skills[0])).toBeLessThan(r(skills[skills.length - 1]));
    for (const n of wg.nodes) expect(r(n)).toBeGreaterThanOrEqual(GLYPH_MIN_R);
  });
  it("keeps skill circles a sane size even when the service sends sizes outside 0 to 1", () => {
    const odd = { nodes: wg.nodes.map((n) => (n.type === "skill" ? { ...n, size: n.size * 60 } : n)), links: wg.links };
    const r = radiusFn(odd.nodes);
    for (const n of odd.nodes.filter((x) => x.type === "skill")) expect(r(n)).toBeLessThanOrEqual(20);
  });
  it("colours the kinds with the design system's semantic tokens, one distinct colour each, and an ink for each", () => {
    expect(NODE_COLOUR).toEqual({ routine: "var(--accent)", skill: "var(--novice)", memory: "var(--expert)", automation: "var(--good)" });
    expect(new Set(Object.values(NODE_COLOUR)).size).toBe(4);
    expect(NODE_INK).toEqual({ routine: "var(--on-accent)", skill: "var(--on-novice)", memory: "var(--on-expert)", automation: "var(--on-good)" });
  });
  it("calls a node lapsed below the line the lede counts as fading, and a link as strong as its weaker end", () => {
    expect(isLapsed({ strength: 0.39 })).toBe(true);
    expect(isLapsed({ strength: 0.4 })).toBe(false);
    expect(linkOpacity(1, 0.2)).toBeCloseTo(0.25 + 0.55 * 0.2);
    expect(linkOpacity(0.9, 0.9)).toBeGreaterThan(linkOpacity(0.9, 0.3));
  });
  it("names a node for a screen reader in the form the smoke test reads", () => {
    expect(nodeAria(mk("a", "memory", { label: "Short summaries, plain tone", strength: 0.86 }))).toBe("Memory: Short summaries, plain tone. Strength 86 percent.");
    expect(nodeAria(mk("a", "skill", { label: "Search operators", strength: 0.2 }))).toBe("Skill: Search operators. Strength 20 percent. Fading.");
  });
});

describe("cleaning a graph", () => {
  it("keeps the first node of a repeated id and drops self-loops, links to nothing and repeated pairs", () => {
    const g = cleanGraph({ nodes: [mk("a"), mk("b"), mk("a", "skill")], links: [lk("a", "a"), lk("a", "zzz"), lk("a", "b", "related", 0.3), lk("b", "a", "combined", 0.9), lk("a", "b", "related", 0.5)] });
    expect(g.nodes.map((n) => `${n.id}:${n.type}`)).toEqual(["a:routine", "b:routine"]);
    expect(g.links).toEqual([{ a: "a", b: "b", kind: "combined", weight: 0.9 }]);
  });
  it("treats a missing or NaN weight as zero", () => {
    expect(cleanGraph({ nodes: [mk("a"), mk("b")], links: [{ a: "a", b: "b", kind: "related", weight: Number.NaN }] }).links[0].weight).toBe(0);
  });
});

describe("work graph layout", () => {
  it("lays out every node deterministically, inside the canvas", () => {
    const a = layoutGraph(wg, 900, 560, false), b = layoutGraph(wg, 900, 560, false);
    expect(a).toEqual(b);
    expect(a).toHaveLength(wg.nodes.length);
    expect(inside(a, 900, 560)).toBe(true);
  });
  it("pulls a combined pair together when combining", () => {
    const link = wg.links.find((l) => l.kind === "combined")!;
    const dist = (ps: ReturnType<typeof layoutGraph>) => { const a = ps.find((p) => p.id === link.a)!, b = ps.find((p) => p.id === link.b)!; return Math.hypot(a.x - b.x, a.y - b.y); };
    expect(dist(layoutGraph(wg, 900, 560, true))).toBeLessThan(dist(layoutGraph(wg, 900, 560, false)));
  });
  it("an empty graph has no nodes to place, and a single node sits in the middle", () => {
    expect(layoutGraph({ nodes: [], links: [] }, 900, 560, true)).toEqual([]);
    const one = layoutGraph({ nodes: [mk("only")], links: [] }, 900, 560, true);
    expect(one).toHaveLength(1);
    expect(one[0].x).toBeCloseTo(450, 0);
    expect(one[0].y).toBeCloseTo(280, 0);
  });
  it("a graph with no edges still spreads out without overlap", () => {
    const ps = layoutGraph({ nodes: Array.from({ length: 12 }, (_, i) => mk(`n${i}`, "memory")), links: [] }, 900, 560, true);
    expect(inside(ps, 900, 560)).toBe(true);
    for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) expect(Math.hypot(ps[i].x - ps[j].x, ps[i].y - ps[j].y)).toBeGreaterThan(ps[i].r + ps[j].r);
  });
  it("survives self-loops, repeated links, links to nothing and repeated ids", () => {
    const g: WorkGraph = { nodes: [mk("a"), mk("b"), mk("c"), mk("a")], links: [lk("a", "a"), lk("a", "b"), lk("b", "a"), lk("c", "ghost")] };
    const ps = layoutGraph(g, 700, 500, true);
    expect(ps.map((p) => p.id)).toEqual(["a", "b", "c"]);
    expect(inside(ps, 700, 500)).toBe(true);
  });
  it("keeps disconnected components apart and inside the canvas", () => {
    const g: WorkGraph = { nodes: ["a", "b", "c", "d", "e", "f"].map((id) => mk(id)), links: [lk("a", "b"), lk("b", "c"), lk("d", "e"), lk("e", "f")] };
    const ps = layoutGraph(g, 900, 560, true);
    expect(inside(ps, 900, 560)).toBe(true);
    const near = (x: string, y: string) => { const p = ps.find((q) => q.id === x)!, q = ps.find((r) => r.id === y)!; return Math.hypot(p.x - q.x, p.y - q.y); };
    expect(near("a", "d")).toBeGreaterThan(near("a", "b"));
  });
  it("lays out a phone-sized canvas inside its bounds", () => {
    expect(inside(layoutGraph(wg, 358, 720, true), 358, 720)).toBe(true);
  });
  it("shrinks nodes as the canvas crowds, and keeps a hoverable dot", () => {
    expect(densityScale(14, 1100, 620)).toBe(1);
    expect(densityScale(1000, 1100, 620)).toBeLessThan(0.5);
    expect(densityScale(100000, 1100, 620)).toBe(0.3);
    const nodes = big(400).nodes;
    const r = radiusFn(nodes, densityScale(400, 1100, 620));
    for (const n of nodes) expect(r(n)).toBeGreaterThanOrEqual(3);
  });
  it("settles a thousand nodes quickly, inside the canvas, with finite numbers, and most of them clear of each other", () => {
    const g = big(1000);
    const t0 = performance.now();
    const ps = layoutGraph(g, 1100, 620, true);
    const ms = performance.now() - t0;
    expect(ps).toHaveLength(1000);
    expect(inside(ps, 1100, 620)).toBe(true);
    expect(ms).toBeLessThan(5000);
    let touching = 0;
    for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) if (Math.hypot(ps[i].x - ps[j].x, ps[i].y - ps[j].y) < (ps[i].r + ps[j].r) * 0.8) touching++;
    expect(touching / ((1000 * 999) / 2)).toBeLessThan(0.002);
  });
  it("spends fewer ticks as a graph grows", () => {
    expect(tickBudget(14)).toBe(420);
    expect(tickBudget(1000)).toBeLessThan(tickBudget(200));
    expect(tickBudget(100000)).toBeGreaterThanOrEqual(90);
  });
});

describe("reaching nodes with the keys", () => {
  const grid = [["a", 0, 0], ["b", 100, 0], ["c", 200, 0], ["d", 0, 100], ["e", 100, 100], ["f", 200, 100]].map(([id, x, y]) => ({ id: id as string, x: x as number, y: y as number, r: 10 }));
  it("an arrow goes to the nearest node that way, preferring the ones straight ahead", () => {
    expect(nextNode(grid, "a", "right")).toBe("b");
    expect(nextNode(grid, "b", "right")).toBe("c");
    expect(nextNode(grid, "e", "up")).toBe("b");
    expect(nextNode(grid, "b", "down")).toBe("e");
    expect(nextNode(grid, "f", "left")).toBe("e");
    expect(nextNode(grid, "a", "down")).toBe("d");
  });
  it("wraps to the far side instead of stopping, on the same line", () => {
    expect(nextNode(grid, "c", "right")).toBe("a");
    expect(nextNode(grid, "d", "left")).toBe("f");
    expect(nextNode(grid, "e", "down")).toBe("b");
  });
  it("starts at the first node, stays on a lone node, and handles nothing", () => {
    expect(nextNode(grid, null, "right")).toBe("a");
    expect(nextNode(grid, "ghost", "up")).toBe("a");
    expect(nextNode([{ id: "x", x: 5, y: 5, r: 5 }], "x", "left")).toBe("x");
    expect(nextNode([], null, "left")).toBeNull();
  });
  it("walks every node of the real graph by list order, and the arrows never trap the focus", () => {
    const ps = layoutGraph(wg, 900, 560, true);
    const ids = ps.map((p) => p.id);
    let at: string | null = null;
    const seen = new Set<string>();
    for (let i = 0; i < ids.length; i++) { at = stepNode(ids, at, 1); seen.add(at!); }
    expect(seen.size).toBe(ids.length);
    expect(stepNode(ids, ids[0], -1)).toBe(ids[ids.length - 1]);
    expect(stepNode([], null, 1)).toBeNull();
    for (const p of ps) for (const d of ["left", "right", "up", "down"] as const) expect(nextNode(ps, p.id, d)).not.toBeNull();
  });
});

describe("when a name is shown", () => {
  const none = { hover: null, active: null, sel: null, dismissed: false };
  it("shows nothing by default: no text is drawn until the pointer, the keys or a click ask for it", () => {
    expect(tipFor(none)).toBeNull();
  });
  it("hover wins over the keyboard, which wins over the pinned node", () => {
    expect(tipFor({ ...none, hover: "a", active: "b", sel: "c" })).toEqual({ id: "a", pinned: false });
    expect(tipFor({ ...none, active: "b", sel: "c" })).toEqual({ id: "b", pinned: false });
    expect(tipFor({ ...none, sel: "c" })).toEqual({ id: "c", pinned: true });
    expect(tipFor({ ...none, hover: "c", sel: "c" })).toEqual({ id: "c", pinned: true });
  });
  it("a clicked node keeps its name once the pointer leaves, until the selection goes (Escape or another click)", () => {
    expect(tipFor({ ...none, hover: null, sel: "a" })).toEqual({ id: "a", pinned: true });
    expect(tipFor({ ...none, sel: "b" })).toEqual({ id: "b", pinned: true });
    expect(tipFor({ ...none, sel: null })).toBeNull();
  });
  it("Escape hides the passing name but not the pinned one, and clears the rest when the selection clears", () => {
    expect(tipFor({ hover: "a", active: "b", sel: "c", dismissed: true })).toEqual({ id: "c", pinned: true });
    expect(tipFor({ hover: "a", active: "b", sel: null, dismissed: true })).toBeNull();
  });
  it("puts the card by the node and inside the stage", () => {
    const p = tipPlace({ x: 20, y: 20, r: 11 }, { w: 180, h: 48 }, { w: 400, h: 300 });
    expect(p.x).toBeGreaterThanOrEqual(6);
    expect(p.x + 180).toBeLessThanOrEqual(394);
    expect(p.y).toBeGreaterThan(20);
    const low = tipPlace({ x: 380, y: 290, r: 11 }, { w: 180, h: 48 }, { w: 400, h: 300 });
    expect(low.side).toBe("above");
    expect(low.x + 180).toBeLessThanOrEqual(394);
    expect(low.y + 48).toBeLessThanOrEqual(294);
  });
});

describe("the headline", () => {
  it("counts the things and the fading ones, in one sentence", () => {
    expect(graphHeadline({ nodes: [mk("a"), mk("b"), mk("c", "skill", { strength: 0.1 }), mk("d", "memory", { strength: 0.3 })] })).toBe("4 things Knack knows about your work, 2 fading now.");
    expect(graphHeadline({ nodes: [mk("a"), mk("b")] })).toBe("2 things Knack knows about your work.");
  });
  it("says 'thing' for one, says nothing for none, and counts a repeated id once", () => {
    expect(graphHeadline({ nodes: [mk("a")] })).toBe("1 thing Knack knows about your work.");
    expect(graphHeadline({ nodes: [] })).toBe("");
    expect(graphHeadline({ nodes: [mk("a", "routine", { strength: 0.1 }), mk("a", "routine", { strength: 0.1 }), mk("b")] })).toBe("2 things Knack knows about your work, 1 fading now.");
  });
  it("agrees with the example graph", () => {
    expect(graphHeadline(wg)).toBe(`${wg.nodes.length} things Knack knows about your work${wg.nodes.some((n) => n.strength < 0.4) ? `, ${wg.nodes.filter((n) => n.strength < 0.4).length} fading now` : ""}.`);
  });
});

describe("the one-line reason", () => {
  it("takes the first sentence", () => {
    expect(firstSentence("Seen 14 times in 3 weeks. Proposed as a routine.")).toBe("Seen 14 times in 3 weeks.");
    expect(firstSentence("No full stop here")).toBe("No full stop here");
    expect(firstSentence("")).toBe("");
    expect(firstSentence("  Why?   Because.  ")).toBe("Why?");
  });
  it("cuts a sentence that runs on, at a word", () => {
    const long = Array.from({ length: 40 }, (_, i) => `word${i}`).join(" ") + ".";
    const s = firstSentence(long, 10);
    expect(s.split(" ")).toHaveLength(10);
    expect(s.endsWith("…")).toBe(true);
  });
  it("copes with unicode and a very long unbroken word", () => {
    expect(firstSentence("Überprüfe die Kündigungsfrist. Dann weiter.")).toBe("Überprüfe die Kündigungsfrist.");
    expect(firstSentence("日本語のメモ。次の文。")).toBe("日本語のメモ。次の文。");
    expect(firstSentence("x".repeat(5000)).length).toBe(5000);
  });
});

describe("drawing the links", () => {
  it("groups links by opacity into a few paths, one move per link, and skips a link to a node that is not placed", () => {
    const at = new Map([["a", { x: 0, y: 0 }], ["b", { x: 10, y: 10 }], ["c", { x: 20, y: 0 }]]);
    const st = new Map([["a", 1], ["b", 1], ["c", 0.1]]);
    const buckets = linkBuckets([lk("a", "b"), lk("b", "c"), lk("a", "c"), lk("a", "ghost")], at, st);
    expect(buckets.length).toBeLessThanOrEqual(4);
    expect(buckets.reduce((n, b) => n + (b.d.match(/M/g)?.length ?? 0), 0)).toBe(3);
    expect(buckets[buckets.length - 1].opacity).toBeGreaterThan(buckets[0].opacity);
    for (const b of buckets) { expect(b.opacity).toBeGreaterThanOrEqual(0.25); expect(b.opacity).toBeLessThanOrEqual(0.8); }
  });
  it("draws the combined envelope as one closed stadium", () => {
    const d = capsule(0, 0, 40, 0, 20);
    expect(d.startsWith("M")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    expect(d).not.toContain("NaN");
    expect(capsule(5, 5, 5, 5, 10)).not.toContain("NaN");
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
