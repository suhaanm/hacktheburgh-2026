// The agent service's task events for the background agent pills (task API contract v1): one connection to GET /tasks/events on the loopback address, which sends a snapshot
// first (the newest tasks), then task_started, task_progress and task_finished (each carries the whole row: upsert by task_id), and a heartbeat every 10 seconds. Twenty-five
// seconds without a byte is a dead connection: it is dropped and opened again, and the fresh snapshot replaces what was held. If the service cannot be reached for that long the
// pills are told, so none of them says "working" about work nobody can see. A service without the route (404) is asked again only every half minute.
//
// Also: stopping a task from its pill (POST /tasks/{id}/stop, as the worker). The service address is checked to be this machine's loopback; nothing here reads a prompt or an output.
import { createSseParser } from './sse'

export const SILENCE_MS = 25_000
export const RETRY = { firstMs: 1000, maxMs: 15_000, noRouteMs: 30_000 } as const
/** While the stream is down the list is read with GET /tasks this often. */
export const POLL_MS = 3000

export interface TasksClientDeps {
  /** The agent service's base address, e.g. http://127.0.0.1:7710 (loopback only). */
  base: string
  /** The whole list as it is now (rows as the service sent them), after every change. */
  onTasks: (rows: unknown[]) => void
  /** The service could not be reached for SILENCE_MS: what was held is no longer known. */
  onLost: () => void
  fetchFn?: (url: string, init: { headers: Record<string, string>; signal: AbortSignal }) => Promise<{
    ok: boolean
    status: number
    body: { getReader(): { read(): Promise<{ done: boolean; value?: Uint8Array }>; cancel(): Promise<void> } } | null
    /** The whole body as JSON (the GET /tasks fallback). */
    json?: () => Promise<unknown>
  }>
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  now?: () => number
  log?: (...a: unknown[]) => void
}

export interface TasksClient {
  stop(): void
}

const isLoopback = (base: string): boolean => {
  try {
    const u = new URL(base)
    return u.protocol === 'http:' && (u.hostname === '127.0.0.1' || u.hostname === 'localhost' || u.hostname === '[::1]')
  } catch {
    return false
  }
}

const rowId = (row: unknown): string | null => (typeof row === 'object' && row !== null && typeof (row as { task_id?: unknown }).task_id === 'string' ? (row as { task_id: string }).task_id : null)

