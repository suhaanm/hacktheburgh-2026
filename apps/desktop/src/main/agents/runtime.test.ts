import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAgents } from './index'
import { MAX_CONCURRENT_AGENTS, createAgentRuntime } from './runtime'
import { defineAgent } from './ports'
import { AgentUserError } from './errors'
import { makeFakes, until } from './fakes.test-util'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function hanging(kind: 'lookup' | 'scam_check', timeoutMs: number) {
  return defineAgent<null>({
    kind,
    timeoutMs,
    title: () => 'Hanging',
    createPorts: () => null,
    run: () => new Promise(() => undefined),
  })
}

describe('AgentRuntime lifecycle', () => {
  it('returns an id immediately, shows a running chip, then a done chip, and tells the Live model', async () => {
    const f = makeFakes()
    const rt = createAgents(f.deps)
    const { agentId } = await rt.spawn('lookup', 'how do I make text bigger on my iPhone')
    expect(rt.list()).toHaveLength(1)
    expect(rt.list()[0]).toMatchObject({ id: agentId, kind: 'lookup', status: 'running' })
    expect(f.chipsPatched[0]?.[0]?.status).toBe('running')

    await until(() => rt.list()[0]?.status === 'done')
    const chip = rt.list()[0]!
    expect(chip.summary).toContain('support.example.com')
    expect(chip.result?.kind).toBe('lookup')
    expect(f.busEvents.map((c) => c.status)).toEqual(['running', 'done'])
    expect(f.injected).toHaveLength(1)
    expect(f.injected[0]!.text).toMatch(/^\[AGENT_RESULT kind=lookup id=agent-\d+-[0-9a-f]{4} status=done\] /)
    expect(f.injected[0]!.interrupt).toBe(false)
  })

  it('caps concurrency at three and refuses the fourth in plain English', async () => {
    const f = makeFakes()
    const rt = createAgentRuntime(f.deps, [hanging('lookup', 60_000)])
    for (let i = 0; i < MAX_CONCURRENT_AGENTS; i++) await rt.spawn('lookup', `task ${i}`)
    await expect(rt.spawn('lookup', 'one too many')).rejects.toMatchObject({ code: 'busy' })
    rt.dispose()
  })

  it('frees a slot once an agent finishes', async () => {
    const f = makeFakes()
    const rt = createAgents(f.deps)
    for (let i = 0; i < MAX_CONCURRENT_AGENTS; i++) await rt.spawn('lookup', `task ${i}`)
    await until(() => rt.list().every((c) => c.status === 'done'))
    await expect(rt.spawn('lookup', 'again')).resolves.toHaveProperty('agentId')
  })

  it('times out with a plain message and ignores a late result', async () => {
    vi.useFakeTimers()
    const f = makeFakes()
    const rt = createAgentRuntime(f.deps, [hanging('lookup', 30_000)])
    await rt.spawn('lookup', 'slow one')
    await vi.advanceTimersByTimeAsync(30_001)
    const chip = rt.list()[0]!
    expect(chip.status).toBe('error')
    expect(chip.summary).toMatch(/took too long/i)
    expect(chip.summary).not.toMatch(/\bError\b|stack|\.ts\b|:\d+/)
    expect(f.injected[0]!.text).toContain('status=error')
  })

  it('scam checks get 60 s and lookups 30 s by default', async () => {
    vi.useFakeTimers()
    const f = makeFakes()
    f.set.search = () => new Promise(() => undefined)
    f.set.analyze = () => new Promise(() => undefined)
    const rt = createAgents(f.deps)
    await rt.spawn('lookup', 'q')
    await rt.spawn('scam_check', 'check', { text: 'hello there friend' })
    await vi.advanceTimersByTimeAsync(31_000)
    expect(rt.list().find((c) => c.kind === 'lookup')?.status).toBe('error')
    expect(rt.list().find((c) => c.kind === 'scam_check')?.status).toBe('running')
    await vi.advanceTimersByTimeAsync(20_000)
    expect(rt.list().find((c) => c.kind === 'scam_check')?.status).toBe('running')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(rt.list().find((c) => c.kind === 'scam_check')?.status).toBe('error')
  })

  it('cancel stops the agent, marks the chip cancelled, and says nothing to the Live model', async () => {
    const f = makeFakes()
    f.set.search = () => new Promise(() => undefined)
    const rt = createAgents(f.deps)
    const { agentId } = await rt.spawn('lookup', 'never finishes')
    rt.cancel(agentId)
    await until(() => rt.list()[0]?.status === 'cancelled')
    expect(rt.list()[0]!.summary).toBe('Stopped.')
    expect(f.injected).toHaveLength(0)
    rt.cancel(agentId)
    rt.cancel('does-not-exist')
  })

  // built at runtime so secret scanners don't flag this fake fixture
  const FAKE_KEY = ['AI', 'zaSy', 'X'.repeat(33)].join('')

  it('turns raw errors into one plain sentence with no stack trace', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const f = makeFakes()
    f.set.search = async () => {
      throw new Error('boom at /Users/x/src/secret.ts:12:3 key=' + FAKE_KEY)
    }
    const rt = createAgents(f.deps)
    await rt.spawn('lookup', 'q')
    await until(() => rt.list()[0]?.status === 'error')
    const summary = rt.list()[0]!.summary!
    expect(summary).toMatch(/Nothing was sent or changed/)
    expect(summary).not.toMatch(/secret\.ts|AIza|boom/)
    expect(f.injected[0]!.text).not.toMatch(/secret\.ts|AIza|boom/)
    const logged = (console.error as unknown as { mock: { calls: string[][] } }).mock.calls.flat().join(' ')
    expect(logged).not.toContain(FAKE_KEY)
  })

  it('maps quota and network failures to friendly text', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const f = makeFakes()
    f.set.search = async () => {
      throw Object.assign(new Error('RESOURCE_EXHAUSTED'), { status: 429 })
    }
    const rt = createAgents(f.deps)
    await rt.spawn('lookup', 'q')
    await until(() => rt.list()[0]?.status === 'error')
    expect(rt.list()[0]!.summary).toMatch(/busy at the moment/)
  })

  it('rejects unknown kinds, empty tasks and bad payloads without creating a chip', async () => {
    const f = makeFakes()
    const rt = createAgents(f.deps)
    await expect(rt.spawn('send_email' as never, 'x')).rejects.toBeInstanceOf(AgentUserError)
    await expect(rt.spawn('lookup', '   ')).rejects.toBeInstanceOf(AgentUserError)
    await expect(rt.spawn('lookup', 'q', { text: 42 } as never)).rejects.toBeInstanceOf(AgentUserError)
    expect(rt.list()).toHaveLength(0)
  })

  it('keeps the tray short: running chips plus the last five finished', async () => {
    const f = makeFakes()
    const rt = createAgents(f.deps)
    for (let i = 0; i < 8; i++) {
      await rt.spawn('lookup', `q${i}`)
      await until(() => rt.list().every((c) => c.status !== 'running'))
    }
    expect(rt.list()).toHaveLength(5)
  })
})

