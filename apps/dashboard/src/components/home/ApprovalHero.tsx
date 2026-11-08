import { useState } from "react";
import { ApiError, api } from "../../api";
import { authForApproval, needsStepUp, useAuth } from "../../auth";
import { Details } from "../ui";
import { useToast } from "../Toasts";
import { consequence, decisionLabels } from "../../screens/Home/approval";
import type { QueueItem } from "../../types";

/**
 * An approval that blocks a running job, or a safety pause, takes Home's hero slot: its title, one line, what it would do that cannot be undone,
 * its own two buttons, and the evidence opening in place. A decision is always a real click (never a key), and an irreversible or outward step
 * still asks for a fresh sign-in when the identity provider is on; without it, nothing is approved.
 */
export function ApprovalHero({ item: it, onDone }: { item: QueueItem; onDone: () => void }) {
  const toast = useToast();
  const auth = useAuth();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const L = decisionLabels(it.kind);
  const cost = consequence(it);
  const keys = Array.from(new Set([...Object.keys(it.evidence.extracted ?? {}), ...Object.keys(it.evidence.expected ?? {})]));
  const diff = (it.evidence.diff ?? []) as { field: string; expected: string; got: string }[];

  const decide = async (a: "approve" | "reject") => {
    setBusy(a); setErr(null);
    try {
      let proof;
      if (a === "approve") {
        const gate = await authForApproval(auth, it.risk_class);
        if (!gate.allowed) { setErr(gate.message); return; }
        proof = gate.auth;
      }
      const res = await api.setQueue(it.id, a, proof);
      if (a === "approve" && res.finalize === "failed") toast({ tone: "error", text: "Approved, but the submit did not finish. Nothing was sent.", detail: it.title });
      else toast({ tone: "success", text: a === "approve" ? `${L.yes}: done.` : `${L.no}: done.`, detail: it.title });
      onDone();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Try again."); }
    finally { setBusy(null); }
  };

  return (
    <section className="home__hero home__hero--approval" aria-labelledby="home-hero" data-testid="home-approval">
      <h1 id="home-hero" className="home__hero-text">{it.title}</h1>
      <p className="home__why">{it.summary}</p>
      {cost && <p className="home__cost" data-risk={it.risk_class}>{cost}{auth.enabled && needsStepUp(it.risk_class) ? " Asks you to sign in again." : ""}</p>}
      {err && <p className="field__error" role="alert">{err}</p>}
      <div className="home__actions">
        <button type="button" className="btn btn--primary" disabled={busy !== null} onClick={() => decide("approve")}>{busy === "approve" ? "Working" : L.yes}</button>
        <button type="button" className="btn btn--secondary" disabled={busy !== null} onClick={() => decide("reject")}>{L.no}</button>
        <Details summary="Evidence">
          <div className="home__evidence">
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
