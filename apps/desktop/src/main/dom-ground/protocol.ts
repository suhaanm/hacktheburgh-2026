// The element-rect protocol with the browser extension (packages/schema/ext_rect.schema.json).
//   The extension polls GET /ext/want on this app; it answers 200 with a RectWant or 204 for "nothing wanted".
//   It answers with POST /ext/rect carrying a RectAnswer. Geometry only: no page text, no URLs, no field values.
// Additive fields this app understands when the extension sends them (proposed as a contract change, ignored when absent):
//   viewport {w,h}  innerWidth/innerHeight in CSS px;  outer {w,h}  outerWidth/outerHeight;  screen {x,y}  screenX/screenY.
// With them the desktop corrects the viewport origin for page zoom and knows when an element is scrolled out of view.
//   content [[y0,x0,y1,x1], ...]  up to 80 boxes (one per visible text line and per visible control) as integers on a 0..1000 grid of the
//   answered rect's viewport (viewport.w by viewport.h), in the rect's frame, in reading order. Numbers only. rect-map.mapContentRects puts them on the screen.
export interface RectWant {
  request_id: string
  frame_id: string
  label_hash?: string
  role?: string
  name?: string
  // A capture ZONE (the coach brain addresses elements by zone; the extension resolves it from data-understudy-zone or its capture
  // config). Proposed as an additive field of RectWant; until the extension understands it, a zone want simply gets no answer.
  zone?: string
}

export interface XY {
  x: number
  y: number
}
export interface Size {
  w: number
  h: number
}
export interface Rect extends XY, Size {}

/** One box of page content: [y0, x0, y1, x1], integers 0..1000 on the grid of the answered rect's viewport, y0 <= y1 and x0 <= x1. */
export type ContentBox = [number, number, number, number]
/** The most boxes an answer may carry (the schema's maxItems). */
export const CONTENT_MAX = 80

export interface RectAnswer {
  request_id: string
  frame_id: string
  found: boolean
  rect?: Rect
  window_offset?: XY
  scroll?: XY
  dpr?: number
  age_ms: number
  viewport?: Size
  outer?: Size
  screen?: XY
  // Absent when the extension did not send the field; an array (possibly empty) when it did.
  content?: ContentBox[]
}

// label_hash / role+name: an element by its salted label hash or its accessible name. zone: a capture zone, with the brain's hints
// kept here (only `zone` goes into the want; the hints are for logs and for a later protocol version).
export type DomTarget = { label_hash: string } | { role: string; name: string } | { zone: string; label_hint?: string; role_hint?: string }

export const REQUEST_ID_RE = /^[A-Za-z0-9_.:-]{1,64}$/
export const FRAME_RE = /^(top|f[0-9]{1,4})$/
export const LABEL_HASH_RE = /^h:[0-9a-f]{4,16}$/
export const ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/
export const ZONE_RE = /^[a-z][a-z0-9_]{1,30}$/ // the schema's own pattern (ext_rect.schema.json)

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const xy = (v: unknown): XY | null => (isObj(v) && fin(v.x) && fin(v.y) ? { x: v.x, y: v.y } : null)
const size = (v: unknown): Size | null => (isObj(v) && fin(v.w) && fin(v.h) && v.w >= 0 && v.h >= 0 ? { w: v.w, h: v.h } : null)

export function targetProblem(t: unknown): string | null {
  if (!isObj(t)) return 'target must be an object'
  const hasZone = t.zone !== undefined
  const hasHash = t.label_hash !== undefined
  const hasName = t.role !== undefined || t.name !== undefined
  if (Number(hasZone) + Number(hasHash) + Number(hasName) !== 1) return 'give exactly one of zone, label_hash, or role and name'
  if (hasZone) {
    if (typeof t.zone !== 'string' || !ZONE_RE.test(t.zone)) return 'bad zone'
    if (t.label_hint !== undefined && (typeof t.label_hint !== 'string' || t.label_hint.length > 80)) return 'bad label_hint'
    if (t.role_hint !== undefined && (typeof t.role_hint !== 'string' || !ROLE_RE.test(t.role_hint))) return 'bad role_hint'
    return null
  }
  if (hasHash) return typeof t.label_hash === 'string' && LABEL_HASH_RE.test(t.label_hash) ? null : 'bad label_hash'
  if (typeof t.role !== 'string' || !ROLE_RE.test(t.role)) return 'bad role'
  if (typeof t.name !== 'string' || t.name.length < 1 || t.name.length > 80) return 'bad name'
  return null
}

