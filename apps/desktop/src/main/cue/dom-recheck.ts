// Following a Cue ring with the browser extension: the CueGrounder that keeps a ring on its element when the page moves under it.
// The decision's own `target.box_2d` is where the ring is FIRST drawn; `step.target` ({zone, label_hint, role_hint}) is only used to FOLLOW it:
// the extension is asked where the ZONE is (a want carries only the zone), and the ring is moved by how far the zone has moved since the ring
// was drawn, never re-drawn on the zone's own rect (a zone can be a whole region; the engine's box is the element that matters). Geometry only:
// numbers go in and out, no page text, no URL, no field value. A missing zone, no answer, an element scrolled out of view, a zone that changed
// size, all mean the ring is gone, and it is dropped after 1.2 s as before: never left stale.
import type { NormBox } from '../../shared/protocol'
import { mapAnswer, mapContentRects, type DisplayInfo } from '../dom-ground/rect-map'
import { trackTarget, type DomGrounder, type TrackOptions } from '../dom-ground/dom-grounder'
import type { DomTarget, Rect, XY } from '../dom-ground/protocol'
import type { CueGrounder } from './controller'
import { MAX_BOX_AREA, MIN_BOX_SIDE } from './types'

export interface DomRecheckDeps {
  grounder: Pick<DomGrounder, 'request'>
  display: () => DisplayInfo
  calibration?: XY
  // The page-content boxes (screen points) of every answer: for the card's docking (the shell's content keeper).
  onContent?: (rects: Rect[]) => void
  // One question to the extension waits this long (a recheck has to finish well inside the ring's 1.2 s grace).
  timeoutMs?: number
  // How often a followed ring is refreshed.
  refreshMs?: number
  // The same question asked twice within this long shares one answer.
  cacheMs?: number
  now?: () => number
  setTimer?: TrackOptions['setTimer']
  clearTimer?: TrackOptions['clearTimer']
  log?: (scope: string, ...args: unknown[]) => void
}

type Box2d = [number, number, number, number]
const toBox2d = (b: NormBox): Box2d => [round(b.ymin), round(b.xmin), round(b.ymax), round(b.xmax)]
const round = (n: number): number => Math.round(n * 10) / 10
const clamp = (n: number): number => Math.min(1000, Math.max(0, n))
const area = (b: NormBox): number => (b.xmax - b.xmin) * (b.ymax - b.ymin)
// A zone that is moving, not growing: the same size within this ratio. Beyond it the page was laid out again and the ring cannot follow.
const SIZE_RATIO = 0.15
// Moves smaller than this (grid units, 1/1000 of the screen) are not worth a redraw.
const MIN_MOVE = 1.2

/** A ring box a ring can really be drawn on: not tiny, not a frame around a third of the screen. */
export const ringable = (b: NormBox): boolean => b.xmax - b.xmin >= MIN_BOX_SIDE && b.ymax - b.ymin >= MIN_BOX_SIDE && area(b) <= MAX_BOX_AREA

const translate = (ring: NormBox, dx: number, dy: number): NormBox => {
  const w = ring.xmax - ring.xmin
  const h = ring.ymax - ring.ymin
  const xmin = Math.min(1000 - w, Math.max(0, ring.xmin + dx))
  const ymin = Math.min(1000 - h, Math.max(0, ring.ymin + dy))
  return { xmin, ymin, xmax: xmin + w, ymax: ymin + h }
}

