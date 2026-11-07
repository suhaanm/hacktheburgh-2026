// Adapted from google-gemini/gemini-live-api-examples — gemini-live-ephemeral-tokens-websocket/frontend/geminilive.js (socket setup and receive loop;
// the example has no reconnect logic) and from this project's earlier renderer/live/connection.ts. The socket now lives in the MAIN process.
//
// WebSocket transport for the Live API. Contract: connect() resolves after setupComplete. An unexpected drop is retried a couple of times,
// resuming with the latest resumption handle on the same token (a resumption is not a new use). After the retries run out onClosed fires
// with expected=false and the session ends; the caller falls back to text. The websocket URL has no credential: the ephemeral token goes in
// the `Authorization: Token ...` header. The ONLY code that calls `send()` is egress.ts (a static test enforces it).
import { LIVE_ENDPOINT_URL, decodeFrame, parseServerMessage, type LiveServerEvent } from './wire'

export interface SocketLike {
  readonly readyState: number
  binaryType: string
  send(data: string): void
  close(code?: number, reason?: string): void
  addEventListener(type: 'open' | 'message' | 'error' | 'close', listener: (ev: never) => void): void
}

export type SocketFactory = (url: string, init: { headers: Record<string, string> }) => SocketLike

/** The real factory: the runtime's WebSocket, which accepts a headers option on the server side (verified on Node 26 / undici 8). */
export const defaultSocketFactory: SocketFactory = (url, init) => new (WebSocket as unknown as new (u: string, o: { headers: Record<string, string> }) => SocketLike)(url, init)

export type ConnState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface CloseInfo {
  code: number
  reason: string
  // True when we asked for the close; false = the connection was lost and could not be recovered.
  expected: boolean
}

export interface ConnectionOptions {
  // The ephemeral token (never the key). Called once per connect; reconnects reuse the same token.
  getToken: () => Promise<string>
  buildSetup: (handle: string | null) => object
  onEvent: (e: LiveServerEvent) => void
  onReconnecting?: () => void
  onReconnected?: (info: { resumed: boolean }) => void
  onClosed: (info: CloseInfo) => void
  socketFactory?: SocketFactory
  // The endpoint; only the real Gemini endpoint, or a loopback ws:// URL for tests.
  url?: string
  maxReconnectAttempts?: number
  setupTimeoutMs?: number
  log?: (...a: unknown[]) => void
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function isAllowedLiveUrl(url: string): boolean {
  if (url.startsWith('wss://generativelanguage.googleapis.com/')) return true
  return /^ws:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?\//.test(url)
}

function withTimeout<T>(p: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), ms)
    p.then(
      (v) => {
        clearTimeout(timer)
        resolve(v)
      },
      (e: unknown) => {
        clearTimeout(timer)
        reject(e instanceof Error ? e : new Error(String(e)))
      },
    )
  })
}

export class LiveConnection {
  state: ConnState = 'idle'
  private sock: SocketLike | null = null
  private pending: SocketLike | null = null
  private handle: string | null = null
  private token: string | null = null
  private expectedClose = false
  private readonly factory: SocketFactory
  private readonly url: string
  private readonly log: (...a: unknown[]) => void

  constructor(private readonly opts: ConnectionOptions) {
    this.factory = opts.socketFactory ?? defaultSocketFactory
    this.url = opts.url ?? LIVE_ENDPOINT_URL
    if (!isAllowedLiveUrl(this.url)) throw new Error('the Live endpoint must be the Gemini service (or a loopback test server)')
    this.log = opts.log ?? (() => undefined)
  }

  get resumptionHandle(): string | null {
    return this.handle
  }

  async connect(): Promise<void> {
    this.state = 'connecting'
    try {
      this.token = await withTimeout(this.opts.getToken(), this.opts.setupTimeoutMs ?? 10_000, 'Live token request timed out')
      if (this.expectedClose) throw new Error('Live connection closed')
      this.sock = await this.openSocket(null)
    } catch (err) {
      this.state = 'closed'
      throw err
    }
    this.state = 'open'
  }

