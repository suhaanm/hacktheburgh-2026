// The glance model's answer, parsed strictly. The model proposes; this code decides what to believe.
//   - only the keys of the closed schema are read; every other key is dropped (so no free text can ride along);
//   - an enum value that is not exactly in the list becomes null (never mapped, never guessed, never lower-cased into a match);
//   - confidence is a number in 0..1 (a string, NaN or anything else becomes 0; a number outside the range is clamped);
//   - box_2d is [ymin, xmin, ymax, xmax] in 0..1000 with ymin < ymax and xmin < xmax, else dropped;
//   - an answer with no usable enum and no box is rejected as a whole (null).
import { APP_KINDS, BLOCKERS, TASK_PHASES, fin, inList, isObj, type GlanceResult } from './types'

const MAX_JSON_CHARS = 4000
const MIN_BOX_SIDE = 4 // of 1000: a box thinner than that is noise

export function parseBox(v: unknown): [number, number, number, number] | undefined {
  if (!Array.isArray(v) || v.length !== 4 || !v.every(fin)) return undefined
  const [ymin, xmin, ymax, xmax] = (v as number[]).map((n) => Math.round(n))
  if ([ymin, xmin, ymax, xmax].some((n) => n < 0 || n > 1000)) return undefined
  if (ymax - ymin < MIN_BOX_SIDE || xmax - xmin < MIN_BOX_SIDE) return undefined
  return [ymin, xmin, ymax, xmax]
}

export function parseGlanceResult(raw: unknown): GlanceResult | null {
  let o: unknown = raw
  if (typeof raw === 'string') {
    if (raw.length > MAX_JSON_CHARS) return null
    try {
      o = JSON.parse(raw)
    } catch {
      return null
    }
  }
  if (!isObj(o)) return null
  const app_kind = inList(APP_KINDS, o.app_kind) ? o.app_kind : null
  const task_phase = inList(TASK_PHASES, o.task_phase) ? o.task_phase : null
  const blocker = inList(BLOCKERS, o.blocker) ? o.blocker : null
  const box = parseBox(o.box_2d)
  if (app_kind === null && task_phase === null && blocker === null && box === undefined) return null
  const confidence = fin(o.confidence) ? Math.min(1, Math.max(0, o.confidence)) : 0
  return { app_kind, task_phase, blocker, confidence: Math.round(confidence * 1000) / 1000, ...(box ? { box_2d: box } : {}) }
}