export function createDomRecheck(deps: DomRecheckDeps): CueGrounder {
  const now = deps.now ?? Date.now
  const log = deps.log ?? (() => undefined)
  const timeoutMs = deps.timeoutMs ?? 900
  const cacheMs = deps.cacheMs ?? 250
  // Where the zone was, and where the ring was, when the ring was first drawn: the movement of the zone since then is the movement of the ring.
  const baselines = new Map<string, { zone: NormBox; ring: NormBox }>()
  const cache = new Map<string, { at: number; answer: Promise<Where> }>()

  type Where = { ok: true; zone: NormBox; content: Rect[] } | { ok: false }

  const ask = (key: string, target: DomTarget): Promise<Where> => {
    const hit = cache.get(key)
    if (hit && now() - hit.at < cacheMs) return hit.answer
    const answer = (async (): Promise<Where> => {
      const out = await deps.grounder.request(target, { timeoutMs })
      if (out.kind !== 'answer') return { ok: false }
      const opts = { display: deps.display(), calibration: deps.calibration }
      const mapped = mapAnswer(out.answer, opts)
      if (!mapped.ok) return { ok: false }
      const content = mapContentRects(out.answer, opts)
      if (content.length > 0) deps.onContent?.(content)
      return { ok: true, zone: mapped.norm, content }
    })().catch(() => ({ ok: false }) as Where)
    cache.set(key, { at: now(), answer })
    return answer
  }

  // What to do with a fresh zone position: the ring where it should be now, or null when the page was laid out again or the ring cannot be drawn.
  const judge = (key: string, zone: NormBox, ring: NormBox): { kind: 'same' } | { kind: 'move'; box: Box2d } | { kind: 'gone' } => {
    const base = baselines.get(key)
    if (!base) {
      baselines.set(key, { zone, ring })
      return { kind: 'same' }
    }
    const bw = base.zone.xmax - base.zone.xmin
    const bh = base.zone.ymax - base.zone.ymin
    const w = zone.xmax - zone.xmin
    const h = zone.ymax - zone.ymin
    if (Math.abs(w - bw) > bw * SIZE_RATIO || Math.abs(h - bh) > bh * SIZE_RATIO) return { kind: 'gone' }
    const dx = zone.xmin - base.zone.xmin
    const dy = zone.ymin - base.zone.ymin
    const moved = translate(base.ring, dx, dy)
    // Nearly off the screen: the element was scrolled away.
    if (area(moved) <= 0 || moved.xmax - moved.xmin < MIN_BOX_SIDE || moved.ymax - moved.ymin < MIN_BOX_SIDE) return { kind: 'gone' }
    const cur = ring
    if (Math.abs(moved.xmin - cur.xmin) < MIN_MOVE && Math.abs(moved.ymin - cur.ymin) < MIN_MOVE) return { kind: 'same' }
    return { kind: 'move', box: toBox2d({ xmin: clamp(moved.xmin), ymin: clamp(moved.ymin), xmax: clamp(moved.xmax), ymax: clamp(moved.ymax) }) }
  }

  return {
    async recheck(t) {
      // No zone (an older engine, or none for this step): nothing can look for it; the ring is dropped.
      if (!t.target) return 'gone'
      const where = await ask(t.key, t.target)
      if (!where.ok) return 'gone'
      const base = baselines.get(t.key)
      if (!base) {
        // Never followed: the ring is put on the zone's own rect, if a ring can be drawn on it (a whole region cannot).
        if (!ringable(where.zone)) return 'gone'
        baselines.set(t.key, { zone: where.zone, ring: where.zone })
        return { box: toBox2d(where.zone) }
      }
      const r = judge(t.key, where.zone, t.box)
      if (r.kind === 'move') return { box: r.box }
      return r.kind
    },

    follow(t, cb) {
      let stopped = false
      // The ring as it is now (it moves as the zone does), to tell a real move from a repeated answer.
      let ring = t.box
      // The zone was lost and has come back: the ring must be shown again even if it is exactly where it was.
      let gone = false
      const lose = (): void => {
        gone = true
        cb.onGone()
      }
      const tracker = trackTarget(
        deps.grounder,
        t.target,
        {
          onVisible(zone, info) {
            if (stopped) return
            if (info.content.length > 0) deps.onContent?.(info.content)
            const r = judge(t.key, zone, ring)
            if (r.kind === 'gone') return lose()
            if (r.kind === 'move') ring = { ymin: r.box[0], xmin: r.box[1], ymax: r.box[2], xmax: r.box[3] }
            if (r.kind === 'move' || gone) {
              gone = false
              cb.onBox(toBox2d(ring))
            }
          },
          onHidden(reason) {
            if (stopped) return
            log('cue', `ring target hidden (${reason})`)
            lose()
          },
        },
        { display: deps.display, calibration: deps.calibration, refreshMs: deps.refreshMs ?? 400, now: deps.now, setTimer: deps.setTimer, clearTimer: deps.clearTimer, log },
      )
      // The ring is on its first box from here: the zone's position now is the baseline everything after is measured against.
      baselines.delete(t.key)
      return () => {
        stopped = true
        tracker.stop()
      }
    },
  }
}
