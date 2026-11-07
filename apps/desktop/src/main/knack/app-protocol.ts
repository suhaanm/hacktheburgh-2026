// app://knack: where the packaged app serves the built dashboard from (apps/dashboard/dist), with no web server and no remote content.
//
//   /                     the dashboard (index.html; a path without a file extension falls back to it, so hash and deep links open)
//   /assets/*, /*.svg ... files from the dist folder, never from outside it
//   /engine/*, /agent/*   the dashboard's two API prefixes, forwarded to the local services on loopback (the job vite.proxy.ts does in development):
//                         the per-boot token is added here, in main, and the page never sees it; a request that did not come from this app's own page is
//                         refused; nothing but those two prefixes is forwarded; only loopback is ever contacted
//   /__shell/*            two or three small embedded pages of our own (the "Starting Knack" and error state)
//
// Every response carries a strict Content-Security-Policy: scripts only from this origin, connections only to this origin (the two prefixes above are
// the only way out of the page), no frames, no plugins, no remote images or fonts.
//
// This file is pure where it can be (path resolution, header rules, the CSP) so tests read it directly; the effectful parts take their file system, token
// and upstream as dependencies.
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { Readable } from 'node:stream'
import { APP_HOST, APP_ORIGIN, APP_SCHEME } from '../../shared/brand'

export const ENGINE_PREFIX = '/engine'
export const AGENT_PREFIX = '/agent'
export const SHELL_PREFIX = '/__shell/'
export const TOKEN_HEADER = 'x-understudy-token'
export const MISSING_HEADER = 'x-understudy-proxy-token'

/** The page's policy. `style-src 'unsafe-inline'` is the one loosening (React and charts set style attributes); scripts stay strictly 'self'. */
export const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "worker-src 'none'",
  "media-src 'none'",
  "manifest-src 'none'",
].join('; ')

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.txt': 'text/plain; charset=utf-8',
}
export const mimeFor = (file: string): string => MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream'

// ---------------------------------------------------------------------------------------------------------------- static files
export type AssetResolution = { kind: 'file'; file: string } | { kind: 'index' } | { kind: 'missing' } | { kind: 'forbidden' }

/**
 * Maps a URL path to a file under `root`. Anything that resolves outside the folder is forbidden (dot segments, encoded slashes, backslashes, NUL).
 * A path with no extension is a page route, not a file: it gets index.html (the dashboard routes in the URL hash, so this is only for safety).
 */
export function resolveAsset(root: string, urlPath: string, isFile: (p: string) => boolean = (p) => fs.existsSync(p) && fs.statSync(p).isFile()): AssetResolution {
  let decoded: string
  try {
    decoded = decodeURIComponent(urlPath)
  } catch {
    return { kind: 'forbidden' }
  }
  if (decoded.includes('\0') || decoded.includes('\\')) return { kind: 'forbidden' }
  const segments = decoded.split('/').filter((s) => s !== '')
  if (segments.some((s) => s === '..' || s === '.')) return { kind: 'forbidden' }
  const rootAbs = path.resolve(root)
  const file = path.resolve(rootAbs, ...segments)
  if (file !== rootAbs && !file.startsWith(rootAbs + path.sep)) return { kind: 'forbidden' }
  if (segments.length === 0) return { kind: 'index' }
  if (isFile(file)) return { kind: 'file', file }
  return path.extname(file) === '' ? { kind: 'index' } : { kind: 'missing' }
}

// ---------------------------------------------------------------------------------------------------------------- the API prefixes
export type ProxyTarget = 'engine' | 'agent'

/** `/engine/x?y` -> { target: 'engine', path: '/x', search: '?y' }; anything else is not ours to forward. */
export function matchProxy(url: URL): { target: ProxyTarget; path: string; search: string } | null {
  for (const [prefix, target] of [[ENGINE_PREFIX, 'engine'], [AGENT_PREFIX, 'agent']] as const) {
    if (url.pathname === prefix || url.pathname.startsWith(`${prefix}/`)) return { target, path: url.pathname.slice(prefix.length) || '/', search: url.search }
  }
  return null
}

export interface Refusal {
  code: 'origin_refused' | 'host_refused' | 'method_refused'
  message: string
}

