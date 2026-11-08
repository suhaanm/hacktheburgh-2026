import { wrapLabel } from "../../lib/git";
import { useId, useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { useWidth } from "../../hooks";
import type { Est } from "./wire";

export interface PlotRow {
  id: string;
  label: string;
  est: Est | null;
  /** expert: amber filled circle. novice: indigo filled square. neutral: ink circle. Shape and the row's label carry the meaning, not colour alone. */
  tone: "expert" | "novice" | "neutral";
  /** A hollow marker: the interval spans zero or the target, so the sign or the side cannot be read. Always paired with words in the row's note. */
  hollow?: boolean;
}

export interface PlotProps {
  title: string;
  rows: PlotRow[];
  domain: [number, number];
  ticks: number[];
  format: (v: number) => string;
  /** A labelled vertical line: zero, a design target. */
  reference?: { value: number; label: string };
  rowHeight?: number;
  /** Axis labels, when they should be shorter than the value labels (plain numbers on the axis, the unit in the row's value). */
  tickFormat?: (v: number) => string;
  /** Keep the label column on the left however narrow the chart is, so a row prints its value only (the interval is drawn and is in the table). */
  side?: boolean;
}

/**
 * Dot-and-whisker rows on one axis shared by every panel that uses the same `domain`. A dot is the estimate and a line through it is its
 * interval. A row with no interval shows its dot and says "no interval yet". The whole chart is also described in its <title>.
 */
export function IntervalPlot({ title, rows, domain, ticks, format, reference, rowHeight = 44, tickFormat, side = false }: PlotProps) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const W = Math.max(240, width);
  const compact = !side && W < 520;
  const tf = tickFormat ?? format;
  const left = compact ? 10 : 132, right = 14, top = 6;
  // A label that wraps to two lines, with its figure under it, needs a taller row so it never runs into the next row's label.
  const wraps = !compact && rows.some((r) => wrapLabel(r.label, 24).length > 1);
  const rh = compact ? rowHeight + 20 : rowHeight + (wraps ? 14 : 0);
  const x = useMemo(() => scaleLinear().domain(domain).range([left, Math.max(left + 40, W - right)]).clamp(true), [domain, left, W]);
  const axisY = top + rh * rows.length + 4;
  const H = axisY + 24 + (reference ? 12 : 0);
  const text = (r: PlotRow) => (r.est ? `${format(r.est.value)}${r.est.ci ? ` (${format(r.est.ci[0])} to ${format(r.est.ci[1])})` : ", no interval yet"}` : "not enough data");

  return (
    <div ref={box} className="ip">
      {width > 0 && (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`ip-${uid}`}>
          <title id={`ip-${uid}`}>{`${title}. ${rows.map((r) => `${r.label}: ${text(r)}`).join(". ")}.`}</title>
          {ticks.map((t) => (
            <g key={t}>
              <line className="svg-grid" x1={x(t)} x2={x(t)} y1={top} y2={axisY} />
              <text className="svg-text" x={x(t)} y={axisY + 15} textAnchor="middle">{tf(t)}</text>
            </g>
          ))}
          <line className="svg-axis" x1={left} x2={W - right} y1={axisY} y2={axisY} />
          {reference && (
            <g className="ip-ref">
              <line x1={x(reference.value)} x2={x(reference.value)} y1={top} y2={axisY} />
              <text className="svg-text svg-text--strong" x={x(reference.value)} y={axisY + 27} textAnchor="middle">{reference.label}</text>
            </g>
          )}
          {rows.map((r, i) => {
            const cy = top + rh * i + (compact ? rh - 14 : rh / 2);
            return (
              <g key={r.id} className="ip-row" data-tone={r.tone}>
                {compact ? (
                  <>
                    <text className="ip-label" x={0} y={top + rh * i + 13}>{r.label}</text>
                    <text className="svg-text ip-value" x={0} y={top + rh * i + 28}>{text(r)}</text>
                  </>
                ) : (
                  <>
                    {(() => {
                      const ls = wrapLabel(r.label, 24);
                      return <text className="ip-label" x={0} y={cy - (ls.length > 1 ? 10 : 3)}>{ls.map((l, k) => <tspan key={k} x={0} dy={k === 0 ? 0 : 12}>{l}</tspan>)}</text>;
                    })()}
                    <text className="svg-text ip-value" x={0} y={cy + (wrapLabel(r.label, 24).length > 1 ? 16 : 11)}>{r.est ? `${format(r.est.value)}${r.est.ci ? "" : " (no interval yet)"}` : "not enough data"}</text>
                  </>
                )}
                {r.est?.ci && <line className="ip-whisker" x1={x(r.est.ci[0])} x2={x(r.est.ci[1])} y1={cy} y2={cy} />}
                {r.est?.ci && [r.est.ci[0], r.est.ci[1]].map((v) => <line key={v} className="ip-cap" x1={x(v)} x2={x(v)} y1={cy - 5} y2={cy + 5} />)}
                {r.est && (r.tone === "novice"
                  ? <rect className="ip-mark" data-hollow={r.hollow ? "true" : "false"} x={x(r.est.value) - 5} y={cy - 5} width={10} height={10} />
                  : <circle className="ip-mark" data-hollow={r.hollow ? "true" : "false"} cx={x(r.est.value)} cy={cy} r={5.5} />)}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

/** Axis settings for a share from 0 to 1, the same in every panel so panels can be compared by eye. */
export const SHARE_AXIS = { domain: [0, 1] as [number, number], ticks: [0, 0.25, 0.5, 0.75, 1] };
