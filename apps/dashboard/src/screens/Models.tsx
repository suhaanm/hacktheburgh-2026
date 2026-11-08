import { api } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, ExampleBadge, Loading, Note, OriginBadge, PageHead, SourceNote, workerOriginLabel } from "../components/common";
import { Hint } from "../components/Hint";
import { Details, FactRows } from "../components/ui";
import { directRoles, fmtMs, fmtUsd, healthReading, latencyText, providerName, roleLabel, scalarRows, totalCalls, totalCost, WHEN_LABEL } from "../lib/models";
import { fmtDateTime } from "../lib/format";
import { useState } from "react";
import type { ModelProvider, ModelRole, ModelsStatus } from "../types";

export default function Models() {
  const m = useLoad(() => api.modelsStatus(), []);
  const rep = useLoad(() => api.evalReport(), []);
  if (m.status === "error" && !m.data) return <div className="page"><ErrorState error={m.error} retry={m.reload} what="the model status" /></div>;
  if (!m.data) return <div className="page"><Loading label="Loading the model status" /></div>;
  const s = m.data;
  const calls = totalCalls(s.meter);
  const cost = totalCost(s.meter);
  const direct = directRoles(s.providers);

  return (
    <div className="page page--wide">
      <PageHead
        title={s.roles.length === 0 && s.providers.length === 0 ? "No model layer yet" : "Which model does each job"}
        lede="Code picks the model. A model never picks itself."
        aside={m.why ? <ExampleBadge why={m.why} /> : <OriginBadge meta={m.meta} label={m.meta ? workerOriginLabel(m.meta.origin) : undefined} />}
      />
      {s.config_error && <Note tone="warn">The model settings could not be read: {s.config_error}</Note>}
      {m.why?.kind === "error" && <SourceNote why={m.why} />}

      <section className="hero" aria-labelledby="route-h">
        <h2 className="u-sr-only" id="route-h">Who does what</h2>
        {s.roles.length === 0 && direct.length === 0 ? (
          <EmptyState title="No jobs routed yet" body="Each job and its models appear here once the agent service reports them." />
        ) : (
          <div className="chains" role="list" aria-label="Model routing by job, first choice first">
            {s.roles.map((r) => <Chain key={r.role} r={r} />)}
            {direct.map((d) => (
              <div key={d.role} className="chain" role="listitem">
                <div className="chain__head"><span className="chain__role">{roleLabel(d.role)}</span><span className="t-data u-muted">one model, no fallback</span></div>
                <div className="chain__steps"><span className="chain__step" data-when="primary"><b>{providerName(d.provider)}</b><code>{d.model}</code></span></div>
              </div>
            ))}
          </div>
        )}
        {s.roles.some((r) => r.steps.some((st) => !st.model)) && <p className="note">With no keys set, model ids are not shown. They appear here once the keys are in place.</p>}
      </section>

      <div className="stack">
        <Details summary="Providers and spend" wide><ProvidersAndSpend s={s} cost={cost} calls={calls} /></Details>
        <Details summary="Every job" wide><Meter s={s} /></Details>
        <Details summary="Model bake-off" wide><Bakeoff status={s.bakeoff} report={rep.data} /></Details>
        <Details summary="More" wide>
          <div className="stack">
            <Details summary="Assumed prices" wide><Prices s={s} /></Details>
            <Details summary="How this page works" wide>
              <div className="stack">
                <p className="note">Each job has a first choice, a stronger one for when it cannot tell, and another provider for when it fails. Code decides when to try the next.</p>
                <ul className="legend" aria-label="Key to the chains">
                  <li className="legend__item"><span className="chain__sw" data-when="primary" />first choice</li>
                  <li className="legend__item"><span className="chain__sw" data-when="escalate" />stronger, when unsure</li>
                  <li className="legend__item"><span className="chain__sw" data-when="fallback" />other provider, on failure</li>
                </ul>
                {m.why && m.why.kind !== "error" && <SourceNote why={m.why} />}
                <FactRows rows={[
                  ["Mode", s.mock && !m.why ? "mock: no real model is called" : "live"],
                  ["Generated", s.generated_at ? fmtDateTime(s.generated_at) : "just now"],
                  ["Keys", "no key, token or password is shown here"],
                ]} />
              </div>
            </Details>
          </div>
        </Details>
      </div>
      <p className="note">Costs are estimates from assumed prices, not a bill.</p>
    </div>
  );
}

