import { Component, Suspense, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { DEFAULT_SCREEN, navigate, screenOf, useRoute } from "./router";
import { resetSources, setState, useAppState } from "./store";
import { Loading } from "./components/common";
import { ToastHost } from "./components/Toasts";
import { AuthContextProvider, createAuth } from "./auth";
import { extensionsFrom } from "./lib/ext";
import { adoptEngineName } from "./lib/profile";
import { refreshNeedsBadge } from "./screens/NeedsYou/count";
import { ScreenFrame } from "./components/home/ScreenFrame";
import { Overlays } from "./components/home/Overlays";
import { BARE_SCREENS, labelOf } from "./components/home/navModel";
import { closeAbout, closeSettings, openSettings } from "./components/home/overlayStore";
import { useViewRole } from "./components/home/viewAs";
import { CompactBars, Sidebar } from "./components/shell/Sidebar";
import { EngineBanner } from "./components/shell/StatusLine";
import { StopProvider, StoppedBanner } from "./components/shell/StopControl";
import { FIRST_RUN_KEY, SEEN_KEY, shouldStartFirstRun } from "./screens/FirstRun/model";
import { screens } from "./screenRegistry";
import "./components/home/home.css";
import "./styles/shell.css";

class Boundary extends Component<{ children: ReactNode; screen: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidUpdate(prev: { screen: string }) { if (prev.screen !== this.props.screen && this.state.error) this.setState({ error: null }); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page page--read">
        <div className="state state--error" role="alert">
          <h1 className="state__title">This screen hit a problem</h1>
          <p className="state__body">{this.state.error.message}. Your data is untouched. Reload the page, or open another screen from the menu.</p>
          <button type="button" className="btn btn--secondary" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      </div>
    );
  }
}

const auth = createAuth();

export function App() {
  return (
    <AuthContextProvider provider={auth}>
      <ToastHost>
        <StopProvider>
          <Shell />
        </StopProvider>
      </ToastHost>
    </AuthContextProvider>
  );
}

const firstRunDone = (): boolean => { try { return window.localStorage.getItem(FIRST_RUN_KEY) !== null; } catch { return true; } };
const firstRunSeen = (): boolean => { try { return window.sessionStorage.getItem(SEEN_KEY) !== null; } catch { return false; } };
/** The Knack app sets html[data-knack-shell] on every page load; a browser tab does not. */
const inKnackApp = (): boolean => typeof document !== "undefined" && document.documentElement.dataset.knackShell !== undefined;

function Shell() {
  const route = useRoute();
  const current = screenOf(route);
  const s = useAppState();
  const view = useViewRole();
  const [nonce, setNonce] = useState(0);
  const bare = current !== "unknown" && BARE_SCREENS.includes(current);

  useEffect(() => {
    // One look at both services and the identity, then every optional screen knows whether to ask for its own data or show an example.
    const health = () => Promise.all([api.health(), api.agentHealth(), api.identity()])
      .then(([r, agent, who]) => {
        setState({ mock: r.data?.mock ?? null, engineUp: r.source === "live", ext: extensionsFrom(r.data, r.source, agent), agentUp: agent !== null, person: who?.person ?? null, role: who?.role ?? null, extReady: true });
        // A name the engine sends wins over the device's own copy. An engine that sends none may simply not know names, so the device's copy stays here;
        // the Account menu asks GET /profile, which does know, and then follows the engine whichever way it answers.
        if (typeof who?.name === "string") adoptEngineName(who.name);
      })
      .catch(() => setState({ engineUp: false, ext: extensionsFrom(null, "demo"), extReady: true }));
    void health();
    void refreshNeedsBadge();
    const on = () => { setNonce((n) => n + 1); void refreshNeedsBadge(); void health(); };
    window.addEventListener("understudy:retry", on);
    return () => window.removeEventListener("understudy:retry", on);
  }, []);
  // The origin badge describes the screen you are on, so count sources afresh for each screen.
  useEffect(() => { resetSources(); }, [current]);
  useEffect(() => { window.scrollTo(0, 0); document.title = current === "unknown" ? "Knack" : `${labelOf(current)} · Knack`; }, [current]);
  useEffect(() => { if (current === "unknown") navigate(view === "admin" ? "/firm" : `/${DEFAULT_SCREEN}`); }, [current, view]);

  // A sheet belongs to the screen it was opened on: following a link closes it (the Settings deep link below opens it again after the move).
  useEffect(() => { closeSettings(); closeAbout(); }, [route.path]);
  // An admin lands on Firm, not Home, when the address names nothing.
  useEffect(() => { if (view === "admin" && !window.location.hash.replace(/^#\/?/, "")) navigate("/firm"); }, [view]);
  // A link to #/home?settings=<section> (the old Notices address, the status line) opens the Settings sheet at that section, then tidies the address.
  const settings = route.query.get("settings");
  useEffect(() => {
    if (!settings) return;
    openSettings(settings);
    const q = new URLSearchParams(route.query);
    q.delete("settings");
    try { window.history.replaceState(null, "", `#${route.path}${q.toString() ? `?${q}` : ""}`); } catch { /* ignore */ }
  }, [settings, route.path, route.query]);
  // First run: only when the engine answered, it does not know the worker, nothing was chosen before, and the address names Home or nothing.
  useEffect(() => {
    if (shouldStartFirstRun({ engineUp: s.engineUp, extReady: s.extReady, role: s.role, person: s.person, done: firstRunDone(), path: route.path, hash: window.location.hash, query: route.query.toString(), inApp: inKnackApp(), seen: firstRunSeen() })) navigate("/first-run");
  }, [s.engineUp, s.extReady, s.role, s.person, route.path]);

  const Screen = current === "unknown" ? screens[DEFAULT_SCREEN] : screens[current];
  return (
    <div className="app" data-bare={bare || undefined}>
      <a className="skip" href="#main">Skip to the screen</a>
      {!bare && <Sidebar current={current} />}
      {!bare && <CompactBars current={current} />}
      <main id="main" className="main" tabIndex={-1}>
        {!bare && <StoppedBanner />}
        {!bare && <EngineBanner />}
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
