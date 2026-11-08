// The context packet a Live conversation starts with (Hey Knack or the talk key): built by CODE from enums, ids and counts, never from the screen,
// a page, a file or anything the worker typed or said. It follows the shape and the freshness rules of the context library
// (services/agent/understudy_agent/context: typed sections, a reading carries the time it was TAKEN, a reading older than its limit is dropped and
// its kind is listed under `unknown`, never shown as if it were current). It is built here in TypeScript because every source it reads lives in
// the desktop process; the engine's context routes are for the Python planners and have no route a voice session could call.
//
// The packet goes into the session's system instruction (trusted: code wrote every token) and, when it changes, as a short update line. Every value
// passes a closed grammar below; a value that does not fit is dropped and counted as unknown. A test pins that the packet holds no free text.
import type { FunctionDeclaration } from '../live/wire'

export const PACKET_VERSION = 1
export const MAX_PACKET_CHARS = 1400

/** A reading with the time (ms) its producer took it. null or undefined: there is none. */
export type Reading<T> = { value: T; t: number } | null | undefined

export const SCREEN_IDS = ['home', 'needs_you', 'routines', 'growth', 'your_data', 'settings', 'first_run', 'admin', 'other'] as const
export type ScreenId = (typeof SCREEN_IDS)[number]
export const CUE_STATES = ['none', 'confirm', 'cue', 'ask', 'offer'] as const
export type CueState = (typeof CUE_STATES)[number]
export const CONSENT_WORDS = ['unset', 'yes', 'not_now', 'never'] as const
export type ConsentWord = (typeof CONSENT_WORDS)[number]

// How old a reading may be (ms). Names and limits follow context/freshness.py where the kind exists there (snapshot 60 s, briefing card 1 h).
export const MAX_AGE_MS: Readonly<Record<string, number>> = {
  screen: 60_000,
  insight: 3_600_000,
  approvals: 60_000,
  routine: 30_000,
  coach: 60_000,
  task: 60_000,
  cue: 20_000,
}

export interface PacketInputs {
  trigger: 'wake' | 'key'
  /** Live models, or example data (mock mode). */
  mode: 'live' | 'example'
  screen?: Reading<string>
  insight?: Reading<{ id: string; template: string } | null>
  approvals?: Reading<number | null>
  routine?: Reading<{ id: string; step: number; of: number } | null>
  /** The coach decision that is live: the step id and the capture zone it points at. */
  coach?: Reading<{ step: string | null; zone: string | null } | null>
  /** The task in progress (its id and step n of m; the task's name is free text and is never used). */
  task?: Reading<{ id: string; step: number; of: number } | null>
  cue?: Reading<string>
  /** The worker is in first-run set-up or has not finished it: the model answers in character for someone new. */
  firstRun?: boolean
  consent: { voice: string; screen: string; frames: boolean }
  /** Whether `do_it_for_me` can ever click: the persisted rung record. */
  click: 'cleared' | 'pending'
  tools: ReadonlyArray<Pick<FunctionDeclaration, 'name' | 'parameters'>>
  now: number
}

export interface PacketManifest {
  included: string[]
  /** Kinds that had a reading older than their limit, or a value that did not fit its grammar. */
  stale: string[]
  /** Kinds with no reading. */
  missing: string[]
  chars: number
}

export interface Packet {
  text: string
  manifest: PacketManifest
}

const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/
const id = (v: unknown): string | null => (typeof v === 'string' && ID_RE.test(v) ? v : null)
const count = (v: unknown): number | null => (typeof v === 'number' && Number.isInteger(v) && v >= 0 ? Math.min(v, 9999) : null)
const oneOf = <T extends string>(set: readonly T[], v: unknown): T | null => (typeof v === 'string' && (set as readonly string[]).includes(v) ? (v as T) : null)

/** The text a session gets when no packet could be built. Fixed, no placeholders. */
export const FALLBACK_PACKET = ['KNACK CONTEXT v1 (built by code)', 'context=unavailable', 'Ask the worker what they are working on before you guess.'].join('\n')

/** One tool as `name(arg:type<=n|a,b)`: from our own declarations, never from the screen. Candidate labels in descriptions are not used. */
export function signature(t: Pick<FunctionDeclaration, 'name' | 'parameters'>): string | null {
  const name = /^[a-z][a-z0-9_]{0,30}$/.test(t.name) ? t.name : null
  if (!name) return null
  const props = (t.parameters?.properties ?? {}) as Record<string, { type?: string; maxLength?: number; enum?: string[]; items?: { enum?: string[] } }>
  const args = Object.keys(props)
    .filter((k) => /^[a-z][a-z0-9_]{0,30}$/.test(k))
    .map((k) => {
      const p = props[k]
      const ty = typeof p.type === 'string' && /^[a-z]{3,10}$/.test(p.type) ? p.type : 'any'
      const limit = typeof p.maxLength === 'number' && p.maxLength > 0 && p.maxLength <= 200 ? `<=${p.maxLength}` : ''
      const en = (p.enum ?? p.items?.enum ?? []).filter((x): x is string => typeof x === 'string' && ID_RE.test(x)).slice(0, 6)
      return `${k}:${ty}${limit}${en.length ? `|${en.join(',')}` : ''}`
    })
  return `${name}(${args.join(', ')})`
}

