import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { idle, useLoad } from "../../hooks";
import { ChartFoot, EmptyState, LegendItem, Loading, SourceNote } from "../common";
import { Ribbon } from "../Ribbon";
import { Explain } from "../Explain";
import { Details, FactRows } from "../ui";
import { GrowthSection, SectionError, useReportSource } from "./GrowthSection";
import { useAppState } from "../../store";
import { notKnown, unknownAsError, useOwnPerson } from "./own";
import { describeColumn, layoutRibbon } from "../../lib/ribbon";
import { cogLabel, fmtDuration } from "../../lib/format";
import { stepsHeadline, topLosses } from "../../lib/steps";
import { ownMeta } from "../../lib/ownMeta";
import { safeWhy } from "../../lib/voice";
import type { Genome as GenomeData } from "../../types";
import type { Loaded } from "../../api";

/** The task the worker's ribbon is cut from, by role: the engine has one reference trace per task (a benefits entitlement check, a programmer's fix, an analyst's chart). */
export const taskFor = (role: string | null | undefined): string => (role === "programmer" ? "programmer" : role === "data-analyst" ? "data-analyst" : "t_entitlement_check");

/**
 * My steps against an experienced worker's: the work ribbon for the worker's own case lined up with ONE experienced worker's, unnamed.
 * No average over other people, no count of them and no other person's id is drawn (docs/knack-ux/views.md).
 */
export function StepsSection({ open }: { open: boolean }) {
  const own = useOwnPerson();
  const me = own.person;
  const task = taskFor(useAppState().role);
  const g = unknownAsError(useLoad(() => (own.ready ? (own.blocked ? notKnown<Loaded<GenomeData>>() : api.genome(task, me, "nearest_expert")) : idle<GenomeData>()), [own.ready, own.blocked, me, task]));
  useReportSource("steps", g.why ?? null);
  const cols = useMemo(() => (g.data ? layoutRibbon(g.data, 1000).columns : []), [g.data]);

  if (g.status === "error" && !g.data) {
    return <GrowthSection id="steps" title="My steps" headline="Your steps could not be read just now."><SectionError error={g.error} retry={g.reload} what="your steps" empty="Nothing has been recorded for you yet." /></GrowthSection>;
  }
  if (!g.data) return <GrowthSection id="steps" title="My steps" headline="Reading your steps." busy><Loading label="Loading your steps" /></GrowthSection>;
  const data = g.data;
  const losses = topLosses(cols);

  return (
    <GrowthSection id="steps" title="My steps against an experienced worker's" headline={stepsHeadline(data.person_gap_s, cols)} open={open}>
      {cols.length === 0 ? (
        <EmptyState title="No steps to line up yet" body="Once Knack has seen you do this task, your steps appear next to an experienced worker's." />
      ) : (
        <div className="stack">
          <RibbonView data={data} cols={cols} />
          {losses.length > 0 && (
            <FactRows rows={losses.map((l) => [cogLabel(l.cog), l.skipped ? `skipped, ${Math.round(l.seconds)} s counted` : `${Math.round(l.seconds)} s lost`] as [string, string])} />
          )}
          <Details summary="Explain this case" wide><Explain person={me} /></Details>
          <Details summary="Key and more" wide><KeyAndMore data={data} cols={cols} meta={ownMeta(g.meta, { n: 1, unit: "case" })} /></Details>
        </div>
      )}
      {g.why && <SourceNote why={safeWhy(g.why)} />}
    </GrowthSection>
  );
}

