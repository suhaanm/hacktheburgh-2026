// Pointing that needs NO Screen Recording permission. `point_at(description)` is answered by code, in this order:
//   1. the Knack window itself (our own page: read its visible controls through the window's own web contents, match by name);
//   2. a browser tab with the Knack extension (DOM grounding: the extension measures the element, no pixels);
//   3. only then the vision route (a screen picture), which needs Screen Recording and the worker's screen consent.
// Steps 1 and 2 never capture the screen, never send an image anywhere, and return geometry only. Step 3 is wrapped by `createScreenGate`: with no
// Screen Recording permission it does not even try, and it tells the worker why once, on a card with a button (see wake/controller.ts).
//
// The description is the model's words, so it is only ever used to LOOK UP something on the page (a name match); what is drawn is the element's own
// box, checked for size, and the model hears only found true or false.
import type { DisplayInfo } from '../dom-ground/rect-map'
import { mapAnswer } from '../dom-ground/rect-map'
import type { DomGrounder } from '../dom-ground/dom-grounder'
import type { DomTarget, XY } from '../dom-ground/protocol'
import type { GroundAnswer, GroundPort, GroundRequest } from './ports'

// ------------------------------------------------------------------------------------------------ what a description is made of
const WORDS_THAT_DO_NOT_NAME_THINGS = new Set([
  'the', 'a', 'an', 'this', 'that', 'these', 'those', 'of', 'in', 'on', 'at', 'to', 'for', 'my', 'your', 'our', 'please', 'here', 'there', 'one', 'and', 'or', 'with',
  'green', 'red', 'blue', 'grey', 'gray', 'yellow', 'orange', 'purple', 'black', 'white', 'pink', 'big', 'small', 'large', 'little', 'top', 'bottom', 'left', 'right', 'first', 'second',
  'third', 'last', 'next', 'new', 'main', 'side', 'sidebar', 'bar', 'list', 'area', 'part', 'section', 'row', 'button', 'link', 'tab', 'field', 'box', 'input', 'icon', 'toggle', 'switch',
  'checkbox', 'dropdown', 'card', 'panel', 'header', 'footer', 'page', 'screen', 'window', 'menu', 'option', 'item', 'thing', 'text', 'label', 'entry', 'name',
])

