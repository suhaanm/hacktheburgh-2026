import { useId, useRef, type KeyboardEvent } from "react";
import { useWidth } from "../hooks";
import { HEAT_CLASSES, isWide, quantize, quietSegments, toGrid } from "../lib/heatmap";
import { dowName, fmtPctInterval, slotTime } from "../lib/format";
import type { Presence } from "../types";

export interface Cursor { dow: number; slot: number }

/** Presence heatmap: 7 days by 96 quarter-hours. Colour is the chance you are at the machine; hatching marks wide intervals. */
export function Heatmap({ data, cursor, onCursor, day, onDay }: {
  data: Presence; cursor: Cursor | null; onCursor: (c: Cursor | null) => void; day: number; onDay: (d: number) => void;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const grid = toGrid(data.bins);
  const labelW = width < 520 ? 30 : 44;
  const axisH = 22;
  const rowH = width < 520 ? 24 : 30;
  const cw = Math.max(2, (width - labelW) / 96);
  const H = axisH + 7 * rowH + 2;
  const svgRef = useRef<SVGSVGElement>(null);

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const c = cursor ?? { dow: day, slot: 0 };
    let { dow, slot } = c;
    if (e.key === "ArrowRight") slot = Math.min(95, slot + 1);
    else if (e.key === "ArrowLeft") slot = Math.max(0, slot - 1);
    else if (e.key === "ArrowDown") dow = Math.min(6, dow + 1);
    else if (e.key === "ArrowUp") dow = Math.max(0, dow - 1);
    else if (e.key === "PageDown") slot = Math.min(95, slot + 4);
    else if (e.key === "PageUp") slot = Math.max(0, slot - 4);
    else if (e.key === "Home") slot = 0;
    else if (e.key === "End") slot = 95;
    else if (e.key === "Enter" || e.key === " ") { onDay(c.dow); e.preventDefault(); return; }
    else return;
    e.preventDefault();
    onCursor({ dow, slot });
  };

  const at = (ev: { clientX: number; clientY: number }) => {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r) return null;
    const x = ev.clientX - r.left - labelW, y = ev.clientY - r.top - axisH;
    if (x < 0 || y < 0) return null;
    const slot = Math.floor(x / cw), dow = Math.floor(y / rowH);
    return slot >= 0 && slot < 96 && dow >= 0 && dow < 7 ? { dow, slot } : null;
  };

  return (
    <div ref={box} className="heat">
      {width > 0 && (
        <svg ref={svgRef} width={width} height={H} viewBox={`0 0 ${width} ${H}`} tabIndex={0} role="application"
          aria-label="Presence heatmap, 7 days by 96 quarter-hours. Use the arrow keys to read a cell. Press Enter to open that day below."
          onKeyDown={onKey} onFocus={() => { if (!cursor) onCursor({ dow: day, slot: 80 }); }}
          onMouseMove={(e) => { const c = at(e); if (c) onCursor(c); }} onMouseLeave={() => onCursor(null)}
          onClick={(e) => { const c = at(e); if (c) onDay(c.dow); }}>
          <defs>
            <pattern id={`wide-${uid}`} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" style={{ stroke: "var(--bg)", strokeWidth: 1, opacity: 0.6 }} />
            </pattern>
          </defs>
          {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
            <text key={h} className="svg-text" x={labelW + h * 4 * cw} y={13}>{String(h).padStart(2, "0")}</text>
          ))}
          <text className="svg-text" x={width} y={13} textAnchor="end">24</text>
          <g transform={`translate(0,${axisH})`}>
            {Array.from({ length: 7 }, (_, d) => (
              <g key={d}>
                <text className="hm-day" data-sel={day === d} x={0} y={d * rowH + rowH / 2 + 4} onClick={() => onDay(d)}>{dowName(d)}</text>
                {grid[d].map((b, s) => b && (
                  <g key={s}>
                    <rect className={`hm hm-q${quantize(b.p)}`} x={labelW + s * cw} y={d * rowH} width={cw + 0.2} height={rowH - 1} />
                    {isWide(b) && <rect className="hm-wide" style={{ fill: `url(#wide-${uid})` }} x={labelW + s * cw} y={d * rowH} width={cw + 0.2} height={rowH - 1} />}
                  </g>
                ))}
                {quietSegments(data.quiet_hours, d).map(([a, z], i) => (
                  <rect key={i} className="hm-quiet" x={labelW + a * cw + 0.6} y={d * rowH + 0.6} width={(z - a) * cw - 1.2} height={rowH - 2.2} />
                ))}
              </g>
            ))}
            <rect className="hm-sel" x={labelW - 2} y={day * rowH - 1} width={96 * cw + 4} height={rowH + 1} rx={2} opacity={0.9} />
            {cursor && <rect className="hm-cursor" x={labelW + cursor.slot * cw - 1} y={cursor.dow * rowH - 1} width={cw + 2} height={rowH + 1} />}
          </g>
        </svg>
      )}
    </div>
  );
}

export function cellReadout(data: Presence, c: Cursor | null): string {
  if (!c) return "Hover a cell, or focus the map and use the arrow keys, to read its interval.";
  const b = data.bins.find((x) => x.dow === c.dow && x.slot === c.slot);
  if (!b) return `${dowName(c.dow)} ${slotTime(c.slot)}: no data.`;
  const end = slotTime((c.slot + 1) % 96);
  return `${dowName(c.dow)} ${slotTime(c.slot)} to ${end}: ${Math.round(b.p * 100)}% likely at the machine. 95% interval ${fmtPctInterval(b.lo, b.hi)}.${isWide(b) ? " Wide interval: treat with care." : ""}`;
}

export function HeatLegend() {
  return (
    <ul className="legend" aria-label="How to read the map">
      {HEAT_CLASSES.map((c) => (
        <li key={c.q} className="legend__item"><span className="sw" style={{ background: `var(--seq-${c.q})`, border: "1px solid var(--line)" }} />{c.label}</li>
      ))}
      <li className="legend__item"><span className="sw sw--hatch sw--muted" />Hatched: interval wider than 40 points</li>
      <li className="legend__item"><span className="sw sw--dashed sw--muted" />Dashed outline: quiet hours</li>
    </ul>
  );
}
