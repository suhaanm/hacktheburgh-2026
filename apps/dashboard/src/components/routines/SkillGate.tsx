import { plainGate } from "../repeats/model";

export interface Gate { mode: string; done: string; message: string }

/**
 * The skill gate says the worker's own skill on this routine's steps is below level 4: coach it first, unless they say they know it.
 * The override is written into the memory file, and the routine still starts by watching. Printed, with two equal choices.
 */
export function SkillGate({ gate, busy, onOverride, onDismiss }: { gate: Gate; busy: boolean; onOverride: () => void; onDismiss: () => void }) {
  return (
    <div className="note note--warn" role="alert" data-testid="skill-gate" style={{ display: "grid", gap: "var(--space-3)" }}>
      <p><b>Knack would rather coach you on this one first.</b> {plainGate(gate.message)}</p>
      <p>If you already know it well, say so. That is written into your memory file, and it still starts by watching.</p>
      <div className="row">
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={onOverride}>I already know this one</button>
        <button type="button" className="btn btn--secondary btn--sm" onClick={onDismiss}>Keep coaching me</button>
      </div>
    </div>
  );
}
