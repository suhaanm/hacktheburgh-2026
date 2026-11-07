import { api } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, Loading, Note, PageHead, SourceNote } from "../components/common";
import { OriginBadge } from "../components/needsyou/Origin";
import "../components/kc.css";
import { Hint } from "../components/Hint";
import { Details } from "../components/ui";
import { directRoles, fmtMs, fmtUsd, healthReading, latencyText, providerName, roleLabel, scalarRows, totalCalls, totalCost, WHEN_LABEL } from "../lib/models";
import { fmtDateTime } from "../lib/format";
import type { ModelProvider, ModelRole, ModelsStatus } from "../types";

export default function Models() {
  const m = useLoad(() => api.modelsStatus(), []);
  const rep = useLoad(() => api.evalReport(), []);
  if (m.status === "error" && !m.data) return <div className="page page--read kc-page"><ErrorState error={m.error} retry={m.reload} what="the model status" /></div>;
  if (!m.data) return <div className="page page--read kc-page"><Loading label="Loading the model status" /></div>;
  const s = m.data;
  const calls = totalCalls(s.meter);
  const cost = totalCost(s.meter);
  const direct = directRoles(s.providers);

  return (
    <div className="page page--read kc-page">
      <PageHead
        title="Models and cost"
        lede="Costs are estimates from assumed prices, not a bill."
        aside={<OriginBadge sources={[m]} />}
      />
      <SourceNote why={m.why} />
      {s.config_error && <Note tone="warn">The model settings could not be read: {s.config_error}</Note>}
      {s.mock && !m.why && <Note>Mock mode is on, so no real model is called.</Note>}
      <p className="note" data-testid="spend-line"><b className="tabular">{fmtUsd(cost)}</b> estimated so far, <b className="tabular">{calls.n}</b> {calls.n === 1 ? "call" : "calls"}{calls.n > 0 ? `, ${calls.failed} failed` : ""}.</p>

      <Details summary="Who does what" defaultOpen>
        {s.roles.length === 0 && direct.length === 0 ? (
          <p className="note">No jobs are routed yet. The agent service has not reported any model roles.</p>
        ) : (
          <div className="stack">
            <div className="chains" role="list" aria-label="Model routing by job">
              {s.roles.map((r) => <Chain key={r.role} r={r} />)}
              {direct.map((d) => (
                <div key={d.role} className="chain" role="listitem">
                  <div className="chain__head"><span className="chain__role">{roleLabel(d.role)}</span><span className="t-data u-muted">one model, no fallback</span></div>
                  <div className="chain__steps"><span className="chain__step" data-when="primary"><b>{providerName(d.provider)}</b><code>{d.model}</code></span></div>
                </div>
              ))}
            </div>
            <p className="legend-inline"><span className="chain__sw" data-when="primary" />first choice <span className="chain__sw" data-when="escalate" />stronger, when unsure <span className="chain__sw" data-when="fallback" />other provider, on failure</p>
            <p className="note">Code, not a model, decides when to try the next.</p>
          </div>
        )}
      </Details>
      <Details summary="Providers" wide><Providers providers={s.providers} boot={s.boot} /></Details>
      <Details summary="Speed and cost" wide><Spend s={s} cost={cost} calls={calls} /><Meter s={s} /></Details>
      <Details summary="Assumed prices" wide><Prices s={s} /></Details>
      <Details summary="Model bake-off" wide><Bakeoff status={s.bakeoff} report={rep.data} /></Details>
      <p className="note">Generated {s.generated_at ? fmtDateTime(s.generated_at) : "just now"}. No key or password is ever shown here.</p>
    </div>
  );
}

