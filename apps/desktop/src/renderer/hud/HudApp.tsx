import { useEffect, useState, type ReactElement } from 'react'
import { EMPTY_HUD_STATE, type HudApi, type HudState } from '../../shared/hud'
import { HudView, noticeEscape } from './HudView'

declare global {
  interface Window {
    understudyHud: HudApi
  }
}

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
  return <HudView state={state} onAction={(a) => window.understudyHud.action(a)} />
}
