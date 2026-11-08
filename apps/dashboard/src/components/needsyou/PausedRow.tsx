import { useState } from "react";
import { ApiError, api } from "../../api";
import { kindLabel } from "../../lib/agents";
import { fmtTime } from "../../lib/format";
import { clip, validTime } from "../../lib/safeText";
import type { AgentRun } from "../../types";
import { useToast } from "../Toasts";
import { Glyph } from "./Glyph";

/** A background run that paused and waits for the worker. The one thing the screen can do for it is stop it; the run itself is under More, Background runs. */
export function PausedRow({ run, onDone }: { run: AgentRun; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const stop = async () => {
    setBusy(true); setErr(null);
    try { await api.agentsStop(run.run_id); toast({ tone: "success", text: "Stop sent." }); onDone(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not stop it. Nothing was changed. Try again."); }
    finally { setBusy(false); }
  };
  return (
    <article className="kc-row" data-kind="paused" data-cls="1" aria-labelledby={`ny-${run.run_id}`}>
      <h3 className="kc-row__title" id={`ny-${run.run_id}`}>
        <Glyph name="paused" />
        <span>Paused: {clip(kindLabel(run.kind), 80)}</span>
        {validTime(run.started) !== null && <time className="kc-row__when" dateTime={run.started}>{fmtTime(run.started)}</time>}
      </h3>
      <p className="kc-row__body">This run stopped to wait for you. Nothing was changed.</p>
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="kc-row__actions">
        <button type="button" className="btn btn--secondary" disabled={busy} onClick={() => void stop()}>{busy ? "Stopping" : "Stop the run"}</button>
        <a className="kc-link" href="#/agents">Open<Glyph name="chevron" /></a>
      </div>
    </article>
  );
}
