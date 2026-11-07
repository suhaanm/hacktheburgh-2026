import http from 'node:http'
import type { AddressInfo } from 'node:net'
import path from 'node:path'
import { Readable } from 'node:stream'
import { describe, expect, it } from 'vitest'
import { APP_ORIGIN } from '../../shared/brand'
import { CSP, MISSING_HEADER, TOKEN_HEADER, buildUpstreamHeaders, checkApiRequest, createAppHandler, matchProxy, mimeFor, nodeUpstream, resolveAsset, type UpstreamRequest, type UpstreamResponse } from './app-protocol'

const root = '/pkg/dashboard/dist'
const files = new Set([`${root}/index.html`, `${root}/assets/app-1a2b.js`, `${root}/favicon.svg`])
const isFile = (p: string) => files.has(p)

describe('the content security policy', () => {
  it('allows scripts and connections only from the app itself, and nothing remote at all', () => {
    expect(CSP).toContain("default-src 'self'")
    expect(CSP).toContain("script-src 'self'")
    expect(CSP).toContain("connect-src 'self'")
    expect(CSP).toContain("object-src 'none'")
    expect(CSP).toContain("frame-ancestors 'none'")
    expect(CSP).toContain("base-uri 'none'")
    expect(CSP).not.toMatch(/https?:|\*|unsafe-eval/)
    expect(CSP.match(/script-src[^;]*/)?.[0]).toBe("script-src 'self'") // no inline script
  })
})

describe('resolving a path to a file in the dist folder', () => {
  it('serves the index for the root, a file that exists, and the index for a page route without an extension', () => {
    expect(resolveAsset(root, '/', isFile)).toEqual({ kind: 'index' })
    expect(resolveAsset(root, '/assets/app-1a2b.js', isFile)).toEqual({ kind: 'file', file: `${root}/assets/app-1a2b.js` })
    expect(resolveAsset(root, '/today', isFile)).toEqual({ kind: 'index' })
  })
  it('answers missing for a file-looking path that is not there', () => {
    expect(resolveAsset(root, '/assets/gone.js', isFile)).toEqual({ kind: 'missing' })
  })
  it('refuses to leave the folder by any spelling', () => {
    for (const p of ['/../secret', '/assets/../../secret', '/%2e%2e/secret', '/%2E%2E%2Fsecret', '/assets/%2e%2e/%2e%2e/x', '/a%00b', '/a\\..\\b', '/%5c..%5csecret', '/%zz']) {
      expect(resolveAsset(root, p, isFile).kind, p).toBe('forbidden')
    }
  })
  it('knows the types the dashboard ships', () => {
    expect(mimeFor('a.js')).toContain('javascript')
    expect(mimeFor('a.css')).toContain('text/css')
    expect(mimeFor('a.woff2')).toBe('font/woff2')
    expect(mimeFor('a.svg')).toBe('image/svg+xml')
    expect(mimeFor('a.unknown')).toBe('application/octet-stream')
  })
})

