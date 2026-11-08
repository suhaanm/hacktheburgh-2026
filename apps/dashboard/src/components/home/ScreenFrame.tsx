import type { ReactNode } from "react";
import type { Screen } from "../../router";
import { ADMIN_GATE, MORE_SCREENS, canView, labelOf } from "./navModel";
import { Breadcrumb } from "../Breadcrumb";
import { useViewRole } from "./viewAs";

/**
 * Wraps the screen in the shell. Two jobs, both small:
 *  - an Admin screen is not rendered in the Worker view (so it makes no request); the one sentence ADMIN_GATE says why, and nothing about the firm shows;
 *  - the three rows behind the Admin More carry a one-line breadcrumb with the way back (it replaces the old frame note).
 */
export function ScreenFrame({ current, children }: { current: Screen | "unknown"; children: ReactNode }) {
  const view = useViewRole();
  if (current !== "unknown" && !canView(current, view)) {
    return (
      <div className="page page--read">
        <div className="state" role="status" data-testid="admin-gate">
          <h1 className="state__title">{ADMIN_GATE}</h1>
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

/** The breadcrumb for a screen behind the Admin More, or null. Pure. */
export function breadcrumb(current: Screen | "unknown"): { label: string; href?: string }[] | null {
  if (current === "unknown") return null;
  if (MORE_SCREENS.includes(current)) return [{ label: "Firm", href: "#/firm" }, { label: labelOf(current) }];
  return null;
}
