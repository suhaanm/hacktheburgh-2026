// Engine client: POST /events (batched, schema-valid, loopback only), kill calls, routine proposals. Best effort everywhere:
// the engine being down must never slow or break the desktop app, so events queue in memory (bounded) and retry quietly.
// Nothing sensitive is sent: events carry no free text, no URLs and no field values (see event.ts).
import { buildEvent, eventProblem, isPerson, isRole, type EventInput, type Identity, type UnderstudyEvent } from './event'
import { DEFAULT_ENDPOINTS, isLoopbackUrl, type Endpoints } from './endpoints'
import { captureFromMemory, roleFromMemory } from './capture-consent'
import { parseCoachNext, type CoachDecision, type FeedbackOutcome, type FeedbackResult } from './coach-next'
import { parseCoachState, type CoachStateInfo } from './coach-state'
import { readServiceToken } from '../kill-file'

export type Log = (scope: string, ...args: unknown[]) => void

export interface EngineClientOptions {
  endpoints?: Pick<Endpoints, 'engine' | 'agent'>
  identity: Identity
  fetchImpl?: typeof fetch
  // data/.token, read for every release request (it rotates every boot). Default: the file under the shared data directory.
  readToken?: () => string | null
  log?: Log
  now?: () => Date
  // Flush when this many events are waiting, or after flushMs, whichever is first.
  batchSize?: number
  flushMs?: number
  // Oldest events are dropped past this many (the engine has been away for a long time).
  maxQueue?: number
  timeoutMs?: number
  // Test seams for timers.
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (handle: unknown) => void
}

// Release routes: the ones that let something run again or approve it. They need X-Understudy-Token (data/.token). Stop-type routes
// (POST /kill, /human-input, /run/{id}/stop) stay open on purpose: stopping must never need a secret.
const RELEASE_ROUTES: RegExp[] = [/\/kill\/clear$/, /\/queue\/[^/]+\/(approve|reject)$/, /\/routines\/[^/]+\/(consent|grants?)$/, /\/offhours\/consent$/, /\/privacy\/ledger\/clear$/, /\/resume$/]
export const isReleaseRoute = (method: string, url: string): boolean => {
  if (method === 'GET') return false
  try {
    const p = new URL(url).pathname
    return RELEASE_ROUTES.some((re) => re.test(p))
  } catch {
    return false
  }
}

export interface IngestResult {
  accepted: number
  rejected: Array<{ index: number; reason: string }>
}

export interface KillResult {
  engine: boolean
  agent: boolean
}

export interface RoutineProposal {
  id: string
  title: string
  status: string
  minutesPerWeek: number | null
  hoursSaved: [number, number] | null
  // The period `hoursSaved` covers (the engine's value.horizon_weeks), or null when it does not say.
  horizonWeeks: number | null
  episodes: number | null
  touches: string[]
  never: string[]
  what: string
  howOften: string
}

// What GET /memory tells the desktop app: who the events belong to, and whether the worker turned desk capture on.
export interface MemoryInfo {
  person: string | null
  role: string | null
  // True only when the Preferences section holds the line "Capture: times only" (see capture-consent.ts).
  captureTimesOnly: boolean
}