function Chain({ r }: { r: ModelRole }) {
  return (
    <div className="chain" role="listitem">
      <div className="chain__head">
        <span className="chain__role">{roleLabel(r.role)}{r.escalate && Object.keys(r.escalate).length > 0 && <Hint label="When the stronger model is tried">Tries the stronger model when {escalateWords(r.escalate)}.</Hint>}</span>
        {typeof r.deadline_s === "number" && <span className="t-data u-muted" title="The job gives up after this long">{r.deadline_s} s limit</span>}
      </div>
      <ol className="chain__steps">
        {r.steps.map((st, i) => (
          <li key={i} className="chain__step" data-when={st.when}>
            <span className="chain__when t-label">{WHEN_LABEL[st.when] ?? st.when}</span>
            <b>{providerName(st.provider)}{st.tier ? ` · ${st.tier}` : ""}</b>
            {st.model ? <code>{st.model}</code> : null}
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

/** One row per provider (name, health, whether it is set up); the spend and the calls as two rows; everything else in one closed More. */
function ProvidersAndSpend({ s, cost, calls }: { s: ModelsStatus; cost: number | null; calls: { n: number; ok: number; failed: number } }) {
  const lat = Object.entries(s.latencies);
  return (
    <div className="stack">
      {s.providers.length === 0 ? <span className="note">No provider reported.</span> : (
        <ul className="plain-list prov-rows" aria-label="Providers">
          {s.providers.map((p) => {
            const h = healthReading(p);
            return (
              <li key={p.name} className="prov-row">
                <b className="prov__name">{providerName(p.name)}</b>{" "}
                <span className="pill pill--health" data-tone={h.tone}><span className="pill__dot" aria-hidden="true" />{h.label}</span>{" "}
                <span className="u-muted">{p.configured ? "set up here" : "not set up, never called"}{p.enabled_by_flag === false ? ", its flag is off" : ""}</span>
              </li>
            );
          })}
        </ul>
      )}
      <FactRows rows={[
        ["Estimated spend", fmtUsd(cost)],
        ["Calls", calls.n === 0 ? "none yet this session" : `${calls.n}: ${calls.ok} worked, ${calls.failed} failed`],
      ]} />
      <Details summary="More" wide>
        <div className="stack">
          <ProviderNotes providers={s.providers} boot={s.boot} />
          <div className="stack" style={{ gap: "var(--space-2)" }}>
            <span className="t-label">Latest response times</span>
            {lat.length === 0 ? <span className="note">No call has been timed yet.</span> : (
              <ul className="plain-list">{lat.map(([k, v]) => <li key={k} className="note"><code>{k.replace(":", " · ")}</code> {latencyText(v)}</li>)}</ul>
            )}
          </div>
        </div>
      </Details>
    </div>
  );
}

/** What each provider reports about itself: its breaker, its resolved ids and its start-up check. */
function ProviderNotes({ providers, boot }: { providers: ModelProvider[]; boot: ModelsStatus["boot"] }) {
  return (
    <div className="stack">
      {providers.map((p) => {
        const b = boot.find((x) => x.provider === p.name);
        return (
          <div key={p.name} className="prov" data-tone={healthReading(p).tone}>
            <b className="prov__name">{providerName(p.name)}</b>
            <ul className="plain-list">
              {p.breaker && <li className="note">Circuit breaker: <b>{p.breaker.state}</b>{p.breaker.recent_failures ? `, ${p.breaker.recent_failures} recent ${p.breaker.recent_failures === 1 ? "failure" : "failures"}` : ""}{p.breaker.opened_count ? `, opened ${p.breaker.opened_count} ${p.breaker.opened_count === 1 ? "time" : "times"}` : ""}. It pauses a provider after repeated failures.</li>}
              {p.models && <li className="note">Resolved ids: {Object.entries(p.models).map(([k, v]) => <span key={k}><code>{k}</code> <code>{v}</code>{" "}</span>)}</li>}
              {b && <li className="note">Start-up check: {b.ok === false ? `failed${b.missing?.length ? `, missing ${b.missing.join(", ")}` : ""}` : b.mock ? "skipped in mock mode" : "passed"}{b.t ? ` (${fmtDateTime(b.t)})` : ""}.</li>}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function Meter({ s }: { s: ModelsStatus }) {
  const [all, setAll] = useState(false);
  const rows = all ? s.meter : s.meter.slice(0, 2);
  if (s.meter.length === 0) return <EmptyState title="No model call has been metered yet" body={s.mock ? "Mock mode makes no real call, so there is nothing to meter." : "When a job calls a model, one row appears here with its counts, times and estimated cost."} />;
  return (
    <div className="stack">
      <div className="table-wrap"><table className="table">
        <caption className="u-sr-only">Every job, as the meter saw it. Response times count successful calls only.</caption>
        <thead><tr><th>Job</th><th>Model</th><th className="num">Calls</th><th className="num">Failed</th><th className="num">Median</th><th className="num">Slowest 5%</th><th className="num hide-narrow">Tokens in / out</th><th className="num">Estimated cost</th></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>
            <td>{roleLabel(r.role)}</td>
            <td><span className="u-muted">{providerName(r.provider)}</span> <code>{r.model}</code></td>
            <td className="num">{r.n}</td><td className="num">{r.failed}</td>
            <td className="num">{fmtMs(r.p50_ms)}</td><td className="num">{fmtMs(r.p95_ms)}</td>
            <td className="num hide-narrow">{r.input_tokens.toLocaleString("en-GB")} / {r.output_tokens.toLocaleString("en-GB")}</td>
            <td className="num">{fmtUsd(r.cost_usd_est)}</td>
          </tr>))}</tbody>
      </table></div>
      {s.meter.length > 2 && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${s.meter.length}`}</button></div>}
      <span className="note">Response times count successful calls only.</span>
    </div>
  );
}

function Prices({ s }: { s: ModelsStatus }) {
  const rows = Object.entries(s.prices_assumed);
  return (
    <div className="stack">
      <Note tone="warn">Every cost on this page is calls multiplied by these assumed prices. They are our own assumptions, not a price list.</Note>
      {rows.length === 0 ? <span className="note">No prices were reported.</span> : (
        <Details summary={`See the ${rows.length} assumed prices`} wide>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Provider and tier</th><th className="num">Input, per million tokens</th><th className="num">Output, per million tokens</th><th>Where the figure came from</th></tr></thead>
            <tbody>{rows.map(([k, p]) => <tr key={k}><td><code>{k}</code></td><td className="num">${p.input_usd_per_million.toFixed(2)}</td><td className="num">${p.output_usd_per_million.toFixed(2)}</td><td>{p.source === "assumed_default" ? "assumed default" : p.source.replace(/_/g, " ")}</td></tr>)}</tbody>
          </table></div>
        </Details>
      )}
    </div>
  );
}

/** The bake-off compares models on our own cases. It lives in the status when the service has one, else in the evidence report. */
function Bakeoff({ status, report }: { status: unknown; report: { sections: Record<string, unknown> } | null }) {
  const fromReport = report ? (report.sections as Record<string, unknown>).modelbench : null;
  const src = (status && typeof status === "object" ? status : fromReport) as Record<string, unknown> | null;
  const stub = src && typeof src.status === "string" && src.status !== "ok";
  const t = src ? scalarRows(src.rows ?? src.models ?? src.results) : { cols: [], rows: [] };
  return (
    <div className="stack">
      {!src || stub || t.rows.length === 0 ? (
        <EmptyState title="The bake-off has not produced results" body={<>No model is called faster or better until it has.{src && typeof src.reason === "string" && src.reason ? <Hint label="Why it has not run">{src.reason}</Hint> : null}</>} action={<a className="btn btn--secondary" href="#/evidence">See the evidence map</a>} />
      ) : (
        <div className="table-wrap"><table className="table">
          <thead><tr>{t.cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
          <tbody>{t.rows.map((r, i) => <tr key={i}>{t.cols.map((c) => <td key={c} className={r[c] !== "" && !Number.isNaN(Number(r[c])) ? "num" : undefined}>{r[c]}</td>)}</tr>)}</tbody>
        </table></div>
      )}
      {!(!src || stub || t.rows.length === 0) && <span className="note">Our own sandbox cases. Speed and accuracy claims come only from here.</span>}
    </div>
  );
}
