import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Range } from "../common";
import { Hint } from "../Hint";
import { Details, FactRows } from "../ui";
import { Headline, SeeNumbers } from "./InsightFirst";
import { MixBar } from "./MixBar";
import { peopleHeadline } from "./insights";
import {
  DEFAULT_SORT, SORT_KEYS, personName, TENURE_LABEL, TREND_GLYPH, TREND_HINT, TREND_LABEL, filterUsers, fmtNum, fmtShare, groupShown, pct, sortUsers, trendCounts, unitWord,
  type SortKey,
} from "./model";
import type { AnalyticMeta } from "../../types";
import type { FirmRole, Trend, UserRow, WireFirm } from "./wire";
import { TRENDS } from "./wire";
import { shortName } from "./insights";

const SORT_LABEL: Record<SortKey, string> = { name: "Name", tenure: "Time in role" };
const STATUS_WORD: Record<string, string> = { onboarding: "just started", stale: "not seen lately", no_data: "no data yet" };

/** The class of a person's trend, as a glyph and words. Only "needs attention" is drawn as a pill: the one non-default state in a row. */
function TrendMark({ t }: { t: Trend }) {
  return (
    <span className={t === "needs_attention" ? "pill firm-trend" : "firm-trend"} data-trend={t}>
      <span className="firm-trend__glyph" aria-hidden="true">{TREND_GLYPH[t]}</span>{TREND_LABEL[t]}
    </span>
  );
}

