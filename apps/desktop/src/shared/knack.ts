// The small IPC surfaces of the Knack shell: the main window's "starting" and error page, and the corner pill. Each has its own preload with these few
// calls and nothing else (main checks the sender on every message).

// ---- the main window: the page shown while the services start, and when they fail
export const KNACK_IPC = {
  get: 'knack:get', // invoke: current ShellUiState
  state: 'knack:state', // main -> page
  retry: 'knack:retry', // page -> main: the one Try again button
  modelsGet: 'knack:models:get', // invoke: KnackModelsState
  modelsSet: 'knack:models:set', // invoke(boolean): the Use live models switch
  settingsGet: 'knack:settings:get', // invoke: the small view of the desktop settings the dashboard Settings shows
  settingsPatch: 'knack:settings:patch', // invoke(patch): the switches the dashboard Settings may change (an allow-list, see settings-bridge.ts)
  permState: 'knack:perm:state', // invoke: KnackPermissionsState
  permRequest: 'knack:perm:request', // invoke(kind): ask macOS where it lets an app ask; answers KnackPermRequestResult
  permOpen: 'knack:perm:open', // invoke(kind): open the System Settings pane; answers boolean
  tryRing: 'knack:try-ring', // invoke(spot?): show the on-screen ring for four seconds; answers KnackTryRingResult
} as const

// ---- permissions for the first run: four kinds, closed states, nothing else (no path, no app name, no sentence from the system)
export type KnackPermKind = 'microphone' | 'speech' | 'screen' | 'accessibility'
/** not_asked: macOS has not been asked yet (or does not say); granted; denied: the worker said no (open System Settings to change it); restricted: this Mac's policy forbids it. */
export type KnackPermState = 'granted' | 'not_asked' | 'denied' | 'restricted'
export interface KnackPermissionsState {
  microphone: KnackPermState
  speech: KnackPermState
  screen: KnackPermState
  accessibility: KnackPermState
  /** Screen Recording is allowed but capture still returns nothing: Knack must be reopened before it works. */
  needsRestart: boolean
}
export type KnackPermRequestResult = { ok: true; state: KnackPermissionsState } | { ok: false; reason: 'bad_request' | 'not_ready' }
export type KnackTryRingResult = { ok: true } | { ok: false; reason: 'bad_request' | 'not_ready' | 'window_hidden' | 'other_display' }
/** A spot in the page's own window, in CSS pixels: where the ring goes. Omitted: a fixed spot in the upper middle of the window. */
export interface KnackRingSpot {
  x: number
  y: number
  width: number
  height: number
}

export type ShellUiState =
  /** `notice`: the one calm line under the text when the app runs on example data ("Running with example data"). */
  | { kind: 'starting'; text: string; notice?: string }
  | { kind: 'ready' }
  | { kind: 'error'; message: string; hint?: string }

// "Use live models" in the dashboard's Settings: the dashboard cannot write this app's settings, so it asks through these two calls. Only this window's own page can.
export interface KnackModelsState {
  /** The worker's switch. */
  useLiveModels: boolean
  /** A Gemini key is in the environment (the value is never sent). */
  keyPresent: boolean
  /** What is running: true live, false example data, null not known yet. */
  live: boolean | null
  /** A run or a voice session is going: the switch is disabled ("A job is running. Stop it first."). */
  running: boolean
}
export type KnackModelsSetResult = { ok: true } | { ok: false; reason: 'no_key' | 'running' | 'bad_request' }

/** Hey Knack's status for the Settings row: the worker's switch, whether it is listening, and the one plain line to print under it. */
export interface KnackWakeStatus {
  switchOn: boolean
  listening: boolean
  line: string
  /** The macOS pane that fixes a blocked listener (show a button beside the line), or null. */
  fix: 'microphone' | 'speech' | 'dictation' | null
  /** The worker has had their first conversation: the Try it step can finish. */
  welcomed: boolean
}
/** What the shell may report for the voice conversation's context packet: ids and counts only (validated again in main). */
export interface KnackWakeContext {
  insight?: { id: string; template: string } | null
  routine?: { id: string; step: number; of: number } | null
  /** Set-up is showing: the packet says first_run=yes and the listener waits for arm(). Send false when set-up is over. */
  firstRun?: boolean
}

/** What the dashboard's Settings screen reads of the desktop settings. `minimiseWhileWorking` is the dashboard's name for the same switch as `moveAsideWhileWorking`. */
export interface DashboardSettingsView {
  useLiveModels: boolean
  minimiseWhileWorking: boolean
  moveAsideWhileWorking: boolean
  keepAwakeWhileWorking: boolean
  showInDock: boolean
  launchAtLogin: boolean
  cueEnabled: boolean
  helpLevelMode: 'auto' | 'locked'
  lockedLevel: number
}

/** `window.knackSettings` in the Knack window: the same two calls the older settings bridge has, over the small view above. */
export interface KnackSettingsApi {
  getSettings(): Promise<DashboardSettingsView>
  patchSettings(patch: Partial<DashboardSettingsView>): Promise<DashboardSettingsView>
}

export interface KnackShellApi {
  get(): Promise<ShellUiState>
  onState(cb: (s: ShellUiState) => void): () => void
  retry(): void
  platform: string
  /** Hey Knack's status and switch (absent in a build without the listener). */
  wake?: {
    state(): Promise<KnackWakeStatus>
    set(listen: boolean): Promise<KnackWakeStatus>
    context(c: KnackWakeContext): Promise<boolean>
    /** The set-up step that turns Hey Knack on: the listener starts, and macOS asks for the microphone, then Speech Recognition. */
    arm(): Promise<KnackWakeStatus>
  }
  models: {
    get(): Promise<KnackModelsState>
    /** Changing it restarts the app (the model port is built once, at start): about 20 seconds. */
    setUseLiveModels(on: boolean): Promise<KnackModelsSetResult>
  }
  /**
   * What the first run needs of macOS. `state()` is read-only and never makes macOS ask. `request(kind)` makes macOS show its own prompt where it has one (microphone, speech
   * recognition through the Hey Knack listener, screen recording through one capture, accessibility through its system dialog); the worker answers there, never here. A grant
   * made in System Settings shows up in the next `state()` (poll it about every second after `openSettings`). Nothing is requested unless the page asks for that one kind.
   */
  permissions: {
    state(): Promise<KnackPermissionsState>
    request(kind: KnackPermKind): Promise<KnackPermRequestResult>
    /** Opens the System Settings pane for the kind. */
    openSettings(kind: KnackPermKind): Promise<boolean>
  }
  /** Draws the on-screen ring and the ghost cursor around `spot` (or a fixed spot) in the Knack window for four seconds. It never clicks and needs no permission. */
  tryRing(spot?: KnackRingSpot): Promise<KnackTryRingResult>
}