describe('the two API prefixes', () => {
  it('matches only /engine and /agent', () => {
    expect(matchProxy(new URL('app://knack/engine/health'))).toEqual({ target: 'engine', path: '/health', search: '' })
    expect(matchProxy(new URL('app://knack/agent/agents/runs?person=p1'))).toEqual({ target: 'agent', path: '/agents/runs', search: '?person=p1' })
    expect(matchProxy(new URL('app://knack/engine'))?.path).toBe('/')
    for (const u of ['app://knack/', 'app://knack/enginex/health', 'app://knack/x/engine/health', 'app://knack/assets/a.js']) expect(matchProxy(new URL(u)), u).toBeNull()
  })
  it('refuses another origin, a cross-site fetch and odd methods; accepts the app itself and a plain read', () => {
    const h = (o: Record<string, string>) => new Headers(o)
    expect(checkApiRequest(h({}), 'GET')).toBeNull()
    expect(checkApiRequest(h({ origin: APP_ORIGIN, 'sec-fetch-site': 'same-origin' }), 'POST')).toBeNull()
    expect(checkApiRequest(h({ origin: 'https://evil.example' }), 'POST')?.code).toBe('origin_refused')
    expect(checkApiRequest(h({ origin: 'http://127.0.0.1:5173' }), 'POST')?.code).toBe('origin_refused')
    expect(checkApiRequest(h({ 'sec-fetch-site': 'cross-site' }), 'GET')?.code).toBe('origin_refused')
    expect(checkApiRequest(h({}), 'TRACE')?.code).toBe('method_refused')
  })
  it('builds upstream headers from a short allow-list, the service Host, and the token the page never sees', () => {
    const page = new Headers({ 'content-type': 'application/json', 'x-understudy-actor': 'worker', cookie: 'a=b', referer: 'app://knack/', [TOKEN_HEADER]: 'forged-forged-forged-forged', origin: APP_ORIGIN, 'user-agent': 'x', host: 'knack' })
    const post = buildUpstreamHeaders(page, { port: 7700, token: 'real-token-real-token-1234', dashboardOrigin: 'http://127.0.0.1:5173', method: 'POST' })
    expect(post).toEqual({ 'content-type': 'application/json', 'x-understudy-actor': 'worker', host: '127.0.0.1:7700', origin: 'http://127.0.0.1:5173', [TOKEN_HEADER]: 'real-token-real-token-1234' })
    const get = buildUpstreamHeaders(page, { port: 7710, token: null, dashboardOrigin: 'http://127.0.0.1:5173', method: 'GET' })
    expect(get).toEqual({ 'content-type': 'application/json', 'x-understudy-actor': 'worker', host: '127.0.0.1:7710' }) // no origin on a read, and a forged token is thrown away
  })
})

