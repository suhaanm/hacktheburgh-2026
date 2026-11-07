import type { ReactNode } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, Loading, PageHead, Range } from "../components/common";
import { DotWhisker, type DwRow } from "../components/DotWhisker";
import { Reliability, RiskCoverage, type RcPoint, type RelPoint } from "../components/EvidenceCharts";
import { fmtInterval, fmtPct, fmtPctInterval, signed } from "../lib/format";
import type { AnalyticMeta, EvalReport, Interval, Limitation } from "../types";

/* The contract fixes the section names and keys (docs/API_CONTRACT.md, "Additions"). Read defensively: a section may be missing,
   or a stub { status: "pending" | "not_run" | "failed", reason, meta }, and a stub never prints defaults. */
type Sec = { meta?: AnalyticMeta; status?: string; reason?: string } & Record<string, unknown>;
const sec = (r: EvalReport, k: string): Sec | null => ((r.sections as Record<string, unknown>)[k] as Sec | undefined) ?? null;
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const stubOf = (s: Sec | null): Sec | null => (s && typeof s.status === "string" && ["pending", "not_run", "failed"].includes(s.status) ? s : null);
const ivl = (v: unknown, fallback: number): Interval => (Array.isArray(v) && v.length === 2 && v.every(isNum) ? (v as Interval) : [fallback, fallback]);
const dashed = (v: unknown, f: (n: number) => string) => (isNum(v) ? f(v) : "not reported");

function Block({ id, kicker, claim, children }: { id: string; kicker: string; claim: ReactNode; children?: ReactNode }) {
  return (
    <section className="ev-block" id={id} aria-labelledby={`${id}-h`}>
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <p className="t-label">{kicker}</p>
        <h2 className="ev-claim" id={`${id}-h`}>{claim}</h2>
      </div>
      {children}
    </section>
  );
}

/** A section that has not produced a result says why, in plain words. It never shows a chart of nothing. */
function StubState({ s, what }: { s: Sec | null; what: string }) {
  if (!s) return <EmptyState title={`${what} is not in the report`} body="Run make eval to write evals/report.json. This block fills in on its own." />;
  const title = s.status === "failed" ? `${what} did not run` : s.status === "not_run" ? `${what} has not run yet` : `${what} is still being worked out`;
  const body = s.reason || "No reason was given.";
  return s.status === "failed"
    ? <div className="state state--error" role="alert"><span className="state__mark" aria-hidden="true" /><h3 className="state__title">{title}</h3><p className="state__body">{body}</p></div>
    : <EmptyState title={title} body={body} />;
}

/** Wrap a section: stub or missing gives the reason, otherwise the real block. */
function Guard({ id, kicker, what, s, children }: { id: string; kicker: string; what: string; s: Sec | null; children: (s: Sec) => ReactNode }) {
  const stub = stubOf(s);
  if (!s || stub) return <Block id={id} kicker={kicker} claim={what}><StubState s={s} what={what} /></Block>;
  return <>{children(s)}</>;
}

const NAV: [string, string][] = [["hazard", "Warning"], ["routing", "Review"], ["controls", "Controls"], ["ope", "Off-policy"], ["redteam", "Injection"], ["ski", "Ski rental"], ["deficits", "Deficits"], ["presence", "Presence"], ["agent", "Agent claims"], ["study", "Live study"], ["limits", "Limits"]];

