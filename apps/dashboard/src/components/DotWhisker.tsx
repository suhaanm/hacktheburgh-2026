import { useWidth } from "../hooks";
import type { Interval } from "../types";
import { scaleLinear } from "d3-scale";
import { fmtInterval, signed } from "../lib/format";

export interface DwRow {
  label: string;
  value: number;
  ci: Interval;
  emphasis?: "real" | "ref" | "plain";
  sub?: string;
}

/** Estimates with their 95% intervals on one shared, labelled scale. Optional reference line (a known truth or zero). */
export function DotWhisker({ rows, unit, reference, refLabel, domain, digits = 0, aria }: {
  rows: DwRow[]; unit: string; reference?: number; refLabel?: string; domain?: [number, number]; digits?: number; aria: string;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const compact = width > 0 && width < 560;
  const labelW = compact ? 0 : 214;
  const valW = compact ? 0 : 150;
  const rowH = compact ? 46 : 34;
  const lo = domain?.[0] ?? Math.min(0, ...rows.map((r) => r.ci[0]));
  const hi = domain?.[1] ?? Math.max(...rows.map((r) => r.ci[1]));
  const x = scaleLinear().domain([lo, hi]).range([0, Math.max(120, width - labelW - valW - 12)]).nice();
  const H = rows.length * rowH + 30;
  return (
    <div ref={box}>
      {width > 0 && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={aria}>
          <g transform={`translate(${labelW},4)`}>
            {x.ticks(compact ? 4 : 6).map((t) => (
              <g key={t}>
                <line className="svg-grid" x1={x(t)} x2={x(t)} y1={0} y2={rows.length * rowH} />
                <text className="svg-text" x={x(t)} y={rows.length * rowH + 16} textAnchor="middle">{signed(t, digits)}</text>
              </g>
            ))}
            <text className="svg-text" x={x.range()[1]} y={rows.length * rowH + 28} textAnchor="end">{unit}</text>
            {reference != null && (
              <g>
                <line className="ev-truth" x1={x(reference)} x2={x(reference)} y1={-2} y2={rows.length * rowH} />
                {refLabel && <text className="ev-truth-text" x={x(reference) + 4} y={10}>{refLabel}</text>}
              </g>
            )}
            {rows.map((r, i) => {
              const cy = (compact ? i * rowH + 30 : i * rowH + rowH / 2);
              return (
                <g key={r.label}>
                  {!compact && <text className="wf-label" x={-12} y={cy + 4} textAnchor="end">{r.label}</text>}
                  {compact && <text className="wf-label" x={0} y={i * rowH + 12}>{r.label}</text>}
                  <line className={`dw-line${r.emphasis === "real" ? " dw-line--real" : ""}`} x1={x(r.ci[0])} x2={x(r.ci[1])} y1={cy} y2={cy} />
                  <line className={`dw-line${r.emphasis === "real" ? " dw-line--real" : ""}`} x1={x(r.ci[0])} x2={x(r.ci[0])} y1={cy - 4} y2={cy + 4} />
                  <line className={`dw-line${r.emphasis === "real" ? " dw-line--real" : ""}`} x1={x(r.ci[1])} x2={x(r.ci[1])} y1={cy - 4} y2={cy + 4} />
                  <circle className={`dw-dot${r.emphasis === "real" ? " dw-dot--real" : ""}`} cx={x(r.value)} cy={cy} r={4.5} />
                  <text className="wf-val" x={compact ? x.range()[1] : x(r.ci[1]) + 10} y={compact ? i * rowH + 12 : cy + 4} textAnchor={compact ? "end" : "start"}>{signed(r.value, digits)} <tspan className="svg-text">{fmtInterval(r.ci, digits)}</tspan></text>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </div>
  );
}
