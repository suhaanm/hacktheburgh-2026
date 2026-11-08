import { describe, expect, it } from 'vitest'
import { buildToolDeclarations, parseToolCall } from '../live/tools'
import { createRunningCount, createTaskClient, parseCreated, parseRow, parseTaskText, type TaskRow } from './tasks'

const CONSENT = {
  kind: 'claude_agent',
  scope_text: 'Knack will start a Claude agent.',
  can: ['Read and change files on this Mac', 'Run commands on this Mac'],
  cannot: ['Use Knack’s own keys or models'],
  folder: '~/Knack/work/summarise',
  command_hash: 'abc123def456',
  cost_note: 'Uses your Claude plan.',
  max_minutes: 30,
  buttons: { allow: 'Allow for this task', decline: 'Not now', more: [{ id: 'everything', label: 'Allow everything for this task' }] },
}
const created = (over: Record<string, unknown> = {}) => ({ task_id: 'tk_ab12cd34', route: 'claude_agent', summary: 'Knack will start a Claude agent for this once you allow it.', needs_consent: CONSENT, question: null, ...over })

describe('what the model may ask for', () => {
  const cand = { items: [] }
  it('start_task is declared and accepted only when code can answer it', () => {
    expect(buildToolDeclarations(cand).map((t) => t.name)).not.toContain('start_task')
    expect(buildToolDeclarations(cand, { tasks: true }).map((t) => t.name)).toContain('start_task')
    expect(buildToolDeclarations(cand, { wake: true }).map((t) => t.name)).not.toContain('start_task')
    expect(parseToolCall('start_task', { text: 'summarise my notes' }, cand)).toMatchObject({ ok: false, code: 'unknown_tool' })
    expect(parseToolCall('start_task', { text: 'summarise my notes' }, cand, { tasks: true })).toEqual({ ok: true, name: 'start_task', args: { text: 'summarise my notes' } })
  })
  it('is in both a talk-key session and a wake session when tasks are on', () => {
    for (const wake of [false, true]) expect(buildToolDeclarations(cand, { tasks: true, wake }).find((t) => t.name === 'start_task')?.parameters?.properties?.text?.maxLength).toBe(300)
  })
  it('cleans the text like a pointing description and caps it at 300 characters', () => {
    expect(parseTaskText('summarise‮   the\nnotes\u0000 please')).toBe('summarise the notes please')
    expect(parseTaskText('a'.repeat(300))).not.toBeNull()
    expect(parseTaskText('a'.repeat(301))).toBeNull()
    expect(parseTaskText('ab')).toBeNull()
    expect(parseTaskText('')).toBeNull()
    expect(parseTaskText(5)).toBeNull()
    for (const bad of ['run `rm -rf /`', 'do <script>x</script>', 'use {{secret}}', '```code```']) expect(parseTaskText(bad)).toBeNull()
    expect(parseTaskText('look at https://example.org/page and tell me the title')).toBe('look at https://example.org/page and tell me the title') // a site name is a normal request here
  })
  it('refuses extra arguments and a bad text with a plain message', () => {
    expect(parseToolCall('start_task', { text: 'summarise my notes', x: 1 }, cand, { tasks: true })).toMatchObject({ ok: false, code: 'unknown_argument' })
    const r = parseToolCall('start_task', { text: '`x`' }, cand, { tasks: true })
    expect(r).toMatchObject({ ok: false, code: 'bad_text' })
    expect(parseToolCall('start_task', 'x', cand, { tasks: true })).toMatchObject({ ok: false, code: 'bad_arguments' })
  })
})