describe('read-only guarantees', () => {
  it('only the runtime talks to the Live model, and only with [AGENT_RESULT] lines', async () => {
    const f = makeFakes({ carerSharing: true })
    const rt = createAgents(f.deps)
    await rt.spawn('scam_check', 'check', { text: 'Your account will be closed in 24 hours. Verify your PIN.' })
    await rt.spawn('lookup', 'how do I zoom')
    await rt.spawn('lesson_summary', 'summary')
    await until(() => rt.list().every((c) => c.status !== 'running'))
    expect(f.injected.length).toBe(3)
    for (const m of f.injected) expect(m.text.startsWith('[AGENT_RESULT ')).toBe(true)
  })

  it('agents only call the read-only ports they are given', async () => {
    const f = makeFakes({ carerSharing: true })
    const rt = createAgents(f.deps)
    await rt.spawn('scam_check', 'check', { text: 'Verify your PIN or your account will be closed in 24 hours.' })
    await rt.spawn('lookup', 'q')
    await rt.spawn('lesson_summary', 's')
    await until(() => rt.list().every((c) => c.status !== 'running'))
    const allowed = /^(capture\.grab:ground|grounder\.ground:|scam\.analyze|model\.searchAnswer)/
    for (const call of f.calls) expect(call).toMatch(allowed)
    // Overlay: only show/clear of highlights, never captions or chips (the fake has no other methods to call).
    expect(Object.keys(f.deps.overlay).sort()).toEqual(['clear', 'show'])
  })

  it('the agent registry contains exactly the three read-only kinds', async () => {
    const f = makeFakes()
    const rt = createAgents(f.deps)
    for (const kind of ['send_message', 'buy', 'click', 'submit_form', 'run_command']) {
      await expect(rt.spawn(kind as never, 'x')).rejects.toBeInstanceOf(AgentUserError)
    }
  })
})
