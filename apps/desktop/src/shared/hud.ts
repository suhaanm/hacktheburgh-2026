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

// KNACK: the corner column. One pill (a status: what is happening, n of m when known, Stop) and at most one card above it. The pill's words are fixed templates
// of at most five words; no model text ever reaches it. (docs/KNACK_UX.md section 7, docs/knack-ux/06-corner-states.svg)
export type HudPhase = 'working' | 'done' | 'error' | 'voice'

export interface HudActivity {
  phase: HudPhase
  // At most five words, from a fixed list (main/knack/activity.ts).
  label: string
  // "n of m", only when both are known.
  step: number | null
  of: number | null
  // The check is fading out (240 ms) before the window goes.
  leaving: boolean
}

// The card for a decision that blocks a run, or a permission prompt: fixed words, a source line, and two buttons ("Review" and "Later").
export interface HudApproval {
  id: string
  title: string
  body: string
  source: string
}

// Why non-safety cards wait: a password field or a denylisted app (secure), a screen share or a call (share), or the Ask bar being open (ask).
export interface HudHold {
  secure: boolean
  share: boolean
  ask: boolean
}

export type HudCardKind = 'stopped' | 'safety' | 'approval' | 'time' | 'digest'

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
  // KNACK: the corner column is in charge: the pill is drawn from `activity` (not from `agentActing`), the window sits bottom-right, and cards wait while `hold` says so.
  corner: boolean
  activity: HudActivity | null
  approval: HudApproval | null
  hold: HudHold
}

/** Priority of the cards, highest first: stopped, safety, approval blocking a run, time-sensitive, digest (docs/knack-ux/08-window-states.md). */
export const HUD_CARD_PRIORITY: readonly HudCardKind[] = ['stopped', 'safety', 'approval', 'time', 'digest']

export type HudCard =
  | { kind: 'stopped' }
  | { kind: 'safety'; notice: HudNotice }
  | { kind: 'approval'; approval: HudApproval }
  | { kind: 'time'; notice: HudNotice }
  | { kind: 'digest'; proposal: HudProposal }

/**
 * The one card the corner draws (or null): the highest-priority one present. A card that is not Stopped or safety waits while a password field or a denylisted app
 * is in front, a screen is shared, or the Ask bar is open. An urgent notice is a safety card; any other notice is time-sensitive; a routine proposal is a digest card.
 */
export function pickCard(state: HudState): HudCard | null {
  if (state.kill.killed) return { kind: 'stopped' }
  if (state.notice?.urgent) return { kind: 'safety', notice: state.notice }
  const held = state.hold.secure || state.hold.share || state.hold.ask
  if (held) return null
  if (state.approval) return { kind: 'approval', approval: state.approval }
  if (state.notice) return { kind: 'time', notice: state.notice }
  if (state.proposal) return { kind: 'digest', proposal: state.proposal }
  return null
}

export type HudAction =
  | { type: 'kill' }
  | { type: 'resume' }
  | { type: 'open_queue' }
  | { type: 'proposal'; id: string; choice: 'not_now' | 'never' | 'look' }
  // A button on the notice (the id is the attention layer's action id) and the notice closing without one (Escape, or its time ran out).
  | { type: 'notice'; id: string; action: string }
  | { type: 'notice_closed'; id: string; how: 'dismissed' | 'timeout' }
  // KNACK corner column: Review and Later on an approval card, Open on the error pill, End on the voice pill.
  | { type: 'review'; id: string }
  | { type: 'later'; id: string }
  | { type: 'pill_open' }
  | { type: 'voice_end' }

export interface HudApi {
  get(): Promise<HudState>
  onState(cb: (s: HudState) => void): () => void
  action(a: HudAction): void
}

export const EMPTY_HUD_STATE: HudState = {
  kill: { killed: false, engine: null, agent: null },
  queuePending: null,
  proposal: null,
  notice: null,
  agentActing: false,
  corner: false,
  activity: null,
  approval: null,
  hold: { secure: false, share: false, ask: false },
}
