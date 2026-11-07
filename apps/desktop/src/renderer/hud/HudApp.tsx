import { useEffect, useRef, useState, type ReactElement } from 'react'
import { EMPTY_HUD_STATE, type HudApi, type HudState } from '../../shared/hud'
import { CornerView, cardKey } from './CornerView'
import { HudView, noticeEscape } from './HudView'

declare global {
  interface Window {
    understudyHud: HudApi
  }
}

/** A card ignores clicks for its first 600 ms, so a click meant for the app underneath cannot answer it. */
export const MISTAP_GUARD_MS = 600
/** The pill sits at full strength for 8 s after any change, then settles to 85%. */
export const SETTLE_MS = 8000

export function HudApp(): ReactElement {
  const [state, setState] = useState<HudState>(EMPTY_HUD_STATE)
  useEffect(() => {
    let alive = true
    const off = window.understudyHud.onState((s) => alive && setState(s))
    void window.understudyHud
      .get()
      .then((s) => alive && setState(s))
      .catch(() => undefined) // main pushes the state too
    return () => {
      alive = false
      off()
    }
  }, [])
  // Escape closes a notice (when this window has the keyboard; the buttons and Close always work).
  useEffect(() => {
    if (!state.notice) return undefined
    const onKey = (e: KeyboardEvent): void => {
      const a = noticeEscape(state, e.key)
      if (a) window.understudyHud.action(a)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state])

  // The mis-click guard: a new card re-arms after 600 ms; the same card staying on screen stays armed.
  const key = cardKey(state)
  const [armedKey, setArmedKey] = useState<string | null>(null)
  useEffect(() => {
    if (key === null) return undefined
    const t = setTimeout(() => setArmedKey(key), MISTAP_GUARD_MS)
    return () => clearTimeout(t)
  }, [key])
  // The pill settles after 8 s without a change.
  const changeKey = `${state.activity?.phase}|${state.activity?.label}|${state.activity?.step}|${state.activity?.of}`
  const [settledKey, setSettledKey] = useState<string | null>(null)
  const last = useRef(changeKey)
  useEffect(() => {
    last.current = changeKey
    const t = setTimeout(() => setSettledKey(changeKey), SETTLE_MS)
    return () => clearTimeout(t)
  }, [changeKey])

  const onAction = (a: Parameters<HudApi['action']>[0]): void => window.understudyHud.action(a)
  if (state.corner) return <CornerView state={state} onAction={onAction} armed={key === null || armedKey === key} settled={settledKey === changeKey} />
  return <HudView state={state} onAction={onAction} />
}
