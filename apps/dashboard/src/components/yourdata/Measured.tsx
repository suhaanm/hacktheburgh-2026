import { useState } from "react";
import { ApiError } from "../../api";
import { plural, totalRows, type LedgerCounts } from "../growth/model";
import { KV } from "../needsyou/KV";
import { useToast } from "../Toasts";
import { ConfirmRow } from "../ui";
import type { LedgerView } from "../../screens/Growth/data";
import { stepForgetText } from "../../screens/YourData/model";

const count = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? Math.max(0, Math.floor(v)) : 0);

/**
 * What Knack measures, as two fact lines (when you are active, and the step counts Growth is drawn from), ONE short paragraph that says what a row holds,
 * and ONE row of actions: export it, or forget it with the same "Forget it" or "Keep" as everywhere in Your data. The capture consent is printed once, beside
 * its switch under Capture and screen glances.
 */
export function Measured({ capture, view, example, onExport, onDelete }: { capture: boolean; view: LedgerView | null; example: boolean; onExport: () => Promise<void>; onDelete: () => Promise<number> }) {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState<"export" | "delete" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const counts: LedgerCounts = { assist: count(view?.counts?.assist), delegated: count(view?.counts?.delegated), automation: count(view?.counts?.automation) };
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
      <KV label="What is measured" rows={[
        ["Active times", capture ? "Times only" : "Not recorded (capture is off)"],
        ["Step counts", view ? `${counts.assist} counted, ${counts.delegated} done for you, ${counts.automation} overnight` : "Reading"],
      ]} />
      <p className="kc-sub">One row per step, as codes and numbers. No text, no screenshots, no page content.</p>
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
