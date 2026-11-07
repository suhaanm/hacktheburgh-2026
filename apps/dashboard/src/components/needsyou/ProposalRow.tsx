import { useState } from "react";
import { ApiError } from "../../api";
import { neverLine, plainWords, saveHint, saveLine, seenLine, touchesLead } from "../../screens/NeedsYou/model";
import type { Routine } from "../../types";
import { Hint } from "../Hint";
import { APPROVAL_TEXT, WATCH_TEXT } from "../routines/consent";
import { AwayChoice } from "../routines/AwayChoice";
import { SkillGate, type Gate } from "../routines/SkillGate";
import type { Decide } from "../routines/types";
import { Glyph } from "./Glyph";

/**
 * A routine proposal. Three choices of one size and one weight: Watch first (the safe opt-in), Not now, Never. "More ways to say yes" opens in place:
 * Run with my approval, and Run while I'm away with its own consent printed beside its own button. What it touches and what it will never do are printed whole.
 */
export function ProposalRow({ routine: p, onDecide }: { routine: Routine; onDecide: Decide }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [more, setMore] = useState(false);
  const [allTouches, setAllTouches] = useState(false);
  const touches = touchesLead(p.proposal.touches.length ? p.proposal.touches : p.touches);
  const never = plainWords(neverLine(p.proposal.never.length ? p.proposal.never : p.never));

  const go = async (mode: string, done: string, override = false) => {
    setBusy(mode); setErr(null); setGate(null);
    try { await onDecide(p, { mode, ...(override ? { skill_override: true } : {}) }, done); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode, done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again.");
    } finally { setBusy(null); }
  };

  return (
    <article className="kc-row" data-kind="proposal" data-cls="2" aria-labelledby={`ny-${p.id}`}>
      <h3 className="kc-row__title" id={`ny-${p.id}`}>
        <Glyph name="routine" />
        <span>{plainWords(p.title)}</span>
        <span className="kc-row__when">new routine</span>
      </h3>
      <p className="kc-row__body">{seenLine(p.proposal.how_often)} {saveLine(p)}<Hint label="About the hours saved">{saveHint(p)}</Hint></p>
      <p className="kc-row__meta" data-testid="never">
        Touches {plainWords(allTouches ? p.proposal.touches.join(", ") : touches.lead)}
        {touches.more > 0 && !allTouches && <> and <button type="button" className="kc-link" style={{ minHeight: 0, padding: 0, display: "inline", textDecoration: "underline" }} onClick={() => setAllTouches(true)}>{touches.more} more</button></>}
        . {never}
      </p>
      <div className="kc-row__actions" role="group" aria-label="Your choice">
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("shadow", "Watching first.")}>Watch first</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("not_now", "Okay, not now.")}>Not now</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("never", "Okay. This will not be suggested again.")}>Never</button>
        <button type="button" className="kc-link" aria-expanded={more} aria-controls={`more-${p.id}`} onClick={() => setMore((v) => !v)}>More ways to say yes<Glyph name="chevron" /></button>
      </div>
      <p className="kc-sub" data-testid="watch-consent">{WATCH_TEXT}</p>
      {more && (
        <div className="kc-panel" id={`more-${p.id}`}>
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            <p className="kc-sub">{APPROVAL_TEXT}</p>
            <div className="row"><button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => void go("approval", "Set to run with your approval.")}>Run with my approval</button></div>
          </div>
          <AwayChoice routine={p} onDecide={onDecide} />
        </div>
      )}
      {gate && <SkillGate gate={gate} busy={!!busy} onOverride={() => void go(gate.mode, gate.done, true)} onDismiss={() => setGate(null)} />}
      {err && <p className="kc-error" role="alert">{err}</p>}
    </article>
  );
}
