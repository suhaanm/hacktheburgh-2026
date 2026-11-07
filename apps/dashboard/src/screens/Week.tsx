import { useEffect, useState } from "react";
import { api } from "../api";
import { idle, useLoad } from "../hooks";
import { useAppState } from "../store";
import { ChartFoot, EmptyState, ErrorState, ExampleBadge, Loading, OriginBadge, PageHead, SourceNote } from "../components/common";
import { WeekLegend, WeekRibbon } from "../components/WeekRibbon";
import { AlignLegend, CalAlignment } from "../components/CalAlignment";
import { Hint } from "../components/Hint";
import { Details } from "../components/ui";
import { DAY_NAMES, KIND_LABEL, alignmentTotals, featureLabel, featureUnit, fmtFeature, gapClear, peopleByGroup, sortGaps, spans, splitSentence, toMinutes, weekHeadline, weekLabel, weekWindow } from "../lib/week";
import { fmtInterval } from "../lib/format";
import type { CalPerson, CalSuggestion, CalendarWeek, GapRow } from "../types";

const BUCKET: Record<string, string> = { lt5: "fewer than 5", "5to9": "5 to 9", "10plus": "10 or more" };
const val = (k: string, v: number | string) => (typeof v === "number" ? fmtFeature(k, v) : BUCKET[v] ?? String(v));
const DEMO_PERSON = "p_ninetofive";

export default function Week() {
  const me = useAppState().person;
  const people = useLoad(() => api.calendarPeople(), []);
  const [person, setPerson] = useState<string | null>(null);
  const [week, setWeek] = useState<string | undefined>(undefined);

  // Start with the worker if they have a calendar, else the first demo person.
  useEffect(() => {
    if (person || !people.data) return;
    const known = new Set(people.data.map((p) => p.person));
    setPerson(me && known.has(me) ? me : known.has(DEMO_PERSON) ? DEMO_PERSON : people.data[0]?.person ?? DEMO_PERSON);
  }, [people.data, person, me]);

  const w = useLoad(() => (person ? api.calendarWeek(person, week) : idle<CalendarWeek>()), [person, week]);
  const sg = useLoad(() => (person ? api.calendarSuggestions(person, week) : idle<CalSuggestion[]>()), [person, week]);

  if (people.status === "error" && !people.data) return <div className="page"><ErrorState error={people.error} retry={people.reload} what="who has a calendar" /></div>;
  if (!person || !people.data) return <div className="page"><Loading label="Loading your week" /></div>;
  if (w.status === "error" && !w.data) return <div className="page"><ErrorState error={w.error} retry={w.reload} what="your week" /></div>;
  if (!w.data) return <div className="page"><Loading label="Loading your week" /></div>;
  const d = w.data;
  const win = weekWindow(d.days, d.expert.days);
  const empty = d.days.every((x) => x.blocks.length === 0);
  const example = !!w.why;
  const entry = people.data.find((p) => p.person === person);

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="Week"
        title={weekHeadline(d.features, d.expert, me && d.person === me ? null : entry?.label ?? "This person")}
        lede="Your calendar blocks next to the expert's. No titles or names exist in this data."
        aside={<><OriginBadge meta={w.meta} /><ExampleBadge why={w.why} /></>}
      />
      <SourceNote why={w.why} />

      <Pickers people={people.data} person={person} entry={entry} week={week ?? d.week} locked={example}
        onPerson={(p) => { setPerson(p); setWeek(undefined); }} onWeek={setWeek} />

      <section className="hero" aria-labelledby="wk-h">
        <h2 id="wk-h" className="u-sr-only">Week ribbon</h2>
        {empty ? (
          <EmptyState title="No calendar blocks this week" body="Nothing is on the calendar for this week, or no calendar source is connected yet. Nothing is read until you connect one." />
        ) : (
          <div className="stack">
            <div className="chart chart--wide stack" style={{ gap: "var(--space-6)" }}>
              <WeekRibbon title={`${me && d.person === me ? "Your" : entry?.label ? `${entry.label}'s` : "This"} week${d.week ? `, ${weekLabel(d.week)}` : ""}`} days={d.days} window={win} />
              {d.expert.days && d.expert.days.length > 0 && <WeekRibbon title={`The expert's week${typeof d.expert.person === "string" ? ` (${d.expert.person})` : ""}`} days={d.expert.days} window={win} />}
            </div>
            <WeekLegend />
            <ChartFoot variant="about" meta={w.meta} extra={<span>Only the kind of block, its time and how many people were in it are used.{d.timezone ? <> Times are in <b>{d.timezone}</b>.</> : null}</span>} />
            <WeekTable days={d.days} />
          </div>
        )}
      </section>

      {d.gap.ribbon?.alignment && d.gap.ribbon.alignment.length > 0 && <><hr className="rule" /><Distance d={d} meta={w.meta} /></>}

      <hr className="rule" />
      <GapTable rows={d.gap.rows} meta={w.meta} note={d.gap.interval} />

      <hr className="rule" />
      <Suggestions state={sg} />
    </div>
  );
}

