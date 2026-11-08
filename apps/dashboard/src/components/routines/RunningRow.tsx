import { useState } from "react";
import { ApiError } from "../../api";
import { clip } from "../../lib/safeText";
import { plainWords } from "../../screens/NeedsYou/model";
import type { Routine } from "../../types";
import { Ladder } from "../Ladder";
import { Glyph } from "../needsyou/Glyph";
import { KV } from "../needsyou/KV";
import { Details } from "../ui";
import { AwayButton, AwayConfirm, useAway } from "./AwayChoice";
import { AWAY_TEXT, CAP_LABEL, CAP_MODE, capOf, stateLine, stepState, trustWord, type Cap } from "./consent";
import { SkillGate, type Gate } from "./SkillGate";
import type { Decide } from "./types";

const STEPS: Cap[] = ["watching", "asks", "own"];
const list = (xs: unknown): string[] => (Array.isArray(xs) ? xs.map((x) => plainWords(String(x ?? "")).replace(/\.$/, "")).filter(Boolean) : []);
const joined = (xs: string[]): string => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/**
 * One routine that runs for the worker: its title, its state in one sentence, how far it is trusted and Run now, in one row. Opening the row shows what
 * it needs to decide and nothing else: the facts as label and value (what it touches, what it will never do, what the next step needs), ONE short
 * paragraph (the consent for running while away, printed whole), ONE row of actions (the three steps of trust, Run while I'm away, Stop for good) and a
 * closed "More" with the record. A step up is offered only when the record earned it. There is no Pause: the engine has no paused state for a routine.
 */
export function RunningRow({ routine: r, open, onToggle, onDecide, onRun, canRun }: { routine: Routine; open: boolean; onToggle: () => void; onDecide: Decide; onRun?: (r: Routine) => Promise<string | null>; canRun: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [stopping, setStopping] = useState(false);
  const [ran, setRan] = useState<string | null>(null);
  const title = plainWords(clip(r.title, 160)) || "A routine";
  const away = useAway(r, onDecide, () => onDecide(r, { mode: "approval" }, `${title}: asks first.`));
  const here = capOf(r.status);

  const choose = async (step: Cap, override = false) => {
    setBusy(step); setErr(null); setGate(null);
    const done = `${title}: ${CAP_LABEL[step].toLowerCase()}.`;
    try { await onDecide(r, { mode: CAP_MODE[step], ...(override ? { skill_override: true } : {}) }, done); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode: CAP_MODE[step], done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again.");
    } finally { setBusy(null); }
  };
  const stop = async () => {
    setBusy("stop"); setErr(null);
    try { await onDecide(r, { mode: "not_now" }, `${title} is stopped.`); setStopping(false); }
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
  const touches = list(r.proposal?.touches?.length ? r.proposal.touches : r.touches);
  const never = list(r.proposal?.never?.length ? r.proposal.never : r.never).map((n) => n.charAt(0).toLowerCase() + n.slice(1));
  const needs = STEPS.map((s) => ({ s, st: stepState(r, s) })).filter((x) => x.st.need);

  return (
    <article className="rt-row" data-status={r.status} data-open={open}>
      <div className="rt-row__line">
        <span className="rt-row__text">
          <span className="rt-row__title">{title}</span>
          <span className="rt-row__state">{stateLine(r)}</span>
        </span>
        <span className="rt-row__trust">{trustWord(r)}</span>
        {canRun && onRun && <button type="button" className="btn btn--secondary btn--sm rt-row__run" disabled={!!busy} onClick={() => void run()}>{busy === "run" ? "Starting" : "Run now"}</button>}
        <Glyph name="chevron" className="kc-glyph rt-row__chev" />
        {/* The whole line opens the row. The control has no words of its own: its name is the routine's. */}
        <button type="button" className="rt-row__open" aria-expanded={open} aria-controls={`rt-${r.id}`} aria-label={`${title}: ${open ? "close" : "open"}`} onClick={onToggle} />
      </div>
      {!open && err && <p className="kc-error rt-row__msg" role="alert">{err}</p>}
      {ran !== null && <p className="note rt-row__msg" role="status" data-testid="ran">{ran}</p>}
      {open && (
        <div className="kc-panel rt-panel" id={`rt-${r.id}`}>
          <KV label="About this routine" rows={[
            ["Touches", touches.length ? joined(touches) : null],
            ["It will never", never.length ? joined(never) : null],
            ["Next step", needs.length ? <>{needs.map(({ s, st }) => <span key={s} data-testid={`need-${s}`} style={{ display: "block" }}>{CAP_LABEL[s]}: {st.need!.replace(/^Needs /, "needs ")}</span>)}</> : null],
          ]} />
          {!away.on && <p className="kc-sub" data-testid="away-consent">Run while I'm away: {AWAY_TEXT.charAt(0).toLowerCase()}{AWAY_TEXT.slice(1)}</p>}
          {gate && <SkillGate gate={gate} busy={!!busy} onOverride={() => void choose(STEPS.find((s) => CAP_MODE[s] === gate.mode) ?? "watching", true)} onDismiss={() => setGate(null)} />}
          {err && <p className="kc-error" role="alert">{err}</p>}
          {stopping ? (
            <div className="kc-confirm" data-tone="danger" role="group" aria-label="Stop for good">
              <p>Stop for good? It stops now and goes back to Not now. Nothing it already did is undone.</p>
              <div className="row">
                <button type="button" className="btn btn--danger btn--sm" disabled={busy === "stop"} onClick={() => void stop()}>{busy === "stop" ? "Stopping" : "Stop for good"}</button>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => setStopping(false)}>Keep it</button>
              </div>
            </div>
          ) : (
            <div className="kc-row__actions" role="group" aria-label="Autonomy">
              <div className="segmented" role="group" aria-label="Autonomy">
                {STEPS.map((s) => {
                  const st = stepState(r, s);
                  return <button key={s} type="button" aria-pressed={here === s} disabled={!st.enabled || !!busy} onClick={() => { if (here !== s) void choose(s); }}>{CAP_LABEL[s]}</button>;
                })}
              </div>
              <AwayButton away={away} />
              <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => setStopping(true)}>Stop for good</button>
            </div>
          )}
          <AwayConfirm away={away} />
          <Details summary="More"><Ladder routine={r} /></Details>
        </div>
      )}
    </article>
  );
}