/** A forwarded request must come from this app's own page: no Origin or exactly app://knack, and the browser must not say cross-site. */
export function checkApiRequest(headers: Headers | { get(name: string): string | null }, method: string): Refusal | null {
  const origin = headers.get('origin')
  if (origin !== null && origin !== '' && origin !== APP_ORIGIN) return { code: 'origin_refused', message: 'This request came from another page, so it was not forwarded.' }
  const site = headers.get('sec-fetch-site')
  if (site !== null && site !== 'same-origin' && site !== 'none') return { code: 'origin_refused', message: 'This request came from another page, so it was not forwarded.' }
  if (!['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase())) return { code: 'method_refused', message: 'That request method is not used here.' }
  return null
}

const FORWARDED_REQUEST_HEADERS = ['accept', 'content-type', 'x-understudy-actor', 'x-understudy-role', 'last-event-id', 'if-none-match', 'cache-control']

export interface UpstreamOptions {
  port: number
  /** The per-boot token, read fresh for each request; null when the file is not there. */
  token: string | null
  /** The origin the services expect from the dashboard (http://127.0.0.1:<dashboard port>). Sent on writes only, as a browser on that page would. */
  dashboardOrigin: string
  method: string
}

/** The headers sent to a service: a short allow-list of the page's, the token (never the page's own), the service's own Host, and the dashboard Origin on writes. */
export function buildUpstreamHeaders(incoming: Headers | { get(name: string): string | null }, o: UpstreamOptions): Record<string, string> {
  const out: Record<string, string> = {}
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const v = incoming.get(name)
    if (v !== null) out[name] = v
  }
  out.host = `127.0.0.1:${o.port}`
  if (!['GET', 'HEAD'].includes(o.method.toUpperCase())) out.origin = o.dashboardOrigin
  if (o.token) out[TOKEN_HEADER] = o.token
  return out
}

const HOP_BY_HOP = new Set(['connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'proxy-authenticate', 'proxy-authorization', 'set-cookie'])

export interface UpstreamRequest {
  port: number
  method: string
  path: string
  headers: Record<string, string>
  body: Buffer | null
  signal?: AbortSignal
}
export interface UpstreamResponse {
  status: number
  headers: Record<string, string | string[] | undefined>
  body: NodeJS.ReadableStream | null
}
export type Upstream = (req: UpstreamRequest) => Promise<UpstreamResponse>

/** The real upstream: node:http to 127.0.0.1 only (the host is fixed here, not taken from the request). Connection attempts give up after 3 s. */
export const nodeUpstream: Upstream = (req) =>
  new Promise((resolve, reject) => {
    const r = http.request({ host: '127.0.0.1', port: req.port, method: req.method, path: req.path, headers: req.headers, agent: false }, (res) => {
      res.socket.setTimeout(0)
      resolve({ status: res.statusCode ?? 502, headers: res.headers, body: res })
    })
    r.on('socket', (s) => {
      s.setTimeout(3000)
      s.once('connect', () => s.setTimeout(0))
      s.once('timeout', () => r.destroy(new Error('connect timeout')))
    })
    r.on('error', reject)
    req.signal?.addEventListener('abort', () => r.destroy(new Error('aborted')), { once: true })
    if (req.body && req.body.length > 0) r.write(req.body)
    r.end()
  })

// ---------------------------------------------------------------------------------------------------------------- the handler
export interface ShellAsset {
  type: string
  body: string
}

export interface AppProtocolDeps {
  /** apps/dashboard/dist, or null when it is not built (the dashboard route then answers with a plain 404). */
  distRoot: string | null
  ports: { engine: number; agent: number; dashboard: number }
  token: () => string | null
  shellAssets: Readonly<Record<string, ShellAsset>>
  upstream?: Upstream
  isFile?: (p: string) => boolean
  readFile?: (p: string) => Promise<Buffer>
  log?: (...args: unknown[]) => void
}

const securityHeaders = (): Record<string, string> => ({
  'content-security-policy': CSP,
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'cross-origin-opener-policy': 'same-origin',
})

const json = (status: number, code: string, message: string, extra: Record<string, string> = {}): Response =>
  new Response(JSON.stringify({ error: { code, message } }), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...extra } })

export function createAppHandler(deps: AppProtocolDeps): (request: Request) => Promise<Response> {
  const upstream = deps.upstream ?? nodeUpstream
  const readFile = deps.readFile ?? ((p: string) => fs.promises.readFile(p))
  const dashboardOrigin = `http://127.0.0.1:${deps.ports.dashboard}`

  const serveFile = async (file: string, request: Request): Promise<Response> => {
    const body = await readFile(file)
    const hashed = /[\\/]assets[\\/]/.test(file)
    return new Response(request.method === 'HEAD' ? null : new Uint8Array(body), {
      status: 200,
      headers: { 'content-type': mimeFor(file), 'cache-control': hashed ? 'public, max-age=31536000, immutable' : 'no-cache', ...securityHeaders() },
    })
  }

  const forward = async (request: Request, m: { target: ProxyTarget; path: string; search: string }): Promise<Response> => {
    const refusal = checkApiRequest(request.headers, request.method)
    if (refusal) return json(403, refusal.code, refusal.message)
    const port = deps.ports[m.target]
    const token = deps.token()
    const headers = buildUpstreamHeaders(request.headers, { port, token, dashboardOrigin, method: request.method })
    const body = ['GET', 'HEAD'].includes(request.method.toUpperCase()) ? null : Buffer.from(await request.arrayBuffer())
    const missing: Record<string, string> = token ? {} : { [MISSING_HEADER]: 'missing' }
    try {
      const res = await upstream({ port, method: request.method, path: `${m.path}${m.search}`, headers, body, signal: request.signal })
      const out = new Headers()
      for (const [k, v] of Object.entries(res.headers)) {
        if (v === undefined || HOP_BY_HOP.has(k.toLowerCase())) continue
        out.set(k, Array.isArray(v) ? v.join(', ') : v)
      }
      if (!out.has('cache-control')) out.set('cache-control', 'no-store')
      for (const [k, v] of Object.entries(missing)) out.set(k, v)
      const noBody = request.method.toUpperCase() === 'HEAD' || res.status === 204 || res.status === 304
      return new Response(noBody || !res.body ? null : (Readable.toWeb(res.body as Readable) as unknown as ReadableStream), { status: res.status, headers: out })
    } catch (err) {
      deps.log?.('app-protocol', `${m.target} did not answer: ${err instanceof Error ? err.message : 'error'}`)
      return json(502, 'upstream_unreachable', `The ${m.target} did not answer.`, missing)
    }
  }

  return async (request) => {
    let url: URL
    try {
      url = new URL(request.url)
    } catch {
      return json(400, 'bad_request', 'Not a valid address.')
    }
    if (url.protocol !== `${APP_SCHEME}:` || url.host !== APP_HOST) return json(404, 'not_found', 'Not found.')

    const proxied = matchProxy(url)
    if (proxied) return forward(request, proxied)

    if (!['GET', 'HEAD'].includes(request.method.toUpperCase())) return json(405, 'method_not_allowed', 'This page only answers to reads.')

    if (url.pathname.startsWith(SHELL_PREFIX)) {
      const asset = deps.shellAssets[url.pathname.slice(SHELL_PREFIX.length)]
      if (!asset) return json(404, 'not_found', 'Not found.')
      return new Response(request.method === 'HEAD' ? null : asset.body, { status: 200, headers: { 'content-type': asset.type, 'cache-control': 'no-store', ...securityHeaders() } })
    }

    if (!deps.distRoot) return json(404, 'dashboard_missing', 'The dashboard has not been built.')
    const found = resolveAsset(deps.distRoot, url.pathname, deps.isFile)
    switch (found.kind) {
      case 'forbidden':
        return json(403, 'forbidden', 'Not allowed.')
      case 'missing':
        return json(404, 'not_found', 'Not found.')
      case 'index':
        try {
          return await serveFile(path.join(deps.distRoot, 'index.html'), request)
        } catch {
          return json(404, 'dashboard_missing', 'The dashboard has not been built.')
        }
      case 'file':
        try {
          return await serveFile(found.file, request)
        } catch {
          return json(404, 'not_found', 'Not found.')
        }
    }
  }
}