function Pickers({ people, person, entry, week, locked, onPerson, onWeek }: {
  people: CalPerson[]; person: string; entry: CalPerson | undefined; week: string | undefined; locked: boolean; onPerson: (p: string) => void; onWeek: (w: string) => void;
}) {
  const weeks = entry?.weeks ?? [];
  const groups = peopleByGroup(people);
  return (
    <div className="row" style={{ alignItems: "flex-end" }}>
      <div className="field" style={{ minWidth: 220 }}>
        <label className="field__label" htmlFor="wk-person">Whose week</label>
        <select id="wk-person" className="select" value={person} disabled={locked} onChange={(e) => onPerson(e.target.value)}>
          {groups.map((g) => (
            <optgroup key={g.group} label={g.label}>
              {g.people.map((p) => <option key={p.person} value={p.person}>{p.label ?? p.person}</option>)}
            </optgroup>
          ))}
        </select>
      </div>
      <div className="field" style={{ minWidth: 180 }}>
        <label className="field__label" htmlFor="wk-week">Week</label>
        <select id="wk-week" className="select" value={week ?? ""} disabled={locked || weeks.length === 0} onChange={(e) => onWeek(e.target.value)}>
          {!weeks.includes(week ?? "") && week && <option value={week}>{weekLabel(week)}</option>}
          {weeks.map((x) => <option key={x} value={x}>{weekLabel(x)}</option>)}
        </select>
      </div>
      {locked && <p className="note" style={{ alignSelf: "center" }}>Choosing someone else needs the live engine.</p>}
    </div>
  );
}

