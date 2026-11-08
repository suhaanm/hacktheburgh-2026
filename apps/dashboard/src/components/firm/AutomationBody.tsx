import type { FirmWire } from "../repeats/types";
import { Headline, NumbersTable, SeeNumbers } from "./InsightFirst";
import { IntervalPlot } from "./IntervalPlot";
import { hitNumbers, hoursChart } from "./charts";
import { automationHeadline, plural } from "./insights";

/**
 * The Automation screen, insight first: one sentence on how many hours a week of repeated work the firm has and where the biggest piece is, one chart of
 * the three biggest actions with their intervals, and the whole list behind "See the numbers". People are counted, never named.
 */
export function AutomationBody({ d, days, onDays }: { d: FirmWire; days: 7 | 30; onDays: (n: 7 | 30) => void }) {
  const ch = hoursChart(d.rows, 3);
  const nums = hitNumbers(d.rows, 30);
  return (
    <div className="insight-first">
      <div className="firm-auto__bar">
        <Headline>{automationHeadline(d)}</Headline>
        <span className="segmented" role="group" aria-label="Window">
          {([7, 30] as const).map((n) => <button key={n} type="button" aria-pressed={days === n} onClick={() => onDays(n)}>{n} days</button>)}
        </span>
      </div>
      {ch.any && (
        <figure className="chart insight-chart">
          <IntervalPlot title="Hours a week of repeated work, the three biggest actions" rows={ch.rows} domain={ch.domain} ticks={ch.ticks} format={(v) => `${Math.round(v * 10) / 10} h`} rowHeight={36} />
          <figcaption className="note">Hours a week, with the 95% interval. The three biggest actions.</figcaption>
        </figure>
      )}
      <p className="note">Counts people, never names them.{d.suppressed > 0 ? ` ${plural(d.suppressed, "row", "rows")} left out (under ${d.min_group} people).` : ""}</p>
      <SeeNumbers><NumbersTable heads={nums.heads} rows={nums.rows} caption="Repeated work across the firm" limit={3} /></SeeNumbers>
    </div>
  );
}
