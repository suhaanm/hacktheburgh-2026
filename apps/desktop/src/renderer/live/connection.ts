// Adapted from google-gemini/gemini-live-api-examples — gemini-live-ephemeral-tokens-websocket/frontend/geminilive.js (socket setup/receive; the example has no reconnect logic)
// WebSocket transport for the Live API with transparent session resumption.
//
// Contract: connect() resolves after setupComplete. Afterwards the connection survives GoAway (the socket is replaced
// when the session is resumable, using the latest resumption handle) and unexpected drops (retry with backoff, resuming
// when a handle exists). After the retries run out onClosed fires with expected=false. Callers only ever see events.
import { decodeFrame, liveUrl, parseServerMessage, type LiveAuth, type LiveServerEvent } from './wire'

export type ConnState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface CloseInfo {
  code: number
  reason: string
  // True when we asked for the close; false = the connection was lost and could not be recovered.
  expected: boolean
}

export interface ConnectionOptions {
  getAuth: () => Promise<LiveAuth>
  // Full setup message for the given resumption handle (null = brand-new session).
  buildSetup: (handle: string | null) => object
  onEvent: (e: LiveServerEvent) => void
  onReconnecting?: (why: 'goaway' | 'dropped') => void
  onReconnected?: (info: { resumed: boolean }) => void
  onClosed: (info: CloseInfo) => void
  WebSocketImpl?: typeof WebSocket
  maxReconnectAttempts?: number
  setupTimeoutMs?: number
  log?: (...a: unknown[]) => void
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

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
  private sock: WebSocket | null = null
  private handle: string | null = null
  private resumable = false
  private expectedClose = false
  private superseded = new WeakSet<WebSocket>()
  private handingOver = false
  // Socket still waiting for setupComplete; close() must be able to cancel it.
  private pending: WebSocket | null = null
  private readonly WS: typeof WebSocket
  private readonly log: (...a: unknown[]) => void

  constructor(private readonly opts: ConnectionOptions) {
    this.WS = opts.WebSocketImpl ?? WebSocket
    this.log = opts.log ?? (() => undefined)
  }

  get resumptionHandle(): string | null {
    return this.handle
  }

  async connect(): Promise<void> {
    this.state = 'connecting'
    try {
      this.sock = await this.openSocket(null)
    } catch (err) {
      this.state = 'closed'
      throw err
    }
    this.state = 'open'
  }

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
    for (const sock of [s, p]) {
      try {
        sock?.close(code, reason)
      } catch {
        /* already closed */
      }
    }
  }

  // Opens a socket, sends setup and resolves once the server answers setupComplete.
  private openSocket(handle: string | null): Promise<WebSocket> {
    return new Promise<WebSocket>((resolve, reject) => {
      withTimeout(this.opts.getAuth(), this.opts.setupTimeoutMs ?? 10_000, 'Live token request timed out')
        .then((auth) => {
          if (this.expectedClose) {
            reject(new Error('Live connection closed'))
            return
          }
          const ws = new this.WS(liveUrl(auth))
          this.pending = ws
          ws.binaryType = 'arraybuffer'
          let ready = false
          let settled = false
          const fail = (why: string) => {
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
          ws.addEventListener('message', (ev: MessageEvent) => {
            const decoded = decodeFrame(ev.data)
            const events = parseServerMessage(decoded)
            if (!ready) {
              if (events.some((e) => e.type === 'setupComplete')) {
                ready = true
                settled = true
                if (this.pending === ws) this.pending = null
                clearTimeout(timer)
                resolve(ws)
              }
              // Anything else before setupComplete is ignored (nothing legitimate precedes it).
              return
            }
            if (ws !== this.sock) return // old socket after handover, or a stray one
            for (const e of events) this.route(e)
          })
          ws.addEventListener('error', () => {
            if (!ready) fail('Live connection error')
          })
          ws.addEventListener('close', (ev: CloseEvent) => {
            if (!ready) {
              fail(`Live connection closed before setup (${ev.code}${ev.reason ? `: ${ev.reason}` : ''})`)
              return
            }
            this.onSocketClosed(ws, ev.code, ev.reason)
          })
        })
        .catch((err: unknown) => reject(err instanceof Error ? err : new Error(String(err))))
    })
  }

  private route(e: LiveServerEvent): void {
    if (e.type === 'resumptionUpdate') {
      this.resumable = e.resumable
      if (e.resumable && e.handle) this.handle = e.handle
    } else if (e.type === 'goAway') {
      this.log('goAway', e.timeLeftMs)
      void this.handover(e.timeLeftMs)
    } else if (e.type === 'interrupted' || e.type === 'toolCall') {
      // Resuming while generating or running function calls loses data.
      this.resumable = false
    }
    this.opts.onEvent(e)
  }

  // GoAway: reconnect on our own schedule before the server cuts us off. The server allows ONE client per session
  // (a second concurrent socket is refused with 1008 "already connected"; verified), so this is break-before-make:
  // wait for a moment the session is resumable (the model is idle), close, then resume straight away.
  private async handover(timeLeftMs: number): Promise<void> {
    if (this.handingOver || this.state !== 'open') return
    this.handingOver = true
    const deadline = Date.now() + Math.max(0, timeLeftMs - 3000)
    try {
      while (!this.resumable && Date.now() < deadline && this.state === 'open') await sleep(100)
      const old = this.sock
      if (this.state !== 'open' || !old) return
      this.superseded.add(old)
      this.sock = null
      try {
        old.close(1000, 'handover')
      } catch {
        /* ignore */
      }
      await this.reconnectLoop(1000, 'handover', 'goaway')
    } finally {
      this.handingOver = false
    }
  }

  private onSocketClosed(ws: WebSocket, code: number, reason: string): void {
    if (this.superseded.has(ws)) return
    if (ws !== this.sock) return
    if (this.expectedClose || this.state === 'closed') {
      this.opts.onClosed({ code, reason, expected: true })
      return
    }
    this.log('socket lost', code, reason, `handle=${this.handle ? 'yes' : 'none'}`)
    this.sock = null
    void this.reconnectLoop(code, reason, 'dropped')
  }

  private async reconnectLoop(code: number, reason: string, why: 'goaway' | 'dropped'): Promise<void> {
    this.state = 'reconnecting'
    this.opts.onReconnecting?.(why)
    // 250, 500, 1000, 2000, 3000, 3000 ms: rides out a ~10 s network blip before telling the user.
    const max = this.opts.maxReconnectAttempts ?? 6
    let lastError = `${code}${reason ? `: ${reason}` : ''}`
    for (let attempt = 0; attempt < max; attempt++) {
      // The first pause also lets the server register the old socket's close before the resume (it refuses two clients).
      await sleep(Math.min(250 * 2 ** attempt, 3000))
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
        this.log('reconnect attempt failed', attempt, lastError)
      }
    }
    this.state = 'closed'
    this.opts.onClosed({ code, reason: `connection lost: ${lastError}`, expected: false })
  }
}
