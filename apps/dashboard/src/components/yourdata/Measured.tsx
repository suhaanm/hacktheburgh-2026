import { useState } from "react";
import { ApiError } from "../../api";
import { plural, totalRows, type LedgerCounts } from "../growth/model";
import { useToast } from "../Toasts";
import { ConfirmRow } from "../ui";
import type { LedgerView } from "../../screens/Growth/data";
import { CAPTURE_TEXT, stepForgetText } from "../../screens/YourData/model";

/**
 * What Knack measures: when you are active (times only, per the capture switch) and one row per step, as codes and numbers, which Growth is drawn from.
 * Export it, or forget it: the same "Forget it" or "Keep" as everywhere in Your data.
 */
export function Measured({ capture, view, example, onExport, onDelete }: { capture: boolean; view: LedgerView | null; example: boolean; onExport: () => Promise<void>; onDelete: () => Promise<number> }) {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState<"export" | "delete" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const counts: LedgerCounts = { assist: view?.counts?.assist ?? 0, delegated: view?.counts?.delegated ?? 0, automation: view?.counts?.automation ?? 0 };
  const total = totalRows(counts);
  const copy = stepForgetText(counts, example);

  const doExport = async () => {
    setErr(null); setBusy("export");
    try { await onExport(); toast({ tone: "success", text: "Exported.", detail: "A JSON file was saved to your downloads: the same rows, codes and numbers only." }); }
    catch (e) { setErr(e instanceof ApiError || e instanceof Error ? e.message : "Could not export it."); }
    finally { setBusy(null); }
  };
  const doDelete = async () => {
    setErr(null); setBusy("delete");
    try { const n = await onDelete(); setConfirm(false); toast({ tone: "success", text: `Forgot ${plural(n, "row")}.`, detail: example ? "That was example data, so only this screen changed." : "Nothing else was touched." }); }
    catch (e) { setErr(e instanceof ApiError || e instanceof Error ? e.message : "Could not forget it. Nothing was deleted."); }
    finally { setBusy(null); }
  };

  return (
    <div className="yd-body" data-testid="measured">
      <p className="kc-row__body" style={{ margin: 0 }}>{capture ? "Capture is on. Times only." : "Capture is off. No times are recorded."}</p>
      <p className="kc-sub">{CAPTURE_TEXT}</p>
      <p className="kc-row__body" style={{ margin: 0 }}>{view ? `${plural(counts.assist, "step")} counted, ${counts.delegated} done for you, ${counts.automation} overnight.` : "Reading the step counts."}</p>
      <p className="kc-sub">One row per step, as codes and numbers. No text, no screenshots, no page content. Growth is drawn from it.</p>
      <div className="row">
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy != null || total === 0} onClick={() => void doExport()}>{busy === "export" ? "Exporting" : "Export as JSON"}</button>
        {!confirm && <button type="button" className="btn btn--secondary btn--sm" disabled={busy != null || total === 0} onClick={() => setConfirm(true)}>Forget</button>}
      </div>
      {confirm && (
        <ul className="kc-list"><ConfirmRow question={copy.question} consequence={copy.consequence} confirmLabel={busy === "delete" ? "Forgetting" : "Forget it"} busy={busy != null} onConfirm={() => void doDelete()} onCancel={() => setConfirm(false)} /></ul>
      )}
      {err && <p className="kc-error" role="alert">{err}</p>}
    </div>
  );
}
