import { Component, Suspense, lazy, useCallback, useEffect, useState, type ReactNode } from "react";
import { api, ENGINE_LABEL, forgetBackoff, refreshQueueBadge } from "./api";
import { DEFAULT_SCREEN, navigate, screenOf, useRoute, type Screen } from "./router";
import { dataMode, getState, resetSources, setState, useAppState } from "./store";
import { Loading } from "./components/common";
import { ToastHost, useToast } from "./components/Toasts";
import { AttentionBanner } from "./components/AttentionBanner";
import { AuthContextProvider, createAuth, useAuth } from "./auth";
import { extensionsFrom } from "./lib/ext";
import { RoleNav } from "./components/home/RoleNav";
import { ViewAsSwitch } from "./components/home/ViewAsSwitch";
import { ScreenFrame } from "./components/home/ScreenFrame";
import { Overlays } from "./components/home/Overlays";
import { labelOf } from "./components/home/navModel";
import "./components/home/home.css";

const screens: Record<Screen, ReturnType<typeof lazy>> = {
  genome: lazy(() => import("./screens/Genome")),
  presence: lazy(() => import("./screens/Presence")),
  routines: lazy(() => import("./screens/Routines")),
  queue: lazy(() => import("./screens/Queue")),
  graph: lazy(() => import("./screens/Graph")),
  today: lazy(() => import("./screens/Today")),
  memory: lazy(() => import("./screens/Memory")),
  evidence: lazy(() => import("./screens/Evidence")),
  onboarding: lazy(() => import("./screens/Onboarding")),
  week: lazy(() => import("./screens/Week")),
  briefing: lazy(() => import("./screens/Briefing")),
  agents: lazy(() => import("./screens/Agents")),
  privacy: lazy(() => import("./screens/Privacy")),
  growth: lazy(() => import("./screens/Growth")),
  models: lazy(() => import("./screens/Models")),
  git: lazy(() => import("./screens/Git")),
  notices: lazy(() => import("./screens/Notices")),
  home: lazy(() => import("./screens/Home")),
  firm: lazy(() => import("./screens/Firm")),
  predictions: lazy(() => import("./screens/Predictions")),
  repeats: lazy(() => import("./screens/Repeats")),
};

/** The menu lives in components/home/navModel.ts (one data file for the menu, palette, tour and the Admin route gate). */

type Theme = "auto" | "light" | "dark";
function loadTheme(): Theme {
  try {
    const t = window.localStorage.getItem("understudy-theme");
    if (t === "light" || t === "dark") return t;
  } catch { /* storage can be blocked */ }
  return "auto";
}
function applyTheme(t: Theme) {
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  try { window.localStorage.setItem("understudy-theme", t); } catch { /* ignore */ }
}

class Boundary extends Component<{ children: ReactNode; screen: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidUpdate(prev: { screen: string }) { if (prev.screen !== this.props.screen && this.state.error) this.setState({ error: null }); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page">
        <div className="state state--error" role="alert">
          <span className="state__mark" aria-hidden="true" />
          <h1 className="state__title">This screen hit a problem</h1>
          <p className="state__body">{this.state.error.message}. Your data is untouched. Reload the page, or open another screen from the menu.</p>
          <button type="button" className="btn btn--secondary" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      </div>
    );
  }
}

function Wordmark() {
  return (
    <a className="wordmark" href={`#/${DEFAULT_SCREEN}`} aria-label="Understudy home">
      <svg width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
        <rect x="0" y="2" width="14" height="4.5" rx="1" fill="var(--expert)" />
        <rect x="4" y="9.5" width="18" height="4.5" rx="1" fill="var(--novice)" />
      </svg>
      <span>Understudy</span>
    </a>
  );
}

function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  useEffect(() => applyTheme(theme), [theme]);
  return (
    <div className="segmented" role="group" aria-label="Colour theme">
      {(["auto", "light", "dark"] as Theme[]).map((t) => (
        <button key={t} type="button" aria-pressed={theme === t} onClick={() => setTheme(t)}>
          {t === "auto" ? "Auto" : t === "light" ? "Light" : "Dark"}
        </button>
      ))}
    </div>
  );
}

function DataNote() {
  const s = useAppState();
  const mode = dataMode(s);
  const retry = () => { forgetBackoff(); resetSources(); window.dispatchEvent(new Event("understudy:retry")); void api.health(); };
  if (mode === "unknown") return <p className="datanote">Connecting</p>;
  if (mode === "live") {
    return <p className="datanote" data-mode="live"><span className="datanote__dot" aria-hidden="true" />Live engine{s.mock ? ", mock mode" : ""}</p>;
  }
  return (
    <p className="datanote" data-mode={mode}>
      <span className="datanote__dot" aria-hidden="true" />
      {mode === "demo" ? "Demo data" : "Some demo data"}
      <span className="datanote__why">{mode === "demo" ? `${ENGINE_LABEL} is not running.` : "A service did not answer some requests, so some screens show example data."}</span>
      <button type="button" className="linkish" onClick={retry}>Try again</button>
    </p>
  );
}

