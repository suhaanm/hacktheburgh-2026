import { fmtInterval } from "../lib/format";
import { liveFixSentence, liveRuns, liveSentence } from "../lib/evidence";
import { ChartFoot, OriginBadge } from "./common";
import type { AnalyticMeta } from "../types";

/**
 * The real-model runs on the sandbox, one line per condition. No number appears without the condition it was measured under:
 * "clean pages, 18 of 20" and "a 503 error, 0 of 20 with 20 false claims" are never reduced to a total. The fix made after the result
 * was seen is marked IN-SAMPLE.
 */
export function LiveRuns({ live, meta }: { live: unknown; meta: AnalyticMeta | null }) {
  const v = liveRuns(live);
  if (!v || v.rows.length === 0) return null;
  return (
    <div className="stack live" data-testid="live-runs">
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <p className="t-label">Real model, small n</p>
        <div className="row" style={{ gap: "var(--space-2)" }}>
          <OriginBadge meta={meta} always />
          <span className="pill">{v.label}</span>
          {v.households != null && <span className="pill">{v.households} households per condition</span>}
          <span className="pill">sandbox calculators</span>
        </div>
        {v.note && <p className="ev-note">{v.note}</p>}
      </div>

      <ul className="live__list">
        {v.rows.map((r) => (
          <li key={r.key} data-testid={`live-${r.key}`} data-false={(r.falseClaims ?? 0) > 0 && !r.mustPause}>
            <span className="live__text">{liveSentence(r)}</span>
            <span className="live__what u-muted">{r.what}</span>
            {r.failureReasons[0] && (r.pass ?? r.n) < r.n && !r.mustPause && <span className="live__what u-muted">Why it failed: {r.failureReasons[0]}.</span>}
          </li>
        ))}
      </ul>

      {v.fix && (
        <div className="live__fix" data-testid="live-fix">
          <div className="row" style={{ gap: "var(--space-2)" }}>
            {v.fix.inSample && <span className="pill pill--insample" title="The fix was made after this result was seen, on the same kind of case">in-sample</span>}
            <b>The fix for the 503 error</b>
          </div>
          <p className="live__text">{liveFixSentence(v.fix)}</p>
          <p className="ev-note">{v.fix.description}.{v.fix.inSample ? " It was made after the result above was seen, so this row is not a fresh test and should not be read as one." : ""}</p>
          {v.fix.droppedNote && <details className="details-lite"><summary>Rows left out of every number</summary><p className="ev-note">{v.fix.droppedNote}</p></details>}
        </div>
      )}

      <details className="details-lite">
        <summary>See the conditions as a table</summary>
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Condition</th><th className="num">Households</th><th className="num">Passed</th><th>95% interval</th><th className="num">False claims</th><th className="num">Paused</th></tr></thead>
          <tbody>
            {v.rows.map((r) => (
              <tr key={r.key}>
                <td>{r.label}</td><td className="num">{r.n}</td>
                <td className="num">{r.mustPause ? "not the measure" : r.pass != null ? `${r.pass} of ${r.n}` : ""}</td>
                <td className="num interval">{r.wilson ? fmtInterval(r.wilson, 2) : ""}</td>
                <td className="num">{r.falseClaims ?? ""}</td><td className="num">{r.paused ?? ""}</td>
              </tr>
            ))}
            {v.fix && (
              <tr>
                <td>After the fix, 503 error <span className="pill pill--insample">in-sample</span></td><td className="num">{v.fix.n}</td>
                <td className="num">{v.fix.pass != null ? `${v.fix.pass} of ${v.fix.n}` : ""}</td>
                <td className="num interval">{v.fix.wilson ? fmtInterval(v.fix.wilson, 2) : ""}</td>
                <td className="num">{v.fix.falseClaims ?? ""}</td><td className="num" />
              </tr>
            )}
          </tbody>
        </table></div>
      </details>

      {v.tier3 && <p className="ev-note">Computer use (tier 3): {v.tier3}</p>}
      <p className="ev-note">This is evidence from a small run, not proof. {v.households ?? "A few"} households per condition shows how the agent fails and what catches it, not how often it would on other pages.{v.costUsd != null ? ` Estimated cost of this run: $${v.costUsd.toFixed(3)}, at assumed prices.` : ""}</p>
      <ChartFoot brief meta={meta} />
    </div>
  );
}
