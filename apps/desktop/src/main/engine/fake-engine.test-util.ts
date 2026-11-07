// A fake engine (and agent) on an ephemeral loopback port for tests: records every request, answers from a function.
import http from 'node:http'
import type { AddressInfo } from 'node:net'

export interface FakeServer {
  url: string
  requests: Array<{ method: string; path: string; body: unknown }>
  respond: (path: string, method: string) => { status: number; body?: unknown }
  close(): Promise<void>
}

const open: FakeServer[] = []

export async function closeFakeServers(): Promise<void> {
  while (open.length) await open.pop()!.close()
}

export async function fakeServer(respond: FakeServer['respond'] = () => ({ status: 200, body: {} })): Promise<FakeServer> {
  const requests: FakeServer['requests'] = []
  const fake: FakeServer = { url: '', requests, respond, close: async () => undefined }
  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = []
    req.on('data', (c: Buffer) => chunks.push(c))
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8')
      requests.push({ method: req.method ?? '', path: req.url ?? '', body: raw ? JSON.parse(raw) : null })
      const r = fake.respond(req.url ?? '', req.method ?? '')
      res.writeHead(r.status, { 'content-type': 'application/json' })
      res.end(r.body === undefined ? '' : JSON.stringify(r.body))
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  fake.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
  fake.close = () => new Promise((resolve) => server.close(() => resolve()))
  open.push(fake)
  return fake
}
