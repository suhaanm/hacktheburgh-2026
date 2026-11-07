// The four tools the voice model may call, and the strict parser every call goes through. The model proposes; this file decides.
//
//   point_at(description)    draw a ring on the screen where this is. Code resolves it (the page's DOM first, a vision model elsewhere).
//   show_step(step_id)       show one step of the worker's pack. The id must be one the code listed; code returns the guidance chip.
//   ask_choice(options)      open the question card with 2 to 4 of the listed candidate steps. The worker answers; the model cannot.
//   end_session()            say goodbye and finish.
//
// There is NO tool that can click, type, run, send, open or change anything, so there is nothing for an injected instruction to reach.
// Unknown tools, unknown arguments, ids outside the closed lists, wrong types and over-long text are refused with a plain message,
// and that message is what the model is told. Free text (only `description`) is cleaned, length-capped and screened before it can
// reach any other component, and it is never stored or logged.
import type { FunctionDeclaration, Scheduling } from './wire'

export const TOOL_NAMES = ['point_at', 'show_step', 'ask_choice', 'end_session'] as const
export type ToolName = (typeof TOOL_NAMES)[number]
// Offered ONLY in a session that began with the words "Hey Knack" (the wake session). `clear` takes the ring and ghost cursor away. `do_it_for_me`
// asks to click ONE thing the worker named: it never clicks by itself, it asks code, and code asks the worker (a real mouse click on a card).
export const WAKE_TOOL_NAMES = ['clear', 'do_it_for_me'] as const
export type WakeToolName = (typeof WAKE_TOOL_NAMES)[number]
export interface ToolOptions {
  wake?: boolean
}

export const DESCRIPTION_MAX_CHARS = 60
export const DESCRIPTION_MIN_CHARS = 2
export const MAX_CHOICES = 4
export const MIN_CHOICES = 2
export const MAX_CANDIDATES = 6

const ID_RE = /^[A-Za-z0-9_.:-]{1,80}$/

/** The closed lists the code offers for this moment: pack step ids with their pack labels (never model text). */
export interface CandidateList {
  items: ReadonlyArray<{ id: string; label: string }>
}

export type ParsedToolCall =
  | { ok: true; name: 'point_at'; args: { description: string } }
  | { ok: true; name: 'show_step'; args: { step_id: string } }
  | { ok: true; name: 'ask_choice'; args: { options: string[] } }
  | { ok: true; name: 'end_session'; args: Record<string, never> }
  | { ok: true; name: 'clear'; args: Record<string, never> }
  | { ok: true; name: 'do_it_for_me'; args: { description: string } }
  | { ok: false; code: ToolRefusal; message: string }

export type ToolRefusal =
  | 'unknown_tool'
  | 'bad_arguments'
  | 'unknown_argument'
  | 'not_a_listed_step'
  | 'bad_description'
  | 'bad_choices'
  | 'no_candidates'

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

// Controls, bidi overrides and zero-width characters out; whitespace collapsed.
// eslint-disable-next-line no-control-regex
const HIDDEN = /[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁠-⁤⁦-⁩﻿]/g
export function cleanLine(v: unknown): string {
  return typeof v === 'string' ? v.replace(HIDDEN, ' ').replace(/\s+/g, ' ').trim() : ''
}

