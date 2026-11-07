import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_PILL_VIEW, type PillViewDto } from '../../shared/knack'
import { PillView, labelName } from './PillView'

type Props = Record<string, unknown> & { children?: ReactNode }
function walk(node: ReactNode, visit: (el: ReactElement<Props>) => void): void {
  if (Array.isArray(node)) return node.forEach((n) => walk(n, visit))
  if (!isValidElement(node)) return
  const el = node as ReactElement<Props>
  visit(el)
  walk(el.props.children, visit)
}
function flat(n: ReactNode): string {
  if (Array.isArray(n)) return n.map(flat).join('').replace(/\s+/g, ' ').trim()
  if (typeof n === 'string' || typeof n === 'number') return String(n)
  if (isValidElement(n)) return flat((n as ReactElement<Props>).props.children)
  return ''
}
function buttons(el: ReactNode) {
  const out: { label: string; name: string; className: string; click: () => void; enter: () => void; leave: () => void }[] = []
  walk(el, (b) => {
    if (b.type === 'button') out.push({ label: flat(b.props.children), name: String(b.props['aria-label'] ?? ''), className: String(b.props.className), click: b.props.onClick as () => void, enter: b.props.onMouseEnter as () => void, leave: b.props.onMouseLeave as () => void })
  })
  return out
}
const view = (over: Partial<PillViewDto>): PillViewDto => ({ ...EMPTY_PILL_VIEW, ...over })

describe('the pill', () => {
  it('draws nothing when idle', () => {
    expect(PillView({ view: EMPTY_PILL_VIEW, onAction: vi.fn(), onInteractive: vi.fn() })).toBeNull()
  })

  it('while working: the sentence opens Knack, and Stop is the one control', () => {
    const onAction = vi.fn()
    const el = PillView({ view: view({ kind: 'working', text: 'Working on it', stop: true, open: true }), onAction, onInteractive: vi.fn() })
    const b = buttons(el)
    expect(b.map((x) => x.label)).toEqual(['Working on it', 'Stop'])
    expect(b[0]!.name).toBe(labelName('Working on it'))
    expect(b[0]!.name).toBe('Working on it. Open Knack.')
    expect(b[1]!.name).toContain('Stop everything')
    b[0]!.click()
    b[1]!.click()
    expect(onAction.mock.calls).toEqual([[{ type: 'open' }], [{ type: 'stop' }]])
  })

  it('every other state has the label and no Stop', () => {
    for (const kind of ['needs-you', 'done', 'error', 'killed'] as const) {
      const b = buttons(PillView({ view: view({ kind, text: 'x', stop: false, open: true }), onAction: vi.fn(), onInteractive: vi.fn() }))
      expect(b.map((x) => x.className), kind).toEqual(['label'])
    }
  })

  it('asks for clicks only while the pointer is over a part that takes them', () => {
    const onInteractive = vi.fn()
    const b = buttons(PillView({ view: view({ kind: 'working', text: 'Working on it', stop: true, open: true }), onAction: vi.fn(), onInteractive }))
    b[1]!.enter()
    b[1]!.leave()
    b[0]!.enter()
    expect(onInteractive.mock.calls).toEqual([[true], [false], [true]])
  })

  it('announces a failure or a request for the worker assertively and the rest politely', () => {
    const live = (kind: PillViewDto['kind']) => {
      let v = ''
      walk(PillView({ view: view({ kind, text: 'x', open: true }), onAction: vi.fn(), onInteractive: vi.fn() }), (n) => {
        if (n.props['data-pill'] !== undefined) v = String(n.props['aria-live'])
      })
      return v
    }
    expect(live('error')).toBe('assertive')
    expect(live('needs-you')).toBe('assertive')
    expect(live('working')).toBe('polite')
    expect(live('done')).toBe('polite')
  })
})
