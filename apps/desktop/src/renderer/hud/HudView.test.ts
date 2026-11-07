import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_HUD_STATE, type HudNotice, type HudState } from '../../shared/hud'
import { HudView, hoursText, hudHasContent, killDetail, noticeButtons, noticeEscape } from './HudView'

type Props = Record<string, unknown> & { children?: ReactNode }
function walk(node: ReactNode, visit: (el: ReactElement<Props>) => void): void {
  if (Array.isArray(node)) return node.forEach((n) => walk(n, visit))
  if (!isValidElement(node)) return
  const el = node as ReactElement<Props>
  visit(el)
  walk(el.props.children, visit)
}
// Function components are called to see what they render.
function expand(node: ReactNode): ReactNode {
  if (Array.isArray(node)) return node.map(expand)
  if (!isValidElement(node)) return node
  const el = node as ReactElement<Props>
  if (typeof el.type === 'function') return expand((el.type as (p: Props) => ReactNode)(el.props))
  return { ...el, props: { ...el.props, children: expand(el.props.children) } } as ReactElement
}
function buttons(el: ReactNode): { label: string; onClick: () => void }[] {
  const out: { label: string; onClick: () => void }[] = []
  walk(expand(el), (b) => {
    if (b.type === 'button') out.push({ label: flat(b.props.children), onClick: b.props.onClick as () => void })
  })
  return out
}
function flat(n: ReactNode): string {
  if (Array.isArray(n)) return n.map(flat).join('').replace(/\s+/g, ' ').trim()
  if (typeof n === 'string' || typeof n === 'number') return String(n)
  if (isValidElement(n)) return flat((n as ReactElement<Props>).props.children)
  return ''
}
function texts(el: ReactNode): string {
  const out: string[] = []
  walk(expand(el), (n) => typeof n.props.children === 'string' && out.push(n.props.children))
  return out.join(' | ')
}

const proposal = { id: 'r1', title: 'Enter the household into three calculators', what: 'You enter the same household three times.', howOften: 'about 14 times in 3 weeks', hoursSaved: [3.1, 5.2] as [number, number], horizonWeeks: 4, touches: ['gov.uk check', 'turn2us'], never: ['submit'] }
const base = (over: Partial<HudState> = {}): HudState => ({ ...EMPTY_HUD_STATE, ...over })

describe('HudView', () => {
  it('idle: nothing on the screen at all (the Stop all pill is only for while an agent acts)', () => {
    expect(HudView({ state: base(), onAction: vi.fn() })).toBeNull()
    expect(hudHasContent(base())).toBe(false)
    // a morning queue waiting does not put a pill on screen: it is in the menu bar menu and the dashboard
    expect(HudView({ state: base({ queuePending: 3 }), onAction: vi.fn() })).toBeNull()
  })

  it('while an agent is acting: just the Stop all pill, which sends kill', () => {
    const onAction = vi.fn()
    const el = HudView({ state: base({ agentActing: true }), onAction })
    expect(hudHasContent(base({ agentActing: true }))).toBe(true)
    expect(buttons(el).map((b) => b.label)).toEqual(['Stop all'])
    buttons(el)[0].onClick()
    expect(onAction).toHaveBeenCalledWith({ type: 'kill' })
  })

  it('proposal toast: plain facts and three equal choices, each sending its own action', () => {
    const onAction = vi.fn()
    const el = HudView({ state: base({ proposal, agentActing: true }), onAction })
    const t = texts(el)
    for (const piece of ['I noticed something', proposal.title, proposal.what, 'about 14 times in 3 weeks', 'about 3.1 to 5.2 hours over 4 weeks', 'gov.uk check, turn2us', 'submit', 'Nothing runs unless you say so.']) expect(t).toContain(piece)
    const bs = buttons(el)
    expect(bs.map((b) => b.label)).toEqual(['Look at it', 'Not now', 'Never for this', 'Stop all'])
    bs[0].onClick()
    bs[1].onClick()
    bs[2].onClick()
    expect(onAction.mock.calls.map((c) => c[0])).toEqual([
      { type: 'proposal', id: 'r1', choice: 'look' },
      { type: 'proposal', id: 'r1', choice: 'not_now' },
      { type: 'proposal', id: 'r1', choice: 'never' },
    ])
  })

  it('stopped state: says so plainly, offers Resume and the queue, and hides the pill', () => {
    const onAction = vi.fn()
    const el = HudView({ state: base({ kill: { killed: true, engine: true, agent: false } }), onAction })
    expect(texts(el)).toContain('Everything is paused. Nothing will run until you resume.')
    expect(texts(el)).toContain('The engine was told to stop. The agent could not be reached.')
    expect(buttons(el).map((b) => b.label)).toEqual(['Resume', 'Open morning queue'])
    expect(hudHasContent(base({ kill: { killed: true, engine: true, agent: false } }))).toBe(true)
    buttons(el)[0].onClick()
    buttons(el)[1].onClick()
    expect(onAction.mock.calls.map((c) => c[0])).toEqual([{ type: 'resume' }, { type: 'open_queue' }])
  })

  it('a stopped HUD never shows a proposal', () => {
    const el = HudView({ state: base({ proposal, kill: { killed: true, engine: null, agent: null } }), onAction: vi.fn() })
    expect(texts(el)).not.toContain(proposal.title)
  })

  it('copy helpers', () => {
    expect(hoursText([3, 5], 4)).toBe('about 3 to 5 hours over 4 weeks')
    expect(hoursText([3, 5], 1)).toBe('about 3 to 5 hours over a week')
    expect(hoursText([3, 5])).toBe('about 3 to 5 hours')
    expect(hoursText(null)).toBeNull()
    expect(killDetail({ killed: true, engine: null, agent: null })).toMatch(/Telling/)
    expect(killDetail({ killed: true, engine: true, agent: true })).toBe('The engine and the agent were told to stop.')
    expect(killDetail({ killed: true, engine: false, agent: false })).toMatch(/could not reach the engine or the agent/)
  })
})

