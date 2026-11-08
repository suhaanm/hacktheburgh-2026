// The work graph's canvas: nodes with an icon each, hairline links, dashed envelopes for routines that always run together. It writes no text.
// A name shows in a card on hover, keyboard focus, or a click (which keeps it until Escape or another click). The whole canvas is one tab stop;
// the arrow keys move between nodes, Enter opens one, Escape closes. Every node keeps its accessible name in an aria-label.
// The look is the design system's "work graph" (colour is the kind, size is minutes or mastery, opacity is strength, a dashed ring is lapsed).
import { memo, useCallback, useEffect, useMemo, useRef, useState, type Ref } from "react";
import { prefersReducedMotion } from "../../hooks";
import { NODE_LABEL, capsule, cleanGraph, isLapsed, layoutGraph, linkBuckets, linkPath, nextNode, nodeAria, nodeOpacity, stepNode, tipFor, type Placed } from "../../lib/graph";
import { GLYPH_MIN_R, NODE_ICON, glyphSize } from "../../lib/nodeIcons";
import type { WorkGraph, WorkNode, WorkNodeType } from "../../types";
import { GlyphG, KindChip } from "./Glyph";
import { GraphTip } from "./GraphTip";
import "../../styles/graph.css";

/** Above this many nodes the canvas skips the intro and the slide between layouts, and draws plain dots: a thousand nodes must stay fast. */
export const BIG_GRAPH = 120;
/** Above this many nodes a node is a small silhouette of its kind rather than a disc with a glyph. */
export const DOT_GRAPH = 250;

