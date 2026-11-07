import { useState } from "react";
import { ApiError } from "../../api";
import { neverLine, plainWords } from "../../screens/NeedsYou/model";
import { touchesSentence } from "../../screens/Routines/model";
import type { Routine } from "../../types";
import { Ladder } from "../Ladder";
import { Glyph } from "../needsyou/Glyph";
import { Details } from "../ui";
import { AwayChoice } from "./AwayChoice";
import { CAP_LABEL, CAP_MODE, capOf, stateLine, stepState, trustWord, type Cap } from "./consent";
import { SkillGate, type Gate } from "./SkillGate";
import type { Decide } from "./types";

const STEPS: Cap[] = ["watching", "asks", "own"];

/**
 * One routine that runs for the worker: its title, its state in one sentence and how far it is trusted, in one row. Opening the row shows, in place, what
 * it touches and will never do, the three steps of trust (a step up is offered only when the record earned it, and a disabled step says what it needs),
 * Run now, Stop for good (an inline confirm) and its separate "Run while I'm away" opt-in. There is no Pause: the engine has no paused state for a routine.
 */
export function RunningRow({ routine: r, open, onToggle, onDecide, onRun, canRun }: { routine: Routine; open: boolean; onToggle: () => void; onDecide: Decide; onRun?: (r: Routine) => Promise<string | null>; canRun: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [stopping, setStopping] = useState(false);
  const [ran, setRan] = useState<string | null>(null);
  const here = capOf(r.status);

  const choose = async (step: Cap, override = false) => {
    setBusy(step); setErr(null); setGate(null);
    const done = `${r.title}: ${CAP_LABEL[step].toLowerCase()}.`;
    try { await onDecide(r, { mode: CAP_MODE[step], ...(override ? { skill_override: true } : {}) }, done); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode: CAP_MODE[step], done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again.");
    } finally { setBusy(null); }
  };
  const stop = async () => {
    setBusy("stop"); setErr(null);
    try { await onDecide(r, { mode: "not_now" }, `${r.title} is stopped.`); setStopping(false); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again."); }
    finally { setBusy(null); }
  };
  const run = async () => {
    if (!onRun) return;
    setBusy("run"); setErr(null); setRan(null);
    try { setRan(await onRun(r)); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "It did not start. Nothing was changed. Try again."); }
    finally { setBusy(null); }
  };
  const never = plainWords(neverLine(r.proposal.never.length ? r.proposal.never : r.never));

  return (
    <article className="rt-row" data-status={r.status} data-open={open}>
      <div className="rt-row__line">
        <span className="rt-row__text">
          <span className="rt-row__title">{plainWords(r.title)}</span>
          <span className="rt-row__state">{stateLine(r)}</span>
        </span>
        <span className="rt-row__trust">{trustWord(r)}</span>
        <Glyph name="chevron" className="kc-glyph rt-row__chev" />
        {/* The whole line opens the row. The control has no words of its own: its name is the routine's. */}
        <button type="button" className="rt-row__open" aria-expanded={open} aria-controls={`rt-${r.id}`} aria-label={`${plainWords(r.title)}: ${open ? "close" : "open"}`} onClick={onToggle} />
      </div>
      {open && (
        <div className="kc-panel rt-panel" id={`rt-${r.id}`}>
          <p>{plainWords(touchesSentence(r))} {never}</p>
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            <p className="kc-label" id={`auto-${r.id}`}>Autonomy</p>
            <div className="segmented" role="group" aria-labelledby={`auto-${r.id}`}>
              {STEPS.map((s) => {
                const st = stepState(r, s);
                return <button key={s} type="button" aria-pressed={here === s} disabled={!st.enabled || !!busy} onClick={() => { if (here !== s) void choose(s); }}>{CAP_LABEL[s]}</button>;
              })}
            </div>
            {STEPS.map((s) => { const st = stepState(r, s); return st.need ? <p key={s} className="kc-sub" data-testid={`need-${s}`}>{CAP_LABEL[s]}: {st.need}</p> : null; })}
          </div>
          {gate && <SkillGate gate={gate} busy={!!busy} onOverride={() => void choose(STEPS.find((s) => CAP_MODE[s] === gate.mode) ?? "watching", true)} onDismiss={() => setGate(null)} />}
          {err && <p className="kc-error" role="alert">{err}</p>}
          {ran !== null && <p className="note" role="status" data-testid="ran">{ran}</p>}
          {stopping ? (
            <div className="kc-confirm" data-tone="danger" role="group" aria-label="Stop for good">
              <p>Stop for good? It stops now and goes back to Not now. Nothing it already did is undone.</p>
              <div className="row">
                <button type="button" className="btn btn--danger btn--sm" disabled={busy === "stop"} onClick={() => void stop()}>{busy === "stop" ? "Stopping" : "Stop for good"}</button>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => setStopping(false)}>Keep it</button>
              </div>
            </div>
          ) : (
            <div className="row">
              {canRun && onRun && <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => void run()}>{busy === "run" ? "Starting" : "Run now"}</button>}
              <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => setStopping(true)}>Stop for good</button>
            </div>
          )}
          <AwayChoice routine={r} onDecide={onDecide} onOff={() => onDecide(r, { mode: "approval" }, `${r.title}: asks first.`)} />
          <Details summary="Record" wide><Ladder routine={r} /></Details>
        </div>
      )}
    </article>
  );
}
