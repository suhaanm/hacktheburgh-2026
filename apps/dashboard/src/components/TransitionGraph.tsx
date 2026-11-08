import { useMemo, useState } from "react";
import { scaleSqrt } from "d3-scale";
import { useWidth } from "../hooks";
import { nextNode, stepNode, tipFor, type Placed } from "../lib/graph";
import { GLYPH_MIN_R, STEP_ICON, STEP_NAME, glyphSize, stepKind, type StepKind } from "../lib/nodeIcons";
import { edgeKind, layoutTransitions, type TNodePos } from "../lib/tgraph";
import { fmtPct } from "../lib/format";
import type { Transitions } from "../types";
import { GlyphG, KindChip } from "./graph/Glyph";
import { GraphLegend, type LegendEntry } from "./graph/GraphLegend";
import { GraphTip } from "./graph/GraphTip";
import "../styles/graph.css";

type Who = "expert" | "novice";
const words = (cog: string): string => { const t = cog.replace(/_/g, " ").toLowerCase(); return t.charAt(0).toUpperCase() + t.slice(1); };
const focusVisible = (el: Element): boolean => { try { return el.matches(":focus-visible"); } catch { return true; } };

/**
 * One person's flow: each step is a disc of the person's colour (the design system's expert and novice tokens) with an icon for what the step is;
 * a step this person never does is a dashed ring. No text is drawn: a name opens in a card on hover, focus or a click. One tab stop, arrow keys between
 * steps, Enter to keep a name open, Escape to close it.
 */
