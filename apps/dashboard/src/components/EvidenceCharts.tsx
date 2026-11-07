import { useWidth } from "../hooks";
import { area, line } from "d3-shape";
import { scaleLinear, scaleSqrt } from "d3-scale";
import { fmtPctInterval } from "../lib/format";
import type { Interval } from "../types";

export interface RelPoint { p_mean: number; freq: number; n: number }

/** Reliability diagram: predicted chance against how often it happened. On the dashed diagonal means calibrated. Dot area is the number of cases. */
export function Reliability({ points, label }: { points: RelPoint[]; label: string }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const size = Math.min(width || 420, 440);
  const m = { l: 44, r: 12, t: 12, b: 40 };
  const side = size - m.l - m.r;
  const h = side + m.t + m.b;
  const x = scaleLinear().domain([0, 1]).range([m.l, m.l + side]);
  const y = scaleLinear().domain([0, 1]).range([m.t + side, m.t]);
  const r = scaleSqrt().domain([0, Math.max(...points.map((p) => p.n), 1)]).range([2.5, 10]);
  const l = line<RelPoint>().x((p) => x(p.p_mean)).y((p) => y(p.freq));
  const sorted = [...points].sort((a, b) => a.p_mean - b.p_mean);
  return (
    <div ref={box} className="chart">
      {width > 0 && (
        <svg width={size} height={h} viewBox={`0 0 ${size} ${h}`} role="img" aria-label={`${label}. Reliability diagram: ${sorted.map((p) => `predicted ${Math.round(p.p_mean * 100)} percent, observed ${Math.round(p.freq * 100)} percent over ${p.n} cases`).join("; ")}.`}>
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <g key={v}>
              <line className="svg-grid" x1={x(v)} x2={x(v)} y1={y(0)} y2={y(1)} />
              <line className="svg-grid" x1={x(0)} x2={x(1)} y1={y(v)} y2={y(v)} />
              <text className="svg-text" x={x(v)} y={y(0) + 15} textAnchor="middle">{Math.round(v * 100)}</text>
              <text className="svg-text" x={m.l - 8} y={y(v) + 3.5} textAnchor="end">{Math.round(v * 100)}</text>
            </g>
          ))}
          <line className="ev-diag" x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} />
          <path className="ev-line" d={l(sorted) ?? ""} />
          {sorted.map((p) => (
            <circle key={p.p_mean} className="ev-pt" cx={x(p.p_mean)} cy={y(p.freq)} r={r(p.n)}><title>{`Predicted ${Math.round(p.p_mean * 100)}%, observed ${Math.round(p.freq * 100)}%, ${p.n} cases`}</title></circle>
          ))}
          <text className="ev-axis-label" x={m.l + side / 2} y={h - 6} textAnchor="middle">Predicted chance, %</text>
          <text className="ev-axis-label" transform={`translate(12,${m.t + side / 2}) rotate(-90)`} textAnchor="middle">Happened, %</text>
        </svg>
      )}
    </div>
  );
}

export interface RcPoint { coverage: number; risk: number; ci: Interval }

/** Risk-coverage: the more cases auto-approved (coverage), the higher the error rate. The dashed line is the target. */
export function RiskCoverage({ curve, alpha, chosen, heldOut }: { curve: RcPoint[]; alpha: number; chosen?: number; heldOut?: { value: number; ci: Interval } }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const m = { l: 48, r: 14, t: 14, b: 42 };
  const h = 280;
  const maxY = Math.max(alpha * 2, ...curve.map((c) => c.ci[1]), heldOut?.ci[1] ?? 0) * 1.1;
  const x = scaleLinear().domain([0, 1]).range([m.l, Math.max(m.l + 120, width - m.r)]);
  const y = scaleLinear().domain([0, maxY]).range([h - m.b, m.t]).nice();
  const a = area<RcPoint>().x((p) => x(p.coverage)).y0((p) => y(p.ci[0])).y1((p) => y(p.ci[1]));
  const l = line<RcPoint>().x((p) => x(p.coverage)).y((p) => y(p.risk));
  return (
    <div ref={box} className="chart">
      {width > 0 && (
        <svg width={width} height={h} viewBox={`0 0 ${width} ${h}`} role="img" aria-label={`Risk-coverage curve. Error rate rises as more cases are auto-approved. Target error rate ${Math.round(alpha * 100)} percent.${heldOut ? ` Held-out error ${fmtPctInterval(heldOut.ci[0], heldOut.ci[1], 1)} at ${Math.round((chosen ?? 0) * 100)} percent coverage.` : ""}`}>
          {y.ticks(5).map((t) => (
            <g key={t}>
              <line className="svg-grid" x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} />
              <text className="svg-text" x={m.l - 8} y={y(t) + 3.5} textAnchor="end">{Math.round(t * 100)}%</text>
            </g>
          ))}
          {[0, 0.25, 0.5, 0.75, 1].map((v) => <text key={v} className="svg-text" x={x(v)} y={h - m.b + 16} textAnchor="middle">{Math.round(v * 100)}%</text>)}
          <text className="ev-axis-label" x={(m.l + width - m.r) / 2} y={h - 6} textAnchor="middle">Share of cases auto-approved (coverage)</text>
          <path className="ev-band" d={a(curve) ?? ""} />
          <path className="ev-line" d={l(curve) ?? ""} />
          <line className="ev-bound" x1={m.l} x2={width - m.r} y1={y(alpha)} y2={y(alpha)} />
          <text className="thr-text" x={width - m.r} y={y(alpha) - 6} textAnchor="end">Target {Math.round(alpha * 100)}%</text>
          {chosen != null && heldOut && (
            <g>
              <line className="ev-whisker" x1={x(chosen)} x2={x(chosen)} y1={y(heldOut.ci[0])} y2={y(heldOut.ci[1])} />
              <line className="ev-whisker" x1={x(chosen) - 4} x2={x(chosen) + 4} y1={y(heldOut.ci[0])} y2={y(heldOut.ci[0])} />
              <line className="ev-whisker" x1={x(chosen) - 4} x2={x(chosen) + 4} y1={y(heldOut.ci[1])} y2={y(heldOut.ci[1])} />
              <circle className="ev-pt" cx={x(chosen)} cy={y(heldOut.value)} r={5.5} />
              <text className="svg-text svg-text--strong" x={x(chosen) - 10} y={y(heldOut.ci[1]) - 8} textAnchor="end">held-out</text>
            </g>
          )}
        </svg>
      )}
    </div>
  );
}
