import { useMemo } from "react";
import { api } from "../../api";
import { useLoad } from "../../hooks";
import { useAppState } from "../../store";
import { EmptyState, ErrorState, Loading, SourceNote, ChartFoot } from "../common";
import { WeekLegend, WeekRibbon } from "../WeekRibbon";
import { Details } from "../ui";
import { GrowthSection, useReportSource } from "./GrowthSection";
import { Distance, GapTable, Suggestions, WeekTable } from "./WeekParts";
import { ForecastSection, HoursMap, IdleStat, QuietEditor } from "./HoursParts";
import { busiestWrap, meanRow, slotLabel, toGrid } from "../../lib/heatmap";
import { weekHeadline, weekLabel, weekWindow } from "../../lib/week";
import { ownMeta } from "../../lib/ownMeta";

/** The example worker the built-in example week belongs to. Used only when the engine does not know the worker yet. */
const EXAMPLE_PERSON = "p_ninetofive";

/**
 * Where my time goes: the worker's own week against ONE experienced worker's, and their own working hours.
 * A headline sentence first (the week against the experienced worker, or the hours when there is no calendar), the picture and the numbers behind it.
 */
export function TimeSection({ open }: { open: boolean }) {
  const me = useAppState().person ?? EXAMPLE_PERSON;
  const w = useLoad(() => api.calendarWeek(me, undefined), [me]);
  const sg = useLoad(() => api.calendarSuggestions(me, undefined), [me]);
  const p = useLoad(() => api.presence(), []);
  useReportSource("time", w.why ?? p.why ?? null);

  const stretch = useMemo(() => (p.data ? busiestWrap(meanRow(toGrid(p.data.bins)), 0.5) : null), [p.data]);
  const hours = stretch ? `You are usually at the machine from ${slotLabel(stretch[0])} to ${slotLabel(stretch[1])}.` : null;

  if (w.status === "error" && !w.data && p.status === "error" && !p.data) {
    return <GrowthSection id="time" title="Where my time goes" headline="Your week could not be read just now."><ErrorState error={w.error} retry={() => { w.reload(); p.reload(); }} what="your week and hours" /></GrowthSection>;
  }
  if (!w.data && !p.data) return <GrowthSection id="time" title="Where my time goes" headline="Reading your week." busy><Loading label="Loading your week" /></GrowthSection>;

  const d = w.data;
  const empty = !d || d.days.every((x) => x.blocks.length === 0);
  const sentence = d && !empty ? `${weekHeadline(d.features, d.expert, null)}.` : hours ?? "Your week and hours appear here once a calendar is connected.";
  const win = d ? weekWindow(d.days, d.expert.days) : undefined;
  const wMeta = ownMeta(w.meta, { n: 1, unit: "week" });
  const pMeta = ownMeta(p.meta, { n: 1, unit: "week" });

  return (
    <GrowthSection id="time" title="Where my time goes" headline={sentence} open={open}>
      <div className="stack">
        {d && !empty ? (
          <>
            <div className="chart chart--wide stack" style={{ gap: "var(--space-6)" }}>
              <WeekRibbon title={`Your week${d.week ? `, ${weekLabel(d.week)}` : ""}`} days={d.days} window={win!} />
              {d.expert.days && d.expert.days.length > 0 && <WeekRibbon title="An experienced worker's week" days={d.expert.days} window={win!} />}
            </div>
            <WeekLegend />
            <ChartFoot variant="about" meta={wMeta} badge={false} extra={<span>Only the kind of block, its time and the size of the meeting are used.{d.timezone ? <> Times are in <b>{d.timezone}</b>.</> : null}</span>} />
          </>
        ) : (
          <EmptyState title="No calendar blocks this week" body="Nothing is on the calendar for this week, or no calendar is connected yet. Nothing is read until you connect one." />
        )}
        {w.why && <SourceNote why={w.why} />}
        {d && !empty && <WeekTable days={d.days} />}
        {d && d.gap.rows.length > 0 && <Details summary="Where your week differs" wide><GapTable rows={d.gap.rows} meta={wMeta} /></Details>}
        {d && <Details summary="Ideas for a calmer week" wide><Suggestions state={sg} /></Details>}
        {p.data && <Details summary="Your working hours" wide><HoursMap data={p.data} meta={pMeta} /></Details>}
        {(d?.gap.ribbon?.alignment?.length || p.data) && (
          <Details summary="More" wide>
            <div className="stack">
              {d && <Details summary="How far from an experienced worker's week" wide><Distance d={d} meta={wMeta} /></Details>}
              {p.data && (
                <>
                  <Details summary="Free hours"><IdleStat data={p.data} /></Details>
                  <Details summary="Will a background run's window last?" wide><ForecastSection data={p.data} meta={pMeta} /></Details>
                  <Details summary="Quiet hours" wide><QuietEditor key={JSON.stringify(p.data.quiet_hours)} quiet={p.data.quiet_hours} onSaved={p.reload} /></Details>
                </>
              )}
            </div>
          </Details>
        )}
      </div>
    </GrowthSection>
  );
}
