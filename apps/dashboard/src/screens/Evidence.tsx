import type { ReactNode } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, Loading, PageHead, Range } from "../components/common";
import { DotWhisker, type DwRow } from "../components/DotWhisker";
import { Reliability, RiskCoverage, type RcPoint, type RelPoint } from "../components/EvidenceCharts";
import { fmtInterval, fmtPct, fmtPctInterval, signed } from "../lib/format";
import type { AnalyticMeta, EvalReport, Interval, Limitation } from "../types";

/* The contract fixes the section names; their inner shapes were agreed with the eval track (see API_CONTRACT "Additions"). Read defensively. */
type Sec = { meta: AnalyticMeta } & Record<string, unknown>;
const sec = (r: EvalReport, k: string): Sec | null => ((r.sections as Record<string, unknown>)[k] as Sec | undefined) ?? null;
const num = (v: unknown, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

function Block({ id, kicker, claim, children }: { id: string; kicker: string; claim: ReactNode; children: ReactNode }) {
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
const Missing = ({ what }: { what: string }) => <EmptyState title={`${what} is not in the report yet`} body="Run make eval to write evals/report.json. This block fills in on its own." />;

const NAV = [["hazard", "Warning"], ["routing", "Review"], ["ope", "Off-policy"], ["redteam", "Injection"], ["ski", "Ski rental"], ["deficits", "Deficits"], ["presence", "Presence"], ["study", "Live study"], ["limits", "Limits"]];

export default function Evidence() {
  const r = useLoad(() => api.evalReport(), []);
  if (r.status === "error" && !r.data) return <div className="page"><ErrorState error={r.error} retry={r.reload} what="the evidence report" /></div>;
  if (!r.data) return <div className="page"><Loading label="Loading the evidence report" /></div>;
  const rep = r.data;
  const limits = arr<Limitation>(rep.sections.limitations);
  const study = sec(rep, "study");
  const anySynthetic = Object.entries(rep.sections).some(([k, v]) => k !== "limitations" && (v as Sec)?.meta?.origin && (v as Sec).meta.origin !== "real");

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow={`Evidence · generated ${new Date(rep.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}${rep.mock ? " · mock mode" : ""}`}
        title="What we can show, and what we cannot"
        lede={<>{anySynthetic ? "Most numbers here come from synthetic apprentices and personas, and each one says so. " : ""}{study ? `The live study has n = ${study.meta.n}. ` : ""}Every chart prints its n, its split and its 95% interval. <a href="#limits-h" onClick={(e) => { e.preventDefault(); document.getElementById("limits")?.scrollIntoView({ behavior: "smooth" }); }}>{limits.length} limits are listed at the end.</a></>}
        aside={<nav className="row" aria-label="On this page" style={{ gap: "var(--space-2) var(--space-4)", maxWidth: 420 }}>{NAV.map(([id, t]) => <a key={id} className="t-data" href={`#/evidence`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); }}>{t}</a>)}</nav>}
      />
      <div className="ev">
        <Hazard rep={rep} />
        <Routing rep={rep} />
        <Ope rep={rep} />
        <Redteam rep={rep} />
        <Ski rep={rep} />
        <Deficits rep={rep} />
        <PresenceBlock rep={rep} />
        <Study rep={rep} />
        <Limits items={limits} />
      </div>
    </div>
  );
}

/* -- 1. Stuck warning calibration ------------------------------------------------------------- */
function Hazard({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "hazard");
  if (!s) return <Block id="hazard" kicker="Is the stuck warning calibrated?" claim="Stuck warning"><Missing what="The hazard result" /></Block>;
  const d = ((s as Record<string, unknown>).data ?? s) as { model?: { log_loss: number; brier: number; ece: number; ci_log_loss: Interval }; baselines?: Record<string, { log_loss: number; brier: number; ece: number }>; calibration?: RelPoint[]; false_alarms_per_hour?: number; split?: string };
  const m = d.model, tsp = d.baselines?.time_since_progress, br = d.baselines?.base_rate;
  const better = m && tsp && br && m.log_loss < tsp.log_loss && m.log_loss < br.log_loss;
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
          {m && <p className="ev-note">Log loss 95% interval {fmtInterval(m.ci_log_loss, 3)}. Lower is better for all three columns. The base rate has the best ECE because it only ever says one number; log loss and Brier show it knows nothing about who is stuck.</p>}
          {d.false_alarms_per_hour != null && <div className="stat"><span className="stat__label">False alarms</span><span className="stat__value tabular">{d.false_alarms_per_hour.toFixed(1)}<span className="stat__unit">an hour</span></span></div>}
        </div>
      </div>
      <ChartFoot meta={s.meta} extra={d.split ? <span>held out: <b>{d.split}</b></span> : undefined} />
    </Block>
  );
}

