import type { Mark } from "./model";
import { BASELINE_N, RETENTION_DAYS, plural, remainingUntil } from "./model";

/** Nothing counted yet: what will appear, and when. A skeleton of the chart shows where it will go. */
export function EmptyHero({ needed, window }: { needed: number; window: number }) {
  return (
    <section className="gr-empty" aria-labelledby="empty-h">
      <h2 id="empty-h" className="section__title">Nothing is counted yet</h2>
      <p className="t-prose">An occurrence is counted each time a step from your role's pack comes up in your real work. You do not have to do anything extra. Here is what will appear, and when.</p>
      <svg className="gr-skeleton" viewBox="0 0 560 150" role="img" aria-label="A sketch of the chart that will appear: an empty curve area with the first five occurrences marked as the starting point">
        <g className="svg-grid">
          {[0, 1, 2, 3, 4].map((i) => <line key={i} x1="44" x2="548" y1={14 + i * 28} y2={14 + i * 28} />)}
        </g>
        <text className="svg-text" x="38" y="18" textAnchor="end">100%</text>
        <text className="svg-text" x="38" y="130" textAnchor="end">0%</text>
        <line className="svg-axis" x1="44" x2="548" y1="126" y2="126" />
        <rect className="gr-skeleton__first" x="44" y="14" width="46" height="112" />
        <text className="svg-text" x="48" y="112">first {BASELINE_N}</text>
        <path className="gr-skeleton__curve" d="M 150 100 C 230 96, 300 70, 360 56 S 480 36, 540 30" />
        <text className="svg-text" x="150" y="143">occurrence {needed}: the curve starts</text>
        <text className="svg-text" x="548" y="143" textAnchor="end">time</text>
      </svg>
      <ol className="gr-steps">
        <li><b>After {plural(BASELINE_N, "occurrence")}.</b> Your starting point is marked on the chart, with its interval.</li>
        <li><b>After {needed}.</b> The curve appears, with its {window}-occurrence window and its interval. Fewer than that would be a guess, so nothing is drawn.</li>
        <li><b>When a step comes back {RETENTION_DAYS} or more days after you were taught it.</b> "Keeps it after a few days" fills in.</li>
      </ol>
    </section>
  );
}

/** A few occurrences, not enough for a curve: show each one, claim nothing. */
export function EarlyHero({ total, needed, marks, unaided, baseline }: { total: number; needed: number; marks: Mark[]; unaided: number; baseline: { k: number; n: number } | null }) {
  const left = remainingUntil(total, needed);
  const slots = Math.max(needed, total);
  const shown = marks.length === total ? marks : null;
  return (
    <section className="gr-early" aria-labelledby="early-h">
      <h2 id="early-h" className="section__title">{plural(total, "occurrence")} so far</h2>
      <p className="t-prose">The curve starts at {needed}, so it needs {plural(left, "more occurrence")}. Until then there is nothing to estimate, so nothing is drawn. Here is each one.</p>
      <ol className="gr-marks" aria-label={`${total} occurrences so far, ${unaided} finished with no cue accepted`}>
        {Array.from({ length: slots }, (_, i) => {
          const m = shown?.[i];
          const kind = i >= total ? "empty" : m ? (m.unaided ? "unaided" : "helped") : i < unaided ? "unaided" : "helped";
          return <li key={i} className="gr-mark" data-kind={kind} title={kind === "empty" ? "Not yet" : kind === "unaided" ? "Finished with no cue accepted" : "Needed a cue"} />;
        })}
      </ol>
      <ul className="legend gr-legend" aria-label="How to read the marks">
        <li className="legend__item"><i className="gr-mark gr-mark--sw" data-kind="unaided" />Finished with no cue accepted ({unaided})</li>
        <li className="legend__item"><i className="gr-mark gr-mark--sw" data-kind="helped" />Needed a cue ({total - unaided})</li>
        <li className="legend__item"><i className="gr-mark gr-mark--sw" data-kind="empty" />Still to come</li>
      </ul>
      {baseline && <p className="note">So far, {baseline.k} of your first {baseline.n} finished with no cue accepted. That becomes your starting point on the chart.</p>}
    </section>
  );
}
