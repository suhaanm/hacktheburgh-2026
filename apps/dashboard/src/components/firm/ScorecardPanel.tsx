import { useMemo, useState, type ReactNode } from "react";
import { api } from "../../api";
import { useLoad, type LoadState } from "../../hooks";
import type { AnalyticMeta, EvalReport } from "../../types";
import { ChartFoot, EmptyState, ErrorState, ExampleBadge, Loading, Note, OriginBadge, SourceNote, workerOriginLabel } from "../common";
import { Hint } from "../Hint";
import { Details, fitItems } from "../ui";
import exampleV2 from "../../fixtures/predictions-mlv2.json";
import { Reliability } from "./Reliability";
import { ScoreChart, TteChart, type ScoreRowSpec } from "./ScoreRows";
import {
  CLOSE_POINTS, THIN_N, baselineShort, binReadout, budgetWords, fmtEst, fmtPctEst, readScorecard, reliabilityLine, summariseBins, verdictWord,
  type CardMeta, type MetricPanel, type Scorecard, type ScorecardRead,
} from "./scorecard";
import "./scorecard.css";

const pc = (x: number): string => `${Math.round(x * 100)}%`;

/** Load the report and read the scorecard from it. Example data (the engine is off) may borrow the example v2 block; live data never does. */
export function useScorecard(): { load: LoadState<EvalReport>; read: ScorecardRead | null } {
  const load = useLoad<EvalReport>(() => api.evalReport(), []);
  const read = useMemo(() => (load.data ? readScorecard(load.data, load.source === "demo" ? exampleV2 : undefined) : null), [load.data, load.source]);
  return { load, read };
}

/** The scorecard with no page header, for the Firm screen's Forecasts tab. It loads itself. */
export function ScorecardPanel() {
  const { load, read } = useScorecard();
  return <ScorecardView load={load} read={read} audience="admin" />;
}

const cardMeta = (m: CardMeta): AnalyticMeta | null =>
  m.n === null ? null : { origin: m.origin, n: m.n, n_unit: m.nUnit, split: m.split, interval_level: m.level, note: null, generated_at: "" };

const rowsOf = (p: MetricPanel): ScoreRowSpec[] => p.rows.map((r) => ({ id: r.id, label: r.label, est: r.est, kind: r.ours ? "ours" : "other" }));

export function ScorecardView({ load, read, audience = "admin" }: { load: LoadState<EvalReport>; read: ScorecardRead | null; audience?: "worker" | "admin" }) {
  if (load.status === "error" && !load.data) return <ErrorState error={load.error} retry={load.reload} what="the forecast scorecard" />;
  if (!read) return <Loading label="Loading the forecast scorecard" />;
  if (read.kind === "unavailable") {
    const title = read.status === "failed" ? `${read.what} did not run` : read.status === "missing" ? "There is no forecast scorecard yet" : `${read.what} has no result yet`;
    return (
      <div className="stack">
        <EmptyState title={title} body={`${read.reason}${read.status === "missing" ? "" : " This page fills in on its own when the evaluation has run."}`} />
        <SourceNote why={load.why} />
      </div>
    );
  }
  return <Ready card={read.card} load={load} audience={audience} />;
}

