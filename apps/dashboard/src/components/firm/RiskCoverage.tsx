import type { ReactNode } from "react";
import { Details, FactRows } from "../ui";
import { Headline, NumbersTable, SeeNumbers } from "./InsightFirst";
import { riskHeadline, shortName } from "./insights";
import { coverageShare, pct } from "./model";
import type { WireOverview } from "./wire";
import type { AnalyticMeta } from "../../types";

const STATUS: Record<string, string> = { ok: "Enough data", onboarding: "Just started", stale: "Not seen lately", no_data: "No data yet" };
const fin = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/**
 * Risk and coverage, insight first: one sentence on what is waiting and what stopped, the figures as label : value rows, and the coverage by role and
 * what each figure means behind "See the numbers". Every figure is a count or an hour, printed.
 */
export function RiskCoverage({ o }: { o: WireOverview; meta?: AnalyticMeta | null }) {
  const r = o.risk;
  const c = o.coverage;
  const rows: [string, ReactNode][] = [];
  if (r) {
    rows.push(["Approvals open now", String(r.open_approvals)]);
    if (r.approval_backlog_age_h && fin(r.approval_backlog_age_h.max)) rows.push(["Oldest still waiting", `${Math.round(r.approval_backlog_age_h.max)} hours`]);
    rows.push(["Runs paused after a page tried to instruct them", `${r.injection_pauses_30d}\u00a0in\u00a030\u00a0days`]);
    rows.push(["Times everything was stopped", `${r.kill_events_30d}\u00a0in\u00a030\u00a0days`]);
  }
  rows.push(["People with enough data", `${c.enough_data} of ${c.users}`]);
  const byRole = c.roles.map((x) => [shortName(x.name), String(x.users), String(x.enough_data)]);
  return (
    <div className="insight-first risk">
      <Headline>{riskHeadline(o)}</Headline>
      <FactRows rows={rows} className="about__list risk__facts" />
      {!r && <p className="risk__none">Approvals, pauses and stops appear here once the engine reports them.</p>}
      <SeeNumbers>
        <div className="stack">
          {r?.approval_backlog_age_h && fin(r.approval_backlog_age_h.median) && <FactRows rows={[["Typical wait", `${Math.round(r.approval_backlog_age_h.median)} hours`]]} />}
          <p className="note">{pct(coverageShare(c))} of the firm has enough data. A trend needs at least {c.min_occurrences} counted steps. Irreversible steps wait for a person.</p>
          <NumbersTable heads={["Role", "People", "With enough data"]} rows={byRole} caption="Coverage by role" />
          {Object.keys(c.by_status).length > 0 && (
            <Details summary="By status"><p className="risk__status">{Object.entries(c.by_status).map(([k, v]) => `${STATUS[k] ?? k}: ${v}`).join(". ")}.</p></Details>
          )}
        </div>
      </SeeNumbers>
    </div>
  );
}