/** One person's detail, opened in place: label : value rows for the figures that are not in the table, then the per-skill lines. */
function Skills({ u }: { u: UserRow }) {
  const t = u.time_to_independence;
  const rows: [string, string][] = [
    ["Steps until independent", t.reached && t.value !== null ? `${Math.round(t.value)} ${unitWord(t.unit)}` : "not yet"],
    ["Needed help", u.assisted_share ? pct(u.assisted_share.value) : "n/a"],
    ["Routines running", String(u.automations_running)],
  ];
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <FactRows rows={rows} />
      {u.skills.length === 0 ? <p className="firm-skills__none">No per-skill figures yet.</p> : (
        <ul className="firm-skills">
          {u.skills.map((k) => (
            <li key={k.skill}>
              <span className="firm-skills__label">{k.label}</span>
              <span className="firm-skills__nums">
                {k.independence_share === null ? "not enough data" : `${pct(k.independence_share)} without help`} of {k.n} steps
                {k.lost_s ? `; ${fmtNum(k.lost_s, "s")} ${k.lost_s.value >= 0 ? "longer" : "shorter"} than the expert's median` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({ u, open, onToggle, cols }: { u: UserRow; open: boolean; onToggle: () => void; cols: number }) {
  const ind = u.independence;
  return (
    <Fragment>
      <tr data-status={u.status ?? "ok"}>
        <th scope="row" className="firm-person">
          <button type="button" className="firm-person__btn" aria-expanded={open} aria-controls={`skills-${u.label}`} data-person={u.label} onClick={onToggle}>
            <span className="firm-person__chev" aria-hidden="true" data-open={open} />
            <span className="firm-person__name">{personName(u)}</span>
          </button>
          <span className="firm-person__tenure">{TENURE_LABEL[u.tenure_band]}{u.status && u.status !== "ok" ? `, ${STATUS_WORD[u.status] ?? u.status}` : ""}</span>
        </th>
        <td><TrendMark t={u.trend} /></td>
        <td className="num firm-ind">
          {ind ? (<>
            <span>{pct(ind.value)}</span>
            {ind.ci && <Range lo={ind.ci[0]} hi={ind.ci[1]} pt={ind.value} min={0} max={1} />}
            <span className="firm-ind__ci">{ind.ci ? `${pct(ind.ci[0])} to ${pct(ind.ci[1])}` : "no interval yet"}</span>
          </>) : "not enough data"}
        </td>
      </tr>
      {open && (
        <tr className="firm-expand" id={`skills-${u.label}`}><td colSpan={cols}><Skills u={u} /></td></tr>
      )}
    </Fragment>
  );
}

/** The group figures above a role: the two that matter as label : value rows, the rest behind one closed More. Hidden when the group is under the minimum. */
function Band({ r, min }: { r: FirmRole; min: number }) {
  const a = r.aggregate;
  if (!groupShown(r, min)) {
    return <p className="firm-band firm-band--none">Fewer than {min} people with data in this group, so no group figure is shown. People are still listed below.</p>;
  }
  const t = a.time_to_independence;
  const main: [string, ReactNode][] = [["Finished without help", fmtShare(a.independence)]];
  if (r.trend) {
    main.push(["Role trend", <><TrendMark t={r.trend.cls} />{r.trend.slope_per_4w ? <span className="firm-band__slope"> {fmtNum({ value: r.trend.slope_per_4w.value * 100, ci: r.trend.slope_per_4w.ci ? [r.trend.slope_per_4w.ci[0] * 100, r.trend.slope_per_4w.ci[1] * 100] : null }, "points a month")}</span> : null}</>]);
  }
  const more: [string, ReactNode][] = [
    ["Needed help", fmtShare(a.assisted_share)],
    ["Steps until independent", t.median !== null ? fmtNum({ value: t.median, ci: t.ci }, unitWord(t.unit)) : "not reached yet"],
  ];
  if (t.reached_share) more.push(["Reached it so far", fmtShare(t.reached_share)]);
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <FactRows rows={main} />
      <Details summary="More"><FactRows rows={more} /></Details>
    </div>
  );
}

function RoleSection({ r, firm, sort, filter }: { r: FirmRole; firm: WireFirm; sort: SortKey; filter: Trend | null }) {
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const min = firm.privacy.min_group;
  const rows = useMemo(() => sortUsers(filterUsers(r.users, filter), sort), [r.users, filter, sort]);
  const shown = all ? rows : rows.slice(0, 2);
  const cols = 3;
  return (
    <Details summary={`${shortName(r.name)}, ${r.users.length} ${r.users.length === 1 ? "person" : "people"}`} wide className="firm-role-details">
      <section className="firm-role" aria-labelledby={`people-${r.role}`}>
        <h3 id={`people-${r.role}`} className="u-sr-only">{r.name}</h3>
        <Band r={r} min={min} />
        {rows.length === 0 ? (
          <p className="firm-role__empty">No one in this group matches that filter.</p>
        ) : (
          <div className="table-wrap">
            <table className="table firm-table">
              <caption className="u-sr-only">{r.name}, sorted by {SORT_LABEL[sort].toLowerCase()}. Not ranked.</caption>
              <thead>
                <tr>
                  <th scope="col">Person</th>
                  <th scope="col">Help needed over time</th>
                  <th scope="col" className="num">Finished without help</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((u) => <Row key={u.id} u={u} open={open === u.id} onToggle={() => setOpen(open === u.id ? null : u.id)} cols={cols} />)}
              </tbody>
            </table>
          </div>
        )}
        {rows.length > 2 && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>}
      </section>
    </Details>
  );
}

/**
 * Everyone in the firm, grouped by role. There is no single score and no league table: the only orders are by name and by time in role, and the
 * only filter is a class of trend. For coaching and onboarding, not for evaluating individuals.
 */
export function PeopleTable({ firm }: { firm: WireFirm; meta?: AnalyticMeta | null }) {
  const [sort, setSort] = useState<SortKey>(DEFAULT_SORT);
  const [filter, setFilter] = useState<Trend | null>(null);
  const all = useMemo(() => firm.roles.flatMap((r) => r.users), [firm]);
  const counts = useMemo(() => trendCounts(all), [all]);
  return (
    <div className="firm-people">
      <Details summary="Sort and filter" wide>
        <div className="firm-people__bar">
          <div className="firm-people__sort" role="group" aria-label="Sort people by">
            <span className="firm-people__label">Sorted by</span>
            <span className="segmented">
              {SORT_KEYS.map((k) => <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)}>{SORT_LABEL[k]}</button>)}
            </span>
          </div>
          <label className="firm-people__filter">
            <span className="firm-people__label">Show</span>
            <select className="select" value={filter ?? ""} onChange={(e) => setFilter((e.target.value || null) as Trend | null)}>
              <option value="">Everyone ({all.length})</option>
              {TRENDS.map((t) => <option key={t} value={t}>{TREND_LABEL[t]} ({counts[t]})</option>)}
            </select>
          </label>
          <Hint label="About the trend classes">
            {filter ? TREND_HINT[filter] : "Each person has a class for how the help they need is changing. A class is a conversation starter for coaching, never a grade, and the list is never ranked."}
          </Hint>
        </div>
        <p className="note">Group figures need at least {firm.privacy.min_group} people. Smaller groups are merged, so a figure never describes two or three individuals. {firm.privacy.note ?? ""}</p>
      </Details>
      {firm.roles.map((r) => <RoleSection key={r.role} r={r} firm={firm} sort={sort} filter={filter} />)}
    </div>
  );
}

/**
 * The People screen, insight first: one sentence on who needs less help and who could use a conversation, one bar of how the trend classes split, and
 * the people, grouped by role, behind "See the numbers". The bar and the sentence count people; the list never ranks them.
 */
export function PeopleBody({ firm, meta }: { firm: WireFirm; meta?: AnalyticMeta | null }) {
  const all = useMemo(() => firm.roles.flatMap((r) => r.users), [firm]);
  const c = useMemo(() => trendCounts(all), [all]);
  return (
    <div className="insight-first">
      <Headline>{peopleHeadline(firm)}</Headline>
      {all.length > 0 && <MixBar title="How the help people need is changing" total={all.length} parts={TRENDS.map((t) => ({ id: t, label: TREND_LABEL[t], count: c[t] }))} />}
      {firm.roles.filter((r) => r.users.length > 0).length > 0 && (
        <p className="note" data-testid="people-groups">
          Groups: {firm.roles.filter((r) => r.users.length > 0).slice(0, 4).map((r) => `${shortName(r.name)} ${r.users.length.toLocaleString("en-GB")}`).join(", ")}
          {firm.roles.filter((r) => r.users.length > 0).length > 4 ? `, and ${firm.roles.filter((r) => r.users.length > 0).length - 4} more` : ""}.
        </p>
      )}
      {all.length > 0 && <SeeNumbers><PeopleTable firm={firm} meta={meta} /></SeeNumbers>}
    </div>
  );
}