describe('the handler', () => {
  function rig(over: { token?: string | null; up?: (r: UpstreamRequest) => Promise<UpstreamResponse>; dist?: string | null } = {}) {
    const seen: UpstreamRequest[] = []
    const handler = createAppHandler({
      distRoot: over.dist === undefined ? root : over.dist,
      ports: { engine: 7700, agent: 7710, dashboard: 5173 },
      token: () => (over.token === undefined ? 'real-token-real-token-1234' : over.token),
      shellAssets: { 'starting.html': { type: 'text/html; charset=utf-8', body: '<p>Starting</p>' } },
      isFile,
      readFile: async (p) => Buffer.from(`file:${path.basename(p)}`),
      upstream:
        over.up ??
        (async (r) => {
          seen.push(r)
          return { status: 200, headers: { 'content-type': 'application/json', connection: 'keep-alive', 'set-cookie': 'a=b' }, body: Readable.from([Buffer.from('{"ok":true}')]) }
        }),
    })
    return { handler, seen }
  }
  const get = (handler: (r: Request) => Promise<Response>, url: string, init?: RequestInit) => handler(new Request(url, init))

  it('serves the dashboard with the policy on, and long caching only for hashed assets', async () => {
    const { handler } = rig()
    const index = await get(handler, 'app://knack/')
    expect(index.status).toBe(200)
    expect(await index.text()).toBe('file:index.html')
    expect(index.headers.get('content-security-policy')).toBe(CSP)
    expect(index.headers.get('x-content-type-options')).toBe('nosniff')
    expect(index.headers.get('cache-control')).toBe('no-cache')
    const js = await get(handler, 'app://knack/assets/app-1a2b.js')
    expect(js.headers.get('content-type')).toContain('javascript')
    expect(js.headers.get('cache-control')).toContain('immutable')
    expect((await get(handler, 'app://knack/assets/missing.js')).status).toBe(404)
    expect((await get(handler, 'app://knack/..%2f..%2fetc%2fpasswd')).status).toBe(403)
    expect((await get(handler, 'app://knack/', { method: 'HEAD' })).status).toBe(200)
  })

  it('answers only for its own host, and says so plainly when the dashboard is not built', async () => {
    expect((await get(rig().handler, 'app://elsewhere/')).status).toBe(404)
    const none = await get(rig({ dist: null }).handler, 'app://knack/')
    expect(none.status).toBe(404)
    expect(((await none.json()) as { error: { code: string } }).error.code).toBe('dashboard_missing')
  })

  it('serves its embedded pages and nothing else under /__shell/', async () => {
    const { handler } = rig()
    const ok = await get(handler, 'app://knack/__shell/starting.html')
    expect(await ok.text()).toBe('<p>Starting</p>')
    expect(ok.headers.get('content-security-policy')).toBe(CSP)
    expect((await get(handler, 'app://knack/__shell/nope.html')).status).toBe(404)
  })

  it('forwards a read to the engine with the token, and strips hop-by-hop headers and cookies from the answer', async () => {
    const { handler, seen } = rig()
    const res = await get(handler, 'app://knack/engine/health?x=1')
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ ok: true })
    expect(res.headers.get('connection')).toBeNull()
    expect(res.headers.get('set-cookie')).toBeNull()
    expect(res.headers.get('cache-control')).toBe('no-store')
    expect(res.headers.get(MISSING_HEADER)).toBeNull()
    expect(seen[0]).toMatchObject({ port: 7700, method: 'GET', path: '/health?x=1', body: null })
    expect(seen[0]!.headers[TOKEN_HEADER]).toBe('real-token-real-token-1234')
    expect(seen[0]!.headers.host).toBe('127.0.0.1:7700')
  })

  it('forwards a write to the agent with the dashboard origin and the JSON body', async () => {
    const { handler, seen } = rig()
    const res = await get(handler, 'app://knack/agent/agents/spawn', { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker', origin: APP_ORIGIN }, body: '{"kind":"shadow"}' })
    expect(res.status).toBe(200)
    expect(seen[0]).toMatchObject({ port: 7710, method: 'POST', path: '/agents/spawn' })
    expect(seen[0]!.headers.origin).toBe('http://127.0.0.1:5173')
    expect(seen[0]!.body?.toString()).toBe('{"kind":"shadow"}')
  })

  it('flags a missing token to the page, as the dev server does', async () => {
    const res = await get(rig({ token: null }).handler, 'app://knack/engine/queue')
    expect(res.headers.get(MISSING_HEADER)).toBe('missing')
  })

  it('refuses a forwarded request from another origin before it reaches any service', async () => {
    const { handler, seen } = rig()
    const res = await get(handler, 'app://knack/engine/kill/clear', { method: 'POST', headers: { origin: 'https://evil.example', 'content-type': 'application/json' }, body: '{}' })
    expect(res.status).toBe(403)
    expect(seen).toHaveLength(0)
  })

  it('answers 502 with a plain error when a service does not answer', async () => {
    const res = await get(rig({ up: async () => { throw new Error('ECONNREFUSED') } }).handler, 'app://knack/agent/health')
    expect(res.status).toBe(502)
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe('upstream_unreachable')
  })

  it('does not take writes on the dashboard files themselves', async () => {
    expect((await get(rig().handler, 'app://knack/index.html', { method: 'POST', body: 'x' })).status).toBe(405)
  })
})

describe('the real upstream', () => {
  it('talks to a local server, streams the body, and fails fast on a closed port', async () => {
    const server = http.createServer((req, res) => {
      res.setHeader('content-type', 'text/event-stream')
      res.write('event: a\n\n')
      setTimeout(() => res.end(`host=${req.headers.host};tok=${String(req.headers[TOKEN_HEADER])};method=${req.method}`), 20)
    })
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r))
    const port = (server.address() as AddressInfo).port
    try {
      const res = await nodeUpstream({ port, method: 'POST', path: '/x', headers: { host: `127.0.0.1:${port}`, [TOKEN_HEADER]: 'tt-tt-tt-tt-tt-tt-tt' }, body: Buffer.from('{}') })
      expect(res.status).toBe(200)
      let text = ''
      for await (const chunk of res.body as AsyncIterable<Buffer>) text += chunk.toString()
      expect(text).toBe(`event: a\n\nhost=127.0.0.1:${port};tok=tt-tt-tt-tt-tt-tt-tt;method=POST`)
    } finally {
      await new Promise((r) => server.close(r))
    }
    await expect(nodeUpstream({ port, method: 'GET', path: '/', headers: {}, body: null })).rejects.toBeTruthy()
  })
})
