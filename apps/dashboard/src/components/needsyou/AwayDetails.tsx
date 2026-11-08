import { useState } from "react";
import { fmtTime } from "../../lib/format";
import { plural } from "../../lib/format";
import type { AuditLine, OffhoursReport } from "../../types";
import { TierPill } from "../common";
import { Glyph } from "./Glyph";

/** What ran while the worker was away: the tally, the ran, failed and stepped-aside lists, and the audit log (redacted, no page text). Behind "Details". */
export function AwayDetails({ rep, audit, line }: { rep: OffhoursReport; audit: AuditLine[] | null; line: string }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="kc-foot" aria-label="Since you were away">
      <button type="button" className="kc-link" style={{ padding: "0 var(--space-1)" }} aria-expanded={open} aria-controls="away-details" onClick={() => setOpen((v) => !v)}>Since you left<Glyph name="chevron" /></button>
      {open && (
        <div className="kc-panel" id="away-details" style={{ marginTop: "var(--space-3)" }}>
          <p data-testid="away-line"><b>{line}</b></p>
          <p>{plural(rep.ran.length, "run")} finished, {rep.queued.length} waiting for you, {plural(rep.failed.length, "failure")}, {rep.yielded.length} stepped aside when you came back.</p>
          {rep.ran.length > 0 && (
            <div><p className="kc-label">Ran</p>
              <ul className="plain-list">{rep.ran.map((r, i) => <li key={`${r.run_id}-${i}`}><b>{r.routine}</b> {r.outcome} <span className="t-data">{r.minutes} min</span> <TierPill tier={r.tier} /></li>)}</ul></div>
          )}
          {rep.failed.length > 0 && (
            <div><p className="kc-label">Failed</p>
              <ul className="plain-list">{rep.failed.map((r, i) => <li key={i}><b>{r.routine}</b> {r.reason}</li>)}</ul></div>
          )}
          {rep.yielded.length > 0 && (
            <div><p className="kc-label">Stepped aside for you</p>
              <ul className="plain-list">{rep.yielded.map((r, i) => <li key={i}><b>{r.routine}</b> paused when you came back at {fmtTime(r.at)}</li>)}</ul></div>
          )}
          {audit && audit.length > 0 && (
            <div>
              <p className="kc-label">Audit log (redacted, no page text)</p>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Time</th><th>Who</th><th>What</th><th>Outcome</th><th>Note</th></tr></thead>
                <tbody>{audit.map((a, i) => <tr key={i}><td className="t-data">{fmtTime(a.t)}</td><td>{a.actor}</td><td>{a.kind.replace(/_/g, " ")}{a.routine ? ` · ${a.routine}` : ""}</td><td>{a.outcome}</td><td>{a.note}</td></tr>)}</tbody>
              </table></div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
