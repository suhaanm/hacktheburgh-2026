// Cue: the stuck-rescue decision as the desktop sees it. This mirrors the CUE-ENGINE's `CueDecision` (docs/REQ7_PLAN.md section 4) and is
// the ONLY place that shape lives here: if the engine's final JSON differs, adapt `parseCueDecision` and nothing else.
//
// Trust: a decision is data from another process, so it is parsed, never cast. Unknown fields are dropped, every string is cleaned and
// length-capped, every enum and id is validated, numbers are clamped, and anything malformed becomes `none` (the default: say nothing).
// No free text from a model is ever shown from here: chips, options and reasons are pack labels the engine chose by id.
// Coordinates: `box_2d` is [y0, x0, y1, x1] on a 0..1000 grid from the top-left of the display (the Gemini box order the engine uses).

import { toTarget, type DomTarget } from '../dom-ground/protocol'

export const CUE_KINDS = ['none', 'confirm', 'cue', 'ask', 'offer'] as const
export type CueKind = (typeof CUE_KINDS)[number]

export type CueTier = 1 | 2 | 3 | 4
export type CueLevel = 1 | 2 | 3 | 4
export type CueTargetSource = 'dom' | 'vision' | 'none'
export type CueSource = 'model' | 'rule'
export type CueTrigger = 'auto' | 'asked'
export type CueOrigin = 'synthetic' | 'recorded'

/** [y0, x0, y1, x1] on the 0..1000 grid. */
export type CueBox2d = [number, number, number, number]

export interface CueTarget {
  // Null when the engine had no usable box (or it failed the sanity checks below): then there is nothing to ring.
  box_2d: CueBox2d | null
  source: CueTargetSource
  confidence: number
}

export interface CueStep {
  id: string
  // The pack's label for the step. Never model text.
  label: string
  reason_id: string | null
  // 1-based position in the walkthrough, when the engine counts it (else the controller counts).
  n: number | null
  // The one-line "why" for this step when the engine sends it inline (else it comes from `texts[reason_id]`).
  reason_text: string | null
  // WHERE the step's element is, by capture zone ({zone, label_hint, role_hint}): only for FOLLOWING a ring that moved (scrolling, a re-layout)
  // through the browser extension. The first placement always uses the decision's own `target.box_2d`; the two are never mixed. Null: an older
  // engine, no zone, or an invalid value (then nothing can follow the ring and it drops after 1.2 s when its screen changes).
  target: DomTarget | null
}

export interface CueOption {
  id: string
  label: string
}

export interface CueSay {
  // Tier 2+ chip. At most CHIP_MAX_CHARS characters.
  chip: string
  // The spoken line for tier 4: at most WHISPER_MAX_WORDS words, or null.
  whisper: string | null
  // The id of the cached audio for the whisper (what CueSpeaker.say takes); null means the line has no audio.
  whisper_id: string | null
  // The question line of an `ask` (falls back to `chip`).
  question: string | null
}

export interface CueWhy {
  path_prob: number | null
  margin: number | null
  p_stuck: number | null
  mastery: number | null
  level: CueLevel | null
  reasons: string[]
  // Whether the path probability comes from simulated or recorded experts. Shown as a small tag when synthetic (honesty).
  origin: CueOrigin | null
}

export interface CueDecision {
  kind: CueKind
  episode_id: string
  decision_id: string | null
  tier: CueTier | null
  step: CueStep | null
  target: CueTarget | null
  options: CueOption[] | null
  say: CueSay
  why: CueWhy
  budget_left: number | null
  cooldown_s: number
  source: CueSource
  // 'asked' = the worker pressed for help (a hotkey, "show me"): hard caps and the level-4 silence do not apply.
  trigger: CueTrigger
  // reason_id -> one plain line, as the engine returns it. Absent id = no text = the UI shows nothing for it.
  texts: Record<string, string>
  // The engine's additive fields (agreed with CUE-ENGINE): true on the poll where this tier first appears; the engine's own display limit;
  // retrieval practice (help withheld, confirmed afterwards); the engine would like a grounded box for the step.
  new: boolean
  expires_in_s: number | null
  retrieval: boolean
  ground_wanted: boolean
  // The kind of question an `ask` is (the engine's fixed templates): which are close, the screen shows several, or nothing is clear.
  question_type: 'close_call' | 'screen_disagrees' | 'unclear' | null
}

