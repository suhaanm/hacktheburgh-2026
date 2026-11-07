import { useEffect, useState, type ReactElement } from 'react'
import { EMPTY_HUD_STATE, type HudApi, type HudState } from '../../shared/hud'
import { HudView } from './HudView'

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
  return <HudView state={state} onAction={(a) => window.understudyHud.action(a)} />
}