  /** Called by the egress choke point only. */
  send(message: object): boolean {
    const s = this.sock
    if (!s || s.readyState !== 1 || this.state !== 'open') return false
    s.send(JSON.stringify(message))
    return true
  }

  close(code = 1000, reason = 'client closed'): void {
    this.expectedClose = true
    this.state = 'closed'
    const s = this.sock
    const p = this.pending
    this.sock = null
    this.pending = null
    this.token = null
    for (const sock of [s, p]) {
      try {
        sock?.close(code, reason)
      } catch {
        /* already closed */
      }
    }
  }

  private openSocket(handle: string | null): Promise<SocketLike> {
    return new Promise<SocketLike>((resolve, reject) => {
      const token = this.token
      if (!token || this.expectedClose) {
        reject(new Error('Live connection closed'))
        return
      }
      const ws = this.factory(this.url, { headers: { Authorization: `Token ${token}` } })
      this.pending = ws
      ws.binaryType = 'arraybuffer'
      let ready = false
      let settled = false
      const fail = (why: string): void => {
        if (settled) return
        settled = true
        if (this.pending === ws) this.pending = null
        clearTimeout(timer)
        try {
          ws.close()
        } catch {
          /* ignore */
        }
        reject(new Error(why))
      }
      const timer = setTimeout(() => fail('Live setup timed out'), this.opts.setupTimeoutMs ?? 10_000)
      ws.addEventListener('open', () => {
        ws.send(JSON.stringify(this.opts.buildSetup(handle)))
      })
      ws.addEventListener('message', ((ev: { data: unknown }) => {
        const events = parseServerMessage(decodeFrame(ev.data))
        if (!ready) {
          if (events.some((e) => e.type === 'setupComplete')) {
            ready = true
            settled = true
            if (this.pending === ws) this.pending = null
            clearTimeout(timer)
            resolve(ws)
          }
          return // nothing legitimate precedes setupComplete
        }
        if (ws !== this.sock) return
        for (const e of events) this.route(e)
      }) as never)
      ws.addEventListener('error', (() => {
        if (!ready) fail('Live connection error')
      }) as never)
      ws.addEventListener('close', ((ev: { code: number; reason: string }) => {
        if (!ready) {
          fail(`Live connection closed before setup (${ev.code}${ev.reason ? `: ${String(ev.reason).slice(0, 80)}` : ''})`)
          return
        }
        this.onSocketClosed(ws, ev.code, String(ev.reason ?? ''))
      }) as never)
    })
  }

  private route(e: LiveServerEvent): void {
    if (e.type === 'resumptionUpdate' && e.resumable && e.handle) this.handle = e.handle
    else if (e.type === 'goAway') this.log('goAway', e.timeLeftMs) // a session here is at most 5 minutes; the server's limit is longer
    this.opts.onEvent(e)
  }

  private onSocketClosed(ws: SocketLike, code: number, reason: string): void {
    if (ws !== this.sock) return
    if (this.expectedClose || this.state === 'closed') {
      this.opts.onClosed({ code, reason, expected: true })
      return
    }
    this.log('socket lost', code, `handle=${this.handle ? 'yes' : 'none'}`)
    this.sock = null
    void this.reconnectLoop(code, reason)
  }

  private async reconnectLoop(code: number, reason: string): Promise<void> {
    this.state = 'reconnecting'
    this.opts.onReconnecting?.()
    const max = this.opts.maxReconnectAttempts ?? 2
    let lastError = `${code}${reason ? `: ${reason.slice(0, 80)}` : ''}`
    for (let attempt = 0; attempt < max; attempt++) {
      await sleep(Math.min(250 * 2 ** attempt, 2000))
      if (this.expectedClose) return
      try {
        const next = await this.openSocket(this.handle)
        if (this.expectedClose) {
          next.close(1000)
          return
        }
        this.sock = next
        this.state = 'open'
        this.opts.onReconnected?.({ resumed: this.handle !== null })
        return
      } catch (err) {
        lastError = err instanceof Error ? err.message : String(err)
        this.log('reconnect attempt failed', attempt)
      }
    }
    this.state = 'closed'
    this.opts.onClosed({ code, reason: `connection lost: ${lastError}`, expected: false })
  }
}