export const CHIP_MAX_CHARS = 40
export const WHISPER_MAX_WORDS = 8
export const QUESTION_MAX_CHARS = 72
export const OPTION_MAX_CHARS = 44
export const REASON_MAX_CHARS = 100
export const MIN_OPTIONS = 2
export const MAX_OPTIONS = 4
export const ID_MAX = 80
// The engine's fixed id for "something else" in a question.
export const OTHER_ID = 'other'
export const MIN_BOX_SIDE = 5 // on the 0..1000 grid: a ring around less than this is not a target
export const MAX_BOX_AREA = 300_000 // of 1_000_000: a ring over a third of the screen is a frame, not a pointer

const ID_RE = /^[A-Za-z0-9_.:-]{1,80}$/
// Reason ids carry a dot in the engine's pack vocabulary ("why.read_case").
const SLUG_RE = /^[a-z0-9_.]{1,40}$/

export const NONE_DECISION: CueDecision = Object.freeze({
  kind: 'none' as const,
  episode_id: '',
  decision_id: null,
  tier: null,
  step: null,
  target: null,
  options: null,
  say: Object.freeze({ chip: '', whisper: null, whisper_id: null, question: null }),
  why: Object.freeze({ path_prob: null, margin: null, p_stuck: null, mastery: null, level: null, reasons: Object.freeze([]) as unknown as string[], origin: null }),
  budget_left: null,
  cooldown_s: 0,
  source: 'rule' as const,
  trigger: 'auto' as const,
  texts: Object.freeze({}) as Record<string, string>,
  new: false,
  expires_in_s: null,
  retrieval: false,
  ground_wanted: false,
  question_type: null,
})

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const own = (o: Record<string, unknown>, k: string): unknown => (Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined)

// Controls, bidi overrides and zero-width characters out; whitespace collapsed. Text can never carry hidden characters to the screen.
// eslint-disable-next-line no-control-regex
const HIDDEN = /[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁠-⁤⁦-⁩﻿]/g
export function cleanText(v: unknown): string {
  return typeof v === 'string' ? v.replace(HIDDEN, ' ').replace(/\s+/g, ' ').trim() : ''
}

/** At most `max` characters, cut at a word where one is close, ending in an ellipsis. */
export function capChars(text: string, max: number): string {
  const chars = [...text]
  if (chars.length <= max) return text
  const head = chars.slice(0, max - 1).join('')
  const cut = head.lastIndexOf(' ')
  const base = cut >= Math.floor(max * 0.55) ? head.slice(0, cut) : head
  return `${base.replace(/[\s,;:.\-–—]+$/, '')}…`
}

const idOf = (v: unknown): string | null => (typeof v === 'string' && ID_RE.test(v) ? v : null)
const slugOf = (v: unknown): string | null => (typeof v === 'string' && SLUG_RE.test(v) ? v : null)
const unit = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : null)
const clamp1000 = (n: number): number => Math.min(1000, Math.max(0, n))

function parseBox(v: unknown): CueBox2d | null {
  if (!Array.isArray(v) || v.length !== 4 || !v.every((n) => typeof n === 'number' && Number.isFinite(n))) return null
  const [a, b, c, d] = (v as number[]).map(clamp1000)
  const y0 = Math.min(a, c)
  const y1 = Math.max(a, c)
  const x0 = Math.min(b, d)
  const x1 = Math.max(b, d)
  if (y1 - y0 < MIN_BOX_SIDE || x1 - x0 < MIN_BOX_SIDE) return null
  if ((y1 - y0) * (x1 - x0) > MAX_BOX_AREA) return null
  return [y0, x0, y1, x1]
}

function parseTarget(v: unknown): CueTarget | null {
  if (!isObj(v)) return null
  const source = own(v, 'source')
  const src: CueTargetSource = source === 'dom' || source === 'vision' ? source : 'none'
  const box = parseBox(own(v, 'box_2d'))
  const confidence = unit(own(v, 'confidence')) ?? 0
  // No box and no source: nothing here at all.
  if (!box && src === 'none') return null
  return { box_2d: box, source: box ? src : 'none', confidence }
}

// The same rules as every other zone in the app (dom-ground/protocol.ts: the zone pattern, an 80-character label hint, a role pattern);
// only {zone, label_hint, role_hint} are read, whatever else the engine sends, and a missing key or an invalid value is null.
function parseStepTarget(v: unknown): DomTarget | null {
  if (!isObj(v)) return null
  const zone = own(v, 'zone')
  if (typeof zone !== 'string') return null
  const hint = (k: string): string | undefined => {
    const x = own(v, k)
    return typeof x === 'string' ? cleanText(x) || undefined : undefined
  }
  return toTarget({ zone, label_hint: hint('label_hint'), role_hint: hint('role_hint') })
}

