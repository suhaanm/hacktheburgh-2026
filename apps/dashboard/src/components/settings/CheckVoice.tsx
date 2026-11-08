// "Check voice": one button, then every stage a conversation needs, each Ready or the one thing to do (the desktop app writes the words; this prints them). It reads status only: it
// never asks macOS by itself, never opens the microphone and plays nothing. A button on a row is the worker's own click: Allow makes macOS ask, Open System Settings opens the pane.
// Used in Settings (under Listen for Hey Knack) and on the first run's last screen.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { navigate } from "../../router";
import { getBridge } from "../shell/bridge";
import { voiceBridge, type VoiceAction, type VoiceCheck, type VoiceStage } from "../../screens/Settings/bridge";

type Perms = { request?: (k: never) => Promise<unknown>; openSettings?: (k: never) => unknown };

/** The label of the one button on a row, or null when the row needs none. */
export function actionLabel(a: VoiceAction | null): string | null {
  if (!a) return null;
  if (a.do === "ask") return "Allow";
  if (a.do === "open") return "Open System Settings";
  if (a.do === "settings") return "Open Settings";
  return "Ask me again";
}

/** The heading line of a report: what works now, in plain words. */
export function checkHeadline(c: VoiceCheck): string {
  if (c.ok && c.heyKnack) return "Talking and Hey Knack are ready.";
  if (c.ok) return "Holding Option-Space to talk is ready. Hey Knack needs one more thing.";
  return "Voice is not ready. Fix the first line marked Fix.";
}

export function CheckVoice({ compact = false }: { compact?: boolean }) {
  const api = useMemo(() => voiceBridge(), []);
  const [report, setReport] = useState<VoiceCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = useRef(false);

  const run = useCallback(async () => {
    if (!api) return;
    setBusy(true);
    setError(null);
    try { setReport(await api.check()); shown.current = true; } catch { setError("Could not check. Nothing was changed."); } finally { setBusy(false); }
  }, [api]);

  // A permission changes in System Settings while the report is on screen: read it again when the window is looked at.
  useEffect(() => {
    if (!api) return;
    const again = () => { if (shown.current && document.visibilityState !== "hidden") void run(); };
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [api, run]);

  const act = async (s: VoiceStage) => {
    const a = s.action;
    if (!a) return;
    setError(null);
    try {
      const perms = getBridge().permissions as Perms | undefined;
      if (a.do === "ask") await perms?.request?.(a.what as never);
      else if (a.do === "open") await perms?.openSettings?.(a.what as never);
      else if (a.do === "settings") navigate("/settings");
      else await api?.askAgain();
    } catch { setError("Could not do that. Nothing was changed."); }
    if (a.do !== "open") void run();
  };

  if (!api) return null;
  const required = report ? report.stages.filter((s) => !s.optional) : [];
  const optional = report ? report.stages.filter((s) => s.optional) : [];
  const row = (s: VoiceStage) => {
    const label = actionLabel(s.action);
    return (
      <li key={s.id} className="cv__row" data-state={s.state} data-testid={`cv-${s.id}`}>
        <span className="cv__text"><b>{s.title}</b><span className="cv__line">{s.state === "ready" ? "Ready. " : "Fix. "}{s.line}</span></span>
        {label && <button type="button" className="btn btn--secondary btn--sm" onClick={() => void act(s)}>{label}</button>}
      </li>
    );
  };
  return (
    <div className="cv" data-compact={compact || undefined}>
      <div><button type="button" className="btn btn--secondary" disabled={busy} onClick={() => void run()}>{busy ? "Checking" : report ? "Check again" : "Check voice"}</button></div>
      {error && <p className="kc-error" role="alert">{error}</p>}
      {report && (
        <>
          <p className="cv__headline" role="status" data-testid="cv-headline">{checkHeadline(report)}</p>
          <ul className="cv__list" aria-label="Voice check">{required.map(row)}</ul>
          {optional.length > 0 && <ul className="cv__list cv__list--optional" aria-label="Not needed to talk">{optional.map(row)}</ul>}
        </>
      )}
    </div>
  );
}

export default CheckVoice;
