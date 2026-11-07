// The desktop app's own settings, when this page runs inside the Knack window. In a browser tab there is no bridge and the desktop-only rows say so.
// Contract with the shell (docs/KNACK_UX.md section 7): the main window's preload exposes the existing `getSettings` and `patchSettings` calls
// (window.alongside today). The keys read here are the desktop's own: useLiveModels, minimiseWhileWorking, launchAtLogin, cueEnabled,
// helpLevelMode, lockedLevel. A live-models change restarts the services the app started, which takes about 20 seconds.
export interface DesktopSettings {
  useLiveModels?: boolean;
  minimiseWhileWorking?: boolean;
  launchAtLogin?: boolean;
  cueEnabled?: boolean;
  helpLevelMode?: "auto" | "locked";
  lockedLevel?: number;
  [k: string]: unknown;
}

export interface DesktopBridge {
  getSettings(): Promise<DesktopSettings>;
  patchSettings(patch: Partial<DesktopSettings>): Promise<DesktopSettings | void>;
}

type Win = { alongside?: Partial<DesktopBridge>; knackSettings?: Partial<DesktopBridge> };

/** The bridge, or null in a browser tab. Both names are accepted so the shell can pick either. */
export function desktopBridge(w: Win | undefined = typeof window === "undefined" ? undefined : (window as unknown as Win)): DesktopBridge | null {
  for (const cand of [w?.knackSettings, w?.alongside]) {
    if (cand && typeof cand.getSettings === "function" && typeof cand.patchSettings === "function") return cand as DesktopBridge;
  }
  return null;
}
