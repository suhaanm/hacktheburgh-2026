import { useWidth } from "../hooks";
import { edgeKind, layoutTransitions } from "../lib/tgraph";
import { LegendItem } from "./common";
import { fmtPct } from "../lib/format";
import type { Transitions } from "../types";
import { scaleSqrt } from "d3-scale";

function Panel({ who, data, w, label }: { who: "expert" | "novice"; data: Transitions; w: number; label: string }) {
  const { pos, height } = layoutTransitions(data.nodes, data.edges, w);
  const maxDwell = Math.max(...data.nodes.flatMap((n) => [n.expert_dwell_s, n.novice_dwell_s]), 1);
  const r = scaleSqrt().domain([0, maxDwell]).range([4, 13]);
  const colour = who === "expert" ? "expert" : "novice";
  return (
    <div className="tgraph__col">
      <p className="t-label">{label}</p>
      <svg width={w} height={height} viewBox={`0 0 ${w} ${height}`} role="img"
        aria-label={`${label} transition graph. ${data.edges.filter((e) => edgeKind(e, who) === "missing").length} moves the expert makes that this person never does.`}>
        {data.edges.map((e, i) => {
          const k = edgeKind(e, who);
          if (k === "none") return null;
          const a = pos.get(e.from), b = pos.get(e.to);
          if (!a || !b) return null;
          const freq = who === "expert" ? e.expert_freq : k === "missing" ? e.expert_freq : e.novice_freq;
          const span = b.layer - a.layer;
          const bulge = span > 1 ? (a.x <= b.x ? -1 : 1) * (28 + span * 8) * (a.x === b.x ? 1 : 0.4) : (b.x - a.x) * 0;
          const ay = a.y + r(who === "expert" ? a.expert : a.novice) + 1, by = b.y - r(who === "expert" ? b.expert : b.novice) - 1;
          const my = (ay + by) / 2;
          const d = `M${a.x},${ay} C${a.x + bulge},${my} ${b.x + bulge},${my} ${b.x},${by}`;
          const cls = k === "missing" ? "tg-edge--missing" : k === "extra" ? "tg-edge--extra" : `tg-edge--${colour}`;
          const sw = k === "missing" ? 2 : 0.8 + freq * 2.6;
          return (
            <g key={i}>
              <path className={`tg-edge ${cls}`} d={d} strokeWidth={sw} />
              {k === "missing" && <text className="rb-lost-text" x={(a.x + b.x) / 2 + (a.x === b.x ? 10 : 0)} y={my + 3} style={{ paintOrder: "stroke", stroke: "var(--bg)", strokeWidth: 3 }}>missing{e.planted ? " (planted)" : ""}</text>}
              {k === "shared" && freq < 0.9 && <text className="svg-text" x={(a.x + b.x) / 2 + 6} y={my + 3}>{fmtPct(freq)}</text>}
            </g>
          );
        })}
        {[...pos.values()].map((n) => {
          const dwell = who === "expert" ? n.expert : n.novice;
          const absent = dwell <= 0;
          return (
            <g key={n.id}>
              <circle className={`tg-node ${absent ? "tg-node--absent" : `tg-node--${colour}`}`} cx={n.x} cy={n.y} r={absent ? 5 : r(dwell)} />
              <text className={`tg-text${absent ? " tg-text--absent" : ""}`} x={n.x + (absent ? 9 : r(dwell) + 6)} y={n.y + 3.5}>{n.cog.replace(/_/g, " ")}{!absent ? ` ${Math.round(dwell)} s` : ""}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** Genome graph: the same cogs for expert and novice, side by side, with the moves the novice never makes in red. */
export function TransitionGraph({ data }: { data: Transitions }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const stacked = width > 0 && width < 720;
  const w = stacked ? width : Math.floor((width - 24) / 2);
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
      <ul className="legend" aria-label="How to read the graph">
        <LegendItem swatch={<span className="sw sw--dot sw--expert" />}>Circle size is time spent on that step</LegendItem>
        <LegendItem swatch={<span className="sw sw--line sw--muted" />}>Line thickness is how often that move follows the step</LegendItem>
        <LegendItem swatch={<span className="sw sw--dashed sw--bad" />}>Red dashed: the expert makes this move, the novice never does</LegendItem>
        <LegendItem swatch={<span className="sw sw--dashed sw--novice" />}>Dotted: a detour only the novice takes</LegendItem>
      </ul>
    </div>
  );
}
