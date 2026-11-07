// Engine client: POST /events (batched, schema-valid, loopback only), kill calls, routine proposals. Best effort everywhere:
// the engine being down must never slow or break the desktop app, so events queue in memory (bounded) and retry quietly.
// Nothing sensitive is sent: events carry no free text, no URLs and no field values (see event.ts).
import { buildEvent, eventProblem, type EventInput, type Identity, type UnderstudyEvent } from './event'
import { DEFAULT_ENDPOINTS, isLoopbackUrl, type Endpoints } from './endpoints'
import { roleFromMemory } from './identity'

export type Log = (scope: string, ...args: unknown[]) => void

export interface EngineClientOptions {
  endpoints?: Pick<Endpoints, 'engine' | 'agent'>
  identity: Identity
  fetchImpl?: typeof fetch
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
  episodes: number | null
  touches: string[]
  never: string[]
  what: string
  howOften: string
}

export interface EngineClient {
  readonly identity: Identity
  setRole(role: string): void
  // Queue one event. Invalid events are dropped (and logged by reason, never content). Returns whether it was queued.
  emit(input: EventInput): boolean
  flush(): Promise<IngestResult | null>
  pending(): number
  // Kill switch calls to the engine (POST /kill) and the agent (POST /kill). Never throws.
  kill(): Promise<KillResult>
  clearKill(): Promise<KillResult>
  // GET /routines, trimmed to what a toast needs. Null when the engine is unreachable.
  routines(): Promise<RoutineProposal[] | null>
  // GET /queue?status=pending -> how many approvals wait in the morning queue. Null when the engine is unreachable.
  pendingQueue(): Promise<number | null>
  // GET /memory front matter -> role (best effort).
  syncRole(): Promise<string | null>
  // POST /routines/{id}/consent with a declining mode. The only consents the desktop ever sends are not_now and never.
  decline(id: string, mode: 'not_now' | 'never'): Promise<boolean>
  health(): Promise<boolean>
  dispose(): void
}

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
      const res = await doFetch(url, {
        method,
        headers: body === undefined ? undefined : { 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
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
    async pendingQueue() {
      const res = await http('GET', `${endpoints.engine}/queue?status=pending`)
      if (!res || res.status >= 300) return null
      const list = Array.isArray(res.json) ? res.json : isObj(res.json) && Array.isArray(res.json.data) ? res.json.data : null
      return list ? list.length : null
    },
    async syncRole() {
      const res = await http('GET', `${endpoints.engine}/memory`)
      if (!res || res.status >= 300 || !isObj(res.json)) return null
      const md = typeof res.json.markdown === 'string' ? res.json.markdown : isObj(res.json.data) && typeof res.json.data.markdown === 'string' ? res.json.data.markdown : ''
      const role = roleFromMemory(md)
      if (role) identity.role = role
      return role
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