describe('what the service answers is parsed strictly', () => {
  it('reads a created task with its consent card and question', () => {
    const c = parseCreated(created())
    expect(c).toMatchObject({ task_id: 'tk_ab12cd34', route: 'claude_agent' })
    expect(c?.needs_consent?.buttons).toEqual({ allow: 'Allow for this task', decline: 'Not now', more: [{ id: 'everything', label: 'Allow everything for this task' }] })
    const q = parseCreated(created({ route: 'unclear', needs_consent: null, question: { text: 'Which do you mean?', options: [{ id: 'answer', label: 'Answer here' }, { id: 'browser', label: 'Use a browser' }] } }))
    expect(q?.question?.options).toHaveLength(2)
  })
  it.each([
    ['no id', { route: 'answer' }],
    ['a bad id', { task_id: '../x', route: 'answer' }],
    ['an unknown route', { task_id: 'tk_1', route: 'shell' }],
    ['not an object', 'x'],
  ])('refuses %s', (_l, raw) => {
    expect(parseCreated(raw)).toBeNull()
  })
  it('drops what does not fit: long lines are cut, odd option ids and a question with one option are ignored', () => {
    const c = parseCreated(created({ summary: 'x'.repeat(500), needs_consent: { ...CONSENT, can: ['a'.repeat(300)], buttons: { allow: 'Go', decline: 'No', more: [{ id: 'bad id!', label: 'x' }] } }, question: { text: 'Q', options: [{ id: 'one', label: 'One' }] } }))
    expect(c?.summary.length).toBeLessThanOrEqual(200)
    expect(c?.needs_consent?.can[0].length).toBeLessThanOrEqual(120)
    expect(c?.needs_consent?.buttons.more).toEqual([])
    expect(c?.question).toBeNull()
  })
  it('reads a row, with the result cut to one line of 140', () => {
    const r = parseRow({ task_id: 'tk_1', route: 'answer', state: 'done', result: 'x'.repeat(400), needs_consent: null, question: null })
    expect(r?.result?.length).toBeLessThanOrEqual(140)
    expect(parseRow({ task_id: 'tk_1', route: 'answer', state: 'weird' })).toBeNull()
  })
})

