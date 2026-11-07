import { useState } from "react";
import { ApiError } from "../../api";
import type { Routine } from "../../types";
import { AWAY_TEXT, IRREVERSIBLE_MODEL, IRREVERSIBLE_SCRIPT } from "./consent";
import { SkillGate, type Gate } from "./SkillGate";
import type { Decide } from "./types";

/**
 * "Run while I'm away" is its own opt-in. Its consent is printed whole beside its one button, so from "More ways to say yes" it is one more click.
 * Steps that cannot be undone are a second, per-routine opt-in: each is its own switch, off by default; a model-driven routine also needs its id typed.
 */
export function AwayChoice({ routine: p, onDecide, onOff }: { routine: Routine; onDecide: Decide; onOff?: () => Promise<void> }) {
  const classes = p.irreversible_classes ?? [];
  const on = p.status === "unattended";
  const [allowed, setAllowed] = useState<string[]>(p.consent.irreversible_unattended ?? []);
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
    try { await onDecide(p, { mode: "unattended", irreversible_unattended: allowed, typed_confirm: typed, ...(override ? { skill_override: true } : {}) }, done); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode: "unattended", done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Try again.");
    } finally { setBusy(false); }
  };
  const turnOff = async () => {
    if (!onOff) return;
    setBusy(true); setErr(null);
    try { await onOff(); } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not save. Try again."); } finally { setBusy(false); }
  };

  return (
    <div className="kc-away" data-on={on} data-testid="away-choice" style={{ display: "grid", gap: "var(--space-3)" }}>
      <p className="kc-label">Run while I'm away{on ? ": on" : ""}</p>
      <p className="kc-sub" data-testid="away-consent">{AWAY_TEXT}</p>
      {!on && classes.length > 0 && (
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--space-2)" }}>
          <legend className="kc-label">Steps that cannot be undone. Each waits for your click unless you allow it.</legend>
          {classes.map((c) => (
            <label key={c} className="toggle">
              <input type="checkbox" role="switch" checked={allowed.includes(c)} onChange={(e) => setAllowed((a) => (e.target.checked ? [...a, c] : a.filter((x) => x !== c)))} />
              <span className="toggle__track" aria-hidden="true" />
              <span className="toggle__text">Allow “{c}” without asking me</span>
            </label>
          ))}
        </fieldset>
      )}
      {!on && irreversible && (
        <div style={{ display: "grid", gap: "var(--space-2)" }}>
          <p className="note note--warn" role="note">{model ? IRREVERSIBLE_MODEL : IRREVERSIBLE_SCRIPT}</p>
          {model ? (
            <div className="field">
              <label className="field__label" htmlFor={`tc-${p.id}`}>Type <code>{p.id}</code> to confirm</label>
              <input id={`tc-${p.id}`} className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} aria-invalid={typed.length > 0 && typed !== p.id} />
            </div>
          ) : (
            <label className="toggle"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /><span className="toggle__track" aria-hidden="true" /><span className="toggle__text">I understand this cannot be undone</span></label>
          )}
        </div>
      )}
      {on && (p.consent.irreversible_unattended ?? []).length > 0 && <p className="kc-row__cons">Allowed without asking: {(p.consent.irreversible_unattended ?? []).join(", ")}.</p>}
      {gate && <SkillGate gate={gate} busy={busy} onOverride={() => void save(true)} onDismiss={() => setGate(null)} />}
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="row">
        {on
          ? onOff && <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void turnOff()}>Turn off</button>
          : <button type="button" className="btn btn--secondary btn--sm" disabled={!ready || busy} onClick={() => void save()}>Allow while I'm away</button>}
      </div>
    </div>
  );
}
