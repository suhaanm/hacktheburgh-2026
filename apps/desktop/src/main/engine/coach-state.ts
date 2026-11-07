// GET /coach/state (docs/API_CONTRACT.md) -> what the desktop does with it: the chip's fade, and a ring on the target element.
//   { task: {id, name, step, steps_total}, level: "L1".."L4", chip: "full"|"small"|"dot"|"gone", message, why, mastery }
// The ring is NOT driven from here: GET /coach/next names the element (by capture zone). This feeds the chip and the task.
import type { ChipFade, HelpLevel } from '../../shared/protocol'
import { chipFromEngine, levelFromEngine } from '../coach-chip'

export interface CoachStateInfo {
  task: { id: string; name: string; step: number; stepsTotal: number } | null
  level: HelpLevel | null
  chip: ChipFade | null
  message: string
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
  return {
    task,
    level: levelFromEngine(body.level),
    chip: chipFromEngine(body.chip),
    message: typeof body.message === 'string' ? body.message.slice(0, 200) : '',
  }
}
