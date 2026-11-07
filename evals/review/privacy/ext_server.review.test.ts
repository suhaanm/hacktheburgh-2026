// REVIEW-PRIVACY (b)(c)(d): can a web page, a DNS-rebinding page, or another browser extension use the desktop extension server (:7720)?
// Hermetic: starts startExtServer on an ephemeral loopback port with a fake grounder; no network, no Electron.
import http from 'node:http'
import { describe, expect, it } from 'vitest'
import { startExtServer } from '../../../apps/desktop/src/main/dom-ground/ext-server'

function call(port: number, method: string, path: string, headers: Record<string, string>, body?: string): Promise<{ status: number; text: string }> {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, method, path, headers, setHost: false }, (res) => {
      let t = ''
      res.on('data', (c) => (t += c))
      res.on('end', () => resolve({ status: res.statusCode ?? 0, text: t }))
    })
    req.on('error', reject)
    if (body) req.write(body)
    req.end()
  })
}

const grounder = {
  nextWant: () => ({ request_id: 'rq_1', target: { label_hash: 'h:9f2c1a77b0aa' } }) as never,
  answer: () => true,
  pending: () => 1,
}

describe('ext server hardening', async () => {
  const rings: unknown[] = []
  const srv = await startExtServer({ grounder: grounder as never, port: 0, onRing: (r) => rings.push(r), onClear: () => rings.push('clear') })
  if (!srv) throw new Error('could not start')
  const port = srv.port()
  const host = `127.0.0.1:${port}`

  it('a web page Origin is refused on every route', async () => {
    for (const [m, p] of [['GET', '/ext/want'], ['POST', '/ext/rect'], ['GET', '/ext/status'], ['POST', '/coach/ring'], ['POST', '/coach/clear']] as const) {
      const r = await call(port, m, p, { host, origin: 'https://evil.example', 'content-type': 'text/plain' }, m === 'POST' ? '{}' : undefined)
      expect(r.status, `${m} ${p}`).toBe(403)
    }
  })
  it('a prefix-style origin is refused (exact extension-scheme regex)', async () => {
    const r = await call(port, 'GET', '/ext/want', { host, origin: 'http://127.0.0.1.evil.example' })
    expect(r.status).toBe(403)
  })
  it('DNS rebinding: a foreign Host header is refused', async () => {
    for (const h of ['evil.example', `evil.example:${port}`, `localhost.evil.example:${port}`, '127.0.0.1', `127.0.0.1:${port + 1}`]) {
      const r = await call(port, 'GET', '/ext/want', { host: h })
      expect(r.status, h).toBe(403)
    }
  })
  it('ring routes accept no Origin at all', async () => {
    const r = await call(port, 'POST', '/coach/ring', { host, origin: 'chrome-extension://abcdefghijklmnop' }, JSON.stringify({ zone: 'x' }))
    expect(r.status).toBe(403)
  })
  it('KNOWN GAP: ANY extension id is accepted (the origin is not pinned to ours), so another installed extension can read wants and post rects', async () => {
    const r = await call(port, 'GET', '/ext/want', { host, origin: 'chrome-extension://zzzzzzzzzzzzzzzz' })
    expect(r.status).toBe(200)   // passes while the gap exists; a fixed server pins the extension id and this becomes 403
    const a = await call(port, 'POST', '/ext/rect', { host, origin: 'chrome-extension://zzzzzzzzzzzzzzzz', 'content-type': 'application/json' }, '{}')
    expect([400, 410, 200]).toContain(a.status)
  })
  it('KNOWN GAP: no Origin and no secret: any local process (or a sandboxed agent child with loopback) can draw rings', async () => {
    const r = await call(port, 'POST', '/coach/ring', { host, 'content-type': 'application/json' }, JSON.stringify({ zone: 'toolbar', message: 'click here' }))
    expect([200, 400]).toContain(r.status)
  })
  it('closes', async () => { await srv.close() })
})
