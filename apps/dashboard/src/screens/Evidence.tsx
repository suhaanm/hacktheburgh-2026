import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import { useLoad, useWidth } from "../hooks";
import { scaleLinear } from "d3-scale";
import { ChartFoot, EmptyState, ErrorState, Loading, PageHead, Range } from "../components/common";
import { DotWhisker, type DwRow } from "../components/DotWhisker";
import { Facts } from "../components/Facts";
import { Reliability, RiskCoverage, type RcPoint, type RelPoint } from "../components/EvidenceCharts";
import { EvidenceMap, OtherSections, PrivacyEvidence, useHashOpen } from "../components/EvidenceMap";
import { LiveRuns } from "../components/LiveRuns";
import { Details } from "../components/ui";
import { mapRows, otherSections } from "../lib/evidence";
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

/** Caveats the engine attaches to a result, in its own words. Shown where the data carries them. */
function Caveats({ s }: { s: Sec }) {
  const list = arr<unknown>(s.caveats).filter((c): c is string => typeof c === "string");
  if (!list.length) return null;
  return (
    <Details summary={`Caveats from the engine (${list.length})`}>
      <ul className="plain-list">{list.map((c) => <li key={c} className="ev-note">{c}</li>)}</ul>
    </Details>
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

const NAV: [string, string][] = [["hazard", "Warning"], ["routing", "Review"], ["controls", "Controls"], ["ope", "Off-policy"], ["redteam", "Injection"], ["ski", "Ski rental"], ["deficits", "Deficits"], ["presence", "Presence"], ["agent", "Agent claims"], ["runs", "Agent runs"], ["privacy", "Privacy"], ["study", "Live study"], ["other", "Other"], ["limits", "Limits"]];

/** A sticky list of sections. The one you are reading is marked, so a very long page never loses its place. */
function JumpBar({ onGo }: { onGo: (id: string) => (e: { preventDefault: () => void }) => void }) {
  const [here, setHere] = useState<string>(NAV[0][0]);
  useEffect(() => {
    const els = NAV.map(([id]) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    if (!els.length || typeof IntersectionObserver === "undefined") return;
    const seen = new Map<string, number>();
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) seen.set(e.target.id, e.isIntersecting ? e.boundingClientRect.top : Infinity);
      const open = [...seen.entries()].filter(([, t]) => t !== Infinity).sort((a, b) => a[1] - b[1])[0];
      if (open) setHere(open[0]);
    }, { rootMargin: "-15% 0px -70% 0px" });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
  return (
    <nav className="ev-jump" aria-label="Sections on this page">
      {NAV.map(([id, t]) => <a key={id} href={`#${id}`} aria-current={here === id ? "true" : undefined} onClick={onGo(id)}>{t}</a>)}
    </nav>
  );
}

export default function Evidence() {
  const r = useLoad(() => api.evalReport(), []);
  useHashOpen();
  if (r.status === "error" && !r.data) return <div className="page"><ErrorState error={r.error} retry={r.reload} what="the evidence report" /></div>;
  if (!r.data) return <div className="page"><Loading label="Loading the evidence report" /></div>;
  const rep = r.data;
  const limits = arr<Limitation>(rep.sections.limitations);
  const study = sec(rep, "study");
  const studyRan = !!study && !stubOf(study) && isNum(study.meta?.n) && (study.meta?.n ?? 0) > 0;
  const anySynthetic = Object.entries(rep.sections).some(([k, v]) => k !== "limitations" && (v as Sec)?.meta?.origin && (v as Sec).meta!.origin !== "real");
  const go = (id: string) => (e: { preventDefault: () => void }) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); };
  const rows = mapRows(rep);
  const others = otherSections(rows);

  return (
    <div className="page page--wide">
      <PageHead
        title="What we can and cannot show"
        lede={<>{`Generated ${new Date(rep.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}${rep.mock ? ", mock mode" : ""}. `}{anySynthetic ? "Most numbers come from synthetic apprentices and personas, and each says so. " : ""}{studyRan ? `The live study has n = ${study!.meta!.n}. ` : "The live study has not run yet. "}<a href="#limits" onClick={go("limits")}>{limits.length} limits are listed at the end.</a></>}
      />
      <EvidenceMap rows={rows} onGo={go} />
      <JumpBar onGo={go} />
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
        <AgentRuns rep={rep} />
        <PrivacyEvidence s={sec(rep, "privacy")} row={rows.find((x) => x.section === "privacy") ?? null} />
        <Study rep={rep} />
        <OtherSections rows={others} sections={rep.sections as unknown as Record<string, unknown>} />
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
        const dd = d as unknown as { false_alarms_within_budget?: boolean; budget_false_alarms_per_hour?: number; false_alarms_per_hour_ci?: Interval; detection_rate?: number; detection_rate_ci?: Interval; interval_note?: string };
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
                {isNum(d.false_alarms_per_hour) && (
                  <div className="stat"><span className="stat__label">False alarms</span><span className="stat__value tabular">{d.false_alarms_per_hour.toFixed(1)}<span className="stat__unit">an hour</span></span>
                    {Array.isArray(dd.false_alarms_per_hour_ci) && <span className="stat__interval">95% interval {fmtInterval(ivl(dd.false_alarms_per_hour_ci, 0), 1)}</span>}
                    {isNum(dd.budget_false_alarms_per_hour) && <span className="stat__meta">Budget {dd.budget_false_alarms_per_hour.toFixed(1)} an hour: {dd.false_alarms_within_budget === false ? "over the budget on held-out people" : "within the budget"}.</span>}
                  </div>
                )}
                {isNum(dd.detection_rate) && (
                  <div className="stat"><span className="stat__label">Stuck moments warned about</span><span className="stat__value tabular">{fmtPct(dd.detection_rate)}</span>
                    {Array.isArray(dd.detection_rate_ci) && <span className="stat__interval">95% interval {fmtPctInterval(ivl(dd.detection_rate_ci, 0)[0], ivl(dd.detection_rate_ci, 0)[1])}</span>}
                  </div>
                )}
                {dd.interval_note && <p className="ev-note">{dd.interval_note}</p>}
                <Caveats s={s} />
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
                <p className="ev-note">{under ? "The point estimate is under the target." : "The point estimate is over the target."}{ciOver ? " The interval reaches above it, so we do not claim the target always holds." : ""} The bound was chosen on a calibration split and checked on a separate held-out split{typeof s.bound_held === "boolean" ? `: the engine reports it ${s.bound_held ? "held" : "did not hold"}` : ""}.{typeof s.bound_held_definition === "string" ? ` Here "held" means: ${s.bound_held_definition}` : ""}</p>
                {isNum(s.expert_minutes_per_case) && <div className="stat"><span className="stat__label">Expert time</span><span className="stat__value tabular">{s.expert_minutes_per_case.toFixed(1)}<span className="stat__unit">min per case</span></span>{isNum(s.expert_minutes_review_all) && <span className="stat__meta">against {s.expert_minutes_review_all.toFixed(1)} min per case if an expert reviewed everything</span>}</div>}
                <Caveats s={s} />
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
        const naive = est.find((e) => e.name === "naive"), dr = est.find((e) => e.name === "dr");
        const rows: DwRow[] = est.map((e) => ({ label: nameOf(e), value: e.value, ci: e.ci, emphasis: e.name === "dr" ? "ref" : "plain" }));
        const lo = Math.min(truth, ...est.map((e) => e.ci[0])) - 0.02, hi = Math.max(truth, ...est.map((e) => e.ci[1])) + 0.02;
        return (
          <Block id="ope" kicker="Can we judge a coaching policy before using it?" claim={naive && dr ? <>The naive average is off by {Math.abs(naive.value - truth).toFixed(3)}; doubly robust is off by {Math.abs(dr.value - truth).toFixed(3)}. {hit.length ? `Intervals that contain the true value: ${hit.join(", ")}.` : "No interval contains the true value."}</> : <>{hit.length ? `Intervals that contain the true value: ${hit.join(", ")}.` : "No estimator contains the true value."}{miss.length ? ` Missed it: ${miss.join(", ")}.` : ""}</>}>
            <div className="chart chart--wide">
              <DotWhisker rows={rows} unit="policy value" reference={truth} refLabel={`true ${truth.toFixed(3)}`} domain={[lo, hi]} digits={3} aria={`Off-policy estimates against the true value ${truth.toFixed(3)}. ${est.map((e) => `${nameOf(e)} ${e.value.toFixed(3)}`).join(", ")}.`} />
              <p className="ev-note">The true value is known because the simulator is ours. This tests the estimators, not the policy on real people.{typeof s.headline_target === "string" ? ` The policy being scored is ${s.headline_target.replace(/_/g, " ")}.` : ""}</p>
              <Caveats s={s} />
              <ChartFoot meta={s.meta ?? null} />
            </div>
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Injection table (scripted planner, and a small real-model run when present) ----------------------------- */
interface RtRow { ablation?: string; label?: string; attack_success: number; attack_ci?: Interval; task_success: number; task_ci?: Interval; paused_rate?: number }
function RtTable({ rows }: { rows: RtRow[] }) {
  const paused = rows.some((r) => isNum(r.paused_rate));
  return (
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Condition</th><th>Attack succeeds</th><th aria-hidden="true" /><th>Task still succeeds</th>{paused && <th className="num">Run paused</th>}</tr></thead>
      <tbody>{rows.map((x) => {
        const a = ivl(x.attack_ci, x.attack_success), t = ivl(x.task_ci, x.task_success);
        return (
          <tr key={x.ablation ?? x.label}>
            <td>{x.label ?? x.ablation}</td>
            <td className="num">{fmtPct(x.attack_success)} <span className="interval">{fmtPctInterval(a[0], a[1])}</span></td>
            <td><Range lo={a[0]} hi={a[1]} pt={x.attack_success} min={0} max={1} /></td>
            <td className="num">{fmtPct(x.task_success)} <span className="interval">{fmtPctInterval(t[0], t[1])}</span></td>
            {paused && <td className="num">{dashed(x.paused_rate, (n) => fmtPct(n))}</td>}
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
            <p className="ev-note">Each row switches off one layer. When a defence pauses the run, the task does not finish, so task success can be low even when the attack fails.{isNum(fp) ? ` Clean pages were paused wrongly ${fmtPct(fp, 1)} of the time${Array.isArray(s.false_pause_ci) ? ` ${fmtPctInterval(ivl(s.false_pause_ci, fp)[0], ivl(s.false_pause_ci, fp)[1], 1)}` : ""}.` : ""} The attacks run on our own sandbox pages.</p>
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
        const rows = arr<{ deficit: string; label?: string; injected_price_s: number; recovered_price_s: number; ci: Interval; precision?: number; recall?: number; precision_ci?: Interval; recall_ci?: Interval }>(s.rows);
        const overall = s.overall as { precision: number; recall: number } | undefined;
        const pc = (v: number | undefined, c?: Interval) => (isNum(v) ? <>{fmtPct(v)} {c && <span className="interval">{fmtPctInterval(c[0], c[1])}</span>}</> : "not reported");
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
              <tbody>{rows.map((x) => <tr key={x.deficit}><td>{x.label ?? x.deficit}</td><td className="num">{signed(x.injected_price_s, 1)} s</td><td className="num">{signed(x.recovered_price_s, 1)} s <span className="interval">{fmtInterval(x.ci)}</span></td><td className="num">{pc(x.precision, x.precision_ci)}</td><td className="num">{pc(x.recall, x.recall_ci)}</td></tr>)}</tbody>
            </table></div>
            {(typeof s.detection_rule === "string" || typeof s.price_definition === "string") && (
              <ul className="plain-list">
                {typeof s.price_definition === "string" && <li className="ev-note">Price: {s.price_definition}.</li>}
                {typeof s.detection_rule === "string" && <li className="ev-note">Detection: {s.detection_rule}.</li>}
              </ul>
            )}
            {rt && (stubOf(rt) ? <StubState s={rt} what="The routine finder result" /> : <RoutineFinder s={rt} />)}
          </Block>
        );
      }}
    </Guard>
  );
}

interface Stage { clusters?: number; proposals?: number; correct?: number; precision?: number; precision_ci?: Interval }
function RoutineFinder({ s }: { s: Sec }) {
  type Row = { persona: string; planted: number; found: number; precision: number; recall: number; raw_finder?: Stage; after_value_gate?: Stage };
  const rows = arr<Row>(s.rows);
  const o = (s.overall ?? {}) as { precision?: number; recall?: number; recall_ci?: Interval; raw_finder?: Stage; after_value_gate?: Stage; precision_basis?: string };
  const m = (s.metrics ?? {}) as { precision?: number; precision_ci?: Interval; recall?: number; recall_ci?: Interval; finder_precision?: number; finder_precision_ci?: Interval };
  const raw = o.raw_finder ?? (isNum(m.finder_precision) ? { precision: m.finder_precision, precision_ci: m.finder_precision_ci } : undefined);
  const gated = o.after_value_gate ?? (isNum(m.precision) ? { precision: m.precision, precision_ci: m.precision_ci } : isNum(o.precision) ? { precision: o.precision } : undefined);
  const recall = isNum(o.recall) ? o.recall : m.recall;
  const recallCi = o.recall_ci ?? m.recall_ci;
  const pc = (v?: number, c?: Interval) => (isNum(v) ? `${fmtPct(v)}${c ? ` ${fmtPctInterval(c[0], c[1])}` : ""}` : "not reported");
  const of = (k: number | undefined, n: number | undefined, unit: string) => (isNum(k) && isNum(n) ? ` (${k} of ${n} ${unit})` : "");
  const cell = (st: Stage | undefined, unit: "clusters" | "proposals") => {
    if (!st || !isNum(st.precision)) return "not reported";
    const n = unit === "clusters" ? st.clusters : st.proposals;
    return <>{fmtPct(st.precision)} <span className="interval">{isNum(st.correct) && isNum(n) ? `${st.correct} of ${n}` : ""}</span></>;
  };
  const hasStages = rows.some((r) => r.raw_finder || r.after_value_gate);
  return (
    <div className="stack">
      <h3 className="section__title" style={{ fontSize: "var(--text-lg)" }}>
        Does the routine finder find the routines we planted?{" "}
        {raw ? <>The finder alone is right {pc(raw.precision, raw.precision_ci)}{of(raw.correct, raw.clusters, "clusters")}. </> : null}
        {gated ? <>What the worker is shown is right {pc(gated.precision, gated.precision_ci)}{of(gated.correct, gated.proposals, "proposals")}{isNum(recall) ? `, and it finds ${pc(recall, recallCi)} of the planted routines` : ""}.</> : null}
      </h3>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Persona</th><th className="num">Planted</th><th className="num">Found</th>{hasStages ? <><th className="num">Finder alone, precision</th><th className="num">Shown to the worker, precision</th></> : <th className="num">Precision of proposals</th>}<th className="num">Recall</th></tr></thead>
        <tbody>{rows.map((x) => (
          <tr key={x.persona}><td>{x.persona}</td><td className="num">{x.planted}</td><td className="num">{x.found}</td>
            {hasStages ? <><td className="num">{cell(x.raw_finder, "clusters")}</td><td className="num">{cell(x.after_value_gate, "proposals")}</td></> : <td className="num">{fmtPct(x.precision)}</td>}
            <td className="num">{fmtPct(x.recall)}</td></tr>))}</tbody>
      </table></div>
      {hasStages && <p className="ev-note">The left precision is the finder's accuracy: how many of the clusters it raised are real routines. The right is what the worker is shown, after the value gate drops the ones that would not pay for themselves.</p>}
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
  type Row = Record<string, unknown> & { n_episodes: number; no_pooling: number; partial_pooling: number; complete_pooling: number; best?: string };
  const rows = arr<Row>(s.rows);
  const cell = (r: Row, k: "no_pooling" | "partial_pooling" | "complete_pooling") => {
    const v = r[k];
    // The engine sends ci_<method>; an older shape had one `ci` for partial pooling, or a map keyed by method.
    const own = r[`ci_${k}`];
    const ci: Interval | null = Array.isArray(own) ? ivl(own, v) : Array.isArray(r.ci) ? (k === "partial_pooling" ? ivl(r.ci, v) : null) : (r.ci as Record<string, Interval> | undefined)?.[k] ?? null;
    return <span style={r.best === k ? { fontWeight: 700 } : undefined}>{v.toFixed(3)} {ci && <span className="interval">{fmtInterval(ci, 3)}</span>}</span>;
  };
  return (
    <div className="stack">
      <h3 className="section__title" style={{ fontSize: "var(--text-lg)" }}>How fast does a new person get a good forecast?</h3>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Episodes seen</th><th className="num">No pooling</th><th className="num">Partial pooling</th><th className="num">Complete pooling</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.n_episodes}><td className="num" style={{ textAlign: "left" }}>{r.n_episodes}</td><td className="num">{cell(r, "no_pooling")}</td><td className="num">{cell(r, "partial_pooling")}</td><td className="num">{cell(r, "complete_pooling")}</td></tr>)}</tbody>
      </table></div>
      <p className="ev-note">{typeof s.note === "string" ? s.note : "Error after this many episodes of a new person. Lower is better. Held out: leave one person out."} Bold marks the best method at each row. Partial pooling borrows from other people at first, then trusts the person's own days.</p>
      <Caveats s={s} />
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
                {isNum(s.base_rate) && <div className="stat"><span className="stat__label">False success claims, base rate</span><span className="stat__value tabular">{fmtPct(s.base_rate, 1)}</span>{Array.isArray(s.false_claim_ci) && <span className="stat__interval">95% interval {fmtPctInterval(ivl(s.false_claim_ci, 0)[0], ivl(s.false_claim_ci, 0)[1], 1)}</span>}{isNum(s.claims) && isNum(s.false_claims) && <span className="stat__meta">{s.false_claims} of {s.claims} runs. The code check caught all {isNum(s.caught_by_code_check) ? s.caught_by_code_check : s.false_claims}.</span>}</div>}
                {isNum(s.brier) && <div className="stat"><span className="stat__label">Brier score of the claim predictor</span><span className="stat__value tabular">{s.brier.toFixed(3)}</span></div>}
                <p className="ev-note">The code check decides success, not the model, and it catches every false claim by construction. This block measures how well a false claim can be predicted from the trace, so a person can look first at the risky ones.</p>
                <Caveats s={s} />
              </div>
            </div>
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Agent runs on the sandbox ---------------------------------------------------------------------------------------- */
interface RunSet { n: number; pass: number; wilson?: Interval; mean_s?: number; tier_households?: Record<string, number>; injected?: { injection: string; n: number; pass: number; used_tier2?: number }[]; label?: string }
function RunStat({ title, r }: { title: string; r: RunSet }) {
  const t2 = r.tier_households?.["2"];
  return (
    <div className="stat">
      <span className="stat__label">{title}</span>
      <span className="stat__value tabular">{r.pass}<span className="stat__unit">of {r.n} passed</span></span>
      {r.wilson && <span className="stat__interval">95% Wilson interval {fmtInterval(r.wilson, 2)}</span>}
      <span className="stat__meta">{isNum(r.mean_s) ? `${r.mean_s.toFixed(1)} s per household` : ""}{isNum(t2) ? `${isNum(r.mean_s) ? ". " : ""}Tier 2 was needed on ${t2} households.` : ""}</span>
    </div>
  );
}

function AgentRuns({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="runs" kicker="Does the agent finish the work, and survive a changed page?" what="Agent runs on the sandbox" s={sec(rep, "agent_runs")}>
      {(s) => {
        const clean = s.clean as RunSet | undefined, robust = s.robust as RunSet | undefined;
        const disc = s.discrepancies_flagged as { n: number; of: number } | undefined;
        const live = s.live as Record<string, unknown> | null | undefined;
        const inj = robust?.injected ?? [];
        const t2 = robust?.tier_households?.["2"];
        return (
          <Block id="runs" kicker="Does the agent finish the work, and survive a changed page?" claim={<>
            {clean ? `Clean path: ${clean.pass} of ${clean.n}. ` : ""}{robust ? `With failures injected: ${robust.pass} of ${robust.n}${isNum(t2) ? `, using tier 2 on ${t2} households` : ""}. ` : ""}
            {disc ? `${disc.n} of ${disc.of} planted discrepancies flagged. ` : ""}{isNum(s.false_claims) ? `${typeof s.false_claims_scope === "string" && s.false_claims_scope ? `${s.false_claims_scope.charAt(0).toUpperCase()}${s.false_claims_scope.slice(1).replace(/\.$/, "")}: ` : "Scripted runs: "}${s.false_claims} false claims.` : ""}</>}>
            <div className="stats">
              {clean && <RunStat title="Clean path" r={clean} />}
              {robust && <RunStat title="With injected failures" r={robust} />}
              {disc && <div className="stat"><span className="stat__label">Planted discrepancies flagged</span><span className="stat__value tabular">{disc.n}<span className="stat__unit">of {disc.of} households</span></span><span className="stat__meta">Passing one means the disagreement between calculators was flagged, not hidden.</span></div>}
            </div>
            <p className="ev-note">The clean path is the compiled path on the sandbox it was written against, so a full pass is expected and says little. The table of injected failures is the evidence that discriminates.</p>
            {inj.length > 0 && (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Injected failure</th><th className="num">Households</th><th className="num">Passed</th><th className="num">Needed tier 2</th></tr></thead>
                <tbody>{inj.map((x) => <tr key={x.injection}><td>{x.injection}</td><td className="num">{x.n}</td><td className="num">{x.pass}</td><td className="num">{dashed(x.used_tier2, (n) => String(n))}</td></tr>)}</tbody>
              </table></div>
            )}
            {live && typeof live === "object" && <LiveRuns live={live} meta={s.meta ?? null} />}
            <Caveats s={s} />
            <ChartFoot meta={s.meta ?? null} />
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Live study ----------------------------------------------------------------------------------------------------- */
/** One dot per participant (coached minus uncoached skill), with the mean and its interval. Zero means no difference. */
function DiffStrip({ values, mean, ci, labels }: { values: number[]; mean: number; ci: Interval; labels: string[] }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const lo = Math.min(-0.1, ...values, ci[0]) - 0.05, hi = Math.max(0.1, ...values, ci[1]) + 0.05;
  const x = scaleLinear().domain([lo, hi]).range([16, Math.max(200, width - 16)]).nice();
  const H = 118;
  return (
    <div ref={box} className="chart">
      {width > 0 && (
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`Per-participant skill difference, coached minus uncoached: ${values.map((v, i) => `${labels[i] ?? `P${i + 1}`} ${signed(v, 2)}`).join(", ")}. Mean ${signed(mean, 2)}, interval ${fmtInterval(ci, 2)}.`}>
          {x.ticks(6).map((t) => (<g key={t}><line className="svg-grid" x1={x(t)} x2={x(t)} y1={6} y2={78} /><text className="svg-text" x={x(t)} y={94} textAnchor="middle">{signed(t, 1)}</text></g>))}
          <line className="ev-truth" x1={x(0)} x2={x(0)} y1={4} y2={80} />
          <text className="ev-truth-text" x={x(0) + 4} y={14}>no difference</text>
          {values.map((v, i) => (<g key={i}><circle className="ev-pt" cx={x(v)} cy={34} r={5.5}><title>{`${labels[i] ?? `Participant ${i + 1}`}: ${signed(v, 2)}`}</title></circle></g>))}
          <line className="ev-whisker" x1={x(ci[0])} x2={x(ci[1])} y1={62} y2={62} /><line className="ev-whisker" x1={x(ci[0])} x2={x(ci[0])} y1={57} y2={67} /><line className="ev-whisker" x1={x(ci[1])} x2={x(ci[1])} y1={57} y2={67} />
          <rect x={x(mean) - 5} y={57} width={10} height={10} transform={`rotate(45 ${x(mean)} 62)`} style={{ fill: "var(--fg)" }} />
          <text className="svg-text" x={x(ci[1]) + 10} y={66}>mean {signed(mean, 2)}</text>
          <text className="svg-text" x={width - 16} y={H - 4} textAnchor="end">skill score difference, 0 to 1 scale</text>
        </svg>
      )}
    </div>
  );
}

interface StudyRow { participant?: string; unassisted_before_s?: number; unassisted_after_s?: number }
function Study({ rep }: { rep: EvalReport }) {
  return (
    <Guard id="study" kicker="Does it help real people?" what="The live study" s={sec(rep, "study")}>
      {(s) => {
        const rows = arr<StudyRow>(s.rows);
        const h = s.headline as { mean_difference?: number; ci95?: Interval; per_participant_difference?: number[]; sign_flip_p_two_sided?: number; smallest_possible_p?: number; ci_method?: string } | undefined;
        const n = isNum(s.n) ? s.n : isNum(s.meta?.n) && (s.meta?.n ?? 0) > 0 ? s.meta!.n : rows.length;
        if (rows.length === 0 && !h) return <Block id="study" kicker="Does it help real people?" claim="The live study"><StubState s={{ status: "not_run", reason: "There are no study results in the report yet.", meta: s.meta }} what="The live study" /></Block>;
        const names = rows.map((r, i) => r.participant ?? `Participant ${i + 1}`);
        const minP = h && isNum(h.smallest_possible_p) ? h.smallest_possible_p : n > 0 ? 2 / 2 ** n : null;
        const hasHeadline = !!h && isNum(h.mean_difference) && Array.isArray(h.ci95);
        const legacy = s as unknown as { mean_change_s?: number; mean_change_ci?: Interval };
        return (
          <Block id="study" kicker="Does it help real people?" claim={hasHeadline ? <>n = {n}. Coached minus uncoached unassisted skill: {signed(h!.mean_difference!, 2)} {fmtInterval(ivl(h!.ci95, 0), 2)} on a 0 to 1 scale. A case study, not a result.</> : <>n = {n}. A case study, not a result.</>}>
            {hasHeadline && (
              <div className="ev-grid">
                <DiffStrip values={arr<number>(h!.per_participant_difference).filter(isNum)} mean={h!.mean_difference!} ci={ivl(h!.ci95, 0)} labels={names} />
                <div className="stack">
                  <div className="stat"><span className="stat__label">Mean difference in unassisted skill</span><span className="stat__value tabular">{signed(h!.mean_difference!, 2)}</span><span className="stat__interval">95% interval {fmtInterval(ivl(h!.ci95, 0), 2)}</span>{h!.ci_method && <span className="stat__meta">Interval method: {h!.ci_method}</span>}</div>
                  {isNum(h!.sign_flip_p_two_sided) && <div className="stat"><span className="stat__label">Sign-flip test, two-sided</span><span className="stat__value tabular">p = {h!.sign_flip_p_two_sided.toFixed(3)}</span>{minP != null && <span className="stat__meta">With n = {n}, the smallest p that is possible is {minP.toFixed(3)}. This page cannot show conventional significance, and does not claim it.</span>}</div>}
                </div>
              </div>
            )}
            {rows.length > 0 && (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Teammate</th><th className="num">Uncoached block, time</th><th className="num">Coached block, time</th>{hasHeadline && <th className="num">Skill difference</th>}</tr></thead>
                <tbody>{rows.map((x, i) => (
                  <tr key={names[i] + i}><td>{names[i]}</td><td className="num">{dashed(x.unassisted_before_s, (v) => `${Math.round(v)} s`)}</td><td className="num">{dashed(x.unassisted_after_s, (v) => `${Math.round(v)} s`)}</td>{hasHeadline && <td className="num">{dashed(arr<number>(h!.per_participant_difference)[i], (v) => signed(v, 2))}</td>}</tr>))}</tbody>
              </table></div>
            )}
            {!hasHeadline && isNum(legacy.mean_change_s) && <p className="ev-note">Mean difference in unassisted time, coached minus uncoached: {signed(legacy.mean_change_s, 0)} s{legacy.mean_change_ci ? ` ${fmtInterval(ivl(legacy.mean_change_ci, 0))} s` : ""}.</p>}
            <div className="ev-grid">
              <Facts title="Assisted speed, reported separately" v={s.assisted_speed} />
              <Facts title="Unassisted speed" v={s.unassisted_speed} />
              <Facts title="How the coach was used" v={s.coach_use} />
            </div>
            <p className="ev-note">The headline is the unassisted skill score on a later, matched task: coached minus uncoached, per person. Speed with the coach on is reported separately and is not the headline. With four people the interval is wide and the sample is not representative.</p>
            <ChartFoot meta={s.meta ?? null} />
          </Block>
        );
      }}
    </Guard>
  );
}

/* -- Limitations register ------------------------------------------------------------------------------------------- */

function Limits({ items }: { items: Limitation[] }) {
  const groups: [string, string][] = [["high", "High"], ["medium", "Medium"], ["low", "Low"]];
  const known = new Set(groups.map(([k]) => k));
  const other = items.filter((l) => !known.has(l.severity));
  const list = (rows: Limitation[]) => (
    <ol className="limits">
      {rows.map((l) => (
        <li key={l.id} className="limit">
          <span className="limit__id">{l.id.length > 6 ? "·" : l.id}</span>
          <span className="limit__text">{l.text}{srcOf(l.source) && <span className="limit__src"> From: {srcOf(l.source)}</span>}</span>
          <span className="sev" data-sev={l.severity}>{l.severity}</span>
        </li>
      ))}
    </ol>
  );
  return (
    <section className="ev-block" id="limits" aria-labelledby="limits-h">
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <p className="t-label">Limitations register · {items.length}</p>
        <h2 className="ev-claim" id="limits-h">What this does not show</h2>
        <p className="ev-note">Every limit the build raised is listed. The serious ones are open; the rest are one click away.</p>
      </div>
      {items.length === 0 ? <EmptyState title="No limitations listed" body="The report has no limitations register. That is itself a problem: every report must list its limits." /> : (
        <div className="stack" style={{ gap: "var(--space-6)" }}>
          {[...groups, ...(other.length ? ([["other", "Other"]] as [string, string][]) : [])].map(([sev, name]) => {
            const rows = sev === "other" ? other : items.filter((l) => l.severity === sev);
            if (!rows.length) return null;
            return sev === "high" || sev === "other" ? (
              <div key={sev} className="stack" style={{ gap: "var(--space-2)" }}>
                <h3 className="t-label">{name} ({rows.length})</h3>
                {list(rows)}
              </div>
            ) : (
              <Details key={sev} className="limits-fold" summary={<><span className="t-label">{name} ({rows.length})</span> <span className="u-muted">show</span></>}>
                {list(rows)}
              </Details>
            );
          })}
        </div>
      )}
    </section>
  );
}

function srcOf(src?: string): string | null {
  if (!src) return null;
  return src.split(";")[0].trim().replace(/:\s*/g, " · ").replace(/_/g, " ");
}
