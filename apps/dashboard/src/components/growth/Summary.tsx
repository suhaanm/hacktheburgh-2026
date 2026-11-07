import { change, pctBracket, type GrowthView } from "./model";

/** Trend, composite and n on one line, always together: the composite is never shown alone. */
export function Summary({ view, n }: { view: GrowthView; n: number }) {
  const t = view.trend;
  const c = view.composite;
  return (
    <div className="gr-summary">
      <dl className="gr-summary__row">
        <div>
          <dt>Trend</dt>
          <dd className="num">
            {t.per10 != null && t.ci ? <>{change(t.per10, Math.abs(t.per10) < 10 ? 1 : 0)} points per 10 occurrences <span className="gr-iv">[{change(t.ci[0], 1)}, {change(t.ci[1], 1)}]</span></> : "Too early"}
          </dd>
        </div>
        <div>
          <dt>Composite</dt>
          <dd className="num">
            {c ? <>{Math.round(c.value)} of 100 {c.ci && <span className="gr-iv">[{Math.round(c.ci[0])}, {Math.round(c.ci[1])}]</span>}</> : "Withheld"}
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
          <summary>How the composite is made</summary>
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
          <p className="note">{c.note} The weights are stated assumptions, not fitted. The score is {Math.round(c.value)} of 100{c.ci ? `, ${pctBracket([c.ci[0] / 100, c.ci[1] / 100])} at ${view.levelPct}%` : ""}.</p>
        </details>
      )}
    </div>
  );
}
