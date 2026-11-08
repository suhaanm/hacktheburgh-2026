// The account button in the sidebar footer: an avatar and the worker's name. It opens a small menu. At the top, who the worker is (name and role; with no name
// yet, "Your name" opens the editor in place). Then Change profile (name and role), Set up again, View as (Worker or Admin, remembered), Settings and Take the tour,
// plus sign-in when the identity provider is configured. Appearance lives in Settings. The owner's Admin switch is reachable in two clicks (the button, then
// "Admin"); the choice is remembered on this device. A name is kept on this Mac only.
import { useEffect, useState } from "react";
import { api } from "../../api";
import { ADD_NAME, adoptEngineName, initialOf, roleLabel, useDisplayName, type ProfileRole } from "../../lib/profile";
import { navigate, screenOf, useRoute } from "../../router";
import { useAppState } from "../../store";
import { useAuth } from "../../auth";
import { canView, landingFor } from "../home/navModel";
import { openSettings, startTour } from "../home/overlayStore";
import { VIEW_LABEL, setViewRole, useViewRole, type ViewRole } from "../home/viewAs";
import { Icon } from "./icons";
import { chord } from "./keys";
import { isApple } from "../home/Overlays";
import { ProfileForm } from "./ProfileForm";
import { usePopover } from "./usePopover";

export function AccountMenu({ placement = "up" }: { placement?: "up" | "down" }) {
  const { open, btn, pop, close, toggle } = usePopover();
  const view = useViewRole();
  const route = useRoute();
  const auth = useAuth();
  const role = useAppState().role;
  const user = auth.user();
  const [saved] = useDisplayName();
  const [imgFailed, setImgFailed] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [roles, setRoles] = useState<ProfileRole[] | null>(null);
  const name = saved ?? user?.name ?? null;
  const roleText = roleLabel(role, roles);

  // The roles to pick from, and the engine's word about the name, are asked once when the menu first opens (GET /profile). An engine without that route
  // gets the packs instead, and the name stays on this device. Before they arrive the role id is shown as words.
  useEffect(() => {
    if (!open || roles !== null) return;
    let live = true;
    api.profile()
      .then(async (p) => {
        if (p) { adoptEngineName(p.name); return p.roles; }
        return (await api.packs()).data.map((x) => ({ id: x.id, name: x.name, summary: x.summary, depth: x.depth }));
      })
      .then((r) => { if (live) setRoles(Array.isArray(r) ? r : []); }, () => { if (live) setRoles([]); });
    return () => { live = false; };
  }, [open, roles]);
  useEffect(() => { if (!open) setEditing(false); }, [open]);

  const pickView = (next: ViewRole) => {
    if (next !== view) {
      setViewRole(next);
      // Each view opens on its own screen: an admin on Firm, a worker on Home (and leaving the Admin view on an Admin screen never lands on a gate).
      if (next === "admin") navigate(`/${landingFor("admin")}`);
      else if (!canView(screenOf(route), next) || screenOf(route) === landingFor("admin")) navigate(`/${landingFor("worker")}`);
    }
    close();
  };
  const run = (fn: () => void) => () => { close(false); fn(); };
  const go = async (fn: () => Promise<void>, msg: string) => { setErr(null); try { await fn(); } catch { setErr(msg); } };
  const initial = initialOf(name);

  return (
    <div className="account" data-placement={placement}>
      <button
        ref={btn}
        type="button"
        className="account__btn"
        data-account
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${name ?? "Local profile"}`}
        onClick={() => toggle(false)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); toggle(true); } }}
      >
        {user?.picture && !saved && !imgFailed
          ? <img className="avatar" src={user.picture} alt="" width={22} height={22} referrerPolicy="no-referrer" onError={() => setImgFailed(true)} />
          : <span className="avatar" aria-hidden="true">{initial ?? <Icon name="person" />}</span>}
        <span className="account__name" dir="auto">{name ?? "Account"}</span>
      </button>
      {open && (
        <div ref={pop} className="popover account__menu" role="menu" aria-label="Account">
          {editing ? (
            <ProfileForm name={saved} role={role} roles={roles} onDone={() => { setEditing(false); btn.current?.focus(); }} />
          ) : (
            <>
              <div className="account__who" data-testid="account-who">
                {name
                  ? <b className="account__who-name" dir="auto">{name}</b>
                  : <button type="button" role="menuitem" className="account__who-add" onClick={() => setEditing(true)}>{ADD_NAME}</button>}
                {roleText && <span className="account__who-role">{roleText}</span>}
              </div>
              <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={() => setEditing(true)}>Change profile</button>
              <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={run(() => navigate("/setup"))}>Set up again</button>
              <hr className="popover__rule" />
              <div className="popover__row">
                <span className="popover__label" id="acct-view">View as</span>
                <div role="group" aria-labelledby="acct-view" className="segmented">
                  {(["worker", "admin"] as ViewRole[]).map((r) => (
                    <button key={r} type="button" role="menuitemradio" aria-checked={view === r} aria-pressed={view === r} onClick={() => pickView(r)}>{VIEW_LABEL[r]}</button>
                  ))}
                </div>
              </div>
              <p className="popover__note">Changes what screens show. It is not a permission.</p>
              <hr className="popover__rule" />
              <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={run(() => openSettings())}>Settings<kbd>{chord(",", isApple())}</kbd></button>
              <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={run(() => startTour())}>Take the tour</button>
              {user && <button type="button" role="menuitem" className="popover__item popover__item--row" onClick={() => go(() => auth.signOut(), "Could not sign out. Close this tab to end the session.")}>Sign out</button>}
              {!user && auth.enabled && <button type="button" role="menuitem" className="popover__item popover__item--row" disabled={auth.status() === "loading"} onClick={() => go(() => auth.signIn(), "Sign-in did not finish. Nothing changed.")}>{auth.status() === "loading" ? "Signing in" : "Sign in"}</button>}
              {!user && auth.enabled && <p className="popover__note">Optional. It confirms approvals that cannot be undone.</p>}
              {err && <p className="popover__note popover__note--error" role="alert">{err}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
