import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { scaleSqrt } from "d3-scale";
import type { WorkGraph, WorkNode, WorkNodeType } from "../types";

export const NODE_COLOUR: Record<WorkNodeType, string> = {
  routine: "var(--accent)",
  skill: "var(--novice)",
  memory: "var(--expert)",
  automation: "var(--good)",
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
  const scales: Record<WorkNodeType, (v: number) => number> = {
    routine: scaleSqrt().domain([0, maxOf("routine")]).range([8, 30]),
    automation: scaleSqrt().domain([0, maxOf("automation")]).range([8, 22]),
    skill: scaleSqrt().domain([0, 1]).range([7, 20]),
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
