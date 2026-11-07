import { useId, useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { useWidth } from "../../hooks";

export interface BandPoint { x: number; y: number; lo: number | null; hi: number | null }

export interface LineBandProps {
  title: string;
  points: BandPoint[];
  xDomain: [number, number];
  yDomain: [number, number];
  xTicks: number[];
  yTicks: number[];
  formatX: (v: number) => string;
  formatY: (v: number) => string;
  /** A labelled horizontal line, for a design target. Drawn dashed with its words beside it, so it never rests on colour. */
  target?: { value: number; label: string };
  /** A labelled vertical mark, for a median. */
  mark?: { x: number; ci: [number, number] | null; label: string };
  xLabel?: string;
  height?: number;
}

/**
 * A line with an interval band. One shape for the onboarding curves (small multiples that share their domains, so panels compare by eye)
 * and for a drill-down's series. The band is the interval; the line is the estimate. The chart is also described in its <title>.
 */
export function LineBand({ title, points, xDomain, yDomain, xTicks, yTicks, formatX, formatY, target, mark, xLabel, height = 190 }: LineBandProps) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const W = Math.max(220, width);
  const left = 40, right = 12, top = 10, bottom = xLabel ? 40 : 26;
  const plotW = W - left - right, plotH = height - top - bottom;
  const x = useMemo(() => scaleLinear().domain(xDomain).range([left, left + plotW]), [xDomain, plotW]);
  const y = useMemo(() => scaleLinear().domain(yDomain).range([top + plotH, top]).clamp(true), [yDomain, plotH]);
  const sorted = useMemo(() => [...points].sort((a, b) => a.x - b.x), [points]);
  const band = useMemo(() => {
    const withCi = sorted.filter((p) => p.lo !== null && p.hi !== null);
    if (withCi.length < 2) return null;
    return area<BandPoint>().x((p) => x(p.x)).y0((p) => y(p.lo as number)).y1((p) => y(p.hi as number))(withCi);
  }, [sorted, x, y]);
  const path = useMemo(() => (sorted.length > 1 ? line<BandPoint>().x((p) => x(p.x)).y((p) => y(p.y))(sorted) : null), [sorted, x, y]);
  const last = sorted[sorted.length - 1];
  const first = sorted[0];

  return (
    <div ref={box} className="lb">
      {width > 0 && (
        <svg width={W} height={height} viewBox={`0 0 ${W} ${height}`} role="img" aria-labelledby={`lb-${uid}`}>
          <title id={`lb-${uid}`}>{`${title}.${first && last ? ` From ${formatY(first.y)} at ${formatX(first.x)} to ${formatY(last.y)} at ${formatX(last.x)}.` : " No points to draw."}${target ? ` ${target.label || "Design target"}: ${formatY(target.value)}.` : ""}${mark ? ` ${mark.label}.` : ""}`}</title>
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line className="svg-grid" x1={left} x2={left + plotW} y1={y(t)} y2={y(t)} />
              <text className="svg-text" x={left - 6} y={y(t) + 3.5} textAnchor="end">{formatY(t)}</text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={`x${t}`} className="svg-text" x={x(t)} y={top + plotH + 15} textAnchor="middle">{formatX(t)}</text>
          ))}
          <line className="svg-axis" x1={left} x2={left + plotW} y1={top + plotH} y2={top + plotH} />
          {xLabel && <text className="svg-text" x={left + plotW / 2} y={height - 6} textAnchor="middle">{xLabel}</text>}
          {band && <path className="lb-band" d={band} />}
          {target && (
            <g className="lb-target">
              <line x1={left} x2={left + plotW} y1={y(target.value)} y2={y(target.value)} />
              {target.label && <text className="svg-text svg-text--strong" x={left + 6} y={y(target.value) - 5} textAnchor="start">{target.label}</text>}
            </g>
          )}
          {mark && (
            <g className="lb-mark">
              {mark.ci && <rect x={x(mark.ci[0])} y={top} width={Math.max(2, x(mark.ci[1]) - x(mark.ci[0]))} height={plotH} className="lb-mark__ci" />}
              <line x1={x(mark.x)} x2={x(mark.x)} y1={top} y2={top + plotH} />
            </g>
          )}
          {path && <path className="lb-line" d={path} />}
          {last && <circle className="lb-end" cx={x(last.x)} cy={y(last.y)} r={4} />}
        </svg>
      )}
    </div>
  );
}

/** Round-number ticks inside a domain, at most `count`. */
export function ticksFor(domain: [number, number], count = 5): number[] {
  return scaleLinear().domain(domain).ticks(count).filter((t) => t >= domain[0] && t <= domain[1]);
}