/* -- 2. Review routing: risk-coverage --------------------------------------------------------- */
function Routing({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "routing");
  if (!s) return <Block id="routing" kicker="Can we skip review safely?" claim="Review routing"><Missing what="The routing result" /></Block>;
  const alpha = num(s.alpha, 0.05), cov = num(s.chosen_coverage), err = num(s.held_out_error);
  const ci = (s.held_out_ci as Interval) ?? [err, err];
  const under = err <= alpha, ciOver = ci[1] > alpha;
  return (
    <Block id="routing" kicker="Can we skip review safely?" claim={<>Auto-approve {fmtPct(cov)} of cases, send the rest to an expert. Held-out error {fmtPct(err, 1)}, target {fmtPct(alpha)}.</>}>
      <div className="ev-grid">
        <div className="chart"><RiskCoverage curve={arr<RcPoint>(s.curve)} alpha={alpha} chosen={cov} heldOut={{ value: err, ci }} /></div>
        <div className="stack">
          <div className="stat"><span className="stat__label">Held-out error at {fmtPct(cov)} coverage</span><span className="stat__value tabular">{fmtPct(err, 1)}</span><span className="stat__interval">95% interval {fmtPctInterval(ci[0], ci[1], 1)}</span></div>
          <p className="ev-note">{under ? "The point estimate is under the target." : "The point estimate is over the target."}{ciOver ? " The interval reaches above it, so we do not claim the target always holds." : ""} The bound was chosen on a calibration split and checked on a separate held-out split{s.bound_held != null ? `: the engine reports it ${s.bound_held ? "held" : "did not hold"}` : ""}.</p>
          {s.expert_minutes_per_case != null && <div className="stat"><span className="stat__label">Expert time</span><span className="stat__value tabular">{num(s.expert_minutes_per_case).toFixed(1)}<span className="stat__unit">min per case</span></span></div>}
        </div>
      </div>
      <ChartFoot meta={s.meta} extra={<span>band: 95% interval</span>} />
    </Block>
  );
}

/* -- 3. Off-policy recovery -------------------------------------------------------------------- */
function Ope({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "ope");
  if (!s) return <Block id="ope" kicker="Can we judge a coaching policy before using it?" claim="Off-policy recovery"><Missing what="The off-policy result" /></Block>;
  const truth = num(s.true_value);
  const est = arr<{ name: string; value: number; ci: Interval }>(s.estimators);
  const hit = est.filter((e) => e.ci[0] <= truth && truth <= e.ci[1]).map((e) => e.name);
  const miss = est.filter((e) => !(e.ci[0] <= truth && truth <= e.ci[1])).map((e) => e.name);
  const rows: DwRow[] = est.map((e) => ({ label: e.name, value: e.value, ci: e.ci, emphasis: /doubly/i.test(e.name) ? "ref" : "plain" }));
  const lo = Math.min(truth, ...est.map((e) => e.ci[0])) - 0.02, hi = Math.max(truth, ...est.map((e) => e.ci[1])) + 0.02;
  return (
    <Block id="ope" kicker="Can we judge a coaching policy before using it?" claim={<>{hit.length ? `Intervals that contain the true value: ${hit.join(", ")}.` : "No estimator contains the true value."}{miss.length ? ` Missed it: ${miss.join(", ")}.` : ""}</>}>
      <div className="chart chart--wide">
        <DotWhisker rows={rows} unit="policy value" reference={truth} refLabel={`true ${truth.toFixed(3)}`} domain={[lo, hi]} digits={3} aria={`Off-policy estimates against the true value ${truth.toFixed(3)}. ${est.map((e) => `${e.name} ${e.value.toFixed(3)}`).join(", ")}.`} />
        <p className="ev-note">The true value is known because the simulator is ours. This tests the estimators, not the policy on real people.</p>
        <ChartFoot meta={s.meta} />
      </div>
    </Block>
  );
}

