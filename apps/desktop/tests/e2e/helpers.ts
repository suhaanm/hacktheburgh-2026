// Shared e2e helpers. Everything talks to the running app over its debug HTTP (7790 by default) and the QA dev HTTP.
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import zlib from 'node:zlib'

export const DEBUG = process.env.E2E_DEBUG_URL ?? 'http://127.0.0.1:7777'
export const DEV = process.env.E2E_DEV_URL ?? 'http://127.0.0.1:7778'
export const MODE = (process.env.E2E_MODE ?? 'mock') as 'mock' | 'real'
export const USERDATA = process.env.E2E_USERDATA ?? ''
export const APP_LOG = process.env.E2E_APP_LOG ?? ''
export const VISIBLE = process.env.E2E_VISIBLE === '1'
export const REPO = path.resolve(__dirname, '../..')
export const REAL = MODE === 'real'

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export async function api<T = unknown>(base: string, route: string, body?: unknown, method?: string): Promise<{ status: number; body: T; ms: number }> {
  const started = Date.now()
  const res = await fetch(`${base}${route}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(Number(process.env.E2E_HTTP_TIMEOUT_MS ?? 25_000)),
  })
  const text = await res.text()
  let parsed: unknown = text
  try {
    parsed = JSON.parse(text)
  } catch {}
  return { status: res.status, body: parsed as T, ms: Date.now() - started }
}

export const dbg = <T = unknown>(route: string, body?: unknown, method?: string) => api<T>(DEBUG, route, body, method)
export const dev = <T = unknown>(route: string, body?: unknown, method?: string) => api<T>(DEV, route, body, method)

export interface ToolOutcome<T = Record<string, unknown>> {
  result: T & { error?: string }
  ms: number
}

export async function tool<T = Record<string, unknown>>(name: string, args: unknown = {}): Promise<ToolOutcome<T>> {
  const r = await dbg<T & { error?: string }>('/tool', { name, args })
  return { result: r.body, ms: r.ms }
}

export interface AgentChipView {
  id: string
  kind: string
  title: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  summary?: string
  result?: { kind: string; report?: { verdict: string; confidence: number; redFlags: { phrase: string; why: string }[]; advice: string[]; humanHelp: string }; text?: string }
}

export interface StateView {
  persona: string | null
  phase: string
  micMuted: boolean
  level: 1 | 2 | 3 | 4
  levelLocked: boolean
  skill?: { id: string; name: string; step: number; stepCount: number }
  captions: { speaker: string; text: string; final: boolean }[]
  agents: AgentChipView[]
  settings: Record<string, unknown> & { doItForMeAllowed: boolean; demoMode: boolean }
  lastError?: string
  pendingConfirm?: { id: string; question: string; options: [string, string] }
}

export const state = async () => (await dbg<StateView>('/state')).body

export async function waitFor<T>(what: string, fn: () => Promise<T | null | undefined | false> | T | null | undefined | false, timeoutMs = 8000, everyMs = 150): Promise<T> {
  const deadline = Date.now() + timeoutMs
  let last: unknown
  while (Date.now() < deadline) {
    try {
      const v = await fn()
      if (v) return v as T
    } catch (err) {
      last = err
    }
    await sleep(everyMs)
  }
  throw new Error(`timed out after ${timeoutMs}ms waiting for: ${what}${last ? ` (last error: ${String(last)})` : ''}`)
}

// ---- overlay call log (QA dev hook) ----
export interface OverlayOp {
  t: number
  op: 'show' | 'clear' | 'caption' | 'chip'
  annotations?: { id: string; kind: string; tone: string; box?: NormBox; to?: unknown; label?: string; boxes?: NormBox[] }[]
  ids?: string[]
  text?: string
  level?: number
}
export interface NormBox {
  xmin: number
  ymin: number
  xmax: number
  ymax: number
}
export const overlayLog = async () => (await dev<OverlayOp[]>('/dev/overlay/log')).body
export const clearOverlayLog = () => dev('/dev/overlay/log/clear', {})
export const injectLog = async () => (await dev<{ t: number; text: string }[]>('/dev/inject/log')).body
export const clearInjectLog = () => dev('/dev/inject/log/clear', {})
export const fetchLog = async () => (await dev<FetchEntry[]>('/dev/fetch/log')).body
export interface FetchEntry {
  t: number
  path: string
  method: string
  model: string | null
  status: number | string
  ms: number
  bodyKeys: string[]
  store: boolean | null
  hasImage: boolean
  faulted?: string
}
export const setFault = (spec: { match: string; mode: string; count?: number; delayMs?: number }) => dev('/dev/fault', spec)
export const clearFault = () => dev('/dev/fault', { match: '*', mode: 'off' })

export function shownBoxes(log: OverlayOp[], kind = 'ring'): NormBox[] {
  return log.filter((o) => o.op === 'show').flatMap((o) => (o.annotations ?? []).filter((a) => a.kind === kind && a.box).map((a) => a.box as NormBox))
}

// Reset to a known idle state between scenarios.
export async function resetApp(): Promise<void> {
  await dbg('/stop', {})
  await tool('clear_annotations')
  await clearFault()
  await dbg('/settings', { patch: { helpLevelMode: 'auto', demoMode: true, doItForMeAllowed: false } })
  await clearOverlayLog()
  await clearInjectLog()
}

// Raw http request so tests can set Host/Origin headers that fetch forbids or rewrites.
export function rawRequest(opts: { port: number; host?: string; headers?: Record<string, string>; method?: string; path?: string; body?: string; hostname?: string }): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: opts.hostname ?? '127.0.0.1', port: opts.port, method: opts.method ?? 'GET', path: opts.path ?? '/state', headers: { ...(opts.host ? { host: opts.host } : {}), ...opts.headers } },
      (res) => {
        const chunks: Buffer[] = []
        res.on('data', (c: Buffer) => chunks.push(c))
        res.on('end', () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString('utf8') }))
      },
    )
    req.on('error', reject)
    req.setTimeout(5000, () => req.destroy(new Error('timeout')))
    if (opts.body) req.write(opts.body)
    req.end()
  })
}

// Saves dock.png + overlay.png under docs/qa-shots for visual review (UX defects). Never throws.
export async function saveShots(tag: string): Promise<void> {
  try {
    const dir = path.join(REPO, 'docs', 'qa-shots')
    fs.mkdirSync(dir, { recursive: true })
    for (const [name, route] of [['dock', '/dock.png'], ['overlay', '/overlay.png']] as const) {
      const res = await fetch(`${DEBUG}${route}`)
      if (res.ok) fs.writeFileSync(path.join(dir, `${tag}-${name}.png`), Buffer.from(await res.arrayBuffer()))
    }
  } catch {
    // screenshots are evidence only
  }
}

export const portOf = (url: string) => Number(new URL(url).port)

// Plain-English check for user-facing error text: no stack frames, raw JSON, SDK class names or status codes.
const UGLY = /\bat [\w.<>$ ]+ \(.*:\d+:\d+\)|node_modules|\bApiError\b|ClientError|\{\s*"error"|\bStatus:?\s*\d{3}\b|\b[45]\d\d\b.*\b(INTERNAL|RESOURCE_EXHAUSTED|UNAUTHENTICATED)\b|undefined|\[object |TypeError|AbortError|fetch failed|GoogleGenAI|ECONN|ENOTFOUND|stack/i
export function uglyText(text: string | undefined | null): string | null {
  if (!text) return null
  return UGLY.test(text) ? text.slice(0, 160) : null
}

// ---- tiny PNG decoder (8-bit RGBA/RGB, non-interlaced) for overlay.png pixel checks ----
export interface Raster {
  width: number
  height: number
  channels: number
  data: Buffer
}
export function decodePng(buf: Buffer): Raster {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error('not a PNG')
  let off = 8
  let width = 0
  let height = 0
  let colorType = 0
  const idat: Buffer[] = []
  while (off < buf.length) {
    const len = buf.readUInt32BE(off)
    const type = buf.toString('ascii', off + 4, off + 8)
    const data = buf.subarray(off + 8, off + 8 + len)
    if (type === 'IHDR') {
      width = data.readUInt32BE(0)
      height = data.readUInt32BE(4)
      colorType = data[9]
      if (data[8] !== 8 || data[12] !== 0) throw new Error('unsupported PNG (need 8-bit non-interlaced)')
    } else if (type === 'IDAT') idat.push(data)
    else if (type === 'IEND') break
    off += 12 + len
  }
  const channels = colorType === 6 ? 4 : colorType === 2 ? 3 : colorType === 0 ? 1 : colorType === 4 ? 2 : 0
  if (!channels) throw new Error(`unsupported PNG colour type ${colorType}`)
  const raw = zlib.inflateSync(Buffer.concat(idat))
  const stride = width * channels
  const out = Buffer.alloc(height * stride)
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)]
    const src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1))
    const dst = out.subarray(y * stride, (y + 1) * stride)
    const prev = y > 0 ? out.subarray((y - 1) * stride, y * stride) : null
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? dst[x - channels] : 0
      const b = prev ? prev[x] : 0
      const c = prev && x >= channels ? prev[x - channels] : 0
      let v = src[x]
      if (filter === 1) v += a
      else if (filter === 2) v += b
      else if (filter === 3) v += (a + b) >> 1
      else if (filter === 4) {
        const p = a + b - c
        const pa = Math.abs(p - a)
        const pb = Math.abs(p - b)
        const pc = Math.abs(p - c)
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c
      }
      dst[x] = v & 255
    }
  }
  return { width, height, channels, data: out }
}

// Bounding box (px) of every pixel that is not fully transparent (needs RGBA), or null when the overlay is empty.
export function opaqueBounds(r: Raster, minAlpha = 24): { x: number; y: number; w: number; h: number; count: number } | null {
  if (r.channels !== 4) return null
  let x0 = r.width
  let y0 = r.height
  let x1 = -1
  let y1 = -1
  let count = 0
  for (let y = 0; y < r.height; y++) {
    for (let x = 0; x < r.width; x++) {
      if (r.data[(y * r.width + x) * 4 + 3] >= minAlpha) {
        count++
        if (x < x0) x0 = x
        if (x > x1) x1 = x
        if (y < y0) y0 = y
        if (y > y1) y1 = y
      }
    }
  }
  return count ? { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1, count } : null
}

// Flood-fills the not-inked area around (cx, cy). When the annotation is a closed ring around that point the fill stays inside and
// its bounds are the ring's inner hole (px); when the fill reaches the image border the point is not enclosed (null).
export function enclosedHole(r: Raster, cx: number, cy: number, inkAlpha = 120): { x: number; y: number; w: number; h: number } | null {
  if (r.channels !== 4) return null
  const w = r.width
  const h = r.height
  const start = Math.round(cy) * w + Math.round(cx)
  const ink = (i: number) => r.data[i * 4 + 3] >= inkAlpha
  if (start < 0 || start >= w * h || ink(start)) return null
  const seen = new Uint8Array(w * h)
  const stack = new Int32Array(w * h)
  let sp = 0
  stack[sp++] = start
  seen[start] = 1
  let x0 = w
  let y0 = h
  let x1 = -1
  let y1 = -1
  while (sp > 0) {
    const i = stack[--sp]
    const x = i % w
    const y = (i - x) / w
    if (x === 0 || y === 0 || x === w - 1 || y === h - 1) return null
    if (x < x0) x0 = x
    if (x > x1) x1 = x
    if (y < y0) y0 = y
    if (y > y1) y1 = y
    for (const n of [i - 1, i + 1, i - w, i + w]) {
      if (!seen[n] && !ink(n)) {
        seen[n] = 1
        stack[sp++] = n
      }
    }
  }
  return { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 }
}

export function iou(a: NormBox, b: NormBox): number {
  const ix = Math.max(0, Math.min(a.xmax, b.xmax) - Math.max(a.xmin, b.xmin))
  const iy = Math.max(0, Math.min(a.ymax, b.ymax) - Math.max(a.ymin, b.ymin))
  const inter = ix * iy
  const union = (a.xmax - a.xmin) * (a.ymax - a.ymin) + (b.xmax - b.xmin) * (b.ymax - b.ymin) - inter
  return union > 0 ? inter / union : 0
}

export const centre = (b: NormBox) => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })
export const insideBox = (p: { x: number; y: number }, b: NormBox) => p.x >= b.xmin && p.x <= b.xmax && p.y >= b.ymin && p.y <= b.ymax

export function percentile(values: number[], p: number): number {
  if (!values.length) return NaN
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))]
}

export function readKeyForScan(): string | null {
  try {
    const m = /^GEMINI_API_KEY=(.+)$/m.exec(fs.readFileSync(path.join(REPO, '.env'), 'utf8'))
    const v = m?.[1].trim().replace(/^['"]|['"]$/g, '')
    return v && v.length > 8 ? v : null
  } catch {
    return null
  }
}