/** The words of a description that could be part of an element's name: lower case, no colours, positions or kinds of control. At most 6. */
export function nameTokens(description: string): string[] {
  const out: string[] = []
  for (const w of description.toLowerCase().replace(/[‘’]/g, "'").split(/[^a-z0-9']+/)) {
    const t = w.replace(/^'+|'+$/g, '')
    if (t && !WORDS_THAT_DO_NOT_NAME_THINGS.has(t) && !out.includes(t)) out.push(t)
    if (out.length >= 6) break
  }
  return out
}

const ROLE_BY_NOUN: Array<[RegExp, string]> = [
  [/\b(checkbox)\b/i, 'checkbox'],
  [/\b(toggle|switch)\b/i, 'switch'],
  [/\b(field|box|input|textbox)\b/i, 'textbox'],
  [/\b(tab)\b/i, 'tab'],
  [/\b(link)\b/i, 'link'],
  [/\b(menu item|option)\b/i, 'menuitem'],
  [/\b(button)\b/i, 'button'],
]

/** Up to three (role, name) wants for the extension, which matches the accessible name exactly: the named role first, then the usual two. */
export function domTargets(description: string): DomTarget[] {
  const tokens = nameTokens(description)
  if (tokens.length === 0) return []
  const name = tokens.join(' ').slice(0, 80)
  const guess = ROLE_BY_NOUN.find(([re]) => re.test(description))?.[1]
  const roles = [...new Set([...(guess ? [guess] : []), 'button', 'link'])].slice(0, 3)
  return roles.map((role) => ({ role, name }))
}

// ------------------------------------------------------------------------------------------------ 2. a browser tab with the extension
export interface DomPointDeps {
  grounder: Pick<DomGrounder, 'request'>
  display: () => DisplayInfo
  calibration?: XY
  /** False when the extension has not been seen lately: answer null at once instead of waiting for a timeout. Absent: always ask. */
  extensionPresent?: () => boolean
  timeoutMs?: number
}

export function createDomPointPort(d: DomPointDeps): GroundPort {
  return {
    async ground(req: GroundRequest): Promise<GroundAnswer | null> {
      const asked = req.menu.find((m) => m.id === 't0')
      if (!asked || (d.extensionPresent && !d.extensionPresent())) return null
      for (const target of domTargets(asked.label)) {
        const out = await d.grounder.request(target, { timeoutMs: d.timeoutMs ?? 1500 })
        if (out.kind !== 'answer' || !out.answer.found) continue
        const m = mapAnswer(out.answer, { display: d.display(), calibration: d.calibration })
        if (!m.ok) continue
        return { available: ['t0'], chosen: 't0', box_2d: [m.norm.ymin, m.norm.xmin, m.norm.ymax, m.norm.xmax], confidence: 0.95, source: 'dom' }
      }
      return null
    },
  }
}

// ------------------------------------------------------------------------------------------------ 1. the Knack window
/** A visible control of the Knack window: its name (our own interface text, at most 80 characters, kept in memory and never logged) and its box in CSS pixels. */
export interface KnackElement {
  name: string
  x: number
  y: number
  w: number
  h: number
}

/** Run inside the Knack window's page (read only): the visible links, buttons, tabs and switches with their names and boxes. At most 150. */
export const COLLECT_KNACK_ELEMENTS_JS = `(() => {
  const sel = 'a[href],button,[role="button"],[role="link"],[role="tab"],[role="menuitem"],[role="switch"],[role="checkbox"],input,select,textarea,summary'
  const out = []
  const vw = window.innerWidth, vh = window.innerHeight
  for (const el of document.querySelectorAll(sel)) {
    if (out.length >= 150) break
    if (el instanceof HTMLInputElement && el.type === 'password') continue
    const r = el.getBoundingClientRect()
    if (r.width < 8 || r.height < 8 || r.bottom <= 0 || r.right <= 0 || r.top >= vh || r.left >= vw) continue
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue
    const raw = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder') || el.innerText || ''
    const name = String(raw).replace(/\\s+/g, ' ').trim().slice(0, 80)
    if (!name) continue
    out.push({ name, x: r.left, y: r.top, w: r.width, h: r.height })
  }
  return out
})()`

const fin = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n)

/** What the page returned, strictly: each entry needs a short name and four finite numbers; anything else is dropped. */
export function parseKnackElements(raw: unknown): KnackElement[] {
  if (!Array.isArray(raw)) return []
  const out: KnackElement[] = []
  for (const e of raw.slice(0, 150)) {
    if (typeof e !== 'object' || e === null) continue
    const o = e as Record<string, unknown>
    if (typeof o.name !== 'string' || o.name.length === 0 || o.name.length > 80 || !fin(o.x) || !fin(o.y) || !fin(o.w) || !fin(o.h) || o.w <= 0 || o.h <= 0) continue
    out.push({ name: o.name, x: o.x, y: o.y, w: o.w, h: o.h })
  }
  return out
}

const wordsOf = (s: string): string[] => s.toLowerCase().split(/[^a-z0-9']+/).map((w) => w.replace(/^'+|'+$/g, '')).filter(Boolean)

/**
 * The control whose name carries every naming word of the description ("the Needs you list in the sidebar" -> needs, you), preferring the shortest
 * name. Null when no control does, or when two equally short names tie (never a guess).
 */
export function pickByName(description: string, elements: readonly KnackElement[]): KnackElement | null {
  const want = nameTokens(description)
  if (want.length === 0) return null
  const scored = elements
    .map((e) => ({ e, words: wordsOf(e.name) }))
    .filter(({ words }) => want.every((w) => words.includes(w)))
    .map(({ e, words }) => ({ e, extra: words.length - want.length }))
    .sort((a, b) => a.extra - b.extra)
  if (scored.length === 0) return null
  if (scored.length > 1 && scored[1].extra === scored[0].extra) return null
  return scored[0].e
}

export interface KnackWindowGroundDeps {
  /** The visible controls of the Knack window, or null when it is not on screen (hidden, minimised, closed). */
  elements: () => Promise<KnackElement[] | null>
  /** The window's content area in screen points and the page zoom (CSS px to points), or null. */
  content: () => { x: number; y: number; zoom: number } | null
  display: () => DisplayInfo
}

export function createKnackWindowGround(d: KnackWindowGroundDeps): GroundPort {
  return {
    async ground(req: GroundRequest): Promise<GroundAnswer | null> {
      const asked = req.menu.find((m) => m.id === 't0')
      const origin = d.content()
      if (!asked || !origin) return null
      let els: KnackElement[] | null
      try {
        els = await d.elements()
      } catch {
        return null
      }
      const hit = els ? pickByName(asked.label, els) : null
      if (!hit) return null
      const b = d.display().bounds
      const x0 = origin.x + hit.x * origin.zoom
      const y0 = origin.y + hit.y * origin.zoom
      const x1 = x0 + hit.w * origin.zoom
      const y1 = y0 + hit.h * origin.zoom
      const clamp = (n: number): number => Math.min(1000, Math.max(0, n))
      const box: [number, number, number, number] = [clamp(((y0 - b.y) / b.height) * 1000), clamp(((x0 - b.x) / b.width) * 1000), clamp(((y1 - b.y) / b.height) * 1000), clamp(((x1 - b.x) / b.width) * 1000)]
      return { available: ['t0'], chosen: 't0', box_2d: box, confidence: 0.95, source: 'dom' }
    },
  }
}

// ------------------------------------------------------------------------------------------------ 3. the screen picture, behind its permission
export interface ScreenGateDeps {
  /** macOS Screen Recording status: 'granted' or anything else. */
  status: () => string
  /** Called once per call that was turned away for want of the permission: the caller shows the card (and rate-limits it). */
  onMissing: () => void
}

/** The vision route only when Screen Recording is granted. Otherwise it answers null at once, with no capture and no request, and says why. */
export function createScreenGate(vision: GroundPort | null, d: ScreenGateDeps): GroundPort | null {
  if (!vision) return null
  return {
    async ground(req) {
      if (d.status() !== 'granted') {
        d.onMissing()
        return null
      }
      return vision.ground(req)
    },
  }
}

/** Chains grounders: the first that answers wins. Any may be null; a thrown error counts as no answer. */
export function chainGround(...ports: Array<GroundPort | null>): GroundPort | null {
  const live = ports.filter((p): p is GroundPort => p !== null)
  if (live.length === 0) return null
  return {
    async ground(req) {
      for (const p of live) {
        const a = await p.ground(req).catch(() => null)
        if (a && a.chosen && a.box_2d) return a
      }
      return null
    },
  }
}
