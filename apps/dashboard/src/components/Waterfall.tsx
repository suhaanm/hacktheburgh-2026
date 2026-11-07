import { useWidth } from "../hooks";
import { layoutWaterfall } from "../lib/waterfall";
import { fmtInterval, signed } from "../lib/format";
import type { Interval, WaterfallStep } from "../types";
import { scaleLinear } from "d3-scale";

/** Gap waterfall: each step floats from where the last one ended; whiskers are 95% intervals. */
export function Waterfall({ steps, totalCi }: { steps: WaterfallStep[]; totalCi: Interval }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const { rows, total, max } = layoutWaterfall(steps, totalCi);
  const compact = width > 0 && width < 640;
  const labelW = compact ? 0 : 252;
  const valW = compact ? 0 : 150;
  const rowH = compact ? 50 : 34;
  const top = 6;
  const axisH = 26;
  const H = top + rows.length * rowH + axisH;
  const x = scaleLinear().domain([0, Math.ceil(max / 50) * 50]).range([0, Math.max(120, width - labelW - valW - 8)]).nice();
  const ticks = x.ticks(compact ? 4 : 7);

  return (
    <div ref={ref} className="wf">
      {width > 0 && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img"
          aria-label={`Gap waterfall. ${rows.slice(0, -1).map((r) => `${r.label}: ${Math.round(r.seconds)} seconds, interval ${fmtInterval(r.ci)}`).join(". ")}. Total ${Math.round(total)} seconds, interval ${fmtInterval(totalCi)}.`}>
          <g transform={`translate(${labelW},${top})`}>
            {ticks.map((t) => (
              <g key={t}>
                <line className="svg-grid" x1={x(t)} x2={x(t)} y1={0} y2={rows.length * rowH} />
                <text className="svg-text" x={x(t)} y={rows.length * rowH + 16} textAnchor="middle">{t}</text>
              </g>
            ))}
            <text className="svg-text" x={x.range()[1]} y={rows.length * rowH + 16} textAnchor="end" dx={compact ? 0 : 0}>{""}</text>
            {rows.map((r, i) => {
              const y = i * rowH;
              const by = compact ? y + 20 : y + 8;
              const bh = compact ? 16 : 18;
              const [wl, wh] = r.whisker;
              const cy = by + bh / 2;
              return (
                <g key={r.label}>
                  {r.total && <line className="svg-axis" x1={-labelW} x2={x.range()[1] + valW} y1={y} y2={y} />}
                  <rect className={`wf-bar${r.total ? " wf-bar--total" : ""}`} x={x(r.start)} y={by} width={Math.max(1.5, x(r.end) - x(r.start))} height={bh} rx={1.5}
                    style={{ opacity: r.total ? 1 : 0.88 }} />
                  <line className="wf-whisker" x1={x(wl)} x2={x(wh)} y1={cy} y2={cy} />
                  <line className="wf-whisker" x1={x(wl)} x2={x(wl)} y1={cy - 4} y2={cy + 4} />
                  <line className="wf-whisker" x1={x(wh)} x2={x(wh)} y1={cy - 4} y2={cy + 4} />
                  {!compact && <text className={`wf-label${r.total ? " wf-label--total" : ""}`} x={-12} y={cy + 4} textAnchor="end">{r.label}</text>}
                  {compact && <text className={`wf-label${r.total ? " wf-label--total" : ""}`} x={0} y={y + 14}>{r.label}</text>}
                  <text className="wf-val" x={compact ? x.range()[1] : x(wh) + 8} y={compact ? y + 14 : cy + 4} textAnchor={compact ? "end" : "start"}>{r.total ? "" : "+"}{signed(r.seconds)} s <tspan className="svg-text">{fmtInterval(r.ci)}</tspan></text>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </div>
  );
}
