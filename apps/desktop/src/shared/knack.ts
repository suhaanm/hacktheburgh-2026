// The small IPC surfaces of the Knack shell: the main window's "starting" and error page, and the corner pill. Each has its own preload with these few
// calls and nothing else (main checks the sender on every message).

// ---- the main window: the page shown while the services start, and when they fail
export const KNACK_IPC = {
  get: 'knack:get', // invoke: current ShellUiState
  state: 'knack:state', // main -> page
  retry: 'knack:retry', // page -> main: the one Try again button
  modelsGet: 'knack:models:get', // invoke: KnackModelsState
  modelsSet: 'knack:models:set', // invoke(boolean): the Use live models switch
} as const

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

export interface KnackShellApi {
  get(): Promise<ShellUiState>
  onState(cb: (s: ShellUiState) => void): () => void
  retry(): void
  platform: string
  models: {
    get(): Promise<KnackModelsState>
    /** Changing it restarts the app (the model port is built once, at start): about 20 seconds. */
    setUseLiveModels(on: boolean): Promise<KnackModelsSetResult>
  }
}
