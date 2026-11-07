import { useState } from "react";
import { ApiError, api, refreshQueueBadge } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, Loading, OriginBadge, PageHead, TierPill } from "../components/common";
import { useToast } from "../components/Toasts";
import { fmtDateTime, fmtTime, plural } from "../lib/format";
import type { AuditLine, OffhoursReport, QueueItem } from "../types";

const RISK: Record<QueueItem["risk_class"], string> = { irreversible: "Cannot be undone", outward: "Reaches outside", normal: "Review" };
const KIND: Record<QueueItem["kind"], string> = {
  irreversible_step: "Waiting at an irreversible step",
  outward_step: "Waiting at an outward step",
  batch_result: "Finished batch",
  injection_pause: "Paused for safety",
  shadow_mismatch: "Shadow run disagreed",
};

function labels(kind: QueueItem["kind"]): { yes: string; no: string } {
  switch (kind) {
    case "irreversible_step": return { yes: "Approve and submit", no: "Reject" };
    case "outward_step": return { yes: "Approve and send", no: "Reject" };
    case "injection_pause": return { yes: "Resume the run", no: "Cancel the run" };
    case "shadow_mismatch": return { yes: "Accept the routine's answer", no: "Keep my answer" };
    default: return { yes: "Approve", no: "Reject" };
  }
}

export default function Queue() {
  const q = useLoad(() => api.queue("all"), []);
  const rep = useLoad(() => api.offhoursReport(), []);
  const audit = useLoad(() => api.audit(20), []);

  if (q.status === "error" && !q.data) return <div className="page"><ErrorState error={q.error} retry={q.reload} what="the queue" /></div>;
  if (!q.data) return <div className="page"><Loading label="Loading the queue" /></div>;
  const pending = q.data.filter((x) => x.status === "pending");
  const decided = q.data.filter((x) => x.status !== "pending");

  return (
    <div className="page">
      <PageHead
        eyebrow="Queue"
        title={pending.length === 0 ? "Nothing is waiting for you" : pending.length === 1 ? "One thing needs your approval" : `${pending.length} things need your approval`}
        lede="Routines ran inside their limits while you were away. Anything that cannot be undone, or that reaches outside, waits here for one click from you."
        aside={<OriginBadge meta={q.meta} />}
      />

      {pending.length === 0 ? (
        <EmptyState title="All clear" body="When a routine reaches a step it may not take alone, it stops and a card appears here with the evidence." />
      ) : (
        <section className="queue-list" aria-label="Waiting for approval">
          {pending.map((it) => <Card key={it.id} item={it} onDone={() => { q.reload(); void refreshQueueBadge(); }} />)}
        </section>
      )}

      {decided.length > 0 && (
        <section className="section" aria-labelledby="dec-h">
          <h2 id="dec-h" className="section__title">Decided</h2>
          <div className="queue-list">
            {decided.map((it) => <Card key={it.id} item={it} onDone={() => undefined} />)}
          </div>
        </section>
      )}

      <hr className="rule" />
      <Report rep={rep.data} audit={audit.data} loading={rep.status === "loading" && !rep.data} />
    </div>
  );
}

