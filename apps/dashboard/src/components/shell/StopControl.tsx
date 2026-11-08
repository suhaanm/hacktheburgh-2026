// Stop everything. The logic of the old KillSwitch, kept: one press calls the kill endpoint, the page shows the stopped state, Shift-Escape and
// Shift-Command-K do the same (inside Knack; the global key belongs to the desktop), and "Resume" clears it. What changes is where it is drawn:
// a small labelled button in the sidebar footer (a red square and the word) instead of a permanent fixed pill, and the stopped bar stays as the
// in-window banner. The stopped state is always printed (honesty: the kill state is never only a colour).
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../../api";
import { dataMode, getState, setState, useAppState } from "../../store";
import { useToast } from "../Toasts";
import { Icon } from "./icons";
import { shellKeyAction } from "./keys";
import { getViewRole } from "../home/viewAs";

/** How often the window asks whether everything is stopped while it is in view (a Stop or Resume from the corner pill, the menu bar or a hotkey shows within this and a request). */
export const KILL_POLL_MS = 3000;
/** The same, while the window is visible but not the one being used. */
export const KILL_POLL_UNFOCUSED_MS = 5000;
export const killPollDelay = (): number => (typeof document !== "undefined" && typeof document.hasFocus === "function" && !document.hasFocus() ? KILL_POLL_UNFOCUSED_MS : KILL_POLL_MS);

interface StopApi { stop: () => Promise<void>; resume: () => Promise<void>; busy: boolean }
const Ctx = createContext<StopApi>({ stop: async () => undefined, resume: async () => undefined, busy: false });
export const useStop = (): StopApi => useContext(Ctx);

export function StopProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const stop = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.kill();
      setState({ killed: r.killed, killedAt: r.at, killError: null });
      // "Stopped." when a service answered; one more short sentence when none did, because then only the screen changed.
      toast({ tone: "success", text: "Stopped.", detail: dataMode(getState()) === "demo" ? "No service was running." : undefined });
    } catch (e) {
      const m = e instanceof Error ? e.message : "The stop request failed.";
      setState({ killError: m });
      toast({ tone: "error", text: "Stop was not confirmed.", detail: m });
    } finally { setBusy(false); }
  }, [busy, toast]);

  const resume = useCallback(async () => {
    setBusy(true);
    try {
      const r = await api.clearKill();
      setState({ killed: r.killed, killedAt: r.at, killError: null });
      toast({ tone: "plain", text: "Resumed.", detail: "Nothing starts by itself. Routines still follow the consent you gave them." });
    } catch (e) {
      toast({ tone: "error", text: "Could not resume.", detail: e instanceof Error ? e.message : "" });
    } finally { setBusy(false); }
  }, [toast]);

  // Stop everything can come from outside this page (the corner pill, the menu bar, the Dock menu, the hotkey) and so can Resume: read the state when the page opens, when the window is
  // looked at again, and every few seconds while it is in view, so the Stop button and the banner never disagree with the corner card (within three seconds).
  useEffect(() => {
    let live = true;
    let pending = false;                                   // one read at a time: a slow engine is not asked again while it is still answering
    const read = () => {
      if (document.visibilityState === "hidden" || pending) return;
      pending = true;
      api.killState().then((r) => { if (live) setState({ killed: !!r.data?.killed, killedAt: r.data?.at ?? null }); }).catch(() => undefined).finally(() => { pending = false; });
    };
    read();
    // The next look is 3 s away while the window has the focus and 5 s away while it does not (it is only visible behind something else then).
    let timer = 0;
    const next = () => { timer = window.setTimeout(() => { read(); next(); }, killPollDelay()); };
    next();
    window.addEventListener("focus", read);
    window.addEventListener("understudy:retry", read);
    document.addEventListener("visibilitychange", read);
    return () => { live = false; window.clearTimeout(timer); window.removeEventListener("focus", read); window.removeEventListener("understudy:retry", read); document.removeEventListener("visibilitychange", read); };
  }, []);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.shiftKey && e.key === "Escape") { e.preventDefault(); void stop(); return; }
      if (shellKeyAction(e, getViewRole())?.type === "stop") { e.preventDefault(); void stop(); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [stop]);

  const value = useMemo(() => ({ stop, resume, busy }), [stop, resume, busy]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/**
 * What the Stop button looks like, with no hooks so a test can draw it. The red square is drawn by CSS (the design system's `.stop-button::before`) and
 * nowhere else: this markup carries the word only. A second square here (an icon, a glyph) is the double-icon bug, and stop.test.ts fails on it.
 */
export function StopFace({ killed, compact = false, busy = false, onClick }: { killed: boolean; compact?: boolean; busy?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      className="stop-button"
      data-compact={compact || undefined}
      aria-pressed={killed}
      onClick={onClick}
      disabled={busy}
      aria-label={killed ? "Resume after stop" : "Stop everything now"}
    >
      <span>{killed ? "Resume" : "Stop"}</span>
    </button>
  );
}

/** A red square and the word, 32 px high, on every screen: in the sidebar footer, and in the bar at the top of a narrow window. */
export function StopButton({ compact = false }: { compact?: boolean }) {
  const killed = useAppState().killed;
  const { stop, resume, busy } = useStop();
  return <StopFace killed={killed} compact={compact} busy={busy} onClick={killed ? resume : stop} />;
}

/** The time a stop began, as the banner prints it ("since 14:05"); empty for no time or one that is not a date. */
export function sinceText(killedAt: string | null): string {
  if (!killedAt) return "";
  const d = new Date(killedAt);
  return Number.isFinite(d.getTime()) ? ` (since ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })})` : "";
}

/** The banner's markup, with no hooks. It names the state in words (never only a colour) and carries one alert icon, not a stop square. */
export function StoppedBar({ killedAt, busy = false, onResume }: { killedAt: string | null; busy?: boolean; onResume?: () => void }) {
  return (
    <div className="banner-wrap stopped-banner">
      <div className="inline-banner" role="alert" data-tone="bad">
        <Icon name="alert" />
        <span className="inline-banner__text">
          <b>Everything is stopped.</b> No agent will run and no routine will start{sinceText(killedAt)}.
        </span>
        <button type="button" className="btn btn--secondary btn--sm" onClick={onResume} disabled={busy}>Resume</button>
      </div>
    </div>
  );
}

/** The in-window banner while everything is stopped. It names the state and offers the way back; it is not drawn when nothing is stopped. */
export function StoppedBanner() {
  const s = useAppState();
  const { resume, busy } = useStop();
  if (!s.killed) return null;
  return <StoppedBar killedAt={s.killedAt} busy={busy} onResume={resume} />;
}
