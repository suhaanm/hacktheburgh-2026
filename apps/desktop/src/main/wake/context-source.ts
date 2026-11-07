// Where the context packet's readings come from. Every source is a small function that returns an id, an enum or a count (or null): none returns
// text from a screen or a person. A reading is stamped with the time it was TAKEN here, and the packet drops it when it is older than its limit.
//
// Wired from the desktop today: pending approvals (the HUD's count), the task in progress with step n of m and the live coach decision's step and
// zone (the coach poller), the Cue state, the consent words, the rung record and the data mode. Reported BY the shell through `hub.set*` (the main
// window and the dashboard own them; until they report, their kinds are listed as unknown): the current Knack screen id, the top Home insight with
// its template id, and the running routine with its step.
import type { FunctionDeclaration } from '../live/wire'
import { buildPacket, type Packet, type PacketInputs, type Reading } from './context-packet'
import type { RungReading } from './rung'

export interface ContextSourceDeps {
  now?: () => number
  mock: boolean
  approvals: () => number | null
  task: () => { id: string; step: number; stepsTotal: number } | null
  /** The last coach decision (its step id and capture zone) with the time it was read. */
  coach: () => { step: string | null; zone: string | null; t: number } | null
  /** Cue's visible kind ('none' when nothing is up). */
  cue: () => string
  consent: () => { voice: string; screen: string; frames: boolean }
  rung: () => RungReading
}

export interface ContextHub {
  /** The packet for a conversation. Never throws (a source that throws counts as missing). */
  build(o: { tools: FunctionDeclaration[]; trigger: 'key' | 'wake' }): string
  /** The shell reports where the worker is. Values are validated by the packet's grammar when it is built, not trusted here. */
  setScreen(id: string | null): void
  setInsight(v: { id: string; template: string } | null): void
  setRoutine(v: { id: string; step: number; of: number } | null): void
  /** The last packet's manifest (kinds only), for a status line or a test. */
  last(): Packet['manifest'] | null
}

export function createContextHub(d: ContextSourceDeps): ContextHub {
  const now = d.now ?? Date.now
  let screen: Reading<string> = null
  let insight: Reading<{ id: string; template: string } | null> = null
  let routine: Reading<{ id: string; step: number; of: number } | null> = null
  let last: Packet['manifest'] | null = null
  const safe = <T>(fn: () => T): T | undefined => {
    try {
      return fn()
    } catch {
      return undefined
    }
  }
  return {
    build(o) {
      const t = now()
      const approvals = safe(d.approvals)
      const task = safe(d.task)
      const coach = safe(d.coach)
      const inputs: PacketInputs = {
        trigger: o.trigger,
        mode: d.mock ? 'example' : 'live',
        screen,
        insight,
        routine,
        approvals: approvals === undefined ? undefined : { value: approvals, t },
        task: task === undefined ? undefined : { value: task ? { id: task.id, step: task.step, of: task.stepsTotal } : null, t },
        coach: coach === undefined ? undefined : coach === null ? { value: null, t } : { value: { step: coach.step, zone: coach.zone }, t: coach.t },
        cue: { value: safe(d.cue) ?? 'none', t },
        consent: safe(d.consent) ?? { voice: 'unset', screen: 'unset', frames: false },
        click: safe(d.rung)?.cleared === true ? 'cleared' : 'pending',
        tools: o.tools,
        now: t,
      }
      const p = buildPacket(inputs)
      last = p.manifest
      return p.text
    },
    setScreen(id) {
      screen = id === null ? null : { value: id, t: now() }
    },
    setInsight(v) {
      insight = { value: v, t: now() }
    },
    setRoutine(v) {
      routine = { value: v, t: now() }
    },
    last: () => last,
  }
}