function RibbonView({ data, cols }: { data: GenomeData; cols: ReturnType<typeof layoutRibbon>["columns"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [scrub, setScrub] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const active = hover ?? scrub;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setScrub((s) => {
        const next = (s ?? -1) + 1;
        if (next >= cols.length) { setPlaying(false); return cols.length - 1; }
        return next;
      });
    }, 900);
    return () => window.clearInterval(id);
  }, [playing, cols.length]);

  const consequences = data.consequences ?? [];
  const consequenceFor = (cog: string | undefined) => consequences.find((c) => cog && c.step.toLowerCase().replace(/[ -]/g, "_") === cog.toLowerCase());
  const sentence = (c: NonNullable<GenomeData["consequences"]>[number]) => {
    const wrong = Math.round(c.p_error * c.n);
    return `Skipping this step gives a wrong answer on ${wrong} of ${c.n} households, by about £${Math.round(c.mean_error_gbp)}${c.source ? ` (${c.source})` : ""}.`;
  };
  const activeCol = active != null ? cols[active] : null;
  const caption = activeCol
    ? `${describeColumn(activeCol, active as number, cols.length, "you")}${activeCol.missing === "novice" && consequenceFor(activeCol.expert?.cog) ? ` ${sentence(consequenceFor(activeCol.expert?.cog)!)}` : ""}`
    : "";

  return (
    <div className="stack">
      <div className="chart chart--wide">
        <Ribbon genome={data} active={active} onActive={setHover} voice="you" />
      </div>
      <div className="scrub">
        <div className="scrub__row">
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => { if (!playing && (scrub == null || scrub >= cols.length - 1)) setScrub(-1); setPlaying((p) => !p); }} aria-pressed={playing}>
            {playing ? "Pause" : "Play"}
          </button>
          <label className="u-sr-only" htmlFor="gr-scrub">Step through the two traces</label>
          <input id="gr-scrub" type="range" min={0} max={cols.length - 1} step={1} value={scrub ?? 0}
            onChange={(e) => { setPlaying(false); setScrub(Number(e.target.value)); }}
            aria-valuetext={caption} />
        </div>
        <p className="scrub__caption" aria-live="polite">{caption}</p>
      </div>
    </div>
  );
}

/** The key, what skipping a step can cost, and every step as a table. The footer says where the numbers came from. */
function KeyAndMore({ data, cols, meta }: { data: GenomeData; cols: ReturnType<typeof layoutRibbon>["columns"]; meta: ReturnType<typeof useLoad<GenomeData>>["meta"] }) {
  const consequences = data.consequences ?? [];
  return (
    <div className="stack">
      <ul className="legend" aria-label="How to read the ribbon">
        <LegendItem swatch={<span className="sw sw--expert" />}>The experienced worker&apos;s step</LegendItem>
        <LegendItem swatch={<span className="sw sw--novice" />}>Your step</LegendItem>
        <LegendItem swatch={<span className="sw sw--hatch sw--muted" />}>Hatched: only one of you did it</LegendItem>
        <LegendItem swatch={<span className="sw sw--bad" />}>Red: seconds lost in that column</LegendItem>
      </ul>
      <p className="note">A skipped step shows as time saved here. It often costs more later.</p>
      <Details summary="More" wide>
        <div className="stack">
          <p className="note">Column width is the longer of the two durations. The ribbon is one case; the time total is {fmtDuration(cols.reduce((s, c) => s + (Number.isFinite(c.lost) ? c.lost : 0), 0))} lost.</p>
          {consequences.length > 0 && <ul className="plain-list">{consequences.map((c) => <li key={c.step} className="note"><b>{cogLabel(c.step)}:</b> {`Skipping this step gives a wrong answer on ${Math.round(c.p_error * c.n)} of ${c.n} households, by about £${Math.round(c.mean_error_gbp)}${c.source ? ` (${c.source})` : ""}.`}</li>)}</ul>}
          <Details summary="As a table" wide>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Step</th><th>Experienced worker</th><th>You</th><th className="num">Lost</th></tr></thead>
                <tbody>
                  {cols.map((c, i) => (
                    <tr key={i}>
                      <td className="num">{i + 1}</td>
                      <td>{c.expert ? `${cogLabel(c.expert.cog)}, ${Math.round(c.expert.seconds)} s` : "no step"}</td>
                      <td>{c.novice ? `${cogLabel(c.novice.cog)}, ${Math.round(c.novice.seconds)} s` : "skipped"}</td>
                      <td className="num">{c.saved > 0 ? `saved ${Math.round(c.saved)} s` : `${Math.round(c.lost)} s`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Details>
          <ChartFoot variant="about" meta={meta} badge={false} />
        </div>
      </Details>
    </div>
  );
}
