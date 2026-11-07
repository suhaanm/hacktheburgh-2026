// The HUD: one small always-on-top window with the kill switch pill (always reachable) and, at natural breaks, a calm toast for
// a newly proposed routine. Its own tiny IPC surface (src/preload/hud.ts): it can only ask for these actions, nothing else.
export const HUD_IPC = {
  get: 'hud:get', // invoke: current HudState
  state: 'hud:state', // main -> hud
  action: 'hud:action', // hud -> main
} as const

export interface HudProposal {
  id: string
  title: string
  // One plain sentence: what the system noticed.
  what: string
  howOften: string
  hoursSaved: [number, number] | null
  // The period the hours cover, in weeks (null: not stated, so the card says no period).
  horizonWeeks: number | null
  touches: string[]
  never: string[]
}

// A notice from the attention layer (REQ-8): the engine's fixed words, one source line and the buttons it offers. It sits above the Stop all
// pill in the same window, so it can never cover the pill. `actions[].id` are the attention layer's action ids (main validates them).
export interface HudNotice {
  id: string
  title: string
  body: string
  // The one source line ("Approval queue", "Your overnight run").
  source: string
  actions: { id: string; label: string }[]
  // A safety item: announced as an alert instead of a status.
  urgent: boolean
}

export interface HudState {
  kill: { killed: boolean; engine: boolean | null; agent: boolean | null }
  // Pending approvals waiting in the morning queue (null: the engine is not reachable, so unknown).
  queuePending: number | null
  proposal: HudProposal | null
  // The attention layer's notice (null: none, or the layer is off). One at a time; the Stopped card wins while everything is stopped.
  notice: HudNotice | null
  // An agent (or a session) is acting for the person right now. The Stop all pill is on screen only while this is true (or the
  // Stopped card is up); the kill hotkey and the menu-bar item work all the time.
  agentActing: boolean
}

export type HudAction =
  | { type: 'kill' }
  | { type: 'resume' }
  | { type: 'open_queue' }
  | { type: 'proposal'; id: string; choice: 'not_now' | 'never' | 'look' }
  // A button on the notice (the id is the attention layer's action id) and the notice closing without one (Escape, or its time ran out).
  | { type: 'notice'; id: string; action: string }
  | { type: 'notice_closed'; id: string; how: 'dismissed' | 'timeout' }

export interface HudApi {
  get(): Promise<HudState>
  onState(cb: (s: HudState) => void): () => void
  action(a: HudAction): void
}

export const EMPTY_HUD_STATE: HudState = { kill: { killed: false, engine: null, agent: null }, queuePending: null, proposal: null, notice: null, agentActing: false }
