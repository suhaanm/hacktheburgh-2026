import { useId } from "react";
import { useWidth } from "../hooks";
import { OP_LABEL, alignmentTotals, enumLabel } from "../lib/week";
import type { RibbonOp } from "../types";

/**
 * Your week and the nearest expert's week, lined up block by block (the work ribbon, for a calendar).
 * Width: minutes. Top row: the expert. Bottom row: you. Hatched and dashed: that side has nothing there.
 * Red underline: minutes that are out of step with the expert. Time inside a block is not drawn; only the order of kinds is compared.
 */
export function CalAlignment({ alignment }: { alignment: RibbonOp[] }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const cols = alignment.map((c) => ({ ...c, w: Math.max(3, Number.isFinite(c.minutes) ? c.minutes : 0) }));
  const totalW = cols.reduce((a, c) => a + c.w, 0) || 1;
  const labelW = width && width < 520 ? 0 : 52;
  const gap = 1;
  const avail = Math.max(120, width - labelW - 2) - gap * cols.length;
  const rowH = 28, top = 6, mid = 4;
  const H = top + rowH * 2 + mid + 14;
  const t = alignmentTotals(alignment);
  let x = labelW;
  return (
    <div ref={box} className="chart">
      {width > 0 && cols.length > 0 && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img"
          aria-label={`Your week lined up with the nearest expert's. ${Math.round(t.matched)} minutes match, ${Math.round(t.mismatch)} differ, ${Math.round(t.learnerOnly)} are only in your week and ${Math.round(t.expertOnly)} are only in the expert's.`}>
          <defs>
            <pattern id={`ce-${uid}`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" style={{ stroke: "var(--expert)", strokeWidth: 1.2, opacity: 0.8 }} /></pattern>
            <pattern id={`cn-${uid}`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" style={{ stroke: "var(--novice)", strokeWidth: 1.2, opacity: 0.8 }} /></pattern>
          </defs>
          {labelW > 0 && <>
            <text className="hm-day" x={0} y={top + rowH / 2 + 4} style={{ cursor: "default" }}>Expert</text>
            <text className="hm-day" x={0} y={top + rowH + mid + rowH / 2 + 4} style={{ cursor: "default" }}>You</text>
          </>}
          {cols.map((c, i) => {
            const w = (c.w / totalW) * avail;
            const x0 = x; x += w + gap;
            const out = c.op !== "match";
            const hasE = c.expert != null, hasL = c.learner != null;
            return (
              <g key={i}>
                <rect x={x0} y={top} width={w} height={rowH} rx={2} className={hasE ? "rb-expert" : ""} style={hasE ? undefined : { fill: `url(#ce-${uid})`, stroke: "var(--expert)", strokeDasharray: "3 2", strokeWidth: 1 }} />
                <rect x={x0} y={top + rowH + mid} width={w} height={rowH} rx={2} className={hasL ? "rb-novice" : ""} style={hasL ? undefined : { fill: `url(#cn-${uid})`, stroke: "var(--novice)", strokeDasharray: "3 2", strokeWidth: 1 }} />
                {hasE && w > 54 && <text className="rb-text rb-text--on-expert" x={x0 + 5} y={top + rowH / 2 + 3.5}>{enumLabel(c.expert)}</text>}
                {hasL && w > 54 && <text className="rb-text rb-text--on-novice" x={x0 + 5} y={top + rowH + mid + rowH / 2 + 3.5}>{enumLabel(c.learner)}</text>}
                {out && <rect x={x0} y={top + rowH * 2 + mid + 3} width={w} height={3} className="rb-lost" />}
                <title>{`${OP_LABEL[c.op] ?? c.op}: expert ${enumLabel(c.expert)}, you ${enumLabel(c.learner)}, ${Math.round(c.minutes)} min`}</title>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

export function AlignLegend() {
  return (
    <ul className="legend" aria-label="How to read the alignment">
      <li className="legend__item"><span className="sw" style={{ background: "var(--expert)" }} />The expert's block</li>
      <li className="legend__item"><span className="sw" style={{ background: "var(--novice)" }} />Your block</li>
      <li className="legend__item"><span className="sw sw--hatch sw--muted" />Nothing on this side</li>
      <li className="legend__item"><span className="sw" style={{ background: "var(--bad)", height: 3, alignSelf: "center" }} />Out of step with the expert</li>
    </ul>
  );
}
