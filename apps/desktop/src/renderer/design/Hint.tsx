import { useEffect, useId, useLayoutEffect, useReducer, useRef, useState, type CSSProperties, type ReactElement, type ReactNode } from 'react'
import { HINT_CLOSED, hintReduce, isHintOpen, placeHint } from './hint-logic'
import './hint.css'

/** Only one Hint is open at a time. */
let closeActive: (() => void) | null = null

/**
 * A small info button that opens a short note, for a unit, a definition or a longer reason that does not belong in a first view (D45).
 * One or two plain sentences, no links or buttons, never the only place a consent or a limit is stated.
 * Opens on hover, focus, tap, Enter or Space; Escape closes it and focus stays on the button; a tap elsewhere closes it.
 * The note is the button's description, so a screen reader reads it on focus. Same behaviour as apps/dashboard/src/components/Hint.tsx.
 */
export function Hint({ label, children, tabIndex }: { label: string; children: ReactNode; tabIndex?: 0 | -1 }): ReactElement {
  const noteId = useId()
  const [state, dispatch] = useReducer(hintReduce, HINT_CLOSED)
  const open = isHintOpen(state)
  const wrap = useRef<HTMLSpanElement>(null)
  const btn = useRef<HTMLButtonElement>(null)
  const pop = useRef<HTMLSpanElement>(null)
  const timer = useRef(0)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)

  const place = (): void => {
    if (!btn.current || !pop.current) return
    const b = btn.current.getBoundingClientRect()
    const p = placeHint({ left: b.left, top: b.top, width: b.width, height: b.height }, { w: pop.current.offsetWidth, h: pop.current.offsetHeight }, { w: document.documentElement.clientWidth, h: window.innerHeight })
    setPos({ x: p.x, y: p.y })
  }

  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    place()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const self = (): void => dispatch('outside')
    if (closeActive && closeActive !== self) closeActive()
    closeActive = self
    const down = (e: Event): void => {
      if (!wrap.current?.contains(e.target as Node)) dispatch('outside')
    }
    document.addEventListener('pointerdown', down)
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, { capture: true, passive: true })
    return () => {
      document.removeEventListener('pointerdown', down)
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      if (closeActive === self) closeActive = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const style = pos ? ({ ['--x' as string]: `${pos.x}px`, ['--y' as string]: `${pos.y}px` } as CSSProperties) : undefined
  return (
    <span
      ref={wrap}
      className="al-hint"
      onPointerEnter={(e) => {
        if (e.pointerType === 'touch') return
        window.clearTimeout(timer.current)
        dispatch('enter')
      }}
      onPointerLeave={(e) => {
        if (e.pointerType === 'touch') return
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => dispatch('leave'), 150)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && open) {
          e.preventDefault()
          e.stopPropagation()
          dispatch('escape')
          btn.current?.focus()
        }
      }}
    >
      <button ref={btn} type="button" className="al-hint__btn" aria-label={label} aria-expanded={open} aria-describedby={noteId} tabIndex={tabIndex} onFocus={() => dispatch('focus')} onBlur={() => dispatch('blur')} onClick={() => dispatch('click')} />
      <span ref={pop} id={noteId} role="note" className="al-hint__pop" hidden={!open} style={style}>
        {children}
      </span>
    </span>
  )
}
