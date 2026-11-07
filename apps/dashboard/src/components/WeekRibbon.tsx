import { useId } from "react";
import { useWidth } from "../hooks";
import { DAY_NAMES, KIND_LABEL, minutesByKind, spans } from "../lib/week";
import type { CalDay } from "../types";

/**
 * One week, a row per day, time across. Block kinds are separate fills (a legend names them); a meeting is darker when more people are in it.
 * The ribbon holds no titles or names because the data has none.
 */
export function WeekRibbon({ title, days, window: win }: { title: string; days: CalDay[]; window: [number, number] }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const labelW = width && width < 520 ? 32 : 44;
  const rowH = width && width < 520 ? 24 : 28;
  const axisH = 20;
  const [lo, hi] = win;
  const px = (m: number) => labelW + ((m - lo) / (hi - lo)) * Math.max(10, width - labelW - 2);
  const H = axisH + 7 * rowH + 2;
  const hours: number[] = [];
  for (let m = lo; m <= hi; m += 60) hours.push(m);
  const step = hours.length > 12 ? 2 : 1;
  const by = minutesByKind(days);
  const summary = (Object.keys(by) as (keyof typeof by)[]).map((k) => `${KIND_LABEL[k]} ${Math.round(by[k] / 60 * 10) / 10} hours`).join(", ");
  const byDow = new Map(days.map((d) => [d.dow, d]));
  return (
    <div ref={box} className="weekribbon">
      <p className="t-label">{title}</p>
      {width > 0 && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${title}. ${summary}.`}>
          <defs>
            <pattern id={`off-${uid}`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="5" style={{ stroke: "var(--muted)", strokeWidth: 1.2, opacity: 0.7 }} />
            </pattern>
          </defs>
          {hours.map((m, i) => (i % step === 0 || m === hi ? (
            <g key={m}>
              <line className="svg-grid" x1={px(m)} x2={px(m)} y1={axisH - 4} y2={H - 2} />
              <text className="svg-text" x={px(m)} y={12} textAnchor={m === hi ? "end" : "middle"}>{String(Math.floor(m / 60)).padStart(2, "0")}</text>
            </g>
          ) : null))}
          {DAY_NAMES.map((name, dow) => {
            const y = axisH + dow * rowH;
            const d = byDow.get(dow);
            const sp = d ? spans(d.blocks) : [];
            return (
              <g key={name}>
                <text className="hm-day" style={{ cursor: "default" }} x={0} y={y + rowH / 2 + 4}>{name}</text>
                {sp.length === 0 && <text className="svg-text" x={px(lo) + 6} y={y + rowH / 2 + 3.5}>{d && d.working === false ? "day off" : "no blocks"}</text>}
                {sp.map((s, i) => {
                  const x = px(s.from), w = Math.max(1.5, px(s.to) - px(s.from) - 1);
                  const cls = s.kind === "meeting" ? `cb-meeting cb-meeting--${s.attendees ?? "none"}` : `cb-${s.kind}`;
                  return (
                    <rect key={i} className={cls} x={x} y={y + 3} width={w} height={rowH - 6} rx={2} style={s.kind === "offscreen" ? { fill: `url(#off-${uid})` } : undefined}>
                      <title>{`${KIND_LABEL[s.kind]}${s.attendees ? `, ${s.attendees === "lt5" ? "fewer than 5" : s.attendees === "5to9" ? "5 to 9" : "10 or more"} people` : ""}, ${fmt(s.from)} to ${fmt(s.to)}`}</title>
                    </rect>
                  );
                })}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

export function WeekLegend() {
  return (
    <ul className="legend" aria-label="How to read the week">
      <li className="legend__item"><span className="sw cb-meeting cb-meeting--5to9" style={{ display: "inline-block" }} />Meeting (darker: more people)</li>
      <li className="legend__item"><span className="sw sw--accent" />Focus</li>
      <li className="legend__item"><span className="sw sw--good" />Break</li>
      <li className="legend__item"><span className="sw sw--hatch sw--muted" />Off the computer</li>
      <li className="legend__item"><span className="sw" style={{ border: "1px dashed var(--line-strong)", background: "transparent" }} />Free (no block)</li>
    </ul>
  );
}
