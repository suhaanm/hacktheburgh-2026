// Integration through the real dispatcher, StateStore and Bus with ARCH's mock services: the same path as POST /tool.
import { describe, expect, it } from 'vitest'
import { Bus } from '../bus'
import { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import { mockCapture, mockGrounder, mockLearner, mockScam } from '../mocks'
import { StateStore } from '../state'
import { createDispatcher } from '../tools/dispatcher'
import type { Services } from '../../shared/contracts'
import type { Annotation } from '../../shared/protocol'
import { DEFAULT_SETTINGS } from '../../shared/settings'
import { until } from './fakes.test-util'
import { createAgentsFromServices } from './wire'

function setup(settings = DEFAULT_SETTINGS, scamOverride?: Services['scam']) {
  const state = new StateStore({ ...settings })
  state.patch({ phase: 'live' })
  const bus = new Bus()
  const shown: Annotation[][] = []
  const cleared: (string[] | undefined)[] = []
  const injected: string[] = []
  const ctx = {
    state,
    bus,
    settings: { get: () => state.get().settings },
    userDataDir: '/tmp/alongside-wire-test',
    sendOverlay: () => undefined,
    sendDock: () => undefined,
    log: () => undefined,
  } as unknown as ServiceContext
  const s = {
    capture: mockCapture(),
    grounder: mockGrounder(),
    scam: scamOverride ?? mockScam(),
    learner: mockLearner(),
    overlay: { show: (a: Annotation[]) => void shown.push(a), clear: (ids?: string[]) => void cleared.push(ids), caption: () => undefined, chip: () => undefined },
    live: { inject: (text: string) => void injected.push(text) },
  } as unknown as Services
  const agents = createAgentsFromServices(ctx, s)
  s.agents = agents
  const dispatch = createDispatcher(ctx, s, new ConfirmBroker(state))
  const events: string[] = []
  bus.on('agent:update', ({ chip }) => events.push(`${chip.kind}:${chip.status}`))
  return { state, bus, dispatch, agents, shown, cleared, injected, events }
}

describe('spawn_agent through the dispatcher', () => {
  it('scam_check: returns {agentId} at once, chip goes running -> done in state, highlights shown, result injected', async () => {
    const t = setup()
    const res = await t.dispatch('spawn_agent', { kind: 'scam_check', task: 'check this text', payload: { text: 'Your account will be closed in 24 hours. Tap here to verify.' } }, 'live')
    expect(res).toHaveProperty('agentId')
    expect(t.state.get().agents[0]).toMatchObject({ kind: 'scam_check', status: 'running' })
    await until(() => t.state.get().agents[0]?.status === 'done', 5000)
    await until(() => t.shown.flat().some((a) => a.kind === 'bubble'), 3000)
    // Progress updates add extra running events; the chip only ever finishes once, at the end.
    expect(t.events[0]).toBe('scam_check:running')
    expect(t.events.at(-1)).toBe('scam_check:done')
    expect(t.events.filter((e) => e === 'scam_check:done')).toHaveLength(1)
    expect(t.shown.flat().some((a) => a.kind === 'highlightText')).toBe(true)
    expect(t.injected[0]).toMatch(/^\[AGENT_RESULT kind=scam_check id=\S+ status=done\]/)
    expect(t.injected[0]).not.toMatch(/\bsafe\b/i)
  })

  it('forwards the analyst progress callback so the tray shows live stages', async () => {
    const real = mockScam()
    let received: string | undefined
    const scam: Services['scam'] = {
      analyze: async (req, opts) => {
        received = typeof opts?.onProgress
        opts?.onProgress?.('Checking the link…')
        return real.analyze(req)
      },
    }
    const t = setup(DEFAULT_SETTINGS, scam)
    await t.dispatch('spawn_agent', { kind: 'scam_check', task: 'x', payload: { text: 'Tap here to verify your account.' } })
    await until(() => t.state.get().agents[0]?.status === 'done', 5000)
    expect(received).toBe('function')
    expect(t.state.get().agents[0]?.summary).toMatch(/^This looks like a scam/)
  })

  it('clear_annotations removes the scam highlights we are tracking', async () => {
    const t = setup()
    await t.dispatch('spawn_agent', { kind: 'scam_check', task: 'x', payload: { text: 'Tap here to verify your account now.' } })
    await until(() => t.state.get().agents[0]?.status === 'done', 5000)
    await until(() => t.shown.flat().some((a) => a.kind === 'bubble'), 3000)
    t.cleared.length = 0
    await t.dispatch('clear_annotations', {})
    expect(t.cleared.some((ids) => ids?.some((id) => id.includes('-flag-') || id.endsWith('-advice')))).toBe(true)
  })

  it('returns a plain error (not a stack) when the fourth agent is refused', async () => {
    const t = setup()
    for (let i = 0; i < 3; i++) await t.dispatch('spawn_agent', { kind: 'scam_check', task: `t${i}`, payload: { text: 'Tap here to verify.' } })
    const fourth = await t.dispatch('spawn_agent', { kind: 'scam_check', task: 't3', payload: { text: 'Tap here to verify.' } })
    // Mock analyst takes 400 ms, so all four attempts overlap: the fourth must be refused politely.
    expect(fourth).toEqual({ error: expect.stringMatching(/already working on three things/) })
    t.agents.dispose?.()
  })

  it('cancelling through the runtime (IPC agent:cancel) marks the chip cancelled', async () => {
    const t = setup()
    const res = (await t.dispatch('spawn_agent', { kind: 'scam_check', task: 'x', payload: { text: 'Tap here to verify.' } })) as { agentId: string }
    t.agents.cancel(res.agentId)
    await until(() => t.state.get().agents[0]?.status === 'cancelled', 3000)
    expect(t.injected).toEqual([])
  })

  it('the Stop control (session:ended stop) cancels running agents; goodbye does not', async () => {
    const t = setup()
    await t.dispatch('spawn_agent', { kind: 'scam_check', task: 'x', payload: { text: 'Tap here to verify.' } })
    t.bus.emit('session:ended', { reason: 'goodbye' })
    expect(t.state.get().agents[0]?.status).toBe('running')
    t.bus.emit('session:ended', { reason: 'stop' })
    await until(() => t.state.get().agents[0]?.status === 'cancelled', 3000)
    expect(t.injected).toEqual([])
  })

  it('rejects unknown kinds at the schema boundary', async () => {
    const t = setup()
    const res = await t.dispatch('spawn_agent', { kind: 'send_email', task: 'x' })
    expect(res).toHaveProperty('error')
  })
})
