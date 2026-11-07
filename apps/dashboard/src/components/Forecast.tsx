import { useWidth } from "../hooks";
import { area, line } from "d3-shape";
import { scaleLinear } from "d3-scale";
import { longestWindow, survivalAt } from "../lib/forecast";
import type { Presence } from "../types";

/** Window forecast: the chance a quiet window lasts at least D minutes, with the decision threshold. */
export function Forecast({ data, d }: { data: Presence; d: number }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const pts = data.forecast;
  const m = { l: 40, r: 12, t: 12, b: 38 };
  const h = 250;
  const maxD = pts[pts.length - 1]?.d_min ?? 240;
  const x = scaleLinear().domain([0, maxD]).range([m.l, Math.max(m.l + 100, width - m.r)]);
  const y = scaleLinear().domain([0, 1]).range([h - m.b, m.t]);
  const thr = data.decision_threshold;
  const best = longestWindow(pts, thr);
  const hasBand = pts.some((p) => p.lo != null && p.hi != null);
  const a = area<(typeof pts)[number]>().x((p) => x(p.d_min)).y0((p) => y(p.lo ?? p.survival)).y1((p) => y(p.hi ?? p.survival));
  const l = line<(typeof pts)[number]>().x((p) => x(p.d_min)).y((p) => y(p.survival));
  const s = survivalAt(pts, d);
  return (
    <div ref={box} className="chart">
      {width > 0 && (
        <svg width={width} height={h} viewBox={`0 0 ${width} ${h}`} role="img"
          aria-label={`Window forecast. Chance a window lasts at least D minutes falls as D grows. Decision threshold ${Math.round(thr * 100)} percent, crossed at about ${best} minutes.`}>
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <g key={v}>
              <line className="svg-grid" x1={m.l} x2={width - m.r} y1={y(v)} y2={y(v)} />
              <text className="svg-text" x={m.l - 6} y={y(v) + 3.5} textAnchor="end">{Math.round(v * 100)}%</text>
            </g>
          ))}
          {x.ticks(6).map((t) => (
            <text key={t} className="svg-text" x={x(t)} y={h - m.b + 16} textAnchor="middle">{t}</text>
          ))}
          <text className="svg-text" x={(m.l + width - m.r) / 2} y={h - 6} textAnchor="middle">Run length D, minutes</text>
          {hasBand && <path className="curve-band" d={a(pts) ?? ""} />}
          <path className="curve" d={l(pts) ?? ""} />
          <line className="thr-line" x1={m.l} x2={width - m.r} y1={y(thr)} y2={y(thr)} />
          <text className="thr-text" x={width - m.r} y={y(thr) - 6} textAnchor="end">Start only above {Math.round(thr * 100)}%</text>
          <line x1={x(best)} x2={x(best)} y1={y(thr)} y2={h - m.b} style={{ stroke: "var(--good)", strokeWidth: 1.5 }} />
          <circle className="win-mark" cx={x(best)} cy={y(thr)} r={5} />
          <text className="svg-text svg-text--strong" x={x(best) + 8} y={h - m.b - 8}>{best} min</text>
          <line x1={x(d)} x2={x(d)} y1={m.t} y2={h - m.b} style={{ stroke: "var(--accent)", strokeWidth: 1.5 }} />
          <circle cx={x(d)} cy={y(s)} r={4.5} style={{ fill: "var(--accent)", stroke: "var(--bg)", strokeWidth: 2 }} />
        </svg>
      )}
    </div>
  );
}
