import { useWidth } from "../hooks";
import { area, line } from "d3-shape";
import { scaleLinear } from "d3-scale";
import { dowName } from "../lib/format";
import { quietSegments, toGrid } from "../lib/heatmap";
import type { Presence } from "../types";

/** One day with its interval band: the line is the estimate, the band is the 95% interval. */
export function DayBand({ data, day }: { data: Presence; day: number }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const row = toGrid(data.bins)[day].filter((b): b is NonNullable<typeof b> => !!b);
  const m = { l: 40, r: 8, t: 8, b: 24 };
  const h = 150;
  const x = scaleLinear().domain([0, 96]).range([m.l, Math.max(m.l + 100, width - m.r)]);
  const y = scaleLinear().domain([0, 1]).range([h - m.b, m.t]);
  const a = area<(typeof row)[number]>().x((d) => x(d.slot + 0.5)).y0((d) => y(d.lo)).y1((d) => y(d.hi));
  const l = line<(typeof row)[number]>().x((d) => x(d.slot + 0.5)).y((d) => y(d.p));
  return (
    <div ref={box} className="chart">
      {width > 0 && (
        <svg width={width} height={h} viewBox={`0 0 ${width} ${h}`} role="img"
          aria-label={`${dowName(day)} presence with 95% interval band. Estimated chance of being at the machine across the day.`}>
          {[0, 0.5, 1].map((v) => (
            <g key={v}>
              <line className="svg-grid" x1={m.l} x2={width - m.r} y1={y(v)} y2={y(v)} />
              <text className="svg-text" x={m.l - 6} y={y(v) + 3.5} textAnchor="end">{Math.round(v * 100)}%</text>
            </g>
          ))}
          {quietSegments(data.quiet_hours, day).map(([s, e], i) => (
            <rect key={i} className="hm-quiet" x={x(s)} y={m.t} width={x(e) - x(s)} height={h - m.b - m.t} />
          ))}
          <path className="band" d={a(row) ?? ""} />
          <path className="band-line" d={l(row) ?? ""} />
          {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((hr) => (
            <text key={hr} className="svg-text" x={x(hr * 4)} y={h - 8} textAnchor="middle">{String(hr).padStart(2, "0")}</text>
          ))}
        </svg>
      )}
    </div>
  );
}
