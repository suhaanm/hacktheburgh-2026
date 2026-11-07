// The element-rect protocol with the browser extension (packages/schema/ext_rect.schema.json).
//   The extension polls GET /ext/want on this app; it answers 200 with a RectWant or 204 for "nothing wanted".
//   It answers with POST /ext/rect carrying a RectAnswer. Geometry only: no page text, no URLs, no field values.
// Additive fields this app understands when the extension sends them (proposed as a contract change, ignored when absent):
//   viewport {w,h}  innerWidth/innerHeight in CSS px;  outer {w,h}  outerWidth/outerHeight;  screen {x,y}  screenX/screenY.
// With them the desktop corrects the viewport origin for page zoom and knows when an element is scrolled out of view.
export interface RectWant {
  request_id: string
  frame_id: string
  label_hash?: string
  role?: string
  name?: string
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
}

export type DomTarget = { label_hash: string } | { role: string; name: string }

export const REQUEST_ID_RE = /^[A-Za-z0-9_.:-]{1,64}$/
export const FRAME_RE = /^(top|f[0-9]{1,4})$/
export const LABEL_HASH_RE = /^h:[0-9a-f]{4,16}$/
export const ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const xy = (v: unknown): XY | null => (isObj(v) && fin(v.x) && fin(v.y) ? { x: v.x, y: v.y } : null)
const size = (v: unknown): Size | null => (isObj(v) && fin(v.w) && fin(v.h) && v.w >= 0 && v.h >= 0 ? { w: v.w, h: v.h } : null)

export function targetProblem(t: unknown): string | null {
  if (!isObj(t)) return 'target must be an object'
  const hasHash = t.label_hash !== undefined
  const hasName = t.role !== undefined || t.name !== undefined
  if (hasHash === hasName) return 'give either label_hash or role and name'
  if (hasHash) return typeof t.label_hash === 'string' && LABEL_HASH_RE.test(t.label_hash) ? null : 'bad label_hash'
  if (typeof t.role !== 'string' || !ROLE_RE.test(t.role)) return 'bad role'
  if (typeof t.name !== 'string' || t.name.length < 1 || t.name.length > 80) return 'bad name'
  return null
}

export function toTarget(t: unknown): DomTarget | null {
  if (targetProblem(t) !== null) return null
  const o = t as Record<string, string>
  return o.label_hash ? { label_hash: o.label_hash } : { role: o.role, name: o.name }
}

export function wantFor(target: DomTarget, request_id: string, frame_id = 'top'): RectWant {
  return { request_id, frame_id, ...target }
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
  return { ...base, found: true, rect, window_offset, scroll, dpr: raw.dpr, ...(viewport ? { viewport } : {}), ...(outer ? { outer } : {}), ...(screen ? { screen } : {}) }
}
