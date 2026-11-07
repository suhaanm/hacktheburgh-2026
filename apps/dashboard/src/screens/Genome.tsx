import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { useRoute } from "../router";
import { ChartFoot, ErrorState, LegendItem, Loading, OriginBadge, PageHead } from "../components/common";
import { Ribbon } from "../components/Ribbon";
import { Waterfall } from "../components/Waterfall";
import { DotWhisker } from "../components/DotWhisker";
import { TransitionGraph } from "../components/TransitionGraph";
import { describeColumn, layoutRibbon } from "../lib/ribbon";
import { cogLabel, fmtDuration, fmtInterval, signed } from "../lib/format";
import type { Genome as GenomeData } from "../types";

type View = "ribbon" | "graph";

export default function Genome() {
  const route = useRoute();
  const person = route.query.get("person") ?? undefined;
  const [view, setView] = useState<View>("ribbon");
  const [reference, setReference] = useState<"nearest_expert" | "consensus">("nearest_expert");
  const g = useLoad(() => api.genome("t_entitlement_check", person, reference), [person, reference]);
  const t = useLoad(() => api.transitions("t_entitlement_check"), []);

  if (g.status === "error" && !g.data) return <div className="page"><ErrorState error={g.error} retry={g.reload} what="the work genome" /></div>;
  if (!g.data) return <div className="page"><Loading label="Loading the work genome" /></div>;
  const data = g.data;
  const total = data.total_gap_s;

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="Genome · benefits entitlement check"
        title={`The novice loses about ${fmtDuration(total)} on this case`}
        lede={<>Expert on top, novice below. The 95% interval is {fmtDuration(data.total_gap_ci[0])} to {fmtDuration(data.total_gap_ci[1])}. Hatched means a step one person did and the other did not. Red is seconds lost.</>}
        aside={<OriginBadge meta={g.meta} />}
      />

      <section className="hero" aria-labelledby="hero-h">
        <div className="hero__bar">
          <h2 id="hero-h" className="u-sr-only">{view === "ribbon" ? "Work ribbon" : "Transition graph"}</h2>
          <div className="segmented" role="group" aria-label="View">
            <button type="button" aria-pressed={view === "ribbon"} onClick={() => setView("ribbon")}>Work ribbon</button>
            <button type="button" aria-pressed={view === "graph"} onClick={() => setView("graph")}>Transition graph</button>
          </div>
          <details className="details-lite">
            <summary>Change the comparison</summary>
            <div className="stack">
              <p className="note">The novice is compared with a reference. The nearest expert is the single closest expert trace. The consensus blends all experts.</p>
              <div className="segmented" role="group" aria-label="Reference">
                <button type="button" aria-pressed={reference === "nearest_expert"} onClick={() => setReference("nearest_expert")}>Nearest expert</button>
                <button type="button" aria-pressed={reference === "consensus"} onClick={() => setReference("consensus")}>Consensus</button>
              </div>
            </div>
          </details>
        </div>

        {view === "ribbon" ? <RibbonView data={data} /> : (
          <div className="stack">
            {t.data ? <TransitionGraph data={t.data} /> : t.status === "error" ? <ErrorState error={t.error} retry={t.reload} what="the transition graph" /> : <Loading label="Loading the transition graph" />}
            <ChartFoot meta={t.meta} />
          </div>
        )}
        {view === "ribbon" && <ChartFoot meta={g.meta} />}
      </section>

      <hr className="rule" />

      <section className="section" aria-labelledby="wf-h">
        <div className="section__head">
          <h2 id="wf-h" className="section__title">What the time was spent on</h2>
          <p className="section__sub">Biggest first. Each bar starts where the one above ended. Whiskers are 95% intervals from a bootstrap over people.</p>
        </div>
        <div className="chart chart--wide">
          <Waterfall steps={data.waterfall} totalCi={data.total_gap_ci} />
          <ChartFoot meta={g.meta} />
        </div>
      </section>

      <hr className="rule" />

      <Controls data={data} meta={g.meta} />
    </div>
  );
}

