import type { TransitionEdge, TransitionNode } from "../types";

export interface TNodePos {
  id: string;
  cog: string;
  x: number;
  y: number;
  layer: number;
  expert: number;
  novice: number;
}

/** Longest-path layers from the sources; cycles are tolerated by capping the passes. */
export function layers(nodes: TransitionNode[], edges: TransitionEdge[]): Map<string, number> {
  const layer = new Map(nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < nodes.length; pass++) {
    let moved = false;
    for (const e of edges) {
      const a = layer.get(e.from), b = layer.get(e.to);
      if (a == null || b == null) continue;
      if (b < a + 1 && a + 1 <= nodes.length) { layer.set(e.to, a + 1); moved = true; }
    }
    if (!moved) break;
  }
  return layer;
}

/** Top-to-bottom flow, one row per layer, nodes in a shared layer spread across the width. */
export function layoutTransitions(nodes: TransitionNode[], edges: TransitionEdge[], width: number, rowH = 46, padTop = 22): { pos: Map<string, TNodePos>; height: number } {
  const L = layers(nodes, edges);
  const byLayer = new Map<number, TransitionNode[]>();
  for (const n of nodes) {
    const l = L.get(n.id) ?? 0;
    byLayer.set(l, [...(byLayer.get(l) ?? []), n]);
  }
  const pos = new Map<string, TNodePos>();
  const maxLayer = Math.max(0, ...byLayer.keys());
  for (const [l, ns] of byLayer) {
    ns.forEach((n, i) => {
      const count = ns.length;
      // One node sits in the middle; several spread across the middle half of the width.
      const x = count === 1 ? width * 0.45 : width * (0.25 + (0.5 * i) / (count - 1));
      pos.set(n.id, { id: n.id, cog: n.cog, x, y: padTop + l * rowH, layer: l, expert: n.expert_dwell_s, novice: n.novice_dwell_s });
    });
  }
  return { pos, height: padTop * 2 + maxLayer * rowH };
}

export type EdgeKind = "shared" | "missing" | "extra" | "none";

/** How an edge looks for one person. `missing` = the expert takes it, the novice never does. `extra` = only the novice takes it. */
export function edgeKind(e: TransitionEdge, who: "expert" | "novice", floor = 0.05): EdgeKind {
  const ex = e.expert_freq >= floor, nv = e.novice_freq >= floor;
  if (who === "expert") return ex ? "shared" : "none";
  if (e.missing_for_novice || (ex && !nv)) return "missing";
  if (nv && !ex) return "extra";
  return nv ? "shared" : "none";
}
