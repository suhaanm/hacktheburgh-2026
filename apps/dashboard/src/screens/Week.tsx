import { api } from "../api";
import { useLoad } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, Loading, OriginBadge, PageHead } from "../components/common";
import { WeekLegend, WeekRibbon } from "../components/WeekRibbon";
import { DAY_NAMES, KIND_LABEL, featureLabel, fmtFeature, gapClear, spans, toMinutes, weekHeadline, weekWindow } from "../lib/week";
import { fmtInterval } from "../lib/format";
import type { CalSuggestion, CalendarWeek, GapRow } from "../types";

const BUCKET: Record<string, string> = { lt5: "fewer than 5", "5to9": "5 to 9", "10plus": "10 or more" };
const val = (k: string, v: number | string) => (typeof v === "number" ? fmtFeature(k, v) : BUCKET[v] ?? String(v));

export default function Week() {
  const w = useLoad(() => api.calendarWeek(), []);
  const sg = useLoad(() => api.calendarSuggestions(), []);

  if (w.status === "error" && !w.data) return <div className="page"><ErrorState error={w.error} retry={w.reload} what="your week" /></div>;
  if (!w.data) return <div className="page"><Loading label="Loading your week" /></div>;
  const d = w.data;
  const win = weekWindow(d.days, d.expert.days);
  const empty = d.days.every((x) => x.blocks.length === 0);

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="Week"
        title={weekHeadline(d.features, d.expert)}
        lede="Your week of calendar blocks next to the expert's. Only the kind of block, its time and how many people were in it are used. No titles or names exist in this data."
        aside={<OriginBadge meta={w.meta} />}
      />

      <section className="hero" aria-labelledby="wk-h">
        <h2 id="wk-h" className="u-sr-only">Week ribbon</h2>
        {empty ? (
          <EmptyState title="No calendar blocks yet" body="When a calendar source is connected, your week appears here. Nothing is read until you connect one." />
        ) : (
          <div className="stack">
            <div className="chart chart--wide stack" style={{ gap: "var(--space-6)" }}>
              <WeekRibbon title="Your week" days={d.days} window={win} />
              {d.expert.days && d.expert.days.length > 0 && <WeekRibbon title="The expert's week" days={d.expert.days} window={win} />}
            </div>
            <WeekLegend />
            <ChartFoot meta={w.meta} />
            <WeekTable days={d.days} />
          </div>
        )}
      </section>

      <hr className="rule" />
      <GapTable rows={d.gap.rows} meta={w.meta} features={d} />

      <hr className="rule" />
      <Suggestions state={sg} />
    </div>
  );
}

function WeekTable({ days }: { days: CalendarWeek["days"] }) {
  const fmt = (v: string | number) => { const m = toMinutes(v); return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
  return (
    <details className="details-lite">
      <summary>See your week as a table</summary>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Day</th><th>Block</th><th>From</th><th>To</th><th>People</th></tr></thead>
        <tbody>{days.flatMap((day) => spans(day.blocks).map((s, i) => (
          <tr key={`${day.dow}-${i}`}><td>{DAY_NAMES[day.dow] ?? day.dow}</td><td>{KIND_LABEL[s.kind]}</td><td className="num">{fmt(s.from)}</td><td className="num">{fmt(s.to)}</td><td>{s.attendees ? BUCKET[s.attendees] : ""}</td></tr>
        )))}</tbody>
      </table></div>
    </details>
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

function GapTable({ rows, meta, features }: { rows: GapRow[]; meta: ReturnType<typeof useLoad<CalendarWeek>>["meta"]; features: CalendarWeek }) {
  void features;
  return (
    <section className="section" aria-labelledby="gap-h">
      <div className="section__head">
        <h2 className="section__title" id="gap-h">Where your week differs</h2>
        <p className="section__sub">Your number, the expert's, and the difference with its 95% interval. A difference whose interval stays on one side of zero is marked clear.</p>
      </div>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>What</th><th className="num">You</th><th className="num">Expert</th><th className="num">Difference</th><th>95% interval</th><th className="hide-narrow" aria-hidden="true" /><th className="hide-narrow">Read</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.feature}>
            <td>{featureLabel(r.feature)}</td>
            <td className="num">{fmtFeature(r.feature, r.learner)}</td>
            <td className="num">{fmtFeature(r.feature, r.expert)}</td>
            <td className="num"><b>{fmtFeature(r.feature, r.delta, true)}</b></td>
            <td className="num interval">{fmtInterval(r.ci, Math.abs(r.delta) < 10 ? 1 : 0)}</td>
            <td className="hide-narrow"><DeltaBar delta={r.delta} ci={r.ci} /></td>
            <td className="hide-narrow">{gapClear(r) ? <span className="pill"><b>clear</b></span> : <span className="pill">within noise</span>}</td>
          </tr>))}</tbody>
      </table></div>
      <ChartFoot meta={meta} />
    </section>
  );
}

function Suggestions({ state }: { state: ReturnType<typeof useLoad<CalSuggestion[]>> }) {
  if (state.status === "error" && !state.data) return <ErrorState error={state.error} retry={state.reload} what="suggestions" />;
  if (!state.data) return <Loading label="Loading suggestions" />;
  const list = state.data.slice(0, 5);
  return (
    <section className="section" aria-labelledby="sug-h">
      <div className="section__head">
        <h2 className="section__title" id="sug-h">Ideas for a calmer week</h2>
        <p className="section__sub">Chosen by code from a fixed list, then worded from the numbers above. They cite your numbers and the expert's. None of them is acted on.</p>
      </div>
      {list.length === 0 ? <EmptyState title="Nothing to suggest" body="Your week is close to the expert's, so there is nothing worth changing right now." /> : (
        <div className="sug-grid">
          {list.map((s) => (
            <article key={s.id} className="card card__pad sug" aria-label={s.text}>
              <p className="sug__text">{s.text}</p>
              <dl className="sug__nums">
                {Object.keys(s.numbers).map((k) => (
                  <div key={k}><dt>{featureLabel(k)}</dt><dd><b className="tabular">{val(k, s.numbers[k])}</b><span className="u-muted"> you</span> · <span className="tabular">{s.expert_ref[k] != null ? val(k, s.expert_ref[k]) : "not given"}</span><span className="u-muted"> expert</span></dd></div>
                ))}
              </dl>
              <div className="row">
                <span className="pill">{s.risk === "low" ? "Low risk" : s.risk}</span>
                <span className="pill">{s.template.replace(/_/g, " ")}</span>
              </div>
              <p className="note">{s.can_draft ? "Draft only. Nothing is sent, booked or changed." : "No draft is available for this one. Nothing is sent, booked or changed."}</p>
            </article>
          ))}
        </div>
      )}
      <ChartFoot meta={state.meta} />
    </section>
  );
}