function Ready({ card, load, audience }: { card: Scorecard; load: LoadState<EvalReport>; audience: "worker" | "admin" }) {
  const [sel, setSel] = useState<number | null>(null);
  const level = Math.round(card.meta.level * 100);
  const summary = useMemo(() => summariseBins(card.bins), [card.bins]);
  const selBin = sel != null ? card.bins[sel] : null;
  const meta = cardMeta(card.meta);
  const busy = load.status === "loading";
  // A worker's screen keeps the reliability diagram and the false alarms open (D45: detail behind a disclosure). An Admin tab prints the comparison; only time to progress folds.
  const fold = (title: string, node: ReactNode, always = false) => (audience === "worker" || always ? <Details summary={title} wide>{node}</Details> : node);

  return (
    <div className="sc" aria-busy={busy}>
      <section className="hero sc-hero" aria-labelledby="sc-hero-h">
        <div className="sc-head">
          <div className="sc-head__text">
            <h2 id="sc-hero-h" className="section__title">Does the forecast mean what it says?</h2>
          </div>
          <div className="sc-head__meta">
            {audience === "admin"
              // On the Firm screen the one origin pill is in the screen head; the origin of these forecasts is printed as words beside the version.
              ? <span className="u-muted">{workerOriginLabel(card.meta.origin)}{load.why ? ", example numbers" : ""}</span>
              : load.why ? <ExampleBadge why={load.why} /> : <OriginBadge meta={meta ?? { origin: card.meta.origin, n: 0, n_unit: card.meta.nUnit, split: null, interval_level: card.meta.level, note: null, generated_at: "" }} always label={workerOriginLabel(card.meta.origin)} />}
            <span className="u-muted">Forecast {card.version}</span>
            <Hint label="About the forecast version">{card.version === "v1" ? "This is the forecast the coach uses today." : "This is the accepted v2 forecast."}</Hint>
            {card.defaultNote && <><span className="u-muted">v2 candidate: {verdictWord(card.verdict)}</span><Hint label="About the v2 candidate">{card.defaultNote}</Hint></>}
          </div>
        </div>

        {card.bins.length === 0 ? (
          <EmptyState title="No calibration bands in the report" body="The report has the scores but not the bands the diagram needs. Run make eval to write them." />
        ) : (
          <div className="sc-hero__grid">
            <figure className="chart sc-fig">
              <Reliability bins={card.bins} levelPct={level} selected={sel} onSelect={setSel} />
              <ChartFoot
                meta={meta} brief badge={false} variant={audience === "worker" ? "about" : "full"}
                extra={<>
                  {card.ece && <span>mean gap (ECE): <b>{fmtEst(card.ece)}</b></span>}
                  {audience === "admin" && <span>not validated on real people</span>}
                </>}
              />
            </figure>
            <div className="sc-read">
              <p className="sc-claim">{reliabilityLine(summary)}</p>
              <p className="sc-readout" aria-live="polite">
                {selBin ? binReadout(selBin, level) : <span className="u-muted">Hover the chart, or focus it and use the arrow keys, to read a band.</span>}
              </p>
              <details className="details-lite">
                <summary>Key to the diagram</summary>
                <p className="note">Each dot is a band of forecasts. On the dashed line, the forecast is exactly right.</p>
                <ul className="legend sc-key" aria-label="How to read the reliability diagram">
                  <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><circle className="sc-dot" cx="11" cy="7" r="4.5" /></svg>A band with {THIN_N} or more cases</li>
                  <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><circle className="sc-dot sc-dot--thin" cx="11" cy="7" r="4.5" /></svg>Hollow: a thin band, fewer than {THIN_N} cases</li>
                  <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><g className="sc-whisker"><line x1="11" x2="11" y1="1" y2="13" /><line x1="7" x2="15" y1="1" y2="1" /><line x1="7" x2="15" y1="13" y2="13" /></g></svg>{level}% interval on how often someone was stuck</li>
                  <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><line className="sc-diag" x1="1" y1="13" x2="21" y2="1" /></svg>Dashed line: the forecast is exactly right</li>
                  <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><rect className="sc-close" x="1" y="3" width="20" height="8" /></svg>Shaded band: within {Math.round(CLOSE_POINTS * 100)} points of right</li>
                  <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><rect className="sc-bar" x="5" y="5" width="12" height="9" /></svg>Strip: how many cases each band has</li>
                </ul>
              </details>
            </div>
          </div>
        )}

        {card.defaultNote && <Note>{card.defaultNote}</Note>}
        <SourceNote why={load.why} />
      </section>

      {card.panels.length > 0 && fold("Against two simple baselines",
        <section className="section" aria-labelledby="sc-base-h">
          <div className="sc-sechead">
            <h2 id="sc-base-h" className="section__title">Against two simple baselines</h2>
            <p className="section__sub">{baselineShort(card.panels).line}{baselineShort(card.panels).detail && <Hint label="About the baseline comparison">{baselineShort(card.panels).detail}</Hint>}</p>
          </div>
          <div className="cols-2">
            {card.panels.map((p) => (
              <figure key={p.key} className="chart">
                <div className="sc-titlerow">
                  <h3 className="chart__title">{p.title}</h3>
                  <Hint label={`What ${p.title} means`}>
                    {p.key === "log_loss"
                      ? "How surprised the forecast was by what happened. A confident wrong forecast costs a lot. Lower is better."
                      : "The average squared miss between the forecast and what happened, from 0 to 1. Lower is better."}
                  </Hint>
                </div>
                <ScoreChart title={p.title} rows={rowsOf(p)} />
              </figure>
            ))}
          </div>
          <ChartFoot meta={meta} brief badge={false} extra={<span>axes do not start at zero</span>} />
          <ul className="legend" aria-label="How to read the rows">
            <li className="legend__item"><svg width="14" height="14" aria-hidden="true"><circle className="sc-dot" cx="7" cy="7" r="5" /></svg>Filled dot: our forecast</li>
            <li className="legend__item"><svg width="14" height="14" aria-hidden="true"><path className="sc-diamond" d="M 7 1 l 6 6 l -6 6 l -6 -6 z" /></svg>Hollow diamond: a baseline</li>
            <li className="legend__item"><svg width="22" height="14" aria-hidden="true"><g className="sc-whisker"><line x1="1" x2="21" y1="7" y2="7" /><line x1="1" x2="1" y1="2" y2="12" /><line x1="21" x2="21" y1="2" y2="12" /></g></svg>Line: {level}% interval</li>
          </ul>
          {card.candidate && <CandidateBlock card={card} />}
        </section>
      )}

      <section className="section" aria-labelledby="sc-alarm-h">
        <div className="sc-titlerow sc-titlerow--section">
          <h2 id="sc-alarm-h" className="section__title">False alarms</h2>
          <Hint label="What a false alarm is">A time the coach would have spoken although the person was not stuck. The budget is a design choice, not a measured limit for real workers.</Hint>
        </div>
        <Alarms card={card} meta={meta} level={level} />
      </section>

      {card.tte && fold("Time to progress", <TteSection card={card} />, true)}

      <section className="section sc-notes" aria-labelledby="sc-notes-h">
        <h2 id="sc-notes-h" className="u-sr-only">Notes on how to read this</h2>
        <details className="details-lite">
          <summary>What a forecast is for</summary>
          <p className="t-prose">The coach speaks only when the chance of being stuck is high enough, and stays quiet otherwise. The forecast never decides alone: code applies a dignity gate that also limits how often the coach speaks.</p>
        </details>
        <details className="details-lite">
          <summary>What this does not show</summary>
          <SoftList items={[
            `n = ${card.meta.n ?? "not reported"} ${card.meta.nUnit}. ${card.meta.origin === "real" ? "Measured from real people." : "Generated people from our own generator, not real people."}${card.meta.split ? ` Split: ${card.meta.split}.` : ""}`,
            "Not validated on real people. The live study with teammates has not been run.",
            "The label is no progress in the next 60 seconds. That is not the same as confusion: fast thinking and slow typing both look stuck.",
            ...card.limits,
            ...card.caveats,
          ]} />
        </details>
        <details className="details-lite">
          <summary>How this was scored</summary>
          <SoftList items={[
            ...(card.basis ? [card.basis] : []),
            ...(card.binsLabel ? [`Bands: ${card.binsLabel}.`] : []),
            "The interval on each dot is a Wilson interval from that band's own count. Bands are treated as independent, so these intervals are narrower than the spread between people.",
            ...(card.intervalNote ? [card.intervalNote] : []),
            ...(card.v2Status ? [`Models v2: ${card.v2Status.status === "pending" ? "no result yet" : card.v2Status.status.replace("_", " ")}${card.v2Status.reason ? ` (${card.v2Status.reason})` : ""}.`] : []),
          ]} />
        </details>
      </section>
    </div>
  );
}

