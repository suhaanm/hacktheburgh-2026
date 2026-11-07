// Remembers the main window's size and position per display (userData/knack-window.json). A small file of numbers: no titles, no paths.
// Reads fail soft (a corrupt file is an empty one) and writes are debounced by the caller through `touch`.
import fs from 'node:fs'
import path from 'node:path'
import { isRect, type Rect } from './window-bounds'

export interface WindowState {
  version: 1
  /** Rectangle per display id (as a string), in screen coordinates. */
  displays: Record<string, Rect>
  /** The display the window was last on. */
  last?: string
}

export const EMPTY_WINDOW_STATE: WindowState = { version: 1, displays: {} }

/** Keeps only valid rectangles; anything else in the file is dropped. */
export function parseWindowState(raw: unknown): WindowState {
  if (typeof raw !== 'object' || raw === null) return { ...EMPTY_WINDOW_STATE, displays: {} }
  const r = raw as { displays?: unknown; last?: unknown }
  const displays: Record<string, Rect> = {}
  if (typeof r.displays === 'object' && r.displays !== null) {
    for (const [id, rect] of Object.entries(r.displays as Record<string, unknown>)) {
      if (/^[0-9]{1,12}$/.test(id) && isRect(rect)) displays[id] = { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    }
  }
  const last = typeof r.last === 'string' && /^[0-9]{1,12}$/.test(r.last) ? r.last : undefined
  return { version: 1, displays, ...(last ? { last } : {}) }
}

export interface WindowStateStore {
  get(displayId: number): Rect | null
  /** Remember the window's rectangle on this display (written after a short pause so a drag is one write). */
  touch(displayId: number, bounds: Rect): void
  lastDisplay(): number | null
  flush(): void
}

export interface WindowStateDeps {
  /** The file, or null to keep everything in memory (tests). */
  file: string | null
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  readFile?: (file: string) => string
  writeFile?: (file: string, data: string) => void
  delayMs?: number
}

export function createWindowStateStore(deps: WindowStateDeps): WindowStateStore {
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const read = deps.readFile ?? ((f) => fs.readFileSync(f, 'utf8'))
  const write =
    deps.writeFile ??
    ((f, data) => {
      fs.mkdirSync(path.dirname(f), { recursive: true })
      fs.writeFileSync(f, data)
    })
  let state: WindowState = { ...EMPTY_WINDOW_STATE, displays: {} }
  if (deps.file) {
    try {
      state = parseWindowState(JSON.parse(read(deps.file)))
    } catch {
      /* no file yet, or a corrupt one: start empty */
    }
  }
  let timer: unknown = null
  let dirty = false
  const flush = (): void => {
    if (timer !== null) clearT(timer)
    timer = null
    if (!dirty || !deps.file) return
    dirty = false
    try {
      write(deps.file, JSON.stringify(state))
    } catch {
      /* a failed write only forgets the position */
    }
  }
  return {
    get: (id) => state.displays[String(id)] ?? null,
    touch(id, bounds) {
      if (!isRect(bounds)) return
      state = { ...state, displays: { ...state.displays, [String(id)]: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } }, last: String(id) }
      dirty = true
      if (timer !== null) clearT(timer)
      timer = setT(flush, deps.delayMs ?? 400)
    },
    lastDisplay: () => (state.last !== undefined ? Number(state.last) : null),
    flush,
  }
}
