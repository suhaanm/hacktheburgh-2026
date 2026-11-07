// The HUD without Electron: state, action validation and what each action does. hud.ts puts it in a window.
import { z } from 'zod'
import type { HudAction, HudActivity, HudApproval, HudHold, HudNotice, HudProposal, HudState } from '../shared/hud'
import { EMPTY_HUD_STATE } from '../shared/hud'
import { ACTION_IDS, type ActionId } from './attention/types'
import { dashboardUrl, type Endpoints } from './engine/endpoints'
import type { KillSwitch } from './kill-switch'

export const HudActionSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('kill') }),
  z.object({ type: z.literal('resume') }),
  z.object({ type: z.literal('open_queue') }),
  z.object({ type: z.literal('proposal'), id: z.string().min(1).max(80), choice: z.enum(['not_now', 'never', 'look']) }),
  // The attention layer's notice: one of its own action ids, or the notice closing without a button.
  z.object({ type: z.literal('notice'), id: z.string().min(1).max(80), action: z.enum(ACTION_IDS) }),
  z.object({ type: z.literal('notice_closed'), id: z.string().min(1).max(80), how: z.enum(['dismissed', 'timeout']) }),
  // KNACK corner column.
  z.object({ type: z.literal('review'), id: z.string().min(1).max(80) }),
  z.object({ type: z.literal('later'), id: z.string().min(1).max(80) }),
  z.object({ type: z.literal('pill_open') }),
  z.object({ type: z.literal('voice_end') }),
])

/** Where a click on the notice goes (attention/adapter.ts: `action` and `closed`). The shell binds it; absent, a notice click does nothing. */
export interface HudNoticeSink {
  action(id: string, action: ActionId): void
  closed(id: string, how: 'dismissed' | 'timeout'): void
}

/** Where the corner column's own buttons go (the Knack shell binds it; absent, a click on them does nothing). */
export interface HudCornerSink {
  /** Review on an approval card: open Knack on Needs you at that item. */
  review(id: string): void
  /** Later on an approval card (or its timeout): the card goes, the count stays. */
  later(id: string): void
  /** Open on the error pill: open Knack and acknowledge the error. */
  open(): void
  /** End on the voice pill. */
  voiceEnd(): void
}

export interface HudModelDeps {
  kill: Pick<KillSwitch, 'trigger' | 'clear' | 'state' | 'subscribe'>
  endpoints: Pick<Endpoints, 'dashboard'>
  // Opens a URL in the person's browser (shell.openExternal in the app). Only ever called with dashboard URLs.
  openExternal(url: string): void
  // A choice on the proposal toast. 'look' has already opened the dashboard; 'not_now' and 'never' are for the engine.
  onProposalChoice(id: string, choice: 'not_now' | 'never' | 'look'): void
  push(state: HudState): void
  log?: (scope: string, ...args: unknown[]) => void
  // KNACK: the corner column is in charge (the pill comes from `setActivity`, the window sits bottom-right, cards wait while `setHold` says so).
  corner?: boolean
  // REQ-8: where the notice's buttons go. Optional: absent, the model is exactly what it was; `setAttention` binds it later.
  attention?: HudNoticeSink | null
}

export interface HudModel {
  state(): HudState
  setProposal(p: HudProposal | null): void
  // The attention layer's notice (null removes it). A notice with the id already showing is not pushed again.
  setNotice(n: HudNotice | null): void
  // Late binding for the notice's buttons (the attention layer starts after the HUD exists). null unbinds.
  setAttention(sink: HudNoticeSink | null): void
  setQueuePending(n: number | null): void
  // An agent or a session is acting for the person (shows the Stop all pill while true).
  setAgentActing(acting: boolean): void
  // KNACK corner column.
  setActivity(a: HudActivity | null): void
  setApproval(a: HudApproval | null): void
  setHold(h: Partial<HudHold>): void
  setCorner(sink: HudCornerSink | null): void
  handle(raw: unknown): boolean
  dispose(): void
}

