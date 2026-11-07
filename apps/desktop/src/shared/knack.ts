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

// ---- the corner pill
export const PILL_IPC = {
  get: 'knack:pill:get', // invoke: current PillViewDto
  state: 'knack:pill:state', // main -> pill
  action: 'knack:pill:action', // pill -> main: Stop, or open Knack
  interactive: 'knack:pill:interactive', // pill -> main: the pointer is over a part that takes clicks (true) or left it (false)
} as const

export type PillKindDto = 'idle' | 'working' | 'needs-you' | 'done' | 'error' | 'killed'

export interface PillViewDto {
  kind: PillKindDto
  /** One of a closed list of short sentences (main/knack/pill-state.ts PILL_TEXTS), or '' when idle. */
  text: string
  /** Show the Stop button. */
  stop: boolean
  /** The label opens Knack. */
  open: boolean
}

export type PillActionDto = { type: 'stop' } | { type: 'open' }

export interface KnackPillApi {
  get(): Promise<PillViewDto>
  onState(cb: (v: PillViewDto) => void): () => void
  action(a: PillActionDto): void
  setInteractive(on: boolean): void
}

export const EMPTY_PILL_VIEW: PillViewDto = { kind: 'idle', text: '', stop: false, open: false }