export default function Evidence() {
  const r = useLoad(() => api.evalReport(), []);
  if (r.status === "error" && !r.data) return <div className="page"><ErrorState error={r.error} retry={r.reload} what="the evidence report" /></div>;
  if (!r.data) return <div className="page"><Loading label="Loading the evidence report" /></div>;
  const rep = r.data;
  const limits = arr<Limitation>(rep.sections.limitations);
  const study = sec(rep, "study");
  const studyRan = !!study && !stubOf(study) && isNum(study.meta?.n) && (study.meta?.n ?? 0) > 0;
  const anySynthetic = Object.entries(rep.sections).some(([k, v]) => k !== "limitations" && (v as Sec)?.meta?.origin && (v as Sec).meta!.origin !== "real");
  const go = (id: string) => (e: { preventDefault: () => void }) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); };

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow={`Evidence · generated ${new Date(rep.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}${rep.mock ? " · mock mode" : ""}`}
        title="What we can show, and what we cannot"
        lede={<>{anySynthetic ? "Most numbers here come from synthetic apprentices and personas, and each one says so. " : ""}{studyRan ? `The live study has n = ${study!.meta!.n}. ` : "The live study has not run yet, so no human results are shown. "}Every chart prints its n, its split and its 95% interval. <a href="#limits" onClick={go("limits")}>{limits.length} limits are listed at the end.</a></>}
        aside={<nav className="row" aria-label="On this page" style={{ gap: "var(--space-2) var(--space-4)", maxWidth: 440 }}>{NAV.map(([id, t]) => <a key={id} className="t-data" href={`#${id}`} onClick={go(id)}>{t}</a>)}</nav>}
      />
      <div className="ev">
        <Hazard rep={rep} />
        <Routing rep={rep} />
        <Controls rep={rep} />
        <Ope rep={rep} />
        <Redteam rep={rep} />
        <Ski rep={rep} />
        <Deficits rep={rep} />
        <PresenceBlock rep={rep} />
        <Claims rep={rep} />
        <Study rep={rep} />
        <Limits items={limits} />
      </div>
    </div>
  );
}

