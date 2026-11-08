// "Hey Knack, do X": the desktop's side of the Task API (agent service, loopback, contract v1). The Live tool `start_task` gives the model's wording of a
// request to code; this file parses what the service answers (strictly: it is data from another process), calls it, and describes the cards.
//
//   POST /tasks            actor voice            {text, source:'voice'} -> {task_id, route, summary, needs_consent, question}
//   POST /tasks/{id}/consent  actor worker_approval + the per-boot token   {choice: allow | everything | decline}   (a real click on a card)
//   POST /tasks/{id}/answer   actor worker_approval + token                {option_id}
//   GET  /tasks, GET /tasks/{id}
//
// Rules this file keeps: the text goes only to the loopback agent service and is never logged or stored here; creating a task never starts anything
// (the service holds it for the worker's click); consent is posted only after a real mouse click (the card window guarantees it) and only with the
// worker_approval actor and the token the main process reads from the data folder. What the model is told about the outcome is a closed answer.
import { cleanLine } from '../live/tools'

export const TASK_ROUTES = ['answer', 'browser', 'desktop', 'claude_agent', 'unclear'] as const
export type TaskRoute = (typeof TASK_ROUTES)[number]
export const TASK_STATES = ['planning', 'waiting_consent', 'running', 'done', 'stopped', 'failed'] as const
export type TaskState = (typeof TASK_STATES)[number]
export type ConsentChoice = 'allow' | 'everything' | 'decline'

export { parseTaskText, TASK_TEXT_MAX } from '../live/tools'
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/

export interface ConsentCard {
  kind: string
  scope_text: string
  can: string[]
  cannot: string[]
  folder: string | null
  max_minutes: number | null
  buttons: { allow: string; decline: string; more: Array<{ id: string; label: string }> }
}
export interface QuestionCard {
  text: string
  options: Array<{ id: string; label: string }>
}
export interface TaskRow {
  task_id: string
  route: TaskRoute
  state: TaskState
  result: string | null
  needs_consent: ConsentCard | null
  question: QuestionCard | null
}
export interface Created extends Omit<TaskRow, 'state' | 'result'> {
  summary: string
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const line = (v: unknown, max: number): string => cleanLine(v).slice(0, max)
const strings = (v: unknown, n: number, max: number): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, n).map((x) => line(x, max)).filter(Boolean) : [])
const opts = (v: unknown, n: number): Array<{ id: string; label: string }> =>
  Array.isArray(v)
    ? v
        .filter(isObj)
        .map((o) => ({ id: typeof o.id === 'string' && ID_RE.test(o.id) ? o.id : '', label: line(o.label, 40) }))
        .filter((o) => o.id && o.label)
        .slice(0, n)
    : []

export function parseConsent(v: unknown): ConsentCard | null {
  if (!isObj(v)) return null
  const b = isObj(v.buttons) ? v.buttons : {}
  const allow = line(b.allow, 40) || 'Allow for this task'
  const decline = line(b.decline, 40) || 'Not now'
  return {
    kind: typeof v.kind === 'string' && /^[a-z_]{1,30}$/.test(v.kind) ? v.kind : 'task',
    scope_text: line(v.scope_text, 400),
    can: strings(v.can, 6, 120),
    cannot: strings(v.cannot, 6, 120),
    folder: typeof v.folder === 'string' ? line(v.folder, 120) || null : null,
    max_minutes: typeof v.max_minutes === 'number' && Number.isFinite(v.max_minutes) ? Math.min(240, Math.max(1, Math.round(v.max_minutes))) : null,
    buttons: { allow, decline, more: opts(b.more, 2) },
  }
}

export function parseQuestion(v: unknown): QuestionCard | null {
  if (!isObj(v)) return null
  const options = opts(v.options, 4)
  const text = line(v.text, 160)
  return text && options.length >= 2 ? { text, options } : null
}

export function parseCreated(raw: unknown): Created | null {
  if (!isObj(raw)) return null
  const route = (TASK_ROUTES as readonly unknown[]).includes(raw.route) ? (raw.route as TaskRoute) : null
  if (typeof raw.task_id !== 'string' || !ID_RE.test(raw.task_id) || !route) return null
  return { task_id: raw.task_id, route, summary: line(raw.summary, 200), needs_consent: parseConsent(raw.needs_consent), question: parseQuestion(raw.question) }
}

export function parseRow(raw: unknown): TaskRow | null {
  if (!isObj(raw)) return null
  const route = (TASK_ROUTES as readonly unknown[]).includes(raw.route) ? (raw.route as TaskRoute) : null
  const state = (TASK_STATES as readonly unknown[]).includes(raw.state) ? (raw.state as TaskState) : null
  if (typeof raw.task_id !== 'string' || !ID_RE.test(raw.task_id) || !route || !state) return null
  return { task_id: raw.task_id, route, state, result: typeof raw.result === 'string' ? line(raw.result, 140) || null : null, needs_consent: parseConsent(raw.needs_consent), question: parseQuestion(raw.question) }
}

// ------------------------------------------------------------------------------------------------ the HTTP client
export type TaskFailure = 'too_many_tasks' | 'kill_switch' | 'no_token' | 'not_offered' | 'unavailable' | 'refused'
export type Result<T> = ({ ok: true } & T) | { ok: false; reason: TaskFailure }

