import type { ReactNode } from "react";
import { useRoute, type Screen } from "../../router";
import { DETAIL_SCREENS, FIRM_TABS, REVIEWER_SCREENS, canView, firmTabOf, labelOf } from "./navModel";
import { useViewRole } from "./viewAs";

/**
 * Wraps the screen in the shell. Two jobs, both small:
 *  - an Admin screen is not rendered in the Worker view (so it makes no request either); a calm state says why;
 *  - the screens under More, and the Firm views that are not destinations, carry a one-line breadcrumb with the way back (it replaces the old frame note).
 */
export function ScreenFrame({ current, children }: { current: Screen | "unknown"; children: ReactNode }) {
  const view = useViewRole();
  const route = useRoute();
  if (current !== "unknown" && !canView(current, view)) {
    return (
      <div className="page page--read">
        <div className="state" role="status">
          <h1 className="state__title">This is part of the Admin view</h1>
          <p className="state__body">Choose Admin in the account menu to see the firm.</p>
          <a className="btn btn--secondary state__action" href="#/home">Go to Home</a>
        </div>
      </div>
    );
  }
  const crumb = breadcrumb(current, route.path);
  return (
    <>
      {crumb && (
        <nav className="crumbs" aria-label="Breadcrumb">
          {crumb.map((c, i) => (i < crumb.length - 1
            ? <span key={c.label} className="crumbs__step"><a href={c.href}>{c.label}</a><span aria-hidden="true"> ›</span></span>
            : <span key={c.label} aria-current="page">{c.label}</span>))}
        </nav>
      )}
      {children}
    </>
  );
}

export interface Crumb { label: string; href: string }

/** The breadcrumb for a screen that is not a sidebar destination, or null. Pure. */
export function breadcrumb(current: Screen | "unknown", path: string): Crumb[] | null {
  if (current === "unknown") return null;
  if (DETAIL_SCREENS.includes(current) || REVIEWER_SCREENS.includes(current)) return [{ label: "Home", href: "#/home" }, { label: labelOf(current), href: `#/${current}` }];
  if (current === "firm") {
    const tab = firmTabOf(path);
    if (tab !== "overview" && tab !== "roles" && tab !== "onboarding") return [{ label: "Firm", href: "#/firm" }, { label: FIRM_TABS.find((t) => t.id === tab)?.label ?? "Firm", href: `#${path}` }];
  }
  return null;
}
