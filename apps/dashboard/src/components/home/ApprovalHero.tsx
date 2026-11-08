import { useState } from "react";
import { ApiError, api } from "../../api";
import { authForApproval, needsStepUp, stepUpNotice, useAuth } from "../../auth";
import { Details } from "../ui";
import { useToast } from "../Toasts";
import { approvalLabels, consequence, leadAndRest, plainWords } from "../../screens/NeedsYou/model";
import { refreshNeedsBadge } from "../../screens/NeedsYou/count";
import { finalizeOf, isSafetyPause } from "../../screens/Home/approval";
import type { QueueItem } from "../../types";

/**
 * An approval that blocks a running job, or a safety pause, takes Home's hero slot: its title, what it says in a line or two, what it would do that cannot
 * be undone, its own two buttons, and the evidence opening in place. A decision is always a real click (never a key), and an irreversible or outward step
 * still asks for a fresh sign-in when the identity provider is on; without it, nothing is approved. The words and labels are the same ones Needs you uses
 * (screens/NeedsYou/model.ts). A pause for safety is a choice of equal weight: it gets no primary button.
 */
export function ApprovalHero({ item: it, onDone }: { item: QueueItem; onDone: () => void }) {
  const toast = useToast();
  const auth = useAuth();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const L = approvalLabels(it.kind);
  const cost = isSafetyPause(it) ? "Paused for safety." : consequence(it.risk_class);
  const stepUp = auth.enabled && needsStepUp(it.risk_class);
  const title = plainWords(it.title || "Something needs you");
  const { lead, rest } = leadAndRest(it.summary ?? "", isSafetyPause(it) ? 30 : 16);
  const keys = Array.from(new Set([...Object.keys(it.evidence?.extracted ?? {}), ...Object.keys(it.evidence?.expected ?? {})]));
  const diff = (Array.isArray(it.evidence?.diff) ? it.evidence.diff : []) as { field: string; expected: string; got: string }[];

  const decide = async (a: "approve" | "reject") => {
    setBusy(a); setErr(null);
    try {
      let proof;
      if (a === "approve") {
        const gate = await authForApproval(auth, it.risk_class);
        if (!gate.allowed) { setErr(gate.message); return; }
        proof = gate.auth;
      }
      const r = await api.setQueue(it.id, a, proof);
      if (a === "approve" && finalizeOf(r) === "failed") {
        // The approval was recorded, but the step it released did not finish: say so, never "done".
        toast({ tone: "error", text: "Approved, but the step did not finish.", detail: "Nothing was submitted. Open Needs you to see it." });
      } else toast({ tone: "success", text: a === "approve" ? `${L.yes}: done.` : `${L.no}: done.`, detail: title });
      void refreshNeedsBadge();
      onDone();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Nothing was changed. Try again."); }
    finally { setBusy(null); }
  };

  return (
    <section className="home__hero home__hero--approval" aria-labelledby="home-hero" data-testid="home-approval">
      <h1 id="home-hero" className="home__hero-text hero-insight" dir="auto">{title}</h1>
      {lead && <p className="home__why home__why--lead" dir="auto">{lead}</p>}
      {cost && <p className="home__cost" data-risk={it.risk_class}>{cost}</p>}
      {stepUp && <p className="home__why home__why--small">{stepUpNotice(it.risk_class)}</p>}
      {err && <p className="field__error" role="alert">{err}</p>}
      <div className="home__actions">
        <button type="button" className={`btn ${isSafetyPause(it) ? "btn--secondary" : "btn--primary"}`} disabled={busy !== null} onClick={() => decide("approve")}>{busy === "approve" ? "Working" : L.yes}</button>
        <button type="button" className="btn btn--secondary" disabled={busy !== null} onClick={() => decide("reject")}>{busy === "reject" ? "Working" : L.no}</button>
        <Details summary="Evidence">
          <div className="home__evidence">
            {rest && <p className="note">{rest}</p>}
            <p className="note">Run {it.run_id}{it.routine_id ? ` · ${it.routine_id}` : ""}</p>
            {keys.length > 0 && (
              <div className="kv" role="table" aria-label="What the run found against what was expected">
                <span className="t-label">Field</span><span className="t-label">Found</span><span className="t-label">Expected</span>
                {keys.map((k) => {
                  const got = String(it.evidence.extracted?.[k] ?? "");
                  const exp = it.evidence.expected?.[k];
                  return (<span key={k} style={{ display: "contents" }}><span className="kv__k">{k}</span><span className={exp != null && String(exp) !== got ? "kv__bad" : ""}>{got || "none"}</span><span>{exp != null ? String(exp) : "not set"}</span></span>);
                })}
              </div>
            )}
            {diff.length > 0 && <p className="note"><b>Difference:</b> {diff.map((d) => `${d.field}: expected ${d.expected}, got ${d.got}`).join("; ")}</p>}
          </div>
        </Details>
      </div>
    </section>
  );
}