export function connectTaskEvents(d: TasksClientDeps): TasksClient {
  const log = d.log ?? (() => undefined)
  if (!isLoopback(d.base)) {
    log('tasks', 'refusing a service address that is not this machine')
    return { stop: () => undefined }
  }
  const setT = d.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = d.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const doFetch = d.fetchFn ?? ((url, init) => fetch(url, init) as never)
  const now = d.now ?? Date.now
  const byId = new Map<string, unknown>()
  let stopped = false
  let ctrl: AbortController | null = null
  let silence: unknown = null
  let retry: unknown = null
  let lostTimer: unknown = null
  let backoff: number = RETRY.firstMs
  let lastByteAt = now()
  let poll: unknown = null
  let polling = false

  const publish = (): void => d.onTasks([...byId.values()])

  const armSilence = (): void => {
    if (silence !== null) clearT(silence)
    silence = setT(() => {
      log('tasks', 'no word from the service for 25 s: reconnecting')
      ctrl?.abort()
    }, SILENCE_MS)
  }
  const armLost = (): void => {
    if (lostTimer !== null) return
    lostTimer = setT(() => {
      lostTimer = null
      byId.clear()
      d.onLost()
    }, SILENCE_MS)
  }
  const connected = (): void => {
    if (lostTimer !== null) clearT(lostTimer)
    lostTimer = null
    backoff = RETRY.firstMs
  }

  // While the stream is down the list is read every 3 s with GET /tasks (the service answers it even when the stream cannot be had), so a pill is neither stuck nor missing.
  const rowsOf = (body: unknown): unknown[] | null => (Array.isArray(body) ? body : Array.isArray((body as { tasks?: unknown } | null)?.tasks) ? ((body as { tasks: unknown[] }).tasks) : null)
  const pollOnce = async (): Promise<void> => {
    if (polling || stopped) return
    polling = true
    try {
      const res = await doFetch(`${d.base}/tasks`, { headers: { accept: 'application/json' }, signal: new AbortController().signal })
      const rows = res.ok && res.json ? rowsOf(await res.json()) : null
      if (rows === null) throw new Error(`status ${res.status}`)
      connected()
      byId.clear()
      for (const r of rows) if (rowId(r)) byId.set(rowId(r)!, r)
      publish()
    } catch {
      armLost()
    } finally {
      polling = false
    }
  }
  const startPolling = (): void => {
    if (poll !== null || stopped) return
    void pollOnce()
    const tick = (): void => {
      poll = setT(() => {
        void pollOnce().then(() => {
          if (poll !== null && !stopped) tick()
        })
      }, POLL_MS)
    }
    tick()
  }
  const stopPolling = (): void => {
    if (poll !== null) clearT(poll)
    poll = null
  }

  const open = async (): Promise<void> => {
    if (stopped) return
    ctrl = new AbortController()
    const parser = createSseParser()
    let wait: number = backoff
    try {
      const res = await doFetch(`${d.base}/tasks/events`, { headers: { accept: 'text/event-stream' }, signal: ctrl.signal })
      if (res.status === 404) {
        wait = RETRY.noRouteMs // this service has no task events yet
      } else if (!res.ok || !res.body) {
        throw new Error(`status ${res.status}`)
      } else {
        connected()
        stopPolling()
        armSilence()
        const reader = res.body.getReader()
        const text = new TextDecoder()
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          lastByteAt = now()
          armSilence()
          for (const ev of parser.push(text.decode(value, { stream: true }))) {
            let body: unknown
            try {
              body = JSON.parse(ev.data)
            } catch {
              continue
            }
            if (ev.event === 'snapshot') {
              byId.clear() // a fresh snapshot replaces what was held
              const rows = (body as { tasks?: unknown })?.tasks
              if (Array.isArray(rows)) for (const r of rows) if (rowId(r)) byId.set(rowId(r)!, r)
              publish()
            } else if (ev.event === 'task_started' || ev.event === 'task_progress' || ev.event === 'task_finished') {
              const id = rowId(body)
              if (id) {
                byId.set(id, body)
                publish()
              }
            } // heartbeat, and anything else: only the byte counted
          }
        }
        wait = backoff
      }
    } catch (err) {
      if (!stopped) log('tasks', 'connection ended:', err instanceof Error ? err.message : String(err))
      armLost()
      wait = backoff
      backoff = Math.min(RETRY.maxMs, backoff * 2)
    } finally {
      if (silence !== null) clearT(silence)
      silence = null
    }
    if (stopped) return
    startPolling() // the stream is down: read the list with GET /tasks meanwhile
    if (wait === RETRY.noRouteMs) armLost()
    retry = setT(() => void open(), wait)
  }
  void open()

  return {
    stop() {
      stopped = true
      ctrl?.abort()
      for (const h of [silence, retry, lostTimer, poll]) if (h !== null) clearT(h)
      silence = retry = lostTimer = poll = null
      void lastByteAt
    },
  }
}

/** Stops one task as the worker (the service checks the actor; no token is needed for this call). Resolves whether the service took it. */
export async function stopTask(base: string, taskId: string, fetchFn: (url: string, init: { method: string; headers: Record<string, string>; body: string }) => Promise<{ ok: boolean }> = (u, i) => fetch(u, i)): Promise<boolean> {
  if (!isLoopback(base) || !/^tk_[A-Za-z0-9]{4,24}$/.test(taskId)) return false
  try {
    return (await fetchFn(`${base}/tasks/${taskId}/stop`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: '{}' })).ok
  } catch {
    return false
  }
}
