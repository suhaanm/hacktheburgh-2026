// The Cue panel page: stacks the current view over the one it replaces (a 150 ms cross-fade), takes the number and Escape keys when it has focus,
// tells main when the pointer is on it (the "untouched" clocks restart) and reports its size so the window is exactly that big.
// It is given a CueView and a way to send actions; the real page gets both from the preload, the storyboard from a fake.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactElement } from 'react'
import type { CueCardAction, CueView } from '../../../main/cue/ipc'
import { CUE_TOKENS } from '../../../main/cue/tokens'
import { ChipView, OfferView, QuestionView } from './CueViews'

type Shown = NonNullable<CueView>
interface Layer {
  key: number
  view: Shown
  exiting: boolean
  // The view this one replaced was the question card: the chip settles where the card was.
  to?: 'chip'
}

export interface CuePanelProps {
  view: CueView
  onAction: (a: CueCardAction) => void
  onSize?: (s: { w: number; h: number }) => void
  // Harness stills: no entrance animations.
  still?: boolean
}

/** The digit of a key press that answers a question card (1 to 9), or 0 for "something else", or null. */
export function digitOf(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey'>): number | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  return /^[0-9]$/.test(e.key) ? Number(e.key) : null
}

export function CuePanel({ view, onAction, onSize, still = false }: CuePanelProps): ReactElement {
  const [layers, setLayers] = useState<Layer[]>([])
  const stage = useRef<HTMLDivElement>(null)
  const latest = useRef({ view, onAction })
  latest.current = { view, onAction }

  // The current view becomes the top layer; a new `seq` starts a new layer and fades the old one out.
  useEffect(() => {
    setLayers((prev) => {
      const top = prev.find((l) => !l.exiting)
      if (view === null) return prev.map((l) => ({ ...l, exiting: true }))
      if (top && top.key === view.seq) return prev.map((l) => (l === top ? { ...l, view } : l))
      const collapsing = view.from === 'question' && top?.view.mode === 'question'
      return [...prev.map((l) => ({ ...l, exiting: true, ...(collapsing ? { to: 'chip' as const } : {}) })), { key: view.seq, view, exiting: false }]
    })
    const t = setTimeout(() => setLayers((prev) => prev.filter((l) => !l.exiting)), CUE_TOKENS.timing.crossfadeMs + 30)
    return () => clearTimeout(t)
  }, [view])

  // Size, so main can fit the window to what is drawn.
  useLayoutEffect(() => {
    const el = stage.current
    if (!el || !onSize || typeof ResizeObserver === 'undefined') return
    const report = (): void => onSize({ w: Math.ceil(el.offsetWidth), h: Math.ceil(el.offsetHeight) })
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [onSize])

  // Keys, while the panel has focus (a click or the focus chord). Global keys while it has none are main's.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const { view: v, onAction: act } = latest.current
      if (!v) return
      if (e.key === 'Escape') {
        e.preventDefault()
        act({ type: 'dismiss' })
        return
      }
      if (v.mode === 'question') {
        const n = digitOf(e)
        if (n === null) return
        if (n === 0) act({ type: 'other' })
        else {
          const opt = v.options[n - 1]
          if (!opt) return
          act({ type: 'answer', id: opt.id })
        }
        e.preventDefault()
        return
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const rows = Array.from(document.querySelectorAll<HTMLElement>('.cue-layer:not([data-exiting="true"]) .row'))
        if (rows.length === 0) return
        const at = rows.indexOf(document.activeElement as HTMLElement)
        const next = e.key === 'ArrowDown' ? (at + 1) % rows.length : (at - 1 + rows.length) % rows.length
        rows[next]?.focus()
        e.preventDefault()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // The pointer is on the panel: the worker is looking at it. Told at most twice a second.
  const lastTouch = useRef(0)
  const touch = useCallback(() => {
    const now = Date.now()
    if (now - lastTouch.current < 500) return
    lastTouch.current = now
    latest.current.onAction({ type: 'touch' })
  }, [])

  return (
    <div className="cue-stage" ref={stage} data-still={still} onPointerMove={touch} onPointerDown={touch}>
      {layers.map((l) => (
        <div key={l.key} className="cue-layer" data-exiting={l.exiting} data-from={l.view.from} data-to={l.to}>
          {l.view.mode === 'chip' ? <ChipView view={l.view} onAction={onAction} /> : null}
          {l.view.mode === 'question' ? <QuestionView view={l.view} onAction={onAction} /> : null}
          {l.view.mode === 'offer' ? <OfferView view={l.view} onAction={onAction} /> : null}
        </div>
      ))}
    </div>
  )
}
