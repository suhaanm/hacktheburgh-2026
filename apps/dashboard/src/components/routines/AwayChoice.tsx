import { useState } from "react";
import { ApiError } from "../../api";
import type { Routine } from "../../types";
import { IRREVERSIBLE_MODEL, IRREVERSIBLE_SCRIPT } from "./consent";
import { SkillGate, type Gate } from "./SkillGate";
import type { Decide } from "./types";

/**
 * "Run while I'm away" is its own opt-in, in two parts so an action row can hold its button: `useAway` keeps the state, `AwayButton` goes in the row
 * of actions, `AwayConfirm` opens under the row only when something must be confirmed. Its consent is printed by the block that holds the button
 * (AWAY_TEXT), right above it. A routine with no step that cannot be undone is one click. A routine with such steps asks, once, in place: each step is
 * its own switch, off by default; a model-driven routine also needs its id typed. Nothing irreversible is ever allowed by the first click.
 */
export function useAway(p: Routine, onDecide: Decide, onOff?: () => Promise<void>, startConfirming = false) {
  const classes = p.irreversible_classes ?? [];
  const on = p.status === "unattended";
  const [confirming, setConfirming] = useState(startConfirming);
  const [allowed, setAllowed] = useState<string[]>(p.consent?.irreversible_unattended ?? []);
  const [typed, setTyped] = useState("");
  const [ack, setAck] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [busy, setBusy] = useState(false);
  const model = p.driver === "model";
  const irreversible = allowed.length > 0;
  const ready = !irreversible || (model ? typed === p.id : ack);

  const save = async (override = false) => {
    setBusy(true); setErr(null); setGate(null);
    const done = "Set to run while you are away.";
    try { await onDecide(p, { mode: "unattended", irreversible_unattended: allowed, typed_confirm: typed, ...(override ? { skill_override: true } : {}) }, done); setConfirming(false); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode: "unattended", done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again.");
    } finally { setBusy(false); }
  };
  const turnOff = async () => {
    if (!onOff) return;
    setBusy(true); setErr(null);
    try { await onOff(); } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again."); } finally { setBusy(false); }
  };
  /** The first click: one click when nothing in the routine cannot be undone, otherwise open the confirm. */
  const begin = () => { if (classes.length === 0) void save(); else setConfirming((v) => !v); };
  return { p, classes, on, confirming, setConfirming, allowed, setAllowed, typed, setTyped, ack, setAck, err, gate, setGate, busy, model, ready, save, turnOff, begin, canTurnOff: !!onOff };
}
export type Away = ReturnType<typeof useAway>;

/** The button for an action row: "Run while I'm away", or "Turn off" when it is on. */
export function AwayButton({ away: a, size = "sm" }: { away: Away; size?: "sm" | "md" }) {
  const cls = `btn btn--secondary${size === "sm" ? " btn--sm" : ""}`;
  if (a.on) return a.canTurnOff ? <button type="button" className={cls} disabled={a.busy} onClick={() => void a.turnOff()}>Turn off away runs</button> : null;
  return <button type="button" className={cls} disabled={a.busy} aria-expanded={a.classes.length ? a.confirming : undefined} onClick={a.begin}>Run while I'm away</button>;
}

/** What opens under the row: the skill gate, an error, and, for a routine with steps that cannot be undone, the one confirm. */
export function AwayConfirm({ away: a }: { away: Away }) {
  const { p } = a;
  if (!a.confirming && !a.gate && !a.err && !(a.on && a.allowed.length > 0)) return null;
  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }} data-testid="away-choice">
      {a.on && a.allowed.length > 0 && <p className="kc-row__cons">Allowed without asking: {a.allowed.join(", ")}.</p>}
      {a.confirming && !a.on && (
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--space-2)" }}>
          <legend className="kc-label">Steps that cannot be undone each wait for your click unless you allow them.</legend>
          {a.classes.map((c) => (
            <label key={c} className="toggle">
              <input type="checkbox" role="switch" checked={a.allowed.includes(c)} onChange={(e) => a.setAllowed((x) => (e.target.checked ? [...x, c] : x.filter((y) => y !== c)))} />
              <span className="toggle__track" aria-hidden="true" />
              <span className="toggle__text">Allow “{c}” without asking me</span>
            </label>
          ))}
          {a.allowed.length > 0 && (
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <p className="note note--warn" role="note">{a.model ? IRREVERSIBLE_MODEL : IRREVERSIBLE_SCRIPT}</p>
              {a.model ? (
                <div className="field">
                  <label className="field__label" htmlFor={`tc-${p.id}`}>Type <code>{p.id}</code> to confirm</label>
                  <input id={`tc-${p.id}`} className="input" value={a.typed} onChange={(e) => a.setTyped(e.target.value)} autoComplete="off" spellCheck={false} aria-invalid={a.typed.length > 0 && a.typed !== p.id} />
                </div>
              ) : (
                <label className="toggle"><input type="checkbox" checked={a.ack} onChange={(e) => a.setAck(e.target.checked)} /><span className="toggle__track" aria-hidden="true" /><span className="toggle__text">I understand this cannot be undone</span></label>
              )}
            </div>
          )}
          <div className="row">
            <button type="button" className="btn btn--secondary btn--sm" disabled={!a.ready || a.busy} onClick={() => void a.save()}>Allow while I'm away</button>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => a.setConfirming(false)}>Cancel</button>
          </div>
        </fieldset>
      )}
      {a.gate && <SkillGate gate={a.gate} busy={a.busy} onOverride={() => void a.save(true)} onDismiss={() => a.setGate(null)} />}
      {a.err && <p className="kc-error" role="alert">{a.err}</p>}
    </div>
  );
}
