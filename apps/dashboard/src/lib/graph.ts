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
  const ring = (i: number, n: number) => ({ x: width / 2 + Math.cos((i / n) * 6.2832) * width * 0.3, y: height / 2 + Math.sin((i / n) * 6.2832) * height * 0.3 });
  const nodes: SimNode[] = graph.nodes.map((n, i) => ({ id: n.id, r: r(n), ...ring(i, graph.nodes.length) }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = graph.links
    .filter((l) => byId.has(l.a) && byId.has(l.b))
    .map((l) => ({ source: l.a, target: l.b, kind: l.kind, weight: l.weight }));
  const sim = forceSimulation(nodes as never)
    .randomSource(lcg(7))
    .force("charge", forceManyBody().strength(-170))
    .force("center", forceCenter(width / 2, height / 2))
    .force("x", forceX(width / 2).strength(0.04))
    .force("y", forceY(height / 2).strength(0.06))
    .force("collide", forceCollide<SimNode>().radius((d) => d.r + 14))
    .force(
      "link",
      forceLink(links as never)
        .id((d) => (d as SimNode).id)
        .distance((l) => {
          const k = (l as unknown as { kind: string; weight: number }).kind;
          const w = (l as unknown as { weight: number }).weight;
          return combine && k === "combined" ? 6 : 150 - 70 * w;
        })
        .strength((l) => {
          const k = (l as unknown as { kind: string; weight: number }).kind;
          const w = (l as unknown as { weight: number }).weight;
          return combine && k === "combined" ? 1 : 0.15 + 0.35 * w;
        }),
    )
    .stop();
  if (combine) {
    // A combined pair is one object: let the two members overlap.
    sim.force("collide", forceCollide<SimNode>().radius((d) => d.r + 14).strength(0.9));
  }
  for (let i = 0; i < 320; i++) sim.tick();
  const pad = 40;
  return nodes.map((n) => ({
    id: n.id,
    r: n.r,
    x: Math.min(width - pad, Math.max(pad, n.x)),
    y: Math.min(height - pad, Math.max(pad, n.y)),
  }));
}

function lcg(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}
