import { Details, MetricRow, Metrics } from "../ui";
import { nWord } from "./Badges";
import { coverageShare, pct } from "./model";
import type { WireOverview } from "./wire";
import type { AnalyticMeta } from "../../types";

const STATUS: Record<string, string> = { ok: "Enough data", onboarding: "Just started", stale: "Not seen lately", no_data: "No data yet" };

/** Risk and coverage, printed (an admin screen keeps every figure's detail visible): how long approvals wait, what stopped a run, and how many people the numbers describe. */
export function RiskCoverage({ o }: { o: WireOverview; meta?: AnalyticMeta | null }) {
  const r = o.risk;
  const c = o.coverage;
  return (
    <div className="risk">
      <Metrics label="Risk and coverage">
        {r?.approval_backlog_age_h && <MetricRow audience="admin" label="Oldest approval still waiting" value={Math.round(r.approval_backlog_age_h.max)} unit="hours" detail={`Across ${nWord(r.open_approvals, "approvals")} open now. An approval is never given by waiting.`} />}
        {r?.approval_backlog_age_h && <MetricRow audience="admin" label="Typical wait for an approval" value={Math.round(r.approval_backlog_age_h.median)} unit="hours" detail="The median across the approvals open now." />}
        {r && <MetricRow audience="admin" label="Approvals open now" value={r.open_approvals} unit={r.open_approvals === 1 ? "approval" : "approvals"} detail="Irreversible steps wait for a person. Nothing runs unattended without it." />}
        {r && <MetricRow audience="admin" label="Runs paused by an injected page" value={r.injection_pauses_30d} unit="in 30 days" tone={r.injection_pauses_30d > 0 ? "bad" : undefined} detail="A page tried to give an agent instructions. The run paused and changed nothing." />}
        {r && <MetricRow audience="admin" label="Times everything was stopped" value={r.kill_events_30d} unit="in 30 days" detail="Presses of the Stop everything switch, anywhere in the firm." />}
        <MetricRow audience="admin" label="People with enough data for a trend" value={`${c.enough_data} of ${c.users}`} unit="people" detail={`${pct(coverageShare(c))} of the firm. A trend needs at least ${c.min_occurrences} counted steps.`} />
      </Metrics>
      {!r && <p className="risk__none">No risk figures were sent. Approvals, pauses and stops appear here once the engine reports them.</p>}
      <Details summary="Coverage by role">
        <table className="table risk__table">
          <thead><tr><th scope="col">Role</th><th scope="col" className="num">People</th><th scope="col" className="num">With enough data</th></tr></thead>
          <tbody>{c.roles.map((x) => <tr key={x.role}><th scope="row">{x.name}</th><td className="num">{x.users}</td><td className="num">{x.enough_data}</td></tr>)}</tbody>
        </table>
        {Object.keys(c.by_status).length > 0 && (
          <p className="risk__status">{Object.entries(c.by_status).map(([k, v]) => `${STATUS[k] ?? k}: ${v}`).join(". ")}.</p>
        )}
      </Details>
    </div>
  );
}
