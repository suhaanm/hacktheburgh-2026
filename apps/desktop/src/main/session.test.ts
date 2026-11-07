import { describe, expect, it, vi } from 'vitest'
import type { Services } from '../shared/contracts'
import { Bus } from './bus'
import { ConfirmBroker } from './confirm'
import type { ServiceContext } from './context'
import { registerSession } from './session'
import { SettingsStore } from './settings'
import { StateStore } from './state'

function setup() {
  const bus = new Bus()
  const settings = new SettingsStore(null)
  const state = new StateStore(settings.get())
  const ctx = { state, bus, settings, userDataDir: null, sendOverlay: vi.fn(), sendDock: vi.fn(), log: vi.fn() } as unknown as ServiceContext
  const services = { runner: { abort: vi.fn(async () => undefined) }, overlay: { clear: vi.fn(), chip: vi.fn() } } as unknown as Services
  const confirm = new ConfirmBroker(state)
  const session = registerSession(ctx, services, confirm)
  return { bus, state, confirm, session, services }
}

describe('session end and pending confirmations', () => {
  it('Stop cancels a pending confirmation even when no session is active', async () => {
    const { state, confirm, session } = setup()
    expect(state.get().phase === 'asleep' || state.get().phase === 'listening_for_name').toBe(true)
    const answer = confirm.ask('Open the website?', ['Yes', 'No'])
    expect(state.get().pendingConfirm).toBeDefined()
    session.stop('stop')
    await expect(answer).resolves.toBeNull()
    expect(state.get().pendingConfirm).toBeUndefined()
  })

  it('Stop during an active session still cancels the confirmation and rests the phase', async () => {
    const { state, confirm, session, services } = setup()
    state.patch({ phase: 'live' })
    const answer = confirm.ask('Click it for you?', ['Yes', 'No'])
    session.stop('stop')
    await expect(answer).resolves.toBeNull()
    expect(state.get().pendingConfirm).toBeUndefined()
    expect(state.get().phase).not.toBe('live')
    expect(services.overlay.clear).toHaveBeenCalled()
  })

  it('an inactive end does not touch the overlay or runner', () => {
    const { session, services } = setup()
    session.stop('stop')
    expect(services.overlay.clear).not.toHaveBeenCalled()
    expect(services.runner.abort).not.toHaveBeenCalled()
  })
})
