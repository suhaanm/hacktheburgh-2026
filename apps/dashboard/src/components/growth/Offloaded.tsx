import { useState } from "react";
import { FactRows } from "../ui";
import { type OffloadItem } from "./model";

/**
 * Work done for the person, inside the closed disclosure "What Knack did for you": two label and value rows, the list, and the one rule that matters
 * (overnight work never moves the curve: printed, never only in a Hint). Two rows of the list, then "Show all".
 */
export function Offloaded({ delegated, automation, minutes, items }: { delegated: number; automation: number; minutes: { delegated: number; automation: number }; items: OffloadItem[] }) {
  const none = delegated + automation === 0;
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 2);
  const row = (n: number, one: string, many: string, min: number): string => `${n} ${n === 1 ? one : many}${min > 0 ? `, about ${Math.round(min)} min` : ""}`;
  return (
    <div className="gr-off">
      {none ? (
        <p className="note">Nothing has run for you yet. Work done for you never changes your independence score.</p>
      ) : (
        <>
          <FactRows rows={[
            ["You asked for", row(delegated, "run", "runs", minutes.delegated)],
            ["Overnight", row(automation, "automation", "automations", minutes.automation)],
          ]} />
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
          <p className="note">None of it changes your independence score.</p>
          {items.length > 2 && <button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${items.length}`}</button>}
        </>
      )}
    </div>
  );
}
