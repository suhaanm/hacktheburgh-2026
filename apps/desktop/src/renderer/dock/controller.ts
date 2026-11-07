// Dock-side wiring. VOICE NO LONGER STARTS HERE. The Live websocket, the token, the gates, the caps and the ledger rows live in the main
// process (src/main/live); the dock only owns the microphone and the speaker, driven by main (src/renderer/live/bridge.ts, started in
// main.tsx). The old renderer-side LiveSession, the wake-word spotter (src/renderer/wake, which streamed the microphone to a cloud model
// from this window) and the `live:token` / `wake:token` channels are gone: nothing in a renderer can open a Gemini socket.
//
// What is left: mirror the shared state, and answer a session request from main by ending it at once (a request to open a session in the
// dock opens nothing; hold the talk key instead). Typed chat has no backend in this build, so a typed line is answered with one plain
// sentence rather than silence.
import type { CompanionState } from '../../shared/protocol'
import { chatBus } from './chat/bus'

export interface LiveHandle {
  // 0..1 smoothed levels for the orb / listening light; always 0 here (the main-process voice path owns the audio).
  outputLevel(): number
  inputLevel(): number
  active(): boolean
}

// DESIGN polls this (rAF) to animate the orb; stable reference for the lifetime of the dock.
export const liveHandle: LiveHandle = { outputLevel: () => 0, inputLevel: () => 0, active: () => false }

export interface ControllerOptions {
  // Kept for callers that passed it (the wake spotter is gone, so it has no effect).
  wake?: boolean
}

export const TYPED_CHAT_OFF = 'Typing to me is not switched on in this build. Hold the talk key to speak, or use the menu bar.'

export function startController(_opts: ControllerOptions = {}): () => void {
  const api = window.alongside
  let current: CompanionState | null = null
  const cleanups: Array<() => void> = []
  const applyState = (next: CompanionState): void => {
    current = next
  }
  void api.getState().then(applyState).catch((err: unknown) => console.log('[dock]', 'getState failed', err))
  cleanups.push(api.onState(applyState))

  // A session request (button, hotkey) used to open a renderer-side Live session. It opens nothing now: say so to main and move on.
  cleanups.push(
    api.onSessionStart(() => {
      api.sessionEnded('stop')
    }),
  )
  cleanups.push(api.onSessionStop(() => undefined))

  // Typed turns: one honest line, never silence and never a model call from this window.
  cleanups.push(
    chatBus.onSend(() => {
      chatBus.push({ id: `a-off-${Date.now()}`, role: 'assistant', text: TYPED_CHAT_OFF, final: true, at: Date.now(), via: 'voice' })
    }),
  )

  void current
  return () => {
    for (const c of cleanups) c()
  }
}
