// Real OverlayController: validates/sanitises what is about to be drawn on the user's real screen, then forwards
// it to the overlay window over `overlay:cmd`. Contract: `show` upserts annotations by id (same id replaces the
// previous drawing); `clear()` with no ids clears every annotation; `caption` text is the whole line so far
// (a non-final line is replaced in place by the next one from the same speaker).
import type { OverlayController } from '../shared/contracts'
import { AnnotationSchema, type Annotation, type NormPoint } from '../shared/protocol'
import type { ServiceContext } from './context'

const clamp = (n: number): number => Math.min(1000, Math.max(0, n))
const point = (p: NormPoint): NormPoint => ({ x: clamp(p.x), y: clamp(p.y) })
const box = <B extends { xmin: number; ymin: number; xmax: number; ymax: number }>(b: B): B => ({
  ...b,
  xmin: clamp(Math.min(b.xmin, b.xmax)),
  xmax: clamp(Math.max(b.xmin, b.xmax)),
  ymin: clamp(Math.min(b.ymin, b.ymax)),
  ymax: clamp(Math.max(b.ymin, b.ymax)),
})

// Clamps coordinates into 0-1000 (models drift out of range) and fixes swapped box corners. Returns null if the
// annotation is malformed (NaN, wrong shape) so one bad drawing never blanks the others.
export function sanitizeAnnotation(a: Annotation): Annotation | null {
  const finite = (v: unknown): boolean => !JSON.stringify(v, (_k, x) => (typeof x === 'number' && !Number.isFinite(x) ? '__bad__' : x)).includes('__bad__')
  if (!finite(a)) return null
  let next: Annotation
  switch (a.kind) {
    case 'ring':
      next = { ...a, box: box(a.box) }
      break
    case 'arrow':
      next = { ...a, to: 'xmin' in a.to ? box(a.to) : point(a.to), from: a.from ? point(a.from) : undefined }
      break
    case 'badge':
    case 'bubble':
      next = { ...a, at: point(a.at) }
      break
    case 'spotlight':
    case 'tick':
      next = { ...a, box: box(a.box) }
      break
    case 'ghostCursor':
      next = { ...a, path: a.path.map(point) }
      break
    case 'highlightText':
      next = { ...a, boxes: a.boxes.map(box) }
      break
  }
  const parsed = AnnotationSchema.safeParse(next)
  return parsed.success ? parsed.data : null
}

export interface OverlayControllerDeps {
  // Current mouse position as a normalised point on the overlay display, or null when unknown / on another display.
  cursorNorm?: () => NormPoint | null
}

async function electronCursorNorm(): Promise<() => NormPoint | null> {
  const { screen } = await import('electron')
  return () => {
    const d = screen.getPrimaryDisplay()
    const p = screen.getCursorScreenPoint()
    const x = ((p.x - d.bounds.x) / d.bounds.width) * 1000
    const y = ((p.y - d.bounds.y) / d.bounds.height) * 1000
    return x < 0 || x > 1000 || y < 0 || y > 1000 ? null : { x, y }
  }
}

// Guidance marks (point_at, lesson steps, do-it-for-me) are temporary: when the next anchor mark (ring, spotlight or
// ghost cursor) with a new id arrives, the previous guidance fades out. Other sources (scam flags, Showtime) manage
// their own marks. Batches go out in a fixed back-to-front order so layering never depends on call order.
const GUIDANCE_PREFIXES = ['point-', 'runner-', 'dfm-']
const ANCHOR_KINDS = new Set(['ring', 'spotlight', 'ghostCursor'])
const Z_ORDER: Record<string, number> = { spotlight: 0, highlightText: 1, ring: 2, arrow: 3, badge: 4, bubble: 5, tick: 6, ghostCursor: 7 }
const isGuidance = (id: string): boolean => GUIDANCE_PREFIXES.some((p) => id.startsWith(p))

export function createOverlayController(ctx: ServiceContext, deps: OverlayControllerDeps = {}): OverlayController {
  const shownGuidance = new Set<string>()
  let cursorNorm = deps.cursorNorm ?? (() => null)
  if (!deps.cursorNorm && process.versions.electron) {
    void electronCursorNorm().then((fn) => {
      cursorNorm = fn
    })
  }

  return {
    show(annotations) {
      const clean: Annotation[] = []
      for (const a of annotations) {
        const s = sanitizeAnnotation(a)
        if (!s) {
          ctx.log('overlay', `dropped malformed annotation ${String((a as { id?: unknown }).id)}`)
          continue
        }
        // A one-point ghost path flies in from where the user's mouse is, like Clicky's cursor leaving the pointer.
        if (s.kind === 'ghostCursor' && s.path.length === 1) {
          const from = cursorNorm()
          if (from) s.path = [from, ...s.path]
        }
        clean.push(s)
      }
      if (clean.length === 0) return
      const incoming = new Set(clean.map((a) => a.id))
      const newAnchor = clean.some((a) => isGuidance(a.id) && ANCHOR_KINDS.has(a.kind) && !shownGuidance.has(a.id))
      if (newAnchor) {
        const stale = [...shownGuidance].filter((id) => !incoming.has(id))
        if (stale.length > 0) ctx.sendOverlay({ type: 'clear', ids: stale })
        shownGuidance.clear()
      }
      // Ticks expire on their own (3.5 s) and must stay visible when the next step's ring arrives straight after them.
      for (const a of clean) if (isGuidance(a.id) && a.kind !== 'tick') shownGuidance.add(a.id)
      clean.sort((a, b) => (Z_ORDER[a.kind] ?? 9) - (Z_ORDER[b.kind] ?? 9))
      ctx.sendOverlay({ type: 'show', annotations: clean })
    },
    clear: (ids) => {
      if (!ids) shownGuidance.clear()
      else for (const id of ids) shownGuidance.delete(id)
      ctx.sendOverlay({ type: 'clear', ids })
    },
    caption: (speaker, text, final) => ctx.sendOverlay({ type: 'caption', speaker, text, final }),
    chip: (level, label) => ctx.sendOverlay({ type: 'chip', level, label }),
  }
}
