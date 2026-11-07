// Where the other Understudy services live. Everything is loopback-only: the desktop app never sends an event, a kill call or
// a routine request to a host that is not this machine, whatever an environment variable says.
export interface Endpoints {
  engine: string // http://127.0.0.1:7700
  agent: string // http://127.0.0.1:7710
  dashboard: string // http://127.0.0.1:5173
  extension: { host: string; port: number } // the local server the browser extension talks to (src/main/dom-ground)
}

export const DEFAULT_ENDPOINTS: Endpoints = {
  engine: 'http://127.0.0.1:7700',
  agent: 'http://127.0.0.1:7710',
  dashboard: 'http://127.0.0.1:5173',
  extension: { host: '127.0.0.1', port: 7720 },
}

const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]', '::1'])

/** True for http(s) URLs whose host is this machine. */
export function isLoopbackUrl(value: string): boolean {
  try {
    const u = new URL(value)
    return (u.protocol === 'http:' || u.protocol === 'https:') && LOOPBACK.has(u.hostname)
  } catch {
    return false
  }
}

/** A loopback base URL without a trailing slash, or the fallback when the candidate is missing or not loopback. */
export function loopbackOr(candidate: string | undefined, fallback: string): string {
  const c = (candidate ?? '').trim().replace(/\/+$/, '')
  return c && isLoopbackUrl(c) ? c : fallback
}

export function endpointsFromEnv(env: Record<string, string | undefined> = process.env): Endpoints {
  const port = Number(env.UNDERSTUDY_EXT_PORT)
  return {
    engine: loopbackOr(env.UNDERSTUDY_ENGINE_URL, DEFAULT_ENDPOINTS.engine),
    agent: loopbackOr(env.UNDERSTUDY_AGENT_URL, DEFAULT_ENDPOINTS.agent),
    dashboard: loopbackOr(env.UNDERSTUDY_DASHBOARD_URL, DEFAULT_ENDPOINTS.dashboard),
    extension: { host: '127.0.0.1', port: Number.isInteger(port) && port > 0 && port < 65536 ? port : DEFAULT_ENDPOINTS.extension.port },
  }
}

/** Dashboard pages the desktop app links to (hash routes of apps/dashboard; an unknown route falls back to its home screen). */
export type DashboardRoute = 'queue' | 'routines' | 'today' | 'agents' | 'notices'
export const dashboardUrl = (e: Pick<Endpoints, 'dashboard'>, route: DashboardRoute): string => `${e.dashboard}/#/${route}`