export interface EngineClient {
  readonly identity: Identity
  setRole(role: string): void
  setPerson(person: string): void
  // Drops events that were queued but not sent yet, for the given sources (used when capture consent is withdrawn).
  purge(source: UnderstudyEvent['source']): number
  // Queue one event. Invalid events are dropped (and logged by reason, never content). Returns whether it was queued.
  emit(input: EventInput): boolean
  flush(): Promise<IngestResult | null>
  pending(): number
  // Kill switch calls to the engine (POST /kill) and the agent (POST /kill). Never throws.
  kill(): Promise<KillResult>
  clearKill(): Promise<KillResult>
  // GET /routines, trimmed to what a toast needs. Null when the engine is unreachable.
  routines(): Promise<RoutineProposal[] | null>
  // GET /coach/state?person=: the task in progress and the chip fade. Null when unreachable.
  coachState(): Promise<CoachStateInfo | null>
  // GET /coach/next?person=: the coach brain's decision (what to do now, and which zone to point at). Null when unreachable.
  coachNext(): Promise<CoachDecision | null>
  // GET /events?partition=real&person=&since=: did the worker touch this capture zone (click, focus, tab, paste) at or after `sinceMs`?
  // That is how the desktop knows the element a ring pointed at was used. Null when the engine did not answer.
  touched(zone: string, sinceMs: number): Promise<boolean | null>
  // POST /coach/feedback: the worker's own response to a prompt (followed or dismissed). It updates their skill state; it is not
  // telemetry, so it is sent whatever the capture preference says.
  coachFeedback(decisionId: string, outcome: FeedbackOutcome): Promise<FeedbackResult>
  // GET /queue?status=pending -> how many approvals wait in the morning queue. Null when the engine is unreachable.
  pendingQueue(): Promise<number | null>
  // GET /identity (when the engine answers 200) and GET /memory: person, role and the capture preference. Null when the engine is unreachable or GET /memory is not usable.
  memory(): Promise<MemoryInfo | null>
  // memory() applied to the identity: person and role from the memory file when present. Returns what it read.
  syncIdentity(): Promise<MemoryInfo | null>
  // POST /routines/{id}/consent with a declining mode. The only consents the desktop ever sends are not_now and never.
  decline(id: string, mode: 'not_now' | 'never'): Promise<boolean>
  health(): Promise<boolean>
  dispose(): void
}

// What counts as the worker using an element a ring pointed at.
const TOUCH_TYPES = new Set(['click', 'focus', 'tab', 'paste'])
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, 8) : [])

/** The shape of GET /routines (docs/API_CONTRACT.md), reduced to a proposal card's essentials. */
export function toProposal(raw: unknown): RoutineProposal | null {
  if (!isObj(raw) || typeof raw.id !== 'string' || typeof raw.status !== 'string') return null
  const value = isObj(raw.value) ? raw.value : {}
  const hours = Array.isArray(value.hours_saved) && value.hours_saved.length === 2 ? [num(value.hours_saved[0]), num(value.hours_saved[1])] : null
  const prop = isObj(raw.proposal) ? raw.proposal : {}
  return {
    id: raw.id,
    title: typeof raw.title === 'string' ? raw.title : raw.id,
    status: raw.status,
    minutesPerWeek: num(raw.minutes_per_week),
    hoursSaved: hours && hours[0] !== null && hours[1] !== null ? [hours[0], hours[1]] : null,
    horizonWeeks: num(value.horizon_weeks),
    episodes: num(raw.episodes),
    touches: strs(raw.touches),
    never: strs(raw.never),
    what: typeof prop.what === 'string' ? prop.what : '',
    howOften: typeof prop.how_often === 'string' ? prop.how_often : '',
  }
}