// ---------- the attention notice (REQ-8) ----------
const notice: HudNotice = {
  id: 'i_one',
  title: 'An approval is waiting',
  body: 'Approval queue: 1 approval waiting.',
  source: 'Approval queue',
  actions: [{ id: 'open_queue', label: 'Open the queue' }, { id: 'dismiss', label: 'Close' }],
  urgent: false,
}

// Every element in a rendered tree, with its props (to look at roles and classes without a DOM).
function elements(el: ReactNode): ReactElement<Props>[] {
  const out: ReactElement<Props>[] = []
  walk(expand(el), (n) => out.push(n))
  return out
}

describe('HudView: the attention notice', () => {
  it('draws the title, the body and one source line, with the buttons labelled as the engine gave them', () => {
    const el = HudView({ state: base({ notice }), onAction: vi.fn() })
    const t = texts(el)
    for (const piece of ['An approval is waiting', 'Approval queue: 1 approval waiting.', 'Approval queue']) expect(t).toContain(piece)
    expect(buttons(el).map((b) => b.label)).toEqual(['Open the queue', 'Close']) // no extra Close: the engine already offers one
    expect(hudHasContent(base({ notice }))).toBe(true)
  })

  it('each button sends its own action id for this notice', () => {
    const onAction = vi.fn()
    const el = HudView({ state: base({ notice }), onAction })
    buttons(el)[0].onClick()
    buttons(el)[1].onClick()
    expect(onAction.mock.calls.map((c) => c[0])).toEqual([
      { type: 'notice', id: 'i_one', action: 'open_queue' },
      { type: 'notice', id: 'i_one', action: 'dismiss' },
    ])
  })

  it('a notice with no way to dismiss it gets a plain Close, which closes it as dismissed', () => {
    const only: HudNotice = { ...notice, actions: [{ id: 'open_settings', label: 'Open settings' }] }
    expect(noticeButtons(only).map((b) => b.label)).toEqual(['Open settings', 'Close'])
    const onAction = vi.fn()
    const el = HudView({ state: base({ notice: only }), onAction })
    buttons(el)[1].onClick()
    expect(onAction).toHaveBeenCalledWith({ type: 'notice_closed', id: 'i_one', how: 'dismissed' })
    // "Not now" and "Never for this" already close it
    const three: HudNotice = { ...notice, actions: [{ id: 'open_routines', label: 'Look at it' }, { id: 'not_now', label: 'Not now' }, { id: 'never', label: 'Never for this' }] }
    expect(noticeButtons(three).map((b) => b.label)).toEqual(['Look at it', 'Not now', 'Never for this'])
  })

  it('Escape closes it as dismissed; nothing else does, and nothing happens without a notice or while stopped', () => {
    expect(noticeEscape(base({ notice }), 'Escape')).toEqual({ type: 'notice_closed', id: 'i_one', how: 'dismissed' })
    expect(noticeEscape(base({ notice }), 'Enter')).toBeNull()
    expect(noticeEscape(base(), 'Escape')).toBeNull()
    expect(noticeEscape(base({ notice, kill: { killed: true, engine: true, agent: true } }), 'Escape')).toBeNull()
  })

  it('sits above the Stop all pill in the same stack, so it can never cover it', () => {
    const el = HudView({ state: base({ notice, agentActing: true }), onAction: vi.fn() })
    expect(buttons(el).map((b) => b.label)).toEqual(['Open the queue', 'Close', 'Stop all'])
    const stack = (expand(el) as ReactElement<Props>).props.children as ReactElement<Props>[]
    const kinds = stack.filter(Boolean).map((c) => (c.props.className as string | undefined)?.split(' ')[0])
    expect(kinds).toEqual(['card', 'pill-row'])
  })

  it('is a plain card: no bar, no emoji, announced as a status (an alert only for a safety item)', () => {
    const plain = elements(HudView({ state: base({ notice }), onAction: vi.fn() })).find((e) => String(e.props.className ?? '').includes('notice'))
    expect(plain?.props.role).toBe('status')
    expect(String(plain?.props.className)).toBe('card notice')
    const urgent = elements(HudView({ state: base({ notice: { ...notice, urgent: true } }), onAction: vi.fn() })).find((e) => String(e.props.className ?? '').includes('notice'))
    expect(urgent?.props.role).toBe('alert')
    expect(texts(HudView({ state: base({ notice }), onAction: vi.fn() }))).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  it('the Stopped card wins while everything is stopped (one idea per surface), and a notice wins over a proposal', () => {
    const stopped = HudView({ state: base({ notice, kill: { killed: true, engine: true, agent: true } }), onAction: vi.fn() })
    expect(texts(stopped)).not.toContain('An approval is waiting')
    expect(texts(stopped)).toContain('Everything is paused. Nothing will run until you resume.')
    const both = HudView({ state: base({ notice, proposal }), onAction: vi.fn() })
    expect(texts(both)).toContain('An approval is waiting')
    expect(texts(both)).not.toContain(proposal.title)
  })

  it('the old states are as they were with no notice', () => {
    expect(HudView({ state: base(), onAction: vi.fn() })).toBeNull()
    expect(hudHasContent(base({ notice: null }))).toBe(false)
  })
})