/** Tween node positions between layouts so a merge or a deletion slides instead of jumping. */
function useTweened(target: Placed[], ms: number): Placed[] {
  const [pos, setPos] = useState<Placed[]>(target);
  const from = useRef<Placed[]>(target);
  const raf = useRef(0);
  useEffect(() => {
    cancelAnimationFrame(raf.current);
    if (prefersReducedMotion() || ms <= 0 || target.length > BIG_GRAPH) { from.current = target; setPos(target); return; }
    const start = performance.now();
    const a = new Map(from.current.map((p) => [p.id, p]));
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const next = target.map((p) => { const q = a.get(p.id) ?? p; return { id: p.id, r: p.r, x: q.x + (p.x - q.x) * e, y: q.y + (p.y - q.y) * e }; });
      from.current = next;
      setPos(next);
      if (t < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, ms]);
  return pos;
}

/** The small silhouette a node takes when the graph is too big for glyphs: the kind still shows by shape, not by colour alone. */
function Dot({ type, r, opacity }: { type: WorkNodeType; r: number; opacity: number }) {
  const style = { opacity };
  if (type === "memory") return <rect className="gnode__disc" x={-r} y={-r} width={2 * r} height={2 * r} rx={Math.min(2, r / 3)} style={style} />;
  if (type === "automation") return <rect className="gnode__disc" x={-r} y={-r} width={2 * r} height={2 * r} rx={Math.min(2, r / 3)} transform="rotate(45)" style={style} />;
  if (type === "skill") return <polygon className="gnode__disc" points={Array.from({ length: 6 }, (_, i) => { const a = (Math.PI / 3) * i + Math.PI / 6; return `${(Math.cos(a) * r * 1.12).toFixed(1)},${(Math.sin(a) * r * 1.12).toFixed(1)}`; }).join(" ")} style={style} />;
  return <circle className="gnode__disc" r={r} style={style} />;
}

/** One node: a disc of its kind with its glyph, a dashed ring when lapsed. Memoised: it redraws only when its own look or place changes. */
const NodeView = memo(function NodeView({ n, p, op, glyph, selected, partner, index, count, onPick, onEnter, onLeave }: {
  n: WorkNode; p: Placed; op: number; glyph: boolean; selected: boolean; partner: string | undefined; index: number; count: number;
  onPick: (id: string) => void; onEnter: (id: string, pointerType: string) => void; onLeave: (id: string) => void;
}) {
  const lapsed = isLapsed(n);
  return (
    <g id={`gn-${n.id}`} className="gnode" data-kind={n.type} data-sel={selected} data-lapsed={lapsed || undefined}
      role="option" aria-label={nodeAria(n, partner)} aria-selected={selected} aria-posinset={index + 1} aria-setsize={count}
      transform={`translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`}
      onClick={() => onPick(n.id)}
      onPointerEnter={(e) => onEnter(n.id, e.pointerType)}
      onPointerLeave={() => onLeave(n.id)}>
      {p.r < 12 && <circle className="gnode__hit" r={12} />}
      {glyph ? <circle className="gnode__disc" r={p.r} style={{ opacity: op }} /> : <Dot type={n.type} r={p.r} opacity={op} />}
      {glyph && <g className="gnode__ink"><GlyphG prims={NODE_ICON[n.type]} size={glyphSize(p.r)} /></g>}
      {lapsed && <circle className="gnode__lapsed" r={p.r + 1.5} />}
    </g>
  );
});

/** Is the keyboard focus visible (not the mouse's)? A browser without :focus-visible says yes. */
function focusVisible(el: Element): boolean {
  try { return el.matches(":focus-visible"); } catch { return true; }
}

export interface GraphCanvasProps {
  graph: WorkGraph;
  width: number;
  height: number;
  /** the node a click, a tap or Enter opened; its name stays on the canvas */
  selected: string | null;
  onSelect: (id: string | null) => void;
  svgRef?: Ref<SVGSVGElement>;
}

export function GraphCanvas({ graph: raw, width, height, selected, onSelect, svgRef }: GraphCanvasProps) {
  const graph = useMemo(() => cleanGraph(raw), [raw]);
  const count = graph.nodes.length;
  const big = count > BIG_GRAPH;
  const dots = count > DOT_GRAPH;

  // The intro: links and nodes fade in, then routines that always run together slide into one envelope. A big graph skips it.
  const [shown, setShown] = useState(big);
  const [combine, setCombine] = useState(big);
  useEffect(() => {
    if (big) { setShown(true); setCombine(true); return; }
    const a = window.setTimeout(() => setShown(true), 60);
    const b = window.setTimeout(() => setCombine(true), prefersReducedMotion() ? 0 : 900);
    return () => { window.clearTimeout(a); window.clearTimeout(b); };
  }, [big]);

  const target = useMemo(() => (width > 0 && height > 0 ? layoutGraph(graph, width, height, combine) : []), [graph, width, height, combine]);
  const pos = useTweened(target, 1100);
  const at = useMemo(() => new Map(pos.map((p) => [p.id, p])), [pos]);
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const order = useMemo(() => graph.nodes.map((n) => n.id), [graph]);
  const strength = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n.strength])), [graph]);
  const partner = useMemo(() => {
    const m = new Map<string, string>();
    for (const l of graph.links) if (l.kind === "combined") { const a = byId.get(l.a), b = byId.get(l.b); if (a && b) { m.set(a.id, b.label); m.set(b.id, a.label); } }
    return m;
  }, [graph, byId]);

  const [hover, setHover] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [kbd, setKbd] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  // A node that has gone (deleted) can no longer be hovered, active or open.
  useEffect(() => {
    if (hover && !byId.has(hover)) setHover(null);
    if (active && !byId.has(active)) setActive(null);
  }, [byId, hover, active]);

  const tip = tipFor({ hover, active: kbd ? active : null, sel: selected, dismissed });
  const emphasis = tip?.id ?? null;
  const tipNode = tip ? byId.get(tip.id) : undefined;
  const tipAt = tip ? at.get(tip.id) : undefined;

  const related = useMemo(() => graph.links.filter((l) => !(combine && l.kind === "combined")), [graph, combine]);
  const buckets = useMemo(() => linkBuckets(related, at, strength), [related, at, strength]);
  const hulls = combine ? graph.links.filter((l) => l.kind === "combined") : [];
  const incident = emphasis ? graph.links.filter((l) => l.a === emphasis || l.b === emphasis) : [];

  // Stable callbacks, so a hover or a key press re-renders the two nodes that changed and not the thousand that did not.
  const pick = useCallback((id: string) => { setActive(id); setDismissed(false); onSelect(id); }, [onSelect]);
  const enter = useCallback((id: string, pointerType: string) => { if (pointerType === "touch") return; setHover(id); setDismissed(false); }, []);
  const leave = useCallback((id: string) => setHover((h) => (h === id ? null : h)), []);

  const onKeyDown = (e: React.KeyboardEvent<SVGSVGElement>) => {
    const from = active ?? order[0] ?? null;
    const go = (id: string | null) => { if (id) { setActive(id); setKbd(true); setDismissed(false); } e.preventDefault(); };
    switch (e.key) {
      case "ArrowRight": return go(nextNode(pos, from, "right"));
      case "ArrowLeft": return go(nextNode(pos, from, "left"));
      case "ArrowDown": return go(nextNode(pos, from, "down"));
      case "ArrowUp": return go(nextNode(pos, from, "up"));
      case "PageDown": return go(stepNode(order, from, 1));
      case "PageUp": return go(stepNode(order, from, -1));
      case "Home": return go(order[0] ?? null);
      case "End": return go(order[order.length - 1] ?? null);
      case "Enter":
      case " ":
        if (from) { setActive(from); onSelect(from); setDismissed(false); e.preventDefault(); }
        return;
      case "Escape":
        setDismissed(true);
        onSelect(null);
        return;
    }
  };

  const chip = (n: WorkNode) => <KindChip kind={n.type} size={20} />;

  return (
    <>
      <svg ref={svgRef} className="gcanvas" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="listbox" tabIndex={0}
        aria-label={`Work graph with ${count} ${count === 1 ? "node" : "nodes"}. Use the arrow keys to move between nodes and Enter to open one.`}
        aria-activedescendant={active ? `gn-${active}` : undefined}
        data-dots={dots || undefined}
        onFocus={(e) => { setKbd(focusVisible(e.currentTarget)); if (!active && order[0] && focusVisible(e.currentTarget)) setActive(order[0]); setDismissed(false); }}
        onBlur={() => { setKbd(false); }}
        onKeyDown={onKeyDown}>
        <rect className="gcanvas__bg" width={width} height={height} onClick={() => onSelect(null)} />
        <g className="glinks" style={{ opacity: shown ? 1 : 0 }}>
          {buckets.map((b) => <path key={b.opacity} className="glink" d={b.d} style={{ opacity: b.opacity }} />)}
        </g>
        {hulls.map((l) => {
          const a = at.get(l.a), b = at.get(l.b);
          if (!a || !b) return null;
          return <path key={`h${l.a}${l.b}`} className="ghull" d={capsule(a.x, a.y, b.x, b.y, Math.max(a.r, b.r) + 9)} style={{ opacity: shown ? 1 : 0 }} />;
        })}
        {incident.length > 0 && <path className="glink glink--on" d={linkPath(incident, at)} aria-hidden="true" />}
        {graph.nodes.map((n, i) => {
          const p = at.get(n.id);
          if (!p) return null;
          return <NodeView key={n.id} n={n} p={p} op={shown ? nodeOpacity(n.strength) : 0} glyph={!dots && p.r >= GLYPH_MIN_R} selected={selected === n.id} partner={partner.get(n.id)} index={i} count={count} onPick={pick} onEnter={enter} onLeave={leave} />;
        })}
        {emphasis && at.get(emphasis) && (
          <g className="gring-layer" transform={`translate(${at.get(emphasis)!.x.toFixed(1)},${at.get(emphasis)!.y.toFixed(1)})`} aria-hidden="true">
            {hover === emphasis && <circle className="gring gring--hover" r={at.get(emphasis)!.r + 4} />}
            {kbd && active === emphasis && <circle className="gring gring--focus" r={at.get(emphasis)!.r + 4} />}
            {selected === emphasis && <circle className="gring gring--sel" r={at.get(emphasis)!.r + 7} />}
          </g>
        )}
      </svg>
      {tip && tipNode && tipAt && (
        <GraphTip anchor={{ x: tipAt.x, y: tipAt.y, r: tipAt.r }} stage={{ w: width, h: height }} pinned={tip.pinned}
          chip={chip(tipNode)} name={tipNode.label} meta={`${NODE_LABEL[tipNode.type]}${isLapsed(tipNode) ? ", fading" : ""}`} />
      )}
    </>
  );
}
