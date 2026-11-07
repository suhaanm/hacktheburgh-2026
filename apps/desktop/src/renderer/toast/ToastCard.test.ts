import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ToastCard, TOAST_TITLE, countdownRemaining } from './ToastCard'

const request = { id: 'r1', question: 'Open example.com for you?', options: ['Yes, open it', 'Not now'] as [string, string] }

type Props = Record<string, unknown> & { children?: ReactNode }

function walk(node: ReactNode, visit: (el: ReactElement<Props>) => void): void {
  if (Array.isArray(node)) return node.forEach((n) => walk(n, visit))
  if (!isValidElement(node)) return
  const el = node as ReactElement<Props>
  visit(el)
  walk(el.props.children, visit)
}

function buttons(el: ReactElement): { label: string; onClick: (e: { isTrusted: boolean }) => void }[] {
  const out: { label: string; onClick: (e: { isTrusted: boolean }) => void }[] = []
  walk(el, (b) => {
    if (b.type === 'button') out.push({ label: String(b.props.children), onClick: b.props.onClick as (e: { isTrusted: boolean }) => void })
  })
  return out
}

function texts(el: ReactElement): string[] {
  const out: string[] = []
  walk(el, (n) => typeof n.props.children === 'string' && out.push(n.props.children))
  return out
}

describe('ToastCard', () => {
  it('shows the title, the question and the two option labels (primary first)', () => {
    const el = ToastCard({ request, remaining: 0.5, armed: true, onAnswer: vi.fn() })
    expect(texts(el)).toEqual(expect.arrayContaining([TOAST_TITLE, request.question]))
    expect(buttons(el).map((b) => b.label)).toEqual(['Yes, open it', 'Not now'])
  })

  it('a trusted click answers with exactly that option', () => {
    const onAnswer = vi.fn()
    const [first, second] = buttons(ToastCard({ request, remaining: 1, armed: true, onAnswer }))
    first!.onClick({ isTrusted: true })
    expect(onAnswer).toHaveBeenLastCalledWith('Yes, open it')
    second!.onClick({ isTrusted: true })
    expect(onAnswer).toHaveBeenLastCalledWith('Not now')
  })

  it('a synthetic (script-made) click never answers, on either button', () => {
    const onAnswer = vi.fn()
    for (const b of buttons(ToastCard({ request, remaining: 1, armed: true, onAnswer }))) b.onClick({ isTrusted: false })
    expect(onAnswer).not.toHaveBeenCalled()
  })

  it('ignores even a trusted click in the moment right after it appeared (not armed yet)', () => {
    const onAnswer = vi.fn()
    for (const b of buttons(ToastCard({ request, remaining: 1, armed: false, onAnswer }))) b.onClick({ isTrusted: true })
    expect(onAnswer).not.toHaveBeenCalled()
  })

  it('draws a countdown bar only when the time left is known', () => {
    const bar = (remaining: number | null) => {
      let found = 0
      walk(ToastCard({ request, remaining, armed: true, onAnswer: vi.fn() }), (n) => {
        if (n.props.role === 'progressbar') found++
      })
      return found
    }
    expect(bar(0.25)).toBe(1)
    expect(bar(null)).toBe(0)
  })

  it('has no key handler of its own: nothing but a focused button can answer', () => {
    let keyHandlers = 0
    walk(ToastCard({ request, remaining: 1, armed: true, onAnswer: vi.fn() }), (n) => {
      if (n.props.onKeyDown || n.props.onKeyUp || n.props.onKeyPress) keyHandlers++
    })
    expect(keyHandlers).toBe(0)
  })

  it('caps the question at 500 characters', () => {
    const long = { ...request, question: 'x'.repeat(900) }
    expect(texts(ToastCard({ request: long, remaining: null, armed: true, onAnswer: vi.fn() })).some((t) => t.length === 500)).toBe(true)
  })
})

describe('countdownRemaining', () => {
  it('runs from 1 to 0 between start and expiry and is clamped', () => {
    expect(countdownRemaining(1000, 3000, 1000)).toBe(1)
    expect(countdownRemaining(1000, 3000, 2000)).toBe(0.5)
    expect(countdownRemaining(1000, 3000, 5000)).toBe(0)
    expect(countdownRemaining(1000, 3000, 0)).toBe(1)
    expect(countdownRemaining(3000, 3000, 3000)).toBe(0)
  })
})
