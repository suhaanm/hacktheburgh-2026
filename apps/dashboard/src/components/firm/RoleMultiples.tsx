import { useState } from "react";
import { Details, Row, Rows } from "../ui";
import { Range } from "../common";
import { Hint } from "../Hint";
import { IntervalPlot, SHARE_AXIS, type PlotRow } from "./IntervalPlot";
import { compareShown, fmtNum, fmtShare, pct, roleGapLine, verdictText } from "./model";
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
              {h.verdict !== "gap" ? <span className="rolecard__verdict" data-verdict={h.verdict}>{verdictText(h.verdict)}</span> : <span />}
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

/** The row's muted line, printed (D45: n and the interval stay on Admin screens): both estimates with their intervals and each group's n. */
function roleLine(r: RoleCompare, ind: RoleMeasure): string {
  return `Experts ${fmtShare(ind.expert)}, n = ${r.n_expert}. Juniors ${fmtShare(ind.junior)}, n = ${r.n_junior}.`;
}

/** The gap in points, as the row's end: a number with its word, never a bare colour. "not clear" when the interval does not say. */
function gapEnd(ind: RoleMeasure): string {
  const g = ind.gap;
  if (!g) return "no gap figure";
  const pts = Math.abs(Math.round(g.value * 100));
  return ind.verdict === "gap" ? `gap ${pts} points` : `gap not clear`;
}

/** What a role opens to, in place: the comparison on one 0 to 100% scale, the gap in words with its verdict, the habits behind it, and the way to the people. */
function RoleOpen({ r, min }: { r: RoleCompare; min: number }) {
  const ind = measureOf(r, "independence");
  const time = measureOf(r, "time_vs_expert");
  if (!ind) return null;
  const rows: PlotRow[] = [
    { id: "expert", label: `Experts (${r.n_expert})`, est: ind.expert, tone: "expert" },
    { id: "junior", label: `Juniors (${r.n_junior})`, est: ind.junior, tone: "novice" },
  ];
  return (
    <li className="role-open">
      <IntervalPlot title={`${ind.label}, ${r.name}`} rows={rows} domain={SHARE_AXIS.domain} ticks={SHARE_AXIS.ticks} format={pct} />
      <p className="rolecard__gap">
        {roleGapLine(ind, time)} {ind.verdict !== "gap" && <span className="rolecard__verdict" data-verdict={ind.verdict}>{verdictText(ind.verdict)}</span>}
      </p>
      <Habits role={r} min={min} />
      <Details summary="About this comparison">
        <p>{r.n_expert} experts and {r.n_junior} juniors, each person counted once. Every role uses the same 0 to 100% scale. Intervals are 95% intervals from resampling people. {r.standard ?? ""}</p>
      </Details>
      <a className="btn btn--quiet btn--sm" href="#/firm/people">People in {r.name}</a>
    </li>
  );
}

/**
 * Experts against juniors, one row per role on one shared 0 to 100% scale (KNACK_UX, 05-admin-firm.md). A row is the whole target: it opens the comparison,
 * the habits that explain the gap and the people in place. A role under the minimum is a plain row that says why it is not compared. No pill per row.
 */
export function RoleMultiples({ roles, min }: { roles: RoleCompare[]; min: number; meta?: AnalyticMeta | null }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Rows label="Roles">
      {roles.flatMap((r) => {
        const ind = measureOf(r, "independence");
        if (!compareShown(r, min) || !ind) {
          return [<Row key={r.role} title={r.name} meta={`Not compared yet. ${(r.reason && REASON[r.reason]) || `Needs at least ${min} experts and ${min} juniors with enough data. This role has ${r.n_expert} and ${r.n_junior}.`}`} />];
        }
        const on = open === r.role;
        const row = <Row key={r.role} title={r.name} meta={roleLine(r, ind)} end={gapEnd(ind)} onClick={() => setOpen(on ? null : r.role)} pressed={on} chevron={!on} />;
        return on ? [row, <RoleOpen key={`${r.role}-open`} r={r} min={min} />] : [row];
      })}
    </Rows>
  );
}
