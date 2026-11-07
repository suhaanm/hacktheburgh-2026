import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { CueCardAction, CueChipView, CueOfferView, CueQuestionView } from '../../../main/cue/ipc'
import { digitOf } from './CuePanel'
import { ChipView, OfferView, QuestionView, sentence } from './CueViews'

type Props = Record<string, unknown> & { children?: ReactNode }
function walk(node: ReactNode, visit: (el: ReactElement<Props>) => void): void {
  if (Array.isArray(node)) return node.forEach((n) => walk(n, visit))
  if (!isValidElement(node)) return
  const el = node as ReactElement<Props>
  visit(el)
  walk(el.props.children, visit)
}
function expand(node: ReactNode): ReactNode {
  if (Array.isArray(node)) return node.map(expand)
  if (!isValidElement(node)) return node
  const el = node as ReactElement<Props>
  if (typeof el.type === 'function') return expand((el.type as (p: Props) => ReactNode)(el.props))
  return { ...el, props: { ...el.props, children: expand(el.props.children) } } as ReactElement
}
function flat(n: ReactNode): string {
  if (Array.isArray(n)) return n.map(flat).join('').replace(/\s+/g, ' ').trim()
  if (typeof n === 'string' || typeof n === 'number') return String(n)
  if (isValidElement(n)) return flat((n as ReactElement<Props>).props.children)
  return ''
}
const buttons = (el: ReactNode): { label: string; cls: string; onClick: () => void; aria: Props }[] => {
  const out: { label: string; cls: string; onClick: () => void; aria: Props }[] = []
  walk(expand(el), (b) => {
    if (b.type === 'button') out.push({ label: flat(b.props.children), cls: String(b.props.className ?? ''), onClick: b.props.onClick as () => void, aria: b.props })
  })
  return out
}

const question: CueQuestionView = {
  mode: 'question',
  question: 'Which of these is next?',
  options: [
    { id: 'calc_a', label: 'Run calculator A', key: '1' },
    { id: 'cliff_a', label: 'Check cliff edges (A)', key: '2' },
    { id: 'write_note', label: 'Copy figures to the note', key: '3' },
  ],
  other: { key: '0', label: 'Something else' },
  chord: '⌥',
}

describe('the question card', () => {
  it('one row per option with its key cap, a quiet "Something else" row last, and a dismiss', () => {
    const act = vi.fn<(a: CueCardAction) => void>()
    const b = buttons(QuestionView({ view: question, onAction: act }))
    expect(b.map((x) => x.label)).toEqual(['esc', '⌥1Run calculator A', '⌥2Check cliff edges (A)', '⌥3Copy figures to the note', '⌥0Something else'])
    expect(b[4].cls).toContain('else')
  })
  it('a click answers with the option id, the last row is "other", and esc dismisses', () => {
    const act = vi.fn<(a: CueCardAction) => void>()
    const b = buttons(QuestionView({ view: question, onAction: act }))
    b[2].onClick()
    b[4].onClick()
    b[0].onClick()
    expect(act.mock.calls.map((c) => c[0])).toEqual([{ type: 'answer', id: 'cliff_a' }, { type: 'other' }, { type: 'dismiss' }])
  })
  it('announces its shortcuts to assistive technology', () => {
    const b = buttons(QuestionView({ view: question, onAction: () => undefined }))
    expect(b[1].aria['aria-keyshortcuts']).toBe('Alt+1')
  })
  it('never shows more than the options it was given', () => {
    const two = { ...question, options: question.options.slice(0, 2) }
    expect(buttons(QuestionView({ view: two, onAction: () => undefined })).map((x) => x.label)).toHaveLength(4)
  })
})

const chip: CueChipView = { mode: 'chip', text: 'Next: Run calculator A', stepN: null, why: { reason: 'Copy the household from the record; retyping invites mistakes.', phrase: 'most experts do this next', simulated: true }, open: false, canShowMe: true, pending: false }

describe('the chip', () => {
  it('is one button for "Why this?" and one to dismiss; the popover holds Show me and I know this', () => {
    const act = vi.fn<(a: CueCardAction) => void>()
    const b = buttons(ChipView({ view: chip, onAction: act }))
    expect(b.map((x) => x.label)).toEqual(['Next: Run calculator A', 'esc', 'Show me', 'I know this'])
    b[0].onClick()
    b[2].onClick()
    b[3].onClick()
    b[1].onClick()
    expect(act.mock.calls.map((c) => c[0])).toEqual([{ type: 'why', open: true }, { type: 'show_me' }, { type: 'know_this' }, { type: 'dismiss' }])
    expect(b[0].aria['aria-label']).toBe('Next: Run calculator A. Why this?')
  })
  it('the step pill appears only when there is a number; "Show me" only when there is something to show', () => {
    const l1 = buttons(ChipView({ view: { ...chip, stepN: 3, canShowMe: false }, onAction: () => undefined }))
    expect(l1[0].label).toBe('3Next: Run calculator A')
    expect(l1.map((x) => x.label)).not.toContain('Show me')
  })
  it('an open chip toggles closed; the reason and phrase are exactly what the engine sent, simulated experts are tagged', () => {
    const act = vi.fn<(a: CueCardAction) => void>()
    buttons(ChipView({ view: { ...chip, open: true }, onAction: act }))[0].onClick()
    expect(act).toHaveBeenCalledWith({ type: 'why', open: false })
    const text = flat(expand(ChipView({ view: chip, onAction: () => undefined })))
    expect(text).toContain('Copy the household from the record; retyping invites mistakes.')
    expect(text).toContain('Most experts do this next.')
    expect(text).toContain('Simulated')
  })
  it('with no reason and no phrase the popover shows nothing but the actions, and recorded experts carry no tag', () => {
    const bare = flat(expand(ChipView({ view: { ...chip, why: null }, onAction: () => undefined })))
    expect(bare).not.toContain('Most experts')
    const recorded = flat(expand(ChipView({ view: { ...chip, why: { reason: null, phrase: 'most experts do this next', simulated: false } }, onAction: () => undefined })))
    expect(recorded).not.toContain('Simulated')
  })
  it('the collapsed answer of a question is plain: no buttons to press yet', () => {
    expect(buttons(ChipView({ view: { ...chip, pending: true, why: null }, onAction: () => undefined }))).toEqual([])
  })
})

describe('the offer', () => {
  it('says what it will do: show me, or not now', () => {
    const act = vi.fn<(a: CueCardAction) => void>()
    const view: CueOfferView = { mode: 'offer', text: 'Want a hand?' }
    const b = buttons(OfferView({ view, onAction: act }))
    expect(b.map((x) => x.label)).toEqual(['Show me', 'Not now'])
    b[0].onClick()
    b[1].onClick()
    expect(act.mock.calls.map((c) => c[0])).toEqual([{ type: 'offer', yes: true }, { type: 'offer', yes: false }])
  })
})

describe('helpers', () => {
  it('digitOf takes a bare digit only, never a chord that belongs to the app', () => {
    const k = (key: string, mods: Partial<Record<'ctrlKey' | 'metaKey' | 'altKey', boolean>> = {}) => digitOf({ key, ctrlKey: false, metaKey: false, altKey: false, ...mods })
    expect(k('2')).toBe(2)
    expect(k('0')).toBe(0)
    expect(k('a')).toBeNull()
    expect(k('2', { metaKey: true })).toBeNull()
    expect(k('2', { altKey: true })).toBeNull()
  })
  it('sentence capitalises and ends the phrase', () => {
    expect(sentence('most experts do this next')).toBe('Most experts do this next.')
    expect(sentence('Done.')).toBe('Done.')
  })
})
