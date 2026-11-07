import type { ReactNode } from "react";
import type { Screen } from "../../router";
import { DETAIL_SCREENS, REVIEWER_SCREENS, canView } from "./navModel";
import { useViewRole } from "./viewAs";

/**
 * Wraps the screen in the shell. Three jobs, all small:
 *  - an Admin screen is not rendered in the Worker view (so it makes no request either); a calm state says why;
 *  - the Details screens carry one line saying these are the detailed numbers, with the way back to "Your week";
 *  - the Evidence screen says it is for reviewers.
 */
export function ScreenFrame({ current, children }: { current: Screen | "unknown"; children: ReactNode }) {
  const view = useViewRole();
  if (current !== "unknown" && !canView(current, view)) {
    return (
      <div className="page page--read">
        <div className="state" role="status">
          <span className="state__mark" aria-hidden="true" />
          <h1 className="state__title">This screen is part of the Admin view</h1>
          <p className="state__body">You are in the Worker view, which shows your own week. Choose the Admin view in the menu to see the firm.</p>
          <a className="btn btn--secondary state__action" href="#/home">Go to your week</a>
        </div>
      </div>
    );
  }
  const detail = current !== "unknown" && DETAIL_SCREENS.includes(current);
  const reviewers = current !== "unknown" && REVIEWER_SCREENS.includes(current);
  return (
    <>
      {detail && (
        <p className="framenote" role="note">
          <span>These are the detailed numbers. Your week shows the few that matter.</span>
          <a href="#/home">Back to your week</a>
        </p>
      )}
      {reviewers && (
        <p className="framenote" role="note">
          <span>For reviewers: how every number was checked. You do not need this day to day.</span>
          <a href="#/home">Back to your week</a>
        </p>
      )}
      {children}
    </>
  );
}
