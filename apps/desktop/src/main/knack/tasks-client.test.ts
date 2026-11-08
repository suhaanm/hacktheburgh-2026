import { describe, expect, it, vi } from 'vitest'
import { POLL_MS, RETRY, SILENCE_MS, connectTaskEvents, stopTask } from './tasks-client'

const enc = new TextEncoder()
const sse = (event: string, data: unknown): string => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
const row = (id: string, state: string, over: Record<string, unknown> = {}) => ({ task_id: id, title: `Title ${id}`, route: 'browser', state, latest: null, result: null, reason: null, started: '2026-11-08T00:10:00Z', ...over })

/** A fake connection: the test pushes text into it, ends it, or fails it; abort ends it with an error, like a real one. */
function connection() {
  const queue: (Uint8Array | 'end' | Error)[] = []
  let wake: (() => void) | null = null
  let aborted = false
  const pull = async (): Promise<{ done: boolean; value?: Uint8Array }> => {
    for (;;) {
      if (aborted) throw new Error('aborted')
      const next = queue.shift()
      if (next === 'end') return { done: true }
      if (next instanceof Error) throw next
      if (next) return { done: false, value: next }
      await new Promise<void>((r) => (wake = r))
      wake = null
    }
  }
  return {
    send: (text: string) => {
      queue.push(enc.encode(text))
      wake?.()
    },
    end: () => {
      queue.push('end')
      wake?.()
    },
    abort: () => {
      aborted = true
      wake?.()
    },
    response: { ok: true, status: 200, body: { getReader: () => ({ read: pull, cancel: async () => undefined }) } },
  }
}

function rig(responses: ((signal: AbortSignal) => unknown)[] | 'always404') {
  const calls: string[] = []
  const timers: { fn: () => void; ms: number; id: number; live: boolean }[] = []
  let id = 1
  const tasks: unknown[][] = []
  let lost = 0
  let i = 0
  const client = connectTaskEvents({
    base: 'http://127.0.0.1:7710',
    onTasks: (rows) => void tasks.push(rows),
    onLost: () => void (lost += 1),
    fetchFn: async (url, init) => {
      calls.push(url)
      if (responses === 'always404') return { ok: false, status: 404, body: null }
      const r = responses[Math.min(i++, responses.length - 1)]!(init.signal)
      if (r instanceof Error) throw r
      return r as never
    },
    setTimer: (fn, ms) => {
      const t = { fn, ms, id: id++, live: true }
      timers.push(t)
      return t.id
    },
    clearTimer: (h) => {
      const t = timers.find((x) => x.id === h)
      if (t) t.live = false
    },
  })
  const live = () => timers.filter((t) => t.live)
  return { client, calls, tasks, timers, live, lost: () => lost }
}
const settle = () => new Promise((r) => setTimeout(r, 0))

describe('the task events connection', () => {
  it('opens GET /tasks/events, holds the snapshot, upserts each row, and a fresh snapshot replaces what was held', async () => {
    const c = connection()
    const r = rig([() => c.response])
    c.send(sse('snapshot', { tasks: [row('tk_aaaa1111', 'running'), row('tk_bbbb2222', 'done')] }))
    await settle()
    expect(r.calls).toEqual(['http://127.0.0.1:7710/tasks/events']) // the stream is up: no polling
    expect((r.tasks.at(-1) as { task_id: string }[]).map((t) => t.task_id)).toEqual(['tk_aaaa1111', 'tk_bbbb2222'])
    c.send(sse('task_progress', row('tk_aaaa1111', 'running', { latest: 'Opening the page' })))
    c.send(sse('task_started', row('tk_cccc3333', 'planning')))
    c.send(sse('heartbeat', { t: 'x' }))
    await settle()
    const rows = r.tasks.at(-1) as { task_id: string; latest?: string }[]
    expect(rows.map((t) => t.task_id)).toEqual(['tk_aaaa1111', 'tk_bbbb2222', 'tk_cccc3333'])
    expect(rows[0]!.latest).toBe('Opening the page')
    c.send(sse('snapshot', { tasks: [row('tk_dddd4444', 'running')] }))
    await settle()
    expect((r.tasks.at(-1) as { task_id: string }[]).map((t) => t.task_id)).toEqual(['tk_dddd4444'])
    r.client.stop()
  })
  it('ignores a malformed event and a row without an id', async () => {
    const c = connection()
    const r = rig([() => c.response])
    c.send('event: snapshot\ndata: not json\n\n')
    c.send(sse('task_started', { title: 'no id' }))
    c.send(sse('task_started', row('tk_aaaa1111', 'running')))
    await settle()
    expect(r.tasks).toHaveLength(1)
    r.client.stop()
  })
  it('treats 25 seconds of silence as a dead connection: it drops it and opens another, and the fresh snapshot replaces the state', async () => {
    const first = connection()
    const second = connection()
    const linked = (c: ReturnType<typeof connection>) => (signal: AbortSignal) => {
      signal.addEventListener('abort', () => c.abort()) // a real connection ends when the client aborts it
      return c.response
    }
    const r = rig([linked(first), linked(second)])
    first.send(sse('snapshot', { tasks: [row('tk_aaaa1111', 'running')] }))
    await settle()
    const watchdog = r.live().find((t) => t.ms === SILENCE_MS)!
    expect(watchdog).toBeTruthy()
    watchdog.fn() // 25 s with no byte
    await settle()
    const retry = r.live().find((t) => t.ms === RETRY.firstMs)!
    retry.fn()
    await settle()
    expect(r.calls.filter((c) => c.endsWith('/tasks/events'))).toHaveLength(2)
    second.send(sse('snapshot', { tasks: [row('tk_bbbb2222', 'running')] }))
    await settle()
    expect((r.tasks.at(-1) as { task_id: string }[]).map((t) => t.task_id)).toEqual(['tk_bbbb2222'])
    r.client.stop()
  })
  it('tells the pills when the service cannot be reached for that long, so none keeps saying working', async () => {
    const r = rig([() => new Error('connection refused')])
    await settle()
    const lost = r.live().find((t) => t.ms === SILENCE_MS)!
    lost.fn()
    expect(r.lost()).toBe(1)
    r.client.stop()
  })
  it('a service without the route (404) is asked again only every half minute', async () => {
    const r = rig('always404')
    await settle()
    expect(r.calls.filter((c) => c.endsWith('/tasks/events'))).toHaveLength(1)
    expect(r.live().some((t) => t.ms === RETRY.noRouteMs)).toBe(true)
    r.client.stop()
  })
  it('refuses an address that is not this machine, and stop ends everything', async () => {
    const fetchFn = vi.fn()
    connectTaskEvents({ base: 'http://example.com:7710', onTasks: () => undefined, onLost: () => undefined, fetchFn })
    await settle()
    expect(fetchFn).not.toHaveBeenCalled()
    const c = connection()
    const r = rig([() => c.response])
    await settle()
    r.client.stop()
    expect(r.live()).toEqual([])
  })
})

