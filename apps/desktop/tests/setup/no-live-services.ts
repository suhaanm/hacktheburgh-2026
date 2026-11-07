// Shared by every desktop test (vitest setupFiles). The dev stack on this machine is shared by every agent: the engine on :7700, the agent
// service on :7710, the dashboard on :5173 and the sandbox sites on :7801-7803. A unit test must never reach them (a stray POST /kill from
// a test once put the live agent service into the killed state). So:
//   1. UNDERSTUDY_DATA_DIR points at a private temp directory unless a test sets its own: nothing here can write <repo>/data (the
//      kill file, the token, the queue) by accident;
//   2. fetch and node:http refuse any request to those ports, with an error that names the test's mistake.
// A test that wants a server starts a fake on an ephemeral port (src/main/engine/fake-engine.test-util.ts).
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'

if (!(process.env.UNDERSTUDY_DATA_DIR ?? '').trim()) {
  process.env.UNDERSTUDY_DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'understudy-test-data-'))
}

const LIVE_PORTS = new Set(['7700', '7710', '5173', '7801', '7802', '7803'])
const HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1'])

export function liveServiceProblem(url: string | URL | { hostname?: string; host?: string; port?: string | number | null; protocol?: string }): string | null {
  try {
    let host = ''
    let port = ''
    if (typeof url === 'string' || url instanceof URL) {
      const u = new URL(String(url))
      host = u.hostname
      port = u.port
    } else {
      host = String(url.hostname ?? url.host ?? '').replace(/:\d+$/, '')
      port = String(url.port ?? '')
    }
    return HOSTS.has(host) && LIVE_PORTS.has(port) ? `a unit test tried to reach the live dev service at ${host}:${port}; use a fake server on an ephemeral port` : null
  } catch {
    return null
  }
}

const realFetch = globalThis.fetch
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const url = typeof input === 'string' || input instanceof URL ? input : input.url
  const problem = liveServiceProblem(url)
  if (problem) throw new Error(problem)
  return realFetch(input as never, init)
}) as typeof fetch

const realRequest = http.request.bind(http)
http.request = ((...args: unknown[]) => {
  const first = args[0] as string | URL | { hostname?: string; host?: string; port?: string | number }
  const problem = liveServiceProblem(first)
  if (problem) throw new Error(problem)
  return (realRequest as (...a: unknown[]) => http.ClientRequest)(...args)
}) as typeof http.request
const realGet = http.get.bind(http)
http.get = ((...args: unknown[]) => {
  const first = args[0] as string | URL | { hostname?: string; host?: string; port?: string | number }
  const problem = liveServiceProblem(first)
  if (problem) throw new Error(problem)
  return (realGet as (...a: unknown[]) => http.ClientRequest)(...args)
}) as typeof http.get
