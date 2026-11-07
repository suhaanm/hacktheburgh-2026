import { useState } from "react";
import { ApiError } from "../../api";
import { useToast } from "../../components/Toasts";
import { fmtMinutes, fmtRange, plainGate, STOPS_TEXT, timesText } from "../../components/repeats/model";
import type { HitRow } from "../../components/repeats/types";
import { watchFirst } from "./data";
import { APP_NAME } from "../../brand";

/**
 * What opens under a row when the worker presses Automate: what Understudy saw, what it would touch, where it would stop, and the one safe
 * first step. "Watch first" is the same choice the Routines proposal card offers: it practises on the worker's next cases and compares with
 * them, and nothing runs, is saved or is sent. The other choices (with my approval, while I am away) stay on Routines, one routine at a time.
 */
export function Peek({ row, windowDays, source, close, onDone }: { row: HitRow; windowDays: number; source: "live" | "demo"; close: () => void; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<string | null>(null);
  const already = row.status === "learning" || row.status === "running";
  const routine = row.actions.routine_id;

  const go = async (override = false) => {
    if (!routine) return;
    setBusy(true); setErr(null); setGate(null);
    try {
      await watchFirst(row.id, routine, source, override);
      toast({ tone: "success", text: "Watching first.", detail: "It practises on your next cases. Nothing runs, is saved or is sent." });
      onDone();
      close();
    } catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate(plainGate(e.message));
      else setErr(e instanceof ApiError ? e.message : "That did not save. Try again.");
    } finally { setBusy(false); }
  };

  return (
    <>
      <p className="hl-peek__what">{row.what}</p>
      <dl className="hl-peek__facts">
        <dt>Could save</dt>
        <dd className="num">about {fmtMinutes(row.minutes_per_week.point)} a week ({fmtRange(row.minutes_per_week)}, 95% interval), {timesText(row.count)} in {windowDays} days</dd>
        {row.touches.length > 0 && (<><dt>It touches</dt><dd>{row.touches.join(", ")}</dd></>)}
        <dt>It stops before</dt>
        <dd>{STOPS_TEXT[row.stops_before]}</dd>
      </dl>
      {already ? (
        <p className="note">{row.status === "learning" ? "It is watching you on this one now." : "This one is running with your approval."} Its record and choices are on Routines.</p>
      ) : (
        <p className="note">Watching first means it practises on your next cases and compares with what you do. Nothing runs, is saved or is sent. You choose what it may do after that, one routine at a time, on Routines.</p>
      )}
      {gate && (
        <div className="note note--warn" role="alert">
          <p><b>{APP_NAME} would rather coach you on this one first.</b> {gate}</p>
          <p>If you already know it well, say so. That is written into your memory file, and it still starts at the lowest rung.</p>
          <div className="row" style={{ marginTop: "var(--space-2)" }}>
            <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void go(true)}>I already know this one</button>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setGate(null)}>Keep coaching me</button>
          </div>
        </div>
      )}
      {err && <p className="field__error" role="alert">{err}</p>}
      <div className="hl-peek__foot">
        {!already && routine && <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => void go()}>Watch first</button>}
        <a className="btn btn--quiet btn--sm" href="#/routines">More choices on Routines</a>
        <button type="button" className="btn btn--quiet btn--sm" onClick={close}>Close</button>
      </div>
    </>
  );
}