function Card({ item: it, onDone }: { item: QueueItem; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const L = labels(it.kind);
  const decide = async (a: "approve" | "reject") => {
    setBusy(a); setErr(null);
    try {
      await api.setQueue(it.id, a);
      toast({ tone: "success", text: a === "approve" ? `${L.yes}: done.` : `${L.no}: done.`, detail: it.title });
      onDone();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Try again."); }
    finally { setBusy(null); }
  };
  const decided = it.status !== "pending";
  const diff = (it.evidence.diff ?? []) as { field: string; expected: string; got: string }[];
  const keys = Array.from(new Set([...Object.keys(it.evidence.extracted ?? {}), ...Object.keys(it.evidence.expected ?? {})]));
  return (
    <article className="queue-item" data-status={it.status} aria-labelledby={`q-${it.id}`}>
      <div className="queue-item__head">
        <h3 className="queue-item__title" id={`q-${it.id}`}>{it.title}</h3>
        <span className="queue-item__when">{fmtDateTime(it.created_at)} · run {it.run_id}</span>
      </div>
      <div className="row">
        <span className="pill" style={it.risk_class === "irreversible" ? { borderColor: "var(--bad)" } : undefined}>{RISK[it.risk_class]}</span>
        <span className="pill">{KIND[it.kind]}</span>
        {it.routine_id && <span className="pill">{it.routine_id}</span>}
      </div>
      <div className="queue-item__ask"><span>{it.summary}</span></div>
      <details className="evidence">
        <summary>Evidence</summary>
        <div className="evidence__body qi-evidence">
          {it.evidence.screenshots.length > 0 && (
            <div className="shots" aria-label="Screenshots">
              {it.evidence.screenshots.map((s) => <span key={s} className="shot">{s.split("/").pop()}<br />screenshot kept on this device</span>)}
            </div>
          )}
          {keys.length > 0 && (
            <div className="kv" role="table" aria-label="What the run found against what was expected">
              <span className="t-label">Field</span><span className="t-label">Found</span><span className="t-label">Expected</span>
              {keys.map((k) => {
                const got = String(it.evidence.extracted?.[k] ?? "");
                const exp = it.evidence.expected?.[k];
                const bad = exp != null && String(exp) !== got;
                return (<span key={k} style={{ display: "contents" }}><span className="kv__k">{k}</span><span className={bad ? "kv__bad" : ""}>{got || "none"}</span><span>{exp != null ? String(exp) : "not set"}</span></span>);
              })}
            </div>
          )}
          {diff.length > 0 && <p className="note"><b>Difference:</b> {diff.map((d) => `${d.field}: expected ${d.expected}, got ${d.got}`).join("; ")}</p>}
          {it.evidence.tier_log.length > 0 && (
            <div className="row" aria-label="Which tier ran each step">{it.evidence.tier_log.map((t) => <TierPill key={t.step} tier={t.tier} step={t.step} />)}</div>
          )}
        </div>
      </details>
      {err && <p className="field__error" role="alert">{err}</p>}
      {decided ? (
        <p className="note">{it.status === "approved" ? "Approved" : it.status === "rejected" ? "Rejected" : "Expired"} {it.decided_at ? `at ${fmtTime(it.decided_at)}` : ""}{it.decided_by ? ` by ${it.decided_by}` : ""}.</p>
      ) : (
        <div className="queue-item__foot">
          <button type="button" className="btn btn--primary" disabled={!!busy} onClick={() => decide("approve")}>{busy === "approve" ? "Working" : L.yes}</button>
          <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => decide("reject")}>{busy === "reject" ? "Working" : L.no}</button>
        </div>
      )}
    </article>
  );
}

function Report({ rep, audit, loading }: { rep: OffhoursReport | null; audit: AuditLine[] | null; loading: boolean }) {
  if (loading) return <Loading label="Loading the morning report" />;
  if (!rep) return null;
  return (
    <section className="report" aria-labelledby="rep-h">
      <div className="stack">
        <h2 className="section__title" id="rep-h">What ran while you were away</h2>
        <p className="tally">
          <span>{plural(rep.ran.length, "run")} finished</span>
          <span>{rep.queued.length} waiting for you</span>
          <span>{plural(rep.failed.length, "failure")}</span>
          <span>{plural(rep.yielded.length, "yield")} when you came back</span>
        </p>
      </div>
      {rep.ran.length > 0 && (
        <div className="stack"><p className="t-label">Ran</p>
          <ul>{rep.ran.map((r) => <li key={r.run_id}><b>{r.routine}</b><span>{r.outcome}</span><span className="t-data">{r.minutes} min</span><TierPill tier={r.tier} /></li>)}</ul></div>
      )}
      {rep.failed.length > 0 && (
        <div className="stack"><p className="t-label">Failed</p>
          <ul>{rep.failed.map((r, i) => <li key={i}><b>{r.routine}</b><span>{r.reason}</span></li>)}</ul></div>
      )}
      {rep.yielded.length > 0 && (
        <div className="stack"><p className="t-label">Stepped aside for you</p>
          <ul>{rep.yielded.map((r, i) => <li key={i}><b>{r.routine}</b><span>paused when you came back at {fmtTime(r.at)}</span></li>)}</ul></div>
      )}
      {audit && audit.length > 0 && (
        <details className="details-lite">
          <summary>Audit log (redacted, no page text)</summary>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Time</th><th>Who</th><th>What</th><th>Outcome</th><th>Note</th></tr></thead>
            <tbody>{audit.map((a, i) => <tr key={i}><td className="t-data">{fmtTime(a.t)}</td><td>{a.actor}</td><td>{a.kind.replace(/_/g, " ")}{a.routine ? ` · ${a.routine}` : ""}</td><td>{a.outcome}</td><td>{a.note}</td></tr>)}</tbody>
          </table></div>
        </details>
      )}
    </section>
  );
}
