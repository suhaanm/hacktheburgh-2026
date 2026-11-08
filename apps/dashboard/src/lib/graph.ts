// The work graph's pure parts: how nodes are cleaned, sized, laid out and reached by keyboard, and when a name is shown.
// The look follows the design system's "work graph" (colour is the kind, size is minutes or mastery, opacity is strength, a dashed ring is lapsed,
// a hairline is a link, a dashed envelope is a combined routine). The graph writes no text on the canvas: a name appears on hover, keyboard focus or a click
// (tipFor), in a card placed by placeHint. Position carries no meaning.
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { scaleSqrt } from "d3-scale";
import { placeHint } from "../components/hint-logic";
import type { WorkGraph, WorkLink, WorkNode, WorkNodeType } from "../types";
import { NODE_NAME } from "./nodeIcons";

/** The design system colours the kinds with its semantic tokens: the one accent for routines, novice for skills, expert for memory, good for automation. */
export const NODE_COLOUR: Record<WorkNodeType, string> = {
  routine: "var(--accent)",
  skill: "var(--novice)",
  memory: "var(--expert)",
  automation: "var(--good)",
};
/** The ink that sits on a filled node of that colour (the glyph). */
export const NODE_INK: Record<WorkNodeType, string> = {
  routine: "var(--on-accent)",
  skill: "var(--on-novice)",
  memory: "var(--on-expert)",
  automation: "var(--on-good)",
};

export const NODE_LABEL: Record<WorkNodeType, string> = NODE_NAME;

/** A node this weak has lapsed: it gets the dashed ring as well as the faint fill (the lede counts these as fading). */
export const LAPSED_BELOW = 0.4;
export const isLapsed = (n: { strength: number }): boolean => n.strength < LAPSED_BELOW;

/**
 * Opacity is strength, in two bands so the glyph inside a node stays readable. A live node (strength 0.4 and up) runs from 0.75 to 1, and the glyph is
 * the token's `--on-*` ink on it. A lapsed node runs from 0.22 to 0.5, gets a dashed ring, and its glyph is `--fg` on the pale disc. Both pairs hold 3 to 1
 * in both themes (graph.test.ts reads the tokens and checks). A floor keeps even the faintest node findable.
 */
export function nodeOpacity(strength: number): number {
  const s = Math.min(1, Math.max(0, Number.isFinite(strength) ? strength : 0));
  return s >= LAPSED_BELOW ? 0.75 + 0.25 * ((s - LAPSED_BELOW) / (1 - LAPSED_BELOW)) : 0.22 + 0.28 * (s / LAPSED_BELOW);
}

/** The link's opacity: as strong as the weaker of its two ends (design system: "0.25 + 0.55 x min strength"). */
export function linkOpacity(a: number, b: number): number {
  return 0.25 + 0.55 * Math.min(1, Math.max(0, Math.min(a, b)));
}

/**
 * A graph the screen can trust: one node per id (the first wins), and only links between two different nodes that exist, once per pair
 * (the strongest weight wins and a combined link beats a related one). Self-loops carry no meaning in this graph and are dropped.
 */
export function cleanGraph(g: WorkGraph): WorkGraph {
  const seen = new Set<string>();
  const nodes = g.nodes.filter((n) => (seen.has(n.id) ? false : (seen.add(n.id), true)));
  const byPair = new Map<string, WorkLink>();
  for (const l of g.links) {
    if (l.a === l.b || !seen.has(l.a) || !seen.has(l.b)) continue;
    const key = l.a < l.b ? `${l.a}\u0000${l.b}` : `${l.b}\u0000${l.a}`;
    const had = byPair.get(key);
    const weight = Number.isFinite(l.weight) ? l.weight : 0;
    if (!had) byPair.set(key, { ...l, weight });
    else byPair.set(key, { ...had, kind: had.kind === "combined" || l.kind === "combined" ? "combined" : "related", weight: Math.max(had.weight, weight) });
  }
  return { nodes, links: [...byPair.values()] };
}

/**
 * How much to shrink nodes so a crowded canvas stays readable: 1 up to about a hundred nodes in a desktop canvas, then the square root of the
 * crowding, never below a dot that can still be hovered.
 */
