import { describe, expect, it, vi } from 'vitest'
import type { HudState } from '../shared/hud'
import { createHudModel, hudBounds, HudActionSchema } from './hud-model'
import type { KillState } from './kill-switch'

function setup() {
  let kstate: KillState = { killed: false, at: null, source: null, engine: null, agent: null }
  const listeners = new Set<(s: KillState) => void>()
  const kill = {
    trigger: vi.fn(async () => {
      kstate = { killed: true, at: 1, source: 'hud', engine: true, agent: false }
      listeners.forEach((l) => l(kstate))
      return { source: 'hud' as const, at: 1, localMs: 1, engine: true, agent: false }
    }),
    clear: vi.fn(async () => {
      kstate = { killed: false, at: null, source: null, engine: null, agent: null }
      listeners.forEach((l) => l(kstate))
    }),
    state: () => kstate,
    subscribe: (cb: (s: KillState) => void) => (listeners.add(cb), () => listeners.delete(cb)),
  }
  const pushed: HudState[] = []
  const opened: string[] = []
  const choices: string[] = []
  const model = createHudModel({ kill, endpoints: { dashboard: 'http://127.0.0.1:5173' }, openExternal: (u) => void opened.push(u), onProposalChoice: (id, c) => void choices.push(`${id}:${c}`), push: (s) => void pushed.push(s) })
  return { model, kill, pushed, opened, choices }
}

const proposal = { id: 'calc-entry-3x', title: 'Enter the household into three calculators', what: 'You enter the same household three times.', howOften: 'about 14 times in 3 weeks', hoursSaved: [3.1, 5.2] as [number, number], touches: ['gov.uk check'], never: ['submit'] }

describe('HUD model', () => {
  it('the kill action triggers the switch, clears any proposal, and the stopped state is pushed', async () => {
    const { model, kill, pushed } = setup()
    model.setProposal(proposal)
    expect(model.handle({ type: 'kill' })).toBe(true)
    await Promise.resolve()
    expect(kill.trigger).toHaveBeenCalledWith('hud')
    expect(model.state().proposal).toBeNull()
    expect(model.state().kill).toEqual({ killed: true, engine: true, agent: false })
    expect(pushed.at(-1)?.kill.killed).toBe(true)
  })

  it('no proposal shows while stopped; Resume clears the stop', async () => {
    const { model, kill } = setup()
    model.handle({ type: 'kill' })
    await Promise.resolve()
    model.setProposal(proposal)
    expect(model.state().proposal).toBeNull()
    model.handle({ type: 'resume' })
    await Promise.resolve()
    expect(kill.clear).toHaveBeenCalled()
    model.setProposal(proposal)
    expect(model.state().proposal?.id).toBe('calc-entry-3x')
  })

  it('opens only dashboard URLs: the morning queue and the routines page', () => {
    const { model, opened } = setup()
    model.handle({ type: 'open_queue' })
    model.setProposal(proposal)
    model.handle({ type: 'proposal', id: 'calc-entry-3x', choice: 'look' })
    expect(opened).toEqual(['http://127.0.0.1:5173/#/queue', 'http://127.0.0.1:5173/#/routines'])
  })

  it('Not now and Never for this dismiss the toast and report the choice once; a stale click does nothing', () => {
    const { model, choices } = setup()
    model.setProposal(proposal)
    expect(model.handle({ type: 'proposal', id: 'calc-entry-3x', choice: 'never' })).toBe(true)
    expect(model.state().proposal).toBeNull()
    expect(model.handle({ type: 'proposal', id: 'calc-entry-3x', choice: 'never' })).toBe(false)
    expect(model.handle({ type: 'proposal', id: 'other', choice: 'not_now' })).toBe(false)
    expect(choices).toEqual(['calc-entry-3x:never'])
  })

  it('ignores malformed actions and does not re-push an unchanged proposal or count', () => {
    const { model, pushed } = setup()
    for (const bad of [null, {}, { type: 'launch' }, { type: 'proposal', id: '', choice: 'look' }, { type: 'proposal', id: 'a', choice: 'approve' }]) expect(model.handle(bad)).toBe(false)
    model.setProposal(proposal)
    model.setProposal(proposal)
    model.setQueuePending(2)
    model.setQueuePending(2)
    expect(pushed).toHaveLength(2)
    expect(HudActionSchema.safeParse({ type: 'kill' }).success).toBe(true)
  })

  it('places the HUD bottom-left of the work area with a margin', () => {
    expect(hudBounds({ x: 0, y: 25, width: 1728, height: 1050 }, { width: 200, height: 40 })).toEqual({ x: 14, y: 25 + 1050 - 40 - 14, width: 200, height: 40 })
  })
})