export function buildPacket(i: PacketInputs): Packet {
  const included: string[] = []
  const stale: string[] = []
  const missing: string[] = []
  const lines: string[] = []

  // A reading is used only if it is there, young enough and its value fits the grammar; otherwise its kind is named, never its content.
  const take = <T, U>(kind: string, r: Reading<T>, fit: (v: T) => U | null): U | null => {
    if (r === null || r === undefined) {
      missing.push(kind)
      return null
    }
    const limit = MAX_AGE_MS[kind]
    if (!(Number.isFinite(r.t)) || (limit !== undefined && i.now - r.t > limit) || r.t > i.now + 5_000) {
      stale.push(kind)
      return null
    }
    const v = fit(r.value)
    if (v === null) {
      stale.push(kind)
      return null
    }
    included.push(kind)
    return v
  }

  lines.push(`KNACK CONTEXT v${PACKET_VERSION} (built by code; ids, enums and counts only; nothing here came from the screen)`)
  lines.push(`trigger=${i.trigger === 'wake' ? 'wake' : 'key'}`)
  lines.push(`data=${i.mode === 'live' ? 'live_models' : 'example_data'}`)
  const screen = take('screen', i.screen, (v) => oneOf(SCREEN_IDS, v))
  if (screen) lines.push(`screen=${screen}`)
  lines.push(`first_run=${i.firstRun === true || screen === 'first_run' ? 'yes' : 'no'}`)
  const ins = take('insight', i.insight, (v) => (v === null ? 'none' : id(v.id) && id(v.template) ? `${v.id}|${v.template}` : null))
  if (ins) lines.push(`home_insight=${ins}`)
  const ap = take('approvals', i.approvals, (v) => (v === null ? null : count(v)))
  if (ap !== null) lines.push(`approvals_pending=${ap}`)
  const rt = take('routine', i.routine, (v) => (v === null ? 'none' : id(v.id) && count(v.step) !== null && count(v.of) !== null && v.step <= v.of ? `${v.id} step=${v.step}/${v.of}` : null))
  if (rt) lines.push(`routine=${rt}`)
  const task = take('task', i.task, (v) => (v === null ? 'none' : id(v.id) && count(v.step) !== null && count(v.of) !== null ? `${v.id} ${v.step}/${v.of}` : null))
  if (task) lines.push(`task=${task}`)
  const coach = take('coach', i.coach, (v) => {
    if (v === null) return 'none'
    const step = v.step === null ? 'none' : id(v.step)
    const zone = v.zone === null ? 'none' : id(v.zone)
    return step !== null && zone !== null ? `step=${step} zone=${zone}` : null
  })
  if (coach) lines.push(`coach=${coach}`)
  const cue = take('cue', i.cue, (v) => oneOf(CUE_STATES, v))
  if (cue) lines.push(`cue=${cue}`)
  const cv = oneOf(CONSENT_WORDS, i.consent.voice) ?? 'unset'
  const cs = oneOf(CONSENT_WORDS, i.consent.screen) ?? 'unset'
  lines.push(`consent_voice=${cv} consent_screen=${cs} frames=${i.consent.frames === true ? 'on' : 'off'}`)
  lines.push(`click=${i.click === 'cleared' ? 'allowed_after_worker_clicks_allow' : 'first_supervised_test_pending'}`)
  const unknown = [...missing, ...stale]
  if (unknown.length) lines.push(`unknown=${[...new Set(unknown)].join(',')}`)
  const sigs = i.tools.map(signature).filter((s): s is string => s !== null).slice(0, 12)
  lines.push('tools (the only ones you may call):')
  for (const s of sigs) lines.push(`- ${s}`)

  let text = lines.join('\n')
  if (text.length > MAX_PACKET_CHARS) text = FALLBACK_PACKET // never a truncated packet: a cut line could be a cut value
  return { text, manifest: { included, stale: [...new Set(stale)], missing: [...new Set(missing)], chars: text.length } }
}

/** The lines of `next` that are not in `prev`, as one short update, or null when nothing changed. Tool lines are never part of an update. */
export function packetUpdate(prev: string | null, next: string): string | null {
  if (prev === null || prev === next) return prev === next ? null : next
  const had = new Set(prev.split('\n'))
  const changed = next.split('\n').filter((l) => !had.has(l) && !l.startsWith('- ') && !l.startsWith('KNACK CONTEXT'))
  return changed.length ? `Context update (code-built, ids and counts only):\n${changed.join('\n')}` : null
}
