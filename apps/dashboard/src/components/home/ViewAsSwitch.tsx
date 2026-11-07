import { navigate, screenOf, useRoute } from "../../router";
import { canView } from "./navModel";
import { startTour, openPalette } from "./overlayStore";
import { shortcutLabel } from "./Overlays";
import { VIEW_LABEL, setViewRole, useViewRole, type ViewRole } from "./viewAs";

/**
 * The demo "view as" control: Worker or Admin. It is labelled a demo view and kept in memory only, so it is never mistaken for a real
 * permission. Switching to Worker while on an admin screen goes back to the worker home.
 */
export function ViewAsSwitch() {
  const view = useViewRole();
  const route = useRoute();
  const pick = (next: ViewRole) => {
    if (next === view) return;
    setViewRole(next);
    if (!canView(screenOf(route), next)) navigate("/home");
  };
  return (
    <div className="viewas">
      <div className="viewas__row">
        <span className="viewas__label" id="viewas-label">Demo view</span>
        <div className="segmented" role="group" aria-labelledby="viewas-label">
          {(["worker", "admin"] as ViewRole[]).map((r) => (
            <button key={r} type="button" aria-pressed={view === r} onClick={() => pick(r)}>{VIEW_LABEL[r]}</button>
          ))}
        </div>
      </div>
      <p className="viewas__help">
        <button type="button" className="linkish" onClick={openPalette} aria-keyshortcuts="Control+K Meta+K">Search <kbd>{shortcutLabel()}</kbd></button>
        <button type="button" className="linkish" onClick={() => startTour()}>Take the tour</button>
      </p>
    </div>
  );
}
