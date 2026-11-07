// Awareness events for POST /awareness/events (packages/schema/awareness.schema.json). Numbers and closed enums only: no coordinates,
// no titles, no text, no pixels. A small mirror of the schema checks lives here (a test compares it with the file through ajv), and
// the sink queues events in memory (bounded) and posts them in batches to the engine on this machine, quietly retrying.
import { randomUUID } from 'node:crypto'
import { APP_KINDS, BLOCKERS, TASK_PHASES, TRIGGER_REASONS, ZONE_RE, fin, inList, isObj, type AppKindOrUnknown, type CursorWindowFeatures, type GlanceResult, type TriggerReason } from './types'
import { parseBox } from './glance-result'

export interface AwarenessCursor {
  dwell_s: number
  dwell_zone: string | null
  wander: number
  back_forth: number
  zone_a: string | null
  zone_b: string | null
  speed_bursts: number
  idle_gap_s: number
  clicks: number | null
}

export interface AwarenessEvent {
  schema: 1
  id: string
  t: string
  origin: 'real' | 'synthetic'
  person: string
  role: string
  type: 'window' | 'glance'
  window_s?: number
  app_kind?: AppKindOrUnknown
  sys_idle_s?: number
  cursor?: AwarenessCursor
  trigger?: TriggerReason
  glance?: GlanceResult
}

export interface Identity {
  person: string
  role: string
}

const PERSON_RE = /^p_[a-z0-9]{2,16}$/
const ROLE_RE = /^[a-z][a-z0-9-]{1,40}$/

/** Builds a window event. dwell_anchor (a position bucket used only for loop detection) is deliberately not copied. */
export function windowEvent(id: Identity, f: CursorWindowFeatures, args: { t: Date; appKind: AppKindOrUnknown; sysIdleS: number | null }, eventId: string = randomUUID()): AwarenessEvent {
  const { dwell_anchor: _anchor, window_s, ...cursor } = f
  return {
    schema: 1,
    id: eventId,
    t: args.t.toISOString(),
    origin: 'real',
    person: id.person,
    role: id.role,
    type: 'window',
    window_s,
    app_kind: args.appKind,
    ...(args.sysIdleS !== null && Number.isFinite(args.sysIdleS) ? { sys_idle_s: Math.round(Math.max(0, args.sysIdleS) * 10) / 10 } : {}),
    cursor,
  }
}

export function glanceEvent(id: Identity, trigger: TriggerReason, glance: GlanceResult, t: Date, eventId: string = randomUUID()): AwarenessEvent {
  return { schema: 1, id: eventId, t: t.toISOString(), origin: 'real', person: id.person, role: id.role, type: 'glance', trigger, glance }
}

const zoneOrNull = (v: unknown): boolean => v === null || (typeof v === 'string' && ZONE_RE.test(v))
const inRange = (v: unknown, lo: number, hi: number): v is number => fin(v) && v >= lo && v <= hi
const intIn = (v: unknown, lo: number, hi: number): boolean => inRange(v, lo, hi) && Number.isInteger(v)

/** Why the engine would reject this event, or null. Mirrors awareness.schema.json (a test checks the two agree). */
export function awarenessEventProblem(e: unknown): string | null {
  if (!isObj(e)) return 'not an object'
  const allowed = new Set(['schema', 'id', 't', 'origin', 'person', 'role', 'type', 'window_s', 'app_kind', 'sys_idle_s', 'cursor', 'trigger', 'glance'])
  for (const k of Object.keys(e)) if (!allowed.has(k)) return `unknown key ${k}`
  if (e.schema !== 1) return 'schema must be 1'
  if (typeof e.id !== 'string' || e.id.length < 8 || e.id.length > 64) return 'bad id'
  if (typeof e.t !== 'string' || Number.isNaN(Date.parse(e.t))) return 'bad time'
  if (e.origin !== 'real' && e.origin !== 'synthetic') return 'bad origin'
  if (typeof e.person !== 'string' || !PERSON_RE.test(e.person)) return 'bad person'
  if (typeof e.role !== 'string' || !ROLE_RE.test(e.role)) return 'bad role'
  if (e.sys_idle_s !== undefined && !inRange(e.sys_idle_s, 0, 86400)) return 'bad sys_idle_s'
  if (e.type === 'window') {
    if (!inRange(e.window_s, 0.5, 30)) return 'bad window_s'
    if (e.app_kind !== 'unknown' && !inList(APP_KINDS, e.app_kind)) return 'bad app_kind'
    if (e.glance !== undefined || e.trigger !== undefined) return 'a window event carries no glance'
    const c = e.cursor
    if (!isObj(c)) return 'missing cursor'
    const keys = ['dwell_s', 'dwell_zone', 'wander', 'back_forth', 'zone_a', 'zone_b', 'speed_bursts', 'idle_gap_s', 'clicks']
    if (Object.keys(c).some((k) => !keys.includes(k)) || keys.some((k) => !(k in c))) return 'bad cursor keys'
    if (!inRange(c.dwell_s, 0, 30) || !inRange(c.wander, 1, 20) || !inRange(c.idle_gap_s, 0, 30)) return 'bad cursor numbers'
    if (!intIn(c.back_forth, 0, 30) || !intIn(c.speed_bursts, 0, 30)) return 'bad cursor counts'
    if (c.clicks !== null && !intIn(c.clicks, 0, 200)) return 'bad clicks'
    if (!zoneOrNull(c.dwell_zone) || !zoneOrNull(c.zone_a) || !zoneOrNull(c.zone_b)) return 'bad zone'
    return null
  }
  if (e.type === 'glance') {
    if (e.cursor !== undefined || e.window_s !== undefined) return 'a glance event carries no cursor'
    if (e.app_kind !== undefined && e.app_kind !== 'unknown' && !inList(APP_KINDS, e.app_kind)) return 'bad app_kind'
    if (!inList(TRIGGER_REASONS, e.trigger)) return 'bad trigger'
    const g = e.glance
    if (!isObj(g)) return 'missing glance'
    const gk = ['app_kind', 'task_phase', 'blocker', 'confidence', 'box_2d']
    if (Object.keys(g).some((k) => !gk.includes(k))) return 'unknown glance key'
    if (g.app_kind !== null && !inList(APP_KINDS, g.app_kind)) return 'bad glance app_kind'
    if (g.task_phase !== null && !inList(TASK_PHASES, g.task_phase)) return 'bad task_phase'
    if (g.blocker !== null && !inList(BLOCKERS, g.blocker)) return 'bad blocker'
    if (!inRange(g.confidence, 0, 1)) return 'bad confidence'
    if (g.box_2d !== undefined && !(Array.isArray(g.box_2d) && g.box_2d.every((n) => intIn(n, 0, 1000)) && parseBox(g.box_2d))) return 'bad box_2d'
    return null
  }
  return 'bad type'
}