// What a pointing description may not look like: a web address, an email, a long number, a code fence or a markup tag. Pointing is
// "the blue Save button", never data; refusing these keeps personal data and instructions out of the grounding prompt.
const URLISH = /(https?:\/\/|www\.|\b[a-z0-9-]+\.(com|org|net|io|uk|gov|co|dev)\b|[a-z0-9._-]+@[a-z0-9.-]+)/i
const LONG_NUMBER = /\d[\d\s-]{6,}\d/
const MARKUP = /[<>{}`]|```/

export function parseDescription(v: unknown): string | null {
  const s = cleanLine(v)
  if (s.length < DESCRIPTION_MIN_CHARS || [...s].length > DESCRIPTION_MAX_CHARS) return null
  if (URLISH.test(s) || LONG_NUMBER.test(s) || MARKUP.test(s)) return null
  return s
}

function onlyKeys(o: Record<string, unknown>, allowed: readonly string[]): string | null {
  for (const k of Object.keys(o)) if (!allowed.includes(k)) return k
  return null
}

const refuse = (code: ToolRefusal, message: string): ParsedToolCall => ({ ok: false, code, message })

export function parseToolCall(name: unknown, args: unknown, candidates: CandidateList, opts: ToolOptions = {}): ParsedToolCall {
  const wakeTool = opts.wake === true && typeof name === 'string' && (WAKE_TOOL_NAMES as readonly string[]).includes(name)
  if (typeof name !== 'string' || (!(TOOL_NAMES as readonly string[]).includes(name) && !wakeTool)) {
    return refuse('unknown_tool', 'That tool does not exist. The only tools are point_at, show_step, ask_choice and end_session.')
  }
  const a = args === undefined || args === null ? {} : args
  if (!isObj(a)) return refuse('bad_arguments', 'The arguments must be an object.')
  const known = new Set(candidates.items.map((c) => c.id))
  if (wakeTool) {
    if (name === 'clear') {
      const extra = onlyKeys(a, [])
      if (extra) return refuse('unknown_argument', 'clear takes no arguments.')
      return { ok: true, name: 'clear', args: {} }
    }
    const extra = onlyKeys(a, ['description'])
    if (extra) return refuse('unknown_argument', `do_it_for_me takes only "description"; "${cleanLine(extra).slice(0, 20)}" is not allowed.`)
    const description = parseDescription(a.description)
    if (!description) return refuse('bad_description', `description must be a short plain description of the one thing to click, ${DESCRIPTION_MAX_CHARS} characters or fewer, with no web addresses, emails or numbers.`)
    return { ok: true, name: 'do_it_for_me', args: { description } }
  }

  switch (name as ToolName) {
    case 'point_at': {
      const extra = onlyKeys(a, ['description'])
      if (extra) return refuse('unknown_argument', `point_at takes only "description"; "${cleanLine(extra).slice(0, 20)}" is not allowed.`)
      const description = parseDescription(a.description)
      if (!description) return refuse('bad_description', `description must be a short plain description of something visible, ${DESCRIPTION_MAX_CHARS} characters or fewer, with no web addresses, emails or numbers.`)
      return { ok: true, name: 'point_at', args: { description } }
    }
    case 'show_step': {
      const extra = onlyKeys(a, ['step_id'])
      if (extra) return refuse('unknown_argument', `show_step takes only "step_id"; "${cleanLine(extra).slice(0, 20)}" is not allowed.`)
      if (known.size === 0) return refuse('no_candidates', 'There is no step to show right now.')
      const id = typeof a.step_id === 'string' && ID_RE.test(a.step_id) ? a.step_id : null
      if (!id || !known.has(id)) return refuse('not_a_listed_step', 'step_id must be one of the listed step ids.')
      return { ok: true, name: 'show_step', args: { step_id: id } }
    }
    case 'ask_choice': {
      const extra = onlyKeys(a, ['options'])
      if (extra) return refuse('unknown_argument', `ask_choice takes only "options"; "${cleanLine(extra).slice(0, 20)}" is not allowed.`)
      if (known.size === 0) return refuse('no_candidates', 'There is nothing to ask about right now.')
      const raw = a.options
      if (!Array.isArray(raw) || raw.length < MIN_CHOICES || raw.length > MAX_CHOICES) return refuse('bad_choices', `options must list ${MIN_CHOICES} to ${MAX_CHOICES} step ids.`)
      const ids: string[] = []
      for (const o of raw) {
        if (typeof o !== 'string' || !ID_RE.test(o) || !known.has(o)) return refuse('not_a_listed_step', 'Every option must be one of the listed step ids.')
        if (!ids.includes(o)) ids.push(o)
      }
      if (ids.length < MIN_CHOICES) return refuse('bad_choices', 'The options must be different from each other.')
      return { ok: true, name: 'ask_choice', args: { options: ids } }
    }
    case 'end_session': {
      const extra = onlyKeys(a, [])
      if (extra) return refuse('unknown_argument', 'end_session takes no arguments.')
      return { ok: true, name: 'end_session', args: {} }
    }
  }
  return refuse('unknown_tool', 'That tool does not exist.')
}

// ---------------------------------------------------------------------------------------------------- declarations
const NB = 'NON_BLOCKING' as const

/** The declarations sent in the session setup. The id lists are the closed candidate list at the moment the session opens. */
export function buildToolDeclarations(candidates: CandidateList, opts: ToolOptions = {}): FunctionDeclaration[] {
  const listed = candidates.items.slice(0, MAX_CANDIDATES)
  const ids = listed.map((c) => c.id)
  // The closed menu, in the pack's own words (never anything the worker typed, said or has on screen): the model needs the labels to pick the right id.
  const menu = listed.map((c) => `${c.id} = ${[...cleanLine(c.label)].slice(0, 40).join('')}`).join('; ')
  const tools: FunctionDeclaration[] = [
    {
      name: 'point_at',
      behavior: NB,
      description:
        'Draws a ring on the worker\'s real screen around one visible control or area. Use it the moment you tell the worker to look at or find something on screen. ' +
        'Returns found=false when it cannot be located: then say you cannot see it, never guess. It only draws; it never clicks.',
      parameters: {
        type: 'object',
        properties: { description: { type: 'string', maxLength: DESCRIPTION_MAX_CHARS, description: `A short plain description of what to ring, for example "the green Submit button". At most ${DESCRIPTION_MAX_CHARS} characters; no web addresses, emails or numbers.` } },
        required: ['description'],
      },
    },
  ]
  if (ids.length > 0) {
    tools.push(
      {
        name: 'show_step',
        behavior: NB,
        description: `Shows one known step of the worker's task as a short guidance chip on the screen. Only use an id from the list; the chip text comes from the task pack, not from you. Steps: ${menu}.`,
        parameters: { type: 'object', properties: { step_id: { type: 'string', enum: ids, description: 'One of the listed step ids.' } }, required: ['step_id'] },
      },
      {
        name: 'ask_choice',
        behavior: NB,
        description:
          'Opens a small question card so the worker can pick which step they mean. Use it when you are not sure what they want. Offer 2 to 4 ids from the list. ' +
          `The worker answers by click, key or voice; you cannot answer for them. Steps: ${menu}.`,
        parameters: { type: 'object', properties: { options: { type: 'array', minItems: MIN_CHOICES, maxItems: MAX_CHOICES, items: { type: 'string', enum: ids }, description: 'Two to four different step ids from the list.' } }, required: ['options'] },
      },
    )
  }
  if (opts.wake === true) {
    tools.push(
      {
        name: 'clear',
        behavior: NB,
        description: 'Takes the ring and the pointer off the screen. Use it when the worker says it is in the way, or when you are done pointing.',
      },
      {
        name: 'do_it_for_me',
        behavior: NB,
        description:
          'Asks to click ONE thing on the worker\'s screen for them, once. Use it ONLY when the worker clearly asks you to click or press something. It does not click by itself: it finds the thing, rings it, ' +
          'and the worker must click Allow on a card. It can refuse (for example "first_supervised_test_pending"); then say you will show them instead and use point_at. Never offer to click unprompted.',
        parameters: {
          type: 'object',
          properties: { description: { type: 'string', maxLength: DESCRIPTION_MAX_CHARS, description: `A short plain description of the one thing to click, for example "the green Submit button". At most ${DESCRIPTION_MAX_CHARS} characters; no web addresses, emails or numbers.` } },
          required: ['description'],
        },
      },
    )
  }
  tools.push({
    name: 'end_session',
    behavior: NB,
    description: 'Ends the conversation. Call it after a short goodbye when the worker says they are done or asks you to stop.',
  })
  return tools
}

// How the model should treat a tool result: SILENT keeps it as context and says nothing; WHEN_IDLE speaks (one short sentence, by the
// instruction) after the current one. Measured against the live model on 7 Nov 2026: with SILENT after a point_at the model said nothing at all,
// so a ring or a chip appeared with no words. Things that change the screen get a spoken acknowledgement; the question card (the worker is
// about to answer it) and the goodbye stay silent.
export function schedulingFor(name: string, result: unknown): Scheduling {
  const r = isObj(result) ? result : {}
  if (r.ok === false) return 'WHEN_IDLE'
  if (name === 'point_at' || name === 'show_step' || name === 'do_it_for_me') return 'WHEN_IDLE'
  return 'SILENT'
}
