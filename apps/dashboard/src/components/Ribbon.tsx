import { useId } from "react";
import { useWidth } from "../hooks";
import { connectorPath, describeColumn, layoutRibbon, type RibbonColumn, type Voice } from "../lib/ribbon";
import { fmtDuration } from "../lib/format";
import type { Genome } from "../types";

interface Props {
  genome: Genome;
  active: number | null;
  onActive: (i: number | null) => void;
  /** "you": the lanes are the experienced worker and you, and no person id is drawn (the worker view). */
  voice?: Voice;
}

const charW = 5.9;

/** Longest label that fits: full, stacked words, the longest word, then shortened words. */
function blockLines(cog: string, w: number): string[] | null {
  const fits = (lines: string[]) => Math.max(...lines.map((l) => l.length)) * charW + 8 <= w;
  const full = cog.replace(/_/g, " ");
  const parts = cog.split("_");
  const short = parts.map((p) => (p.length > 5 ? p.slice(0, 4) : p));
  for (const c of [[full], parts, [parts.reduce((a, b) => (b.length > a.length ? b : a))], short]) {
    if (fits(c)) return c;
  }
  return null;
}

/** The work ribbon: expert above novice, matched steps joined, gaps hatched, seconds lost in red beneath. */
export function Ribbon({ genome, active, onActive, voice = "group" }: Props) {
  const you = voice === "you";
  const [ref, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const narrow = width > 0 && width < 640;
  const left = narrow ? 0 : 104;
  const laneH = narrow ? 34 : 44;
  const connH = narrow ? 34 : 54;
  const labelH = narrow ? 18 : 0;
  const lostH = 74;
  const inner = Math.max(240, width - left);
  const layout = width ? layoutRibbon(genome, inner, narrow ? 2 : 3, narrow ? 16 : 30) : null;

  const yE = labelH;
  const yConn = yE + laneH;
  const yN = yConn + connH;
  const yLostTop = yN + laneH + 18 + (narrow ? 18 : 0);
  const yBase = yLostTop + lostH;
  const H = yBase + 22;

  return (
    <div ref={ref} className="ribbon">
      {layout && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="group" aria-label={`Work ribbon. ${you ? "Experienced worker" : "Expert"} ${fmtDuration(layout.expertTotal)}, ${you ? "you" : "novice"} ${fmtDuration(layout.noviceTotal)}, ${Math.round(layout.totalLost)} seconds lost in total.`}>
          <defs>
            {(["expert", "novice"] as const).map((k) => (
              <pattern key={k} id={`hatch-${k}-${uid}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="6" style={{ stroke: `var(--${k})`, strokeWidth: 1.4, opacity: 0.55 }} />
              </pattern>
            ))}
          </defs>

          {/* Lane labels */}
          {narrow ? (
            <>
              <text className="svg-text svg-text--strong" x={0} y={12}>{you ? "Experienced worker" : "Expert"} <tspan className="svg-text">{you ? "" : `${genome.expert_person} · `}{fmtDuration(layout.expertTotal)}</tspan></text>
              <text className="svg-text svg-text--strong" x={0} y={yN + laneH + 14}>{you ? "You" : "Novice"} <tspan className="svg-text">{you ? "" : `${genome.person} · `}{fmtDuration(layout.noviceTotal)}</tspan></text>
            </>
          ) : (
            <>
              <text className="svg-text svg-text--strong" x={0} y={yE + 14}>{you ? "EXPERIENCED" : "EXPERT"}</text>
              <text className="svg-text" x={0} y={yE + 28}>{you ? "worker" : genome.expert_person}</text>
              <text className="svg-text" x={0} y={yE + 42}>{fmtDuration(layout.expertTotal)}</text>
              <text className="svg-text svg-text--strong" x={0} y={yN + 14}>{you ? "YOU" : "NOVICE"}</text>
              <text className="svg-text" x={0} y={yN + 28}>{you ? fmtDuration(layout.noviceTotal) : genome.person}</text>
              {!you && <text className="svg-text" x={0} y={yN + 42}>{fmtDuration(layout.noviceTotal)}</text>}
            </>
          )}

          <g transform={`translate(${left},0)`}>
            {layout.columns.map((c) => (
              <Column key={c.index} c={c} uid={uid} yE={yE} yN={yN} laneH={laneH} yBase={yBase} lostH={lostH} maxLost={layout.maxLost} narrow={narrow}
                active={active === c.index} dim={active != null && active !== c.index} />
            ))}

            {/* Seconds-lost scale */}
            <line className="svg-grid" x1={0} x2={layout.width} y1={yLostTop} y2={yLostTop} />
            <line className="svg-axis" x1={0} x2={layout.width} y1={yBase} y2={yBase} />
            {layout.columns.map((c) => (
              <rect key={`hit${c.index}`} className="rb-col-hit mark-hit" x={c.x - 1} y={0} width={c.w + 2} height={yBase} tabIndex={0}
                role="img" aria-label={describeColumn(c, c.index, layout.columns.length, voice)}
                onMouseEnter={() => onActive(c.index)} onMouseLeave={() => onActive(null)} onFocus={() => onActive(c.index)} onBlur={() => onActive(null)} />
            ))}
          </g>
          <text className="svg-text" x={0} y={yLostTop + 4}>{narrow ? `${Math.round(layout.maxLost)} s` : `${Math.round(layout.maxLost)} s lost`}</text>
          <text className="svg-text" x={0} y={yBase + 14}>0</text>
          {!narrow && <text className="svg-text" x={0} y={yLostTop + 20}>SECONDS LOST</text>}
        </svg>
      )}
    </div>
  );
}

function Column({ c, uid, yE, yN, laneH, yBase, lostH, maxLost, narrow, active, dim }: {
  c: RibbonColumn; uid: string; yE: number; yN: number; laneH: number; yBase: number; lostH: number; maxLost: number; narrow: boolean; active: boolean; dim: boolean;
}) {
  const path = connectorPath(c, yE + laneH, yN);
  const lostBar = maxLost > 0 ? (c.lost / maxLost) * (lostH - 22) : 0;
  const barW = Math.max(6, c.w - 4);
  const blank = (lane: "expert" | "novice", y: number) => (
    <rect x={c.x} y={y} width={c.w} height={laneH} rx={2} style={{ fill: `url(#hatch-${lane}-${uid})` }} className={lane === "expert" ? "rb-gap-expert" : "rb-gap-novice"} />
  );
  const lines = (cog: string, w: number, cls: string, y: number, x: number) => {
    const l = blockLines(cog, w);
    if (!l || narrow && w < 40) return null;
    const lh = 10.5;
    const top = y + laneH / 2 - ((l.length - 1) * lh) / 2 + 3.4;
    return l.map((t, i) => (
      <text key={i} className={`rb-text ${cls}`} x={x + 5} y={top + i * lh}>{t}</text>
    ));
  };
  return (
    <g className="rb-col" data-active={active} data-dim={dim}>
      {path && <path className="rb-connector" d={path} />}
      {c.expert ? (
        <>
          <rect className="rb-expert" x={c.expert.x} y={yE} width={Math.max(2, c.expert.w)} height={laneH} rx={2} />
          {lines(c.expert.cog, c.expert.w, "rb-text--on-expert", yE, c.expert.x)}
        </>
      ) : blank("expert", yE)}
      {c.novice ? (
        <>
          <rect className="rb-novice" x={c.novice.x} y={yN} width={Math.max(2, c.novice.w)} height={laneH} rx={2} />
          {/* The step is named once per column: on the novice lane only when it differs from the expert's (the column's accessible name says both). */}
          {!(c.expert && c.expert.cog === c.novice.cog) && lines(c.novice.cog, c.novice.w, "rb-text--on-novice", yN, c.novice.x)}
        </>
      ) : (
        <>
          {blank("novice", yN)}
          {c.expert && !narrow && c.w >= 50 && <text className="rb-text" style={{ fill: "var(--novice)" }} x={c.x + 5} y={yN + laneH / 2 + 3.4}>skipped</text>}
        </>
      )}
      {c.lost >= 1 && (
        <>
          <rect className="rb-lost" x={c.x + (c.w - barW) / 2} y={yBase - lostBar} width={barW} height={Math.max(1.5, lostBar)} rx={1.5} />
          <text className="rb-lost-text" x={c.x + c.w / 2} y={yBase - lostBar - 5} textAnchor="middle">{Math.round(c.lost)}</text>
        </>
      )}
    </g>
  );
}
