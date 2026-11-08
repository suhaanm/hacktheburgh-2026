import { useState } from "react";
import { ApiError } from "../../api";
import { neverLine, plainWords, saveHint, saveLine, seenLine } from "../../screens/NeedsYou/model";
import type { Routine } from "../../types";
import { Hint } from "../Hint";
import { APPROVAL_TEXT, WATCH_TEXT } from "../routines/consent";
import { AwayChoice } from "../routines/AwayChoice";
import { SkillGate, type Gate } from "../routines/SkillGate";
import type { Decide } from "../routines/types";
import { Glyph } from "./Glyph";

/**
 * Everything else about a routine proposal, behind its Details: what it touches, Never (as light as the buttons on the row), and what every way of saying
 * yes does, printed whole: Watch first, Run with my approval, and Run while I'm away with its own consent next to its own button.
 */
export function ProposalDetails({ routine: p, touches, busy, onApproval, onNever, onDecide }: { routine: Routine; touches: string; busy: boolean; onApproval: () => void; onNever: () => void; onDecide: Decide }) {
  return (
    <div className="kc-panel" id={`more-${p.id}`} data-testid="proposal-details">
      <p data-testid="touches">Touches {touches}.</p>
      <div style={{ display: "grid", gap: "var(--space-2)" }}>
        <p className="kc-sub" data-testid="never-caption">Never: do not suggest this again.</p>
        <div className="row"><button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={onNever}>Never</button></div>
      </div>
      <p className="kc-sub" data-testid="watch-consent">{WATCH_TEXT}</p>
      <div style={{ display: "grid", gap: "var(--space-2)" }}>
        <p className="kc-sub">{APPROVAL_TEXT}</p>
        <div className="row"><button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={onApproval}>Run with my approval</button></div>
      </div>
      <AwayChoice routine={p} onDecide={onDecide} />
    </div>
  );
}

/**
 * A routine proposal, as short as it can honestly be: the title, one line of what it would save, what it will never do (printed whole, never folded),
 * and two choices of one size and one weight, Watch first and Not now, so a taller window adds no words. Details opens the rest in place: what it touches,
 * Never, and the other ways to say yes with their consent text.
 */
export function ProposalRow({ routine: p, onDecide }: { routine: Routine; onDecide: Decide }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [more, setMore] = useState(false);
  const touchList = (p.proposal.touches.length ? p.proposal.touches : p.touches).map((t) => plainWords(t));
  const neverItems = (p.proposal.never.length ? p.proposal.never : p.never).map((n) => plainWords(n).replace(/\.$/, ""));
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
      {neverItems.length > 1 ? (
        <div className="kc-row__meta" data-testid="never">
          <p style={{ margin: 0 }}>It will never</p>
          <ul className="ny-never">{neverItems.map((n) => <li key={n}>{n.charAt(0).toLowerCase() + n.slice(1)}</li>)}</ul>
        </div>
      ) : (
        <p className="kc-row__meta" data-testid="never">{never}</p>
      )}
      <div className="kc-row__actions" role="group" aria-label="Your choice">
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("shadow", "Watching first.")}>Watch first</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("not_now", "Okay, not now.")}>Not now</button>
        <button type="button" className="kc-link" aria-expanded={more} aria-controls={`more-${p.id}`} onClick={() => setMore((v) => !v)}>Details<Glyph name="chevron" /></button>
      </div>
      {more && <ProposalDetails routine={p} touches={touchList.length > 1 ? `${touchList.slice(0, -1).join(", ")} and ${touchList[touchList.length - 1]}` : touchList.join("")} busy={!!busy}
        onApproval={() => void go("approval", "Set to run with your approval.")} onNever={() => void go("never", "Okay. This will not be suggested again.")} onDecide={onDecide} />}
      {gate && <SkillGate gate={gate} busy={!!busy} onOverride={() => void go(gate.mode, gate.done, true)} onDismiss={() => setGate(null)} />}
      {err && <p className="kc-error" role="alert">{err}</p>}
    </article>
  );
}
