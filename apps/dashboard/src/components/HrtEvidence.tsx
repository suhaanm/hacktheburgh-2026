import type { ReactNode } from "react";
import { Reliability, type RelPoint } from "./EvidenceCharts";
import { ChartFoot, EmptyState } from "./common";
import { Details } from "./ui";
import { fmtInterval, fmtPct, fmtPctInterval, signed } from "../lib/format";
import type { AnalyticMeta, EvalReport, Interval } from "../types";

/**
 * Two blocks of the Evidence page (an admin More row, for reviewers), read from `sections.hrt_ledger` and `sections.hrt_decisions` of evals/report.json, which the
 * HRT track writes from its single frozen held-out runs (evals/hrt/PLAN.md). Each block opens with one headline and one picture or four short lines; every table is
 * behind a disclosure. A section that has not run says why and shows nothing else. The words in this file are the app's: "generated worlds", "generators we wrote".
 *   1. Does it hold out of time: forecasts written before their outcomes, scored forward, in the world the model was fitted for and in worlds where it was not.
 *   2. Does the rule beat the naive one: each shipped rule against a naive policy and an oracle, four registered contrasts at the adjusted level.
 */
type Sec = { meta?: AnalyticMeta; status?: string; reason?: string } & Record<string, unknown>;
const sec = (r: EvalReport, k: string): Sec | null => ((r.sections as unknown as Record<string, unknown>)[k] as Sec | undefined) ?? null;
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const stubOf = (s: Sec | null) => (s && typeof s.status === "string" && ["pending", "not_run", "failed"].includes(s.status) ? s : null);
const ci = (v: unknown, d = 3): string => (Array.isArray(v) && v.length === 2 && v.every(isNum) ? fmtInterval(v as Interval, d) : "");
const name = (k: string) => ({ online_base: "online base rate", frozen_tsp: "frozen time since progress", frozen_base: "frozen base rate" } as Record<string, string>)[k] ?? k.replace(/_/g, " ");

function Result({ ok }: { ok: boolean }) {
  return <span className="pill pill--status" data-status={ok ? "ok" : "failed"}><span className="pill__glyph-char" aria-hidden="true">{ok ? "✓" : "✕"}</span>{ok ? "passed" : "did not pass"}</span>;
}

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

function Waiting({ id, kicker, what, s }: { id: string; kicker: string; what: string; s: Sec | null }) {
  const stub = stubOf(s);
  return (
    <Block id={id} kicker={kicker} claim={what}>
      <EmptyState title={stub ? `${what} has not run yet` : `${what} is not in the report`} body={stub?.reason || "Run make eval to write evals/report.json. This block fills in on its own."} />
    </Block>
  );
}

interface Claim { id: string; claim: string; result: string; evidence: string }
interface World { world: string; deployments: number; people_or_blocks: number; predictions: number; model_log_loss: number; best_naive: string; model_minus_best_naive: number; model_minus_best_naive_ci: Interval; verdict: string; calibration_slope: number; calibration_slope_ci: Interval; calibration_intercept: number; calibration_intercept_ci: Interval; guard_flags: string }
interface GuardRow { world: string; flags: number; of: number; flag_rate_ci: Interval; always_model: number; always_fallback: number; guarded: number; oracle: number; guarded_minus_always_model: number; guarded_minus_always_model_ci: Interval; share_on_fallback: number }