/* -- 4. Injection table ------------------------------------------------------------------------- */
function Redteam({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "redteam");
  if (!s) return <Block id="redteam" kicker="Do the defences stop injected instructions?" claim="Injection red team"><Missing what="The red-team result" /></Block>;
  const rows = arr<{ ablation: string; attack_success: number; attack_ci: Interval; task_success: number; task_ci: Interval }>(s.rows);
  const on = rows[0], off = rows[rows.length - 1];
  const fp = num(s.false_pause_rate);
  return (
    <Block id="redteam" kicker="Do the defences stop injected instructions?" claim={on && off ? <>Attacks succeed {fmtPct(on.attack_success)} of the time with every layer on, and {fmtPct(off.attack_success)} with every layer off.</> : "Injection red team"}>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Condition</th><th>Attack succeeds</th><th aria-hidden="true" /><th>Task still succeeds</th></tr></thead>
        <tbody>{rows.map((x) => (
          <tr key={x.ablation}>
            <td>{x.ablation}</td>
            <td className="num">{fmtPct(x.attack_success)} <span className="interval">{fmtPctInterval(x.attack_ci[0], x.attack_ci[1])}</span></td>
            <td><Range lo={x.attack_ci[0]} hi={x.attack_ci[1]} pt={x.attack_success} min={0} max={1} /></td>
            <td className="num">{fmtPct(x.task_success)} <span className="interval">{fmtPctInterval(x.task_ci[0], x.task_ci[1])}</span></td>
          </tr>))}</tbody>
      </table></div>
      <p className="ev-note">Each row switches off one layer. Clean pages were paused wrongly {fmtPct(fp, 1)} of the time{s.false_pause_ci ? ` ${fmtPctInterval((s.false_pause_ci as Interval)[0], (s.false_pause_ci as Interval)[1], 1)}` : ""}. The attacks run on our own sandbox pages.</p>
      <ChartFoot meta={s.meta} />
    </Block>
  );
}

/* -- 5. Ski rental ------------------------------------------------------------------------------- */
function Ski({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "ski_rental");
  if (!s) return <Block id="ski" kicker="When should a routine be built?" claim="Ski-rental regret"><Missing what="The ski-rental result" /></Block>;
  const rows = arr<{ rule: string; regret: number; ci: Interval }>(s.rows);
  const best = [...rows].sort((a, b) => a.regret - b.regret)[0];
  const hind = num(s.hindsight, 1);
  return (
    <Block id="ski" kicker="When should a routine be built?" claim={best ? <>{best.rule} has the lowest regret: {best.regret.toFixed(1)} times the best choice in hindsight.</> : "Ski-rental regret"}>
      <div className="chart chart--wide">
        <DotWhisker rows={rows.map((x) => ({ label: x.rule, value: x.regret, ci: x.ci }))} unit="cost as a multiple of the hindsight-best choice" reference={hind} refLabel="hindsight best = 1" domain={[hind - 0.1, Math.max(...rows.map((x) => x.ci[1])) + 0.2]} digits={1} aria="Regret against the hindsight best choice, by rule." />
        <ChartFoot meta={s.meta} />
      </div>
    </Block>
  );
}

/* -- 6. Deficit recovery and routine finder ------------------------------------------------------ */
function Deficits({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "deficit_recovery"), rt = sec(rep, "routines"), np = sec(rep, "null_placebo");
  if (!s) return <Block id="deficits" kicker="Does the genome find the deficit we planted?" claim="Deficit recovery"><Missing what="The deficit-recovery result" /></Block>;
  const rows = arr<{ deficit: string; true_s: number; est_s: number; ci: Interval }>(s.rows);
  const rrows = arr<{ persona: string; planted: number; found: number; precision: number; recall: number }>(rt?.rows);
  const overall = (rt?.overall ?? null) as { precision: number; recall: number } | null;
  return (
    <Block id="deficits" kicker="Does the genome find the deficit we planted?" claim={<>Precision {fmtPct(num(s.precision))}, recall {fmtPct(num(s.recall))} on injected deficits, with the price of each in seconds.</>}>
      <div className="chart chart--wide">
        <DotWhisker rows={rows.map((x) => ({ label: `${x.deficit} (true ${x.true_s} s)`, value: x.est_s, ci: x.ci }))} unit="seconds recovered" reference={0} refLabel="0" domain={[Math.min(0, ...rows.map((x) => x.ci[0])) - 5, Math.max(...rows.map((x) => x.ci[1])) + 10]} aria="Estimated cost of each injected deficit with its interval." />
        <ChartFoot meta={s.meta} />
      </div>
      {np && (
        <p className="ev-note">Controls: expert against expert {signed(num((np.placebo as { gap_s: number })?.gap_s), 1)} s {fmtInterval(((np.placebo as { ci: Interval })?.ci) ?? [0, 0], 1)}, shuffled labels {signed(num((np.null as { gap_s: number })?.gap_s), 1)} s {fmtInterval(((np.null as { ci: Interval })?.ci) ?? [0, 0], 1)}. Both include zero.</p>
      )}
      {rt && (
        <div className="stack">
          <h3 className="section__title" style={{ fontSize: "var(--text-lg)" }}>Does the routine finder find the routines we planted?{overall ? ` Precision ${fmtPct(overall.precision)}, recall ${fmtPct(overall.recall)}.` : ""}</h3>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Persona</th><th className="num">Planted</th><th className="num">Found</th><th className="num">Precision</th><th className="num">Recall</th></tr></thead>
            <tbody>{rrows.map((x) => <tr key={x.persona}><td>{x.persona}</td><td className="num">{x.planted}</td><td className="num">{x.found}</td><td className="num">{fmtPct(x.precision)}</td><td className="num">{fmtPct(x.recall)}</td></tr>)}</tbody>
          </table></div>
          <ChartFoot meta={rt.meta} />
        </div>
      )}
    </Block>
  );
}

