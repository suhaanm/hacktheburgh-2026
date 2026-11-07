import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { scaleLinear, scaleSqrt } from "d3-scale";
import { useWidth } from "../../hooks";
import { CLOSE_POINTS, binReadout, type Bin } from "./scorecard";
import "./scorecard.css";

const TICKS = [0, 0.25, 0.5, 0.75, 1];
const pc = (x: number): string => `${Math.round(x * 100)}%`;

/**
 * The reliability diagram. x: what the forecast said (mean of each band). y: how often someone really was stuck in that band.
 * On the dashed diagonal the forecast is exactly right; the shaded band is "within five points". Each dot has its Wilson interval;
 * a band with fewer than 30 cases is a hollow dot with a dashed whisker. The strip beneath is how many cases each band has
 * (bar height is the square root of n, so a thin band is still visible), with the count printed on it.
 */
export function Reliability({ bins, levelPct, selected, onSelect }: { bins: Bin[]; levelPct: number; selected: number | null; onSelect: (i: number | null) => void }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const [focused, setFocused] = useState(false);

  const W = Math.max(260, width);
  const compact = W < 420;
  const left = compact ? 38 : 44, right = 12, top = 12;
  const side = Math.min(W - left - right, 440);
  const x = useMemo(() => scaleLinear().domain([0, 1]).range([left, left + side]), [left, side]);
  const y = useMemo(() => scaleLinear().domain([0, 1]).range([top + side, top]), [top, side]);
  const axisY = top + side;
  const stripTop = axisY + 40;
  const stripH = 54;
  const stripBase = stripTop + stripH;
  const maxN = Math.max(1, ...bins.map((b) => b.n));
  const bar = useMemo(() => scaleSqrt().domain([0, maxN]).range([0, stripH]), [maxN]);
  const H = stripBase + 22;
  const barW = Math.max(8, Math.min(28, (side / Math.max(1, bins.length)) * 0.62));

  const move = (to: number) => onSelect(Math.max(0, Math.min(bins.length - 1, to)));
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const c = selected ?? -1;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") move(c + 1);
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") move(c < 0 ? 0 : c - 1);
    else if (e.key === "Home") move(0);
    else if (e.key === "End") move(bins.length - 1);
    else if (e.key === "Escape") onSelect(null);
    else return;
    e.preventDefault();
  };
  const nearest = (clientX: number) => {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r || !bins.length) return;
    const px = clientX - r.left;
    let best = 0, d = Infinity;
    bins.forEach((b, i) => { const dd = Math.abs(x(b.p) - px); if (dd < d) { d = dd; best = i; } });
    onSelect(best);
  };

  const sel = selected != null ? bins[selected] : null;
  // The band of "close": the diagonal plus and minus CLOSE_POINTS, clipped to the plot.
  const close = `M ${x(0)} ${y(0)} L ${x(0)} ${y(CLOSE_POINTS)} L ${x(1 - CLOSE_POINTS)} ${y(1)} L ${x(1)} ${y(1)} L ${x(1)} ${y(1 - CLOSE_POINTS)} L ${x(CLOSE_POINTS)} ${y(0)} Z`;

  return (
    <div ref={box} className="sc-rel">
      {width > 0 && (
        <svg
          ref={svgRef} width={W} height={H} viewBox={`0 0 ${W} ${H}`} tabIndex={0} role="application" aria-labelledby={`t-${uid}`}
          aria-describedby={`d-${uid}`}
          onKeyDown={onKey} onPointerMove={(e) => nearest(e.clientX)} onPointerLeave={() => { if (!focused) onSelect(null); }}
          onFocus={() => { setFocused(true); if (selected == null && bins.length) onSelect(0); }} onBlur={() => { setFocused(false); onSelect(null); }}
        >
          <title id={`t-${uid}`}>Reliability diagram: what the forecast said against how often someone was stuck</title>
          <desc id={`d-${uid}`}>{`${bins.length} bands of forecasts. Use the left and right arrow keys to read each band; the reading appears beside the chart.`}</desc>

          {TICKS.map((t) => (
            <g key={t}>
              <line className="svg-grid" x1={left} x2={left + side} y1={y(t)} y2={y(t)} />
              <line className="svg-grid" x1={x(t)} x2={x(t)} y1={top} y2={axisY} />
              <text className="svg-text" x={left - 6} y={y(t) + 3.5} textAnchor="end">{pc(t)}</text>
              <text className="svg-text" x={x(t)} y={axisY + 15} textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}>{pc(t)}</text>
            </g>
          ))}
          <line className="svg-axis" x1={left} x2={left + side} y1={axisY} y2={axisY} />
          <line className="svg-axis" x1={left} x2={left} y1={top} y2={axisY} />
          <text className="svg-text sc-axis-title" x={left + side / 2} y={axisY + 31} textAnchor="middle">What the forecast said</text>
          <text className="svg-text sc-axis-title" transform={`translate(${compact ? 9 : 11} ${top + side / 2}) rotate(-90)`} textAnchor="middle">How often someone was stuck</text>

          <path className="sc-close" d={close} />
          <line className="sc-diag" x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} />

          {bins.map((b, i) => {
            const cx = x(b.p), cy = y(b.freq);
            const isSel = selected === i;
            return (
              <g key={i} className="sc-bin" data-thin={b.thin} data-selected={isSel}>
                {b.ci && (
                  <g className="sc-whisker">
                    <line x1={cx} x2={cx} y1={y(b.ci[0])} y2={y(b.ci[1])} strokeDasharray={b.thin ? "3 2" : undefined} />
                    <line x1={cx - 4} x2={cx + 4} y1={y(b.ci[0])} y2={y(b.ci[0])} />
                    <line x1={cx - 4} x2={cx + 4} y1={y(b.ci[1])} y2={y(b.ci[1])} />
                  </g>
                )}
                <circle className={b.thin ? "sc-dot sc-dot--thin" : "sc-dot"} cx={cx} cy={cy} r={isSel ? 6 : 4.5} />
                {b.thin && <text className="svg-text sc-thin" x={b.p > 0.8 ? cx - 9 : cx + 9} y={cy + 3.5} textAnchor={b.p > 0.8 ? "end" : "start"}>thin</text>}
                {isSel && <circle className="sc-ring" cx={cx} cy={cy} r={10} />}
              </g>
            );
          })}

          <line className="svg-axis" x1={left} x2={left + side} y1={stripBase} y2={stripBase} />
          <text className="svg-text" x={left - 6} y={stripBase - 2} textAnchor="end">n</text>
          {bins.map((b, i) => {
            const h = Math.max(1.5, bar(b.n));
            const cx = x(b.p);
            const show = !compact || i % 2 === 0 || selected === i;
            return (
              <g key={i} className="sc-count" data-thin={b.thin} data-selected={selected === i}>
                <rect className={b.thin ? "sc-bar sc-bar--thin" : "sc-bar"} x={cx - barW / 2} y={stripBase - h} width={barW} height={h} />
                {show && <text className="svg-text sc-n" x={cx} y={stripBase - h - 4} textAnchor="middle">{b.n >= 10000 ? `${Math.round(b.n / 1000)}k` : b.n}</text>}
              </g>
            );
          })}
          <text className="svg-text" x={left + side} y={stripBase + 16} textAnchor="end">cases in each band (bar height is the square root of n)</text>
        </svg>
      )}
      <p className="u-sr-only" aria-live="polite">{sel ? binReadout(sel, levelPct) : ""}</p>
    </div>
  );
}
