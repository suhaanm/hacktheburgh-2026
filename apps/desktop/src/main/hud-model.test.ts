import { describe, expect, it, vi } from 'vitest'
import type { HudNotice, HudState } from '../shared/hud'
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

const proposal = { id: 'calc-entry-3x', title: 'Enter the household into three calculators', what: 'You enter the same household three times.', howOften: 'about 14 times in 3 weeks', hoursSaved: [3.1, 5.2] as [number, number], horizonWeeks: 4, touches: ['gov.uk check'], never: ['submit'] }

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

  it('knows whether an agent is acting (the Stop all pill shows only then) and pushes only on a change', () => {
    const { model, pushed } = setup()
    expect(model.state().agentActing).toBe(false)
    model.setAgentActing(false)
    expect(pushed).toHaveLength(0)
    model.setAgentActing(true)
    model.setAgentActing(true)
    expect(model.state().agentActing).toBe(true)
    expect(pushed).toHaveLength(1)
    model.setAgentActing(false)
    expect(model.state().agentActing).toBe(false)
  })

  it('places the HUD bottom-left of the work area with a margin', () => {
    expect(hudBounds({ x: 0, y: 25, width: 1728, height: 1050 }, { width: 200, height: 40 })).toEqual({ x: 14, y: 25 + 1050 - 40 - 14, width: 200, height: 40 })
  })
})

const notice: HudNotice = { id: 'i_one', title: 'An approval is waiting', body: 'Approval queue: 1 approval waiting.', source: 'Approval queue', actions: [{ id: 'open_queue', label: 'Open the queue' }, { id: 'dismiss', label: 'Close' }], urgent: false }

describe('HUD model: the attention notice', () => {
  const sinkRig = () => {
    const r = setup()
    const sink = { action: vi.fn(), closed: vi.fn() }
    r.model.setAttention(sink)
    return { ...r, sink }
  }

  it('starts without a notice, pushes when one is set or removed, and not again for the same notice', () => {
    const { model, pushed } = setup()
    expect(model.state().notice).toBeNull()
    model.setNotice(notice)
    model.setNotice(notice)
    expect(model.state().notice?.id).toBe('i_one')
    expect(pushed).toHaveLength(1)
    model.setNotice({ ...notice, id: 'i_two' })
    expect(model.state().notice?.id).toBe('i_two')
    model.setNotice(null)
    model.setNotice(null)
    expect(model.state().notice).toBeNull()
    expect(pushed).toHaveLength(3)
  })

  it('a button goes to the layer with the id and the action, and the card is removed', () => {
    const { model, sink } = sinkRig()
    model.setNotice(notice)
    expect(model.handle({ type: 'notice', id: 'i_one', action: 'open_queue' })).toBe(true)
    expect(sink.action).toHaveBeenCalledWith('i_one', 'open_queue')
    expect(model.state().notice).toBeNull()
  })

  it('closing without a button goes to the layer as dismissed or timeout', () => {
    const { model, sink } = sinkRig()
    model.setNotice(notice)
    expect(model.handle({ type: 'notice_closed', id: 'i_one', how: 'dismissed' })).toBe(true)
    expect(sink.closed).toHaveBeenCalledWith('i_one', 'dismissed')
    model.setNotice(notice)
    expect(model.handle({ type: 'notice_closed', id: 'i_one', how: 'timeout' })).toBe(true)
    expect(sink.closed).toHaveBeenLastCalledWith('i_one', 'timeout')
  })

  it('a stale click, an unknown action id, a bad way of closing, or no layer bound does nothing', () => {
    const { model, sink } = sinkRig()
    model.setNotice(notice)
    expect(model.handle({ type: 'notice', id: 'i_gone', action: 'open_queue' })).toBe(false)
    expect(model.handle({ type: 'notice', id: 'i_one', action: 'delete_everything' })).toBe(false)
    expect(model.handle({ type: 'notice', id: '', action: 'open_queue' })).toBe(false)
    expect(model.handle({ type: 'notice_closed', id: 'i_one', how: 'maybe' })).toBe(false)
    expect(sink.action).not.toHaveBeenCalled()
    expect(sink.closed).not.toHaveBeenCalled()
    expect(model.state().notice?.id).toBe('i_one')
    model.setAttention(null)
    expect(model.handle({ type: 'notice', id: 'i_one', action: 'open_queue' })).toBe(false)
    expect(model.state().notice?.id).toBe('i_one')
  })

  it('every action id the layer can send is accepted, nothing else', () => {
    for (const action of ['open_menu', 'open_run', 'open_queue', 'open_calendar', 'open_routines', 'open_briefing', 'open_report', 'open_settings', 'open_summary', 'dismiss', 'not_now', 'never'])
      expect(HudActionSchema.safeParse({ type: 'notice', id: 'i', action }).success, action).toBe(true)
    expect(HudActionSchema.safeParse({ type: 'notice', id: 'i', action: 'approve' }).success).toBe(false)
  })

  it('the old actions are unchanged: kill and the proposal still work with a layer bound', () => {
    const { model, kill, choices } = sinkRig()
    model.setProposal(proposal)
    expect(model.handle({ type: 'proposal', id: 'calc-entry-3x', choice: 'never' })).toBe(true)
    expect(choices).toEqual(['calc-entry-3x:never'])
    model.handle({ type: 'kill' })
    expect(kill.trigger).toHaveBeenCalledWith('hud')
  })

  it('a layer given at construction works without setAttention', () => {
    const sink = { action: vi.fn(), closed: vi.fn() }
    const kstate: KillState = { killed: false, at: null, source: null, engine: null, agent: null }
    const model = createHudModel({ kill: { trigger: vi.fn(), clear: vi.fn(), state: () => kstate, subscribe: () => () => undefined } as never, endpoints: { dashboard: 'http://127.0.0.1:18173' }, openExternal: vi.fn(), onProposalChoice: vi.fn(), push: vi.fn(), attention: sink })
    model.setNotice(notice)
    model.handle({ type: 'notice', id: 'i_one', action: 'dismiss' })
    expect(sink.action).toHaveBeenCalledWith('i_one', 'dismiss')
  })
})