function Distance({ d, meta }: { d: CalendarWeek; meta: ReturnType<typeof useLoad<CalendarWeek>>["meta"] }) {
  const r = d.gap.ribbon!;
  const t = alignmentTotals(r.alignment ?? []);
  const pct = (x: number) => (t.total > 0 ? `${Math.round((x / t.total) * 100)}%` : "0%");
  return (
    <section className="section" aria-labelledby="dist-h">
      <div className="section__head">
        <h2 className="section__title" id="dist-h">How far this week is from the nearest expert's</h2>
        <p className="section__sub">The two weeks lined up block by block.</p>
      </div>
      <div className="stats">
        <div className="stat"><span className="stat__label">Distance<Hint label="About the distance">0 is identical, 1 is entirely different.</Hint></span><span className="stat__value tabular">{r.distance.toFixed(2)}</span></div>
        {r.placebo && <div className="stat"><span className="stat__label">Placebo<Hint label="About the placebo">Expert weeks against each other, interval {fmtInterval(r.placebo.ci, 2)}{r.placebo.n_experts ? `, ${r.placebo.n_experts} experts` : ""}. Even two experts' weeks differ by about this much, so a distance near it is normal.</Hint></span><span className="stat__value tabular">{r.placebo.distance.toFixed(2)}</span></div>}
        <div className="stat"><span className="stat__label">Out of step</span><span className="stat__value tabular">{pct(t.outOfStep)}</span><span className="stat__meta">{Math.round(t.outOfStep)} of {Math.round(t.total)} minutes</span></div>
      </div>
      <div className="chart chart--wide stack">
        <CalAlignment alignment={r.alignment ?? []} />
        <AlignLegend />
        <ChartFoot variant="about" meta={meta} brief extra={r.nearest_expert ? <span>Nearest expert: <b>{r.nearest_expert}</b>.</span> : undefined} />
      </div>
    </section>
  );
}

function WeekTable({ days }: { days: CalendarWeek["days"] }) {
  const fmt = (v: string | number) => { const m = toMinutes(v); return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
  return (
    <Details summary="See your week as a table" wide>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Day</th><th>Block</th><th>From</th><th>To</th><th>People</th></tr></thead>
        <tbody>{days.flatMap((day) => spans(day.blocks).map((s, i) => (
          <tr key={`${day.dow}-${i}`}><td>{DAY_NAMES[day.dow] ?? day.dow}</td><td>{KIND_LABEL[s.kind]}</td><td className="num">{fmt(s.from)}</td><td className="num">{fmt(s.to)}</td><td>{s.attendees ? BUCKET[s.attendees] : ""}</td></tr>
        )))}</tbody>
      </table></div>
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
function GapTable({ rows, meta, note }: { rows: GapRow[]; meta: ReturnType<typeof useLoad<CalendarWeek>>["meta"]; note?: string }) {
  const [all, setAll] = useState(false);
  const sorted = sortGaps(rows);
  const shown = all ? sorted : sorted.slice(0, SHOWN);
  const clear = rows.filter(gapClear).length;
  return (
    <section className="section" aria-labelledby="gap-h">
      <div className="section__head">
        <h2 className="section__title" id="gap-h">Where your week differs</h2>
        <p className="section__sub">Your number, the expert's, and the gap.</p>
      </div>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>What</th><th className="num">You</th><th className="num">Expert</th><th className="num">Difference</th><th>95% interval</th><th className="hide-narrow" aria-hidden="true" /><th className="hide-narrow">Experts range from</th><th className="hide-narrow">Read</th></tr></thead>
        <tbody>{shown.map((r) => (
          <tr key={r.feature}>
            <td>{featureLabel(r.feature)}</td>
            <td className="num">{fmtFeature(r.feature, r.learner)}</td>
            <td className="num">{fmtFeature(r.feature, r.expert)}</td>
            <td className="num"><b>{fmtFeature(r.feature, r.delta, true)}</b></td>
            <td className="num interval">{fmtInterval(r.ci, featureUnit(r.feature) === "share" ? 2 : Math.abs(r.delta) < 10 ? 1 : 0)}</td>
            <td className="hide-narrow"><DeltaBar delta={r.delta} ci={r.ci} /></td>
            <td className="hide-narrow num interval">{r.expert_range ? `${fmtFeature(r.feature, r.expert_range[0])} to ${fmtFeature(r.feature, r.expert_range[1])}` : ""}</td>
            <td className="hide-narrow">{gapClear(r) ? <span className="pill"><b>clear</b></span> : <span className="pill">within noise</span>}</td>
          </tr>))}</tbody>
      </table></div>
      {rows.length > SHOWN && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button></div>}
      <ChartFoot variant="about" brief meta={meta} extra={<span>{clear} of {rows.length} differences are clear: their 95% interval stays on one side of zero. The interval covers the spread among the expert references only{note ? ` (${note})` : ""}.</span>} />
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
        <p className="section__sub">Chosen by code from a fixed list and worded from your numbers. None is acted on.</p>
      </div>
      {list.length === 0 ? <EmptyState title="Nothing to suggest" body="Your week is close to the expert's, so there is nothing worth changing right now." /> : (
        <div className="sug-grid">
          {list.map((s) => {
            const [first, rest] = splitSentence(s.text);
            return (
              <article key={s.id} className="card card__pad sug" aria-label={s.title ?? s.text}>
                {s.title && <h3 className="sug__title">{s.title}</h3>}
                <p className="sug__text">{first}</p>
                <Details summary="How this was worked out">
                  <div className="stack" style={{ gap: "var(--space-2)" }}>
                    {rest && <p className="note">{rest}</p>}
                    <dl className="sug__nums">
                      {Object.keys(s.numbers).map((k) => (
                        <div key={k}><dt>{featureLabel(k)}</dt><dd><b className="tabular">{val(k, s.numbers[k])}</b><span className="u-muted"> you</span> · <span className="tabular">{s.expert_ref[`${k}_reference`] != null ? val(k, s.expert_ref[`${k}_reference`]) : s.expert_ref[k] != null ? val(k, s.expert_ref[k]) : "not given"}</span><span className="u-muted"> expert</span></dd></div>
                      ))}
                    </dl>
                    <p className="note">{s.can_draft ? "A draft can be prepared." : "No draft is available for this one."}{s.evidence_weeks ? ` Seen over ${s.evidence_weeks} weeks.` : ""}</p>
                  </div>
                </Details>
                {s.risk !== "low" && <div className="row"><span className="pill">{s.risk}</span></div>}
                <p className="note">Nothing is sent, booked or changed.</p>
              </article>
            );
          })}
        </div>
      )}
      <ChartFoot variant="about" brief meta={state.meta} />
    </section>
  );
}