describe('the task client', () => {
  type Seen = { url: string; method: string; headers: Record<string, string>; body: unknown }
  function fake(answer: (seen: Seen) => { status: number; json?: unknown } | 'throw') {
    const seen: Seen[] = []
    const fetchImpl = (async (url: string, init: RequestInit) => {
      const s: Seen = { url, method: String(init.method), headers: init.headers as Record<string, string>, body: init.body ? JSON.parse(String(init.body)) : undefined }
      seen.push(s)
      const a = answer(s)
      if (a === 'throw') throw new Error('refused')
      return { status: a.status, json: async () => a.json ?? {} } as Response
    }) as unknown as typeof fetch
    return { seen, fetchImpl }
  }
  const client = (f: ReturnType<typeof fake>, token: string | null = 'tok-123') => createTaskClient({ agentUrl: 'http://127.0.0.1:7710', isLoopback: (u) => /127\.0\.0\.1/.test(u), readToken: () => token, fetchImpl: f.fetchImpl })

  it('only talks to the loopback service', () => {
    expect(() => createTaskClient({ agentUrl: 'https://evil.example', isLoopback: (u) => /127\.0\.0\.1/.test(u), readToken: () => null })).toThrow()
  })
  it('creates a task as the voice actor with no token, sending the text and the source only', async () => {
    const f = fake(() => ({ status: 201, json: created() }))
    const r = await client(f).create('summarise my notes')
    expect(r).toMatchObject({ ok: true, created: { task_id: 'tk_ab12cd34' } })
    expect(f.seen).toHaveLength(1)
    expect(f.seen[0]).toMatchObject({ url: 'http://127.0.0.1:7710/tasks', method: 'POST', body: { text: 'summarise my notes', source: 'voice' } })
    expect(f.seen[0].headers['x-understudy-actor']).toBe('voice')
    expect(f.seen[0].headers['x-understudy-token']).toBeUndefined()
    expect(Object.keys(f.seen[0].body as object).sort()).toEqual(['source', 'text'])
  })
  it('maps the service errors to closed reasons', async () => {
    for (const [status, code, reason] of [[429, 'too_many_tasks', 'too_many_tasks'], [423, 'kill_switch_set', 'kill_switch'], [403, 'write_refused', 'refused'], [500, 'x', 'unavailable'], [422, 'bad_body', 'refused']] as const) {
      const f = fake(() => ({ status, json: { error: { code, message: 'Some words the model must not see.' } } }))
      expect(await client(f).create('summarise my notes')).toEqual({ ok: false, reason })
    }
    expect(await client(fake(() => 'throw')).create('summarise my notes')).toEqual({ ok: false, reason: 'unavailable' })
    expect(await client(fake(() => ({ status: 201, json: { nope: 1 } }))).create('summarise my notes')).toEqual({ ok: false, reason: 'unavailable' })
  })
  it('posts consent as worker_approval with the token, and never without one', async () => {
    const f = fake(() => ({ status: 200, json: { task_id: 'tk_ab12cd34', route: 'claude_agent', state: 'running', result: null } }))
    const r = await client(f).consent('tk_ab12cd34', 'allow')
    expect(r).toMatchObject({ ok: true, row: { state: 'running' } })
    expect(f.seen[0]).toMatchObject({ url: 'http://127.0.0.1:7710/tasks/tk_ab12cd34/consent', body: { choice: 'allow' } })
    expect(f.seen[0].headers['x-understudy-actor']).toBe('worker_approval')
    expect(f.seen[0].headers['x-understudy-token']).toBe('tok-123')
    const none = fake(() => ({ status: 200 }))
    expect(await client(none, null).consent('tk_ab12cd34', 'allow')).toEqual({ ok: false, reason: 'no_token' })
    expect(none.seen).toHaveLength(0)
  })
  it('refuses an id that is not an id, and maps a refused consent', async () => {
    const f = fake(() => ({ status: 200 }))
    expect(await client(f).consent('../etc', 'allow')).toEqual({ ok: false, reason: 'refused' })
    expect(await client(f).get('../etc')).toBeNull()
    expect(f.seen).toHaveLength(0)
    expect(await client(fake(() => ({ status: 409, json: { error: { code: 'not_offered', message: 'x' } } }))).consent('tk_1', 'everything')).toEqual({ ok: false, reason: 'not_offered' })
  })
  it('lists rows and reads one', async () => {
    const f = fake((s) => (s.url.endsWith('/tasks') ? { status: 200, json: [{ task_id: 'tk_1', route: 'answer', state: 'running' }, { nope: 1 }] } : { status: 200, json: { task_id: 'tk_1', route: 'answer', state: 'done', result: 'Done it.' } }))
    expect((await client(f).list())?.map((r) => r.task_id)).toEqual(['tk_1'])
    expect((await client(f).get('tk_1'))?.result).toBe('Done it.')
    expect(await client(fake(() => 'throw')).list()).toBeNull()
  })
})

describe('the count of running tasks', () => {
  const row = (state: TaskRow['state']): TaskRow => ({ task_id: 'tk_1', route: 'answer', state, result: null, needs_consent: null, question: null })
  it('counts planning and running tasks and nothing else', async () => {
    let t = 1000
    const rc = createRunningCount({ list: async () => [row('running'), row('planning'), row('done'), row('waiting_consent'), row('failed')], now: () => t, setInterval: () => 0, clearInterval: () => undefined })
    expect(rc.running()).toBeNull()
    rc.start()
    await Promise.resolve()
    await Promise.resolve()
    expect(rc.running()).toEqual({ n: 2, t: 1000 })
    t = 5000
    expect(rc.running()?.t).toBe(1000) // the time it was counted, not now
  })
  it('is unknown when the service does not answer', async () => {
    const rc = createRunningCount({ list: async () => null, setInterval: () => 0, clearInterval: () => undefined })
    rc.start()
    await Promise.resolve()
    expect(rc.running()).toBeNull()
  })
})