export interface TaskClient {
  create(text: string): Promise<Result<{ created: Created }>>
  consent(taskId: string, choice: ConsentChoice): Promise<Result<{ row: TaskRow | null }>>
  answer(taskId: string, optionId: string): Promise<Result<{ row: TaskRow | null }>>
  get(taskId: string): Promise<TaskRow | null>
  list(): Promise<TaskRow[] | null>
  stop(taskId: string): Promise<boolean>
}

export interface TaskClientDeps {
  agentUrl: string
  isLoopback: (url: string) => boolean
  readToken: () => string | null
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export function createTaskClient(d: TaskClientDeps): TaskClient {
  if (!d.isLoopback(d.agentUrl)) throw new Error('the task service must be on this machine (127.0.0.1)')
  const base = d.agentUrl.replace(/\/+$/, '')
  const doFetch = d.fetchImpl ?? ((i, init) => fetch(i, init))
  const call = async (method: 'GET' | 'POST', path: string, o: { actor?: string; token?: string; body?: object } = {}): Promise<{ status: number; json: unknown } | null> => {
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), d.timeoutMs ?? 20_000)
    try {
      const headers: Record<string, string> = { 'content-type': 'application/json' }
      if (o.actor) headers['x-understudy-actor'] = o.actor
      if (o.token) headers['x-understudy-token'] = o.token
      const res = await doFetch(`${base}${path}`, { method, headers, ...(o.body ? { body: JSON.stringify(o.body) } : {}), signal: ctl.signal })
      const json: unknown = await res.json().catch(() => null)
      return { status: res.status, json }
    } catch {
      return null
    } finally {
      clearTimeout(timer)
    }
  }
  const failure = (r: { status: number; json: unknown } | null): TaskFailure => {
    if (!r) return 'unavailable'
    const code = isObj(r.json) && isObj(r.json.error) && typeof r.json.error.code === 'string' ? r.json.error.code : ''
    if (r.status === 429 || code === 'too_many_tasks') return 'too_many_tasks'
    if (r.status === 423 || code === 'kill_switch_set') return 'kill_switch'
    if (code === 'not_offered') return 'not_offered'
    if (r.status >= 500) return 'unavailable'
    return 'refused'
  }
  const safeId = (id: string): boolean => ID_RE.test(id)
  return {
    async create(text) {
      const r = await call('POST', '/tasks', { actor: 'voice', body: { text, source: 'voice' } })
      if (!r || r.status !== 201) return { ok: false, reason: failure(r) }
      const created = parseCreated(r.json)
      return created ? { ok: true, created } : { ok: false, reason: 'unavailable' }
    },
    async consent(taskId, choice) {
      if (!safeId(taskId)) return { ok: false, reason: 'refused' }
      const token = d.readToken()
      if (!token) return { ok: false, reason: 'no_token' }
      const r = await call('POST', `/tasks/${taskId}/consent`, { actor: 'worker_approval', token, body: { choice } })
      return r && r.status >= 200 && r.status < 300 ? { ok: true, row: parseRow(r.json) } : { ok: false, reason: failure(r) }
    },
    async answer(taskId, optionId) {
      if (!safeId(taskId) || !ID_RE.test(optionId)) return { ok: false, reason: 'refused' }
      const token = d.readToken()
      const r = await call('POST', `/tasks/${taskId}/answer`, { actor: 'worker_approval', ...(token ? { token } : {}), body: { option_id: optionId } })
      return r && r.status >= 200 && r.status < 300 ? { ok: true, row: parseRow(r.json) } : { ok: false, reason: failure(r) }
    },
    async get(taskId) {
      if (!safeId(taskId)) return null
      const r = await call('GET', `/tasks/${taskId}`)
      return r && r.status === 200 ? parseRow(r.json) : null
    },
    async list() {
      const r = await call('GET', '/tasks')
      if (!r || r.status !== 200 || !Array.isArray(r.json)) return null
      return r.json.map(parseRow).filter((x): x is TaskRow => x !== null)
    },
    async stop(taskId) {
      if (!safeId(taskId)) return false
      const r = await call('POST', `/tasks/${taskId}/stop`, { actor: 'worker_approval', ...(d.readToken() ? { token: d.readToken() as string } : {}), body: {} })
      return !!r && r.status >= 200 && r.status < 300
    },
  }
}

// ------------------------------------------------------------------------------------------------ the number of running tasks (a count, nothing else)
export interface RunningCount {
  start(): void
  stop(): void
  /** How many tasks are planning or running, or null when the service has not answered lately. */
  running(): { n: number; t: number } | null
}

export function createRunningCount(o: { list: () => Promise<TaskRow[] | null>; everyMs?: number; now?: () => number; setInterval?: (fn: () => void, ms: number) => unknown; clearInterval?: (h: unknown) => void }): RunningCount {
  const now = o.now ?? Date.now
  const setI = o.setInterval ?? ((fn, ms) => setInterval(fn, ms))
  const clearI = o.clearInterval ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  let last: { n: number; t: number } | null = null
  let handle: unknown = null
  const tick = (): void => {
    void o.list().then(
      (rows) => {
        last = rows === null ? null : { n: rows.filter((r) => r.state === 'running' || r.state === 'planning').length, t: now() }
      },
      () => {
        last = null
      },
    )
  }
  return {
    start() {
      if (handle !== null) return
      tick()
      handle = setI(tick, o.everyMs ?? 10_000)
    },
    stop() {
      if (handle !== null) clearI(handle)
      handle = null
    },
    running: () => last,
  }
}
