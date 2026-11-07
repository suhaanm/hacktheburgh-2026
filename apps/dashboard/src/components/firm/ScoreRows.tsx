import { useId, useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { useWidth } from "../../hooks";
import type { Est } from "./scorecard";
import "./scorecard.css";

export interface ScoreRowSpec {
  id: string;
  label: string;
  est: Est | null;
  /** ours: filled dot. other: hollow diamond (a baseline). candidate: hollow ring (a v2 candidate that is not accepted). */
  kind: "ours" | "other" | "candidate";
}

/**
 * Dot-and-whisker rows on one shared axis: a dot is the estimate, the whisker is its interval. Rows with no interval show a dot and say so.
 * Position carries the value, so the axis need not start at zero (unless `zero` is set, as for rates): the footer says which.
 * `reference` is a labelled vertical line (a budget, or chance).
 */
export function ScoreChart({
  title, rows, digits = 3, zero = false, reference, minRight = 0,
}: { title: string; rows: ScoreRowSpec[]; digits?: number; zero?: boolean; reference?: { value: number; label: string }; minRight?: number }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const fmt = (v: number): string => v.toFixed(digits);

  const { domain, ticks } = useMemo(() => {
    const vals: number[] = [];
    for (const r of rows) if (r.est) { vals.push(r.est.value); if (r.est.ci) vals.push(r.est.ci[0], r.est.ci[1]); }
    if (reference) vals.push(reference.value);
    if (minRight) vals.push(minRight);
    if (!vals.length) return { domain: [0, 1] as [number, number], ticks: [0, 0.5, 1] };
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo || Math.abs(hi) || 1) * 0.14;
    lo = zero ? 0 : lo - pad;
    hi += pad;
    const s = scaleLinear().domain([lo, hi]).nice(4);
    const d = s.domain() as [number, number];
    return { domain: zero ? ([0, d[1]] as [number, number]) : d, ticks: s.ticks(4) };
  }, [rows, reference, zero, minRight]);

  const W = Math.max(280, width);
  const compact = W < 560;
  const labelW = compact ? 0 : 196;
  const left = labelW + 12, right = 20;
  const rowH = compact ? 62 : 48;
  const top = 6;
  const x = scaleLinear().domain(domain).range([left, Math.max(left + 60, W - right)]);
  const axisY = top + rowH * rows.length + 4;
  const H = axisY + 26 + (reference ? 14 : 0);

  return (
    <div ref={box} className="sc-scores">
      {width > 0 && (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`t-${uid}`}>
          <title id={`t-${uid}`}>{`${title}. ${rows.map((r) => `${r.label}: ${r.est ? `${fmt(r.est.value)}${r.est.ci ? `, interval ${fmt(r.est.ci[0])} to ${fmt(r.est.ci[1])}` : ", no interval"}` : "not reported"}`).join(". ")}.`}</title>
          {ticks.map((t) => (
            <g key={t}>
              <line className="svg-grid" x1={x(t)} x2={x(t)} y1={top} y2={axisY} />
              <text className="svg-text" x={x(t)} y={axisY + 15} textAnchor="middle">{fmt(t)}</text>
            </g>
          ))}
          <line className="svg-axis" x1={left} x2={W - right} y1={axisY} y2={axisY} />
          {reference && (
            <g className="sc-ref">
              <line x1={x(reference.value)} x2={x(reference.value)} y1={top} y2={axisY} />
              <text className="svg-text svg-text--strong" x={x(reference.value)} y={axisY + 28} textAnchor="middle">{reference.label}</text>
            </g>
          )}
          {rows.map((r, i) => {
            const cy = top + rowH * i + (compact ? 40 : rowH / 2);
            const valueText = r.est ? `${fmt(r.est.value)}${r.est.ci ? ` (${fmt(r.est.ci[0])} to ${fmt(r.est.ci[1])})` : " (no interval yet)"}` : "not reported";
            return (
              <g key={r.id} className="sc-row" data-kind={r.kind}>
                {i > 0 && <line className="svg-grid" x1={compact ? 0 : 0} x2={W} y1={top + rowH * i} y2={top + rowH * i} opacity={0.6} />}
                {compact ? (
                  <>
                    <text className={r.kind === "ours" ? "sc-label sc-label--ours" : "sc-label"} x={0} y={top + rowH * i + 18}>{r.label}</text>
                    <text className="svg-text sc-value" x={0} y={top + rowH * i + 33}>{valueText}</text>
                  </>
                ) : (
                  <>
                    <text className={r.kind === "ours" ? "sc-label sc-label--ours" : "sc-label"} x={0} y={cy - 4}>{r.label}</text>
                    <text className="svg-text sc-value" x={0} y={cy + 12}>{valueText}</text>
                  </>
                )}
                {r.est ? (
                  <g>
                    {r.est.ci && (
                      <g className="sc-whisker">
                        <line x1={x(r.est.ci[0])} x2={x(r.est.ci[1])} y1={cy} y2={cy} />
                        <line x1={x(r.est.ci[0])} x2={x(r.est.ci[0])} y1={cy - 5} y2={cy + 5} />
                        <line x1={x(r.est.ci[1])} x2={x(r.est.ci[1])} y1={cy - 5} y2={cy + 5} />
                      </g>
                    )}
                    {r.kind === "ours" && <circle className="sc-dot" cx={x(r.est.value)} cy={cy} r={5.5} />}
                    {r.kind === "other" && <path className="sc-diamond" d={`M ${x(r.est.value)} ${cy - 6} l 6 6 l -6 6 l -6 -6 z`} />}
                    {r.kind === "candidate" && <circle className="sc-dot sc-dot--cand" cx={x(r.est.value)} cy={cy} r={6} />}
                  </g>
                ) : (
                  <text className="svg-text" x={left + 4} y={cy + 4}>not in the report</text>
                )}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

/**
 * Time to progress, predicted against observed minutes, in groups of cases ordered from the shortest predicted wait to the longest.
 * An outlined bar is what the head predicted; a solid bar is what was observed (Kaplan-Meier, which handles spells still running).
 */
export function TteChart({ pairs }: { pairs: { n: number | null; predicted: number; observed: number }[] }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const groups = useMemo(() => [...pairs].sort((a, b) => a.predicted - b.predicted), [pairs]);
  const W = Math.max(280, width);
  const compact = W < 420;
  const left = 38, right = 8, top = 22, plotH = compact ? 150 : 170;
  const maxV = Math.max(0.1, ...groups.flatMap((g) => [g.predicted, g.observed]));
  const y = scaleLinear().domain([0, maxV]).nice(4).range([top + plotH, top]);
  const ticks = y.ticks(4);
  const slot = (W - left - right) / Math.max(1, groups.length);
  const bw = Math.min(30, slot * 0.34);
  const axisY = top + plotH;
  const H = axisY + 44;
  return (
    <div ref={box} className="sc-scores">
      {width > 0 && groups.length > 0 && (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`t-${uid}`}>
          <title id={`t-${uid}`}>{`Predicted and observed minutes to progress in ${groups.length} groups of cases. ${groups.map((g, i) => `Group ${i + 1}: predicted ${g.predicted.toFixed(2)}, observed ${g.observed.toFixed(2)}`).join(". ")}.`}</title>
          {ticks.map((t) => (
            <g key={t}>
              <line className="svg-grid" x1={left} x2={W - right} y1={y(t)} y2={y(t)} />
              <text className="svg-text" x={left - 6} y={y(t) + 3.5} textAnchor="end">{t}</text>
            </g>
          ))}
          <text className="svg-text" x={left} y={12}>minutes to progress</text>
          <line className="svg-axis" x1={left} x2={W - right} y1={axisY} y2={axisY} />
          {groups.map((g, i) => {
            const cx = left + slot * (i + 0.5);
            return (
              <g key={i}>
                <rect className="sc-tte sc-tte--pred" x={cx - bw - 2} y={y(g.predicted)} width={bw} height={Math.max(0, axisY - y(g.predicted))} />
                <rect className="sc-tte sc-tte--obs" x={cx + 2} y={y(g.observed)} width={bw} height={Math.max(0, axisY - y(g.observed))} />
                <text className="svg-text sc-n" x={cx - bw / 2 - 2} y={y(g.predicted) - 4} textAnchor="middle">{g.predicted.toFixed(2)}</text>
                <text className="svg-text sc-n" x={cx + bw / 2 + 2} y={y(g.observed) - 4} textAnchor="middle">{g.observed.toFixed(2)}</text>
                <text className="svg-text" x={cx} y={axisY + 15} textAnchor="middle">{i + 1}</text>
                {g.n !== null && !compact && <text className="svg-text" x={cx} y={axisY + 29} textAnchor="middle">n {g.n.toLocaleString("en-GB")}</text>}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
