import { Suspense, lazy, useState, type ComponentType } from "react";
import { ApiError, api } from "../../api";
import { IMAGE_KIND_LABEL, blockReasonLabel, canaryReading, fmtBytes, imageSize, purposeLabel, rowClass, sentRows, sourceLabel } from "../../lib/ledger";
import { fmtDateTime } from "../../lib/format";
import type { LedgerEntry, PrivacySummary } from "../../types";
import { useToast } from "../Toasts";
import { ConfirmRow, Details } from "../ui";

const SHOWN = 4;
const dot = (parts: (string | null | false | undefined)[]) => parts.filter(Boolean).join(" · ");

/** The Connections track fills this slot with what each connection has read. Shown only when its file exists; it never blocks the list. */
const CONNECTION_READS = import.meta.glob("../connections/ConnectionReads.tsx");
const ConnectionReads = Object.values(CONNECTION_READS)[0] ? lazy(Object.values(CONNECTION_READS)[0] as () => Promise<{ default: ComponentType }>) : null;

/**
 * What Knack looked at or sent: every call to a remote model, listed exactly as sent (a screen frame by its size and a short hash only: the picture is
 * never kept). The limit is printed: the list cannot show what other software on this computer does. Export it, or forget it with the same inline confirm.
 */
export function Sent({ entries, summary, onChanged }: { entries: LedgerEntry[]; summary: PrivacySummary | null; onChanged: () => void }) {
  const toast = useToast();
  const [all, setAll] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const sent = sentRows(entries).length;
  const blocked = entries.length - sent;
  const shown = all ? entries : entries.slice(0, SHOWN);
  const firstText = shown.findIndex((e) => rowClass(e) === "text");
  const c = summary ? canaryReading(summary.canary) : null;

  const clear = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.privacyClear();
      const n = (r.data.cleared ?? 0) + (r.data.blocked_cleared ?? 0);
      toast({ tone: "success", text: "Forgotten.", detail: `${n} ${n === 1 ? "record was" : "records were"} removed from this laptop. It does not recall anything already sent.` });
      setConfirm(false); onChanged();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not forget it. Nothing was changed."); }
    finally { setBusy(false); }
  };
  const download = async () => {
    setErr(null);
    try {
      const { text } = await api.privacyExport();
      const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
      const a = document.createElement("a");
      a.href = url; a.download = `knack-model-calls-${new Date().toISOString().slice(0, 10)}.jsonl`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setErr("Could not make the file. Nothing was changed."); }
  };

  return (
    <div className="yd-body" data-testid="sent">
      <p className="kc-row__body" style={{ margin: 0 }}>{entries.length === 0 ? "Nothing has been sent to a model." : `${sent} ${sent === 1 ? "call" : "calls"} to a model, listed exactly as sent${blocked ? `, and ${blocked} blocked` : ""}.`}</p>
      <p className="kc-sub" data-testid="sent-limit">Every call from Knack is listed. It cannot show what other software on this computer does.</p>
      {summary?.local_only_note && <p className="kc-sub">{summary.local_only_note}</p>}
      {entries.length > 0 && (
        <ol className="kc-list ledger" aria-label="Calls, newest first">
          {shown.map((e, i) => <Row key={`${e.id ?? e.t}-${i}`} e={e} first={i === firstText} />)}
        </ol>
      )}
      {entries.length > SHOWN && <div><button type="button" className="btn btn--secondary btn--sm" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${entries.length}`}</button></div>}
      {ConnectionReads && <Suspense fallback={null}><ConnectionReads /></Suspense>}
      <div className="row">
        <button type="button" className="btn btn--secondary btn--sm" disabled={entries.length === 0} onClick={() => void download()}>Export as JSON lines</button>
        {!confirm && <button type="button" className="btn btn--secondary btn--sm" disabled={entries.length === 0} onClick={() => setConfirm(true)}>Forget</button>}
      </div>
      {confirm && (
        <ul className="kc-list"><ConfirmRow question={`Forget ${entries.length} ${entries.length === 1 ? "record" : "records"}?`} consequence="This empties the list on this laptop for good. It does not recall anything already sent, and a note of when you cleared it stays."
          confirmLabel={busy ? "Forgetting" : "Forget it"} busy={busy} onConfirm={() => void clear()} onCancel={() => setConfirm(false)} /></ul>
      )}
      {err && <p className="kc-error" role="alert">{err}</p>}
      {c && (
        <Details summary="How this is checked">
          <p className="kc-sub" data-testid="canary">{c.text}</p>
          {summary && (summary.blocked_attempts ?? 0) > 0 && <p className="kc-sub">The guard also refused {summary.blocked_attempts} {summary.blocked_attempts === 1 ? "attempt" : "attempts"} to send text. Nothing from them was sent.</p>}
          {summary && (summary.mock_calls ?? 0) > 0 && <p className="kc-sub">{summary.mock_calls} of these were made on example data and reached no model.</p>}
        </Details>
      )}
    </div>
  );
}

function Row({ e, first }: { e: LedgerEntry; first: boolean }) {
  const c = rowClass(e);
  if (c === "text") {
    return (
      <li className="ledger__row yd-call">
        <p className="yd-call__top"><span className="t-data">{fmtDateTime(e.t)}</span> <b>{purposeLabel(e.purpose)}</b></p>
        <p className="kc-sub">{dot([e.model ?? "model not recorded", fmtBytes(e.bytes), e.mock && "example data, reached no model"])}</p>
        <Details summary="Payload, exactly as sent" defaultOpen={first}>
          <p className="kc-sub">{e.fields.map((f) => <code key={f}>{f}</code>)}</p>
          <pre className="payload">{JSON.stringify(e.payload ?? {}, null, 2)}</pre>
        </Details>
      </li>
    );
  }
  const kind = IMAGE_KIND_LABEL[e.image?.kind ?? ""] ?? purposeLabel(e.purpose);
  if (c === "image_blocked") {
    return (
      <li className="ledger__row yd-call" data-testid="blocked-row">
        <p className="yd-call__top"><span className="t-data">{fmtDateTime(e.t)}</span> <b>{kind}</b> Blocked, nothing sent.</p>
        <p className="kc-sub">{dot([sourceLabel(e.source), blockReasonLabel(e.reason)])}</p>
      </li>
    );
  }
  return (
    <li className="ledger__row yd-call">
      <p className="yd-call__top"><span className="t-data">{fmtDateTime(e.t)}</span> <b>{kind}</b></p>
      <p className="kc-sub">{dot([sourceLabel(e.source), imageSize(e), e.image?.sha8 ? `hash ${e.image.sha8}` : null, fmtBytes(e.image?.bytes ?? e.bytes), typeof e.latency_ms === "number" ? `${Math.round(e.latency_ms)} ms` : null, e.model ?? "model not recorded", e.status && e.status !== "ok" ? e.status : null, e.mock && "example data, reached no model"])}</p>
      <p className="kc-sub" data-testid="frame-note">The picture is held in memory for one call and never stored. Only its size, a short hash and the result are kept.</p>
    </li>
  );
}
