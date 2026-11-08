import { useId, useMemo, useState } from "react";
import { useLoad } from "../../hooks";
import { EmptyState, ErrorState, Loading, SourceNote } from "../common";
import { Details, FactRows } from "../ui";
import { loadFirm as loadFirmHits } from "../../screens/Repeats/data";
import { loadFirm, loadOnboarding, loadRoles } from "../../screens/Firm/data";
import { CONFIDENCE_ROWS, ConfidenceWord, FreshNote, NumbersTable, SeeNumbers } from "./InsightFirst";
import { IntervalPlot } from "./IntervalPlot";
import { MixBar } from "./MixBar";
import { ScorecardView, useScorecard } from "./ScorecardPanel";
import { buildForecastInsights, type ForecastChart, type ForecastInsight } from "./forecastInsights";
import { pct } from "./model";

const valueFor = (unit: "share" | "steps" | "hours") => (unit === "share" ? pct : unit === "hours" ? (v: number) => `${Math.round(v * 10) / 10} h` : (v: number) => String(Math.round(v)));
const tickFor = (unit: "share" | "steps" | "hours") => (unit === "share" ? pct : (v: number) => String(Math.round(v * 10) / 10));

/** The one chart of an insight: dots with their intervals on one axis, or one stacked bar. It is the evidence for the sentences above it and nothing else. */
export function ChartOf({ chart }: { chart: ForecastChart }) {
  if (chart.kind === "mix") return <MixBar title={chart.title} parts={chart.parts} total={chart.total} />;
  return <IntervalPlot title={chart.title} rows={chart.rows} domain={chart.domain} ticks={chart.ticks} format={valueFor(chart.unit)} tickFormat={tickFor(chart.unit)} rowHeight={34} side />;
}

/**
 * One insight: its confidence word and n, what to expect, what to do. The evidence (the interval and the one chart) opens in place; the first insight
 * opens on arrival. Two short sentences, never more. The sentences are fixed templates filled by code, so a model never writes what an admin reads.
 */
export function InsightCard({ i, open, onToggle }: { i: ForecastInsight; open: boolean; onToggle: () => void }) {
  const evidence = useId();
  return (
    <article className="fc" aria-label={`${i.expect} ${i.todo}`}>
      <div className="fc__head">
        <ConfidenceWord level={i.confidence} />
        <span className="fc__n">{i.n}</span>
        <button type="button" className="fc__toggle" aria-expanded={open} aria-controls={evidence} aria-label={open ? "Hide the evidence for this forecast" : "Show the evidence for this forecast"} onClick={onToggle}>
          <span className="fc__chev" aria-hidden="true" data-open={open} />
        </button>
      </div>
      <p className="fc__line">{i.expect}</p>
      <p className="fc__line fc__do"><span aria-hidden="true">→ </span><span className="u-sr-only">Do: </span>{i.todo}</p>
      {open && (
        <div className="fc__evidence" id={evidence}>
          {i.detail && <p className="fc__meta">{i.detail}</p>}
          <div className="fc__chart"><ChartOf chart={i.chart} /></div>
        </div>
      )}
    </article>
  );
}

/**
 * Forecasts for the Admin: up to three plain insights (what to expect, what to do about it, one confidence word), the first with its one chart open,
 * then the numbers behind one closed "See the numbers". How well the forecasts hold up is a second closed disclosure.
 * Everything is read from the answers the other Admin views read, so the page and the screens cannot disagree.
 */
export function ForecastsView() {
  const onb = useLoad(loadOnboarding, []);
  const roles = useLoad(loadRoles, []);
  const firm = useLoad(loadFirm, []);
  const hits = useLoad(() => loadFirmHits(7), []);
  const card = useScorecard();
  const now = useMemo(() => new Date(), []);
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const all = [onb, roles, firm, hits];
  const insights = useMemo(
    () => buildForecastInsights({ onboarding: onb.data, roles: roles.data, firm: firm.data, hits: hits.data, now }),
    [onb.data, roles.data, firm.data, hits.data, now],
  );

  if (all.every((q) => q.status === "error" && !q.data)) return <ErrorState error={onb.error ?? new Error("The forecasts could not be read")} retry={() => all.forEach((q) => q.reload())} what="the forecasts" />;
  if (all.some((q) => q.status === "loading" && !q.data)) return <Loading label="Working out the forecasts" />;
  const why = all.find((q) => q.why)?.why ?? null;
  const asOf = (onb.meta as { as_of?: string } | null)?.as_of ?? onb.meta?.generated_at ?? null;
  // The first insight is open until the admin chooses another; choosing the open one closes it.
  const openId = picked === undefined ? insights[0]?.id ?? null : picked;

  return (
    <section className="firm-panel fc-panel" aria-label="Forecasts">
      {!why && <FreshNote asOf={asOf} now={now} />}
      {insights.length === 0 ? (
        <EmptyState title="Nothing to forecast yet" body="Forecasts appear once people have been followed for weeks." />
      ) : (
        <>
          <div className="fc-list">
            {insights.map((i) => <InsightCard key={i.id} i={i} open={openId === i.id} onToggle={() => setPicked(openId === i.id ? null : i.id)} />)}
          </div>
          <p className="note fc-limit">Not validated on real people yet.</p>
          <SeeNumbers>
            <div className="stack" style={{ gap: "var(--space-2)" }}>
              {insights.map((i) => (
                <Details key={i.id} summary={i.short}><NumbersTable heads={i.numbers.heads} rows={i.numbers.rows} caption={i.chart.title} /></Details>
              ))}
            </div>
          </SeeNumbers>
        </>
      )}
      <Details summary="How reliable are these forecasts?" wide>
        <div className="stack">
          <p className="note">Not validated on real people. The check below scores the stuck-moment forecast that decides when Knack speaks.</p>
          <Details summary="What the confidence words mean"><FactRows rows={CONFIDENCE_ROWS} /></Details>
          <Details summary="The reliability check" wide>
            <ScorecardView load={card.load} read={card.read} audience="admin" />
          </Details>
        </div>
      </Details>
      <SourceNote why={why} />
    </section>
  );
}
