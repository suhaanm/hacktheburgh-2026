import type { Mark } from "./model";
import { BASELINE_N, RETENTION_DAYS, plural } from "./model";
import { Details } from "../ui";

/**
 * Nothing counted yet. The page title already says "Not enough to show yet"; this is the one line that follows: when the curve starts.
 * No ghost chart, no numbered list (KNACK_UX, Growth: empty state). How steps are counted is one closed disclosure.
 */
export function EmptyHero({ needed, window }: { needed: number; window: number }) {
  return (
    <section className="gr-empty" data-empty="true" aria-label="Nothing counted yet">
      <p className="gr-empty__line">{`Your curve starts after ${needed} steps.`}</p>
      <Details summary="How steps are counted">
        <p>Knack counts a step each time one from your role&apos;s pack comes up in your work. You do nothing extra.</p>
        <ul className="plain-list">
          <li>After {plural(BASELINE_N, "step")}, your starting point is marked on the chart, with its interval.</li>
          <li>After {needed}, the curve appears, over a {window}-step window with its interval. Fewer would be a guess, so nothing is drawn.</li>
          <li>When a step comes back {RETENTION_DAYS} or more days after you were taught it, &quot;Kept after days&quot; fills in.</li>
        </ul>
      </Details>
    </section>
  );
}

/** A few steps, not enough for a curve: show each one, claim nothing. The key and the starting point are in one closed disclosure. */
export function EarlyHero({ total, needed, marks, unaided, baseline }: { total: number; needed: number; marks: Mark[]; unaided: number; baseline: { k: number; n: number } | null }) {
  const slots = Math.max(needed, total);
  const shown = marks.length === total ? marks : null;
  return (
    <section className="gr-early" aria-label="Too few steps for a curve">
      <p className="gr-empty__line">{`${plural(total, "step")} so far. Your curve starts after ${needed}.`}</p>
      <ol className="gr-marks" aria-label={`${total} steps so far, ${unaided} finished with no cue accepted`}>
        {Array.from({ length: slots }, (_, i) => {
          const m = shown?.[i];
          const kind = i >= total ? "empty" : m ? (m.unaided ? "unaided" : "helped") : i < unaided ? "unaided" : "helped";
          return <li key={i} className="gr-mark" data-kind={kind} />;
        })}
      </ol>
      <Details summary="About these marks">
        <ul className="legend gr-legend" aria-label="How to read the marks">
          <li className="legend__item"><i className="gr-mark gr-mark--sw" data-kind="unaided" />Finished with no cue accepted ({unaided})</li>
          <li className="legend__item"><i className="gr-mark gr-mark--sw" data-kind="helped" />Needed a cue ({total - unaided})</li>
          <li className="legend__item"><i className="gr-mark gr-mark--sw" data-kind="empty" />Still to come</li>
        </ul>
        {baseline && <p className="note">So far, {baseline.k} of your first {baseline.n} finished with no cue accepted. That becomes your starting point on the chart.</p>}
      </Details>
    </section>
  );
}
