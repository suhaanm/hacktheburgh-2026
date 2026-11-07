// Builds events for POST /events: schema v1 (packages/schema/event.schema.json). No free text, no URLs, no field values.
// Identifiers are hashed or enum-like; `meta` holds numbers, booleans and short enum tokens only.
import { randomUUID } from 'node:crypto'

export const EVENT_TYPES = [
  'nav', 'click', 'scroll', 'focus', 'tab', 'copy', 'paste', 'search', 'idle', 'lock', 'unlock', 'sleep', 'resume', 'stuck',
  'coach_shown', 'coach_followed', 'coach_dismissed', 'agent_step', 'approval', 'undo', 'task_start', 'task_end', 'progress',
] as const
export type EventType = (typeof EVENT_TYPES)[number]
export const EVENT_SOURCES = ['browser', 'screen', 'os', 'desk', 'agent', 'coach'] as const
export type EventSource = (typeof EVENT_SOURCES)[number]

export type MetaValue = number | boolean | string
export interface EventTarget {
  role?: string
  label_hash?: string
  domain_hash?: string
}

export interface UnderstudyEvent {
  schema: 1
  id: string
  t: string
  origin: 'real' | 'synthetic'
  actor: 'human' | 'agent'
  person: string
  role: string
  source: EventSource
  type: EventType
  target?: EventTarget
  task_id?: string
  meta?: Record<string, MetaValue>
}

export interface Identity {
  person: string // ^p_[a-z0-9]{2,16}$
  role: string // ^[a-z][a-z0-9-]{1,40}$
}

export interface EventInput {
  source: EventSource
  type: EventType
  actor?: 'human' | 'agent'
  target?: EventTarget
  task_id?: string
  meta?: Record<string, MetaValue>
}

const PERSON_RE = /^p_[a-z0-9]{2,16}$/
const ROLE_RE = /^[a-z][a-z0-9-]{1,40}$/
const TARGET_ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/
const LABEL_HASH_RE = /^h:[0-9a-f]{4,16}$/
const DOMAIN_HASH_RE = /^d:[0-9a-f]{4,16}$/
const TASK_RE = /^t_[A-Za-z0-9_-]{1,32}$/
const META_KEY_RE = /^[a-z][a-z0-9_]{0,31}$/
const META_STR_RE = /^[a-z0-9_:\-.]{0,32}$/

export const isPerson = (v: string): boolean => PERSON_RE.test(v)
export const isRole = (v: string): boolean => ROLE_RE.test(v)

/** Why an event would be rejected by the engine, or null when it is valid. A small mirror of the JSON schema (tests check it against the file). */
export function eventProblem(e: UnderstudyEvent): string | null {
  if (e.schema !== 1) return 'schema must be 1'
  if (typeof e.id !== 'string' || e.id.length < 8 || e.id.length > 64) return 'bad id'
  if (typeof e.t !== 'string' || Number.isNaN(Date.parse(e.t))) return 'bad time'
  if (e.origin !== 'real' && e.origin !== 'synthetic') return 'bad origin'
  if (e.actor !== 'human' && e.actor !== 'agent') return 'bad actor'
  if (!PERSON_RE.test(e.person)) return 'bad person'
  if (!ROLE_RE.test(e.role)) return 'bad role'
  if (!(EVENT_SOURCES as readonly string[]).includes(e.source)) return 'bad source'
  if (!(EVENT_TYPES as readonly string[]).includes(e.type)) return 'bad type'
  if (e.target) {
    const extra = Object.keys(e.target).filter((k) => !['role', 'label_hash', 'domain_hash'].includes(k))
    if (extra.length) return 'target has unknown keys'
    if (e.target.role !== undefined && !TARGET_ROLE_RE.test(e.target.role)) return 'bad target role'
    if (e.target.label_hash !== undefined && !LABEL_HASH_RE.test(e.target.label_hash)) return 'bad label hash'
    if (e.target.domain_hash !== undefined && !DOMAIN_HASH_RE.test(e.target.domain_hash)) return 'bad domain hash'
  }
  if (e.task_id !== undefined && !TASK_RE.test(e.task_id)) return 'bad task id'
  if (e.meta) {
    const keys = Object.keys(e.meta)
    if (keys.length > 16) return 'meta has too many keys'
    for (const k of keys) {
      if (!META_KEY_RE.test(k)) return `bad meta key ${k}`
      const v = e.meta[k]
      if (typeof v === 'number') {
        if (!Number.isFinite(v)) return `meta ${k} is not finite`
      } else if (typeof v === 'string') {
        if (!META_STR_RE.test(v)) return `meta ${k} is not a short enum token`
      } else if (typeof v !== 'boolean') return `meta ${k} has a bad type`
    }
  }
  return null
}

export function buildEvent(identity: Identity, input: EventInput, now: Date = new Date(), id: string = randomUUID()): UnderstudyEvent {
  return {
    schema: 1,
    id,
    t: now.toISOString(),
    origin: 'real',
    actor: input.actor ?? 'human',
    person: identity.person,
    role: identity.role,
    source: input.source,
    type: input.type,
    ...(input.target ? { target: input.target } : {}),
    ...(input.task_id ? { task_id: input.task_id } : {}),
    ...(input.meta ? { meta: input.meta } : {}),
  }
}
