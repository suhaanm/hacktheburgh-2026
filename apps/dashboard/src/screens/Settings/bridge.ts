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

/**
 * The shell's own live-models calls (Track A): `models.get()` says whether live models are on and whether a key was found, `models.setUseLiveModels(on)`
 * restarts the services the app started. Absent in a browser tab and in an older shell: the switch is then disabled and says so.
 */
export interface LiveModelsBridge {
  get(): Promise<{ useLiveModels?: boolean; keyPresent?: boolean; live?: boolean }>;
  setUseLiveModels(on: boolean): Promise<unknown>;
}

type Win = { alongside?: Partial<DesktopBridge>; knackSettings?: Partial<DesktopBridge>; knackShell?: { models?: Partial<LiveModelsBridge> } };

/** The live-models bridge, or null. */
export function liveModelsBridge(w: Win | undefined = typeof window === "undefined" ? undefined : (window as unknown as Win)): LiveModelsBridge | null {
  const m = w?.knackShell?.models;
  return m && typeof m.get === "function" && typeof m.setUseLiveModels === "function" ? (m as LiveModelsBridge) : null;
}

/** The bridge, or null in a browser tab. Both names are accepted so the shell can pick either. */
export function desktopBridge(w: Win | undefined = typeof window === "undefined" ? undefined : (window as unknown as Win)): DesktopBridge | null {
  for (const cand of [w?.knackSettings, w?.alongside]) {
    if (cand && typeof cand.getSettings === "function" && typeof cand.patchSettings === "function") return cand as DesktopBridge;
  }
  return null;
}
