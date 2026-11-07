import { useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, ExampleBadge, Loading, Note, OriginBadge, PageHead, SourceNote } from "../components/common";
import { Details } from "../components/ui";
import { NoticesDataRow } from "../components/home/NoticesDataRow";
import { useToast } from "../components/Toasts";
import { IMAGE_KIND_LABEL, blockReasonLabel, callsToday, canaryReading, countLines, filterLedger, fmtBytes, imageSize, lastCallTime, purposeLabel, purposesSorted, rowClass, sentRows, sourceLabel, type LedgerFilter } from "../lib/ledger";
import { fmtDateTime } from "../lib/format";
import type { LedgerEntry, LocalModelStatus, PrivacySummary } from "../types";

/** Seven rows by default, then "Show all". */
const PAGE = 7;
const FILTERS: { id: LedgerFilter; label: string }[] = [{ id: "all", label: "Everything" }, { id: "text", label: "Text" }, { id: "images", label: "Screen frames" }, { id: "blocked", label: "Blocked" }];

export default function Privacy() {
  const ledger = useLoad(() => api.privacyLedger(), []);
  const summary = useLoad(() => api.privacySummary(), []);
  const model = useLoad(() => api.localModel(), []);
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);
  const [filter, setFilter] = useState<LedgerFilter>("all");

  if (ledger.status === "error" && !ledger.data) return <div className="page"><ErrorState error={ledger.error} retry={ledger.reload} what="the egress ledger" /></div>;
  if (!ledger.data) return <div className="page"><Loading label="Loading the egress ledger" /></div>;
  const entries = ledger.data;
  const sent = sentRows(entries).length;
  const blocked = entries.length - sent;
  const visible = filterLedger(entries, filter);
  const firstText = visible.findIndex((e) => rowClass(e) === "text"); // the newest text call opens by itself, so a first look shows what was sent
  const anyFrames = visible.slice(0, shown).some((e) => rowClass(e) !== "text");
  const localNote = summary.data?.local_only_note;

  const clear = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.privacyClear();
      const n = (r.data.cleared ?? 0) + (r.data.blocked_cleared ?? 0);
      toast({ tone: "success", text: "Ledger cleared.", detail: `${n} ${n === 1 ? "line was" : "lines were"} removed from this laptop. It does not recall anything already sent.` });
      setConfirm(false); ledger.reload(); summary.reload();
    }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not clear it. Try again."); }
    finally { setBusy(false); }
  };
  const download = async () => {
    setErr(null);
    try {
      const { text } = await api.privacyExport();
      const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
      const a = document.createElement("a");
      a.href = url; a.download = `understudy-egress-ledger-${new Date().toISOString().slice(0, 10)}.jsonl`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setErr("Could not make the file. Try again."); }
  };

  return (
    <div className="page">
      <PageHead
        eyebrow="Privacy"
        title={entries.length === 0 ? "Nothing has been sent to a model" : `${sent} ${sent === 1 ? "call" : "calls"} to a model, listed exactly as sent${blocked ? `, and ${blocked} blocked` : ""}`}
        lede="Every call to a remote model from the new features is listed here, exactly as sent. It cannot show what other software on this computer does."
        aside={<><OriginBadge meta={ledger.meta} /><ExampleBadge why={ledger.why} /></>}
      />
      <SourceNote why={ledger.why} />
      <Details summary="What this list shows">
        <div className="stack" style={{ gap: "var(--space-2)" }}>
          <p className="note">Each line has the fields and the payload as they left. A screen frame is listed by its size and a short hash only: the picture and anything read from it are never kept. A line marked mock was made in mock mode or on a test port, so nothing reached a model.</p>
        </div>
      </Details>
      {localNote && <p className="note">{localNote}</p>}

      <section className="hero" aria-labelledby="led-h">
        <div className="hero__bar">
          <h2 className="section__title" id="led-h">The egress ledger</h2>
          <div className="row">
            <button type="button" className="btn btn--secondary btn--sm" onClick={download} disabled={entries.length === 0}>Download as JSON lines</button>
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
        {confirm && <Note tone="warn">This empties the list on this laptop for good. It does not recall anything already sent, and a note of when you cleared it stays.</Note>}
        {err && <p className="field__error" role="alert">{err}</p>}
        {entries.length === 0 ? (
          <EmptyState title="The ledger is empty" body="When a feature sends something to a model, one line appears here first. You can export or clear it whenever you like." />
        ) : (
          <>
            <div className="segmented" role="group" aria-label="Show">
              {FILTERS.map((f) => <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => { setFilter(f.id); setShown(PAGE); }}>{f.label} <span className="tabular u-muted">{filterLedger(entries, f.id).length}</span></button>)}
            </div>
            {anyFrames && <p className="note" data-testid="frame-note">A screen frame is held in memory for one call and never stored. Only its size, a short hash and the result are kept.</p>}
            {visible.length === 0 ? <p className="note">Nothing in this view.</p> : (
              <ol className="ledger" aria-label="Calls, newest first">
                {visible.slice(0, shown).map((e, i) => <Row key={`${e.id ?? e.t}-${i}`} e={e} first={i === firstText} />)}
              </ol>
            )}
            {visible.length > shown && <div><button type="button" className="btn btn--quiet btn--sm" onClick={() => setShown(visible.length)}>Show all {visible.length}</button></div>}
          </>
        )}
      </section>

      <hr className="rule" />
      <div className="cols-2">
        <Summary state={summary} entries={entries} />
        <ModelStatus state={model} />
      </div>
      <hr className="rule" />
      <NoticesDataRow />
    </div>
  );
}

