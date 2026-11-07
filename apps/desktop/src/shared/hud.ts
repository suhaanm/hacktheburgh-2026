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

export interface HudState {
  kill: { killed: boolean; engine: boolean | null; agent: boolean | null }
  // Pending approvals waiting in the morning queue (null: the engine is not reachable, so unknown).
  queuePending: number | null
  proposal: HudProposal | null
}

export type HudAction =
  | { type: 'kill' }
  | { type: 'resume' }
  | { type: 'open_queue' }
  | { type: 'proposal'; id: string; choice: 'not_now' | 'never' | 'look' }

export interface HudApi {
  get(): Promise<HudState>
  onState(cb: (s: HudState) => void): () => void
  action(a: HudAction): void
}

export const EMPTY_HUD_STATE: HudState = { kill: { killed: false, engine: null, agent: null }, queuePending: null, proposal: null }
