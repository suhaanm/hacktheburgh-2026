import { useEffect, useMemo, useState } from "react";
import { useRoute } from "../../router";
import { useLoad, type LoadState } from "../../hooks";
import { ErrorState, Loading, SourceNote } from "../../components/common";
import { Breadcrumb } from "../../components/Breadcrumb";
import { Details } from "../../components/ui";
import { HitList } from "../../components/repeats/HitList";
import { SYNTHETIC_NOTE } from "../../components/firm/Badges";
import { FirmBrief } from "../../components/firm/FirmBrief";
import { InsightRows } from "../../components/firm/InsightRows";
import { OnboardingCurves } from "../../components/firm/OnboardingCurves";
import { PeopleTable } from "../../components/firm/PeopleTable";
import { RiskCoverage } from "../../components/firm/RiskCoverage";
import { RoleMultiples } from "../../components/firm/RoleMultiples";
import { ScorecardPanel } from "../../components/firm/ScorecardPanel";
import { fmtNum } from "../../components/firm/model";
import { firmTabOf, type FirmTab } from "../../components/home/navModel";
import { ADMIN_MARKER } from "../../components/home/viewAs";
import { loadFirm as loadFirmHits } from "../Repeats/data";
import { loadFirm, loadOnboarding, loadOverview, loadRoles } from "./data";
import "../../components/firm/firm.css";

/** A title is a name, six words at most. The other five views are rows in More and in the palette; the tab strip is retired. */
const TITLE: Record<FirmTab, string> = {
  overview: "Firm",
  roles: "Roles",
  people: "People",
  onboarding: "Onboarding",
  automation: "Automation",
  risk: "Risk and coverage",
  forecasts: "Forecasts",
  brief: "Firm brief",
};
/** The one printed line under every Firm title: a use limit, so it is never behind a Hint. */
export const FIRM_LIMIT = "For coaching and onboarding, not for evaluating individuals.";
const MIN_GROUP = 5;

/** Wraps a loaded panel: loading, error and the example note are designed, never blank. The one origin pill is in the screen head, not on each panel. */
function Panel<T>({ q, what, children }: { q: LoadState<T>; what: string; children: (d: T) => React.ReactNode }) {
  if (q.status === "error" && !q.data) return <ErrorState error={q.error} retry={q.reload} what={what} />;
  if (!q.data) return <Loading label={`Loading ${what}`} />;
  return (
    <section className="firm-panel" aria-busy={q.status === "loading"}>
      {children(q.data)}
      <SourceNote why={q.why} />
    </section>
  );
}

function Overview({ openId }: { openId: string | null }) {
  const q = useLoad(loadOverview, []);
  return (
    <Panel q={q} what="the overview">
      {(o) => (
        <>
          <p className="firm-summary">{o.firm.users} people, {o.firm.roles} roles. {o.coverage.enough_data} have enough data for a trend.</p>
          {o.top.length > 0 ? <InsightRows items={o.top} openId={openId} /> : (
            <div className="state"><h2 className="state__title">Nothing stands out this week</h2><p className="state__body">No insight passed every check. That is a normal result.</p></div>
          )}
          <p className="firm-links"><a href="#/firm/brief">Print the firm brief</a></p>
          {o.suppressed && o.suppressed.count > 0 && (
            <Details summary={`${o.suppressed.count} other candidates were left out`}>
              <p>A short list is not a hidden one. They were left out because:</p>
              <ul>{Object.entries(o.suppressed.by_reason).map(([k, v]) => <li key={k}>{REASON[k] ?? k.replace(/_/g, " ")}: {v}</li>)}</ul>
            </Details>
          )}
        </>
      )}
    </Panel>
  );
}
const REASON: Record<string, string> = {
  below_effect_floor: "Too small to matter",
  group_too_small: "The group had fewer than 5 people",
  interval_spans_zero: "The interval included no change",
  no_expert_reference: "No expert to compare with",
  over_cap: "More than seven passed, and these ranked lower",
  same_kind_lower_score: "A similar insight was shown instead",
};

function Roles() {
  const q = useLoad(loadRoles, []);
  return <Panel q={q} what="the role comparison">{(d) => <RoleMultiples roles={d.roles} min={MIN_GROUP} meta={q.meta} />}</Panel>;
}

function People() {
  const q = useLoad(loadFirm, []);
  return <Panel q={q} what="the people list">{(d) => <PeopleTable firm={d} meta={q.meta} />}</Panel>;
}

function Onboarding() {
  const q = useLoad(loadOnboarding, []);
  return <Panel q={q} what="the onboarding curves">{(d) => <OnboardingCurves data={d} meta={q.meta} />}</Panel>;
}

function Automation() {
  const [days, setDays] = useState<7 | 30>(7);
  const q = useLoad(() => loadFirmHits(days), [days]);
  return (
    <Panel q={q} what="the firm's repeated work">
      {(d) => (
        <>
          <div className="firm-auto__bar">
            <p className="firm-summary">
              About <b>{fmtNum({ value: d.total.hours_per_week.point, ci: [d.total.hours_per_week.lo, d.total.hours_per_week.hi] }, "hours a week")}</b> of repeated work
              across {d.total.people} people, in {d.total.actions} actions.
            </p>
            <span className="segmented" role="group" aria-label="Window">
              {([7, 30] as const).map((n) => <button key={n} type="button" aria-pressed={days === n} onClick={() => setDays(n)}>{n} days</button>)}
            </span>
          </div>
          <HitList audience="admin" rows={d.rows} windowDays={d.window_days} label="Repeated work across the firm" />
          {d.suppressed > 0 && <p className="note">{d.suppressed} {d.suppressed === 1 ? "row is" : "rows are"} not shown because fewer than {d.min_group} people do it. The list counts people and never names them.</p>}
        </>
      )}
    </Panel>
  );
}

function Risk() {
  const q = useLoad(loadOverview, []);
  return <Panel q={q} what="risk and coverage">{(o) => <RiskCoverage o={o} meta={q.meta} />}</Panel>;
}

/** The Firm screen (Admin view only). One idea per view, reached by the tab strip or the command palette. */
export default function Firm() {
  const route = useRoute();
  const tab = firmTabOf(route.path);
  const openId = route.query.get("insight");
  useEffect(() => { document.title = tab === "overview" ? "Firm · Knack" : `${TITLE[tab]} · Firm · Knack`; }, [tab]);
  const body = useMemo(() => {
    switch (tab) {
      case "roles": return <Roles />;
      case "people": return <People />;
      case "onboarding": return <Onboarding />;
      case "automation": return <Automation />;
      case "risk": return <Risk />;
      case "forecasts": return <ScorecardPanel />;
      case "brief": return <FirmBrief />;
      default: return <Overview openId={openId} />;
    }
  }, [tab, openId]);

  const sub = tab !== "overview" && tab !== "roles" && tab !== "onboarding";
  return (
    <div className="page page--wide firm" data-tab={tab}>
      <header className="screenhead">
        {sub && <Breadcrumb items={[{ label: "Firm", href: "#/firm" }, { label: TITLE[tab] }]} />}
        <div className="screenhead__row">
          <h1 className="screenhead__title">{TITLE[tab]}</h1>
          <div className="page__aside">
            <span className="screenhead__marker">{ADMIN_MARKER}</span>
            <span className="pill pill--origin firm-synthetic" data-origin="synthetic">{SYNTHETIC_NOTE}</span>
          </div>
        </div>
        <p className="screenhead__limit">{FIRM_LIMIT}</p>
      </header>
      {body}
    </div>
  );
}
