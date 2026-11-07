// Glue between the bus (wake/hotkey/button), state, and the dock renderer that actually hosts the Live session.
import { IPC } from '../shared/ipc'
import type { Services } from '../shared/contracts'
import { HELP_LEVEL_LABELS } from '../shared/protocol'
import type { SessionEndReason } from '../shared/protocol'
import type { ConfirmBroker } from './confirm'
import type { ServiceContext } from './context'

const ACTIVE = new Set(['connecting', 'live', 'thinking', 'speaking'])

export interface SessionController {
  stop(reason: SessionEndReason): void
}

export function registerSession(ctx: ServiceContext, s: Services, confirm: ConfirmBroker): SessionController {
  const { bus, state, settings } = ctx

  const restingPhase = () => (settings.get().wakeEnabled ? 'listening_for_name' : 'asleep')

  bus.on('session:request', (req) => {
    if (ACTIVE.has(state.get().phase)) ctx.sendDock(IPC.sessionStop, 'replaced')
    settings.patch({ persona: req.personaId })
    state.patch({ persona: req.personaId, phase: 'connecting', captions: [], lastError: undefined })
    ctx.sendDock(IPC.sessionStart, req)
  })

  bus.on('session:ended', ({ reason }) => {
    confirm.cancel() // always: a pending ask/act_for_me confirmation must not outlive Stop, whatever the phase
    if (!ACTIVE.has(state.get().phase) && state.get().phase !== 'error') return
    void s.runner.abort(`session ended: ${reason}`)
    s.overlay.clear()
    state.patch({ phase: reason === 'error' ? 'error' : restingPhase(), skill: undefined })
  })

  bus.on('level:changed', ({ to }) => {
    state.patch({ level: to })
    s.overlay.chip(to, HELP_LEVEL_LABELS[to])
  })

  settings.onChange((next) => {
    const locked = next.helpLevelMode === 'locked'
    state.patch({ settings: next, persona: next.persona ?? state.get().persona, levelLocked: locked, ...(locked ? { level: next.lockedLevel } : {}) })
    if (locked) s.overlay.chip(next.lockedLevel, HELP_LEVEL_LABELS[next.lockedLevel])
  })

  return {
    stop(reason) {
      ctx.sendDock(IPC.sessionStop, reason)
      bus.emit('session:ended', { reason })
    },
  }
}