export function createHudModel(deps: HudModelDeps): HudModel {
  let state: HudState = { ...EMPTY_HUD_STATE, corner: deps.corner === true, kill: killOf(deps.kill.state()) }
  let corner: HudCornerSink | null = null
  const set = (patch: Partial<HudState>): void => {
    state = { ...state, ...patch }
    deps.push(state)
  }
  const off = deps.kill.subscribe((k) => set({ kill: killOf(k) }))
  let sink: HudNoticeSink | null = deps.attention ?? null

  return {
    state: () => state,
    setProposal(p) {
      // A proposal never shows while everything is stopped.
      if (p && state.kill.killed) return
      if (state.proposal?.id === p?.id && p !== null) return
      set({ proposal: p })
    },
    setNotice(n) {
      if (n === null) {
        if (state.notice !== null) set({ notice: null })
        return
      }
      if (state.notice?.id === n.id) return
      set({ notice: n })
    },
    setAttention(next) {
      sink = next
    },
    setQueuePending(n) {
      if (state.queuePending !== n) set({ queuePending: n })
    },
    setAgentActing(acting) {
      if (state.agentActing !== acting) set({ agentActing: acting })
    },
    setActivity(a) {
      const cur = state.activity
      if (a === null ? cur === null : cur !== null && cur.phase === a.phase && cur.label === a.label && cur.step === a.step && cur.of === a.of && cur.leaving === a.leaving) return
      set({ activity: a })
    },
    setApproval(a) {
      if (a !== null && state.kill.killed) return // while everything is stopped the Stopped card is the only card
      if (state.approval?.id === a?.id && a !== null) return
      if (a === null && state.approval === null) return
      set({ approval: a })
    },
    setHold(h) {
      const next = { ...state.hold, ...h }
      if (next.secure !== state.hold.secure || next.share !== state.hold.share || next.ask !== state.hold.ask) set({ hold: next })
    },
    setCorner(next) {
      corner = next
    },
    handle(raw) {
      const parsed = HudActionSchema.safeParse(raw)
      if (!parsed.success) {
        deps.log?.('hud', 'ignored a malformed action')
        return false
      }
      const a: HudAction = parsed.data
      switch (a.type) {
        case 'kill':
          void deps.kill.trigger('hud')
          set({ proposal: null })
          return true
        case 'resume':
          void deps.kill.clear()
          return true
        case 'open_queue':
          deps.openExternal(dashboardUrl(deps.endpoints, 'queue'))
          return true
        case 'proposal': {
          if (state.proposal?.id !== a.id) return false // a stale click on a toast that already left
          if (a.choice === 'look') deps.openExternal(dashboardUrl(deps.endpoints, 'routines'))
          set({ proposal: null })
          deps.onProposalChoice(a.id, a.choice)
          return true
        }
        case 'notice': {
          if (!sink || state.notice?.id !== a.id) return false // no layer to tell, or a stale click on a notice that already left
          set({ notice: null })
          sink.action(a.id, a.action as ActionId)
          return true
        }
        case 'review': {
          if (state.approval?.id !== a.id) return false // a stale click on a card that already left
          corner?.review(a.id)
          set({ approval: null })
          return true
        }
        case 'later': {
          if (state.approval?.id !== a.id) return false
          corner?.later(a.id)
          set({ approval: null })
          return true
        }
        case 'pill_open':
          corner?.open()
          return true
        case 'voice_end':
          corner?.voiceEnd()
          return true
        case 'notice_closed': {
          if (!sink || state.notice?.id !== a.id) return false
          set({ notice: null })
          sink.closed(a.id, a.how)
          return true
        }
      }
    },
    dispose: off,
  }
}

function killOf(k: { killed: boolean; engine: boolean | null; agent: boolean | null }): HudState['kill'] {
  return { killed: k.killed, engine: k.engine, agent: k.agent }
}

/** KNACK: bottom-right of the work area (it excludes the menu bar and the Dock), 16 px in from the edges; the card sits above the pill and grows upwards. */
export function cornerBounds(workArea: { x: number; y: number; width: number; height: number }, size: { width: number; height: number }, margin = 16): { x: number; y: number; width: number; height: number } {
  return { x: workArea.x + workArea.width - size.width - margin, y: workArea.y + workArea.height - size.height - margin, width: size.width, height: size.height }
}

/** Bottom-left of the work area, above the Dock, with a margin; the card grows upwards. (The window of the old HUD; the Knack corner column uses cornerBounds.) */
export function hudBounds(workArea: { x: number; y: number; width: number; height: number }, size: { width: number; height: number }, margin = 14): { x: number; y: number; width: number; height: number } {
  return { x: workArea.x + margin, y: workArea.y + workArea.height - size.height - margin, width: size.width, height: size.height }
}
