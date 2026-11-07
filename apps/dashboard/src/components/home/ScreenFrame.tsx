import type { ReactNode } from "react";
import type { Screen } from "../../router";
import { DETAIL_SCREENS, REVIEWER_SCREENS, canView, labelOf } from "./navModel";
import { Breadcrumb } from "../Breadcrumb";
import { useViewRole } from "./viewAs";

/**
 * Wraps the screen in the shell. Two jobs, both small:
 *  - an Admin screen is not rendered in the Worker view (so it makes no request either); a calm state says why;
 *  - the screens under More, and the Firm views that are not destinations, carry a one-line breadcrumb with the way back (it replaces the old frame note).
 */
export function ScreenFrame({ current, children }: { current: Screen | "unknown"; children: ReactNode }) {
  const view = useViewRole();
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
  const crumb = breadcrumb(current);
  return (
    <>
      {crumb && <div className="crumb-wrap"><Breadcrumb items={crumb} /></div>}
      {children}
    </>
  );
}

/** The breadcrumb for a screen that is not a sidebar destination, or null. Pure. */
export function breadcrumb(current: Screen | "unknown"): { label: string; href?: string }[] | null {
  if (current === "unknown") return null;
  if (DETAIL_SCREENS.includes(current) || REVIEWER_SCREENS.includes(current)) return [{ label: "Home", href: "#/home" }, { label: labelOf(current) }];
  return null;
}
