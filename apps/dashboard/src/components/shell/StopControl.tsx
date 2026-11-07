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

  useEffect(() => {
    api.killState().then((r) => setState({ killed: !!r.data?.killed, killedAt: r.data?.at ?? null })).catch(() => undefined);
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

/** A red square and the word, 32 px high, on every screen: in the sidebar footer, and in the bar at the top of a narrow window. */
export function StopButton({ compact = false }: { compact?: boolean }) {
  const killed = useAppState().killed;
  const { stop, resume, busy } = useStop();
  return (
    <button
      type="button"
      className="stop-button"
      data-compact={compact || undefined}
      aria-pressed={killed}
      onClick={killed ? resume : stop}
      disabled={busy}
      aria-label={killed ? "Resume after stop" : "Stop everything now"}
    >
      <span>{killed ? "Resume" : "Stop"}</span>
    </button>
  );
}

/** The in-window banner while everything is stopped. It names the state and offers the way back; it is not drawn when nothing is stopped. */
export function StoppedBanner() {
  const s = useAppState();
  const { resume, busy } = useStop();
  if (!s.killed) return null;
  return (
    <div className="banner-wrap stopped-banner">
      <div className="inline-banner" role="alert" data-tone="bad">
        <Icon name="alert" />
        <span className="inline-banner__text">
          <b>Everything is stopped.</b> No agent will run and no routine will start{s.killedAt ? ` (since ${new Date(s.killedAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })})` : ""}.
        </span>
        <button type="button" className="btn btn--secondary btn--sm" onClick={resume} disabled={busy}>Resume</button>
      </div>
    </div>
  );
}
