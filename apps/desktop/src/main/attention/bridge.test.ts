import { describe, expect, it } from 'vitest'
import { approvalEvent, createProducerBridge, runEvents, type ProducerSources, type QueueItemView, type RunView } from './bridge'
import type { AttentionEvent } from './types'

function rig(sources: ProducerSources) {
  const sent: AttentionEvent[] = []
  const bridge = createProducerBridge(sources, async (e) => void sent.push(e))
  return { bridge, sent }
}
const q = (over: Partial<QueueItemView> = {}): QueueItemView => ({ id: 'q_1', kind: 'batch_result', risk: 'normal', blocksRun: false, ...over })

describe('mapping', () => {
  it('queue kinds become the right event types', () => {
    expect(approvalEvent(q({ kind: 'injection_pause', runId: 'run_7' }))).toMatchObject({ type: 'injection_pause', subject: 'run_7' })
    expect(approvalEvent(q({ kind: 'irreversible_step', risk: 'irreversible', runId: 'run_8' }))).toMatchObject({ type: 'irreversible_decision', risk_class: 'irreversible', run_mode: 'overnight' })
    expect(approvalEvent(q({ blocksRun: true }))).toMatchObject({ type: 'approval_blocking', blocks_run: true, subject: 'q_1' })
    expect(approvalEvent(q())).toMatchObject({ type: 'approval_waiting' })
  })
  it('runs: running is nothing, a paused run needing the worker is blocked, an ended run is finished', () => {
    const r = (o: Partial<RunView>): RunView => ({ id: 'r1', mode: 'overnight', state: 'running', ...o })
    expect(runEvents(r({}))).toEqual([])
    expect(runEvents(r({ state: 'paused', needsHuman: 'target' }))[0].type).toBe('run_blocked_target')
    expect(runEvents(r({ state: 'paused', needsHuman: 'error' }))[0].type).toBe('run_blocked_error')
    expect(runEvents(r({ state: 'paused' }))).toEqual([])
    expect(runEvents(r({ state: 'done' }))[0]).toMatchObject({ type: 'run_finished', outcome: 'done', run_mode: 'overnight' })
    expect(runEvents(r({ state: 'failed' }))[0]).toMatchObject({ outcome: 'failed' })
  })
})

describe('the bridge raises once and resolves when a thing is gone', () => {
  it('raises a new approval once, and resolves it when it disappears', async () => {
    let items: QueueItemView[] | null = [q()]
    const { bridge, sent } = rig({ approvals: async () => items })
    expect(await bridge.pollOnce()).toBe(1)
    expect(await bridge.pollOnce()).toBe(0)
    expect(sent).toHaveLength(1)
    items = []
    expect(await bridge.pollOnce()).toBe(1)
    expect(sent[1]).toEqual({ type: 'approval_waiting', subject: 'q_1', op: 'resolve' })
  })

  it('a failed read never resolves anything', async () => {
    let items: QueueItemView[] | null = [q()]
    const { bridge, sent } = rig({ approvals: async () => items })
    await bridge.pollOnce()
    items = null
    await bridge.pollOnce()
    expect(sent).toHaveLength(1)
  })

  it('a source that throws changes nothing and does not throw', async () => {
    const { bridge, sent } = rig({
      approvals: async () => {
        throw new Error('down')
      },
    })
    await expect(bridge.pollOnce()).resolves.toBe(0)
    expect(sent).toEqual([])
  })

  it('a run finishing is raised once; a service that comes back is resolved; a briefing and proposals are counted', async () => {
    let runs: RunView[] = [{ id: 'r1', mode: 'overnight', state: 'done' }]
    let svc = [{ service: 'agent' as const, ok: false }]
    const { bridge, sent } = rig({
      runs: async () => runs,
      services: async () => svc,
      briefing: async () => ({ generation: 'G7', cards: 3 }),
      proposals: async () => [{ id: 'calc-entry' }],
      morning: async () => ({ id: 'M1', runs: 2 }),
    })
    await bridge.pollOnce()
    const types = sent.map((e) => e.type).sort()
    expect(types).toEqual(['briefing_ready', 'morning_report', 'routine_proposal', 'run_finished', 'service_degraded'])
    expect(sent.find((e) => e.type === 'briefing_ready')).toMatchObject({ subject: 'gen_g7', count: 3 })
    svc = [{ service: 'agent', ok: true }]
    runs = []
    sent.length = 0
    await bridge.pollOnce()
    expect(sent.map((e) => `${e.type}:${e.op}`).sort()).toEqual(['run_finished:resolve', 'service_degraded:resolve'])
  })

  it('nothing it sends can carry text: only the schema fields', async () => {
    const { bridge, sent } = rig({ approvals: async () => [q({ blocksRun: true, runId: 'Run 7 / secret?' })], briefing: async () => ({ generation: 'My Secret Gen', cards: 2 }) })
    await bridge.pollOnce()
    const allowed = new Set(['type', 'subject', 'op', 'risk_class', 'outcome', 'run_mode', 'service', 'count', 'minutes', 'expires_in_s', 'deadline_in_s', 'blocks_run', 'asked', 'state'])
    for (const e of sent) {
      for (const k of Object.keys(e)) expect(allowed.has(k)).toBe(true)
      expect(e.subject).toMatch(/^[a-z0-9][a-z0-9_.:-]{0,63}$/)
    }
  })
})