/** One muted line of where a call came from, how big it was and whether it was real. */
const dot = (parts: (string | null | false | undefined)[]) => parts.filter(Boolean).join(" · ");

function Row({ e, first }: { e: LedgerEntry; first: boolean }) {
  const c = rowClass(e);
  if (c === "text") {
    return (
      <li className="ledger__row">
        <div className="ledger__top">
          <span className="t-data">{fmtDateTime(e.t)}</span>
          <b className="ledger__purpose">{purposeLabel(e.purpose)}</b>
        </div>
        <p className="ledger__meta u-muted">{dot([e.model ?? "model not recorded", fmtBytes(e.bytes), e.mock && "mock, reached no model"])}</p>
        <p className="ledger__fields"><span className="t-label">Fields</span> {e.fields.map((f) => <code key={f}>{f}</code>)}</p>
        <Details summary="Payload, exactly as sent" defaultOpen={first}>
          <pre className="payload">{JSON.stringify(e.payload ?? {}, null, 2)}</pre>
        </Details>
      </li>
    );
  }
  const kind = IMAGE_KIND_LABEL[e.image?.kind ?? ""] ?? purposeLabel(e.purpose);
  if (c === "image_blocked") {
    return (
      <li className="ledger__row ledger__row--blocked" data-testid="blocked-row">
        <div className="ledger__top">
          <span className="t-data">{fmtDateTime(e.t)}</span>
          <span className="pill pill--blocked"><span className="pill__glyph-char" aria-hidden="true">✕</span>Blocked, nothing sent</span>
          <b className="ledger__purpose">{kind}</b>
        </div>
        <p className="ledger__meta u-muted">{dot([sourceLabel(e.source), e.mock && "mock"])}</p>
        <p className="ledger__fields"><span className="t-label">Why</span> {blockReasonLabel(e.reason)} <code>{e.reason ?? "unknown"}</code></p>
      </li>
    );
  }
  return (
    <li className="ledger__row">
      <div className="ledger__top">
        <span className="t-data">{fmtDateTime(e.t)}</span>
        <b className="ledger__purpose">{kind}</b>
      </div>
      <p className="ledger__meta u-muted">
        {dot([sourceLabel(e.source), imageSize(e), e.image?.sha8 ? `hash ${e.image.sha8}` : null, fmtBytes(e.image?.bytes ?? e.bytes), typeof e.latency_ms === "number" ? `${Math.round(e.latency_ms)} ms` : null, e.model ?? "model not recorded", e.status && e.status !== "ok" ? e.status : null, e.mock && "mock, reached no model"])}
      </p>
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
  const im = s.images;
  const byPurpose = purposesSorted(s.by_purpose);
  return (
    <section className="section" aria-labelledby="sum-h">
      <h2 className="section__title" id="sum-h">Summary</h2>
      <div className="stats">
        <div className="stat"><span className="stat__label">Calls in the ledger</span><span className="stat__value tabular">{s.calls}</span></div>
        <div className="stat"><span className="stat__label">Calls today</span><span className="stat__value tabular">{todayTotal}</span></div>
        <div className="stat"><span className="stat__label">Last call</span><span className="stat__value" style={{ fontSize: "var(--text-lg)" }}>{lastCallTime(s.last_call) ? fmtDateTime(lastCallTime(s.last_call)) : "none"}</span></div>
      </div>
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <span className="t-label">Calls by purpose</span>
        {byPurpose.length === 0 ? <p className="note">None.</p> : (
          <ul className="plain-list">{byPurpose.slice(0, 7).map(([p, n]) => <li key={p} className="note">{purposeLabel(p)}: <b className="tabular">{n}</b>{today[p] ? <span className="u-muted"> ({today[p]} today)</span> : null}</li>)}</ul>
        )}
        {byPurpose.length > 7 && <p className="note">And {byPurpose.length - 7} more purposes.</p>}
      </div>

      {im && (
        <div className="stack" style={{ gap: "var(--space-3)" }} data-testid="image-summary">
          <span className="t-label">Screen frames</span>
          <div className="stats">
            <div className="stat"><span className="stat__label">Sent</span><span className="stat__value tabular">{im.sent}</span><span className="stat__meta">{fmtBytes(im.bytes_sent)} in all</span></div>
            <div className="stat"><span className="stat__label">Blocked</span><span className="stat__value tabular">{im.blocked}</span><span className="stat__meta">nothing left the laptop</span></div>
          </div>
          {(countLines(im.sent_by_source, sourceLabel).length > 0 || countLines(im.blocked_by_reason, blockReasonLabel).length > 0) && (
            <Details summary="Where they came from and why some were blocked">
              <ul className="plain-list">
                {countLines(im.sent_by_source, sourceLabel).map((x) => <li key={`s-${x.key}`} className="note">Sent from {x.label.toLowerCase()}: <b className="tabular">{x.n}</b></li>)}
                {countLines(im.blocked_by_reason, blockReasonLabel).map((x) => <li key={`b-${x.key}`} className="note">Blocked, {x.label.charAt(0).toLowerCase()}{x.label.slice(1)} <b className="tabular">{x.n}</b></li>)}
              </ul>
            </Details>
          )}
        </div>
      )}

      {typeof s.mock_calls === "number" && s.mock_calls > 0 && <p className="note">{s.mock_calls} of these were made in mock mode and reached no model.</p>}
      {typeof s.blocked_attempts === "number" && s.blocked_attempts > 0 && <p className="note">The guard also refused {s.blocked_attempts} {s.blocked_attempts === 1 ? "attempt" : "attempts"} to send text. Nothing from them was sent.</p>}
      {s.cleared && s.cleared.times > 0 && <p className="note">The ledger was cleared {s.cleared.times} {s.cleared.times === 1 ? "time" : "times"}{s.cleared.last_cleared_at ? `, last on ${fmtDateTime(s.cleared.last_cleared_at)}` : ""}, removing {s.cleared.calls_removed} lines.</p>}
      <div className="canary" data-tone={c.tone} role="status">
        <span className="t-label">Canary check</span>
        <p>{c.short}</p>
        {c.text !== c.short && <Details summary="About this check"><p className="note">{c.text}</p></Details>}
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
            <span className="stat__meta">{m.mode === "model" ? (m.running ? "Running." : "Switched on but not running, so it falls back to rules.") : m.reason === "mock_mode" ? "Mock mode is on, so rules do the work." : "No model file was found, so rules do the work."}</span>
          </div>
          {m.model && (
            <Details summary="File, size and speed">
              <ul className="plain-list">
                <li className="note">File: <code>{m.model.file}</code></li>
                <li className="note">Size: {fmtBytes(m.model.size_bytes)}. Checksum: {m.model.sha_ok == null ? "not checked yet" : m.model.sha_ok ? "matches" : "does not match"}.</li>
                {m.endpoint && <li className="note">Listens on <code>{m.endpoint}</code> (this laptop only)</li>}
                {typeof m.tokens_per_s === "number" && <li className="note">Speed: <b className="tabular">{m.tokens_per_s.toFixed(1)}</b> tokens a second</li>}
              </ul>
            </Details>
          )}
        </div>
      )}
    </section>
  );
}
