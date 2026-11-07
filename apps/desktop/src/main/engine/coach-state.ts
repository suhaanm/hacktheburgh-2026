// GET /coach/state (docs/API_CONTRACT.md) -> what the desktop does with it: the chip's fade, and a ring on the target element.
//   { task: {id, name, step, steps_total}, level: "L1".."L4", chip: "full"|"small"|"dot"|"gone", message, why, mastery }
// Additive fields proposed for the ring (ignored when the engine does not send them):
//   target { label_hash } or { role, name }, optional target_label (a short phrase, at most 40 characters).
import type { ChipFade, HelpLevel } from '../../shared/protocol'
import { chipFromEngine, levelFromEngine } from '../coach-chip'
import { toTarget, type DomTarget } from '../dom-ground/protocol'

export interface CoachStateInfo {
  task: { id: string; name: string; step: number; stepsTotal: number } | null
  level: HelpLevel | null
  chip: ChipFade | null
  message: string
  target: DomTarget | null
  targetLabel: string | null
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const int = (v: unknown): number | null => (typeof v === 'number' && Number.isInteger(v) ? v : null)

export function parseCoachState(raw: unknown): CoachStateInfo | null {
  if (!isObj(raw)) return null
  const body = isObj(raw.data) ? raw.data : raw
  const t = isObj(body.task) ? body.task : null
  const step = t ? int(t.step) : null
  const total = t ? int(t.steps_total) : null
  const task = t && typeof t.id === 'string' && step !== null && total !== null ? { id: t.id, name: typeof t.name === 'string' ? t.name.slice(0, 80) : '', step, stepsTotal: total } : null
  const label = typeof body.target_label === 'string' ? body.target_label.replace(/\s+/g, ' ').trim().slice(0, 40) : ''
  return {
    task,
    level: levelFromEngine(body.level),
    chip: chipFromEngine(body.chip),
    message: typeof body.message === 'string' ? body.message.slice(0, 200) : '',
    target: toTarget(body.target),
    targetLabel: label || null,
  }
}
