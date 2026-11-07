import { useId, useRef, useState, type KeyboardEvent } from "react";
import { area, curveLinear, curveStepAfter, line } from "d3-shape";
import { useWidth } from "../../hooks";
import { Y_TICKS, frameFor, nearestIndex, xScale, xTicks, yScale } from "./chart";
import { glyphOf, pct, pctBracket, pctRange, pickSamples, pointReadout, signed, type GrowthView } from "./model";

const LEVEL_WORD = ["", "full", "small", "dot", "gone"];

/**
 * The independence curve (hero) with The Fade beneath it, drawn on one shared occurrence axis in one SVG, so every
 * glyph of the fade sits directly under the curve point it describes.
 *  - curve: share of the latest window that finished with no cue accepted, 0 to 100%; band is the Wilson interval
 *  - fade, top row: the help level the engine allowed (L1 full help at the top, L4 gone at the bottom)
 *  - fade, bottom row: the cue the worker actually saw (ring thickness = tier, fainter = fewer occurrences cued, bar = text chip)
 */
export function GrowthChart({ view }: { view: GrowthView }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [keyOpen, setKeyOpen] = useState<boolean | null>(null);
  const pts = view.curve;
  const last = pts.length - 1;

  const f = frameFor(width || 600);
  const maxI = pts.length ? pts[last].i : 1;
  const x = xScale(maxI, f);
  const y = yScale(f);
  const xs = pts.map((p) => x(p.i));
  const ticks = xTicks(maxI, f.compact ? 4 : 8);

  const axisY = f.top + f.plotH;
  const tickRowY = axisY + 16;
  const nRowY = axisY + 31;
  const fadeTop = axisY + 58;
  const levelTop = fadeTop + 20;
  const levelH = f.compact ? 36 : 44;
  const glyphTop = levelTop + levelH + 12;
  const glyphH = 30;
  const H = glyphTop + glyphH + 6;
  const lv = (l: number) => levelTop + ((Math.min(4, Math.max(1, l)) - 1) / 3) * levelH;

  const bandPath = area<(typeof pts)[number]>().x((p) => x(p.i)).y0((p) => y(p.lo)).y1((p) => y(p.hi))(pts) ?? "";
  const linePath = line<(typeof pts)[number]>().x((p) => x(p.i)).y((p) => y(p.p))(pts) ?? "";
  const levelPath = line<(typeof pts)[number]>().defined((p) => p.lv != null).x((p) => x(p.i)).y((p) => lv(p.lv as number)).curve(view.smoothLevel ? curveLinear : curveStepAfter)(pts) ?? "";

  const markers = pickSamples(xs, f.compact ? 22 : 18);
  const glyphs = pickSamples(xs, f.compact ? 30 : 36);
  const b = view.baseline;
  const shown = cursor ?? last;
  const readout = pts[shown] ? pointReadout(pts[shown], view.window, view.levelPct, view.smoothLevel) : "";

  const move = (to: number) => setCursor(Math.max(0, Math.min(last, to)));
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const c = cursor ?? last;
    if (e.key === "ArrowRight") move(c + 1);
    else if (e.key === "ArrowLeft") move(c - 1);
    else if (e.key === "PageDown") move(c + 10);
    else if (e.key === "PageUp") move(c - 10);
    else if (e.key === "Home") move(0);
    else if (e.key === "End") move(last);
    else if (e.key === "Escape") setCursor(null);
    else return;
    e.preventDefault();
  };
  const at = (ev: { clientX: number }) => {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r || !xs.length) return;
    setCursor(nearestIndex(xs, ev.clientX - r.left));
  };

  const hasFade = view.hasCueWeights;
  const levelPts = pts.filter((p) => p.lv != null);

  return (
    <div className="gr-chart">
      <div ref={box} className="gr-chart__box">
        {width > 0 && (
          <svg
            ref={svgRef} width={width} height={H} viewBox={`0 0 ${width} ${H}`} tabIndex={0} role="application"
            aria-label={`Independence curve with the help fade beneath it. ${pts.length} points. Use the left and right arrow keys to read each point; the reading appears below the chart.`}
            onKeyDown={onKey} onMouseMove={at} onMouseLeave={() => setCursor(null)} onBlur={() => setCursor(null)}
            onFocus={() => { if (cursor == null) setCursor(last); }}
          >
            {/* y axis: 0 to 100% */}
            {Y_TICKS.map((t) => (
              <g key={t}>
                <line className="svg-grid" x1={f.left} x2={f.width - f.right} y1={y(t)} y2={y(t)} />
                <text className="svg-text" x={f.left - 6} y={y(t) + 3.5} textAnchor="end">{Math.round(t * 100)}%</text>
              </g>
            ))}
            <line className="svg-axis" x1={f.left} x2={f.width - f.right} y1={axisY} y2={axisY} />
            {/* x axis: occurrence number, with n for the window ending there */}
            {ticks.map((t) => {
              const p = pts.find((q) => q.i === t);
              return (
                <g key={t}>
                  <line className="svg-axis" x1={x(t)} x2={x(t)} y1={axisY} y2={axisY + 4} />
                  <text className="svg-text" x={x(t)} y={tickRowY} textAnchor="middle">{t}</text>
                  {p && !f.compact && <text className="svg-text gr-n" x={x(t)} y={nRowY} textAnchor="middle">n {p.n}</text>}
                </g>
              );
            })}
            {!f.compact && <text className="svg-text gr-n" x={f.left} y={nRowY} textAnchor="end" dx={-6}>n</text>}

            {/* the curve */}
            <path className="gr-band" d={bandPath} />
            {/* baseline: the first occurrences, with its own interval */}
            {b && (
              <g className="gr-base">
                <line className="gr-base__line" x1={f.left} x2={f.width - f.right} y1={y(b.share)} y2={y(b.share)} />
                <line className="gr-base__whisker" x1={x(b.n)} x2={x(b.n)} y1={y(b.wilson[0])} y2={y(b.wilson[1])} />
                <line className="gr-base__whisker" x1={x(b.n) - 4} x2={x(b.n) + 4} y1={y(b.wilson[0])} y2={y(b.wilson[0])} />
                <line className="gr-base__whisker" x1={x(b.n) - 4} x2={x(b.n) + 4} y1={y(b.wilson[1])} y2={y(b.wilson[1])} />
                <path className="gr-base__mark" d={`M ${x(b.n)} ${y(b.share) - 5} l 5 5 l -5 5 l -5 -5 z`} />
                <text className="gr-base__text" x={f.width - f.right} y={y(b.share) + (b.share > 0.85 ? 14 : -6)} textAnchor="end">
                  first {b.n}: {b.k} of {b.n} unaided
                </text>
              </g>
            )}
            <path className="gr-line" d={linePath} />
            {markers.map((i) => (
              <circle key={i} className={pts[i].n < view.window ? "gr-dot gr-dot--part" : "gr-dot"} cx={x(pts[i].i)} cy={y(pts[i].p)} r={3} />
            ))}
            {pts[last] && (
              <g>
                <circle className="gr-dot gr-dot--last" cx={x(pts[last].i)} cy={y(pts[last].p)} r={5} />
                <text className="gr-last" x={x(pts[last].i) + 9} y={y(pts[last].p) + 4.5}>{pct(pts[last].p)}</text>
              </g>
            )}

            {/* The Fade */}
            <text className="svg-text gr-fade__title" x={f.left} y={fadeTop + 2}>THE FADE</text>
            <text className="svg-text" x={f.left + 66} y={fadeTop + 2}>{f.compact ? "help level, and the cue you saw" : "help level the engine allowed, and the cue you actually saw"}</text>
            {[1, 2, 3, 4].map((l) => (
              <g key={l}>
                <line className="svg-grid" x1={f.left} x2={f.width - f.right} y1={lv(l)} y2={lv(l)} />
                <text className="svg-text" x={f.left - 6} y={lv(l) + 3.5} textAnchor="end">L{l}</text>
              </g>
            ))}
            {levelPts.length > 0 && <path className="gr-level" d={levelPath} />}
            {levelPts.length === 0 && <text className="svg-text" x={f.left + 4} y={levelTop + levelH / 2}>Help level not reported</text>}
            <text className="svg-text" x={f.left - 6} y={glyphTop + 15} textAnchor="end">cue</text>
            {hasFade ? glyphs.map((i) => {
              const g = glyphOf(pts[i].cue);
              const cx = x(pts[i].i), cy = glyphTop + 12;
              if (!g) return null;
              if (g.none) return <circle key={i} className="gr-nocue" cx={cx} cy={cy} r={2} />;
              return (
                <g key={i} className="gr-cue">
                  <circle className="gr-cue__ring" cx={cx} cy={cy} r={7} strokeWidth={g.stroke} opacity={g.opacity} />
                  {g.chip && <rect className="gr-cue__chip" x={cx - 5} y={cy + 11} width={10} height={3} rx={1} opacity={g.opacity} />}
                </g>
              );
            }) : <text className="svg-text" x={f.left + 4} y={glyphTop + 15}>The service does not report cue weight.</text>}

            {/* cursor across both panels */}
            {cursor != null && pts[cursor] && (
              <g className="gr-cursor" pointerEvents="none">
                <line x1={x(pts[cursor].i)} x2={x(pts[cursor].i)} y1={f.top} y2={glyphTop + glyphH} />
                <circle cx={x(pts[cursor].i)} cy={y(pts[cursor].p)} r={5.5} />
                {pts[cursor].lv != null && <circle cx={x(pts[cursor].i)} cy={lv(pts[cursor].lv as number)} r={3.5} />}
              </g>
            )}
            <title id={`t-${uid}`}>Independence curve and help fade</title>
          </svg>
        )}
      </div>
      <p className="gr-readout" aria-live="polite">
        {cursor == null ? "Latest. " : ""}{readout}
        {cursor == null && <span className="gr-readout__hint"> Hover the chart, or focus it and use the arrow keys, to read other points.</span>}
      </p>
      <details className="details-lite gr-key" open={keyOpen ?? !f.compact} onToggle={(e) => setKeyOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Key to the curve and the fade</summary>
      <ul className="legend gr-legend" aria-label="How to read the curve">
        <li className="legend__item"><svg width="22" height="10" aria-hidden="true"><line className="gr-line" x1="0" x2="22" y1="5" y2="5" /></svg>Share finished with no cue accepted, over the {view.window} occurrences ending at each point</li>
        <li className="legend__item"><svg width="22" height="10" aria-hidden="true"><rect className="gr-band" x="0" y="1" width="22" height="8" /></svg>{view.levelPct}% interval</li>
        <li className="legend__item"><svg width="12" height="12" aria-hidden="true"><circle className="gr-dot gr-dot--part" cx="6" cy="6" r="3.5" /></svg>Hollow: fewer than {view.window} occurrences so far</li>
        {b && <li className="legend__item"><svg width="22" height="12" aria-hidden="true"><line className="gr-base__line" x1="0" x2="22" y1="6" y2="6" /></svg>Your first {b.n} occurrences, {pctBracket(b.wilson)}</li>}
        <li className="legend__item">Bottom axis: occurrence number, then n for that window</li>
      </ul>
      <ul className="legend gr-legend" aria-label="How to read the fade">
        <li className="legend__item"><svg width="22" height="12" aria-hidden="true"><line className="gr-level" x1="0" x2="22" y1="6" y2="6" /></svg>Help level: {LEVEL_WORD.slice(1).map((w, i) => `L${i + 1} ${w}`).join(", ")}{view.smoothLevel ? ", averaged over each window" : ""}</li>
        <li className="legend__item">
          <svg width="40" height="16" aria-hidden="true"><circle className="gr-cue__ring" cx="8" cy="8" r="6" strokeWidth="3" /><circle className="gr-cue__ring" cx="30" cy="8" r="6" strokeWidth="0.8" opacity="0.4" /></svg>
          Ring: thicker is a heavier cue, fainter means fewer occurrences were cued
        </li>
        <li className="legend__item"><svg width="16" height="16" aria-hidden="true"><circle className="gr-cue__ring" cx="8" cy="6" r="4.5" strokeWidth="1.5" /><rect className="gr-cue__chip" x="3" y="12" width="10" height="3" rx="1" /></svg>Bar: a text chip came with it</li>
        <li className="legend__item"><svg width="12" height="12" aria-hidden="true"><circle className="gr-nocue" cx="6" cy="6" r="2" /></svg>Dot: no cue at all</li>
      </ul>
      </details>
      <span className="u-sr-only">{`Baseline ${b ? `${b.k} of ${b.n}, interval ${pctRange(b.wilson)}` : "not available"}. Last point ${pts[last] ? `${signed(pts[last].p * 100)} percent` : ""}.`}</span>
    </div>
  );
}