function parseStep(v: unknown): CueStep | null {
  if (!isObj(v)) return null
  const id = idOf(own(v, 'id'))
  if (!id) return null
  const label = capChars(cleanText(own(v, 'label')), 60)
  const nRaw = own(v, 'n')
  const n = typeof nRaw === 'number' && Number.isInteger(nRaw) && nRaw >= 1 && nRaw <= 99 ? nRaw : null
  const reasonText = capChars(cleanText(own(v, 'reason_text')), REASON_MAX_CHARS)
  return { id, label, reason_id: slugOf(own(v, 'reason_id')), n, reason_text: reasonText || null, target: parseStepTarget(own(v, 'target')) }
}

function parseOptions(v: unknown): CueOption[] | null {
  if (!Array.isArray(v)) return null
  const out: CueOption[] = []
  const seen = new Set<string>()
  for (const raw of v) {
    if (!isObj(raw)) continue
    const id = idOf(own(raw, 'id'))
    const label = capChars(cleanText(own(raw, 'label')), OPTION_MAX_CHARS)
    // The engine appends the fixed "something else" option (id "other"); the card always draws that row itself, so it is not a step option.
    if (!id || id === OTHER_ID || !label || seen.has(id)) continue
    seen.add(id)
    out.push({ id, label })
    if (out.length === MAX_OPTIONS) break
  }
  return out.length >= MIN_OPTIONS ? out : null
}

function parseSay(v: unknown): CueSay {
  const o = isObj(v) ? v : {}
  const chip = capChars(cleanText(own(o, 'chip')), CHIP_MAX_CHARS)
  const whisperRaw = cleanText(own(o, 'whisper'))
  const words = whisperRaw === '' ? 0 : whisperRaw.split(' ').length
  // A spoken line is dropped, not cut: half a sentence read aloud is worse than silence.
  const whisper = whisperRaw !== '' && words <= WHISPER_MAX_WORDS ? whisperRaw : null
  const question = capChars(cleanText(own(o, 'question')), QUESTION_MAX_CHARS)
  return { chip, whisper, whisper_id: whisper ? idOf(own(o, 'whisper_id')) : null, question: question || null }
}

function parseWhy(v: unknown): CueWhy {
  const o = isObj(v) ? v : {}
  const lvl = own(o, 'level')
  const level: CueLevel | null = lvl === 1 || lvl === 2 || lvl === 3 || lvl === 4 ? lvl : null
  const reasonsRaw = own(o, 'reasons')
  const reasons = Array.isArray(reasonsRaw) ? reasonsRaw.map(slugOf).filter((r): r is string => r !== null).slice(0, 12) : []
  const origin = own(o, 'origin')
  return {
    path_prob: unit(own(o, 'path_prob')),
    margin: unit(own(o, 'margin')),
    p_stuck: unit(own(o, 'p_stuck')),
    mastery: unit(own(o, 'mastery')),
    level,
    reasons,
    origin: origin === 'synthetic' || origin === 'recorded' ? origin : null,
  }
}

function parseTexts(v: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!isObj(v)) return out
  let n = 0
  for (const key of Object.keys(v)) {
    if (n >= 24) break
    if (!SLUG_RE.test(key)) continue
    const text = capChars(cleanText(own(v, key)), REASON_MAX_CHARS)
    if (text) {
      out[key] = text
      n += 1
    }
  }
  return out
}

/**
 * A decision from the engine -> a CueDecision, or NONE_DECISION when it is malformed. Accepts the bare object or `{ data }` / `{ meta, data }`.
 * Kind-specific rules: `cue` needs a tier and something to show (a box or a chip); `ask` needs 2 to 4 options; `offer` needs words; `confirm` needs a box.
 */
