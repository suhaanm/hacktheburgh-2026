import { useState } from "react";
import { ApiError } from "../../api";
import { Hint } from "../../components/Hint";
import { KV } from "../../components/needsyou/KV";
import { SkillGate } from "../../components/routines/SkillGate";
import { useToast } from "../../components/Toasts";
import { Details } from "../../components/ui";
import { fmtMinutes, fmtRange, STOPS_TEXT, timesText } from "../../components/repeats/model";
import type { HitRow } from "../../components/repeats/types";
import { plainWords } from "../NeedsYou/model";
import { watchFirst } from "./data";

/**
 * What opens under a row when the worker presses Automate: what it could save, what it would touch and where it would stop as label and value, ONE short
 * paragraph (what Watch first does, printed whole: nothing runs, is saved or is sent), and ONE row of actions. What the action is, in the engine's words,
 * waits behind one closed "More". "Watch first" is the same choice a routine proposal in Needs you offers; the other choices come one routine at a time,
 * once it is running.
 */
export function Peek({ row, windowDays, source, close, onDone }: { row: HitRow; windowDays: number; source: "live" | "demo"; close: () => void; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<string | null>(null);
  const already = row.status === "learning" || row.status === "running";
  const routine = row.actions?.routine_id;
  const touches = Array.isArray(row.touches) ? row.touches.map((t) => plainWords(String(t))) : [];
  const mpw = row.minutes_per_week;

  const go = async (override = false) => {
    if (!routine) return;
    setBusy(true); setErr(null); setGate(null);
    try {
      await watchFirst(row.id, routine, source, override);
      toast({ tone: "success", text: "Set to watch first.", detail: "It practises on your next cases. Nothing runs, is saved or is sent." });
      onDone();
      close();
    } catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate(e.message);
      else setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed. Try again.");
    } finally { setBusy(false); }
  };

  return (
    <>
      <KV label="About this repeat" rows={[
        ["Could save", mpw && Number.isFinite(mpw.point) ? <>about {fmtMinutes(mpw.point)} a week<Hint label="About this figure">{fmtRange(mpw)}, 95% interval, {timesText(row.count ?? 0)} in {windowDays} days.</Hint></> : null],
        ["It touches", touches.length ? touches.join(", ") : null],
        ["It stops before", STOPS_TEXT[row.stops_before] ?? null],
      ]} />
      <p className="kc-sub" data-testid="peek-consent">{already
        ? `${row.status === "learning" ? "It is set to watch first on this one." : "This one is set to run with your approval."} Its record and choices are under Your routines.`
        : "Watch first: it practises on your next cases and compares with what you do. Nothing runs, is saved or is sent."}</p>
      {gate && <SkillGate gate={{ mode: "shadow", done: "", message: gate }} busy={busy} onOverride={() => void go(true)} onDismiss={() => setGate(null)} />}
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="hl-peek__foot">
        {!already && routine && <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => void go()}>Watch first</button>}
        <button type="button" className="btn btn--quiet btn--sm" onClick={close}>Close</button>
      </div>
      {row.what && <Details summary="More"><p className="kc-sub">{plainWords(String(row.what))}</p></Details>}
    </>
  );
}