// ------------------------------------------------------------------------------------------------ sink
export type PostFn = (url: string, body: unknown) => Promise<{ status: number } | null>

export interface AwarenessSinkOptions {
  engineUrl: string
  post: PostFn
  batchSize?: number
  flushMs?: number
  maxQueue?: number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface AwarenessSink {
  emit(e: AwarenessEvent): boolean
  flush(): Promise<number>
  pending(): number
  dropped(): number
  dispose(): void
}

export function createAwarenessSink(opts: AwarenessSinkOptions): AwarenessSink {
  const batchSize = opts.batchSize ?? 15
  const flushMs = opts.flushMs ?? 10_000
  const maxQueue = opts.maxQueue ?? 600
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  let queue: AwarenessEvent[] = []
  let timer: unknown = null
  let inflight: Promise<number> | null = null
  let failures = 0
  let dropped = 0
  let disposed = false

  const schedule = (): void => {
    if (timer !== null || disposed || queue.length === 0) return
    const wait = Math.min(60_000, flushMs * 2 ** Math.min(failures, 3))
    timer = setT(() => {
      timer = null
      void flush()
    }, wait)
  }

  async function flush(): Promise<number> {
    if (inflight) return inflight
    if (queue.length === 0) return 0
    const batch = queue.splice(0, queue.length)
    inflight = (async () => {
      let res: { status: number } | null = null
      try {
        res = await opts.post(`${opts.engineUrl}/awareness/events`, batch)
      } catch {
        res = null
      }
      if (!res || res.status >= 500) {
        failures++
        queue = [...batch, ...queue].slice(-maxQueue)
        return 0
      }
      failures = 0
      // 404 means the layer is off on the engine side, 4xx that it refused: retrying the same events cannot help.
      if (res.status >= 400) {
        dropped += batch.length
        opts.log?.('awareness', `events refused with HTTP ${res.status}; ${batch.length} dropped`)
        return 0
      }
      return batch.length
    })().finally(() => {
      inflight = null
      schedule()
    })
    return inflight
  }

  return {
    emit(e) {
      if (disposed) return false
      const problem = awarenessEventProblem(e)
      if (problem) {
        opts.log?.('awareness', `event dropped: ${problem}`)
        return false
      }
      queue.push(e)
      if (queue.length > maxQueue) {
        queue.splice(0, queue.length - maxQueue)
        dropped++
      }
      if (queue.length >= batchSize) void flush()
      else schedule()
      return true
    },
    flush,
    pending: () => queue.length,
    dropped: () => dropped,
    dispose() {
      disposed = true
      if (timer !== null) clearT(timer)
      timer = null
      queue = []
    },
  }
}

/** A fetch-based POST to a loopback URL only, with a timeout. Never logs the body. */
export function createLoopbackPost(opts: { fetchImpl?: typeof fetch; timeoutMs?: number; isLoopback: (url: string) => boolean }): PostFn {
  const doFetch = opts.fetchImpl ?? ((i, init) => fetch(i, init))
  return async (url, body) => {
    if (!opts.isLoopback(url)) return null
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), opts.timeoutMs ?? 2000)
    try {
      const res = await doFetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal })
      return { status: res.status }
    } catch {
      return null
    } finally {
      clearTimeout(t)
    }
  }
}
