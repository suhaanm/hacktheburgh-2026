import { change, pct, pctBracket, type GrowthView } from "./model";

/**
 * The headline line: the trend, independence now, and n, always together.
 * The composite is not here. It overstated improvement on simulated learners whose skill had not changed, so it lives
 * inside a disclosure marked experimental, with its caveat and its parts.
 */
export function Summary({ view, n }: { view: GrowthView; n: number }) {
  const t = view.trend;
  const ind = view.independence;
  const c = view.composite;
  return (
    <div className="gr-summary">
      <dl className="gr-summary__row">
        <div>
          <dt>Trend</dt>
          <dd className="num">
            {t.per10 != null && t.ci ? <>{change(t.per10, Math.abs(t.per10) < 10 ? 1 : 0)} points per 10 occurrences <span className="gr-iv">[{change(t.ci[0], 1)}, {change(t.ci[1], 1)}]</span></> : "Too early"}
            {t.direction === "steady" && <span className="gr-tag gr-tag--wait">cannot tell yet</span>}
          </dd>
        </div>
        <div>
          <dt>Independent now</dt>
          <dd className="num">
            {ind ? <>{pct(ind.share)} <span className="gr-iv">{pctBracket(ind.ci)}</span> <span className="gr-iv">of the latest {ind.n}</span></> : "Not yet"}
          </dd>
        </div>
        <div>
          <dt>Counted</dt>
          <dd className="num">{n} {n === 1 ? "occurrence" : "occurrences"}</dd>
        </div>
      </dl>
      <p className="gr-summary__says">{t.sentence}</p>
      {c && (
        <details className="details-lite gr-comp-detail">
          <summary>Experimental composite score and how it is made</summary>
          <p className="gr-experimental"><span className="pill gr-exp" data-experimental="true">experimental</span>{c.caveat}</p>
          <p className="gr-comp-value num">
            {Math.round(c.value)} of 100 {c.ci && <span className="gr-iv">[{Math.round(c.ci[0])}, {Math.round(c.ci[1])}]</span>}
          </p>
          <table className="table">
            <caption className="u-sr-only">The four parts of the composite and their weights</caption>
            <thead><tr><th scope="col">Part</th><th scope="col" className="num">Weight</th><th scope="col" className="num">Value</th></tr></thead>
            <tbody>
              {c.parts.map((p) => (
                <tr key={p.id}>
                  <th scope="row" className="gr-rowhead">{p.label}</th>
                  <td className="num">{p.weight > 0 ? `${Math.round(p.weight * 100)}%` : "left out"}</td>
                  <td className="num">{p.shown}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">{c.note} The weights are stated assumptions, not fitted. Do not read the composite on its own: it moves with its parts, and the trend and the independence interval above are the reliable figures.</p>
        </details>
      )}
    </div>
  );
}
