// The status line (replaces the old data note): a dot and at most four words saying whether Knack is using live models or example data.
// It opens Settings at "Use live models". The engine-unreachable case also prints one line at the top of the content (EngineBanner).
import { useEffect, useState } from "react";
import { api, forgetBackoff } from "../../api";
import { dataMode, resetSources, useAppState } from "../../store";
import { openSettings } from "../home/overlayStore";
import { Icon } from "./icons";
import { statusFor, type Status } from "./statusModel";

/** The current status, with a timer so a silent engine is reported after 30 seconds instead of "Starting" for ever. */
export function useStatus(): Status {
  const s = useAppState();
  const [waited, setWaited] = useState(0);
  useEffect(() => {
    if (s.engineUp !== null) return;
    const t0 = Date.now();
    const id = window.setInterval(() => setWaited(Date.now() - t0), 1000);
    return () => window.clearInterval(id);
  }, [s.engineUp]);
  return statusFor({ engineUp: s.engineUp, mock: s.mock, mode: dataMode(s), waitedMs: waited });
}

export function StatusLine() {
  const st = useStatus();
  return (
    <button type="button" className="status-line" data-kind={st.kind} data-mode={st.kind === "live" ? "live" : st.kind === "down" ? "down" : undefined} onClick={() => openSettings("live-models")} aria-label={`${st.text}. Open the live models setting.`}>
      <span className="status-line__dot" aria-hidden="true" />
      <span className="status-line__text">{st.text}</span>
    </button>
  );
}

/** One line at the top of the content when the engine cannot be reached. Nothing is changed by it; Try again asks once more. */
export function EngineBanner() {
  const st = useStatus();
  if (st.kind !== "down") return null;
  const retry = () => { forgetBackoff(); resetSources(); window.dispatchEvent(new Event("understudy:retry")); void api.health(); };
  return (
    <div className="banner-wrap">
      <div className="inline-banner" role="status" data-tone="warn" data-testid="engine-banner">
        <Icon name="alert" />
        <span className="inline-banner__text">Knack cannot reach its engine.</span>
        <button type="button" className="btn btn--secondary btn--sm" onClick={retry}>Try again</button>
      </div>
    </div>
  );
}