export function densityScale(count: number, width: number, height: number): number {
  if (count <= 1 || width <= 0 || height <= 0) return 1;
  const perNode = (width * height * 0.7) / count;
  return Math.max(0.3, Math.min(1, Math.sqrt(perNode / 4200)));
}

/** Size per type: routines and automations by weekly minutes, skills by mastery, memory fixed. Never smaller than a glyph can be read in at scale 1. */
export function radiusFn(nodes: WorkNode[], scale = 1): (n: WorkNode) => number {
  const maxOf = (t: WorkNodeType) => Math.max(1, ...nodes.filter((n) => n.type === t).map((n) => (Number.isFinite(n.size) ? n.size : 0)));
  // Each type is scaled to its own largest value, so a service that sends skill sizes as mastery (0 to 1) or as anything else still draws sensibly.
  const scales: Record<WorkNodeType, (v: number) => number> = {
    routine: scaleSqrt().domain([0, maxOf("routine")]).range([11, 30]).clamp(true),
    automation: scaleSqrt().domain([0, maxOf("automation")]).range([11, 22]).clamp(true),
    skill: scaleSqrt().domain([0, maxOf("skill")]).range([10, 20]).clamp(true),
    memory: () => 11,
  };
  return (n) => Math.max(3, scales[n.type](Number.isFinite(n.size) ? n.size : 0) * scale);
}

export interface Placed {
  id: string;
  x: number;
  y: number;
  r: number;
}

interface SimNode extends Placed {
  index?: number;
  vx?: number;
  vy?: number;
}

/** The simulation's tick budget: all 420 for an ordinary graph, fewer as it grows so a thousand nodes still settle in about a second. */
export function tickBudget(count: number): number {
  return count <= 120 ? 420 : Math.max(90, Math.round(420 * Math.sqrt(120 / count)));
}

/**
 * Deterministic layout: the simulation runs to rest before anything is drawn, so nodes do not jitter on screen. `combine` makes combined pairs
 * sit together; without it they stay apart, which lets the screen animate the merge. The graph may be raw: duplicates, self-loops and dangling
 * links are ignored, so the result always has one entry per distinct node id and finite coordinates inside the canvas.
 */
export function layoutGraph(input: WorkGraph, width: number, height: number, combine: boolean): Placed[] {
  const graph = cleanGraph(input);
  const count = graph.nodes.length;
  if (count === 0) return [];
  const w = Math.max(1, width), h = Math.max(1, height);
  const scale = densityScale(count, w, h);
  const r = radiusFn(graph.nodes, scale);
  const tall = h > w * 1.2;
  const ring = (i: number, n: number) => ({ x: w / 2 + Math.cos((i / n) * 6.2832) * w * 0.34, y: h / 2 + Math.sin((i / n) * 6.2832) * h * 0.34 });
  const nodes: SimNode[] = graph.nodes.map((n, i) => ({ id: n.id, r: r(n), ...ring(i, count) }));
  const links = graph.links.map((l) => ({ source: l.a, target: l.b, kind: l.kind, weight: l.weight }));
  type L = { kind: string; weight: number; source: SimNode; target: SimNode };
  const sim = forceSimulation(nodes as never)
    .randomSource(lcg(7))
    .force("charge", forceManyBody().strength(-520 * scale * scale).distanceMax(520))
    .force("center", forceCenter(w / 2, h / 2))
    // A tall, narrow canvas (a phone) gets its spread along the long side.
    .force("x", forceX(w / 2).strength(tall ? 0.09 : 0.025))
    .force("y", forceY(h / 2).strength(tall ? 0.008 : 0.04))
    .force("collide", forceCollide<SimNode>().radius((d) => d.r + (tall ? 30 : 24) * scale).strength(1).iterations(count > 300 ? 1 : 3))
    .force(
      "link",
      forceLink(links as never)
        .id((d) => (d as SimNode).id)
        .distance((l) => {
          const k = l as unknown as L;
          if (combine && k.kind === "combined") return k.source.r + k.target.r + 30 * scale;
          return (150 - 60 * k.weight) * scale + k.source.r + k.target.r;
        })
        .strength((l) => {
          const k = l as unknown as L;
          return combine && k.kind === "combined" ? 1 : 0.1 + 0.3 * Math.min(1, Math.max(0, k.weight));
        }),
    )
    .stop();
  const ticks = tickBudget(count);
  for (let i = 0; i < ticks; i++) sim.tick();
  // Fit the settled layout into the canvas. No labels are drawn, so the margin only has to hold the largest node and its ring.
  const maxR = Math.max(...nodes.map((n) => n.r));
  const pad = maxR + 12;
  const mx = Math.min(pad, w / 2 - 1), my = Math.min(pad, h / 2 - 1);
  const finite = (v: number, d: number) => (Number.isFinite(v) ? v : d);
  const xs = nodes.map((n) => finite(n.x, w / 2)), ys = nodes.map((n) => finite(n.y, h / 2));
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = x1 > x0 ? Math.min(1.5, (w - 2 * mx) / (x1 - x0)) : 1;
  const sy = y1 > y0 ? Math.min(1.5, (h - 2 * my) / (y1 - y0)) : 1;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  return nodes.map((n, i) => ({
    id: n.id,
    r: n.r,
    x: clamp(w / 2 + (xs[i] - cx) * sx, mx, w - mx),
    y: clamp(h / 2 + (ys[i] - cy) * sy, my, h - my),
  }));
}

