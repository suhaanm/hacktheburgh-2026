import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { useRoute } from "../router";
import { ChartFoot, ErrorState, LegendItem, Loading, OriginBadge, PageHead, workerOriginLabel } from "../components/common";
import { Ribbon } from "../components/Ribbon";
import { Waterfall } from "../components/Waterfall";
import { Explain } from "../components/Explain";
import { Details } from "../components/ui";
import { Hint } from "../components/Hint";
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
        hero
        title={`Novices lose about ${fmtDuration(total)} per case`}
        lede={<>{"Average over all novices."}<Hint label="About this average">{`95% interval ${fmtDuration(data.total_gap_ci[0])} to ${fmtDuration(data.total_gap_ci[1])}.${data.person_gap_s != null ? ` The case below: ${data.person}, ${fmtDuration(data.person_gap_s)} lost.` : ""}`}</Hint></>}
        aside={<OriginBadge meta={g.meta} label={g.meta ? workerOriginLabel(g.meta.origin) : undefined} />}
      />

      <section className="hero" aria-labelledby="hero-h">
        <div className="hero__bar">
          <h2 id="hero-h" className="u-sr-only">{view === "ribbon" ? "Work ribbon" : "Transition graph"}</h2>
          <div className="segmented" role="group" aria-label="View">
            <button type="button" aria-pressed={view === "ribbon"} onClick={() => setView("ribbon")}>Work ribbon</button>
            <button type="button" aria-pressed={view === "graph"} onClick={() => setView("graph")}>Transition graph</button>
          </div>
        </div>

        {view === "ribbon" ? <RibbonView data={data} meta={g.meta} reference={reference} setReference={setReference} /> : (
          <div className="stack">
            {t.data ? <TransitionGraph data={t.data} /> : t.status === "error" ? <ErrorState error={t.error} retry={t.reload} what="the transition graph" /> : <Loading label="Loading the transition graph" />}
            <ChartFoot variant="about" meta={t.meta} badge={false} />
          </div>
        )}
      </section>

      <hr className="rule" />

      <section className="section" aria-labelledby="wf-h">
        <div className="section__head">
          <h2 id="wf-h" className="section__title">Where the time went</h2>
        </div>
        <div className="chart chart--wide">
          <Waterfall steps={data.waterfall} totalCi={data.total_gap_ci} />
          <ChartFoot variant="about" meta={g.meta} badge={false} extra={<>each bar starts where the one above ended; whiskers are a bootstrap over people</>} />
        </div>
      </section>

      <hr className="rule" />

      <Controls data={data} meta={g.meta} />

      <hr className="rule" />

      <Explain person={person} />
    </div>
  );
}

