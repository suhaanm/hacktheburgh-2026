// The engine side over loopback: GET /attention/next, POST /attention/events, POST /attention/feedback. Best effort everywhere: the engine
// being down must never slow or break the desktop app, so every call answers null (or nothing) instead of throwing, and a notice simply
// does not appear. Only a loopback URL is ever used. Ids, enums and numbers only: nothing sensitive is sent.
import { parseNext, type AttentionEvent, type AttentionNext } from './types'
import { toQuery, type AttentionSignals } from './signals'

export type FeedbackEvent = 'shown' | 'followed' | 'dismissed' | 'ignored' | 'never' | 'opened' | 'deferred'

export interface SubmitResult {
  itemId: string | null
  show: boolean
  reason: string | null
  coalesced: boolean
}

export interface AttentionClient {
  next(signals: AttentionSignals, nowMs: number): Promise<AttentionNext | null>
  /** The passive counts and what is on screen; delivers nothing. */
  peek(): Promise<AttentionNext | null>
  /** Report an event. For a helpful-now event (a cue) `show` is the admission answer. Null when the engine did not answer. */
  submit(ev: AttentionEvent): Promise<SubmitResult | null>
  feedback(itemId: string, event: FeedbackEvent, seconds?: number): Promise<void>
}

export interface HttpClientOptions {
  baseUrl: string
  person: () => string | null
  fetchImpl?: typeof fetch
  timeoutMs?: number
  log?: (scope: string, ...args: unknown[]) => void
}

const isLoopback = (url: string): boolean => {
  try {
    const u = new URL(url)
    return u.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]', '::1'].includes(u.hostname)
  } catch {
    return false
  }
}

export function createHttpClient(o: HttpClientOptions): AttentionClient {
  const doFetch = o.fetchImpl ?? fetch
  const timeoutMs = o.timeoutMs ?? 2_000
  const log = o.log ?? (() => undefined)
  const base = o.baseUrl.replace(/\/+$/, '')

  async function call(method: 'GET' | 'POST', path: string, actor: string, body?: unknown): Promise<unknown | null> {
    if (!isLoopback(base)) return null
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), timeoutMs)
    try {
      const res = await doFetch(`${base}${path}`, {
        method,
        signal: ctl.signal,
        headers: method === 'POST' ? { 'Content-Type': 'application/json', 'X-Understudy-Actor': actor } : { 'X-Understudy-Actor': actor },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      if (!res.ok) {
        log('attention', `${method} ${path.split('?')[0]} answered ${res.status}`)
        return null
      }
      return await res.json()
    } catch (err) {
      log('attention', `${method} ${path.split('?')[0]} failed:`, err instanceof Error ? err.message : String(err))
      return null
    } finally {
      clearTimeout(timer)
    }
  }
  const personQ = () => {
    const p = o.person()
    return p ? `person=${encodeURIComponent(p)}` : ''
  }
  return {
    async next(signals, nowMs) {
      const p = personQ()
      if (!p) return null
      const raw = await call('GET', `/attention/next?${p}&${toQuery(signals, nowMs)}`, 'desktop')
      return raw === null ? null : parseNext(raw)
    },
    async peek() {
      const p = personQ()
      if (!p) return null
      const raw = await call('GET', `/attention/next?${p}&peek=1`, 'desktop')
      return raw === null ? null : parseNext(raw)
    },
    async submit(ev) {
      const p = personQ()
      if (!p) return null
      const raw = (await call('POST', `/attention/events?${p}`, 'desktop', ev)) as { item_id?: unknown; show?: unknown; coalesced?: unknown; decision?: { reason_code?: unknown } | null } | null
      if (!raw || typeof raw !== 'object') return null
      return {
        itemId: typeof raw.item_id === 'string' ? raw.item_id : null,
        show: raw.show === true,
        coalesced: raw.coalesced === true,
        reason: typeof raw.decision?.reason_code === 'string' ? raw.decision.reason_code.slice(0, 40) : null,
      }
    },
    async feedback(itemId, event, seconds) {
      const p = personQ()
      if (!p) return
      await call('POST', `/attention/feedback?${p}`, 'worker', { item_id: itemId, event, ...(seconds === undefined ? {} : { seconds: Math.max(0, seconds) }) })
    },
  }
}

/** A client that records what it was asked and answers from a script. For tests and storyboards. */
export function createFakeClient(script: { next?: AttentionNext[]; submit?: (ev: AttentionEvent) => SubmitResult | null } = {}) {
  const nexts = [...(script.next ?? [])]
  const calls = { next: [] as AttentionSignals[], peek: 0, submit: [] as AttentionEvent[], feedback: [] as Array<{ itemId: string; event: FeedbackEvent; seconds?: number }> }
  const client: AttentionClient = {
    async next(signals) {
      calls.next.push(signals)
      return nexts.length > 0 ? (nexts.shift() as AttentionNext) : null
    },
    async peek() {
      calls.peek += 1
      return null
    },
    async submit(ev) {
      calls.submit.push(ev)
      return script.submit ? script.submit(ev) : { itemId: 'i_fake', show: true, reason: 'shown_now', coalesced: false }
    },
    async feedback(itemId, event, seconds) {
      calls.feedback.push({ itemId, event, seconds })
    },
  }
  return { client, calls, push: (n: AttentionNext) => void nexts.push(n) }
}
