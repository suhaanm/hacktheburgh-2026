import { useState } from "react";
import { ChartFoot, EmptyState, ErrorState, Loading } from "../common";
import { AlignLegend, CalAlignment } from "../CalAlignment";
import { Hint } from "../Hint";
import { Details, fitItems } from "../ui";
import { DAY_NAMES, KIND_LABEL, alignmentTotals, featureLabel, featureUnit, fmtFeature, gapClear, sortGaps, spans, splitSentence, toMinutes } from "../../lib/week";
import { fmtInterval } from "../../lib/format";
import type { LoadState } from "../../hooks";
import type { CalSuggestion, CalendarWeek, GapRow } from "../../types";

// The parts of "Where my time goes" that draw the worker's calendar week against ONE experienced worker's.
// Nothing here names another person, counts people, or draws a cohort figure (docs/knack-ux/views.md): the baseline is "an experienced worker".

type Meta = LoadState<CalendarWeek>["meta"];

const BUCKET: Record<string, string> = { lt5: "fewer than 5", "5to9": "5 to 9", "10plus": "10 or more" };
const val = (k: string, v: number | string) => (typeof v === "number" ? fmtFeature(k, v) : BUCKET[v] ?? String(v));

/** The week as a table: seven rows, then "Show all N". */
export function WeekTable({ days }: { days: CalendarWeek["days"] }) {
  const [all, setAll] = useState(false);
  const fmt = (v: string | number) => { const m = toMinutes(v); return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
  const rows = days.flatMap((day) => spans(day.blocks).map((sp, i) => ({ key: `${day.dow}-${i}`, day: DAY_NAMES[day.dow] ?? String(day.dow), sp })));
  const shown = all ? rows : rows.slice(0, 7);
  return (
    <Details summary="Your week as a table" wide>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Day</th><th>Block</th><th>From</th><th>To</th><th>Meeting size</th></tr></thead>
        <tbody>{shown.map(({ key, day, sp }) => (
          <tr key={key}><td>{day}</td><td>{KIND_LABEL[sp.kind]}</td><td className="num">{fmt(sp.from)}</td><td className="num">{fmt(sp.to)}</td><td>{sp.attendees ? BUCKET[sp.attendees] : ""}</td></tr>
        ))}</tbody>
      </table></div>
      {rows.length > 7 && <button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>}
    </Details>
  );
}

/** A zero line, the point and its interval, per row. Each row has its own scale (units differ), so read it for direction and certainty only. */
function DeltaBar({ delta, ci }: { delta: number; ci: [number, number] }) {
  const m = Math.max(Math.abs(ci[0]), Math.abs(ci[1]), Math.abs(delta)) * 1.15 || 1;
  const x = (v: number) => 60 + (v / m) * 56;
  return (
    <svg width="120" height="16" viewBox="0 0 120 16" aria-hidden="true">
      <line x1={60} x2={60} y1={1} y2={15} className="ev-truth" />
      <line x1={x(ci[0])} x2={x(ci[1])} y1={8} y2={8} className="dw-line" />
      <line x1={x(ci[0])} x2={x(ci[0])} y1={4} y2={12} className="dw-line" />
      <line x1={x(ci[1])} x2={x(ci[1])} y1={4} y2={12} className="dw-line" />
      <circle cx={x(delta)} cy={8} r={3.5} className="dw-dot" />
    </svg>
  );
}

const SHOWN = 6;
/** Where the week differs from the experienced worker's: six rows, then "Show all N". No spread among other people is drawn. */
export function GapTable({ rows, meta }: { rows: GapRow[]; meta: Meta }) {
  const [all, setAll] = useState(false);
  const sorted = sortGaps(rows);
  const shown = all ? sorted : sorted.slice(0, SHOWN);
  const clear = rows.filter(gapClear).length;
  if (rows.length === 0) return <EmptyState title="Nothing to compare yet" body="Differences appear once a full week has been read." />;
  return (
    <div className="stack">
      <div className="table-wrap"><table className="table">
        <thead><tr><th>What</th><th className="num">You</th><th className="num">Experienced worker</th><th className="num">Difference</th><th>95% interval</th><th className="hide-narrow" aria-hidden="true" /><th className="hide-narrow">Read</th></tr></thead>
        <tbody>{shown.map((r) => (
          <tr key={r.feature}>
            <td>{featureLabel(r.feature)}</td>
            <td className="num">{fmtFeature(r.feature, r.learner)}</td>
            <td className="num">{fmtFeature(r.feature, r.expert)}</td>
            <td className="num"><b>{fmtFeature(r.feature, r.delta, true)}</b></td>
            <td className="num interval">{fmtInterval(r.ci, featureUnit(r.feature) === "share" ? 2 : Math.abs(r.delta) < 10 ? 1 : 0)}</td>
            <td className="hide-narrow"><DeltaBar delta={r.delta} ci={r.ci} /></td>
            <td className="hide-narrow">{gapClear(r) ? <b>clear</b> : <span className="u-muted">within noise</span>}</td>
          </tr>))}</tbody>
      </table></div>
      {rows.length > SHOWN && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button></div>}
      <ChartFoot variant="about" brief meta={meta} extra={<span>{clear} of {rows.length} differences are clear: the 95% interval stays on one side of zero.</span>} />
    </div>
  );
}

/** How far this week is from the experienced worker's: the distance, the share out of step, and the lined-up blocks. */
export function Distance({ d, meta }: { d: CalendarWeek; meta: Meta }) {
  const r = d.gap.ribbon;
  if (!r || !r.alignment || r.alignment.length === 0) return null;
  const t = alignmentTotals(r.alignment);
  const pct = (x: number) => (t.total > 0 ? `${Math.round((x / t.total) * 100)}%` : "0%");
  return (
    <div className="stack">
      <div className="stats">
        <div className="stat"><span className="stat__label">Distance<Hint label="About the distance">0 is identical, 1 is entirely different.</Hint></span><span className="stat__value tabular">{r.distance.toFixed(2)}</span></div>
        <div className="stat"><span className="stat__label">Out of step</span><span className="stat__value tabular">{pct(t.outOfStep)}</span><span className="stat__meta">{Math.round(t.outOfStep)} of {Math.round(t.total)} minutes</span></div>
      </div>
      <div className="chart chart--wide stack">
        <CalAlignment alignment={r.alignment} />
        <AlignLegend />
        <ChartFoot variant="about" meta={meta} brief />
      </div>
    </div>
  );
}

/** Ideas for a calmer week: three rows, each with its working-out closed, and one line saying nothing is sent, booked or changed. */
export function Suggestions({ state }: { state: LoadState<CalSuggestion[]> }) {
  const [all, setAll] = useState(false);
  if (state.status === "error" && !state.data) return <ErrorState error={state.error} retry={state.reload} what="suggestions" />;
  if (!state.data) return <Loading label="Loading suggestions" />;
  const list = state.data.slice(0, 5);
  const shown = all ? list : list.slice(0, 3);
  if (list.length === 0) return <EmptyState title="Nothing to suggest" body="Your week is close to the experienced worker's, so there is nothing worth changing now." />;
  return (
    <div className="stack">
      <ul className="plain-list sug-list" aria-label="Ideas, none acted on">
        {shown.map((sg) => {
          const [first, rest] = splitSentence(sg.text);
          const nums = Object.keys(sg.numbers);
          return (
            <li key={sg.id} className="sug sug-item">
              {sg.title && <b className="sug__title">{sg.title}</b>}
              <span className="sug__text">{first}</span>
              {(rest || nums.length > 0) && (
                <Details summary="Worked out">
                  <div className="stack" style={{ gap: "var(--space-2)" }}>
                    {rest && <p className="note">{rest}</p>}
                    <dl className="sug__nums">
                      {nums.map((k) => (
                        <div key={k}><dt>{featureLabel(k)}</dt><dd><b className="tabular">{val(k, sg.numbers[k])}</b><span className="u-muted"> you</span> · <span className="tabular">{sg.expert_ref[`${k}_reference`] != null ? val(k, sg.expert_ref[`${k}_reference`]) : sg.expert_ref[k] != null ? val(k, sg.expert_ref[k]) : "not given"}</span><span className="u-muted"> experienced worker</span></dd></div>
                      ))}
                    </dl>
                    <p className="note">{sg.can_draft ? "A draft can be prepared." : "No draft is available."}{sg.evidence_weeks ? ` Seen over ${sg.evidence_weeks} weeks.` : ""}{sg.risk !== "low" ? ` Risk: ${sg.risk}.` : ""}</p>
                  </div>
                </Details>
              )}
            </li>
          );
        })}
      </ul>
      <p className="note">Nothing is sent, booked or changed.</p>
      {list.length > 3 && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${list.length}`}</button></div>}
    </div>
  );
}

/** One short list: the lines that fit in about fifty words, the rest behind one closed More. */
export function ShortList({ items, maxWords = 50 }: { items: string[]; maxWords?: number }) {
  const { shown, rest } = fitItems(items, maxWords);
  return (
    <>
      <ul className="plain-list">{shown.map((t) => <li key={t} className="note">{t}</li>)}</ul>
      {rest.length > 0 && <Details summary={`More (${rest.length})`}><ul className="plain-list">{rest.map((t) => <li key={t} className="note">{t}</li>)}</ul></Details>}
    </>
  );
}