/* -- 7. Presence and agent claims ----------------------------------------------------------------- */
function PresenceBlock({ rep }: { rep: EvalReport }) {
  const p = sec(rep, "presence"), a = sec(rep, "agent_claims");
  if (!p && !a) return <Block id="presence" kicker="Does the window forecast hold up?" claim="Presence and agent claims"><Missing what="The presence result" /></Block>;
  return (
    <Block id="presence" kicker="Does the window forecast hold up?" claim={p ? <>Presence forecast Brier {num(p.brier).toFixed(3)}, against {num(p.brier_baseline_overnight).toFixed(3)} for a fixed overnight window and {num(p.brier_baseline_idle5).toFixed(3)} for running whenever idle five minutes.</> : "Agent claims"}>
      <div className="ev-grid">
        {p && <div className="chart"><Reliability points={arr<RelPoint>(p.calibration)} label="Presence forecast calibration" /><ChartFoot meta={p.meta} /></div>}
        <div className="stack">
          {p && <div className="stat"><span className="stat__label">Interruptions</span><span className="stat__value tabular">{fmtPct(num(p.interruption_rate), 1)}</span><span className="stat__meta">cap {fmtPct(num(p.interruption_cap))}. Share of runs where you came back before they finished.</span></div>}
          {a && (
            <div className="stat"><span className="stat__label">False success claims by the agent</span><span className="stat__value tabular">{num(a.false_claims)}<span className="stat__unit">of {num(a.claims)}</span></span>
              <span className="stat__interval">{fmtPct(num(a.false_claim_rate), 1)} {fmtPctInterval(((a.false_claim_ci as Interval) ?? [0, 0])[0], ((a.false_claim_ci as Interval) ?? [0, 0])[1], 1)}</span>
              <span className="stat__meta">{num(a.caught_by_code_check)} caught by the code check, which decides success, not the model.</span></div>
          )}
          {a && <ChartFoot meta={a.meta} />}
        </div>
      </div>
    </Block>
  );
}

/* -- 8. Live study -------------------------------------------------------------------------------- */
function Study({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "study");
  if (!s) return <Block id="study" kicker="Does it help real people?" claim="Live study"><Missing what="The live study" /></Block>;
  const rows = arr<{ participant: string; unassisted_before_s: number; unassisted_after_s: number }>(s.rows);
  const ci = (s.mean_change_ci as Interval) ?? [0, 0];
  return (
    <Block id="study" kicker="Does it help real people?" claim={<>n = {s.meta.n}. Unassisted time changed by {signed(num(s.mean_change_s), 0)} s on average. Treat it as a case study.</>}>
      <div className="ev-grid">
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Teammate</th><th className="num">Before</th><th className="num">After</th><th className="num">Change</th></tr></thead>
          <tbody>{rows.map((x) => <tr key={x.participant}><td>{x.participant}</td><td className="num">{x.unassisted_before_s} s</td><td className="num">{x.unassisted_after_s} s</td><td className="num">{signed(x.unassisted_after_s - x.unassisted_before_s)} s</td></tr>)}</tbody>
        </table></div>
        <div className="stack">
          <div className="stat"><span className="stat__label">Mean change, unassisted</span><span className="stat__value tabular">{signed(num(s.mean_change_s), 1)}<span className="stat__unit">s</span></span><span className="stat__interval">95% interval {fmtInterval(ci, 1)} s</span></div>
          <p className="ev-note">Unassisted time on a later, matched task, measured separately from assisted speed. With four people the interval is wide and the sample is not representative.</p>
        </div>
      </div>
      <ChartFoot meta={s.meta} />
    </Block>
  );
}

/* -- 9. Limitations register -------------------------------------------------------------------------- */
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
            <li key={l.id} className="limit"><span className="limit__id">{l.id}</span><span className="limit__text">{l.text}</span><span className="sev" data-sev={l.severity}>{l.severity}</span></li>
          ))}
        </ol>
      )}
    </section>
  );
}
const sevRank = (s: string) => ({ high: 0, medium: 1, low: 2 } as Record<string, number>)[s] ?? 3;
