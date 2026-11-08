// What the page may ask of the desktop app. In the desktop window the main process exposes `window.knackShell` (docs/KNACK_UX.md section 7);
// in a browser it is absent. Every member is optional and the page only offers a command whose member exists, so no row in the palette and no
// button on first run is dead.

/** The three macOS permissions Knack can use, by the names the shell uses. */
export type PermKind = "microphone" | "speech" | "screen";
export const PERM_KINDS: PermKind[] = ["microphone", "speech", "screen"];
/** granted: allowed. not-asked: macOS has not been asked yet, so a request shows its prompt. off: turned off (or restricted) in System Settings, which only the worker can change. */
export type PermState = "granted" | "not-asked" | "off";

export interface KnackShellBridge {
  platform?: string;
  /** Open the Ask bar, with the phrase filled in when there is one. */
  ask?: (phrase?: string) => void;
  /** Pause everything for a number of minutes. The desktop menu's "Pause for 1 hour". */
  pause?: (minutes: number) => void;
  /** Open macOS System Settings at a privacy pane (a human-only step: the worker grants the permission there). */
  openSystemSettings?: (pane: "accessibility" | "screen-recording") => void;
  /** The permissions the first run shows: read the state, show macOS's own prompt, or open the System Settings pane. Answers are read with `permState`. */
  permissions?: {
    state: () => Promise<Record<string, unknown>>;
    request: (kind: PermKind) => Promise<unknown>;
    openSettings: (kind: PermKind) => void | Promise<void>;
  };
  /** Draw the annotation ring and the ghost cursor on a sample element, so the worker sees how Knack points. It never clicks. */
  tryRing?: () => Promise<unknown> | unknown;
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

/**
 * Any reasonable answer of the shell as one of three states. "granted", "authorized", "allowed" and true are allowed; "denied", "restricted", "off" and false are
 * turned off; everything else, including a missing answer, is "not asked yet" (the safe reading: offer the prompt, claim nothing).
 */
export function permState(raw: unknown): PermState {
  if (raw === true) return "granted";
  if (raw === false) return "off";
  const v = typeof raw === "string" ? raw.toLowerCase().replace(/[\s_]/g, "-") : "";
  if (v === "granted" || v === "authorized" || v === "authorised" || v === "allowed") return "granted";
  if (v === "denied" || v === "restricted" || v === "off" || v === "turned-off") return "off";
  return "not-asked";
}

/** The three permission states from whatever `permissions.state()` answered, each read with `permState`. */
export function permStates(raw: Record<string, unknown> | null | undefined): Record<PermKind, PermState> {
  const o = raw ?? {};
  return { microphone: permState(o.microphone ?? o.mic), speech: permState(o.speech ?? o.speechRecognition), screen: permState(o.screen ?? o.screenRecording ?? o["screen-recording"]) };
}

export const permissionsAvailable = (b: KnackShellBridge = getBridge()): boolean => !!b.permissions && typeof b.permissions.state === "function";