export function HrtLedger({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "hrt_ledger");
  if (!s || stubOf(s)) return <Waiting id="hrt-ledger" kicker="Does it hold out of time?" what="Forecasts scored forward in time" s={s} />;
  const claims = arr<Claim>(s.rows), worlds = arr<World>(s.worlds), guard = arr<GuardRow>(s.guard);
  const passed = claims.filter((c) => c.result === "passed").length, applicable = claims.filter((c) => c.result !== "not applicable").length;
  const failed = claims.filter((c) => c.result === "not passed");
  const v1 = worlds[0];
  const changed = worlds.filter((w) => w.verdict === "a worse");
  const rel = arr<RelPoint>(s.reliability_v1);
  const meta = (s.meta ?? null) as AnalyticMeta | null;
  const limits = arr<{ id: string; text: string }>(s.limitations);
  return (
    <Block id="hrt-ledger" kicker="Does it hold out of time?"
      claim={<>Every forecast was written before its outcome and scored forward in time. {passed} of {applicable} registered claims passed{failed.length ? `; ${failed.map((c) => c.id).join(" and ")} did not` : ""}. Where the world changed, the model was worse than a one-line baseline in {changed.length} of {Math.max(0, worlds.filter((w) => /shifted/.test(w.world)).length)} worlds.</>}>
      <div className="ev-grid">
        <div className="chart">
          <Reliability points={rel} label="Stuck warning calibration, scored forward in time, in the world the model was fitted for" />
          <p className="ev-note">In the world the model was fitted for. On the dashed diagonal means a forecast of 40% happens 40% of the time. Dot area is the number of forecasts.</p>
        </div>
        <div className="stack">
          {v1 && (
            <div className="stat"><span className="stat__label">Log loss against the better naive predictor ({name(v1.best_naive)})</span>
              <span className="stat__value tabular">{signed(v1.model_minus_best_naive, 3)}<span className="stat__unit">nats a forecast</span></span>
              <span className="stat__interval">95% interval {ci(v1.model_minus_best_naive_ci)}. Negative is better.</span></div>
          )}
          {v1 && <div className="stat"><span className="stat__label">Calibration slope</span><span className="stat__value tabular">{v1.calibration_slope.toFixed(2)}</span><span className="stat__interval">95% interval {ci(v1.calibration_slope_ci, 2)}. Intercept {signed(v1.calibration_intercept, 3)} {ci(v1.calibration_intercept_ci)}. 1 and 0 are ideal.</span></div>}
        </div>
      </div>

      <Details summary={`The worlds, one row each (${worlds.length})`}>
        <div className="table-wrap"><table className="table" style={{ minWidth: 700 }}>
          <thead><tr><th>World</th><th className="num">Forecasts</th><th className="num">Model log loss</th><th className="num">Model minus best naive</th><th className="num">Calibration slope</th><th className="num">Guard flags</th></tr></thead>
          <tbody>{worlds.map((w) => (
            <tr key={w.world}><td>{w.world}</td><td className="num">{w.predictions.toLocaleString("en-GB")}</td><td className="num">{w.model_log_loss.toFixed(3)}</td>
              <td className="num">{signed(w.model_minus_best_naive, 3)} <span className="interval">{ci(w.model_minus_best_naive_ci)}</span><br /><span className="u-muted">{w.verdict.replace(/^a /, "model ")} than {name(w.best_naive)}</span></td>
              <td className="num">{w.calibration_slope.toFixed(2)}</td><td className="num">{w.guard_flags}</td></tr>))}</tbody>
        </table></div>
        <p className="ev-note">Where the world changes the model is worse than a one-line baseline and its calibration slope turns negative, so it points the wrong way. The guard compares the model with the online base rate episode by episode and falls back when the evidence says the model is no better.</p>
      </Details>
      <Details summary={`Every registered claim, as run (${claims.length})`}>
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Id</th><th>Claim, registered before any number existed</th><th>Result</th></tr></thead>
          <tbody>{claims.map((c) => <tr key={c.id}><td>{c.id}</td><td>{c.claim}<br /><span className="u-muted">{c.evidence}</span></td><td><Result ok={c.result === "passed"} /></td></tr>)}</tbody>
        </table></div>
      </Details>
      <Details summary="The guard: what falling back cost and saved">
        <div className="table-wrap"><table className="table" style={{ minWidth: 700 }}>
          <thead><tr><th>World</th><th className="num">Flags</th><th className="num">Always model</th><th className="num">Always fallback</th><th className="num">Guarded</th><th className="num">Oracle</th><th className="num">Guarded minus always model</th></tr></thead>
          <tbody>{guard.map((g) => (
            <tr key={g.world}><td>{g.world}</td><td className="num">{g.flags} of {g.of} <span className="interval">{fmtPctInterval(g.flag_rate_ci[0], g.flag_rate_ci[1])}</span></td><td className="num">{g.always_model.toFixed(3)}</td><td className="num">{g.always_fallback.toFixed(3)}</td><td className="num">{g.guarded.toFixed(3)}</td><td className="num">{g.oracle.toFixed(3)}</td>
              <td className="num">{signed(g.guarded_minus_always_model, 3)} <span className="interval">{ci(g.guarded_minus_always_model_ci)}</span></td></tr>))}</tbody>
        </table></div>
        <p className="ev-note">Mean log loss per forecast. The oracle is the better of the first two in hindsight. Intervals resample deployments, eight a world, so they are wide.</p>
      </Details>
      {limits.length > 0 && <Details summary={`Limits (${limits.length})`}><ul className="plain-list">{limits.map((l) => <li key={l.id} className="ev-note">{l.text}</li>)}</ul></Details>}
      <ChartFoot meta={meta} extra={<span>registered in evals/hrt/PLAN.md; run once</span>} />
    </Block>
  );
}

