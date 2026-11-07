import { describe, expect, it } from 'vitest'
import { DEFAULT_SETTINGS } from '../shared/settings'
import { Bus } from './bus'
import { ConfirmBroker, dismissConfirmOnStepVerified } from './confirm'
import { StateStore } from './state'

const step = { lessonId: 'l', skillId: 'video_call' as const, stepIndex: 0, stepCount: 3 }

function setup() {
  const bus = new Bus()
  const state = new StateStore(DEFAULT_SETTINGS)
  const confirm = new ConfirmBroker(state)
  const off = dismissConfirmOnStepVerified(bus, confirm)
  return { bus, state, confirm, off }
}

describe('dismissConfirmOnStepVerified', () => {
  it('a verified step clears the pending approval as a decline (null), never an approval', async () => {
    const { bus, state, confirm } = setup()
    const answer = confirm.ask('Open it for you?', ['Do it', 'No'])
    expect(state.get().pendingConfirm).toBeDefined()
    bus.emit('lesson:step', { ...step, phase: 'verified' })
    expect(await answer).toBeNull()
    expect(state.get().pendingConfirm).toBeUndefined()
  })

  it('other phases leave it pending, and a later real click still works', async () => {
    const { bus, state, confirm } = setup()
    const answer = confirm.ask('Open it for you?', ['Do it', 'No'])
    for (const phase of ['started', 'repair'] as const) bus.emit('lesson:step', { ...step, phase })
    const pending = state.get().pendingConfirm
    expect(pending).toBeDefined()
    expect(confirm.answer(pending!.id, 'Do it')).toBe(true)
    expect(await answer).toBe('Do it')
  })

  it('does nothing when nothing is pending and stops after unsubscribe', async () => {
    const { bus, state, confirm, off } = setup()
    expect(() => bus.emit('lesson:step', { ...step, phase: 'verified' })).not.toThrow()
    off()
    const answer = confirm.ask('Q?', ['Yes', 'No'])
    bus.emit('lesson:step', { ...step, phase: 'verified' })
    expect(state.get().pendingConfirm).toBeDefined()
    confirm.cancel()
    expect(await answer).toBeNull()
  })
})
