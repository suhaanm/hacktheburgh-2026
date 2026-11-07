import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api";
import { useToast } from "../Toasts";
import { deleteCopy, plural, totalRows, type LedgerCounts } from "./model";

/** Export and delete the ledger. Delete asks once, says what goes and what stays, then works. */
export function LedgerControls({ counts, fields, example, onExport, onDelete }: {
  counts: LedgerCounts;
  fields: string[];
  example: boolean;
  onExport: () => Promise<void>;
  onDelete: () => Promise<number>;
}) {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState<"export" | "delete" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const keep = useRef<HTMLButtonElement>(null);
  const total = totalRows(counts);
  const copy = deleteCopy(counts, example);

  useEffect(() => { if (confirm) keep.current?.focus(); }, [confirm]);

  const doExport = async () => {
    setErr(null); setBusy("export");
    try { await onExport(); toast({ tone: "success", text: "Ledger exported.", detail: "A JSON file was saved to your downloads. It holds the same rows, enums and numbers only." }); }
    catch (e) { setErr(e instanceof ApiError || e instanceof Error ? e.message : "Could not export the ledger."); }
    finally { setBusy(null); }
  };
  const doDelete = async () => {
    setErr(null); setBusy("delete");
    try {
      const n = await onDelete();
      setConfirm(false);
      toast({ tone: "success", text: `Deleted ${plural(n, "row")}.`, detail: example ? "That was example data, so only this screen changed." : "The ledger is empty. Nothing else was touched. An audit line records the deletion." });
    } catch (e) { setErr(e instanceof ApiError || e instanceof Error ? e.message : "Could not delete the ledger. Nothing was deleted."); }
    finally { setBusy(null); }
  };

  return (
    <section className="section gr-ledger" aria-labelledby="led-h">
      <h2 id="led-h" className="section__title">Your ledger</h2>
      <p className="section__sub">One row each time a step came up in your work: what happened, as codes and numbers. No text, no screenshots, no page content. It stays on this computer and you own it.</p>
      {fields.length > 0 && (
        <details className="details-lite">
          <summary>What is stored in a row</summary>
          <p className="gr-fields num">{fields.map((f) => <code key={f}>{f}</code>)}</p>
        </details>
      )}
      <div className="row">
        <button type="button" className="btn btn--secondary" onClick={doExport} disabled={busy != null || total === 0}>{busy === "export" ? "Exporting" : "Export the ledger as JSON"}</button>
        {!confirm && <button type="button" className="btn btn--danger" onClick={() => setConfirm(true)} disabled={busy != null || total === 0}>Delete the ledger</button>}
        <a className="btn btn--quiet" href="#/privacy">See what has left this computer</a>
      </div>
      {total === 0 && <p className="note">The ledger is empty.</p>}
      {confirm && (
        <div className="gr-confirm" role="group" aria-labelledby="gr-confirm-h">
          <h3 id="gr-confirm-h" className="gr-confirm__title">Delete {plural(total, "row")}?</h3>
          <p>{copy.what}</p>
          <p className="gr-confirm__kept">{copy.kept}</p>
          <div className="row">
            <button type="button" className="btn btn--danger" onClick={doDelete} disabled={busy != null}>{busy === "delete" ? "Deleting" : copy.button}</button>
            <button type="button" className="btn btn--secondary" ref={keep} onClick={() => setConfirm(false)} disabled={busy != null}>Keep them</button>
          </div>
        </div>
      )}
      {err && <p className="field__error" role="alert">{err}</p>}
    </section>
  );
}