function lcg(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}

/* -- Reaching a node by keyboard ---------------------------------------------------------------------------------------------------------------- */

export type Dir = "left" | "right" | "up" | "down";

/**
 * The node an arrow key goes to: the nearest one in that direction, preferring the ones almost straight ahead. From nothing it goes to the first
 * node. At the edge it wraps to the far side, so no key ever dead-ends. (PageDown and PageUp walk the list in order and reach everything.)
 */
export function nextNode(placed: Placed[], fromId: string | null, dir: Dir): string | null {
  if (placed.length === 0) return null;
  const from = fromId ? placed.find((p) => p.id === fromId) : undefined;
  if (!from) return placed[0].id;
  const horizontal = dir === "left" || dir === "right";
  const sign = dir === "right" || dir === "down" ? 1 : -1;
  // along: signed distance in the direction asked; across: how far off the line.
  const measure = (p: Placed) => ({ along: (horizontal ? p.x - from.x : p.y - from.y) * sign, across: Math.abs(horizontal ? p.y - from.y : p.x - from.x) });
  let best: { id: string; score: number } | null = null;
  for (const p of placed) {
    if (p.id === from.id) continue;
    const m = measure(p);
    if (m.along <= 0.5) continue;
    const score = m.along + 2 * m.across;
    if (!best || score < best.score) best = { id: p.id, score };
  }
  if (best) return best.id;
  // Nothing ahead: wrap to the far side, on the line closest to this node.
  let wrap: { id: string; score: number } | null = null;
  for (const p of placed) {
    if (p.id === from.id) continue;
    const m = measure(p);
    // The most negative `along` is the farthest node on the opposite side.
    const score = m.along + 2 * m.across;
    if (!wrap || score < wrap.score) wrap = { id: p.id, score };
  }
  return wrap ? wrap.id : from.id;
}

/** The next or previous node in list order, wrapping. Reaches every node, however the layout hides one behind another. */
export function stepNode(ids: string[], fromId: string | null, by: 1 | -1): string | null {
  if (ids.length === 0) return null;
  const i = fromId ? ids.indexOf(fromId) : -1;
  if (i < 0) return ids[by === 1 ? 0 : ids.length - 1];
  return ids[(i + by + ids.length) % ids.length];
}

/* -- When a name is shown ----------------------------------------------------------------------------------------------------------------------- */

export interface TipState {
  /** the node under the pointer */
  hover: string | null;
  /** the node the keyboard is on; pass it only while focus is visible, so a mouse click on the empty canvas does not name the first node */
  active: string | null;
  /** the node opened by a click, a tap or Enter: its name stays until Escape or another click */
  sel: string | null;
  /** Escape was pressed: the transient name stays hidden until the pointer or the keys move again (WCAG 1.4.13) */
  dismissed: boolean;
}

