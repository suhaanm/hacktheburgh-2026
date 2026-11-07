// The HUD without Electron: state, action validation and what each action does. hud.ts puts it in a window.
import { z } from 'zod'
import type { HudAction, HudNotice, HudProposal, HudState } from '../shared/hud'
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
])

/** Where a click on the notice goes (attention/adapter.ts: `action` and `closed`). The shell binds it; absent, a notice click does nothing. */
export interface HudNoticeSink {
  action(id: string, action: ActionId): void
  closed(id: string, how: 'dismissed' | 'timeout'): void
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
  handle(raw: unknown): boolean
  dispose(): void
}

export function createHudModel(deps: HudModelDeps): HudModel {
  let state: HudState = { ...EMPTY_HUD_STATE, kill: killOf(deps.kill.state()) }
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

/** Bottom-left of the work area, above the Dock, with a margin; the card grows upwards. */
export function hudBounds(workArea: { x: number; y: number; width: number; height: number }, size: { width: number; height: number }, margin = 14): { x: number; y: number; width: number; height: number } {
  return { x: workArea.x + margin, y: workArea.y + workArea.height - size.height - margin, width: size.width, height: size.height }
}
