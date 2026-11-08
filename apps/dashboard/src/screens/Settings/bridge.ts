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
export interface LiveModelsState {
  /** The worker's switch. */
  useLiveModels: boolean;
  /** A Gemini key is in the environment (the value is never sent). */
  keyPresent: boolean;
  /** What is running: true live, false example data, null not known yet. */
  live: boolean | null;
  /** A run or a voice session is going: the switch is disabled. */
  running: boolean;
  /** Why the app chose what it runs (the shell's closed word); "boot_check_failed" is models off only because the service could not be reached. Absent in an older shell. */
  reason?: string | null;
}
export type LiveModelsResult = { ok: true } | { ok: false; reason: "no_key" | "running" | "bad_request" };
export interface LiveModelsBridge {
  get(): Promise<LiveModelsState>;
  /** Changing it restarts the app (about 20 seconds). */
  setUseLiveModels(on: boolean): Promise<LiveModelsResult>;
}

/** Hey Knack's status for its Settings row: the worker's switch, whether it is listening, and one plain line. */
export interface WakeStatus { switchOn: boolean; listening: boolean; line: string }
/** What the dashboard may tell the voice conversation: ids and counts only (the shell checks them again). */
export interface WakeContext { insight?: { id: string; template: string } | null; routine?: { id: string; step: number; of: number } | null }
export interface WakeBridge {
  state(): Promise<WakeStatus>;
  set(listen: boolean): Promise<WakeStatus>;
  context(c: WakeContext): Promise<boolean>;
}

/** Check voice (the shell's `voice.check`): one report of every stage a conversation needs, each Ready or the one thing to do. The words are written by the desktop app; the page prints them. */
export type VoiceAction = { do: "ask"; what: "microphone" | "speech" | "screen" | "accessibility" } | { do: "open"; what: "microphone" | "speech" | "screen" | "accessibility" | "sound" } | { do: "settings" } | { do: "ask_again" };
export interface VoiceStage { id: string; title: string; state: "ready" | "fix"; line: string; action: VoiceAction | null; needs: "both" | "hey"; optional?: boolean }
export interface VoiceCheck { ok: boolean; heyKnack: boolean; stages: VoiceStage[]; at: number }
export interface VoiceBridge { check(): Promise<VoiceCheck>; askAgain(): Promise<boolean> }

type Win = { alongside?: Partial<DesktopBridge>; knackSettings?: Partial<DesktopBridge>; knackShell?: { models?: Partial<LiveModelsBridge>; wake?: Partial<WakeBridge>; voice?: Partial<VoiceBridge> } };

/** The Check voice calls, or null (a browser tab, or a build without them). */
export function voiceBridge(w: Win | undefined = typeof window === "undefined" ? undefined : (window as unknown as Win)): VoiceBridge | null {
  const v = w?.knackShell?.voice;
  return v && typeof v.check === "function" ? ({ check: v.check, askAgain: typeof v.askAgain === "function" ? v.askAgain : async () => false } as VoiceBridge) : null;
}

/** Hey Knack's calls, or null (a browser tab, or a build without the listener). */
export function wakeBridge(w: Win | undefined = typeof window === "undefined" ? undefined : (window as unknown as Win)): WakeBridge | null {
  const k = w?.knackShell?.wake;
  return k && typeof k.state === "function" && typeof k.set === "function" ? (k as WakeBridge) : null;
}

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
