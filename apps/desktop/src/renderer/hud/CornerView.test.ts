import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_HUD_STATE, type HudActivity, type HudState } from '../../shared/hud'
import { CornerView, cardKey, cornerHasContent, limitWords } from './CornerView'

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
const flat = (n: ReactNode): string => (Array.isArray(n) ? n.map(flat).join('').replace(/\s+/g, ' ').trim() : typeof n === 'string' || typeof n === 'number' ? String(n) : isValidElement(n) ? flat((n as ReactElement<Props>).props.children) : '')
function buttons(el: ReactNode) {
  const out: { label: string; disabled: boolean; click: () => void }[] = []
  walk(expand(el), (b) => {
    if (b.type === 'button') out.push({ label: flat(b.props.children), disabled: b.props.disabled === true, click: b.props.onClick as () => void })
  })
  return out
}
const classes = (el: ReactNode): string[] => {
  const out: string[] = []
  walk(expand(el), (n) => void (typeof n.props.className === 'string' && out.push(n.props.className)))
  return out
}
const texts = (el: ReactNode): string => {
  const out: string[] = []
  walk(expand(el), (n) => void (typeof n.props.children === 'string' && out.push(n.props.children)))
  return out.join(' | ')
}

const base = (over: Partial<HudState> = {}): HudState => ({ ...EMPTY_HUD_STATE, corner: true, ...over })
const act = (over: Partial<HudActivity> = {}): HudActivity => ({ phase: 'working', label: 'Filling in calculator B', step: 3, of: 8, leaving: false, ...over })
const approval = { id: 'a_1', title: 'A run is waiting for you', body: 'It needs your approval to go on.', source: 'your run' }

describe('the corner pill', () => {
  it('says the words, n of m when known, and has one Stop button while working', () => {
    const onAction = vi.fn()
    const el = CornerView({ state: base({ activity: act() }), onAction })
    expect(texts(el)).toContain('Filling in calculator B')
    expect(texts(el)).toContain('3 of 8')
    const b = buttons(el)
    expect(b.map((x) => x.label)).toEqual(['Stop'])
    b[0]!.click()
    expect(onAction).toHaveBeenCalledWith({ type: 'kill' })
  })
  it('leaves out n of m when it is not known, and never says more than five words', () => {
    expect(texts(CornerView({ state: base({ activity: act({ step: null, of: null }) }), onAction: vi.fn() }))).not.toContain(' of ')
    expect(limitWords('one two three four five six seven')).toBe('one two three four five')
    expect(texts(CornerView({ state: base({ activity: act({ label: 'a b c d e f g' }) }), onAction: vi.fn() }))).toContain('a b c d e')
  })
  it('voice has End instead of Stop; error has Open; done has no button', () => {
    const onAction = vi.fn()
    const voice = buttons(CornerView({ state: base({ activity: act({ phase: 'voice', label: 'Listening', step: null, of: null }) }), onAction }))
    expect(voice.map((x) => x.label)).toEqual(['End'])
    voice[0]!.click()
    expect(onAction).toHaveBeenCalledWith({ type: 'voice_end' })
    const error = buttons(CornerView({ state: base({ activity: act({ phase: 'error', label: 'Something went wrong', step: null, of: null }) }), onAction }))
    expect(error.map((x) => x.label)).toEqual(['Open'])
    error[0]!.click()
    expect(onAction).toHaveBeenCalledWith({ type: 'pill_open' })
    expect(buttons(CornerView({ state: base({ activity: act({ phase: 'done', label: 'Done', step: null, of: null }) }), onAction: vi.fn() }))).toEqual([])
  })
  it('settles to 85% after a while and fades when leaving', () => {
    const el = CornerView({ state: base({ activity: act({ leaving: true }) }), onAction: vi.fn(), settled: true })
    const pill = (expand(el) as ReactElement<Props>).props.children as ReactElement<Props>[]
    const p = pill.filter(Boolean).find((c) => String(c.props.className).startsWith('cpill'))!
    expect(p.props['data-settled']).toBe(true)
    expect(p.props['data-leaving']).toBe(true)
  })
})

describe('the card above the pill', () => {
  it('an approval has Review and Later, in the engine-free fixed words, and sits above the pill in the same column', () => {
    const onAction = vi.fn()
    const el = CornerView({ state: base({ activity: act(), approval }), onAction })
    expect(buttons(el).map((x) => x.label)).toEqual(['Review', 'Later', 'Stop'])
    expect(texts(el)).toContain('A run is waiting for you')
    expect(texts(el)).toContain('Knack · your run')
    const order = classes(el).filter((c) => c.startsWith('card') || c.startsWith('cpill'))
    expect(order[0]).toMatch(/^card/)
    expect(order.at(-1)).toMatch(/^cpill/)
    buttons(el)[0]!.click()
    buttons(el)[1]!.click()
    expect(onAction.mock.calls.map((c) => c[0])).toEqual([{ type: 'review', id: 'a_1' }, { type: 'later', id: 'a_1' }])
  })
  it('a card ignores clicks for its first 600 ms (the buttons are disabled until armed)', () => {
    const state = base({ approval })
    expect(buttons(CornerView({ state, onAction: vi.fn(), armed: false })).every((b) => b.disabled)).toBe(true)
    expect(buttons(CornerView({ state, onAction: vi.fn(), armed: true })).some((b) => b.disabled)).toBe(false)
  })
  it('the Stopped card replaces the pill and has one button, Resume', () => {
    const onAction = vi.fn()
    const el = CornerView({ state: base({ activity: act(), kill: { killed: true, engine: true, agent: true } }), onAction })
    expect(buttons(el).map((x) => x.label)).toEqual(['Resume'])
    expect(texts(el)).toContain('Everything is paused. Nothing runs until you resume.')
    expect(classes(el).some((c) => c.startsWith('cpill'))).toBe(false)
    buttons(el)[0]!.click()
    expect(onAction).toHaveBeenCalledWith({ type: 'resume' })
  })
  it('draws nothing when there is no pill and no card, and a held card is not drawn', () => {
    expect(CornerView({ state: base(), onAction: vi.fn() })).toBeNull()
    expect(cornerHasContent(base())).toBe(false)
    const held = base({ approval, hold: { secure: true, share: false, ask: false } })
    expect(CornerView({ state: held, onAction: vi.fn() })).toBeNull()
    expect(cornerHasContent(base({ activity: act() }))).toBe(true)
  })
  it('a new card re-arms the guard, the same one staying up does not', () => {
    expect(cardKey(base())).toBeNull()
    expect(cardKey(base({ approval }))).toBe('approval:a_1')
    expect(cardKey(base({ approval }))).toBe(cardKey(base({ approval: { ...approval } })))
    expect(cardKey(base({ approval: { ...approval, id: 'a_2' } }))).not.toBe(cardKey(base({ approval })))
    expect(cardKey(base({ kill: { killed: true, engine: null, agent: null } }))).toBe('stopped')
  })
})
