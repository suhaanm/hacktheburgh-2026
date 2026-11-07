// The small IPC surfaces of the Knack shell: the main window's "starting" and error page, and the corner pill. Each has its own preload with these few
// calls and nothing else (main checks the sender on every message).

// ---- the main window: the page shown while the services start, and when they fail
export const KNACK_IPC = {
  get: 'knack:get', // invoke: current ShellUiState
  state: 'knack:state', // main -> page
  retry: 'knack:retry', // page -> main: the one Try again button
} as const

export type ShellUiState =
  /** `notice`: the one calm line under the text when the app runs on example data ("Running with example data"). */
  | { kind: 'starting'; text: string; notice?: string }
  | { kind: 'ready' }
  | { kind: 'error'; message: string; hint?: string }

export interface KnackShellApi {
  get(): Promise<ShellUiState>
  onState(cb: (s: ShellUiState) => void): () => void
  retry(): void
  platform: string
}