export function toTarget(t: unknown): DomTarget | null {
  if (targetProblem(t) !== null) return null
  const o = t as Record<string, string | undefined>
  if (o.zone) return { zone: o.zone, ...(o.label_hint ? { label_hint: o.label_hint } : {}), ...(o.role_hint ? { role_hint: o.role_hint } : {}) }
  return o.label_hash ? { label_hash: o.label_hash } : { role: o.role as string, name: o.name as string }
}

export function wantFor(target: DomTarget, request_id: string, frame_id = 'top'): RectWant {
  // A zone want carries only the zone: the extension's schema has no other zone fields.
  if ('zone' in target) return { request_id, frame_id, zone: target.zone }
  return { request_id, frame_id, ...target }
}

/**
 * The `content` field of an answer, strictly: not an array, or more than 80 entries, gives []; each entry must be exactly four finite
 * integers, which are clamped to 0..1000, and y0 <= y1 and x0 <= x1 must hold or the entry is dropped. Anything else in the array is
 * dropped. Never throws (a hostile or odd value only costs the field).
 */
export function parseContent(v: unknown): ContentBox[] {
  const out: ContentBox[] = []
  try {
    if (!Array.isArray(v) || v.length > CONTENT_MAX) return out
    for (let i = 0; i < v.length; i++) {
      const e: unknown = v[i]
      if (!Array.isArray(e) || e.length !== 4) continue
      const [a, b, c, d] = e as unknown[]
      if (!Number.isInteger(a) || !Number.isInteger(b) || !Number.isInteger(c) || !Number.isInteger(d)) continue
      const clamp = (n: unknown): number => Math.min(1000, Math.max(0, n as number))
      const box: ContentBox = [clamp(a), clamp(b), clamp(c), clamp(d)]
      if (box[0] <= box[2] && box[1] <= box[3]) out.push(box)
    }
  } catch {
    return []
  }
  return out
}

/** Parses a POST /ext/rect body; null when it does not satisfy the schema (unknown keys are tolerated and dropped). */
export function parseAnswer(raw: unknown): RectAnswer | null {
  if (!isObj(raw)) return null
  if (typeof raw.request_id !== 'string' || !REQUEST_ID_RE.test(raw.request_id)) return null
  if (typeof raw.frame_id !== 'string' || !FRAME_RE.test(raw.frame_id)) return null
  if (!fin(raw.age_ms) || raw.age_ms < 0) return null
  const found = raw.found === undefined ? true : raw.found
  if (typeof found !== 'boolean') return null
  const base = { request_id: raw.request_id, frame_id: raw.frame_id, age_ms: raw.age_ms }
  if (!found) return { ...base, found: false }
  const rect = isObj(raw.rect) && fin(raw.rect.x) && fin(raw.rect.y) && fin(raw.rect.w) && fin(raw.rect.h) && raw.rect.w >= 0 && raw.rect.h >= 0 ? { x: raw.rect.x, y: raw.rect.y, w: raw.rect.w, h: raw.rect.h } : null
  const window_offset = xy(raw.window_offset)
  const scroll = xy(raw.scroll)
  if (!rect || !window_offset || !scroll || !fin(raw.dpr) || raw.dpr <= 0) return null
  const viewport = size(raw.viewport)
  const outer = size(raw.outer)
  const screen = xy(raw.screen)
  let content: ContentBox[] | null = null
  try {
    if (raw.content !== undefined) content = parseContent(raw.content)
  } catch {
    content = [] // a value that cannot even be read costs the field, not the answer
  }
  return { ...base, found: true, rect, window_offset, scroll, dpr: raw.dpr, ...(viewport ? { viewport } : {}), ...(outer ? { outer } : {}), ...(screen ? { screen } : {}), ...(content ? { content } : {}) }
}
