import { Suspense, lazy, useState, type ComponentType } from "react";
import { ApiError, api } from "../../api";
import { IMAGE_KIND_LABEL, blockReasonLabel, canaryReading, fmtBytes, imageSize, purposeLabel, rowClass, sentRows, sourceLabel } from "../../lib/ledger";
import { fmtDateTime } from "../../lib/format";
import type { LedgerEntry, PrivacySummary } from "../../types";
import { KV } from "../needsyou/KV";
import { useToast } from "../Toasts";
import { ConfirmRow, Details } from "../ui";

const SHOWN = 4;
const dot = (parts: (string | null | false | undefined)[]) => parts.filter(Boolean).join(" · ");
const text = (v: unknown, max = 80): string => { const s = String(v ?? ""); return s.length > max ? `${s.slice(0, max)}…` : s; };

/** The Connections track fills this slot with what each connection has read. Shown only when its file exists; it never blocks the list. */
const CONNECTION_READS = import.meta.glob("../connections/ConnectionReads.tsx");
const ConnectionReads = Object.values(CONNECTION_READS)[0] ? lazy(Object.values(CONNECTION_READS)[0] as () => Promise<{ default: ComponentType }>) : null;

/**
 * What Knack looked at or sent: every call to a remote model, listed exactly as sent, one line each (a screen frame by its size and a short hash only: the
 * picture is never kept). ONE short paragraph says what the list cannot show; ONE row of actions exports or forgets it; the payload of each call, the
 * canary check and the counts of what was refused sit behind closed disclosures. Entries may be missing fields.
 */
export function Sent({ entries: all, summary, onChanged }: { entries: LedgerEntry[]; summary: PrivacySummary | null; onChanged: () => void }) {
  const toast = useToast();
  const entries = Array.isArray(all) ? all.filter((e) => e && typeof e === "object") : [];
  const [showAll, setShowAll] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const sent = sentRows(entries).length;
  const blocked = entries.length - sent;
  const shown = showAll ? entries.slice(0, 200) : entries.slice(0, SHOWN);
  const frames = entries.some((e) => rowClass(e) !== "text");
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
      const { text: body } = await api.privacyExport();
      const url = URL.createObjectURL(new Blob([body], { type: "application/x-ndjson" }));
      const a = document.createElement("a");
      a.href = url; a.download = `knack-model-calls-${new Date().toISOString().slice(0, 10)}.jsonl`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setErr("Could not make the file. Nothing was changed."); }
  };

  return (
    <div className="yd-body" data-testid="sent">
      <p className="kc-sub" data-testid="sent-limit">Every call from Knack is listed. It cannot show what other software on this computer does.{frames ? " A screen picture is held in memory for one call and never stored." : ""}</p>
      {entries.length === 0 ? <p className="kc-row__body" style={{ margin: 0 }}>Nothing has been sent to a model.</p> : <KV label="Model calls" rows={[["Model calls", `${sent} sent${blocked ? `, ${blocked} blocked` : ""}`]]} />}
      {entries.length > 0 && (
        <ol className="kc-list ledger" aria-label="Calls, newest first">
          {shown.map((e, i) => <Row key={`${e.id ?? e.t}-${i}`} e={e} />)}
        </ol>
      )}
      {ConnectionReads && <Suspense fallback={null}><ConnectionReads /></Suspense>}
      <div className="row">
        {entries.length > SHOWN && <button type="button" className="btn btn--secondary btn--sm" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>{showAll ? "Show fewer" : `Show all ${entries.length}`}</button>}
        <button type="button" className="btn btn--secondary btn--sm" disabled={entries.length === 0} onClick={() => void download()}>Export as JSON lines</button>
        {!confirm && <button type="button" className="btn btn--secondary btn--sm" disabled={entries.length === 0} onClick={() => setConfirm(true)}>Forget</button>}
      </div>
      {showAll && entries.length > 200 && <p className="kc-sub">The newest 200 of {entries.length} are shown. Export has them all.</p>}
      {confirm && (
        <ul className="kc-list"><ConfirmRow question={`Forget ${entries.length} ${entries.length === 1 ? "record" : "records"}?`} consequence="This empties the list on this laptop for good. It does not recall anything already sent, and a note of when you cleared it stays."
          confirmLabel={busy ? "Forgetting" : "Forget it"} busy={busy} onConfirm={() => void clear()} onCancel={() => setConfirm(false)} /></ul>
      )}
      {err && <p className="kc-error" role="alert">{err}</p>}
      {(c || summary?.local_only_note) && (
        <Details summary="More">
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {summary?.local_only_note && <p className="kc-sub">{summary.local_only_note}</p>}
            {c && <p className="kc-sub" data-testid="canary">{c.text}</p>}
            {summary && (summary.blocked_attempts ?? 0) > 0 && <p className="kc-sub">The guard also refused {summary.blocked_attempts} {summary.blocked_attempts === 1 ? "attempt" : "attempts"} to send text. Nothing from them was sent.</p>}
            {summary && (summary.mock_calls ?? 0) > 0 && <p className="kc-sub">{summary.mock_calls} of these were made on example data and reached no model.</p>}
          </div>
        </Details>
      )}
    </div>
  );
}

function Row({ e }: { e: LedgerEntry }) {
  const c = rowClass(e);
  const when = e.t ? fmtDateTime(e.t) : "time unknown";
  if (c === "text") {
    const fields = Array.isArray(e.fields) ? e.fields : [];
    return (
      <li className="ledger__row yd-call">
        <p className="yd-call__top"><span className="t-data">{when}</span> <b>{purposeLabel(e.purpose ?? "")}</b> <span className="u-muted">{dot([text(e.model ?? "model not recorded", 40), fmtBytes(e.bytes), e.mock && "example data, reached no model"])}</span></p>
        <Details summary="Payload, exactly as sent">
          {fields.length > 0 && <p className="kc-sub">{fields.map((f) => <code key={f}>{f}</code>)}</p>}
          <pre className="payload">{JSON.stringify(e.payload ?? {}, null, 2)}</pre>
        </Details>
      </li>
    );
  }
  const kind = IMAGE_KIND_LABEL[e.image?.kind ?? ""] ?? purposeLabel(e.purpose ?? "");
  if (c === "image_blocked") {
    return (
      <li className="ledger__row yd-call" data-testid="blocked-row">
        <p className="yd-call__top"><span className="t-data">{when}</span> <b>{kind}</b> <span className="u-muted">{dot(["Blocked, nothing sent", sourceLabel(e.source), blockReasonLabel(e.reason)])}</span></p>
      </li>
    );
  }
  return (
    <li className="ledger__row yd-call">
      <p className="yd-call__top"><span className="t-data">{when}</span> <b>{kind}</b> <span className="u-muted">{dot([sourceLabel(e.source), imageSize(e), e.image?.sha8 ? `hash ${e.image.sha8}` : null, fmtBytes(e.image?.bytes ?? e.bytes), typeof e.latency_ms === "number" ? `${Math.round(e.latency_ms)} ms` : null, text(e.model ?? "model not recorded", 40), e.status && e.status !== "ok" ? e.status : null, e.mock && "example data, reached no model"])}</span></p>
    </li>
  );
}