export function createEngineClient(opts: EngineClientOptions): EngineClient {
  const endpoints = { engine: opts.endpoints?.engine ?? DEFAULT_ENDPOINTS.engine, agent: opts.endpoints?.agent ?? DEFAULT_ENDPOINTS.agent }
  for (const url of [endpoints.engine, endpoints.agent]) if (!isLoopbackUrl(url)) throw new Error('the engine and agent must be on this machine (127.0.0.1)')
  const doFetch = opts.fetchImpl ?? ((input, init) => fetch(input, init))
  const log: Log = opts.log ?? (() => undefined)
  const now = opts.now ?? (() => new Date())
  const batchSize = opts.batchSize ?? 20
  const flushMs = opts.flushMs ?? 2000
  const maxQueue = opts.maxQueue ?? 500
  const timeoutMs = opts.timeoutMs ?? 2000
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const identity: Identity = { ...opts.identity }

  let queue: UnderstudyEvent[] = []
  let timer: unknown = null
  let inflight: Promise<IngestResult | null> | null = null
  let disposed = false
  let failures = 0
  let dropped = 0

  async function http(method: 'GET' | 'POST', url: string, body?: unknown, ms = timeoutMs): Promise<{ status: number; json: unknown } | null> {
    const controller = new AbortController()
    const t = setTimeout(() => controller.abort(), ms)
    try {
      // Every write says it is JSON and that the worker's own app sent it; release routes also carry the token. No token file for a
      // release route: nothing is sent and the caller sees "not reachable" (the existing state), never a silent half-call.
      const headers: Record<string, string> = {}
      if (method !== 'GET') {
        headers['content-type'] = 'application/json'
        headers['x-understudy-actor'] = 'worker'
        if (isReleaseRoute(method, url)) {
          const token = (opts.readToken ?? (() => readServiceToken()))()
          if (!token) {
            log('engine', 'no data/.token: a release route was not sent')
            return null
          }
          headers['x-understudy-token'] = token
        }
      }
      const res = await doFetch(url, {
        method,
        headers,
        body: method === 'GET' ? undefined : JSON.stringify(body ?? {}),
        signal: controller.signal,
      })
      let json: unknown = null
      try {
        json = await res.json()
      } catch {
        json = null
      }
      return { status: res.status, json }
    } catch {
      return null
    } finally {
      clearTimeout(t)
    }
  }

  const schedule = (): void => {
    if (timer !== null || disposed || queue.length === 0) return
    // Back off while the engine is away (2 s, 4 s, ... up to 30 s).
    const wait = Math.min(30_000, flushMs * 2 ** Math.min(failures, 4))
    timer = setT(() => {
      timer = null
      void flush()
    }, wait)
  }

  async function flush(): Promise<IngestResult | null> {
    if (inflight) return inflight
    if (queue.length === 0) return null
    const batch = queue.splice(0, queue.length)
    inflight = (async () => {
      const res = await http('POST', `${endpoints.engine}/events`, batch)
      if (!res || res.status >= 500) {
        failures += 1
        queue = [...batch, ...queue].slice(-maxQueue)
        return null
      }
      failures = 0
      if (res.status >= 400) {
        // The engine understood the request and refused it: retrying the same events cannot help.
        log('engine', `events refused with HTTP ${res.status}; ${batch.length} dropped`)
        return null
      }
      const body = isObj(res.json) ? res.json : {}
      const rejected = Array.isArray(body.rejected) ? (body.rejected as unknown[]).filter(isObj).map((r) => ({ index: num(r.index) ?? -1, reason: String(r.reason ?? '').slice(0, 80) })) : []
      if (rejected.length) log('engine', `${rejected.length} of ${batch.length} events rejected: ${rejected.slice(0, 3).map((r) => r.reason).join('; ')}`)
      return { accepted: num(body.accepted) ?? batch.length - rejected.length, rejected }
    })().finally(() => {
      inflight = null
      schedule()
    })
    return inflight
  }

  return {
    identity,
    setRole(role) {
      identity.role = role
    },
    setPerson(person) {
      if (isPerson(person)) identity.person = person
    },
    purge(source) {
      const before = queue.length
      queue = queue.filter((e) => e.source !== source)
      return before - queue.length
    },
    emit(input) {
      if (disposed) return false
      const ev = buildEvent(identity, input, now())
      const problem = eventProblem(ev)
      if (problem) {
        log('engine', `event dropped (${ev.type}): ${problem}`)
        return false
      }
      queue.push(ev)
      if (queue.length > maxQueue) {
        queue.splice(0, queue.length - maxQueue)
        dropped += 1
        if (dropped === 1 || dropped % 50 === 0) log('engine', 'event queue full; the oldest events were dropped')
      }
      if (queue.length >= batchSize) void flush()
      else schedule()
      return true
    },
    flush,
    pending: () => queue.length,

    async kill() {
      const [engine, agent] = await Promise.all([http('POST', `${endpoints.engine}/kill`, {}, 1500), http('POST', `${endpoints.agent}/kill`, {}, 1500)])
      return { engine: !!engine && engine.status < 300, agent: !!agent && agent.status < 300 }
    },
    async clearKill() {
      const engine = await http('POST', `${endpoints.engine}/kill/clear`, {}, 1500)
      return { engine: !!engine && engine.status < 300, agent: false }
    },

    async routines() {
      const res = await http('GET', `${endpoints.engine}/routines`)
      if (!res || res.status >= 300) return null
      const list = Array.isArray(res.json) ? res.json : isObj(res.json) && Array.isArray(res.json.data) ? res.json.data : []
      return list.map(toProposal).filter((p): p is RoutineProposal => p !== null)
    },
    async coachState() {
      const res = await http('GET', `${endpoints.engine}/coach/state?person=${encodeURIComponent(identity.person)}`)
      if (!res || res.status >= 300) return null
      return parseCoachState(res.json)
    },
    async coachNext() {
      const res = await http('GET', `${endpoints.engine}/coach/next?person=${encodeURIComponent(identity.person)}`)
      if (!res || res.status >= 300) return null
      return parseCoachNext(res.json)
    },
    async touched(zone, sinceMs) {
      const q = new URLSearchParams({ partition: 'real', person: identity.person, since: new Date(sinceMs).toISOString(), limit: '200' })
      const res = await http('GET', `${endpoints.engine}/events?${q.toString()}`, undefined, 1500)
      if (!res || res.status >= 300 || !isObj(res.json) || !Array.isArray(res.json.events)) return null
      return res.json.events.some((ev) => isObj(ev) && typeof ev.type === 'string' && TOUCH_TYPES.has(ev.type) && isObj(ev.meta) && ev.meta.zone === zone && Date.parse(String(ev.t)) >= sinceMs)
    },
    async coachFeedback(decisionId, outcome) {
      const res = await http('POST', `${endpoints.engine}/coach/feedback`, { decision_id: decisionId, outcome })
      if (!res || res.status >= 300) return { ok: false, recorded: null, note: null }
      const body = isObj(res.json) ? res.json : {}
      return { ok: true, recorded: typeof body.recorded === 'boolean' ? body.recorded : null, note: typeof body.note === 'string' ? body.note.slice(0, 80) : null }
    },
    async pendingQueue() {
      const res = await http('GET', `${endpoints.engine}/queue?status=pending`)
      if (!res || res.status >= 300) return null
      const list = Array.isArray(res.json) ? res.json : isObj(res.json) && Array.isArray(res.json.data) ? res.json.data : null
      return list ? list.length : null
    },
    async memory() {
      // GET /identity -> {person, role} wins when the engine answers 200 (also tolerated: wrapped in {data}).
      const idRes = await http('GET', `${endpoints.engine}/identity`)
      const idBody = idRes && idRes.status < 300 && isObj(idRes.json) ? (isObj(idRes.json.data) ? idRes.json.data : idRes.json) : null
      const idPerson = idBody && typeof idBody.person === 'string' && isPerson(idBody.person) ? idBody.person : null
      const idRole = idBody && typeof idBody.role === 'string' && isRole(idBody.role) ? idBody.role : null
      // GET /memory: the capture preference, and a fallback for the person (when the engine adds it) and the role (front matter).
      const res = await http('GET', `${endpoints.engine}/memory`)
      if (!res || res.status >= 300 || !isObj(res.json)) return null
      const body = isObj(res.json.data) ? res.json.data : res.json
      const markdown = typeof body.markdown === 'string' ? body.markdown : ''
      const memPerson = typeof body.person === 'string' && isPerson(body.person) ? body.person : null
      return { person: idPerson ?? memPerson, role: idRole ?? roleFromMemory(markdown), captureTimesOnly: captureFromMemory(markdown) }
    },
    async syncIdentity() {
      const info = await this.memory()
      if (!info) return null
      if (info.person) identity.person = info.person
      if (info.role) identity.role = info.role
      return info
    },
    async decline(id, mode) {
      const res = await http('POST', `${endpoints.engine}/routines/${encodeURIComponent(id)}/consent`, { mode, irreversible_unattended: [], typed_confirm: '' })
      return !!res && res.status < 300
    },
    async health() {
      const res = await http('GET', `${endpoints.engine}/health`, undefined, 1000)
      return !!res && res.status < 300
    },
    dispose() {
      disposed = true
      if (timer !== null) clearT(timer)
      timer = null
    },
  }
}
