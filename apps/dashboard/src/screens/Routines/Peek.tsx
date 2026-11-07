import { useState } from "react";
import { ApiError } from "../../api";
import { SkillGate } from "../../components/routines/SkillGate";
import { useToast } from "../../components/Toasts";
import { fmtMinutes, fmtRange, STOPS_TEXT, timesText } from "../../components/repeats/model";
import type { HitRow } from "../../components/repeats/types";
import { watchFirst } from "./data";

/**
 * What opens under a row when the worker presses Automate: what Knack saw, what it would touch, where it would stop, and the one safe first step.
 * "Watch first" is the same choice a routine proposal in Needs you offers: it practises on the worker's next cases and compares with them, and nothing
 * runs, is saved or is sent. The other choices (with my approval, while I am away) are made one routine at a time, once it is running.
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
      if (e instanceof ApiError && e.code === "skill_gate") setGate(e.message);
      else setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again.");
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
        <p className="note">{row.status === "learning" ? "It is watching you on this one now." : "This one is running with your approval."} Its record and choices are under Running.</p>
      ) : (
        <p className="note">Watching first means it practises on your next cases and compares with what you do. Nothing runs, is saved or is sent. You choose what it may do after that, one routine at a time, under Running.</p>
      )}
      {gate && <SkillGate gate={{ mode: "shadow", done: "", message: gate }} busy={busy} onOverride={() => void go(true)} onDismiss={() => setGate(null)} />}
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="hl-peek__foot">
        {!already && routine && <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => void go()}>Watch first</button>}
        <button type="button" className="btn btn--quiet btn--sm" onClick={close}>Close</button>
      </div>
    </>
  );
}
