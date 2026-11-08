import { useState } from "react";
import { ApiError, api } from "../../api";
import { authForApproval, needsStepUp, stepUpNotice, useAuth } from "../../auth";
import { approvalLabels, consequence, leadAndRest, plainWords } from "../../screens/NeedsYou/model";
import { clip, whenText } from "../../lib/safeText";
import type { QueueItem } from "../../types";
import { useToast } from "../Toasts";
import { Evidence } from "./Evidence";
import { Glyph } from "./Glyph";

/**
 * One approval: what it is, what it does if you say yes (printed), and a real click. No keystroke approves: there is no shortcut and no key handler
 * here; a button pressed with the keyboard is an ordinary click on that button. The first approval in the list carries the one primary button.
 */
export function ApprovalRow({ item: it, primary, cls, onDone }: { item: QueueItem; primary: boolean; cls: number; onDone: () => void }) {
  const toast = useToast();
  const auth = useAuth();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [signing, setSigning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const L = approvalLabels(it.kind);
  const stepUp = auth.enabled && needsStepUp(it.risk_class);
  const cons = consequence(it.risk_class);
  const { lead, rest } = leadAndRest(it.summary, it.kind === "injection_pause" ? 20 : 16)   // a pause for safety prints what it did and what it did not change, whole;
  const title = plainWords(clip(it.title, 160)) || "An approval";

  const decide = async (a: "approve" | "reject") => {
    setBusy(a); setErr(null);
    try {
      let proof;
      if (a === "approve") {
        // Irreversible and outward items need a fresh sign-in when Auth0 is on. Without it, nothing is approved.
        if (stepUp) setSigning(true);
        const gate = await authForApproval(auth, it.risk_class);
        setSigning(false);
        if (!gate.allowed) { setErr(gate.message); return; }
        proof = gate.auth;
      }
      const res = await api.setQueue(it.id, a, proof);
      if (a === "approve" && res.finalize === "failed") toast({ tone: "error", text: "Approved, but the submit did not finish. Nothing was sent.", detail: title });
      else toast({ tone: "success", text: a === "approve" ? `${L.yes}: done.` : `${L.no}: done.`, detail: title });
      onDone();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Nothing was changed. Try again."); }
    finally { setBusy(null); setSigning(false); }
  };

  return (
    <article className="kc-row" data-kind="approval" data-cls={cls} data-risk={it.risk_class} aria-labelledby={`ny-${it.id}`}>
      <h3 className="kc-row__title" id={`ny-${it.id}`}>
        <Glyph name={cls === 0 ? "alert" : "decision"} />
        <span>{title}</span>
      </h3>
      {lead.split(/(?<=[.!?])\s+/).filter(Boolean).map((sentence, i) => <p key={i} className="kc-row__body">{sentence}</p>)}
      {cons && <p className="kc-row__cons" data-testid="consequence">{cons}</p>}
      {stepUp && <p className="kc-row__meta">{stepUpNotice(it.risk_class)}</p>}
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="kc-row__actions">
        <button type="button" className={`btn ${primary ? "btn--primary" : "btn--secondary"}`} disabled={!!busy} onClick={() => void decide("approve")}>{busy === "approve" ? (signing ? "Waiting for sign-in" : "Working") : L.yes}</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void decide("reject")}>{busy === "reject" ? "Working" : L.no}</button>
        <button type="button" className="kc-link" data-toggle aria-expanded={open} aria-controls={`ev-${it.id}`} onClick={() => setOpen((v) => !v)}>Evidence<Glyph name="chevron" /></button>
      </div>
      {open && <div id={`ev-${it.id}`}><Evidence item={it} rest={rest} since={whenText(it.created_at)} /></div>}
    </article>
  );
}