interface Contrast { label: string; est: number; ci95: Interval; verdict: string; primary: boolean; ci_adjusted?: Interval }
interface Cell { policies: Record<string, { est: number; ci: Interval }>; contrasts: Record<string, Contrast> }
interface BoardRow { id: string; decision: string; unit: string; direction: string; replicates: number; cells: Record<string, Cell>; primary_cell: string; note?: string }
interface Summary { id: string; decision: string; unit: string; shipped_rule: number; naive_policy: string; naive_value: number; oracle_value: number; primary_contrast: number; ci95: Interval; ci_adjusted_98_75: Interval; verdict: string; share_of_naive_to_oracle_gap_closed: number | null; share_ci?: Interval | null; replicates: number; better: string }

const SHORT: Record<string, string> = { D1: "Build timing", D2: "Which cases an expert reviews", D3: "When to start a background run", D4: "Speak or stay silent" };

export function HrtDecisions({ rep }: { rep: EvalReport }) {
  const s = sec(rep, "hrt_decisions");
  if (!s || stubOf(s)) return <Waiting id="hrt-decisions" kicker="Does the rule beat the naive one?" what="Decisions against naive and oracle policies" s={s} />;
  const rows = arr<Summary>(s.rows), board = arr<BoardRow>(s.scoreboard);
  const wins = rows.filter((r) => r.verdict === "win").length;
  const meta = (s.meta ?? null) as AnalyticMeta | null;
  const limits = arr<{ id: string; text: string }>(s.limitations);
  const cue = arr<Record<string, unknown>>(s.recorded)[0];
  const cueShipped = cue && typeof cue.shipped === "object" ? (cue.shipped as { est?: number; ci?: Interval }) : null;
  const d = (r: Summary, v: number) => v.toFixed(r.id === "D4" ? 3 : 2);
  return (
    <Block id="hrt-decisions" kicker="Does the rule beat the naive one?"
      claim={<>{wins} of {rows.length} shipped rules beat a naive policy in generated worlds, judged at the adjusted level, and a naive policy beats one of them.</>}>
      <div className="stats">
        {rows.map((r) => (
          <div className="stat" key={r.id}>
            <span className="stat__label">{SHORT[r.id] ?? r.decision}</span>
            <span className="stat__value tabular">{d(r, r.shipped_rule)}<span className="stat__unit">against {d(r, r.naive_value)} for {r.naive_policy}</span></span>
            <span className="stat__meta">Oracle {d(r, r.oracle_value)}. {r.share_of_naive_to_oracle_gap_closed != null ? `Closes ${fmtPct(r.share_of_naive_to_oracle_gap_closed)} of the gap.` : "The gap is not defined."} {r.better === "lower" ? "Lower is better." : "Higher is better."}</span>
          </div>
        ))}
      </div>
      <p className="ev-note">Four contrasts were registered before any number existed. Four wins is what one expects when the same people write the generator and the rule, so read the cells where a rule does not win: building at once costs less than the shipped build-timing rule at the pack's own build costs (4 to 9 runs), and the review router's edge over random review partly comes from signal the generator hands it.</p>

      <Details summary="The four registered contrasts, with the adjusted interval">
        <div className="table-wrap"><table className="table" style={{ minWidth: 700 }}>
          <thead><tr><th>Decision</th><th className="num">Shipped</th><th>Naive</th><th className="num">Oracle</th><th className="num">Shipped minus naive</th><th className="num">Adjusted 98.75%</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id}><td>{r.decision}<br /><span className="u-muted">{r.unit}; {r.replicates} worlds</span></td><td className="num">{d(r, r.shipped_rule)}</td><td>{r.naive_policy} <span className="tabular">{d(r, r.naive_value)}</span></td><td className="num">{d(r, r.oracle_value)}</td>
              <td className="num">{signed(r.primary_contrast, r.id === "D4" ? 3 : 2)} <span className="interval">{ci(r.ci95, r.id === "D4" ? 3 : 2)}</span></td><td className="num">{ci(r.ci_adjusted_98_75, r.id === "D4" ? 3 : 2)} <span className="u-muted">{r.verdict}</span></td></tr>))}</tbody>
        </table>
        {rows.some((r) => r.share_ci) && <p className="ev-note">Share of the naive-to-oracle gap closed: {rows.map((r) => `${r.id} ${r.share_of_naive_to_oracle_gap_closed != null ? fmtPct(r.share_of_naive_to_oracle_gap_closed) : "n/a"}${r.share_ci ? ` ${fmtPctInterval(r.share_ci[0], r.share_ci[1])}` : ""}`).join("; ")}.</p>}
        </div>
      </Details>
      {board.map((b) => (
        <Details key={b.id} summary={`${SHORT[b.id] ?? b.id}: every cell, exploratory unless marked registered`}>
          {Object.entries(b.cells).map(([k, cell]) => (
            <div key={k} className="stack" style={{ gap: "var(--space-2)" }}>
              <span className="t-label">{Object.keys(b.cells).length > 1 ? `setting ${k}` : "all"}</span>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Contrast</th><th className="num">Estimate</th><th className="num">95% interval</th><th>Reading</th></tr></thead>
                <tbody>{Object.values(cell.contrasts).map((c) => (
                  <tr key={c.label}><td>{c.label}{c.primary ? " (registered)" : ""}</td><td className="num">{signed(c.est, 3)}</td><td className="num">{ci(c.ci95)}</td><td>{c.verdict}</td></tr>))}</tbody>
              </table></div>
            </div>
          ))}
          {b.note && <p className="ev-note">{b.note}</p>}
        </Details>
      ))}
      {cueShipped && isNum(cueShipped.est) && (
        <p className="ev-note">Recorded, not re-run: Cue saves {cueShipped.est.toFixed(1)} s per hour of work net of interruptions {ci(cueShipped.ci, 1)} against 0 for staying silent, and met one of its two registered targets. The help-level ladder is not scored: it is deterministic code with no outcome to score until the live study.</p>
      )}
      {limits.length > 0 && <Details summary={`Limits (${limits.length})`}><ul className="plain-list">{limits.map((l) => <li key={l.id} className="ev-note">{l.text}</li>)}</ul></Details>}
      <ChartFoot meta={meta} extra={<span>registered in evals/hrt/PLAN.md; run once</span>} />
    </Block>
  );
}

/** Both blocks, in the order the Evidence page shows them. */
export function HrtEvidence({ rep }: { rep: EvalReport }) {
  return <><HrtLedger rep={rep} /><HrtDecisions rep={rep} /></>;
}
