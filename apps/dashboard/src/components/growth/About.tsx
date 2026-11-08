import type { ReactNode } from "react";
import type { AnalyticMeta } from "../../types";
import { Details, FactRows, splitRows } from "../ui";
import { GrowthKey } from "./GrowthChart";
import { Summary } from "./Summary";
import { Cards } from "./Cards";
import { limitations, originSentence, plural, type GrowthView } from "./model";

/**
 * "About this data": the one disclosure under the chart (KNACK_UX, Growth). The first lines are the facts a figure needs (n, window, the interval level,
 * where the numbers come from, in the screen's own words); the key, the three plain measures and the limits are one closed disclosure each inside it,
 * so nothing is lost and nothing crowds the first screen. The origin badge itself stays printed in the header.
 */
export function AboutGrowth({ view, meta, n, children }: { view: GrowthView; meta: AnalyticMeta | null; n: number; children?: ReactNode }) {
  const w = view.weights;
  const origin = meta?.origin;
  const rows: [string, ReactNode][] = [
    ["n", plural(n, "step")],
    ...(meta?.split ? ([["window", meta.split]] as [string, ReactNode][]) : []),
    ["intervals", `${view.levelPct}%`],
    ["origin", `${originSentence(view.originDetail, origin)}${meta?.note ? ` ${meta.note}` : ""}`],
    ...(view.claim ? ([["skills", view.claim]] as [string, ReactNode][]) : []),
  ];
  const { short, long } = splitRows(rows);
  return (
    <Details summary="About this data" className="about" wide>
      <FactRows rows={short} />
      <Details summary="More" wide>
        {long.length > 0 && <FactRows rows={long} />}
        {children}
        {view.status === "ready" && (
          <>
            <Details summary="Key" wide><GrowthKey view={view} /></Details>
            <Details summary="The three measures" wide>
              <Cards cards={view.cards} levelPct={view.levelPct} />
              <Summary view={view} n={n} />
            </Details>
          </>
        )}
        <Details summary="Limits" wide>
          <ul className="plain-list gr-lims">
            <li>Every share has a Wilson interval and every trend a bootstrap interval, both at {view.levelPct}%. Where the data are thin, the interval is wide.</li>
            <li>The headline figures are the trend and independence now. The composite is experimental and sits in its own disclosure, with its weights ({Math.round(w.independence_lb * 100)}% independence, {Math.round(w.mastery * 100)}% mastery, {Math.round(w.gap_closure * 100)}% time lost won back, {Math.round(w.retention * 100)}% kept after days). {view.weightsNote}</li>
            <li>When a trend&apos;s interval includes zero, the page says it cannot tell yet. It never says nothing changed.</li>
            {limitations({ ...view, caveat: view.composite?.caveat }, origin).map((l) => <li key={l}>{l}</li>)}
          </ul>
        </Details>
      </Details>
    </Details>
  );
}
