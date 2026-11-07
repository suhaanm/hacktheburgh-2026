import { useState } from "react";
import { plural, type OffloadItem } from "./model";

/**
 * Work done for the person, inside the closed disclosure "What Knack did for you". Counted and listed apart from the score, and said to be outside it:
 * overnight work never moves the curve (a printed rule, never only in a Hint).
 */
export function Offloaded({ delegated, automation, minutes, items }: { delegated: number; automation: number; minutes: { delegated: number; automation: number }; items: OffloadItem[] }) {
  const none = delegated + automation === 0;
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 5);
  return (
    <div className="gr-off">
      <p className="note">Runs you asked for and overnight automations. They never change your independence score.</p>
      {none ? (
        <p className="note">Nothing has run for you yet.</p>
      ) : (
        <>
          <p className="gr-off__counts num">
            <span><b>{delegated}</b> {delegated === 1 ? "run you asked for" : "runs you asked for"}{minutes.delegated > 0 && <span className="gr-off__min"> · about {Math.round(minutes.delegated)} min</span>}</span>
            <span><b>{automation}</b> {automation === 1 ? "overnight automation" : "overnight automations"}{minutes.automation > 0 && <span className="gr-off__min"> · about {Math.round(minutes.automation)} min</span>}</span>
          </p>
          {items.length > 0 && (
            <ol className="gr-off__list">
              {shown.map((i) => (
                <li key={i.id} className="gr-off__item">
                  <span className="gr-off__when num">{i.when}</span>
                  <span className="gr-off__what">{i.streamWord}: {i.what}</span>
                  <span className="gr-off__outcome">{i.outcome}{i.minutes != null ? ` · ${Math.round(i.minutes)} min` : ""}</span>
                </li>
              ))}
            </ol>
          )}
          {items.length > 5 && <button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${items.length}`}</button>}
          {items.length > 0 && items.length < delegated + automation && <p className="note">Showing the latest {plural(items.length, "run")}.</p>}
        </>
      )}
    </div>
  );
}
