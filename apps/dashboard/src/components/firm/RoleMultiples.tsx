import { useState } from "react";
import { Details } from "../ui";
import { Range } from "../common";
import { Hint } from "../Hint";
import { FirmBadge } from "./Badges";
import { IntervalPlot, SHARE_AXIS, type PlotRow } from "./IntervalPlot";
import { compareShown, fmtNum, pct, roleGapLine, verdictText } from "./model";
import type { RoleCompare, RoleHabit, RoleMeasure } from "./wire";
import type { AnalyticMeta } from "../../types";

const REASON: Record<string, string> = {
  no_expert_reference: "There is no expert in this role to compare with yet.",
  group_too_small: "Fewer than 5 people in a group, so no comparison is shown.",
};

const measureOf = (r: RoleCompare, key: string): RoleMeasure | undefined => r.measures.find((m) => m.key === key);

/** Habits are plotted in seconds per case, on one axis for the whole role so their sizes can be compared by eye. */
function habitDomain(hs: RoleHabit[]): { domain: [number, number]; ticks: number[] } {
  const hi = Math.max(1, ...hs.flatMap((h) => (h.explains_s ? [h.explains_s.value, h.explains_s.ci?.[1] ?? 0] : [0])));
  const top = Math.ceil(hi / 5) * 5;
  return { domain: [0, top], ticks: [0, top / 2, top] };
}

function Habits({ role, min }: { role: RoleCompare; min: number }) {
  const [all, setAll] = useState(false);
  const hs = role.habits;
  if (!compareShown(role, min) || hs.length === 0) return null;
  const sorted = [...hs].sort((a, b) => (b.explains_s?.value ?? 0) - (a.explains_s?.value ?? 0));
  const shown = all ? sorted : sorted.slice(0, 3);
  const { domain } = habitDomain(sorted);
  return (
    <div className="rolecard__habits">
      <h4 className="t-label">
        Habits that explain the gap
        <Hint label="About these habits">Seconds per case that this habit adds for juniors beyond the experts, with the experts' mix of skills held fixed. {role.standard ?? ""}</Hint>
      </h4>
      <ul className="rolecard__habitlist">
        {shown.map((h) => {
          const e = h.explains_s;
          return (
            <li key={h.id}>
              <span className="rolecard__habit">{h.label}</span>
              <span className="rolecard__verdict" data-verdict={h.verdict}>{verdictText(h.verdict)}</span>
              {e && e.ci ? <Range lo={e.ci[0]} hi={e.ci[1]} pt={e.value} min={domain[0]} max={domain[1]} /> : <span className="rolecard__noint">no interval yet</span>}
              <span className="rolecard__rates">
                {e ? `Adds ${fmtNum(e, "s")} per case.` : "No figure yet."} Experts needed help {h.expert_rate ? pct(h.expert_rate.value) : "n/a"} of the time, juniors {h.junior_rate ? pct(h.junior_rate.value) : "n/a"}.
              </span>
            </li>
          );
        })}
      </ul>
      <p className="rolecard__scale">Bars share one scale: 0 to {domain[1]} s per case.</p>
      {sorted.length > 3 && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${sorted.length}`}</button>}
    </div>
  );
}

/** One role as a small multiple: experts and juniors on a share axis that is 0 to 100% in every role, then the gap in plain words, then the habits. */
function RoleCard({ r, min, meta }: { r: RoleCompare; min: number; meta: AnalyticMeta | null }) {
  const ind = measureOf(r, "independence");
  const time = measureOf(r, "time_vs_expert");
  const shown = compareShown(r, min);
  const rows: PlotRow[] = shown && ind ? [
    { id: "expert", label: `Experts (${r.n_expert})`, est: ind.expert, tone: "expert" },
    { id: "junior", label: `Juniors (${r.n_junior})`, est: ind.junior, tone: "novice" },
  ] : [];
  return (
    <article className="rolecard" aria-labelledby={`role-${r.role}`}>
      <header className="rolecard__head">
        <h3 id={`role-${r.role}`} className="rolecard__name">{r.name}</h3>
        <FirmBadge meta={meta} />
      </header>
      {shown && ind ? (
        <>
          <p className="rolecard__lede">{ind.label}: experts and juniors on one scale.</p>
          <IntervalPlot title={`${ind.label}, ${r.name}`} rows={rows} domain={SHARE_AXIS.domain} ticks={SHARE_AXIS.ticks} format={pct} />
          <p className="rolecard__gap">
            {roleGapLine(ind, time)} <span className="rolecard__verdict" data-verdict={ind.verdict}>{verdictText(ind.verdict)}</span>
          </p>
          <Habits role={r} min={min} />
        </>
      ) : (
        <div className="state state--inline" role="status">
          <span className="state__mark" aria-hidden="true" />
          <p className="state__title">Not compared yet</p>
          <p className="state__body">{(r.reason && REASON[r.reason]) || `Needs at least ${min} experts and ${min} juniors with enough data. This role has ${r.n_expert} and ${r.n_junior}.`}</p>
        </div>
      )}
      {shown && r.n_expert + r.n_junior > 0 && (
        <Details summary="About this comparison">
          <p>{r.n_expert} experts and {r.n_junior} juniors, each person counted once. Intervals are 95% intervals from resampling people. {r.standard ?? ""}</p>
        </Details>
      )}
    </article>
  );
}

/** Experts against juniors for every role, as small multiples that share one scale. Groups under the minimum are not drawn. */
export function RoleMultiples({ roles, min, meta }: { roles: RoleCompare[]; min: number; meta: AnalyticMeta | null }) {
  return (
    <div className="rolewrap">
      <ul className="legend" aria-label="How to read the charts">
        <li className="legend__item"><i className="sw sw--dot sw--expert" />Experts</li>
        <li className="legend__item"><i className="sw sw--novice" style={{ width: 9, height: 9 }} />Juniors</li>
        <li className="legend__item"><i className="sw sw--line sw--muted" />95% interval</li>
        <li className="legend__item">Every role uses the same 0 to 100% scale</li>
      </ul>
      <div className="rolegrid">
        {roles.map((r) => <RoleCard key={r.role} r={r} min={min} meta={meta} />)}
      </div>
    </div>
  );
}
