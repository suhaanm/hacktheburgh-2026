// The global kill switch (OFF-6, SEC-8). One press: stop everything this app is doing, say so, and tell the engine and the agent.
//   Local first and synchronous (nothing here waits on the network or a model): kill flag on, act_for_me loop stopped, spawned
//   agents cancelled, any approval declined, the walkthrough stopped, the session stopped (which aborts the lesson runner and
//   clears the overlay), then one plain line on the overlay. THEN, best effort and in parallel, engine POST /kill and agent
//   POST /kill. The flag stays on until the worker presses Resume: a stopped assistant does not quietly start again.
// Reachable three ways: a global shortcut, the menu-bar item, and the always-visible pill in the HUD window.
import type { OverlayController } from '../shared/contracts'
import type { AgentChip, SessionEndReason } from '../shared/protocol'
import { isKilled, setKilled } from './kill-flag'

export type KillSource = 'hotkey' | 'tray' | 'hud' | 'cli'

export interface KillReport {
  source: KillSource
  at: number
  localMs: number
  engine: boolean
  agent: boolean
}

export interface KillState {
  killed: boolean
  at: number | null
  source: KillSource | null
  // After the network leg finished: did the engine and the agent acknowledge?
  engine: boolean | null
  agent: boolean | null
}

export interface KillDeps {
  stopSession(reason: SessionEndReason): void
  stopAgency(): void
  stopShowtime(): void
  cancelConfirm(): void
  agents(): readonly Pick<AgentChip, 'id' | 'status'>[]
  cancelAgent(id: string): void
  overlay: Pick<OverlayController, 'clear' | 'caption'>
  engine: { kill(): Promise<{ engine: boolean; agent: boolean }>; clearKill(): Promise<{ engine: boolean; agent: boolean }> }
  log?: (scope: string, ...args: unknown[]) => void
  now?: () => number
}

export interface KillSwitch {
  trigger(source: KillSource): Promise<KillReport>
  clear(): Promise<void>
  isKilled(): boolean
  state(): KillState
  subscribe(cb: (s: KillState) => void): () => void
}

export const STOPPED_LINE = 'Stopped. Everything is paused until you press Resume.'

export function createKillSwitch(deps: KillDeps): KillSwitch {
  const now = deps.now ?? Date.now
  const log = deps.log ?? (() => undefined)
  const listeners = new Set<(s: KillState) => void>()
  let state: KillState = { killed: isKilled(), at: null, source: null, engine: null, agent: null }

  const set = (next: Partial<KillState>): void => {
    state = { ...state, ...next }
    for (const l of listeners) {
      try {
        l(state)
      } catch {
        /* a broken listener must not stop the stop */
      }
    }
  }
  // Every local step runs even if an earlier one throws.
  const safely = (what: string, fn: () => void): void => {
    try {
      fn()
    } catch (err) {
      log('kill', `${what} failed:`, err instanceof Error ? err.message : String(err))
    }
  }

  return {
    async trigger(source) {
      const t0 = now()
      setKilled(true) // first: the actuator and every new start refuse from this instant
      safely('act_for_me', () => deps.stopAgency())
      safely('approval', () => deps.cancelConfirm())
      safely('agents', () => {
        for (const chip of deps.agents()) if (chip.status === 'running') deps.cancelAgent(chip.id)
      })
      safely('walkthrough', () => deps.stopShowtime())
      safely('session', () => deps.stopSession('stop'))
      safely('overlay', () => {
        deps.overlay.clear()
        deps.overlay.caption('system', STOPPED_LINE, true)
      })
      const localMs = now() - t0
      set({ killed: true, at: t0, source, engine: null, agent: null })
      log('kill', `local stop done in ${localMs}ms (${source})`)
      // Best effort and in parallel: the engine and the agent service. Never throws, never delays the local stop above.
      let remote = { engine: false, agent: false }
      try {
        remote = await deps.engine.kill()
      } catch {
        /* unreachable is expected when they are not running */
      }
      set({ engine: remote.engine, agent: remote.agent })
      log('kill', `engine ${remote.engine ? 'acknowledged' : 'not reached'}, agent ${remote.agent ? 'acknowledged' : 'not reached'}`)
      return { source, at: t0, localMs, ...remote }
    },
    async clear() {
      setKilled(false)
      set({ killed: false, at: null, source: null, engine: null, agent: null })
      safely('overlay', () => deps.overlay.caption('system', 'Resumed.', true))
      try {
        await deps.engine.clearKill()
      } catch {
        /* the engine may be down */
      }
    },
    isKilled: () => state.killed,
    state: () => state,
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
  }
}
