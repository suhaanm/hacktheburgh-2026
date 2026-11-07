import { useWidth } from "../hooks";
import { scaleLinear } from "d3-scale";
import { fmtPoints, fmtPointsInterval, fmtShare, habitAxis, readHabit } from "../lib/git";
import type { GitHabit } from "../types";

const pp = (x: number) => `${x < 0 ? "−" : x > 0 ? "+" : ""}${Math.abs(Math.round(x * 100))}`;

/**
 * Each habit's difference from the experts, you minus them, on one shared axis in percentage points.
 * Dot: the difference. Line: its 95% interval. Hatched band: differences smaller than the habit's floor are never flagged.
 * Filled red: flagged and worse than the experts. Hollow: not flagged. Zero is the experts' value.
 */
export function HabitDeltas({ habits }: { habits: GitHabit[] }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const compact = width > 0 && width < 640;
  const labelW = compact ? 0 : 236;
  const sideW = compact ? 0 : 168;
  const rowH = compact ? 58 : 44;
  const axis = habitAxis(habits);
  const plotW = Math.max(160, width - labelW - sideW - 8);
  const x = scaleLinear().domain([-axis, axis]).range([0, plotW]);
  const H = habits.length * rowH + 34;
  const ticks = [-axis, -axis / 2, 0, axis / 2, axis];
  return (
    <div ref={box} className="chart">
      {width > 0 && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img"
          aria-label={`Difference from the experts for ${habits.length} commit habits, in percentage points. ${habits.filter((h) => h.flagged).length} differ clearly.`}>
          <defs>
            <pattern id="floor-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="5" style={{ stroke: "var(--muted)", strokeWidth: 1, opacity: 0.55 }} />
            </pattern>
          </defs>
          <g transform={`translate(${labelW},4)`}>
            {ticks.map((t) => (
              <g key={t}>
                <line className={t === 0 ? "ev-truth" : "svg-grid"} x1={x(t)} x2={x(t)} y1={0} y2={habits.length * rowH} />
                <text className="svg-text" x={x(t)} y={habits.length * rowH + 16} textAnchor="middle">{pp(t)}</text>
              </g>
            ))}
            <text className="svg-text" x={x(0)} y={habits.length * rowH + 30} textAnchor="middle">percentage points. 0 = the experts</text>
            {habits.map((h, i) => {
              const r = readHabit(h);
              const top = i * rowH;
              const cy = compact ? top + 36 : top + rowH / 2;
              const floor = h.min_delta ?? 0;
              const tone = r.flagged ? (r.direction === "better" ? "good" : "bad") : "none";
              return (
                <g key={h.id} opacity={r.flagged ? 1 : 0.85}>
                  {!compact && <text className="wf-label" style={{ fontWeight: r.flagged ? 700 : 500 }} x={-14} y={cy + 4} textAnchor="end">{h.label.length > 34 ? `${h.label.slice(0, 33)}…` : h.label}</text>}
                  {compact && <text className="wf-label" style={{ fontWeight: r.flagged ? 700 : 500 }} x={0} y={top + 14}>{h.label}</text>}
                  {floor > 0 && <rect x={x(-floor)} y={cy - 9} width={x(floor) - x(-floor)} height={18} fill="url(#floor-hatch)" />}
                  <line className="dw-line" x1={x(h.ci[0])} x2={x(h.ci[1])} y1={cy} y2={cy} />
                  <line className="dw-line" x1={x(h.ci[0])} x2={x(h.ci[0])} y1={cy - 4} y2={cy + 4} />
                  <line className="dw-line" x1={x(h.ci[1])} x2={x(h.ci[1])} y1={cy - 4} y2={cy + 4} />
                  <circle cx={x(h.delta)} cy={cy} r={5} className={tone === "bad" ? "gh-dot gh-dot--bad" : tone === "good" ? "gh-dot gh-dot--good" : "gh-dot"} />
                  {compact
                    ? <text className="wf-val" x={plotW} y={top + 14} textAnchor="end">{fmtPoints(h.delta)} <tspan className="svg-text">you {fmtShare(h.learner)} · experts {fmtShare(h.expert)}</tspan></text>
                    : <text className="wf-val" x={plotW + 14} y={cy - 2} dominantBaseline="auto">{fmtPoints(h.delta)}<tspan className="svg-text" x={plotW + 14} dy="13">you {fmtShare(h.learner)} · experts {fmtShare(h.expert)}</tspan></text>}
                  <title>{`${h.label}: you ${fmtShare(h.learner)}, experts ${fmtShare(h.expert)}, difference ${fmtPoints(h.delta)}, 95% interval ${fmtPointsInterval(h.ci)}. ${r.state}.`}</title>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </div>
  );
}