describe('while the stream is down: GET /tasks every three seconds', () => {
  function pollRig(tasksBody: () => unknown) {
    const calls: string[] = []
    const timers: { fn: () => void; ms: number; id: number; live: boolean }[] = []
    let id = 1
    const tasks: unknown[][] = []
    let lost = 0
    const client = connectTaskEvents({
      base: 'http://127.0.0.1:7710',
      onTasks: (rows) => void tasks.push(rows),
      onLost: () => void (lost += 1),
      fetchFn: async (url) => {
        calls.push(url)
        if (url.endsWith('/tasks/events')) return { ok: false, status: 503, body: null }
        const body = tasksBody()
        if (body instanceof Error) throw body
        return { ok: true, status: 200, body: null, json: async () => body }
      },
      setTimer: (fn, ms) => {
        const t = { fn, ms, id: id++, live: true }
        timers.push(t)
        return t.id
      },
      clearTimer: (h) => {
        const t = timers.find((x) => x.id === h)
        if (t) t.live = false
      },
    })
    return { client, calls, tasks, lost: () => lost, live: () => timers.filter((t) => t.live) }
  }
  it('reads the list with GET /tasks when the stream cannot be had, and keeps reading every three seconds', async () => {
    const r = pollRig(() => ({ tasks: [row('tk_aaaa1111', 'running')] }))
    await settle()
    await settle()
    expect(r.calls).toContain('http://127.0.0.1:7710/tasks')
    expect((r.tasks.at(-1) as { task_id: string }[]).map((t) => t.task_id)).toEqual(['tk_aaaa1111'])
    const next = r.live().find((t) => t.ms === POLL_MS)!
    expect(next).toBeTruthy()
    next.live = false // it fires now
    next.fn()
    await settle()
    await settle()
    expect(r.calls.filter((c) => c.endsWith('/tasks')).length).toBeGreaterThanOrEqual(2)
    r.client.stop()
    expect(r.live()).toEqual([])
  })
  it('takes a bare list as well as { tasks: [...] }', async () => {
    const r = pollRig(() => [row('tk_bbbb2222', 'planning')])
    await settle()
    await settle()
    expect((r.tasks.at(-1) as { task_id: string }[]).map((t) => t.task_id)).toEqual(['tk_bbbb2222'])
    r.client.stop()
  })
  it('a service that answers neither the stream nor the list for 25 seconds is lost', async () => {
    const r = pollRig(() => new Error('refused'))
    await settle()
    await settle()
    const lost = r.live().find((t) => t.ms === SILENCE_MS)!
    lost.fn()
    expect(r.lost()).toBe(1)
    r.client.stop()
  })
})

describe('stopping a task from its pill', () => {
  it('posts an empty body as the worker, to the service on this machine, for a well-formed id only', async () => {
    const f = vi.fn(async () => ({ ok: true }))
    expect(await stopTask('http://127.0.0.1:7710', 'tk_8f3a1c2e', f)).toBe(true)
    expect(f).toHaveBeenCalledWith('http://127.0.0.1:7710/tasks/tk_8f3a1c2e/stop', { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: '{}' })
    expect(await stopTask('http://127.0.0.1:7710', '../../kill', f)).toBe(false)
    expect(await stopTask('http://evil.test', 'tk_8f3a1c2e', f)).toBe(false)
    expect(f).toHaveBeenCalledTimes(1)
  })
  it('says no when the service does or cannot', async () => {
    expect(await stopTask('http://127.0.0.1:7710', 'tk_8f3a1c2e', async () => ({ ok: false }))).toBe(false)
    expect(
      await stopTask('http://127.0.0.1:7710', 'tk_8f3a1c2e', async () => {
        throw new Error('down')
      }),
    ).toBe(false)
  })
})