function RibbonView({ data, meta, reference, setReference }: { data: GenomeData; meta: ReturnType<typeof useLoad<GenomeData>>["meta"]; reference: "nearest_expert" | "consensus"; setReference: (r: "nearest_expert" | "consensus") => void }) {
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

  const consequences = data.consequences ?? [];
  const consequenceFor = (cog: string | undefined) => consequences.find((c) => cog && c.step.toLowerCase().replace(/[ -]/g, "_") === cog.toLowerCase());
  const sentence = (c: NonNullable<GenomeData["consequences"]>[number]) => {
    const wrong = Math.round(c.p_error * c.n);
    return `Skipping this step gives a wrong answer on ${wrong} of ${c.n} households, by about £${Math.round(c.mean_error_gbp)}${c.source ? ` (${c.source})` : ""}.`;
  };
  const activeCol = active != null ? cols[active] : null;
  const caption = activeCol
    ? `${describeColumn(activeCol, active as number, cols.length)}${activeCol.missing === "novice" && consequenceFor(activeCol.expert?.cog) ? ` ${sentence(consequenceFor(activeCol.expert?.cog)!)}` : ""}`
    : "";

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
      <Details summary="Details" wide>
        <div className="stack">
          <ul className="legend" aria-label="How to read the ribbon">
            <LegendItem swatch={<span className="sw sw--expert" />}>Expert step</LegendItem>
            <LegendItem swatch={<span className="sw sw--novice" />}>Novice step</LegendItem>
            <LegendItem swatch={<span className="sw sw--hatch sw--muted" />}>Hatched: a step only one of them did (a skipped step counts as time saved)</LegendItem>
            <LegendItem swatch={<span className="sw sw--bad" />}>Red: seconds lost in that column</LegendItem>
            <LegendItem swatch={<span className="sw sw--muted" />}>Column width: the longer of the two durations</LegendItem>
          </ul>
          <div className="stack">
            <p className="note">Nearest expert is the closest single trace; consensus blends all experts.</p>
            <div className="segmented" role="group" aria-label="Reference">
              <button type="button" aria-pressed={reference === "nearest_expert"} onClick={() => setReference("nearest_expert")}>Nearest expert</button>
              <button type="button" aria-pressed={reference === "consensus"} onClick={() => setReference("consensus")}>Consensus</button>
            </div>
          </div>
          <p className="note">Skipping a step shows as time saved here. It often costs more later, and the waterfall counts that rework separately when it happened.</p>
          {consequences.length > 0 && <ul className="plain-list">{consequences.map((c) => <li key={c.step} className="note"><b>{cogLabel(c.step)}:</b> {sentence(c)}</li>)}</ul>}
      <Details summary="As a table" wide>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Step</th><th>Expert</th><th>Novice</th><th className="num">Lost</th></tr></thead>
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

function Controls({ data, meta }: { data: GenomeData; meta: ReturnType<typeof useLoad<GenomeData>>["meta"] }) {
  const { placebo, null: nul } = data.controls;
  const zero = (ci: [number, number]) => ci[0] <= 0 && ci[1] >= 0;
  const ok = zero(placebo.ci) && zero(nul.ci);
  const wide = Math.abs(nul.gap_s) > 0.1 * data.total_gap_s || Math.abs(placebo.gap_s) > 0.1 * data.total_gap_s;
  const lo = Math.min(-40, placebo.ci[0], nul.ci[0]);
  return (
    <section className="section" aria-labelledby="ctl-h">
      <div className="section__head">
        <h2 id="ctl-h" className="section__title">Does the method invent gaps?</h2>
        <p className="section__sub controls__lede">
          {ok
            ? <>Expert against expert {signed(placebo.gap_s)} s, shuffled labels {signed(nul.gap_s)} s: both include 0.{wide ? " The shuffled-label interval is wide, so read the real gap with that in mind." : " The ribbon is not inventing the gap."}</>
            : <>A control is off zero: expert against expert {signed(placebo.gap_s)} s, shuffled labels {signed(nul.gap_s)} s. Do not trust the ribbon until this is explained.</>}
        </p>
      </div>
      <Details summary="The three bars" wide>
      <div className="chart chart--wide">
        <DotWhisker
          unit="seconds of gap"
          reference={0}
          refLabel="0"
          domain={[lo, Math.max(data.total_gap_ci[1], nul.ci[1], placebo.ci[1]) + 20]}
          aria={`Controls. Real gap ${signed(data.total_gap_s)} seconds, interval ${fmtInterval(data.total_gap_ci)}. Placebo ${signed(placebo.gap_s, 1)}, interval ${fmtInterval(placebo.ci, 1)}. Null ${signed(nul.gap_s, 1)}, interval ${fmtInterval(nul.ci, 1)}.`}
          rows={[
            { label: "Novice against expert", value: data.total_gap_s, ci: data.total_gap_ci, emphasis: "real" },
            { label: "Expert against expert (placebo)", value: placebo.gap_s, ci: placebo.ci },
            { label: "Shuffled labels (null)", value: nul.gap_s, ci: nul.ci },
          ]}
        />
        <ChartFoot variant="about" meta={meta} badge={false} />
      </div>
      </Details>
    </section>
  );
}
