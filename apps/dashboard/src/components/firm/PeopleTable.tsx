import { Fragment, useMemo, useState } from "react";
import { Range } from "../common";
import { Hint } from "../Hint";
import { FirmBadge } from "./Badges";
import {
  DEFAULT_SORT, SORT_KEYS, TENURE_LABEL, TREND_GLYPH, TREND_HINT, TREND_LABEL, filterUsers, fmtNum, fmtShare, groupShown, pct, sortUsers, trendCounts, unitWord,
  type SortKey,
} from "./model";
import type { AnalyticMeta } from "../../types";
import type { FirmRole, Trend, UserRow, WireFirm } from "./wire";
import { TRENDS } from "./wire";

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

function Skills({ u }: { u: UserRow }) {
  if (u.skills.length === 0) return <p className="firm-skills__none">No per-skill figures yet.</p>;
  return (
    <ul className="firm-skills">
      {u.skills.map((k) => (
        <li key={k.skill}>
          <span className="firm-skills__label">{k.label}</span>
          <span className="firm-skills__nums">
            {k.independence_share === null ? "not enough data" : `${pct(k.independence_share)} finished without help`} of {k.n} steps
            {k.lost_s ? `; ${fmtNum(k.lost_s, "s")} ${k.lost_s.value >= 0 ? "longer" : "shorter"} than the expert's median` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Row({ u, open, onToggle, cols }: { u: UserRow; open: boolean; onToggle: () => void; cols: number }) {
  const t = u.time_to_independence;
  const ind = u.independence;
  return (
    <Fragment>
      <tr data-status={u.status ?? "ok"}>
        <th scope="row" className="firm-person">
          <button type="button" className="firm-person__btn" aria-expanded={open} onClick={onToggle}>
            <span className="firm-person__chev" aria-hidden="true" data-open={open} />
            <span>{u.label}</span>
          </button>
          <span className="firm-person__tenure">{TENURE_LABEL[u.tenure_band]}</span>
          {u.status && u.status !== "ok" && <span className="firm-person__status">{STATUS_WORD[u.status] ?? u.status}</span>}
        </th>
        <td className="col-wide">{TENURE_LABEL[u.tenure_band]}</td>
        <td><TrendMark t={u.trend} /></td>
        <td className="num firm-ind">
          {ind ? (<>
            <span>{pct(ind.value)}</span>
            {ind.ci && <Range lo={ind.ci[0]} hi={ind.ci[1]} pt={ind.value} min={0} max={1} />}
            <span className="firm-ind__ci">{ind.ci ? `${pct(ind.ci[0])} to ${pct(ind.ci[1])}` : "no interval yet"}</span>
          </>) : "not enough data"}
        </td>
        <td className="num col-opt">{t.reached && t.value !== null ? `${Math.round(t.value)} ${unitWord(t.unit)}` : "not yet"}</td>
        <td className="num col-opt">{u.assisted_share ? pct(u.assisted_share.value) : "n/a"}</td>
        <td className="num col-opt">{u.automations_running}</td>
      </tr>
      {open && (
        <tr className="firm-expand"><td colSpan={cols}><Skills u={u} /></td></tr>
      )}
    </Fragment>
  );
}

/** The aggregate band above a role: one group figure per line, with its interval printed. Hidden when the group is under the minimum. */
function Band({ r, min }: { r: FirmRole; min: number }) {
  const a = r.aggregate;
  if (!groupShown(r, min)) {
    return <p className="firm-band firm-band--none">Fewer than {min} people with data in this group, so no group figure is shown. People are still listed below.</p>;
  }
  const t = a.time_to_independence;
  return (
    <dl className="firm-band">
      <div><dt>Finished without help</dt><dd>{fmtShare(a.independence)}</dd></div>
      <div><dt>Needed help</dt><dd>{fmtShare(a.assisted_share)}</dd></div>
      <div><dt>Steps until independent</dt><dd>{t.median !== null ? fmtNum({ value: t.median, ci: t.ci }, unitWord(t.unit)) : "not reached yet"}</dd></div>
      {t.reached_share && <div><dt>Reached it so far</dt><dd>{fmtShare(t.reached_share)}</dd></div>}
      {r.trend && (
        <div>
          <dt>Role trend</dt>
          <dd><TrendMark t={r.trend.cls} />{r.trend.slope_per_4w ? <span className="firm-band__slope"> {fmtNum({ value: r.trend.slope_per_4w.value * 100, ci: r.trend.slope_per_4w.ci ? [r.trend.slope_per_4w.ci[0] * 100, r.trend.slope_per_4w.ci[1] * 100] : null }, "points / 4 weeks")}</span> : null}</dd>
        </div>
      )}
    </dl>
  );
}

function RoleSection({ r, firm, sort, filter, meta }: { r: FirmRole; firm: WireFirm; sort: SortKey; filter: Trend | null; meta: AnalyticMeta | null }) {
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const min = firm.privacy.min_group;
  const rows = useMemo(() => sortUsers(filterUsers(r.users, filter), sort), [r.users, filter, sort]);
  const shown = all ? rows : rows.slice(0, 7);
  const cols = 7;
  return (
    <section className="firm-role" aria-labelledby={`people-${r.role}`}>
      <header className="firm-role__head">
        <h3 id={`people-${r.role}`} className="firm-role__name">{r.name}</h3>
        <span className="firm-role__count">{r.users.length} {r.users.length === 1 ? "person" : "people"}</span>
        <Hint label="About group figures">
          Group figures need at least {min} people. Smaller groups are merged, so a figure never describes two or three individuals. {firm.privacy.note ?? ""}
        </Hint>
        <FirmBadge meta={meta} />
      </header>
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
                <th scope="col" className="col-wide">Time in role</th>
                <th scope="col">Help needed over time</th>
                <th scope="col" className="num">Finished without help</th>
                <th scope="col" className="num col-opt">Steps until independent</th>
                <th scope="col" className="num col-opt">Needed help</th>
                <th scope="col" className="num col-opt">Routines running</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => <Row key={u.id} u={u} open={open === u.id} onToggle={() => setOpen(open === u.id ? null : u.id)} cols={cols} />)}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 7 && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>}
    </section>
  );
}

/**
 * Everyone in the firm, grouped by role. There is no single score and no league table: the only orders are by name and by time in role, and the
 * only filter is a class of trend. For coaching and onboarding, not for evaluating individuals.
 */
export function PeopleTable({ firm, meta }: { firm: WireFirm; meta: AnalyticMeta | null }) {
  const [sort, setSort] = useState<SortKey>(DEFAULT_SORT);
  const [filter, setFilter] = useState<Trend | null>(null);
  const all = useMemo(() => firm.roles.flatMap((r) => r.users), [firm]);
  const counts = useMemo(() => trendCounts(all), [all]);
  return (
    <div className="firm-people">
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
      {firm.roles.map((r) => <RoleSection key={r.role} r={r} firm={firm} sort={sort} filter={filter} meta={meta} />)}
    </div>
  );
}
