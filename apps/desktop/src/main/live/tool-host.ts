// What the model's four tools actually do. Every effect here is code-decided and visual only: a ring, a chip, a question card. Nothing
// here can click, type, open, run or send.
//
// point_at(description): the description is the model's words, so it is never trusted as a target. Code builds a CLOSED MENU (2 to 6
// entries: the description under a code-made id, then decoys from the pack's own step labels and a fixed "something else" entry), asks the
// grounder (the page's DOM first, a vision model elsewhere; both answer in the same shape), and accepts the answer only when it chose the
// description's id with enough confidence and a sane box. The model hears only {found: true|false}; it never sees a coordinate.
import type { GroundMenuItem, GroundPort, LiveCuePort, RingPort, ToolHost } from './ports'
import type { CandidateList } from './tools'

export const POINT_ID = 't0'
export const NONE_ID = 't_none'
export const MIN_POINT_CONFIDENCE = 0.55
export const MIN_BOX_SIDE = 5 // on the 0..1000 grid: a ring around less than this is not a target
export const MAX_BOX_AREA = 300_000 // of 1_000_000: a ring over a third of the screen is a frame, not a pointer
export const RING_VISIBLE_MS = 15_000

export function buildMenu(description: string, candidates: ReadonlyArray<{ id: string; label: string }>): GroundMenuItem[] {
  const menu: GroundMenuItem[] = [{ id: POINT_ID, label: description }]
  const seen = new Set([description.toLowerCase()])
  for (const c of candidates) {
    if (menu.length >= 5) break
    const label = c.label.trim()
    if (!label || seen.has(label.toLowerCase())) continue
    seen.add(label.toLowerCase())
    menu.push({ id: `t${menu.length}`, label })
  }
  menu.push({ id: NONE_ID, label: 'something else on the screen' })
  return menu
}

/** A box that passes the sanity checks, normalised to [y0, x0, y1, x1] inside 0..1000, or null. */
export function sanePointBox(box: unknown): [number, number, number, number] | null {
  if (!Array.isArray(box) || box.length !== 4 || !box.every((n) => typeof n === 'number' && Number.isFinite(n))) return null
  const [a, b, c, d] = (box as number[]).map((n) => Math.min(1000, Math.max(0, n))) as [number, number, number, number]
  const y0 = Math.min(a, c)
  const y1 = Math.max(a, c)
  const x0 = Math.min(b, d)
  const x1 = Math.max(b, d)
  if (y1 - y0 < MIN_BOX_SIDE || x1 - x0 < MIN_BOX_SIDE) return null
  if ((y1 - y0) * (x1 - x0) > MAX_BOX_AREA) return null
  return [y0, x0, y1, x1]
}

export interface ToolHostDeps {
  cue: LiveCuePort
  ground: GroundPort | null
  ring: RingPort
  appKind?: () => string | undefined
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  ringMs?: number
}

export function createToolHost(d: ToolHostDeps): ToolHost & { dispose(): void } {
  const setT = d.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = d.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  let ringTimer: unknown = null
  const clearRing = (): void => {
    if (ringTimer !== null) clearT(ringTimer)
    ringTimer = null
    d.ring.clear()
  }
  const candidateList = (): CandidateList => ({ items: d.cue.candidates().slice(0, 6) })
  return {
    candidates: candidateList,
    async point(description) {
      if (!d.ground) return { found: false }
      const menu = buildMenu(description, d.cue.candidates())
      let answer
      try {
        answer = await d.ground.ground({ menu, ...(d.appKind?.() ? { app_kind: d.appKind() } : {}) })
      } catch {
        return { found: false }
      }
      if (!answer || answer.chosen !== POINT_ID || !(answer.confidence >= MIN_POINT_CONFIDENCE)) return { found: false }
      const box = sanePointBox(answer.box_2d)
      if (!box) return { found: false }
      d.ring.show(box)
      if (ringTimer !== null) clearT(ringTimer)
      ringTimer = setT(clearRing, d.ringMs ?? RING_VISIBLE_MS)
      return { found: true }
    },
    showStep(stepId) {
      return d.cue.showStep(stepId)
    },
    askChoice(ids) {
      return d.cue.askChoice(ids)
    },
    dispose: clearRing,
  }
}
