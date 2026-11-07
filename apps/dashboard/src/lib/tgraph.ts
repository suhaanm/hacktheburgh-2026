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

/**
 * Layers for a flow that may contain cycles (re-checks, self loops). A depth-first walk from the first step,
 * following the busiest moves first, marks the moves that point back up the flow; those are left out when
 * layering, so the main route reads top to bottom. Then longest-path layers on what remains.
 */
export function layers(nodes: TransitionNode[], edges: TransitionEdge[]): Map<string, number> {
  const adj = new Map<string, { to: string; w: number }[]>();
  for (const n of nodes) adj.set(n.id, []);
  for (const e of edges) {
    if (e.from === e.to || !adj.has(e.from) || !adj.has(e.to)) continue;
    adj.get(e.from)!.push({ to: e.to, w: Math.max(e.expert_freq, e.novice_freq) });
  }
  for (const list of adj.values()) list.sort((a, b) => b.w - a.w);
  const state = new Map<string, 0 | 1 | 2>(nodes.map((n) => [n.id, 0]));
  const dag: [string, string][] = [];
  const visit = (u: string) => {
    state.set(u, 1);
    for (const { to } of adj.get(u) ?? []) {
      if (state.get(to) === 1) continue; // a move back up the flow
      dag.push([u, to]);
      if (state.get(to) === 0) visit(to);
    }
    state.set(u, 2);
  };
  const first = nodes.find((n) => n.cog === "READ") ?? nodes[0];
  const roots = [first, ...nodes.filter((n) => n !== first)];
  for (const r of roots) if (r && state.get(r.id) === 0) visit(r.id);
  const layer = new Map(nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < nodes.length; pass++) {
    let moved = false;
    for (const [u, v] of dag) {
      if ((layer.get(v) ?? 0) < (layer.get(u) ?? 0) + 1) { layer.set(v, (layer.get(u) ?? 0) + 1); moved = true; }
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
  if (e.extra_for_novice || (nv && !ex)) return "extra";
  return nv ? "shared" : "none";
}
