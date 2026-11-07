import { OriginBadge } from "../common";
import type { AnalyticMeta } from "../../types";
import { limitations, originSentence, type GrowthView } from "./model";

/** What these numbers are and what they are not: the origin, n, interval, the weights assumption, and the limits. */
export function About({ view, meta }: { view: GrowthView; meta: AnalyticMeta | null }) {
  const w = view.weights;
  const origin = meta?.origin;
  return (
    <section className="section gr-about" aria-labelledby="about-h">
      <h2 id="about-h" className="section__title">About these numbers</h2>
      <p className="gr-about__origin">
        <OriginBadge meta={meta} always />
        <span>{originSentence(view.originDetail, origin)}</span>
      </p>
      <ul className="plain-list gr-about__list">
        <li>This shows how much less help you need. It does not show how expert you are.</li>
        <li>Every share has a Wilson interval and every trend a bootstrap interval, both at {view.levelPct}%. Where the data are thin, the interval is wide.</li>
        <li>The composite weights are {Math.round(w.independence_lb * 100)}% independence, {Math.round(w.mastery * 100)}% mastery, {Math.round(w.gap_closure * 100)}% time lost won back and {Math.round(w.retention * 100)}% kept after days. {view.weightsNote}</li>
      </ul>
      <details className="details-lite">
        <summary>Limitations</summary>
        <ul className="plain-list gr-lims">
          {limitations(view, origin).map((l) => <li key={l}>{l}</li>)}
        </ul>
      </details>
    </section>
  );
}
