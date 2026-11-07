// From what the extension measured to a place on the screen (and to the overlay's 0-1000 coordinates), plus how stale it is.
// Units: the extension reports the rect in CSS pixels of the viewport; window positions are screen points (DIPs, top-left origin,
// the same space as Electron's display.bounds). On a Retina display at 100% page zoom, dpr is 2 and one CSS pixel is one point;
// page zoom z makes dpr = scaleFactor * z and one CSS pixel z points, so points per CSS pixel = dpr / scaleFactor.
import type { NormBox } from '../../shared/protocol'
import type { Rect, RectAnswer, XY } from './protocol'

export interface DisplayInfo {
  bounds: { x: number; y: number; width: number; height: number }
  scaleFactor: number
}

export interface MapOptions {
  display: DisplayInfo
  // A fixed correction in points, added last. From UNDERSTUDY_RING_OFFSET="dx,dy" (see parseCalibration) after measuring on the real machine.
  calibration?: XY
}

export type MapFailure = 'not_found' | 'frame_relative' | 'out_of_view' | 'off_display' | 'no_geometry'

export type Mapped = { ok: true; screen: Rect; norm: NormBox; zoom: number } | { ok: false; reason: MapFailure }

/** Points per CSS pixel. Within 2% of 1 snaps to 1 (rounding noise in dpr). */
export function pageZoom(dpr: number, scaleFactor: number): number {
  const z = dpr / Math.max(0.5, scaleFactor)
  const clamped = Math.min(5, Math.max(0.25, z))
  return Math.abs(clamped - 1) < 0.02 ? 1 : clamped
}

/** Screen position (points) of the viewport's top-left corner. Zoom-correct when the extension sends outer, viewport and screen; otherwise its window_offset. */
export function viewportOrigin(a: RectAnswer, zoom: number): XY {
  if (a.outer && a.viewport && a.screen) {
    const side = Math.max(0, (a.outer.w - a.viewport.w * zoom) / 2)
    const chrome = Math.max(0, a.outer.h - a.viewport.h * zoom - side)
    return { x: a.screen.x + side, y: a.screen.y + chrome }
  }
  return a.window_offset ?? { x: 0, y: 0 }
}

export function toNormBox(r: Rect, display: DisplayInfo['bounds']): NormBox | null {
  const clamp = (n: number) => Math.min(1000, Math.max(0, n))
  const box = {
    xmin: clamp(((r.x - display.x) / display.width) * 1000),
    ymin: clamp(((r.y - display.y) / display.height) * 1000),
    xmax: clamp(((r.x + r.w - display.x) / display.width) * 1000),
    ymax: clamp(((r.y + r.h - display.y) / display.height) * 1000),
  }
  return box.xmax - box.xmin < 1 || box.ymax - box.ymin < 1 ? null : box
}

const MIN_SIDE_NORM = 6 // about 10 points on a 1700-wide display: a ring needs something to surround

export function mapAnswer(a: RectAnswer, opts: MapOptions): Mapped {
  if (!a.found || !a.rect || a.dpr === undefined) return { ok: false, reason: a.found ? 'no_geometry' : 'not_found' }
  // A rect from a sub-frame is relative to that frame; this app has no frame offsets, so it cannot place it.
  if (a.frame_id !== 'top') return { ok: false, reason: 'frame_relative' }
  const zoom = pageZoom(a.dpr, opts.display.scaleFactor)
  const origin = viewportOrigin(a, zoom)
  // Scrolled out of view: the viewport (when known) says whether any part of the element is inside it.
  if (a.viewport && (a.rect.x + a.rect.w <= 0 || a.rect.y + a.rect.h <= 0 || a.rect.x >= a.viewport.w || a.rect.y >= a.viewport.h)) return { ok: false, reason: 'out_of_view' }
  const cal = opts.calibration ?? { x: 0, y: 0 }
  const screen: Rect = { x: origin.x + a.rect.x * zoom + cal.x, y: origin.y + a.rect.y * zoom + cal.y, w: a.rect.w * zoom, h: a.rect.h * zoom }
  const norm = toNormBox(screen, opts.display.bounds)
  if (!norm) return { ok: false, reason: 'off_display' }
  if (norm.xmax - norm.xmin < MIN_SIDE_NORM || norm.ymax - norm.ymin < MIN_SIDE_NORM) {
    // Very small elements still get a ring: grow to the minimum around the centre.
    const cx = (norm.xmin + norm.xmax) / 2
    const cy = (norm.ymin + norm.ymax) / 2
    const h = MIN_SIDE_NORM / 2
    return { ok: true, screen, zoom, norm: { xmin: Math.max(0, cx - h), ymin: Math.max(0, cy - h), xmax: Math.min(1000, cx + h), ymax: Math.min(1000, cy + h) } }
  }
  return { ok: true, screen, norm, zoom }
}

/** Age of the measurement now: how old it was when it was posted, plus how long ago it arrived. */
export const ageNow = (a: Pick<RectAnswer, 'age_ms'>, receivedAt: number, now: number): number => a.age_ms + Math.max(0, now - receivedAt)

export const sameScroll = (a: XY | undefined, b: XY | undefined): boolean => !!a && !!b && Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1

/** "dx,dy" in points -> a calibration, or undefined when absent or malformed. */
export function parseCalibration(value: string | undefined): XY | undefined {
  const m = /^\s*(-?\d{1,4}(?:\.\d+)?)\s*,\s*(-?\d{1,4}(?:\.\d+)?)\s*$/.exec(value ?? '')
  return m ? { x: Number(m[1]), y: Number(m[2]) } : undefined
}
