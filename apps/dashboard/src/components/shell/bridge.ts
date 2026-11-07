// What the page may ask of the desktop app. In the desktop window the main process exposes `window.knackShell` (docs/KNACK_UX.md section 7);
// in a browser it is absent. Every member is optional and the page only offers a command whose member exists, so no row in the palette is dead.
export interface KnackShellBridge {
  platform?: string;
  /** Open the Ask bar, with the phrase filled in when there is one. */
  ask?: (phrase?: string) => void;
  /** Pause everything for a number of minutes. The desktop menu's "Pause for 1 hour". */
  pause?: (minutes: number) => void;
  /** Open macOS System Settings at a privacy pane (a human-only step: the worker grants the permission there). */
  openSystemSettings?: (pane: "accessibility" | "screen-recording") => void;
}

export function getBridge(): KnackShellBridge {
  if (typeof window === "undefined") return {};
  return ((window as unknown as { knackShell?: KnackShellBridge }).knackShell ?? {}) as KnackShellBridge;
}

/** Which desktop-only commands exist right now. */
export interface BridgeCaps { ask: boolean; pause: boolean; accessibility: boolean }
export function capsOf(b: KnackShellBridge = getBridge()): BridgeCaps {
  return { ask: typeof b.ask === "function", pause: typeof b.pause === "function", accessibility: typeof b.openSystemSettings === "function" };
}
