import { useState } from "react";
import { fmtTime } from "../../lib/format";
import { plainDuration, plainWords, routineName } from "../../screens/NeedsYou/model";
import type { AuditLine, OffhoursReport } from "../../types";
import { Details } from "../ui";
import { Glyph } from "./Glyph";
import { KV } from "./KV";

const clip = (v: unknown, max = 80): string => { const s = plainWords(String(v ?? "")); return s.length > max ? `${s.slice(0, max)}…` : s; };
const arr = <T,>(x: T[] | null | undefined): T[] => (Array.isArray(x) ? x : []);

/**
 * What ran while the worker was away, opened from one link: the sentence, the tally and what ran, failed and stepped aside as label and value (one line each),
 * and under one closed "More" the audit log (redacted, no page text). Every list may be missing.
 */
export function AwayDetails({ rep, audit, line }: { rep: OffhoursReport; audit: AuditLine[] | null; line: string }) {
  const [open, setOpen] = useState(false);
  const ran = arr(rep.ran), failed = arr(rep.failed), yielded = arr(rep.yielded), queued = arr(rep.queued);
  const log = arr(audit);
  return (
    <section className="kc-foot" aria-label="Since you left">
      <button type="button" className="kc-link" style={{ padding: "0 var(--space-1)" }} aria-expanded={open} aria-controls="away-details" onClick={() => setOpen((v) => !v)}>Since you left<Glyph name="chevron" /></button>
      {open && (
        <div className="kc-panel" id="away-details" style={{ marginTop: "var(--space-3)" }}>
          <p data-testid="away-line"><b>{line}</b></p>
          <KV label="While you were away" rows={[
            ...ran.slice(0, 5).map((r, i): [string, string] => [ran.length > 1 ? `Ran ${i + 1}` : "Ran", [clip(routineName(r.routine), 60), clip(r.outcome, 40), plainDuration(r.minutes)].filter(Boolean).join(", ")]),
            ...failed.slice(0, 5).map((r, i): [string, string] => [failed.length > 1 ? `Failed ${i + 1}` : "Failed", `${clip(routineName(r.routine), 60)}, ${clip(r.reason, 80)}`]),
            ...yielded.slice(0, 5).map((r, i): [string, string] => [yielded.length > 1 ? `Paused to let you work ${i + 1}` : "Paused to let you work", `${clip(routineName(r.routine), 60)}, when you came back at ${fmtTime(r.at)}`]),
            ["Waiting for you", queued.length ? String(queued.length) : null],
          ]} />
          {log.length > 0 && (
            <Details summary="More" wide>
              <p className="kc-label">Audit log (redacted, no page text)</p>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Time</th><th>Who</th><th>What</th><th>Outcome</th><th>Note</th></tr></thead>
                <tbody>{log.map((a, i) => <tr key={i}><td className="t-data">{fmtTime(a.t)}</td><td>{clip(a.actor, 20)}</td><td>{clip(String(a.kind ?? "").replace(/_/g, " "), 40)}{a.routine ? ` · ${clip(a.routine, 40)}` : ""}</td><td>{clip(a.outcome, 40)}</td><td>{clip(a.note, 80)}</td></tr>)}</tbody>
              </table></div>
            </Details>
          )}
        </div>
      )}
    </section>
  );
}
