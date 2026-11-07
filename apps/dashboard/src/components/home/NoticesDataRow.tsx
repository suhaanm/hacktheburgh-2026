import { useState } from "react";
import { useAppState } from "../../store";
import { downloadText } from "../../screens/Growth/data";
import { deleteNotices, exportNotices } from "./noticesData";
import { APP_NAME } from "../../brand";

/**
 * "Your notices data": a short row on the Privacy screen. What Understudy learned about how loudly to speak to you stays on this laptop;
 * you can take a copy of it or delete it. Deleting does not stop notices, it only makes Understudy forget what it learned.
 */
export function NoticesDataRow() {
  const person = useAppState().person;
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  const doExport = async () => {
    setSaid(null);
    try {
      const f = await exportNotices(person);
      downloadText(f.filename, f.text);
      setSaid({ tone: "ok", text: f.example ? "Saved a copy of the example data." : "Saved a copy to your downloads." });
    } catch (e) { setSaid({ tone: "error", text: e instanceof Error ? e.message : "Could not make the file. Try again." }); }
  };
  const doDelete = async () => {
    setBusy(true); setSaid(null);
    try {
      const r = await deleteNotices(person);
      setConfirm(false);
      setSaid({ tone: "ok", text: r.example ? "Cleared the example data. With the engine running this would remove your real notices data." : r.deleted === 0 ? "There was nothing to delete." : `Deleted. ${APP_NAME} has forgotten how loudly you like it to speak.` });
    } catch (e) { setSaid({ tone: "error", text: e instanceof Error ? e.message : "Could not delete it. Nothing was changed." }); }
    finally { setBusy(false); }
  };

  return (
    <section className="noticesdata" aria-labelledby="nd-h">
      <div>
        <h2 id="nd-h" className="section__title">Your notices data</h2>
        <p className="note">What {APP_NAME} learned about how loudly to speak to you. It stays on this laptop.</p>
      </div>
      <div className="row">
        <button type="button" className="btn btn--secondary btn--sm" onClick={doExport}>Export a copy</button>
        {confirm ? (
          <>
            <button type="button" className="btn btn--danger btn--sm" disabled={busy} onClick={doDelete}>{busy ? "Deleting" : "Yes, delete it"}</button>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirm(false)}>Keep it</button>
          </>
        ) : (
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => setConfirm(true)}>Delete it</button>
        )}
      </div>
      {confirm && <p className="note note--warn">This makes {APP_NAME} forget what it learned about your notices. It does not turn notices off, and safety stops stay visible.</p>}
      {said && <p className={said.tone === "error" ? "field__error" : "note"} role={said.tone === "error" ? "alert" : "status"}>{said.text}</p>}
    </section>
  );
}
