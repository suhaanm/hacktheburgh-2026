import { useState } from "react";
import { ApiError } from "../../api";
import { useToast } from "../Toasts";
import { ConfirmRow, Details } from "../ui";
import { deleteCopy, plural, totalRows, type LedgerCounts } from "./model";

/** Export and delete the ledger. Delete asks once in an inline row ("Forget it" or "Keep"), says what goes and what stays, then works. */
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
  const total = totalRows(counts);
  const copy = deleteCopy(counts, example);

  const doExport = async () => {
    setErr(null); setBusy("export");
    try { await onExport(); toast({ tone: "success", text: "Record exported.", detail: "A JSON file was saved to your downloads. It holds the same rows, enums and numbers only." }); }
    catch (e) { setErr(e instanceof ApiError || e instanceof Error ? e.message : "Could not export your record."); }
    finally { setBusy(null); }
  };
  const doDelete = async () => {
    setErr(null); setBusy("delete");
    try {
      const n = await onDelete();
      setConfirm(false);
      toast({ tone: "success", text: `Deleted ${plural(n, "row")}.`, detail: example ? "That was example data, so only this screen changed." : "Your record is empty. Nothing else was touched. An audit line records the deletion." });
    } catch (e) { setErr(e instanceof ApiError || e instanceof Error ? e.message : "Could not delete your record. Nothing was deleted."); }
    finally { setBusy(null); }
  };

  return (
    <div className="gr-ledger">
      <p className="note">One row per step, as codes and numbers only. It stays on this computer and you own it.</p>
      {fields.length > 0 && (
        <Details summary="What is stored in a row">
          <p className="gr-fields num">{fields.map((f) => <code key={f}>{f}</code>)}</p>
          <p className="note">No text, no screenshots, no page content.</p>
        </Details>
      )}
      <div className="row">
        <button type="button" className="btn btn--secondary" onClick={doExport} disabled={busy != null || total === 0}>{busy === "export" ? "Exporting" : "Export as JSON"}</button>
        {!confirm && <button type="button" className="btn btn--danger" onClick={() => setConfirm(true)} disabled={busy != null || total === 0}>Forget</button>}
        <a className="btn btn--quiet" href="#/your-data?section=sent">See what has left this computer</a>
      </div>
      {total === 0 && <p className="note">Your record is empty.</p>}
      {confirm && (
        <ul className="listrows">
          <ConfirmRow
            question={`Forget ${plural(total, "row")}?`}
            consequence={`${copy.what} ${copy.kept}`}
            confirmLabel={busy === "delete" ? "Forgetting" : "Forget it"}
            onConfirm={doDelete}
            onCancel={() => setConfirm(false)}
            busy={busy != null}
          />
        </ul>
      )}
      {err && <p className="field__error" role="alert">{err}</p>}
    </div>
  );
}
