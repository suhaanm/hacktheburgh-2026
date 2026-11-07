import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_HUD_STATE, type HudState } from '../../shared/hud'
import { HudView, hoursText, hudHasContent, killDetail } from './HudView'

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