function Chain({ r }: { r: ModelRole }) {
  const esc = r.escalate && Object.keys(r.escalate).length > 0 ? `Tries the stronger model when ${escalateWords(r.escalate)}.` : "";
  const dl = typeof r.deadline_s === "number" ? `Gives up after ${r.deadline_s} s.` : "";
  return (
    <div className="chain" role="listitem">
      <div className="chain__head">
        <span className="chain__role">{roleLabel(r.role)}{(esc || dl) && <Hint label="About this job's models">{[esc, dl].filter(Boolean).join(" ")}</Hint>}</span>
      </div>
      <ol className="chain__steps">
        {r.steps.map((st, i) => (
          <li key={i} className="chain__step" data-when={st.when}>
            <span className="chain__when t-label">{WHEN_LABEL[st.when] ?? st.when}</span>
            <b>{providerName(st.provider)}{st.tier ? ` · ${st.tier}` : ""}</b>
            {st.model ? <code>{st.model}</code> : <span className="u-muted">model id not resolved</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function escalateWords(e: Record<string, unknown>): string {
  const w: string[] = [];
  if (e.not_found === true) w.push("the target is not found");
  if (typeof e.confidence_below === "number" && e.confidence_below > 0) w.push(`confidence is under ${e.confidence_below}`);
  if (e.schema_failure === true) w.push("the answer breaks its format");
  if (e.timeout === true) w.push("the first one is too slow");
  return w.length ? w.join(", ").replace(/, ([^,]*)$/, " or $1") : "it cannot tell";
}

function Providers({ providers, boot }: { providers: ModelProvider[]; boot: ModelsStatus["boot"] }) {
  return (
    <section className="section" aria-label="Providers">
      {providers.length === 0 ? <p className="note">No provider reported.</p> : (
        <div className="stack">
          {providers.map((p) => {
            const h = healthReading(p);
            const b = boot.find((x) => x.provider === p.name);
            return (
              <div key={p.name} className="prov" data-tone={h.tone}>
                <div className="row">
                  <b className="prov__name">{providerName(p.name)}</b>
                  <span className="pill pill--health" data-tone={h.tone}><span className="pill__dot" aria-hidden="true" />{h.label}</span>
                </div>
                <ul className="plain-list">
                  <li className="note">{p.configured ? "Set up on this laptop." : "Not set up here, so it is never called."}{p.enabled_by_flag === false ? " Its feature flag is off." : ""}</li>
                  {p.breaker && <li className="note">Circuit breaker: <b>{p.breaker.state}</b>{p.breaker.recent_failures ? `, ${p.breaker.recent_failures} recent ${p.breaker.recent_failures === 1 ? "failure" : "failures"}` : ""}{p.breaker.opened_count ? `, opened ${p.breaker.opened_count} ${p.breaker.opened_count === 1 ? "time" : "times"}` : ""}. It pauses a provider after repeated failures so one outage cannot stall everything.</li>}
                  {p.models && <li className="note">Resolved ids: {Object.entries(p.models).map(([k, v]) => <span key={k}><code>{k}</code> <code>{v}</code>{" "}</span>)}</li>}
                  {b && <li className="note">Start-up check: {b.ok === false ? `failed${b.missing?.length ? `, missing ${b.missing.join(", ")}` : ""}` : b.mock ? "skipped in mock mode" : "passed"}{b.t ? ` (${fmtDateTime(b.t)})` : ""}.</li>}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Spend({ s, cost, calls }: { s: ModelsStatus; cost: number | null; calls: { n: number; ok: number; failed: number } }) {
  const lat = Object.entries(s.latencies);
  return (
    <section className="section" aria-label="Cost and speed so far">
      <div className="stats">
        <div className="stat"><span className="stat__label">Estimated spend</span><span className="stat__value tabular">{fmtUsd(cost)}</span><span className="stat__meta">an estimate from assumed prices, not a bill</span></div>
        <div className="stat"><span className="stat__label">Calls</span><span className="stat__value tabular">{calls.n}</span><span className="stat__meta">{calls.n === 0 ? "none yet this session" : `${calls.ok} worked, ${calls.failed} failed`}</span></div>
      </div>
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <span className="t-label">Latest response times</span>
        {lat.length === 0 ? <p className="note">No call has been timed yet.</p> : (
          <ul className="plain-list">{lat.map(([k, v]) => <li key={k} className="note"><code>{k.replace(":", " · ")}</code> {latencyText(v)}</li>)}</ul>
        )}
      </div>
    </section>
  );
}

function Meter({ s }: { s: ModelsStatus }) {
  return (
    <section className="section" aria-label="Every job, as the meter saw it">
      <p className="note">Response times count successful calls only.</p>
      {s.meter.length === 0 ? (
        <EmptyState title="No model call has been metered yet" body={s.mock ? "Mock mode makes no real call, so there is nothing to meter." : "When a job calls a model, one row appears here with its counts, times and estimated cost."} />
      ) : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Job</th><th>Model</th><th className="num">Calls</th><th className="num">Failed</th><th className="num">Median</th><th className="num">Slowest 5%</th><th className="num hide-narrow">Tokens in / out</th><th className="num">Estimated cost</th></tr></thead>
          <tbody>{s.meter.map((r, i) => (
            <tr key={i}>
              <td>{roleLabel(r.role)}</td>
              <td><span className="u-muted">{providerName(r.provider)}</span> <code>{r.model}</code></td>
              <td className="num">{r.n}</td><td className="num">{r.failed}</td>
              <td className="num">{fmtMs(r.p50_ms)}</td><td className="num">{fmtMs(r.p95_ms)}</td>
              <td className="num hide-narrow">{r.input_tokens.toLocaleString("en-GB")} / {r.output_tokens.toLocaleString("en-GB")}</td>
              <td className="num">{fmtUsd(r.cost_usd_est)}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </section>
  );
}

function Prices({ s }: { s: ModelsStatus }) {
  const rows = Object.entries(s.prices_assumed);
  return (
    <section className="section" aria-label="Prices these estimates assume">
      <Note tone="warn">Every cost here is calls multiplied by these assumed prices. They are our own assumptions, not a price list or a bill.</Note>
      {rows.length === 0 ? <p className="note">No prices were reported.</p> : (
        <Details summary={`See the ${rows.length} assumed prices`} wide>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Provider and tier</th><th className="num">Input, per million tokens</th><th className="num">Output, per million tokens</th><th>Where the figure came from</th></tr></thead>
            <tbody>{rows.map(([k, p]) => <tr key={k}><td><code>{k}</code></td><td className="num">${p.input_usd_per_million.toFixed(2)}</td><td className="num">${p.output_usd_per_million.toFixed(2)}</td><td>{p.source === "assumed_default" ? "assumed default" : p.source.replace(/_/g, " ")}</td></tr>)}</tbody>
          </table></div>
        </Details>
      )}
    </section>
  );
}

/** The bake-off compares models on our own cases. It lives in the status when the service has one, else in the evidence report. */
function Bakeoff({ status, report }: { status: unknown; report: { sections: Record<string, unknown> } | null }) {
  const fromReport = report ? (report.sections as Record<string, unknown>).modelbench : null;
  const src = (status && typeof status === "object" ? status : fromReport) as Record<string, unknown> | null;
  const stub = src && typeof src.status === "string" && src.status !== "ok";
  const t = src ? scalarRows(src.rows ?? src.models ?? src.results) : { cols: [], rows: [] };
  return (
    <section className="section" aria-label="Model bake-off">
      <p className="note">Candidate models on our own sandbox cases. Speed and accuracy claims come only from here.</p>
      {!src || stub || t.rows.length === 0 ? (
        <EmptyState title="The bake-off has not produced results" body={<>No model is called faster or better until it has.{src && typeof src.reason === "string" && src.reason ? <Hint label="Why it has not run">{src.reason}</Hint> : null}</>} action={<a className="btn btn--secondary" href="#/evidence">Evidence map</a>} />
      ) : (
        <div className="table-wrap"><table className="table">
          <thead><tr>{t.cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
          <tbody>{t.rows.map((r, i) => <tr key={i}>{t.cols.map((c) => <td key={c} className={r[c] !== "" && !Number.isNaN(Number(r[c])) ? "num" : undefined}>{r[c]}</td>)}</tr>)}</tbody>
        </table></div>
      )}
    </section>
  );
}
