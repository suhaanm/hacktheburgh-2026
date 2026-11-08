// The macOS permissions as On or Off, each with one button (Settings), or in two steps (the first run: "Allow voice", then "Allow clicking and screen help"). It reads status only and never
// asks macOS by itself: a button is the worker's own click, and macOS (or System Settings) is where the grant is made. Knack can never turn one on.
import { useCallback, useEffect, useState } from "react";
import { getBridge } from "../shell/bridge";
import { PERM_GROUPS, groupPlan, permRows, type Perm, type PermGroup, type PermRow } from "./permModel";

type Perms = { state?: () => Promise<Record<string, unknown>>; request?: (k: never) => Promise<unknown>; openSettings?: (k: never) => unknown };
const perms = (): Perms | null => (getBridge().permissions as Perms | undefined) ?? null;

/** The shell's read-only answer, kept fresh when the window is looked at (a grant made in System Settings shows on return). */
function usePermRows(): { rows: PermRow[]; error: string | null; reload: () => void; ask: (k: Perm) => Promise<void>; open: (k: Perm) => void; available: boolean } {
  const [rows, setRows] = useState<PermRow[]>(() => permRows(null));
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    const p = perms();
    if (!p?.state) return;
    p.state().then((s) => setRows(permRows(s)), () => undefined);
  }, []);
  useEffect(() => {
    reload();
    const again = () => { if (document.visibilityState !== "hidden") reload(); };
    window.addEventListener("focus", again);
    document.addEventListener("visibilitychange", again);
    return () => { window.removeEventListener("focus", again); document.removeEventListener("visibilitychange", again); };
  }, [reload]);
  const ask = useCallback(async (k: Perm) => {
    setError(null);
    try { await perms()?.request?.(k as never); } catch { setError("Could not ask. Nothing was changed."); }
    reload();
  }, [reload]);
  const open = useCallback((k: Perm) => {
    setError(null);
    try { void perms()?.openSettings?.(k as never); } catch { setError("Could not open System Settings."); }
  }, []);
  return { rows, error, reload, ask, open, available: !!perms()?.state };
}

function Row({ r, ask, open, allow = true }: { r: PermRow; ask: (k: Perm) => void; open: (k: Perm) => void; allow?: boolean }) {
  return (
    <li className="cv__row" data-state={r.on ? "ready" : "fix"} data-testid={`perm-${r.kind}`}>
      <span className="cv__text"><b>{r.title}</b><span className="cv__line">{r.word}. {r.line}</span></span>
      {r.button && (allow || r.button !== "Allow") && <button type="button" className="btn btn--secondary btn--sm" onClick={() => (r.button === "Allow" ? ask(r.kind) : open(r.kind))}>{r.button}</button>}
    </li>
  );
}

/** Settings: each permission On or Off, with one button. Renders nothing in a browser tab (no desktop app to ask). */
export function PermissionRows() {
  const { rows, error, ask, open, available } = usePermRows();
  if (!available) return null;
  return (
    <div className="cv">
      {error && <p className="kc-error" role="alert">{error}</p>}
      <ul className="cv__list" aria-label="Permissions" data-testid="permissions">{rows.map((r) => <Row key={r.kind} r={r} ask={(k) => void ask(k)} open={open} />)}</ul>
    </div>
  );
}

/** The first run: two steps, each one button on the worker's click. A permission macOS was told no to shows Open System Settings (only the worker can change it there). */
export function PermissionSteps() {
  const { rows, error, ask, open, available } = usePermRows();
  const [busy, setBusy] = useState<string | null>(null);
  if (!available) return null;
  const run = async (g: PermGroup) => {
    setBusy(g.id);
    const plan = groupPlan(g, rows);
    for (const k of plan.ask) await ask(k); // in order: macOS shows its own question for each, one at a time
    setBusy(null);
  };
  return (
    <div className="cv" data-testid="permission-steps">
      {error && <p className="kc-error" role="alert">{error}</p>}
      {PERM_GROUPS.map((g) => {
        const plan = groupPlan(g, rows);
        const mine = rows.filter((r) => g.kinds.includes(r.kind));
        return (
          <div key={g.id} className="cv" data-testid={`perm-group-${g.id}`}>
            <div><b>{g.title}</b></div>
            <ul className="cv__list" aria-label={g.title}>
              {mine.map((r) => <Row key={r.kind} r={r} ask={(k) => void ask(k)} open={open} allow={false} />)}
            </ul>
            {plan.ask.length > 0 && <div><button type="button" className="btn btn--secondary" disabled={busy === g.id} onClick={() => void run(g)}>{busy === g.id ? "Asking" : g.button}</button></div>}
          </div>
        );
      })}
    </div>
  );
}