function Panel({ who, data, w, label }: { who: Who; data: Transitions; w: number; label: string }) {
  const { pos, height } = useMemo(() => layoutTransitions(data.nodes, data.edges, w), [data, w]);
  const maxDwell = Math.max(...data.nodes.flatMap((n) => [n.expert_dwell_s, n.novice_dwell_s]), 1);
  const maxFreq = Math.max(...data.edges.flatMap((e) => [e.expert_freq, e.novice_freq]), 1e-9);
  const perCase = maxFreq > 1.0001;
  const r = scaleSqrt().domain([0, maxDwell]).range([10, 17]);
  const tone: Who = who;
  const missing = data.edges.filter((e) => edgeKind(e, who) === "missing").length;
  const dwellOf = (n: TNodePos) => (who === "expert" ? n.expert : n.novice);
  const radiusOf = (n: TNodePos) => (dwellOf(n) <= 0 ? 9 : r(dwellOf(n)));
  const placed: Placed[] = useMemo(() => [...pos.values()].map((n) => ({ id: n.id, x: n.x, y: n.y, r: radiusOf(n) })), [pos]); // eslint-disable-line react-hooks/exhaustive-deps
  const order = useMemo(() => placed.map((p) => p.id), [placed]);
  const nameOf = (id: string) => words(pos.get(id)?.cog ?? id);

  const [hover, setHover] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [kbd, setKbd] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  // A step's accessible name carries what the edges would have shown: time spent, and the moves this person misses from it.
  const awayFrom = (id: string) => data.edges.filter((e) => e.from === id && edgeKind(e, who) === "missing").map((e) => nameOf(e.to));
  const ariaOf = (n: TNodePos) => {
    const d = dwellOf(n);
    const miss = who === "novice" ? awayFrom(n.id) : [];
    return `${words(n.cog)}. ${d > 0 ? `${Math.round(d)} seconds here` : "Not done here"}.${miss.length ? ` Missing ${miss.length === 1 ? "move" : "moves"} to ${miss.join(", ")}.` : ""}`;
  };

  // Nodes are keyed "n:id", edges "e:index", so one policy names either.
  const tip = tipFor({ hover, active: kbd ? (active ? `n:${active}` : null) : null, sel, dismissed });
  const tipNode = tip?.id.startsWith("n:") ? pos.get(tip.id.slice(2)) : undefined;
  const tipEdge = tip?.id.startsWith("e:") ? data.edges[Number(tip.id.slice(2))] : undefined;
  const focusId = tip?.id.startsWith("n:") ? tip.id.slice(2) : null;

  type Geo = { d: string; mx: number; my: number };
  const geo = (e: (typeof data.edges)[number]): Geo | null => {
    const a = pos.get(e.from), b = pos.get(e.to);
    if (!a || !b) return null;
    const ra = radiusOf(a), rb = radiusOf(b);
    if (e.from === e.to) return { d: `M${a.x - ra},${a.y - 2} C${a.x - ra - 28},${a.y - 18} ${a.x - ra - 28},${a.y + 18} ${a.x - ra},${a.y + 2}`, mx: a.x - ra - 24, my: a.y };
    if (b.layer > a.layer) {
      const span = b.layer - a.layer;
      const bulge = span > 1 ? (a.x <= b.x ? -1 : 1) * (22 + span * 8) : 0;
      const ay = a.y + ra + 1, by = b.y - rb - 1;
      const my = (ay + by) / 2;
      return { d: `M${a.x},${ay} C${a.x + bulge},${my} ${b.x + bulge},${my} ${b.x},${by}`, mx: (a.x + b.x) / 2 + bulge * 0.75, my };
    }
    // A move back up the flow, or sideways: loop round the left of the nodes.
    const out = 34 + 8 * Math.abs(a.layer - b.layer);
    return { d: `M${a.x - ra},${a.y} C${a.x - ra - out},${a.y} ${b.x - rb - out},${b.y} ${b.x - rb},${b.y}`, mx: Math.min(a.x - ra, b.x - rb) - out * 0.75, my: (a.y + b.y) / 2 };
  };
  // What the edge said when it was written on the canvas, now said in the card: how often, and whether it is a missing move or a detour.
  const edgeWords = (e: (typeof data.edges)[number], k: string) => {
    const amount = (f: number) => (perCase ? `${f.toFixed(1)} per case` : fmtPct(f));
    const name = `${nameOf(e.from)} to ${nameOf(e.to)}`;
    const planted = e.planted ? " (planted)" : "";
    if (k === "missing") return { name, meta: `${e.novice_freq < 0.05 ? `Missing; the expert makes it ${amount(e.expert_freq)}` : `Less often: ${amount(e.novice_freq)} against the expert's ${amount(e.expert_freq)}`}${planted}` };
    if (k === "extra") return { name, meta: `A detour, ${amount(e.novice_freq)}${planted}` };
    return { name, meta: amount(who === "expert" ? e.expert_freq : e.novice_freq) };
  };

  const tipAnchor = tipNode ? { x: tipNode.x, y: tipNode.y, r: radiusOf(tipNode) } : tipEdge ? (() => { const g = geo(tipEdge); return g ? { x: g.mx, y: g.my, r: 4 } : null; })() : null;
  const tipView = (() => {
    if (tipNode) { const d = dwellOf(tipNode); return { name: words(tipNode.cog), meta: d > 0 ? `${STEP_NAME[stepKind(tipNode.cog)]}, ${Math.round(d)} s here` : `${STEP_NAME[stepKind(tipNode.cog)]}, not done here`, chip: <KindChip step={stepKind(tipNode.cog)} tone={d > 0 ? tone : "muted"} size={20} /> }; }
    if (tipEdge) { const k = edgeKind(tipEdge, who); const t = edgeWords(tipEdge, k); return { name: t.name, meta: t.meta, chip: undefined }; }
    return null;
  })();

  const onKeyDown = (e: React.KeyboardEvent<SVGSVGElement>) => {
    const from = active ?? order[0] ?? null;
    const go = (id: string | null) => { if (id) { setActive(id); setKbd(true); setDismissed(false); } e.preventDefault(); };
    switch (e.key) {
      case "ArrowRight": return go(nextNode(placed, from, "right"));
      case "ArrowLeft": return go(nextNode(placed, from, "left"));
      case "ArrowDown": return go(nextNode(placed, from, "down"));
      case "ArrowUp": return go(nextNode(placed, from, "up"));
      case "PageDown": return go(stepNode(order, from, 1));
      case "PageUp": return go(stepNode(order, from, -1));
      case "Home": return go(order[0] ?? null);
      case "End": return go(order[order.length - 1] ?? null);
      case "Enter":
      case " ":
        if (from) { setActive(from); setSel(`n:${from}`); setDismissed(false); e.preventDefault(); }
        return;
      case "Escape": setDismissed(true); setSel(null); return;
    }
  };

  return (
    <div className="tgraph__col">
      <p className="t-label">{label}</p>
      <div className="tgraph__stage">
        <svg className="tgraph__svg" width={w} height={height} viewBox={`0 0 ${w} ${height}`} role="listbox" tabIndex={0}
          aria-label={`${label} transition graph.${who === "novice" ? ` ${missing} moves the expert makes that this person makes rarely or never.` : ""} Use the arrow keys to move between steps.`}
          aria-activedescendant={active ? `tg-${who}-${active}` : undefined}
          onFocus={(e) => { const v = focusVisible(e.currentTarget); setKbd(v); if (v && !active && order[0]) setActive(order[0]); setDismissed(false); }}
          onBlur={() => setKbd(false)}
          onKeyDown={onKeyDown}>
          <rect width={w} height={height} fill="transparent" onClick={() => setSel(null)} />
          {data.edges.map((e, i) => {
            const k = edgeKind(e, who);
            if (k === "none") return null;
            const g = geo(e);
            if (!g) return null;
            const nf = who === "expert" ? e.expert_freq : e.novice_freq;
            const freq = k === "missing" && nf < 0.05 ? e.expert_freq : nf;
            const cls = k === "missing" ? "tg-edge--missing" : k === "extra" ? "tg-edge--extra" : `tg-edge--${tone}`;
            const sw = k === "missing" ? 1.4 + 2 * (freq / maxFreq) : 0.8 + 3.2 * (freq / maxFreq);
            const on = focusId !== null && (e.from === focusId || e.to === focusId);
            return (
              <g key={i}>
                <path className={`tg-edge ${cls}${on ? " tg-edge--on" : ""}`} d={g.d} strokeWidth={on ? Math.max(sw, 2.5) : sw} aria-hidden="true" />
                <path className="tg-edge--hit" d={g.d} aria-hidden="true"
                  onPointerEnter={(ev) => { if (ev.pointerType === "touch") return; setHover(`e:${i}`); setDismissed(false); }}
                  onPointerLeave={() => setHover((h) => (h === `e:${i}` ? null : h))}
                  onClick={() => { setSel(`e:${i}`); setDismissed(false); }} />
              </g>
            );
          })}
          {[...pos.values()].map((n) => {
            const dwell = dwellOf(n);
            const absent = dwell <= 0;
            const rr = radiusOf(n);
            const kind: StepKind = stepKind(n.cog);
            return (
              <g key={n.id} id={`tg-${who}-${n.id}`} className="tgnode" role="option" aria-label={ariaOf(n)} aria-selected={sel === `n:${n.id}`}
                data-tone={absent ? "muted" : tone} data-active={(kbd && active === n.id) || undefined} data-absent={absent || undefined}
                transform={`translate(${n.x},${n.y})`}
                onClick={() => { setActive(n.id); setSel(`n:${n.id}`); setDismissed(false); }}
                onPointerEnter={(ev) => { if (ev.pointerType === "touch") return; setHover(`n:${n.id}`); setDismissed(false); }}
                onPointerLeave={() => setHover((h) => (h === `n:${n.id}` ? null : h))}>
                {rr < 12 && <circle className="gnode__hit" r={12} />}
                <circle className="tgnode__disc" r={rr} />
                <g className="tgnode__ink"><GlyphG prims={STEP_ICON[kind]} size={rr >= GLYPH_MIN_R ? glyphSize(rr) : 9} /></g>
              </g>
            );
          })}
          {focusId && pos.get(focusId) && (
            <g transform={`translate(${pos.get(focusId)!.x},${pos.get(focusId)!.y})`} aria-hidden="true">
              {hover === `n:${focusId}` && <circle className="gring gring--hover" r={radiusOf(pos.get(focusId)!) + 4} />}
              {kbd && active === focusId && <circle className="gring gring--focus" r={radiusOf(pos.get(focusId)!) + 4} />}
              {sel === `n:${focusId}` && <circle className="gring gring--sel" r={radiusOf(pos.get(focusId)!) + 7} />}
            </g>
          )}
        </svg>
        {tip && tipView && tipAnchor && (
          <GraphTip anchor={tipAnchor} stage={{ w, h: height }} pinned={tip.pinned} chip={tipView.chip} name={tipView.name} meta={tipView.meta} />
        )}
      </div>
    </div>
  );
}

/** What the transition graph's key shows: the kinds of step in this flow, then how size, thickness and the two dashed lines read. */
export function transitionLegend(data: Transitions): LegendEntry[] {
  const kinds = [...new Set(data.nodes.map((n) => stepKind(n.cog)))];
  const sw = { width: 30, height: 20, viewBox: "0 0 30 20", "aria-hidden": true as const, focusable: false as const };
  const steps = kinds.map((k): LegendEntry => ({ id: `step-${k}`, name: STEP_NAME[k], note: k === "step" ? "A step in the task." : `A step where the person is ${STEP_NAME[k].toLowerCase()}.`, group: "kind", graphic: <KindChip step={k} tone="expert" size={24} /> }));
  return [
    ...steps,
    { id: "size", name: "Size", note: "Time spent on that step.", group: "mark", graphic: <svg {...sw}><circle cx="8" cy="10" r="4" className="gk-fill" /><circle cx="21" cy="10" r="7" className="gk-fill" /></svg> },
    { id: "thick", name: "Thickness", note: "How often that move happens.", group: "mark", graphic: <svg {...sw}><path d="M2 6h26" className="gk-hair" /><path d="M2 13h26" className="gk-hair" style={{ strokeWidth: 3 }} /></svg> },
    { id: "missing", name: "Missing move", note: "The expert makes this move; the novice rarely or never does.", group: "mark", graphic: <svg {...sw}><path d="M2 10h26" className="gk-hair" style={{ stroke: "var(--bad)", strokeWidth: 2, strokeDasharray: "5 3" }} /></svg> },
    { id: "detour", name: "Detour", note: "A move only the novice makes.", group: "mark", graphic: <svg {...sw}><path d="M2 10h26" className="gk-hair" style={{ stroke: "var(--novice)", strokeWidth: 2, strokeDasharray: "2 3" }} /></svg> },
    { id: "absent", name: "Not done here", note: "A step this person never does.", group: "mark", graphic: <KindChip step="step" tone="muted" size={20} /> },
  ];
}

/** Genome graph: the same steps for expert and novice, side by side, with the moves the novice never makes in red. */
export function TransitionGraph({ data }: { data: Transitions }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const stacked = width > 0 && width < 720;
  const w = stacked ? width : Math.floor((width - 24) / 2);
  const legend = useMemo(() => transitionLegend(data), [data]);
  return (
    <div className="stack">
      <div ref={ref} className="tgraph" style={stacked ? { gridTemplateColumns: "1fr" } : undefined}>
        {width > 0 && (
          <>
            <Panel who="expert" data={data} w={w} label="Expert" />
            <Panel who="novice" data={data} w={w} label="Novice" />
          </>
        )}
      </div>
      <GraphLegend entries={legend} label="How to read the transition graph" />
    </div>
  );
}
