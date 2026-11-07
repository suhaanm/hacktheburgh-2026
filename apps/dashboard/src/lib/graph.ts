import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { scaleSqrt } from "d3-scale";
import type { WorkGraph, WorkNode, WorkNodeType } from "../types";

export const NODE_COLOUR: Record<WorkNodeType, string> = {
  routine: "var(--node-routine)",
  skill: "var(--node-skill)",
  memory: "var(--node-memory)",
  automation: "var(--fg)",
};

export const NODE_LABEL: Record<WorkNodeType, string> = {
  routine: "Routine",
  skill: "Skill",
  memory: "Memory",
  automation: "Automation",
};

/** Opacity is strength. A floor keeps even a faded node findable. */
export function nodeOpacity(strength: number): number {
  return 0.22 + 0.78 * Math.min(1, Math.max(0, strength));
}

/** Size per type: routines and automations by weekly minutes, skills by mastery, memory fixed. */
export function radiusFn(nodes: WorkNode[]): (n: WorkNode) => number {
  const maxOf = (t: WorkNodeType) => Math.max(1, ...nodes.filter((n) => n.type === t).map((n) => n.size));
  // Each type is scaled to its own largest value, so a service that sends skill sizes as mastery (0 to 1) or as anything else still draws sensibly.
  const scales: Record<WorkNodeType, (v: number) => number> = {
    routine: scaleSqrt().domain([0, maxOf("routine")]).range([8, 30]).clamp(true),
    automation: scaleSqrt().domain([0, maxOf("automation")]).range([8, 22]).clamp(true),
    skill: scaleSqrt().domain([0, maxOf("skill")]).range([7, 20]).clamp(true),
    memory: () => 9,
  };
  return (n) => scales[n.type](n.size);
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

/**
 * Deterministic layout: the simulation runs to rest before anything is drawn, so nodes do not
 * jitter on screen. `combine` makes combined pairs sit together; without it they stay apart, which
 * lets the screen animate the merge.
 */
export function layoutGraph(graph: WorkGraph, width: number, height: number, combine: boolean): Placed[] {
  const r = radiusFn(graph.nodes);
  const tall = height > width * 1.2;
  const ring = (i: number, n: number) => ({ x: width / 2 + Math.cos((i / n) * 6.2832) * width * 0.34, y: height / 2 + Math.sin((i / n) * 6.2832) * height * 0.34 });
  const nodes: SimNode[] = graph.nodes.map((n, i) => ({ id: n.id, r: r(n), ...ring(i, graph.nodes.length) }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = graph.links
    .filter((l) => byId.has(l.a) && byId.has(l.b))
    .map((l) => ({ source: l.a, target: l.b, kind: l.kind, weight: l.weight }));
  type L = { kind: string; weight: number; source: SimNode; target: SimNode };
  const sim = forceSimulation(nodes as never)
    .randomSource(lcg(7))
    .force("charge", forceManyBody().strength(-520).distanceMax(520))
    .force("center", forceCenter(width / 2, height / 2))
    // A tall, narrow canvas (a phone) gets its spread along the long side.
    .force("x", forceX(width / 2).strength(tall ? 0.09 : 0.025))
    .force("y", forceY(height / 2).strength(tall ? 0.008 : 0.04))
    .force("collide", forceCollide<SimNode>().radius((d) => d.r + (tall ? 30 : 24)).strength(1).iterations(3))
    .force(
      "link",
      forceLink(links as never)
        .id((d) => (d as SimNode).id)
        .distance((l) => {
          const k = l as unknown as L;
          if (combine && k.kind === "combined") return k.source.r + k.target.r + 30;
          return 150 - 60 * k.weight + k.source.r + k.target.r;
        })
        .strength((l) => {
          const k = l as unknown as L;
          return combine && k.kind === "combined" ? 1 : 0.1 + 0.3 * k.weight;
        }),
    )
    .stop();
  for (let i = 0; i < 420; i++) sim.tick();
  // Fit the settled layout into the canvas with a margin for labels.
  const mx = 70, my = 44;
  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = x1 > x0 ? (width - 2 * mx) / (x1 - x0) : 1;
  const sy = y1 > y0 ? (height - 2 * my) / (y1 - y0) : 1;
  const k = Math.min(1.35, sx, sy > 1.35 ? 1.35 : sy);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  return nodes.map((n) => ({
    id: n.id,
    r: n.r,
    x: width / 2 + (n.x - cx) * Math.min(sx, 1.5),
    y: height / 2 + (n.y - cy) * Math.min(sy, 1.5) * (k > 0 ? 1 : 1),
  }));
}

function lcg(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}

export interface LabelItem { id: string; x: number; y: number; r: number; text: string; priority: number }
export interface LabelPlace { dx: number; dy: number; anchor: "start" | "middle" | "end"; hidden: boolean; w: number; box: [number, number, number, number] }

const CHAR_W = 5.8;
const LABEL_H = 13;

/**
 * Put each label where it collides with no other label and no other node, trying below, above, right, then left.
 * The most important nodes choose first. If no spot is clear, the label is hidden (the node keeps its tooltip),
 * unless it is the selected node, which always gets a label.
 */
export function placeLabels(items: LabelItem[], width: number, height: number, forced: string | null = null): Map<string, LabelPlace> {
  const out = new Map<string, LabelPlace>();
  const placed: [number, number, number, number][] = [];
  const hit = (a: [number, number, number, number], b: [number, number, number, number], pad = 2) => a[0] < b[2] + pad && a[2] > b[0] - pad && a[1] < b[3] + pad && a[3] > b[1] - pad;
  const circleHit = (b: [number, number, number, number], n: LabelItem) => {
    const cx = Math.max(b[0], Math.min(n.x, b[2])), cy = Math.max(b[1], Math.min(n.y, b[3]));
    return Math.hypot(cx - n.x, cy - n.y) < n.r + 2;
  };
  const order = [...items].sort((a, b) => (a.id === forced ? -1 : b.id === forced ? 1 : b.priority - a.priority));
  for (const n of order) {
    const w = n.text.length * CHAR_W;
    const cands: { dx: number; dy: number; anchor: "start" | "middle" | "end" }[] = [
      { dx: 0, dy: n.r + 15, anchor: "middle" },
      { dx: 0, dy: -n.r - 8, anchor: "middle" },
      { dx: n.r + 6, dy: 4, anchor: "start" },
      { dx: -n.r - 6, dy: 4, anchor: "end" },
    ];
    const boxOf = (c: (typeof cands)[number]): [number, number, number, number] => {
      const ty = n.y + c.dy;
      const x0 = c.anchor === "middle" ? n.x - w / 2 : c.anchor === "start" ? n.x + c.dx : n.x + c.dx - w;
      return [x0, ty - LABEL_H + 3, x0 + w, ty + 3];
    };
    const inside = (b: [number, number, number, number]) => b[0] >= 2 && b[2] <= width - 2 && b[1] >= 2 && b[3] <= height - 2;
    const others = items.filter((o) => o.id !== n.id);
    const clear = cands.find((c) => { const b = boxOf(c); return inside(b) && !placed.some((p) => hit(b, p)) && !others.some((o) => circleHit(b, o)); });
    // No clear spot: hide the label (its node keeps a tooltip) rather than print it over another node. The selected node always gets one.
    const soft = clear ?? (n.id === forced ? cands.find((c) => { const b = boxOf(c); return inside(b) && !placed.some((p) => hit(b, p)); }) : undefined);
    if (soft) { const b = boxOf(soft); placed.push(b); out.set(n.id, { dx: soft.dx, dy: soft.dy, anchor: soft.anchor, hidden: false, w, box: b }); }
    else if (n.id === forced) { const c = cands[0]; out.set(n.id, { dx: c.dx, dy: c.dy, anchor: c.anchor, hidden: false, w, box: boxOf(c) }); }
    else out.set(n.id, { dx: 0, dy: n.r + 15, anchor: "middle", hidden: true, w, box: boxOf(cands[0]) });
  }
  return out;
}
