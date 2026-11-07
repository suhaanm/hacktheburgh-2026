// Record / replay of the HTTP Gemini calls (Grounder, Verifier, Architect, Scam, Router) as a venue-Wi-Fi backup.
//   ALONGSIDE_RECORD=1  record every successful JSON response from *.googleapis.com, keyed by request hash.
//   ALONGSIDE_REPLAY=1  serve recorded responses; a miss behaves like a dead network (services already handle that).
//   ALONGSIDE_REPLAY=hybrid  serve hits, pass misses through to the network.
// The key ignores image bytes, so a re-run on the same stage screen with different pixels still hits.
// Live voice runs over a renderer WebSocket and is NOT covered. Files live in ALONGSIDE_REPLAY_DIR (default <userData>/replay).
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { readRequestBody } from '../fetch-probe'

export type ReplayMode = 'off' | 'record' | 'replay' | 'hybrid'

export interface ReplayOptions {
  dir: string
  mode: ReplayMode
  log?: (scope: string, ...args: unknown[]) => void
  realFetch?: typeof fetch
}

interface Recording {
  key: string
  at: number
  model: string | null
  preview: string
  status: number
  contentType: string
  body: string
}

const GOOGLE_HOST = /(^|\.)googleapis\.com$/
const SKIP_PATH = /token|auth/i

export function replayModeFromEnv(env: NodeJS.ProcessEnv): ReplayMode {
  if (env.ALONGSIDE_REPLAY === 'hybrid') return 'hybrid'
  if (env.ALONGSIDE_REPLAY === '1') return 'replay'
  if (env.ALONGSIDE_RECORD === '1') return 'record'
  return 'off'
}

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => (a < b ? -1 : 1))
        .map(([k, v]) => [k, stable(v)]),
    )
  }
  return value
}

// Blank out bulky binary-looking strings (screenshots) and chain ids so the key depends on the prompt, not the pixels.
function normalise(value: unknown, keyName = ''): unknown {
  if (typeof value === 'string') {
    if (value.length > 400 && /^[A-Za-z0-9+/=_-]+$/.test(value.slice(0, 400))) return '<binary>'
    if (keyName === 'previous_interaction_id') return '<chain>'
    return value
  }
  if (Array.isArray(value)) return value.map((v) => normalise(v))
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, normalise(v, k)]))
  return value
}

export function requestKey(method: string, pathname: string, body: string | undefined): string {
  let canonical: unknown = body ?? ''
  if (body) {
    try {
      canonical = stable(normalise(JSON.parse(body)))
    } catch {
      canonical = body
    }
  }
  return crypto.createHash('sha256').update(JSON.stringify([method.toUpperCase(), pathname, canonical])).digest('hex')
}

function previewOf(body: string | undefined): { model: string | null; preview: string } {
  try {
    const json = JSON.parse(body ?? '') as Record<string, unknown>
    const model = typeof json.model === 'string' ? json.model : null
    const texts: string[] = []
    const visit = (v: unknown): void => {
      if (typeof v === 'string' && v.length < 400 && v.length > 3) texts.push(v)
      else if (Array.isArray(v)) v.forEach(visit)
      else if (v && typeof v === 'object') Object.values(v).forEach(visit)
    }
    visit(json.input)
    return { model, preview: texts.join(' | ').slice(0, 200) }
  } catch {
    return { model: null, preview: '' }
  }
}

export function createReplayFetch(opts: ReplayOptions): { fetch: typeof fetch; stats: { hits: number; misses: number; recorded: number } } {
  const log = opts.log ?? (() => undefined)
  const realFetch = opts.realFetch ?? globalThis.fetch.bind(globalThis)
  const stats = { hits: 0, misses: 0, recorded: 0 }
  const store = new Map<string, Recording>()
  if (opts.mode !== 'record' && fs.existsSync(opts.dir)) {
    for (const file of fs.readdirSync(opts.dir)) {
      if (!file.endsWith('.json')) continue
      try {
        const rec = JSON.parse(fs.readFileSync(path.join(opts.dir, file), 'utf8')) as Recording
        store.set(rec.key, rec)
      } catch {
        // a half-written recording is skipped
      }
    }
    log('replay', `loaded ${store.size} recordings from ${opts.dir}`)
  }
  if (opts.mode === 'record' || opts.mode === 'hybrid') fs.mkdirSync(opts.dir, { recursive: true })

  const wrapped = async (input: Request | URL | string, init?: RequestInit): Promise<Response> => {
    let url: URL
    try {
      url = new URL(input instanceof Request ? input.url : String(input))
    } catch {
      return realFetch(input, init)
    }
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const body = await readRequestBody(input, init)
    if (!GOOGLE_HOST.test(url.hostname) || method !== 'POST' || SKIP_PATH.test(url.pathname)) {
      if (opts.mode === 'replay' && GOOGLE_HOST.test(url.hostname)) throw new TypeError('fetch failed') // offline: nothing else may leave
      return realFetch(input, init)
    }
    const key = requestKey(method, url.pathname, body)

    if (opts.mode === 'replay' || opts.mode === 'hybrid') {
      const hit = store.get(key)
      if (hit) {
        stats.hits++
        log('replay', `hit ${hit.model ?? url.pathname} ${key.slice(0, 8)} "${hit.preview.slice(0, 60)}"`)
        return new Response(hit.body, { status: hit.status, headers: { 'content-type': hit.contentType } })
      }
      stats.misses++
      log('replay', `MISS ${previewOf(body).model ?? url.pathname} ${key.slice(0, 8)}`)
      if (opts.mode === 'replay') throw new TypeError('fetch failed')
    }

    const res = await realFetch(input, init)
    const contentType = res.headers.get('content-type') ?? 'application/json'
    if ((opts.mode === 'record' || opts.mode === 'hybrid') && res.ok && /json/.test(contentType)) {
      try {
        const text = await res.clone().text()
        const { model, preview } = previewOf(body)
        const rec: Recording = { key, at: Date.now(), model, preview, status: res.status, contentType, body: text }
        fs.writeFileSync(path.join(opts.dir, `${key.slice(0, 24)}.json`), JSON.stringify(rec))
        store.set(key, rec)
        stats.recorded++
        log('replay', `recorded ${model ?? url.pathname} ${key.slice(0, 8)}`)
      } catch (err) {
        log('replay', 'could not record:', err instanceof Error ? err.message : err)
      }
    }
    return res
  }
  return { fetch: wrapped as typeof fetch, stats }
}

export function installReplay(userDataDir: string | null, log: (scope: string, ...args: unknown[]) => void): void {
  const mode = replayModeFromEnv(process.env)
  if (mode === 'off') return
  const dir = process.env.ALONGSIDE_REPLAY_DIR ? path.resolve(process.env.ALONGSIDE_REPLAY_DIR) : path.join(userDataDir ?? process.cwd(), 'replay')
  const { fetch: replayFetch } = createReplayFetch({ dir, mode, log })
  globalThis.fetch = replayFetch
  log('replay', `mode=${mode} dir=${dir}`)
}
