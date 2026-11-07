import { useWidth } from "../hooks";
import { edgeKind, layoutTransitions } from "../lib/tgraph";
import { LegendItem } from "./common";
import { fmtPct } from "../lib/format";
import type { Transitions } from "../types";
import { scaleSqrt } from "d3-scale";

function Panel({ who, data, w, label }: { who: "expert" | "novice"; data: Transitions; w: number; label: string }) {
  const { pos, height } = layoutTransitions(data.nodes, data.edges, w);
  const maxDwell = Math.max(...data.nodes.flatMap((n) => [n.expert_dwell_s, n.novice_dwell_s]), 1);
  const maxFreq = Math.max(...data.edges.flatMap((e) => [e.expert_freq, e.novice_freq]), 1e-9);
  const perCase = maxFreq > 1.0001;
  const r = scaleSqrt().domain([0, maxDwell]).range([4, 13]);
  const colour = who === "expert" ? "expert" : "novice";
  const missing = data.edges.filter((e) => edgeKind(e, who) === "missing").length;
  const rad = (id: string) => { const n = pos.get(id)!; return r(who === "expert" ? n.expert : n.novice); };
  return (
    <div className="tgraph__col">
      <p className="t-label">{label}</p>
      <svg width={w} height={height} viewBox={`0 0 ${w} ${height}`} role="img"
        aria-label={`${label} transition graph.${who === "novice" ? ` ${missing} moves the expert makes that this person makes rarely or never.` : ""}`}>
        {data.edges.map((e, i) => {
          const k = edgeKind(e, who);
          if (k === "none") return null;
          const a = pos.get(e.from), b = pos.get(e.to);
          if (!a || !b) return null;
          const nf = who === "expert" ? e.expert_freq : e.novice_freq;
          const freq = k === "missing" && nf < 0.05 ? e.expert_freq : nf;
          const ra = rad(e.from), rb = rad(e.to);
          let d: string;
          let mx: number, my: number;
          if (e.from === e.to) {
            d = `M${a.x - ra},${a.y - 2} C${a.x - ra - 28},${a.y - 18} ${a.x - ra - 28},${a.y + 18} ${a.x - ra},${a.y + 2}`;
            mx = a.x - ra - 24; my = a.y;
          } else if (b.layer > a.layer) {
            const span = b.layer - a.layer;
            const bulge = span > 1 ? (a.x <= b.x ? -1 : 1) * (22 + span * 8) : 0;
            const ay = a.y + ra + 1, by = b.y - rb - 1;
            my = (ay + by) / 2; mx = (a.x + b.x) / 2 + bulge * 0.75;
            d = `M${a.x},${ay} C${a.x + bulge},${my} ${b.x + bulge},${my} ${b.x},${by}`;
          } else {
            // A move back up the flow, or sideways: loop round the left of the nodes.
            const out = 34 + 8 * Math.abs(a.layer - b.layer);
            d = `M${a.x - ra},${a.y} C${a.x - ra - out},${a.y} ${b.x - rb - out},${b.y} ${b.x - rb},${b.y}`;
            mx = Math.min(a.x - ra, b.x - rb) - out * 0.75; my = (a.y + b.y) / 2;
          }
          const cls = k === "missing" ? "tg-edge--missing" : k === "extra" ? "tg-edge--extra" : `tg-edge--${colour}`;
          const sw = k === "missing" ? 1.4 + 2 * (freq / maxFreq) : 0.8 + 3.2 * (freq / maxFreq);
          const amount = perCase ? `${freq.toFixed(1)} per case` : fmtPct(freq);
          return (
            <g key={i}>
              <path className={`tg-edge ${cls}`} d={d} strokeWidth={sw}><title>{`${e.from.replace(/_/g, " ")} to ${e.to.replace(/_/g, " ")}: ${amount}`}</title></path>
              {k === "missing" && <text className="rb-lost-text" x={mx + 6} y={my + 3} style={{ paintOrder: "stroke", stroke: "var(--bg)", strokeWidth: 3 }}>{e.novice_freq < 0.05 ? "missing" : "less often"}{e.planted ? " (planted)" : ""}</text>}
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
        <LegendItem swatch={<span className="sw sw--line sw--muted" />}>Line thickness is how often that move happens</LegendItem>
        <LegendItem swatch={<span className="sw sw--dashed sw--bad" />}>Red dashed: the expert makes this move, the novice rarely or never does</LegendItem>
        <LegendItem swatch={<span className="sw sw--dashed sw--novice" />}>Dotted: a detour only the novice takes</LegendItem>
      </ul>
    </div>
  );
}
