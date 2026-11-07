import { useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, Loading, OriginBadge, PageHead } from "../components/common";
import { useToast } from "../components/Toasts";
import { callsToday, canaryReading, exportLedger, fmtBytes, purposeLabel, purposesSorted } from "../lib/ledger";
import { fmtDateTime } from "../lib/format";
import type { LedgerEntry, LocalModelStatus, PrivacySummary } from "../types";

const PAGE = 20;

export default function Privacy() {
  const ledger = useLoad(() => api.privacyLedger(), []);
  const summary = useLoad(() => api.privacySummary(), []);
  const model = useLoad(() => api.localModel(), []);
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);

  if (ledger.status === "error" && !ledger.data) return <div className="page"><ErrorState error={ledger.error} retry={ledger.reload} what="the egress ledger" /></div>;
  if (!ledger.data) return <div className="page"><Loading label="Loading the egress ledger" /></div>;
  const entries = ledger.data;

  const clear = async () => {
    setBusy(true); setErr(null);
    try { await api.privacyClear(); toast({ tone: "success", text: "Ledger cleared.", detail: "This empties the list on this laptop. It does not recall anything already sent." }); setConfirm(false); ledger.reload(); summary.reload(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not clear it. Try again."); }
    finally { setBusy(false); }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([exportLedger(entries)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = `understudy-egress-ledger-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="page">
      <PageHead
        eyebrow="Privacy"
        title={entries.length === 0 ? "Nothing has been sent to a model" : `${entries.length} ${entries.length === 1 ? "call" : "calls"} to a model, listed exactly as sent`}
        lede="Every call to a remote model from the new features is written down here, with the fields and the payload as they left. Calls for steps you asked for are listed too. This list cannot show what other software on this computer does."
        aside={<OriginBadge meta={ledger.meta} />}
      />

      <section className="hero" aria-labelledby="led-h">
        <div className="hero__bar">
          <h2 className="section__title" id="led-h">The egress ledger</h2>
          <div className="row">
            <button type="button" className="btn btn--secondary btn--sm" onClick={download} disabled={entries.length === 0}>Download as JSON</button>
            {confirm ? (
              <>
                <button type="button" className="btn btn--danger btn--sm" disabled={busy} onClick={clear}>{busy ? "Clearing" : "Yes, clear the list"}</button>
                <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirm(false)}>Keep it</button>
              </>
            ) : (
              <button type="button" className="btn btn--secondary btn--sm" disabled={entries.length === 0} onClick={() => setConfirm(true)}>Clear the ledger</button>
            )}
          </div>
        </div>
        {err && <p className="field__error" role="alert">{err}</p>}
        {entries.length === 0 ? (
          <EmptyState title="The ledger is empty" body="When a feature sends something to a model, one line appears here before anything else happens. You can export it or clear it whenever you like." />
        ) : (
          <>
            <ol className="ledger" aria-label="Calls, newest first">
              {entries.slice(0, shown).map((e, i) => <Row key={`${e.t}-${i}`} e={e} first={i === 0} />)}
            </ol>
            {entries.length > shown && <div><button type="button" className="btn btn--quiet btn--sm" onClick={() => setShown((n) => n + PAGE)}>Show {Math.min(PAGE, entries.length - shown)} more</button></div>}
          </>
        )}
      </section>

      <hr className="rule" />
      <div className="cols-2">
        <Summary state={summary} entries={entries} />
        <ModelStatus state={model} />
      </div>
    </div>
  );
}

function Row({ e, first }: { e: LedgerEntry; first: boolean }) {
  return (
    <li className="ledger__row">
      <div className="ledger__top">
        <span className="t-data">{fmtDateTime(e.t)}</span>
        <span className="pill">{purposeLabel(e.purpose)}</span>
        <span className="t-data u-muted">{e.model} · {fmtBytes(e.bytes)}</span>
      </div>
      <p className="ledger__fields"><span className="t-label">Fields</span> {e.fields.map((f) => <code key={f}>{f}</code>)} <span className="u-muted">· schema {e.schema}</span></p>
      <details className="details-lite" open={first}>
        <summary>Payload, exactly as sent</summary>
        <pre className="payload">{JSON.stringify(e.payload, null, 2)}</pre>
      </details>
    </li>
  );
}

function Summary({ state, entries }: { state: ReturnType<typeof useLoad<PrivacySummary>>; entries: LedgerEntry[] }) {
  if (state.status === "error" && !state.data) return <ErrorState error={state.error} retry={state.reload} what="the summary" />;
  if (!state.data) return <Loading label="Loading the summary" />;
  const s = state.data;
  const today = callsToday(entries);
  const todayTotal = Object.values(today).reduce((a, b) => a + b, 0);
  const c = canaryReading(s.canary);
  return (
    <section className="section" aria-labelledby="sum-h">
      <h2 className="section__title" id="sum-h">Summary</h2>
      <div className="stats">
        <div className="stat"><span className="stat__label">Calls in the ledger</span><span className="stat__value tabular">{s.calls}</span></div>
        <div className="stat"><span className="stat__label">Calls today</span><span className="stat__value tabular">{todayTotal}</span></div>
        <div className="stat"><span className="stat__label">Last call</span><span className="stat__value" style={{ fontSize: "var(--text-lg)" }}>{s.last_call ? fmtDateTime(s.last_call) : "none"}</span></div>
      </div>
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <span className="t-label">Calls by purpose</span>
        {purposesSorted(s.by_purpose).length === 0 ? <p className="note">None.</p> : (
          <ul className="plain-list">{purposesSorted(s.by_purpose).map(([p, n]) => <li key={p} className="note">{purposeLabel(p)}: <b className="tabular">{n}</b>{today[p] ? <span className="u-muted"> ({today[p]} today)</span> : null}</li>)}</ul>
        )}
      </div>
      <p className="note">{s.local_only_note}</p>
      <div className="canary" data-tone={c.tone} role="status">
        <span className="t-label">Canary check</span>
        <p>{c.text}</p>
      </div>
    </section>
  );
}

function ModelStatus({ state }: { state: ReturnType<typeof useLoad<LocalModelStatus>> }) {
  if (state.status === "error" && !state.data) return <ErrorState error={state.error} retry={state.reload} what="the local model status" />;
  if (!state.data) return <Loading label="Loading the local model status" />;
  const m = state.data;
  return (
    <section className="section" aria-labelledby="lm-h">
      <h2 className="section__title" id="lm-h">Local model</h2>
      {!m.enabled ? (
        <p className="note">The local model is switched off. Digests, if any, come from fixed rules.</p>
      ) : (
        <div className="stack">
          <div className="stat">
            <span className="stat__label">Digests are made by</span>
            <span className="stat__value" style={{ fontSize: "var(--text-xl)" }}>{m.mode === "model" ? "A model on this laptop" : "Fixed rules"}</span>
            <span className="stat__meta">{m.mode === "model" ? (m.running ? "Running." : "Switched on but not running, so it falls back to rules.") : "No model file was found, so rules do the work. That is slower to adapt but needs nothing else."}</span>
          </div>
          {m.model && (
            <ul className="plain-list">
              <li className="note">File: <code>{m.model.file}</code></li>
              <li className="note">Size: {fmtBytes(m.model.size_bytes)}. Checksum: {m.model.sha_ok ? "matches" : "does not match"}.</li>
              {m.endpoint && <li className="note">Listens on <code>{m.endpoint}</code> (this laptop only)</li>}
              {typeof m.tokens_per_s === "number" && <li className="note">Speed: <b className="tabular">{m.tokens_per_s.toFixed(1)}</b> tokens a second</li>}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