export function parseCueDecision(raw: unknown): CueDecision {
  if (!isObj(raw)) return NONE_DECISION
  const body = isObj(own(raw, 'data')) ? (own(raw, 'data') as Record<string, unknown>) : raw
  const kindRaw = own(body, 'kind')
  const kind = (CUE_KINDS as readonly unknown[]).includes(kindRaw) ? (kindRaw as CueKind) : 'none'
  const episode = idOf(own(body, 'episode_id'))
  if (kind === 'none') {
    // A quiet answer still carries the episode and the engine's reason codes ("step_done", "on_track"): that is how Cue learns a cue is over.
    const reasons = parseWhy(own(body, 'why')).reasons
    return episode && reasons.length > 0 ? { ...NONE_DECISION, episode_id: episode, why: { ...NONE_DECISION.why, reasons } } : NONE_DECISION
  }
  if (!episode) return NONE_DECISION

  const tierRaw = own(body, 'tier')
  const tier: CueTier | null = tierRaw === 1 || tierRaw === 2 || tierRaw === 3 || tierRaw === 4 ? tierRaw : null
  const step = parseStep(own(body, 'step'))
  const target = parseTarget(own(body, 'target'))
  const say = parseSay(own(body, 'say'))
  const why = parseWhy(own(body, 'why'))
  const options = kind === 'ask' ? parseOptions(own(body, 'options')) : null
  const q = isObj(own(body, 'question')) ? (own(body, 'question') as Record<string, unknown>) : null
  const qType = q ? own(q, 'type') : null
  const qText = q ? capChars(cleanText(own(q, 'text')), QUESTION_MAX_CHARS) : ''
  const exp = own(body, 'expires_in_s')
  const budget = own(body, 'budget_left')
  const cooldown = own(body, 'cooldown_s')

  if (kind === 'cue') {
    if (tier === null) return NONE_DECISION
    if (!target?.box_2d && say.chip === '') return NONE_DECISION
  }
  if (kind === 'ask' && !options) return NONE_DECISION
  if (kind === 'offer' && say.chip === '') return NONE_DECISION
  if (kind === 'confirm' && !target?.box_2d) return NONE_DECISION

  return {
    kind,
    episode_id: episode,
    decision_id: idOf(own(body, 'decision_id')),
    tier,
    step,
    target,
    options,
    say: qText && !say.question ? { ...say, question: qText } : say,
    why,
    budget_left: typeof budget === 'number' && Number.isInteger(budget) && budget >= 0 && budget <= 1000 ? budget : null,
    cooldown_s: typeof cooldown === 'number' && Number.isFinite(cooldown) ? Math.min(86_400, Math.max(0, cooldown)) : 0,
    source: own(body, 'source') === 'model' ? 'model' : 'rule',
    trigger: own(body, 'trigger') === 'asked' ? 'asked' : 'auto',
    texts: parseTexts(own(body, 'texts')),
    new: own(body, 'new') === true,
    expires_in_s: typeof exp === 'number' && Number.isFinite(exp) && exp >= 1 && exp <= 300 ? exp : null,
    retrieval: own(body, 'retrieval') === true,
    ground_wanted: own(body, 'ground_wanted') === true,
    question_type: qType === 'close_call' || qType === 'screen_disagrees' || qType === 'unclear' ? qType : null,
  }
}

// Reason codes on a quiet (`none`) answer that mean the worker got past the step on their own: the cue on screen is over.
export const PROGRESS_REASONS: ReadonlySet<string> = new Set(['progress', 'recovered', 'step_done', 'progressed', 'on_track', 'resolved'])
export const isProgress = (d: CueDecision): boolean => d.kind === 'none' && d.why.reasons.some((r) => PROGRESS_REASONS.has(r))

/** Does the decision put anything on the screen? */
export const isVisibleKind = (d: CueDecision): boolean => d.kind !== 'none'

/** Same cue as far as the worker can tell: same episode, kind, step and options. A higher tier is the same cue growing, not a new one. */
export function sameCue(a: CueDecision, b: CueDecision): boolean {
  return (
    a.kind === b.kind &&
    a.episode_id === b.episode_id &&
    (a.step?.id ?? null) === (b.step?.id ?? null) &&
    (a.options ?? []).map((o) => o.id).join('|') === (b.options ?? []).map((o) => o.id).join('|')
  )
}

/** The plain phrase for the path probability. No number: "most experts do this next". */
export function pathPhrase(p: number | null): string | null {
  if (p === null) return null
  if (p >= 0.85) return 'nearly every expert does this next'
  if (p >= 0.6) return 'most experts do this next'
  if (p >= 0.4) return 'about half of experts do this next'
  if (p >= 0.2) return 'some experts do this next'
  return 'few experts do this next'
}

/** The one-line reason for the step: inline text, else the engine's table by reason id, else nothing. */
export function reasonLine(d: CueDecision): string | null {
  if (d.step?.reason_text) return d.step.reason_text
  const id = d.step?.reason_id
  return id && d.texts[id] ? d.texts[id] : null
}