function RibbonView({ data }: { data: GenomeData }) {
  const cols = useMemo(() => layoutRibbon(data, 1000).columns, [data]);
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

  const caption = active != null && cols[active]
    ? describeColumn(cols[active], active, cols.length)
    : "Drag the slider, press Play, or hover a step to compare the two traces one step at a time.";

  return (
    <div className="stack">
      <div className="chart chart--wide">
        <Ribbon genome={data} active={active} onActive={setHover} />
      </div>
      <div className="scrub">
        <div className="scrub__row">
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => { if (!playing && (scrub == null || scrub >= cols.length - 1)) setScrub(-1 + 0); setPlaying((p) => !p); }} aria-pressed={playing}>
            {playing ? "Pause" : "Play"}
          </button>
          <label className="u-sr-only" htmlFor="scrub">Step through the two traces</label>
          <input id="scrub" type="range" min={0} max={cols.length - 1} step={1} value={scrub ?? 0}
            onChange={(e) => { setPlaying(false); setScrub(Number(e.target.value)); }}
            aria-valuetext={caption} />
        </div>
        <p className="scrub__caption" aria-live="polite">{caption}</p>
      </div>
      <ul className="legend" aria-label="How to read the ribbon">
        <LegendItem swatch={<span className="sw sw--expert" />}>Expert step</LegendItem>
        <LegendItem swatch={<span className="sw sw--novice" />}>Novice step</LegendItem>
        <LegendItem swatch={<span className="sw sw--hatch sw--muted" />}>Hatched: this person did not do the step</LegendItem>
        <LegendItem swatch={<span className="sw sw--bad" />}>Red: seconds lost in that column</LegendItem>
        <LegendItem swatch={<span className="sw sw--muted" />}>Column width: the longer of the two durations</LegendItem>
      </ul>
      <details className="details-lite">
        <summary>See the same ribbon as a table</summary>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Step</th><th>Expert</th><th>Novice</th><th className="num">Lost</th></tr></thead>
            <tbody>
              {cols.map((c, i) => (
                <tr key={i}>
                  <td className="num">{i + 1}</td>
                  <td>{c.expert ? `${cogLabel(c.expert.cog)}, ${Math.round(c.expert.seconds)} s` : "no step"}</td>
                  <td>{c.novice ? `${cogLabel(c.novice.cog)}, ${Math.round(c.novice.seconds)} s` : "skipped"}</td>
                  <td className="num">{Math.round(c.lost)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function Controls({ data, meta }: { data: GenomeData; meta: ReturnType<typeof useLoad<GenomeData>>["meta"] }) {
  const { placebo, null: nul } = data.controls;
  const zero = (ci: [number, number]) => ci[0] <= 0 && ci[1] >= 0;
  const ok = zero(placebo.ci) && zero(nul.ci);
  const lo = Math.min(-40, placebo.ci[0], nul.ci[0]);
  return (
    <section className="section" aria-labelledby="ctl-h">
      <div className="section__head">
        <h2 id="ctl-h" className="section__title">Does the method invent gaps?</h2>
        <p className="section__sub controls__lede">
          {ok
            ? <>Expert against expert, and shuffled labels, both show about zero. Their intervals include 0, so the ribbon is not inventing the gap.</>
            : <>A control is off zero. Do not trust the ribbon until this is explained.</>}
        </p>
      </div>
      <div className="chart chart--wide">
        <DotWhisker
          unit="seconds of gap"
          reference={0}
          refLabel="0"
          domain={[lo, data.total_gap_ci[1] + 20]}
          aria={`Controls. Real gap ${signed(data.total_gap_s)} seconds, interval ${fmtInterval(data.total_gap_ci)}. Placebo ${signed(placebo.gap_s, 1)}, interval ${fmtInterval(placebo.ci, 1)}. Null ${signed(nul.gap_s, 1)}, interval ${fmtInterval(nul.ci, 1)}.`}
          rows={[
            { label: "Novice against expert", value: data.total_gap_s, ci: data.total_gap_ci, emphasis: "real" },
            { label: "Expert against expert (placebo)", value: placebo.gap_s, ci: placebo.ci },
            { label: "Shuffled labels (null)", value: nul.gap_s, ci: nul.ci },
          ]}
        />
        <ChartFoot meta={meta} />
      </div>
    </section>
  );
}