/* -- Stuck warning calibration ------------------------------------------------------------------ */
function Hazard({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="hazard" kicker="Is the stuck warning calibrated?" what="The stuck warning" s={sec(rep, "hazard")}>
      {(s) => {
        const d = ((s as Record<string, unknown>).data ?? s) as { model?: { log_loss: number; brier: number; ece: number; ci_log_loss: Interval }; baselines?: Record<string, { log_loss: number; brier: number; ece: number }>; calibration?: RelPoint[]; false_alarms_per_hour?: number; split?: string; caveats?: string[] };
        const m = d.model, tsp = d.baselines?.time_since_progress, br = d.baselines?.base_rate;
        const better = m && tsp && br && m.log_loss < tsp.log_loss && m.log_loss < br.log_loss;
        const caveats = arr<string>(d.caveats);
        return (
          <Block id="hazard" kicker="Is the stuck warning calibrated?" claim={m && tsp && br ? <>Log loss {m.log_loss.toFixed(2)}, against {tsp.log_loss.toFixed(2)} for time since progress and {br.log_loss.toFixed(2)} for the base rate{better ? ": better than both." : ": not better than both."}</> : "Stuck warning"}>
            <div className="ev-grid">
              <div className="chart"><Reliability points={arr<RelPoint>(d.calibration)} label="Stuck warning calibration" /><p className="ev-note">On the dashed diagonal means the warning says 40% and it happens 40% of the time. Dot area is the number of 30-second bins.</p></div>
              <div className="stack">
                {m && tsp && br && (
                  <div className="table-wrap"><table className="table">
                    <thead><tr><th>Model</th><th className="num">Log loss</th><th className="num">Brier</th><th className="num">ECE</th></tr></thead>
                    <tbody>
                      <tr><td><b>Stuck hazard</b></td><td className="num">{m.log_loss.toFixed(3)}</td><td className="num">{m.brier.toFixed(3)}</td><td className="num">{m.ece.toFixed(3)}</td></tr>
                      <tr><td>Time since progress</td><td className="num">{tsp.log_loss.toFixed(3)}</td><td className="num">{tsp.brier.toFixed(3)}</td><td className="num">{tsp.ece.toFixed(3)}</td></tr>
                      <tr><td>Base rate</td><td className="num">{br.log_loss.toFixed(3)}</td><td className="num">{br.brier.toFixed(3)}</td><td className="num">{br.ece.toFixed(3)}</td></tr>
                    </tbody></table></div>
                )}
                {m && <p className="ev-note">Log loss 95% interval {fmtInterval(m.ci_log_loss, 3)}. Lower is better in all three columns. A baseline can have a good ECE just because it says one number; log loss and Brier show whether it knows who is stuck.</p>}
                {caveats.length > 0 && (
                  <div className="stack" style={{ gap: "var(--space-1)" }}>
                    <span className="t-label">Caveats from the engine</span>
                    <ul className="plain-list">{caveats.map((c) => <li key={c} className="ev-note">{c}</li>)}</ul>
                  </div>
                )}
                {isNum(d.false_alarms_per_hour) && <div className="stat"><span className="stat__label">False alarms</span><span className="stat__value tabular">{d.false_alarms_per_hour.toFixed(1)}<span className="stat__unit">an hour</span></span></div>}
              </div>
            </div>
            <ChartFoot meta={s.meta ?? null} extra={d.split ? <span>held out: <b>{d.split}</b></span> : undefined} />
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Review routing: risk-coverage ---------------------------------------------------------------- */
function Routing({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="routing" kicker="Can we skip review safely?" what="Review routing" s={sec(rep, "routing")}>
      {(s) => {
        const alpha = isNum(s.alpha) ? s.alpha : 0.05, cov = isNum(s.chosen_coverage) ? s.chosen_coverage : 0, err = isNum(s.held_out_error) ? s.held_out_error : 0;
        const ci = ivl(s.held_out_ci, err);
        const under = err <= alpha, ciOver = ci[1] > alpha;
        return (
          <Block id="routing" kicker="Can we skip review safely?" claim={<>Auto-approve {fmtPct(cov)} of cases, send the rest to an expert. Held-out error {fmtPct(err, 1)}, target {fmtPct(alpha)}.</>}>
            <div className="ev-grid">
              <div className="chart"><RiskCoverage curve={arr<RcPoint>(s.curve)} alpha={alpha} chosen={cov} heldOut={{ value: err, ci }} /></div>
              <div className="stack">
                <div className="stat"><span className="stat__label">Held-out error at {fmtPct(cov)} coverage</span><span className="stat__value tabular">{fmtPct(err, 1)}</span><span className="stat__interval">95% interval {fmtPctInterval(ci[0], ci[1], 1)}</span></div>
                <p className="ev-note">{under ? "The point estimate is under the target." : "The point estimate is over the target."}{ciOver ? " The interval reaches above it, so we do not claim the target always holds." : ""} The bound was chosen on a calibration split and checked on a separate held-out split{typeof s.bound_held === "boolean" ? `: the engine reports it ${s.bound_held ? "held" : "did not hold"}` : ""}.</p>
                {isNum(s.expert_minutes_per_case) && <div className="stat"><span className="stat__label">Expert time</span><span className="stat__value tabular">{s.expert_minutes_per_case.toFixed(1)}<span className="stat__unit">min per case</span></span></div>}
              </div>
            </div>
            <ChartFoot meta={s.meta ?? null} extra={<span>band: 95% interval</span>} />
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Controls: does the method invent gaps? ---------------------------------------------------------- */
function Controls({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="controls" kicker="Does the method invent gaps?" what="The null and placebo controls" s={sec(rep, "null_placebo")}>
      {(s) => {
        const real = s.real as { gap_s: number; ci: Interval } | undefined, pl = s.placebo as { gap_s: number; ci: Interval } | undefined, nu = s.null as { gap_s: number; ci: Interval } | undefined;
        if (!real || !pl || !nu) return <Block id="controls" kicker="Does the method invent gaps?" claim="Controls"><StubState s={{ status: "pending", reason: "The report has the controls section but not all three gaps.", meta: s.meta }} what="The controls" /></Block>;
        return (
          <Block id="controls" kicker="Does the method invent gaps?" claim={<>Shuffled labels give {signed(nu.gap_s)} s {fmtInterval(nu.ci)}, against a real gap of {signed(real.gap_s)} s {fmtInterval(real.ci)}.</>}>
            <div className="chart chart--wide">
              <DotWhisker unit="seconds of gap" reference={0} refLabel="0" domain={[Math.min(-40, pl.ci[0], nu.ci[0]), Math.max(real.ci[1], nu.ci[1]) + 20]}
                aria={`Controls. Real gap ${signed(real.gap_s)} seconds. Placebo ${signed(pl.gap_s, 1)}. Null ${signed(nu.gap_s, 1)}.`}
                rows={[{ label: "Novice against expert", value: real.gap_s, ci: real.ci, emphasis: "real" }, { label: "Expert against expert (placebo)", value: pl.gap_s, ci: pl.ci }, { label: "Shuffled labels (null)", value: nu.gap_s, ci: nu.ci }]} />
              <p className="ev-note">Both control intervals include zero, but the shuffled-label interval is wide. That is a limit of this method on this much data, not something to hide.</p>
              <ChartFoot meta={s.meta ?? null} />
            </div>
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Off-policy recovery ------------------------------------------------------------------------------ */
function Ope({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="ope" kicker="Can we judge a coaching policy before using it?" what="Off-policy recovery" s={sec(rep, "ope")}>
      {(s) => {
        const truth = isNum(s.true_value) ? s.true_value : 0;
        const est = arr<{ name: string; label?: string; value: number; ci: Interval }>(s.estimators);
        const nameOf = (e: { name: string; label?: string }) => e.label ?? e.name;
        const hit = est.filter((e) => e.ci[0] <= truth && truth <= e.ci[1]).map(nameOf);
        const miss = est.filter((e) => !(e.ci[0] <= truth && truth <= e.ci[1])).map(nameOf);
        const rows: DwRow[] = est.map((e) => ({ label: nameOf(e), value: e.value, ci: e.ci, emphasis: e.name === "dr" ? "ref" : "plain" }));
        const lo = Math.min(truth, ...est.map((e) => e.ci[0])) - 0.02, hi = Math.max(truth, ...est.map((e) => e.ci[1])) + 0.02;
        return (
          <Block id="ope" kicker="Can we judge a coaching policy before using it?" claim={<>{hit.length ? `Intervals that contain the true value: ${hit.join(", ")}.` : "No estimator contains the true value."}{miss.length ? ` Missed it: ${miss.join(", ")}.` : ""}</>}>
            <div className="chart chart--wide">
              <DotWhisker rows={rows} unit="policy value" reference={truth} refLabel={`true ${truth.toFixed(3)}`} domain={[lo, hi]} digits={3} aria={`Off-policy estimates against the true value ${truth.toFixed(3)}. ${est.map((e) => `${nameOf(e)} ${e.value.toFixed(3)}`).join(", ")}.`} />
              <p className="ev-note">The true value is known because the simulator is ours. This tests the estimators, not the policy on real people. The doubly robust estimate is the one we would use.</p>
              <ChartFoot meta={s.meta ?? null} />
            </div>
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Injection table (scripted planner, and a small real-model run when present) ----------------------------- */
interface RtRow { ablation?: string; label?: string; attack_success: number; attack_ci?: Interval; task_success: number; task_ci?: Interval }
function RtTable({ rows }: { rows: RtRow[] }) {
  return (
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Condition</th><th>Attack succeeds</th><th aria-hidden="true" /><th>Task still succeeds</th></tr></thead>
      <tbody>{rows.map((x) => {
        const a = ivl(x.attack_ci, x.attack_success), t = ivl(x.task_ci, x.task_success);
        return (
          <tr key={x.ablation ?? x.label}>
            <td>{x.label ?? x.ablation}</td>
            <td className="num">{fmtPct(x.attack_success)} <span className="interval">{fmtPctInterval(a[0], a[1])}</span></td>
            <td><Range lo={a[0]} hi={a[1]} pt={x.attack_success} min={0} max={1} /></td>
            <td className="num">{fmtPct(x.task_success)} <span className="interval">{fmtPctInterval(t[0], t[1])}</span></td>
          </tr>);
      })}</tbody>
    </table></div>
  );
}

function Redteam({ rep }: { rep: EvalReport }) {
  const live = sec(rep, "redteam_live");
  return (
    <Guard id="redteam" kicker="Do the defences stop injected instructions?" what="The injection red team" s={sec(rep, "redteam")}>
      {(s) => {
        const rows = arr<RtRow>(s.rows);
        const on = rows[0], off = rows[rows.length - 1];
        const fp = s.false_pause_rate;
        return (
          <Block id="redteam" kicker="Do the defences stop injected instructions?" claim={on && off ? <>Attacks succeed {fmtPct(on.attack_success)} of the time with every layer on, and {fmtPct(off.attack_success)} with every layer off.</> : "Injection red team"}>
            <RtTable rows={rows} />
            <p className="ev-note">Each row switches off one layer.{isNum(fp) ? ` Clean pages were paused wrongly ${fmtPct(fp, 1)} of the time${Array.isArray(s.false_pause_ci) ? ` ${fmtPctInterval(ivl(s.false_pause_ci, fp)[0], ivl(s.false_pause_ci, fp)[1], 1)}` : ""}.` : ""} The attacks run on our own sandbox pages.</p>
            <ChartFoot meta={s.meta ?? null} />
            {live && (stubOf(live) ? <StubState s={live} what="The real-model run" /> : (
              <div className="stack">
                <h3 className="section__title" style={{ fontSize: "var(--text-lg)" }}>With a real model: a spot check, small n</h3>
                <RtTable rows={arr<RtRow>(live.rows)} />
                <ChartFoot meta={live.meta ?? null} />
              </div>
            ))}
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Ski rental --------------------------------------------------------------------------------------------- */
function Ski({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="ski" kicker="When should a routine be built?" what="Ski-rental regret" s={sec(rep, "ski_rental")}>
      {(s) => {
        const rows = arr<{ rule: string; label?: string; regret: number; ci: Interval }>(s.rows);
        const best = [...rows].sort((a, b) => a.regret - b.regret)[0];
        const hind = isNum(s.hindsight_regret) ? s.hindsight_regret : isNum(s.hindsight) ? s.hindsight : 1;
        const nameOf = (r: { rule: string; label?: string }) => r.label ?? r.rule;
        return (
          <Block id="ski" kicker="When should a routine be built?" claim={best ? <>{nameOf(best)} has the lowest regret: {best.regret.toFixed(1)} times the best choice in hindsight.</> : "Ski-rental regret"}>
            <div className="chart chart--wide">
              <DotWhisker rows={rows.map((x) => ({ label: nameOf(x), value: x.regret, ci: x.ci, emphasis: x.rule === "predictions" ? "ref" : "plain" }))} unit="cost as a multiple of the hindsight-best choice" reference={hind} refLabel={`hindsight best = ${hind}`} domain={[hind - 0.1, Math.max(...rows.map((x) => x.ci[1])) + 0.2]} digits={1} aria="Regret against the hindsight best choice, by rule." />
              <ChartFoot meta={s.meta ?? null} />
            </div>
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Deficit recovery and the routine finder ------------------------------------------------------------------- */
function Deficits({ rep }: { rep: EvalReport }) {
  const rt = sec(rep, "routines");
  return (
    <Guard id="deficits" kicker="Does the genome find the deficit we planted?" what="Deficit recovery" s={sec(rep, "deficit_recovery")}>
      {(s) => {
        const rows = arr<{ deficit: string; label?: string; injected_price_s: number; recovered_price_s: number; ci: Interval; precision?: number; recall?: number }>(s.rows);
        const overall = s.overall as { precision: number; recall: number } | undefined;
        const weakest = [...rows].filter((r) => isNum(r.recall)).sort((a, b) => (a.recall as number) - (b.recall as number))[0];
        const lessPrecise = [...rows].filter((r) => isNum(r.precision)).sort((a, b) => (a.precision as number) - (b.precision as number))[0];
        return (
          <Block id="deficits" kicker="Does the genome find the deficit we planted?" claim={<>{overall ? <>Precision {fmtPct(overall.precision)}, recall {fmtPct(overall.recall)} on injected deficits.</> : "Injected deficits and the price recovered for each."}{weakest && weakest.recall != null && weakest.recall < 0.8 ? <> Weakest: {(weakest.label ?? weakest.deficit).toLowerCase()}, recall {fmtPct(weakest.recall)}.</> : null}{lessPrecise && lessPrecise.precision != null && lessPrecise.precision < 0.8 ? <> Least precise: {(lessPrecise.label ?? lessPrecise.deficit).toLowerCase()}, {fmtPct(lessPrecise.precision)}.</> : null}</>}>
            <div className="chart chart--wide">
              <DotWhisker rows={rows.map((x) => ({ label: `${x.label ?? x.deficit} (injected ${signed(x.injected_price_s)} s)`, value: x.recovered_price_s, ci: x.ci }))} unit="seconds recovered" reference={0} refLabel="0" domain={[Math.min(0, ...rows.map((x) => x.ci[0])) - 5, Math.max(...rows.map((x) => x.ci[1])) + 10]} aria="Recovered cost of each injected deficit with its interval." />
              <ChartFoot meta={s.meta ?? null} />
            </div>
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Deficit</th><th className="num">Injected</th><th className="num">Recovered</th><th className="num">Precision</th><th className="num">Recall</th></tr></thead>
              <tbody>{rows.map((x) => <tr key={x.deficit}><td>{x.label ?? x.deficit}</td><td className="num">{signed(x.injected_price_s, 1)} s</td><td className="num">{signed(x.recovered_price_s, 1)} s <span className="interval">{fmtInterval(x.ci)}</span></td><td className="num">{dashed(x.precision, (n) => fmtPct(n))}</td><td className="num">{dashed(x.recall, (n) => fmtPct(n))}</td></tr>)}</tbody>
            </table></div>
            {rt && (stubOf(rt) ? <StubState s={rt} what="The routine finder result" /> : <RoutineFinder s={rt} />)}
          </Block>
        );
      }}
    </Guard>
  );
}

function RoutineFinder({ s }: { s: Sec }) {
  const rows = arr<{ persona: string; planted: number; found: number; precision: number; recall: number }>(s.rows);
  const overall = s.overall as { precision: number; recall: number } | undefined;
  const gate = s.proposals_after_value_gate as { proposed: number; real: number } | undefined;
  return (
    <div className="stack">
      <h3 className="section__title" style={{ fontSize: "var(--text-lg)" }}>Does the routine finder find the routines we planted?{overall ? ` Raw precision ${fmtPct(overall.precision)}, recall ${fmtPct(overall.recall)}.` : ""}{gate ? ` After the value gate, ${gate.real} of ${gate.proposed} proposals are real.` : ""}</h3>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Persona</th><th className="num">Planted</th><th className="num">Found</th><th className="num">Precision</th><th className="num">Recall</th></tr></thead>
        <tbody>{rows.map((x) => <tr key={x.persona}><td>{x.persona}</td><td className="num">{x.planted}</td><td className="num">{x.found}</td><td className="num">{fmtPct(x.precision)}</td><td className="num">{fmtPct(x.recall)}</td></tr>)}</tbody>
      </table></div>
      <ChartFoot meta={s.meta ?? null} />
    </div>
  );
}

/* -- Presence forecast, and pooling when present ----------------------------------------------------------------- */
interface Pol { interruption_rate?: number; idle_time_used?: number }
function PresenceBlock({ rep }: { rep: EvalReport }) {
  const pool = sec(rep, "pooling");
  return (
    <Guard id="presence" kicker="Does the window forecast hold up?" what="The presence forecast" s={sec(rep, "presence")}>
      {(s) => {
        const base = (s.baselines ?? {}) as { fixed_overnight?: Pol; idle_5min?: Pol };
        const rel = arr<RelPoint>(s.reliability ?? s.calibration);
        const ours: Pol = { interruption_rate: s.interruption_rate as number, idle_time_used: s.idle_time_used as number };
        const rows: [string, Pol | undefined, boolean][] = [["Our window rule", ours, true], ["Fixed overnight window", base.fixed_overnight, false], ["Run whenever idle for five minutes", base.idle_5min, false]];
        return (
          <Block id="presence" kicker="Does the window forecast hold up?" claim={<>{isNum(s.brier) ? <>The window forecast has a Brier score of {s.brier.toFixed(3)}{isNum(s.brier_prior_only) ? `, against ${s.brier_prior_only.toFixed(3)} for the prior alone` : ""}. </> : ""}{isNum(s.interruption_rate) ? <>It interrupts {fmtPct(s.interruption_rate, 1)} of runs{isNum(s.cap) ? `, with a cap of ${fmtPct(s.cap)}` : ""}.</> : null}</>}>
            <div className="ev-grid">
              <div className="chart">{rel.length > 0 ? <Reliability points={rel} label="Presence forecast calibration" /> : <EmptyState title="No reliability curve" body="The report has no calibration points for the forecast." />}<ChartFoot meta={s.meta ?? null} /></div>
              <div className="stack">
                <div className="table-wrap"><table className="table">
                  <thead><tr><th>Start policy</th><th className="num">Interrupted</th><th className="num">Idle time used</th></tr></thead>
                  <tbody>{rows.map(([name, p, bold]) => (
                    <tr key={name}><td>{bold ? <b>{name}</b> : name}</td><td className="num">{dashed(p?.interruption_rate, (n) => fmtPct(n, 1))}</td><td className="num">{dashed(p?.idle_time_used, (n) => fmtPct(n))}</td></tr>))}</tbody>
                </table></div>
                <p className="ev-note">The two baselines are start policies, not forecasts, so they have no Brier score. Compare how often they interrupt you and how much idle time they use.</p>
              </div>
            </div>
            {pool && (stubOf(pool) ? <StubState s={pool} what="The pooling result" /> : <Pooling s={pool} />)}
          </Block>
        );
      }}
    </Guard>
  );
}

function Pooling({ s }: { s: Sec }) {
  type Row = { n_episodes: number; no_pooling: number; partial_pooling: number; complete_pooling: number; ci?: Interval | Record<string, Interval> };
  const rows = arr<Row>(s.rows);
  const cell = (r: Row, k: "no_pooling" | "partial_pooling" | "complete_pooling") => {
    const v = r[k];
    const ci = Array.isArray(r.ci) ? (k === "partial_pooling" ? r.ci : null) : (r.ci as Record<string, Interval> | undefined)?.[k] ?? null;
    return <>{v.toFixed(1)} {ci && <span className="interval">{fmtInterval(ci, 1)}</span>}</>;
  };
  return (
    <div className="stack">
      <h3 className="section__title" style={{ fontSize: "var(--text-lg)" }}>How fast does a new person get a good forecast?</h3>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Episodes seen</th><th className="num">No pooling</th><th className="num">Partial pooling</th><th className="num">Complete pooling</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.n_episodes}><td className="num" style={{ textAlign: "left" }}>{r.n_episodes}</td><td className="num">{cell(r, "no_pooling")}</td><td className="num"><b>{cell(r, "partial_pooling")}</b></td><td className="num">{cell(r, "complete_pooling")}</td></tr>)}</tbody>
      </table></div>
      <p className="ev-note">{typeof s.note === "string" ? s.note : "Error of the forecast after this many episodes of a new person. Lower is better. Held out: leave one person out."} Partial pooling borrows from other people at first, then trusts the person's own days.</p>
      <ChartFoot meta={s.meta ?? null} />
    </div>
  );
}

/* -- Agent claims ------------------------------------------------------------------------------------------------- */
function Claims({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="agent" kicker="Can the agent's claim of success be trusted?" what="Agent claims" s={sec(rep, "agent_claims")}>
      {(s) => {
        const rel = arr<RelPoint>(s.reliability ?? s.calibration);
        return (
          <Block id="agent" kicker="Can the agent's claim of success be trusted?" claim={<>{isNum(s.base_rate) ? `About ${fmtPct(s.base_rate, 1)} of the agent's success claims are false. ` : ""}{isNum(s.brier) ? `Predicting which ones: Brier ${s.brier.toFixed(3)}.` : ""}</>}>
            <div className="ev-grid">
              <div className="chart">{rel.length > 0 ? <Reliability points={rel} label="Agent claim calibration" /> : <EmptyState title="No reliability curve" body="The report has no calibration points for this." />}<ChartFoot meta={s.meta ?? null} /></div>
              <div className="stack">
                {isNum(s.base_rate) && <div className="stat"><span className="stat__label">False success claims, base rate</span><span className="stat__value tabular">{fmtPct(s.base_rate, 1)}</span></div>}
                {isNum(s.brier) && <div className="stat"><span className="stat__label">Brier score of the claim predictor</span><span className="stat__value tabular">{s.brier.toFixed(3)}</span></div>}
                <p className="ev-note">The code check decides success, not the model, and it catches every false claim by construction. This block measures how well a false claim can be predicted from the trace, so a person can look first at the risky ones.</p>
              </div>
            </div>
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Live study ----------------------------------------------------------------------------------------------------- */
function Study({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="study" kicker="Does it help real people?" what="The live study" s={sec(rep, "study")}>
      {(s) => {
        const rows = arr<{ participant: string; unassisted_before_s: number; unassisted_after_s: number }>(s.rows);
        if (rows.length === 0) return <Block id="study" kicker="Does it help real people?" claim="The live study"><StubState s={{ status: "not_run", reason: "There are no study results in the report yet.", meta: s.meta }} what="The live study" /></Block>;
        const ci = Array.isArray(s.mean_change_ci) ? ivl(s.mean_change_ci, 0) : null;
        return (
          <Block id="study" kicker="Does it help real people?" claim={<>n = {s.meta?.n ?? rows.length}.{isNum(s.mean_change_s) ? ` Unassisted time changed by ${signed(s.mean_change_s, 0)} s on average.` : ""} Treat it as a case study.</>}>
            <div className="ev-grid">
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Teammate</th><th className="num">Before</th><th className="num">After</th><th className="num">Change</th></tr></thead>
                <tbody>{rows.map((x) => <tr key={x.participant}><td>{x.participant}</td><td className="num">{x.unassisted_before_s} s</td><td className="num">{x.unassisted_after_s} s</td><td className="num">{signed(x.unassisted_after_s - x.unassisted_before_s)} s</td></tr>)}</tbody>
              </table></div>
              <div className="stack">
                {isNum(s.mean_change_s) && <div className="stat"><span className="stat__label">Mean change, unassisted</span><span className="stat__value tabular">{signed(s.mean_change_s, 1)}<span className="stat__unit">s</span></span>{ci && <span className="stat__interval">95% interval {fmtInterval(ci, 1)} s</span>}</div>}
                <p className="ev-note">Unassisted time on a later, matched task, measured separately from assisted speed. With four people the interval is wide and the sample is not representative.</p>
              </div>
            </div>
            <ChartFoot meta={s.meta ?? null} />
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Limitations register ------------------------------------------------------------------------------------------- */
function Limits({ items }: { items: Limitation[] }) {
  return (
    <section className="ev-block" id="limits" aria-labelledby="limits-h">
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <p className="t-label">Limitations register</p>
        <h2 className="ev-claim" id="limits-h">What this does not show</h2>
        <p className="ev-note">Kept here, in the product, on purpose. The most serious first.</p>
      </div>
      {items.length === 0 ? <EmptyState title="No limitations listed" body="The report has no limitations register. That is itself a problem: every report must list its limits." /> : (
        <ol className="limits">
          {[...items].sort((a, b) => sevRank(a.severity) - sevRank(b.severity)).map((l) => (
            <li key={l.id} className="limit">
              <span className="limit__id">{l.id}</span>
              <span className="limit__text">{l.text}{l.source && <span className="limit__src"> From: {l.source.replace(/_/g, " ")}</span>}</span>
              <span className="sev" data-sev={l.severity}>{l.severity}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
const sevRank = (s: string) => ({ high: 0, medium: 1, low: 2 } as Record<string, number>)[s] ?? 3;
