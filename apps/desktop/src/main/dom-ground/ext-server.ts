// The small localhost server the browser extension talks to (default 127.0.0.1:7720), plus a local-only way for other Understudy
// processes to ask for a ring.
//   GET  /ext/want    the next RectWant (200) or 204.            extension -> desktop
//   POST /ext/rect    a RectAnswer; 200 when it matched a pending want, 410 when it was late or unknown. The optional `content` (up to 80
//                     boxes of four integers) is parsed by protocol.parseAnswer; a worst-case answer is about 2.5 KB, well inside MAX_BODY.
//   POST /coach/ring  { zone | label_hash | role+name, label?, message?, step? }  draw a ring on that element.   local processes only
//   POST /coach/clear remove the ring.                                                         local processes only
//   GET  /ext/status  { pending, extension_seen_ms }
// Hardening: bound to loopback; the Host header must be 127.0.0.1 or localhost on this port (DNS rebinding); a request that
// carries an Origin must come from a browser extension (chrome-extension:// or moz-extension://), never from a web page; the ring
// routes accept no Origin at all, so a web page cannot make the overlay draw; bodies are capped; nothing is executed.
import http from 'node:http'
import type { AddressInfo } from 'node:net'
import { parseAnswer, targetProblem, toTarget, type DomTarget } from './protocol'
import type { DomGrounder } from './dom-grounder'

export interface RingRequest {
  target: DomTarget
  label?: string
  // The coach's words for the ring (shown as one short note).
  message?: string
  step?: number
}

export interface ExtServerOptions {
  grounder: Pick<DomGrounder, 'nextWant' | 'answer' | 'pending'>
  host?: string
  port?: number
  // Draw (or clear) a ring for a local caller. Absent: the ring routes answer 404.
  onRing?: (req: RingRequest) => void
  onClear?: () => void
  now?: () => number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface ExtServer {
  port(): number
  close(): Promise<void>
  // When the extension last asked for a want (ms since epoch), or null.
  lastSeenAt(): number | null
}

const MAX_BODY = 8 * 1024
const EXTENSION_ORIGIN = /^(chrome-extension|moz-extension):\/\/[a-z0-9-]{8,64}$/i

function readBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks: Buffer[] = []
    req.on('data', (c: Buffer) => {
      size += c.length
      if (size > MAX_BODY) {
        reject(new Error('body too large'))
        req.destroy()
      } else chunks.push(c)
    })
    req.on('end', () => {
      try {
        const text = Buffer.concat(chunks).toString('utf8')
        resolve(text ? JSON.parse(text) : null)
      } catch {
        reject(new Error('not JSON'))
      }
    })
    req.on('error', reject)
  })
}

export function startExtServer(opts: ExtServerOptions): Promise<ExtServer | null> {
  const host = opts.host ?? '127.0.0.1'
  const log = opts.log ?? (() => undefined)
  const now = opts.now ?? Date.now
  let seenAt: number | null = null
  let boundPort = 0

  const server = http.createServer((req, res) => {
    const origin = typeof req.headers.origin === 'string' ? req.headers.origin : null
    const send = (status: number, body?: unknown, extra: Record<string, string> = {}): void => {
      const headers: Record<string, string> = { 'cache-control': 'no-store', ...extra }
      if (origin && EXTENSION_ORIGIN.test(origin)) {
        headers['access-control-allow-origin'] = origin
        headers['access-control-allow-methods'] = 'GET, POST, OPTIONS'
        headers['access-control-allow-headers'] = 'content-type'
        headers.vary = 'Origin'
      }
      if (body !== undefined) headers['content-type'] = 'application/json'
      res.writeHead(status, headers)
      res.end(body === undefined ? undefined : JSON.stringify(body))
    }

    const hostHeader = (req.headers.host ?? '').toLowerCase()
    if (hostHeader !== `127.0.0.1:${boundPort}` && hostHeader !== `localhost:${boundPort}`) return send(403, { error: 'bad host' })
    if (origin !== null && !EXTENSION_ORIGIN.test(origin)) return send(403, { error: 'web pages may not use this server' })
    const path = (req.url ?? '/').split('?')[0]

    if (req.method === 'OPTIONS') return send(204)

    void (async () => {
      try {
        if (req.method === 'GET' && path === '/ext/want') {
          seenAt = now()
          const want = opts.grounder.nextWant()
          return want ? send(200, want) : send(204)
        }
        if (req.method === 'POST' && path === '/ext/rect') {
          const answer = parseAnswer(await readBody(req))
          if (!answer) return send(400, { error: 'not a RectAnswer' })
          return opts.grounder.answer(answer) ? send(200, {}) : send(410, { error: 'unknown or late request' })
        }
        if (req.method === 'GET' && path === '/ext/status') return send(200, { pending: opts.grounder.pending(), extension_seen_ms: seenAt === null ? null : now() - seenAt })
        if (path === '/coach/ring' || path === '/coach/clear') {
          // Local processes only: a browser always sends an Origin on POST, so any Origin means "not a local process".
          if (origin !== null) return send(403, { error: 'local callers only' })
          if (req.method !== 'POST' || !opts.onRing || !opts.onClear) return send(404, { error: 'not found' })
          if (path === '/coach/clear') {
            opts.onClear()
            return send(200, {})
          }
          const body = await readBody(req)
          const o = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {}
          const candidate = o.zone !== undefined ? { zone: o.zone, label_hint: o.label_hint, role_hint: o.role_hint } : o.label_hash !== undefined ? { label_hash: o.label_hash } : { role: o.role, name: o.name }
          const problem = targetProblem(candidate)
          const target = toTarget(candidate)
          if (problem || !target) return send(400, { error: problem ?? 'bad target' })
          const label = typeof o.label === 'string' ? o.label.replace(/\s+/g, ' ').trim().slice(0, 40) : undefined
          const message = typeof o.message === 'string' ? o.message.replace(/\s+/g, ' ').trim().slice(0, 200) : undefined
          const step = typeof o.step === 'number' && Number.isInteger(o.step) && o.step >= 1 && o.step <= 99 ? o.step : undefined
          opts.onRing({ target, ...(label ? { label } : {}), ...(message ? { message } : {}), ...(step ? { step } : {}) })
          return send(200, {})
        }
        return send(404, { error: 'not found' })
      } catch (err) {
        return send(400, { error: err instanceof Error ? err.message : 'bad request' })
      }
    })()
  })

  return new Promise((resolve) => {
    server.once('error', (err: NodeJS.ErrnoException) => {
      log('ext-server', err.code === 'EADDRINUSE' ? `port ${opts.port} is in use; browser grounding is off` : `server error: ${err.message}`)
      resolve(null)
    })
    server.listen(opts.port ?? 7720, host, () => {
      boundPort = (server.address() as AddressInfo).port
      log('ext-server', `listening on ${host}:${boundPort}`)
      resolve({
        port: () => boundPort,
        lastSeenAt: () => seenAt,
        close: () => new Promise<void>((r) => server.close(() => r())),
      })
    })
  })
}
