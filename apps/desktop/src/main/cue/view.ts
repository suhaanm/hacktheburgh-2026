// The words and keys on the Cue panel, from what is visible. Pure: the page draws this and nothing else.
import { CUE_TOKENS } from './tokens'
import type { CueView, CueViewBody } from './ipc'
import type { CuePlan } from './plan'

export interface ViewInput {
  seq: number
  plan: CuePlan
  popover: boolean
  // The demonstration already played (or is playing): "Show me" is not offered again.
  ghost: boolean
  // The chip is the collapsed answer of the question card.
  pending: boolean
  from?: 'question'
  // "⌥" on a Mac, "Alt+" elsewhere.
  chord: string
}

export const SOMETHING_ELSE = 'Something else'

export function buildView(i: ViewInput): CueView {
  const p = i.plan
  let body: CueViewBody | null = null
  if (p.question) {
    body = {
      mode: 'question',
      question: p.question.text,
      options: p.question.options.slice(0, CUE_TOKENS.card.maxOptions),
      other: { key: '0', label: SOMETHING_ELSE },
      chord: i.chord,
    }
  } else if (p.offer) {
    body = { mode: 'offer', text: p.offer.text }
  } else if (p.chip) {
    body = {
      mode: 'chip',
      text: p.chip.text,
      stepN: p.chip.stepN,
      why: p.why,
      open: i.popover,
      canShowMe: p.anchor !== null && !i.ghost && !i.pending,
      pending: i.pending,
    }
  }
  if (!body) return null
  return { seq: i.seq, ...(i.from ? { from: i.from } : {}), ...body }
}
