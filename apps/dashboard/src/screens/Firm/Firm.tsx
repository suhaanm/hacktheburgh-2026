import { useEffect, useMemo } from "react";
import { useRoute } from "../../router";
import { useLoad, type LoadState } from "../../hooks";
import { ErrorState, Loading } from "../../components/common";
import { Details } from "../../components/ui";
import { AutomationBody } from "../../components/firm/AutomationBody";
import { FirmBrief } from "../../components/firm/FirmBrief";
import { FirmHead, FIRM_LIMIT } from "../../components/firm/FirmHead";
import { ForecastsView } from "../../components/firm/ForecastsView";
import { FreshNote, Headline } from "../../components/firm/InsightFirst";
import { InsightRows } from "../../components/firm/InsightRows";
import { OnboardingBody } from "../../components/firm/OnboardingCurves";
import { PeopleBody } from "../../components/firm/PeopleTable";
import { RiskCoverage } from "../../components/firm/RiskCoverage";
import { RolesBody } from "../../components/firm/RoleMultiples";
import { firmHeadline } from "../../components/firm/insights";
import { firmTabOf, type FirmTab } from "../../components/home/navModel";
import { useRemembered } from "../../lib/remember";
import { loadFirm as loadFirmHits } from "../Repeats/data";
import { loadFirm, loadOnboarding, loadOverview, loadRoles } from "./data";
import "../../components/firm/firm.css";

export { FIRM_LIMIT };

/** A title is a name, six words at most. The other views are rows in the Admin nav and the palette; the tab strip is retired. */
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
const MIN_GROUP = 5;

/** Wraps a loaded panel: loading, error and the example note are designed, never blank. The one origin pill is in the screen head, not on each panel. */
function Panel<T>({ q, what, children }: { q: LoadState<T>; what: string; children: (d: T) => React.ReactNode }) {
  if (q.status === "error" && !q.data) return <ErrorState error={q.error} retry={q.reload} what={what} />;
  if (!q.data) return <Loading label={`Loading ${what}`} />;
  return (
    <section className="firm-panel" aria-busy={q.status === "loading"}>
      {children(q.data)}
    </section>
  );
}

const asOfOf = (meta: unknown): string | null => {
  const m = meta as { as_of?: string; generated_at?: string } | null;
  return m?.as_of ?? m?.generated_at ?? null;
};

function Overview({ openId }: { openId: string | null }) {
  const q = useLoad(loadOverview, []);
  const now = useMemo(() => new Date(), []);
  return (
    <Panel q={q} what="the overview">
      {(o) => (
        <div className="insight-first">
          <Headline>{firmHeadline(o)}</Headline>
          {!q.why && <FreshNote asOf={asOfOf(q.meta)} now={now} />}
          {o.top.length > 0 ? <InsightRows items={o.top} openId={openId} /> : o.firm.users <= 0 ? (
            <p className="note">Knack shows the firm once people have been followed for a few days.</p>
          ) : (
            <div className="state"><h2 className="state__title">Nothing stands out this week</h2><p className="state__body">No insight passed every check. That is a normal result.</p></div>
          )}
          {o.firm.users > 0 && <p className="firm-links"><a href="#/firm/brief">Print the firm brief</a></p>}
          {o.suppressed && o.suppressed.count > 0 && (
            <Details summary={`${o.suppressed.count} other findings are not shown`}>
              <ul>{Object.entries(o.suppressed.by_reason).map(([k, v]) => <li key={k}>{REASON[k] ?? k.replace(/_/g, " ")}: {v}</li>)}</ul>
            </Details>
          )}
        </div>
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
  return <Panel q={q} what="the role comparison">{(d) => <RolesBody roles={d} min={MIN_GROUP} meta={q.meta} />}</Panel>;
}

function People() {
  const q = useLoad(loadFirm, []);
  return <Panel q={q} what="the people list">{(d) => <PeopleBody firm={d} meta={q.meta} />}</Panel>;
}

function Onboarding() {
  const q = useLoad(loadOnboarding, []);
  return <Panel q={q} what="the onboarding curves">{(d) => <OnboardingBody data={d} meta={q.meta} />}</Panel>;
}

function Automation() {
  // The last window the admin chose is kept, so the screen opens on it.
  const [win, setWin] = useRemembered<"7" | "30">("firm-automation-window", ["7", "30"], "7");
  const days = win === "30" ? 30 : 7;
  const q = useLoad(() => loadFirmHits(days), [days]);
  return <Panel q={q} what="the firm's repeated work">{(d) => <AutomationBody d={d} days={days} onDays={(n) => setWin(n === 30 ? "30" : "7")} />}</Panel>;
}

function Risk() {
  const q = useLoad(loadOverview, []);
  return <Panel q={q} what="risk and coverage">{(o) => <RiskCoverage o={o} meta={q.meta} />}</Panel>;
}

/** The Firm screen (Admin view only). One idea per view, reached by the Admin nav rows or the command palette. */
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
      case "forecasts": return <ForecastsView />;
      case "brief": return <FirmBrief />;
      default: return <Overview openId={openId} />;
    }
  }, [tab, openId]);

  return (
    <div className="page page--wide firm" data-tab={tab}>
      <FirmHead title={TITLE[tab]} />
      {body}
    </div>
  );
}
