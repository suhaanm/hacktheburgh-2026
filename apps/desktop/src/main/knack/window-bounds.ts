// The sizing maths for the Knack main window (docs/KNACK_UX.md section 7, "The default window"), without Electron. Electron's screen module only supplies the numbers.
//
//   first launch   80% of the work area's width by 84% of its height, width held to 960..1440 and height to 600..1000, centred across, a little above centre
//                  down (40% of the free height). On a 1440 by 900 display (work area 1440 by 875): 1152 by 735.
//   minimum        800 by 560 (the dashboard's sidebar becomes an icon rail under 880 px), but never more than the work area itself.
//   remembered     size and position per display id, saved 400 ms after a move or resize; used only when at least 60% of the window is inside a display that is
//                  still there, otherwise the default is worked out again. A first launch has nothing remembered.

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

export const WINDOW_SPEC = {
  widthFraction: 0.8,
  heightFraction: 0.84,
  widthClamp: [960, 1440],
  heightClamp: [600, 1000],
  min: [800, 560],
  verticalCentreFraction: 0.4,
  restoreMinVisibleFraction: 0.6,
  saveDebounceMs: 400,
} as const
export const MIN_SIZE: Size = { width: WINDOW_SPEC.min[0], height: WINDOW_SPEC.min[1] }

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n)
export const isRect = (r: unknown): r is Rect => typeof r === 'object' && r !== null && finite((r as Rect).x) && finite((r as Rect).y) && finite((r as Rect).width) && finite((r as Rect).height) && (r as Rect).width > 0 && (r as Rect).height > 0

/** The smallest the window may be on this display: 800 by 560, but never larger than the work area itself (small laptops, scaled displays). */
export function minSizeFor(workArea: Size): Size {
  return { width: Math.min(MIN_SIZE.width, Math.floor(workArea.width)), height: Math.min(MIN_SIZE.height, Math.floor(workArea.height)) }
}

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v))

/** The first-launch size: 80 by 84 percent of the work area, held to the spec's clamps, and never larger than the work area. */
export function defaultSize(workArea: Size): Size {
  const [wlo, whi] = WINDOW_SPEC.widthClamp
  const [hlo, hhi] = WINDOW_SPEC.heightClamp
  return {
    width: Math.min(Math.floor(workArea.width), clamp(Math.round(workArea.width * WINDOW_SPEC.widthFraction), wlo, whi)),
    height: Math.min(Math.floor(workArea.height), clamp(Math.round(workArea.height * WINDOW_SPEC.heightFraction), hlo, hhi)),
  }
}

/** Centred across; down by 40% of the free height (a little above centre). */
export function placeDefault(workArea: Rect, size: Size): Rect {
  return {
    x: Math.round(workArea.x + (workArea.width - size.width) / 2),
    y: Math.round(workArea.y + (workArea.height - size.height) * WINDOW_SPEC.verticalCentreFraction),
    width: size.width,
    height: size.height,
  }
}

export const defaultBounds = (workArea: Rect): Rect => placeDefault(workArea, defaultSize(workArea))

/** Pulls a rectangle inside the work area: size within [minimum, work area], position so that all of it is on this display. */
export function clampToWorkArea(r: Rect, workArea: Rect): Rect {
  const min = minSizeFor(workArea)
  const width = Math.round(Math.min(Math.max(r.width, min.width), workArea.width))
  const height = Math.round(Math.min(Math.max(r.height, min.height), workArea.height))
  const x = Math.round(Math.min(Math.max(r.x, workArea.x), workArea.x + workArea.width - width))
  const y = Math.round(Math.min(Math.max(r.y, workArea.y), workArea.y + workArea.height - height))
  return { x, y, width, height }
}

/** How much of the rectangle (0 to 1) lies inside the work area. */
export function visibleFraction(r: Rect, workArea: Rect): number {
  const w = Math.min(r.x + r.width, workArea.x + workArea.width) - Math.max(r.x, workArea.x)
  const h = Math.min(r.y + r.height, workArea.y + workArea.height) - Math.max(r.y, workArea.y)
  return w > 0 && h > 0 ? (w * h) / (r.width * r.height) : 0
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
  const overlap = (d: D): number => visibleFraction(bounds, d.workArea) * bounds.width * bounds.height
  const best = [...displays].sort((a, b) => overlap(b) - overlap(a))[0]
  return best && overlap(best) > 0 ? best : displayAtPoint(displays, { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 })
}

export interface RestoreInput<D extends DisplayLike> {
  displays: readonly D[]
  /** The pointer, for the display to open on when nothing usable was remembered. */
  cursor: { x: number; y: number }
  /** What was remembered for a display id (null: nothing). */
  saved(displayId: number): Rect | null
  /** The display the window was last on, if it was remembered. */
  lastDisplay: number | null
}

export interface Restored {
  bounds: Rect
  displayId: number
  source: 'saved' | 'default'
}

/**
 * Where the window opens. The remembered rectangle of the display it was last on is used when at least 60% of it is still inside a display's work area (it is
 * then pulled fully inside and held to the minimum size); a display that was unplugged or a half-offscreen save gives the default on the display under the pointer.
 */
export function restoreBounds<D extends DisplayLike>(i: RestoreInput<D>): Restored | null {
  if (i.displays.length === 0) return null
  const order = [...(i.lastDisplay !== null ? [i.lastDisplay] : []), ...i.displays.map((d) => d.id)]
  for (const id of new Set(order)) {
    const r = i.saved(id)
    if (!r || !isRect(r)) continue
    // Judged against every display that is there now: a window saved on a display that has gone may still sit mostly on another one.
    const home = [...i.displays].sort((a, b) => visibleFraction(r, b.workArea) - visibleFraction(r, a.workArea))[0]!
    if (visibleFraction(r, home.workArea) >= WINDOW_SPEC.restoreMinVisibleFraction) return { bounds: clampToWorkArea(r, home.workArea), displayId: home.id, source: 'saved' }
  }
  const at = displayAtPoint(i.displays, i.cursor) ?? i.displays[0]!
  return { bounds: defaultBounds(at.workArea), displayId: at.id, source: 'default' }
}
