// Is an agent acting for the person right now? A read-only look at the agent service (GET /health -> supervisor.state, and GET
// /agents/runs when the runtime flag has that route on), so the Stop all pill shows during background and shadow runs too.
//   acting  = the supervisor is `running`, or any listed run is `running`
// Any failure (the service is down, a timeout, a bad body) never turns the pill on and never turns an already-showing pill off: the
// last known answer stays. Quick polling (2 s) while the person is at the machine or something is acting, 10 s when it is quiet.
import { RUN_MAX_AGE_MS } from '../knack/pill-state'
import { isLoopbackUrl } from './endpoints'

export interface AgentActivityDeps {
  agentUrl: string
  fetchImpl?: typeof fetch
  onChange(acting: boolean): void
  // Every poll's raw answers (parsed GET /health and GET /agents/runs, null when a call failed), for readers that need more than acting or not (the Knack pill).
  onSample?(sample: { health: unknown; runs: unknown }): void
  // Seconds since the person last touched the keyboard or mouse (powerMonitor.getSystemIdleTime); absent means "unknown: stay quick".
  idleSeconds?: () => number
  now?: () => number
  fastMs?: number
  slowMs?: number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  timeoutMs?: number
}

export interface AgentActivity {
  acting(): boolean
  poll(): Promise<void>
  dispose(): void
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/**
 * A run record the service lists as "running" that began longer ago than any run can last (a whole run is capped at 15 minutes) is a ghost: a record a dead process left on disk
 * with its last state. It is not work, so it must not read as an agent acting (which would keep the Stop all pill up, hold back Cue and keep Hey Knack asleep for ever).
 */
const isGhost = (r: Record<string, unknown>, now: number): boolean => {
  const started = typeof r.started === 'string' ? Date.parse(r.started) : Number.NaN
  return Number.isFinite(started) && now - started > RUN_MAX_AGE_MS
}

/** Pure: what the two answers say. `null` means "could not tell" (keep the last answer). */
export function actingFrom(health: unknown, runs: unknown, now: number = Date.now()): boolean | null {
  let known = false
  let acting = false
  if (isObj(health) && isObj(health.supervisor) && typeof health.supervisor.state === 'string') {
    known = true
    if (health.supervisor.state === 'running') acting = true
  }
  const list = Array.isArray(runs) ? runs : isObj(runs) && Array.isArray(runs.data) ? runs.data : null
  if (list) {
    known = true
    if (list.some((r) => isObj(r) && r.state === 'running' && !isGhost(r, now))) acting = true
  }
  return known ? acting : null
}

export function createAgentActivity(deps: AgentActivityDeps): AgentActivity {
  const doFetch = deps.fetchImpl ?? fetch
  const now = deps.now ?? Date.now
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const fast = deps.fastMs ?? 2000
  const slow = deps.slowMs ?? 10_000
  const base = isLoopbackUrl(deps.agentUrl) ? deps.agentUrl.replace(/\/+$/, '') : null
  let last = false
  let lastActingAt = 0
  let timer: unknown = null
  let disposed = false

  const get = async (path: string): Promise<unknown | null> => {
    if (!base) return null
    const controller = new AbortController()
    const t = setTimeout(() => controller.abort(), deps.timeoutMs ?? 1500)
    try {
      const res = await doFetch(`${base}${path}`, { signal: controller.signal })
      if (!res.ok) return null
      return (await res.json()) as unknown
    } catch {
      return null
    } finally {
      clearTimeout(t)
    }
  }

  const poll = async (): Promise<void> => {
    const [health, runs] = await Promise.all([get('/health'), get('/agents/runs')])
    deps.onSample?.({ health, runs })
    const answer = actingFrom(health, runs, now())
    if (answer !== null && answer !== last) {
      last = answer
      deps.onChange(answer)
    }
    if (answer) lastActingAt = now()
  }

  const next = (): number => {
    const recentlyActing = last || now() - lastActingAt < 30_000
    const atMachine = deps.idleSeconds ? deps.idleSeconds() < 60 : true
    return recentlyActing || atMachine ? fast : slow
  }
  const loop = (): void => {
    if (disposed) return
    timer = setT(() => {
      void poll().finally(loop)
    }, next())
  }
  void poll().finally(loop)

  return {
    acting: () => last,
    poll,
    dispose() {
      disposed = true
      if (timer !== null) clearT(timer)
    },
  }
}
