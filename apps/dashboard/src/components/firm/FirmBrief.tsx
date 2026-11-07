import { useMemo } from "react";
import { useLoad } from "../../hooks";
import { ErrorState, Loading } from "../common";
import { loadOnboarding, loadOverview, loadRoles } from "../../screens/Firm/data";
import { BRIEF_LIMITS, buildBrief, longDate } from "./brief";
import { OnboardingCurves } from "./OnboardingCurves";
import { FirmBadge } from "./Badges";

/**
 * The firm brief: one A4 page, printable (the screen's own menu and controls are left out of the print). It reads the same three answers as the
 * other Firm views, so the page and the screens cannot disagree. The print button opens the browser's own print dialog, where "Save as PDF" is the export.
 */
export function FirmBrief() {
  const o = useLoad(loadOverview, []);
  const r = useLoad(loadRoles, []);
  const w = useLoad(loadOnboarding, []);
  const brief = useMemo(() => (o.data && r.data && w.data ? buildBrief(o.data, r.data, w.data, (o.meta as { as_of?: string } | null)?.as_of ?? o.meta?.generated_at ?? null) : null), [o.data, r.data, w.data]);

  const failed = [o, r, w].find((q) => q.status === "error" && !q.data);
  if (failed && failed.status === "error") return <ErrorState error={failed.error} retry={() => { o.reload(); r.reload(); w.reload(); }} what="the firm brief" />;
  if (!brief || !o.data || !r.data || !w.data) return <Loading label="Preparing the firm brief" />;
  const date = longDate(brief.asOf);
  const example = [o, r, w].find((q) => q.why)?.why ?? null;

  return (
    <div className="brief-doc">
      <div className="brief-bar" data-noprint="true">
        <p className="brief-bar__text">One page, A4. Print it or save it as a PDF from the print dialog.</p>
        <button type="button" className="btn btn--primary btn--sm" onClick={() => window.print()}>Print the brief</button>
        {example && <span className="u-muted">Example numbers</span>}
      </div>
      <article className="brief-page" aria-labelledby="brief-title">
        <header className="brief-page__head">
          <p className="t-label">Knack · firm brief</p>
          <h2 id="brief-title" className="brief-page__title">How people are getting on</h2>
          <p className="brief-page__sub">{[brief.label, date ? `as of ${date}` : null, brief.summary].filter(Boolean).join(" · ")}</p>
          <p className="brief-page__statement">{brief.statement}</p>
        </header>

        <section className="brief-sec">
          <h3 className="brief-sec__title">Things to know</h3>
          <ol className="brief-list">
            {brief.insights.map((i) => (
              <li key={i.headline}><span className="brief-list__head">{i.headline}</span><span className="brief-list__meta">{i.effect ? `${i.effect}. ` : ""}n = {i.n}.</span></li>
            ))}
          </ol>
        </section>

        <section className="brief-sec">
          <h3 className="brief-sec__title">Experts and juniors, by role</h3>
          <table className="table brief-table">
            <thead><tr><th scope="col">Role</th><th scope="col">People</th><th scope="col">Finished without help</th><th scope="col">The gap</th></tr></thead>
            <tbody>{brief.roles.map((x) => <tr key={x.role}><th scope="row">{x.name}</th><td>{x.people}</td><td>{x.independence || "not compared"}</td><td>{x.gap}</td></tr>)}</tbody>
          </table>
        </section>

        <section className="brief-sec">
          <h3 className="brief-sec__title">How fast people reach independence</h3>
          <p className="brief-sec__sub">{brief.target}. A line to aim at, not a standard.</p>
          <OnboardingCurves data={w.data} meta={w.meta} />
          <table className="table brief-table">
            <thead><tr><th scope="col">Role</th><th scope="col" className="num">People followed</th><th scope="col">Median step to the target</th><th scope="col">Reached it so far</th></tr></thead>
            <tbody>{brief.onboarding.map((x) => <tr key={x.role}><th scope="row">{x.name}</th><td className="num">{x.n}</td><td>{x.median}</td><td>{x.reached}</td></tr>)}</tbody>
          </table>
        </section>

        <section className="brief-sec">
          <h3 className="brief-sec__title">What this cannot show</h3>
          <ul className="brief-limits">{BRIEF_LIMITS.map((l) => <li key={l}>{l}</li>)}</ul>
        </section>
        <footer className="brief-page__foot"><FirmBadge meta={o.meta} /> Built from the same data as the Firm screens.</footer>
      </article>
    </div>
  );
}
