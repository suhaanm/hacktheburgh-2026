import { useState } from "react";
import { ApiError } from "../../api";
import { neverLine, plainWords, proposalFacts } from "../../screens/NeedsYou/model";
import { clip } from "../../lib/safeText";
import type { BriefingCard, Routine } from "../../types";
import { APPROVAL_TEXT, AWAY_TEXT, WATCH_TEXT } from "../routines/consent";
import { AwayButton, AwayConfirm, useAway } from "../routines/AwayChoice";
import { SkillGate, type Gate } from "../routines/SkillGate";
import type { Decide } from "../routines/types";
import { Glyph } from "./Glyph";
import { KV } from "./KV";

/**
 * Everything else about a routine proposal, behind its Details, as one fact line (what it touches), ONE short paragraph that says what each way of saying
 * yes does (the consent, printed whole), and ONE row of actions: Run with my approval, Run while I'm away and Never. A routine with steps that cannot be
 * undone asks once more, in place, under the row.
 */
export function ProposalDetails({ routine: p, touches, interval, also, busy, onApproval, onNever, onDecide }: { routine: Routine; touches: string; /** What is behind the hours: the 95% interval and the money, never the only copy of the range (which is printed on the row). */ interval?: string; /** What a prepared action about this same routine says (its reason), when there is one. */ also?: string; busy: boolean; onApproval: () => void; onNever: () => void; onDecide: Decide }) {
  const away = useAway(p, onDecide);
  return (
    <div className="kc-panel" id={`more-${p.id}`} data-testid="proposal-details">
      <KV rows={[["Touches", touches], ["The hours", interval], ["Also prepared", also]]} label="About this routine" />
      <p className="kc-sub" data-testid="watch-consent">{WATCH_TEXT} {APPROVAL_TEXT} Run while I'm away: {AWAY_TEXT.charAt(0).toLowerCase()}{AWAY_TEXT.slice(1)}</p>
      <div className="kc-row__actions">
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={onApproval}>Run with my approval</button>
        <AwayButton away={away} />
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={onNever}>Never</button>
      </div>
      <AwayConfirm away={away} />
    </div>
  );
}

/**
 * A routine proposal, as short as it can honestly be: the title, one line of what it would save, what it will never do (printed whole, never folded),
 * and two choices of one size and one weight, Watch first and Not now, so a taller window adds no words. Details opens the rest in place: what it touches,
 * Never, and the other ways to say yes with their consent text.
 */
export function ProposalRow({ routine: p, also, onDecide }: { routine: Routine; also?: BriefingCard; onDecide: Decide }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [more, setMore] = useState(false);
  const f = proposalFacts(p);
  const touchList = f.touches;
  const neverItems = f.never;
  const never = neverLine(f.never);

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
        <span>{f.title}</span>
      </h3>
      {(f.seen || f.save) && <p className="kc-row__body">{f.seen}{f.seen && f.save ? " " : ""}{f.save}</p>}
      {neverItems.length > 1 ? (
        <div className="kc-row__meta" data-testid="never">
          <p style={{ margin: 0 }}>It will never</p>
          <ul className="ny-never">{neverItems.map((n, i) => <li key={`${i}-${n}`}>{n.charAt(0).toLowerCase() + n.slice(1)}</li>)}</ul>
        </div>
      ) : never ? (
        <p className="kc-row__meta" data-testid="never">{never}</p>
      ) : null}
      <div className="kc-row__actions" role="group" aria-label="Your choice">
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("shadow", "Set to watch first.")}>Watch first</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("not_now", "Okay, not now.")}>Not now</button>
        <button type="button" className="kc-link" aria-expanded={more} aria-controls={`more-${p.id}`} onClick={() => setMore((v) => !v)}>Details<Glyph name="chevron" /></button>
      </div>
      {more && <ProposalDetails routine={p} interval={f.save ? f.hint : undefined} also={also ? plainWords(clip(also.why, 160)) || undefined : undefined} touches={touchList.length > 1 ? `${touchList.slice(0, -1).join(", ")} and ${touchList[touchList.length - 1]}` : touchList.join("")} busy={!!busy}
        onApproval={() => void go("approval", "Set to run with your approval.")} onNever={() => void go("never", "Okay. This will not be suggested again.")} onDecide={onDecide} />}
      {gate && <SkillGate gate={gate} busy={!!busy} onOverride={() => void go(gate.mode, gate.done, true)} onDismiss={() => setGate(null)} />}
      {err && <p className="kc-error" role="alert">{err}</p>}
    </article>
  );
}