function KillSwitch() {
  const s = useAppState();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const stop = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.kill();
      setState({ killed: r.killed, killedAt: r.at, killError: null });
      toast({ tone: "success", text: "Stopped.", detail: dataMode(getState()) === "demo" ? "No service was reachable, so nothing was running. In demo mode this only changes the screen." : "Agent runs, background routines and coaching are off until you resume." });
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
    const on = (e: KeyboardEvent) => { if (e.shiftKey && e.key === "Escape") { e.preventDefault(); void stop(); } };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [stop]);

  return (
    <>
      {s.killed && (
        <div className="killbar" role="alert">
          <p>
            <b>Everything is stopped.</b> No agent will run and no routine will start{s.killedAt ? ` (since ${new Date(s.killedAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })})` : ""}.
          </p>
          <button type="button" className="btn btn--secondary" onClick={resume} disabled={busy}>Resume</button>
        </div>
      )}
      <button type="button" className="kill kill--fixed" aria-pressed={s.killed} onClick={s.killed ? resume : stop} disabled={busy} aria-label={s.killed ? "Resume after stop" : "Stop everything now"}>
        <span className="kill__icon" aria-hidden="true" />
        {s.killed ? <><span className="kill__long">Stopped. Click to resume</span><span className="kill__short">Resume</span></> : <><span className="kill__long">Stop everything</span><span className="kill__short">Stop</span></>}
        {!s.killed && <kbd aria-hidden="true">Shift Esc</kbd>}
      </button>
    </>
  );
}

const auth = createAuth();

export function App() {
  return (
    <AuthContextProvider provider={auth}>
      <ToastHost>
        <Shell />
      </ToastHost>
    </AuthContextProvider>
  );
}

/** Quiet sign-in. Optional: nothing waits on it, and without Auth0 it only says "Local profile". */
function AuthControl() {
  const auth = useAuth();
  const role = useAppState().role;
  const user = auth.user();
  const [err, setErr] = useState<string | null>(null);
  const [imgFailed, setImgFailed] = useState(false);
  const go = async (fn: () => Promise<void>, msg: string) => { setErr(null); try { await fn(); } catch { setErr(msg); } };
  if (user) {
    return (
      <div className="authctl">
        {user.picture && !imgFailed
          ? <img className="authctl__avatar" src={user.picture} alt="" width={22} height={22} referrerPolicy="no-referrer" onError={() => setImgFailed(true)} />
          : <span className="authctl__avatar authctl__avatar--letter" aria-hidden="true">{user.name.slice(0, 1).toUpperCase()}</span>}
        <span className="authctl__name">{user.name}</span>
        <button type="button" className="linkish" onClick={() => go(() => auth.signOut(), "Could not sign out. Close this tab to end the session.")}>Sign out</button>
        {err && <span className="field__error" role="alert">{err}</span>}
      </div>
    );
  }
  return (
    <div className="authctl">
      <span className="authctl__name">Local profile{role ? ` · ${role}` : ""}</span>
      {auth.enabled && <button type="button" className="linkish" disabled={auth.status() === "loading"} onClick={() => go(() => auth.signIn(), "Sign-in did not finish. Nothing changed.")}>{auth.status() === "loading" ? "Signing in" : "Sign in"}</button>}
      {auth.enabled && <span className="datanote__why">Optional. Used to confirm approvals that cannot be undone.</span>}
      {err && <span className="field__error" role="alert">{err}</span>}
    </div>
  );
}

function Shell() {
  const route = useRoute();
  const current = screenOf(route);
  const s = useAppState();
  const [menu, setMenu] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    // One look at both services and the identity, then every optional screen knows whether to ask for its own data or show an example.
    const health = () => Promise.all([api.health(), api.agentHealth(), api.identity()])
      .then(([r, agent, who]) => setState({ mock: r.data?.mock ?? null, ext: extensionsFrom(r.data, r.source, agent), agentUp: agent !== null, person: who?.person ?? null, role: who?.role ?? null, extReady: true }))
      .catch(() => setState({ ext: extensionsFrom(null, "demo"), extReady: true }));
    void health();
    void refreshQueueBadge();
    const on = () => { setNonce((n) => n + 1); void refreshQueueBadge(); void health(); };
    window.addEventListener("understudy:retry", on);
    return () => window.removeEventListener("understudy:retry", on);
  }, []);
  // The data note describes the screen you are on, so count sources afresh for each screen.
  useEffect(() => { resetSources(); }, [current]);
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); document.title = `${labelOf(current)} · Understudy`; }, [current]);
  useEffect(() => { if (current === "unknown") navigate(`/${DEFAULT_SCREEN}`); }, [current]);

  const Screen = current === "unknown" ? screens[DEFAULT_SCREEN] : screens[current];
  return (
    <div className="app">
      <a className="skip" href="#main">Skip to the screen</a>
      <KillSwitch />
      <header className="topbar">
        <Wordmark />
        <button type="button" className="btn btn--secondary btn--sm" aria-expanded={menu} aria-controls="nav" onClick={() => setMenu((m) => !m)}>
          {menu ? "Close" : "Menu"}
        </button>
      </header>
      <aside className="side" data-open={menu}>
        <div className="side__brand"><Wordmark /></div>
        <nav id="nav" aria-label="Screens" className="nav">
          <RoleNav current={current} pending={s.pendingQueue} />
        </nav>
        <div className="side__foot">
          <AuthControl />
          <DataNote />
          <ViewAsSwitch />
          <ThemeSwitch />
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        <AttentionBanner />
        <ScreenFrame current={current}>
          <Boundary screen={current}>
            <Suspense fallback={<div className="page"><Loading label="Loading screen" /></div>}>
              <Screen key={`${current}-${nonce}`} />
            </Suspense>
          </Boundary>
        </ScreenFrame>
      </main>
      <Overlays />
    </div>
  );
}
