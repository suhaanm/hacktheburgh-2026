// The sizing maths for the Knack main window, without Electron: a calm default (about 1120 by 740, never more than 80% of the work area of the display the
// worker is on), a floor (881 by 600; see MIN_SIZE), centred, and a remembered size and position per display that is always pulled back inside the work area.
// Electron's screen module only supplies the numbers; main-window.ts calls these.

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}
export interface Size {
  width: number
  height: number
}

export const DEFAULT_SIZE: Size = { width: 1120, height: 740 }
// 881, not 880: the dashboard switches to its narrow, menu-button layout at 880 px and below (eight media queries), and the smallest window should still
// show the wide one.
export const MIN_SIZE: Size = { width: 881, height: 600 }
/** The first-run window is at most this share of the work area, so it never looks like a full-screen takeover. */
export const WORK_AREA_SHARE = 0.8

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n)
export const isRect = (r: unknown): r is Rect => typeof r === 'object' && r !== null && finite((r as Rect).x) && finite((r as Rect).y) && finite((r as Rect).width) && finite((r as Rect).height) && (r as Rect).width > 0 && (r as Rect).height > 0

/** The smallest the window may be on this display: MIN_SIZE, but never larger than the work area itself (small laptops, scaled displays). */
export function minSizeFor(workArea: Size): Size {
  return { width: Math.min(MIN_SIZE.width, Math.floor(workArea.width)), height: Math.min(MIN_SIZE.height, Math.floor(workArea.height)) }
}

/** The first-run size: the default, held to 80% of the work area, and not below the minimum (which itself never exceeds the work area). */
export function defaultSize(workArea: Size): Size {
  const min = minSizeFor(workArea)
  const cap = (value: number, share: number, floor: number): number => Math.max(floor, Math.min(value, Math.floor(share)))
  return {
    width: cap(DEFAULT_SIZE.width, workArea.width * WORK_AREA_SHARE, min.width),
    height: cap(DEFAULT_SIZE.height, workArea.height * WORK_AREA_SHARE, min.height),
  }
}

/** A window of this size centred in the work area. */
export function centred(workArea: Rect, size: Size): Rect {
  return {
    x: Math.round(workArea.x + (workArea.width - size.width) / 2),
    y: Math.round(workArea.y + (workArea.height - size.height) / 2),
    width: size.width,
    height: size.height,
  }
}

/** Pulls a rectangle inside the work area: size within [minimum, work area], position so that all of it is on this display. */
export function clampToWorkArea(r: Rect, workArea: Rect): Rect {
  const min = minSizeFor(workArea)
  const width = Math.round(Math.min(Math.max(r.width, min.width), workArea.width))
  const height = Math.round(Math.min(Math.max(r.height, min.height), workArea.height))
  const x = Math.round(Math.min(Math.max(r.x, workArea.x), workArea.x + workArea.width - width))
  const y = Math.round(Math.min(Math.max(r.y, workArea.y), workArea.y + workArea.height - height))
  return { x, y, width, height }
}

/** Where the window opens on this display: the remembered rectangle for it (clamped), else the default size, centred. */
export function initialBounds(workArea: Rect, saved?: Rect | null): Rect {
  if (saved && isRect(saved)) return clampToWorkArea(saved, workArea)
  return centred(workArea, defaultSize(workArea))
}

export interface DisplayLike {
  id: number
  workArea: Rect
}

/** The display a point is on (the cursor at launch), else the nearest by centre distance, else the first. */
export function displayAtPoint<D extends DisplayLike>(displays: readonly D[], point: { x: number; y: number }): D | undefined {
  const inside = displays.find((d) => point.x >= d.workArea.x && point.x < d.workArea.x + d.workArea.width && point.y >= d.workArea.y && point.y < d.workArea.y + d.workArea.height)
  if (inside) return inside
  const dist = (d: D): number => Math.hypot(d.workArea.x + d.workArea.width / 2 - point.x, d.workArea.y + d.workArea.height / 2 - point.y)
  return [...displays].sort((a, b) => dist(a) - dist(b))[0]
}

/** The display a window mostly sits on (largest overlap), for remembering where the worker put it. */
export function displayForBounds<D extends DisplayLike>(displays: readonly D[], bounds: Rect): D | undefined {
  const overlap = (d: D): number => {
    const w = Math.min(bounds.x + bounds.width, d.workArea.x + d.workArea.width) - Math.max(bounds.x, d.workArea.x)
    const h = Math.min(bounds.y + bounds.height, d.workArea.y + d.workArea.height) - Math.max(bounds.y, d.workArea.y)
    return w > 0 && h > 0 ? w * h : 0
  }
  const best = [...displays].sort((a, b) => overlap(b) - overlap(a))[0]
  return best && overlap(best) > 0 ? best : displayAtPoint(displays, { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 })
}
