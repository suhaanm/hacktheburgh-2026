// The Settings sheet: the frame only. Cmd-comma, the account menu, the status line and the palette open it, at a section when asked.
// The contents belong to the Settings screen folder (apps/dashboard/src/screens/Settings/index.tsx, default export, props { section, onClose }):
// the shell finds that file with import.meta.glob. Until it exists, a short fallback shows the two settings the shell itself owns (Appearance and Views).
import { Suspense, lazy, useEffect, useRef, type ComponentType } from "react";
import { pick } from "../../screenRegistry";
import { closeSettings, useOverlay } from "../home/overlayStore";
import { VIEW_LABEL, setViewRole, useViewRole, type ViewRole } from "../home/viewAs";
import { Icon } from "./icons";
import { THEMES, THEME_LABEL, useTheme } from "./theme";

export interface SettingsProps { section: string | null; onClose: () => void }

const FILES = import.meta.glob("../../screens/Settings/index.tsx");
const Contents = lazy(pick(FILES, ["../../screens/Settings/index.tsx"]) ?? (async () => ({ default: Fallback as ComponentType }))) as unknown as ComponentType<SettingsProps>;

function Fallback({ section }: SettingsProps) {
  const [theme, setTheme] = useTheme();
  const view = useViewRole();
  return (
    <div className="settings__fallback" data-section={section ?? undefined}>
      <section aria-labelledby="set-look">
        <h3 id="set-look" className="settings__h">Appearance</h3>
        <div className="segmented" role="group" aria-labelledby="set-look">
          {THEMES.map((t) => <button key={t} type="button" aria-pressed={theme === t} onClick={() => setTheme(t)}>{THEME_LABEL[t]}</button>)}
        </div>
      </section>
      <section aria-labelledby="set-views">
        <h3 id="set-views" className="settings__h">Views</h3>
        <div className="segmented" role="group" aria-label="View as">
          {(["worker", "admin"] as ViewRole[]).map((r) => <button key={r} type="button" aria-pressed={view === r} onClick={() => setViewRole(r)}>{VIEW_LABEL[r]}</button>)}
        </div>
      </section>
      <p><a href="#/setup" onClick={() => closeSettings()}>Set up again</a></p>
    </div>
  );
}

export function SettingsSheet() {
  const { settings } = useOverlay();
  return settings ? <Sheet section={settings.section} /> : null;
}

function Sheet({ section }: { section: string | null }) {
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(typeof document === "undefined" ? null : document.activeElement);
  useEffect(() => {
    box.current?.querySelector<HTMLElement>("button")?.focus();
    const back = opener.current as HTMLElement | null;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); closeSettings(); return; }
      if (e.key !== "Tab" || !box.current) return;
      const f = Array.from(box.current.querySelectorAll<HTMLElement>('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')).filter((x) => !x.hasAttribute("disabled") && x.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); if (back && document.contains(back)) back.focus(); };
  }, []);
  return (
    <div className="drawer" data-testid="settings-sheet">
      <div className="drawer__scrim" onClick={closeSettings} aria-hidden="true" />
      <div ref={box} className="drawer__panel" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="drawer__head">
          <h2 id="settings-title" className="drawer__title">Settings</h2>
          <button type="button" className="drawer__close" aria-label="Close settings" onClick={closeSettings}><Icon name="close" /></button>
        </header>
        <div className="drawer__body">
          <Suspense fallback={<p className="note" role="status">Opening settings</p>}>
            <Contents section={section} onClose={closeSettings} />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
