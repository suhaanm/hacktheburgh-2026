// The account button in the sidebar footer: an avatar and a name. It opens a small menu: View as (Worker or Admin, remembered), Appearance,
// Settings and Take the tour, plus sign-in when the identity provider is configured. The owner's Admin switch lives here and is reachable in
// two clicks (the button, then "Admin"); the choice is remembered on this device, so the second time it is no click at all.
import { useState } from "react";
import { navigate, screenOf, useRoute } from "../../router";
import { useAppState } from "../../store";
import { useAuth } from "../../auth";
import { canView } from "../home/navModel";
import { openSettings, startTour } from "../home/overlayStore";
import { VIEW_LABEL, setViewRole, useViewRole, type ViewRole } from "../home/viewAs";
import { Icon } from "./icons";
import { chord } from "./keys";
import { isApple } from "../home/Overlays";
import { THEMES, THEME_LABEL, useTheme } from "./theme";
import { usePopover } from "./usePopover";

export function AccountMenu({ placement = "up" }: { placement?: "up" | "down" }) {
  const { open, btn, pop, close, toggle } = usePopover();
  const view = useViewRole();
  const route = useRoute();
  const [theme, setTheme] = useTheme();
  const auth = useAuth();
  const role = useAppState().role;
  const user = auth.user();
  const [imgFailed, setImgFailed] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const name = user?.name ?? "Account";

  const pickView = (next: ViewRole) => {
    if (next !== view) {
      setViewRole(next);
      // An admin lands on Firm; leaving the Admin view on an admin screen goes back Home.
      if (next === "admin") navigate("/firm");
      else if (!canView(screenOf(route), next)) navigate("/home");
    }
    close();
  };
  const run = (fn: () => void) => () => { close(false); fn(); };
  const go = async (fn: () => Promise<void>, msg: string) => { setErr(null); try { await fn(); } catch { setErr(msg); } };

  return (
    <div className="account" data-placement={placement}>
      <button
        ref={btn}
        type="button"
        className="account__btn"
        data-account
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${user?.name ?? "Local profile"}`}
        onClick={() => toggle(false)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); toggle(true); } }}
      >
        {user?.picture && !imgFailed
          ? <img className="avatar" src={user.picture} alt="" width={22} height={22} referrerPolicy="no-referrer" onError={() => setImgFailed(true)} />
          : <span className="avatar" aria-hidden="true">{user ? user.name.slice(0, 1).toUpperCase() : <Icon name="person" />}</span>}
        <span className="account__name">{name}</span>
      </button>
      {open && (
        <div ref={pop} className="popover account__menu" role="menu" aria-label="Account">
          <p className="popover__meta">{user ? user.name : "Local profile"}{role ? ` · ${role}` : ""}</p>
          <div className="popover__row">
            <span className="popover__label" id="acct-view">View as</span>
            <div role="group" aria-labelledby="acct-view" className="segmented">
              {(["worker", "admin"] as ViewRole[]).map((r) => (
                <button key={r} type="button" role="menuitemradio" aria-checked={view === r} aria-pressed={view === r} onClick={() => pickView(r)}>{VIEW_LABEL[r]}</button>
              ))}
            </div>
          </div>
          <p className="popover__note">Changes what screens show. It is not a permission.</p>
          <div className="popover__row">
            <span className="popover__label" id="acct-look">Appearance</span>
            <div role="group" aria-labelledby="acct-look" className="segmented">
              {THEMES.map((t) => (
                <button key={t} type="button" role="menuitemradio" aria-checked={theme === t} aria-pressed={theme === t} onClick={() => setTheme(t)}>{THEME_LABEL[t]}</button>
              ))}
            </div>
          </div>
          <hr className="popover__rule" />
          <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={run(() => openSettings())}>Settings<kbd>{chord(",", isApple())}</kbd></button>
          <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={run(() => startTour())}>Take the tour</button>
          {user && <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={() => go(() => auth.signOut(), "Could not sign out. Close this tab to end the session.")}>Sign out</button>}
          {!user && auth.enabled && <button type="button" role="menuitem" className="popover__item popover__item--row" disabled={auth.status() === "loading"} onClick={() => go(() => auth.signIn(), "Sign-in did not finish. Nothing changed.")}>{auth.status() === "loading" ? "Signing in" : "Sign in"}</button>}
          {!user && auth.enabled && <p className="popover__note">Optional. It confirms approvals that cannot be undone.</p>}
          {err && <p className="popover__note popover__note--error" role="alert">{err}</p>}
        </div>
      )}
    </div>
  );
}
