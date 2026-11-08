import type { ReactNode } from "react";
import { Details } from "../ui";
import { CAPTURE_TEXT } from "../../screens/YourData/model";
import { choiceFor, type AwarenessChoice, type AwarenessState } from "../../screens/YourData/awareness";
import type { DesktopSettings } from "../../screens/Settings/bridge";

export const FILES_TEXT = "Knack may search an index of the folders you chose. Folders are added in the Knack app.";
export const APP_ONLY = "Available in the Knack app.";
export const APP_ONLY_ALL = "Screen glances and folders are in the Knack app.";
export const APP_ONLY_GLANCE = "Screen glances are in the Knack app.";

function Switch({ label, checked, disabled, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="toggle st-switch">
      <input type="checkbox" role="switch" aria-label={label} checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" aria-hidden="true" />
    </label>
  );
}

function Item({ title, text, control, id }: { title: string; text: ReactNode; control: ReactNode; id: string }) {
  return (
    <div className="yd-switch" data-testid={`switch-${id}`}>
      <div className="yd-switch__text"><b>{title}</b><p className="kc-sub">{text}</p></div>
      <div className="yd-switch__control">{control}</div>
    </div>
  );
}

/**
 * Anything that lets Knack see or send a specific thing lives here, each with its consent text printed whole beside its switch: capture (times only),
 * screen glances (a reduced picture to a cloud model, never saved), the microphone and folders. A switch that needs the app says so in a browser tab.
 */
export function Switches({ capture, onCapture, busy, glance, onGlance, desktop, onDesktop, error }: {
  capture: boolean;
  onCapture: (on: boolean) => void;
  busy: boolean;
  /** Null in a browser tab: the glance switches then say they are in the app. */
  glance: AwarenessState | null;
  onGlance: (c: AwarenessChoice) => void;
  desktop: DesktopSettings | null;
  onDesktop: (patch: Partial<DesktopSettings>) => void;
  error: string | null;
}) {
  const folders = Array.isArray(desktop?.fileFolders) ? (desktop?.fileFolders as unknown[]).length : 0;
  return (
    <div className="yd-body" data-testid="switches">
      <Item id="capture" title="Learn from when I am active" text={<>{CAPTURE_TEXT} {capture ? "It is on." : "It is off."}</>} control={<Switch label="Learn from when I am active" checked={capture} disabled={busy} onChange={onCapture} />} />
      {error && <p className="kc-error" role="alert">{error}</p>}
      <Details summary="More">
        {glance === null && !desktop ? (
          <p className="kc-sub" data-testid="app-only">{APP_ONLY_ALL}</p>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-1)" }}>
            {glance === null ? (
              <p className="kc-sub">{APP_ONLY_GLANCE}</p>
            ) : !glance.available ? (
              <Item id="glance" title="Look at my screen" text="This is switched off in this build, so nothing is looked at." control={null} />
            ) : (
              <>
                <Item id="glance" title="Look at my screen when I seem stuck" text={glance.consentText} control={<Switch label="Look at my screen when I seem stuck" checked={glance.trigger && glance.agreed} onChange={(on) => onGlance(choiceFor(glance, { trigger: on }))} />} />
                {glance.trigger && glance.agreed && (
                  <>
                    <Item id="glance-periodic" title={`Also look about every ${glance.intervalSec} seconds`} text="Off unless you turn it on. Each look is listed in What it looked at or sent." control={<Switch label="Also look about every 30 seconds" checked={glance.periodic} onChange={(on) => onGlance(choiceFor(glance, { periodic: on }))} />} />
                    <Item id="glance-strict" title="Skip messaging and mail apps" text="On by default. Nothing is sent while one of them is in front." control={<Switch label="Skip messaging and mail apps" checked={glance.strict} onChange={(on) => onGlance(choiceFor(glance, { strict: on }))} />} />
                  </>
                )}
                {glance.lastSkip && <p className="kc-sub">Last look skipped: {glance.lastSkip}</p>}
              </>
            )}
            {desktop && <Item id="files" title="Search my folders" text={`${FILES_TEXT} ${folders} ${folders === 1 ? "folder" : "folders"} chosen.`} control={<Switch label="Search my folders" checked={!!desktop.filesEnabled} onChange={(on) => onDesktop({ filesEnabled: on })} />} />}
          </div>
        )}
      </Details>
    </div>
  );
}