/** A short list: the lines that fit in about fifty words, then the rest behind one closed "More". */
function SoftList({ items }: { items: string[] }) {
  const { shown, rest } = fitItems(items, 50);
  return (
    <>
      <ul className="plain-list sc-list">{shown.map((t) => <li key={t}>{t}</li>)}</ul>
      {rest.length > 0 && <Details summary={`More (${rest.length})`}><ul className="plain-list sc-list">{rest.map((t) => <li key={t}>{t}</li>)}</ul></Details>}
    </>
  );
}

function Alarms({ card, meta, level }: { card: Scorecard; meta: AnalyticMeta | null; level: number }) {
  const a = card.alarms;
  const words = budgetWords(a);
  const rows: ScoreRowSpec[] = [{ id: "rate", label: "False alarms per hour", est: a.rate, kind: "ours" }];
  const [open, setOpen] = useState(false);
  return (
    <div className="stack">
      <div className="sc-verdict">
        <span className="pill pill--state" data-tone={a.verdict === "over" ? "bad" : a.verdict === "within" ? "good" : "muted"}>
          <span className="pill__dot" aria-hidden="true" />
          {words.title}
        </span>
        <span className="chart__sub">{words.detail}</span>
      </div>
      {a.rate ? (
        <figure className="chart">
          <ScoreChart title="False alarms per hour against the budget" rows={rows} digits={2} zero reference={a.budget !== null ? { value: a.budget, label: `budget ${a.budget.toFixed(1)} an hour` } : undefined} />
          <ChartFoot meta={meta} brief badge={false} extra={<span>axis starts at zero</span>} />
        </figure>
      ) : <Note>The report gives no false-alarm rate.</Note>}
      {a.detection && (
        <p className="t-prose">It flags {fmtPctEst(a.detection)} of stuck spells. The rest it misses, by design: a quiet coach is better than a nagging one.</p>
      )}
      {card.perPerson.length > 0 && (
        <details className="details-lite" open={open} onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
          <summary>By person ({card.perPerson.length} {card.meta.nUnit})</summary>
          <table className="table sc-table">
            <caption className="u-sr-only">False alarms per hour and share of stuck spells flagged, for each generated person. Not a ranking.</caption>
            <thead><tr><th>Persona</th><th className="num">False alarms an hour</th><th className="num">Spells flagged</th><th className="num">Bands scored</th></tr></thead>
            <tbody>
              {card.perPerson.slice(0, 7).map((p) => (
                <tr key={p.id}>
                  <td>{p.label}</td>
                  <td className="num">{p.falseAlarms === null ? "not reported" : p.falseAlarms.toFixed(2)}</td>
                  <td className="num">{p.detection === null ? "not reported" : pc(p.detection)}</td>
                  <td className="num">{p.bins === null ? "n/a" : p.bins.toLocaleString("en-GB")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">Listed by name, not ranked. With {card.perPerson.length} people, this spread is the honest uncertainty. The {level}% intervals above only resample episodes.</p>
        </details>
      )}
    </div>
  );
}

function CandidateBlock({ card }: { card: Scorecard }) {
  const c = card.candidate;
  if (!c) return null;
  const meta = cardMeta(c.meta);
  const pair = (label: string, a: { candidate: ScoreRowSpec["est"]; v1: ScoreRowSpec["est"] }): ScoreRowSpec[] => [
    { id: `v1-${label}`, label: "Forecast v1, same pool", est: a.v1, kind: "other" },
    { id: `c-${label}`, label: "v2 candidate (not accepted)", est: a.candidate, kind: "candidate" },
  ];
  return (
    <details className="details-lite sc-cand">
      <summary>The v2 candidate, on its own pool</summary>
      <div className="stack">
        <p className="note">{c.label}, scored on {c.meta.pool ?? "its own pool"}{c.meta.n !== null ? ` (${c.meta.n} ${c.meta.nUnit})` : ""}. v1 is scored on the same pool, so these two can share an axis. Do not compare them with the rows above.</p>
        <div className="cols-2">
          <figure className="chart"><h3 className="chart__title">Log loss</h3><ScoreChart title="Log loss, candidate against v1" rows={pair("ll", c.logLoss)} /><ChartFoot meta={meta} brief badge={false} /></figure>
          <figure className="chart"><h3 className="chart__title">Brier score</h3><ScoreChart title="Brier score, candidate against v1" rows={pair("br", c.brier)} /><ChartFoot meta={meta} brief badge={false} /></figure>
        </div>
        <ul className="plain-list sc-list">
          {(c.falseAlarms.candidate || c.falseAlarms.v1) && <li>False alarms an hour: candidate {fmtEst(c.falseAlarms.candidate, 2)}, v1 {fmtEst(c.falseAlarms.v1, 2)}.</li>}
          {(c.detection.candidate || c.detection.v1) && <li>Spells flagged: candidate {fmtPctEst(c.detection.candidate)}, v1 {fmtPctEst(c.detection.v1)}.</li>}
        </ul>
      </div>
    </details>
  );
}

function TteSection({ card }: { card: Scorecard }) {
  const t = card.tte;
  if (!t) return null;
  // The time-to-progress head is scored on the v2 pool, not on v1's four personas: its footer says so.
  const poolMeta = card.v2Meta ?? card.meta;
  const meta = cardMeta(poolMeta);
  const rows: ScoreRowSpec[] = [];
  if (t.cIndex) rows.push({ id: "c", label: t.candidate ? "Time-to-progress head (candidate)" : "Time-to-progress head", est: t.cIndex, kind: t.candidate ? "candidate" : "ours" });
  if (t.baselineC) rows.push({ id: "b", label: "Time since progress only", est: t.baselineC, kind: "other" });
  const help: ReactNode = t.runsHigh === true
    ? "Its minutes run higher than what happened in every group. Use it to rank spells, not as a clock."
    : "How well it orders stuck spells from short to long, and how close its minutes are.";
  return (
    <section className="section" aria-labelledby="sc-tte-h">
      <div className="sc-sechead">
        <h2 id="sc-tte-h" className="section__title">Time to progress</h2>
        <p className="section__sub">{help}</p>
      </div>
      <div className="cols-2">
        {rows.length > 0 && (
          <figure className="chart">
            <div className="sc-titlerow">
              <h3 className="chart__title">Ranking quality</h3>
              <Hint label="What concordance means">Pick two spells at random: how often does the head say the longer one will last longer? 0.5 is a coin toss, 1 is always right.</Hint>
            </div>
            <ScoreChart title="Ranking quality (concordance)" rows={rows} digits={2} reference={{ value: 0.5, label: "chance" }} />
          </figure>
        )}
        {t.pairs.length > 0 && (
          <figure className="chart">
            <div className="sc-titlerow"><h3 className="chart__title">Predicted and observed minutes</h3></div>
            <TteChart pairs={t.pairs} />
            <Details summary="Key">
              <ul className="legend" aria-label="How to read the bars">
                <li className="legend__item"><svg width="14" height="12" aria-hidden="true"><rect className="sc-tte sc-tte--pred" x="1" y="1" width="12" height="10" /></svg>Outline: predicted</li>
                <li className="legend__item"><svg width="14" height="12" aria-hidden="true"><rect className="sc-tte sc-tte--obs" x="1" y="1" width="12" height="10" /></svg>Solid: observed (Kaplan-Meier)</li>
                <li className="legend__item">Groups run from the shortest predicted wait to the longest</li>
              </ul>
            </Details>
          </figure>
        )}
      </div>
      <ChartFoot meta={meta} brief badge={false} extra={<>{poolMeta.pool && <span>pool: <b>{poolMeta.pool}</b></span>}{t.cIndex && <span>ranking axis does not start at zero</span>}{t.meanExpected !== null && t.kmMean !== null && <span>mean predicted <b>{t.meanExpected.toFixed(2)}</b> min, observed <b>{t.kmMean.toFixed(2)}</b> min</span>}</>} />
    </section>
  );
}