/** Whose name is on screen right now, if anyone: the hovered node, else the keyboard's, else the one a click pinned. */
export function tipFor(s: TipState): { id: string; pinned: boolean } | null {
  if (!s.dismissed) {
    if (s.hover) return { id: s.hover, pinned: s.hover === s.sel };
    if (s.active) return { id: s.active, pinned: s.active === s.sel };
  }
  return s.sel ? { id: s.sel, pinned: true } : null;
}

/** Where the name card goes: beside the node's box, inside the stage, never off it. Reuses the Hint's placement rule. */
export function tipPlace(anchor: { x: number; y: number; r: number }, size: { w: number; h: number }, stage: { w: number; h: number }): { x: number; y: number; side: "below" | "above" } {
  const reach = anchor.r + 3;
  return placeHint({ left: anchor.x - reach, top: anchor.y - reach, width: 2 * reach, height: 2 * reach }, size, stage, 6, 4);
}

/* -- Words for the node, for the card, the panel and the screen reader ------------------------------------------------------------------------ */

/** The accessible name of a node, which the canvas never draws. The smoke test and the screen readers both read this form. */
export function nodeAria(n: WorkNode, partner?: string): string {
  const pct = Math.round(Math.min(1, Math.max(0, Number.isFinite(n.strength) ? n.strength : 0)) * 100);
  return `${NODE_LABEL[n.type]}: ${n.label}. Strength ${pct} percent.${isLapsed(n) ? " Fading." : ""}${partner ? ` Always runs with ${partner}.` : ""}`;
}

/** The first sentence of a text, at most `maxWords` words (cut with an ellipsis when it runs on). For the one-line reason in the panel. */
export function firstSentence(text: string, maxWords = 24): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return "";
  const m = /^(.+?[.!?])(?:\s|$)/u.exec(t);
  const s = m ? m[1] : t;
  const words = s.split(" ");
  return words.length <= maxWords ? s : `${words.slice(0, maxWords).join(" ").replace(/[,;:]$/, "")}…`;
}

/** Links grouped by opacity into a few paths, so a graph of a thousand nodes draws a handful of elements instead of thousands of lines. */
export function linkBuckets(links: WorkLink[], at: Map<string, { x: number; y: number }>, strength: Map<string, number>, steps = 4): { opacity: number; d: string }[] {
  const out = new Map<number, string[]>();
  for (const l of links) {
    const a = at.get(l.a), b = at.get(l.b);
    if (!a || !b) continue;
    const o = linkOpacity(strength.get(l.a) ?? 0, strength.get(l.b) ?? 0);
    const bucket = Math.round(((o - 0.25) / 0.55) * (steps - 1));
    const key = 0.25 + (0.55 * bucket) / (steps - 1);
    const seg = `M${a.x.toFixed(1)} ${a.y.toFixed(1)}L${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
    (out.get(key) ?? out.set(key, []).get(key)!).push(seg);
  }
  return [...out.entries()].sort((x, y) => x[0] - y[0]).map(([opacity, segs]) => ({ opacity, d: segs.join("") }));
}

/** One path for a set of links, every link a straight line between its two placed nodes (a link to a node that is not placed is skipped). */
export function linkPath(links: WorkLink[], at: Map<string, { x: number; y: number }>): string {
  const segs: string[] = [];
  for (const l of links) {
    const a = at.get(l.a), b = at.get(l.b);
    if (a && b) segs.push(`M${a.x.toFixed(1)} ${a.y.toFixed(1)}L${b.x.toFixed(1)} ${b.y.toFixed(1)}`);
  }
  return segs.join("");
}

/** The envelope round two routines that always run together: a stadium from node a to node b, `R` beyond the larger of the two. */
export function capsule(ax: number, ay: number, bx: number, by: number, R: number): string {
  const dx = bx - ax, dy = by - ay;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const p = (x: number, y: number, s: number) => `${(x + nx * R * s).toFixed(1)},${(y + ny * R * s).toFixed(1)}`;
  return `M${p(ax, ay, 1)} L${p(bx, by, 1)} A${R},${R} 0 0 0 ${p(bx, by, -1)} L${p(ax, ay, -1)} A${R},${R} 0 0 0 ${p(ax, ay, 1)} Z`;
}
