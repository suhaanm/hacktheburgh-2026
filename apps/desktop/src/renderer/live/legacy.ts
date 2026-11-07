// REMOVED: the renderer-side Live session of the earlier Alongside app (it opened the websocket, the 1 fps frame loop and the tool dispatch
// from a renderer). Voice now lives in the MAIN process (src/main/live), where one choke point applies the gates, the caps and the ledger;
// the renderer only owns the microphone and the speaker (bridge.ts).
//
// This stub exists ONLY so the old dock controller (src/renderer/dock/controller.ts, owned by the shell track) still type-checks until its
// Live lines are removed. It cannot be constructed: there is no websocket, no frame loop and no model call left in any renderer. Delete this
// file together with those lines.
import type { LiveAuth, LivePhase } from './types'

export const LEGACY_LIVE_REMOVED = 'The renderer-side Live session was removed. Voice runs in the main process, from the talk key (src/main/live).'

type Anything = any // eslint-disable-line @typescript-eslint/no-explicit-any

// Only the shape the old controller passes, so its callbacks keep their types.
export interface LegacyLiveSessionOptions {
  host: { getAuth(): Promise<LiveAuth>; systemInstruction(): Promise<string> }
  audioIn: unknown
  audioOut: unknown
  model: string
  toolHandler?: (call: { id: string; name: string; args: Record<string, unknown> }, signal: AbortSignal) => Promise<unknown>
  frames?: unknown
  idleTimeoutMs?: number
  duplex?: 'full' | 'half'
  log?: (...a: unknown[]) => void
}

export class LiveSession {
  phase: LivePhase = 'idle'
  constructor(_opts: LegacyLiveSessionOptions) {
    throw new Error(LEGACY_LIVE_REMOVED)
  }
  on(_event: string, _handler: (payload: Anything) => void): () => void {
    return () => undefined
  }
  start(_opts: Anything): Promise<void> {
    return Promise.reject(new Error(LEGACY_LIVE_REMOVED))
  }
  stop(_reason?: string): Promise<void> {
    return Promise.resolve()
  }
  setTextMode(_on: boolean): Promise<void> {
    return Promise.resolve()
  }
  sendUserText(_text: string): boolean {
    return false
  }
  setMicMuted(_muted: boolean): void {}
  setIdleTimeout(_ms: number): void {}
  injectText(_text: string, _o?: Anything): boolean {
    return false
  }
  getOutputLevel(): number {
    return 0
  }
  getInputLevel(): number {
    return 0
  }
}

export type { LiveAuth }
