import { useEffect, useState, type ReactElement } from 'react'
import { EMPTY_PILL_VIEW, type KnackPillApi, type PillViewDto } from '../../shared/knack'
import { PillView } from './PillView'

declare global {
  interface Window {
    knackPill: KnackPillApi
  }
}

export function PillApp(): ReactElement {
  const [view, setView] = useState<PillViewDto>(EMPTY_PILL_VIEW)
  useEffect(() => {
    let alive = true
    const off = window.knackPill.onState((v) => alive && setView(v))
    void window.knackPill
      .get()
      .then((v) => alive && setView(v))
      .catch(() => undefined) // main pushes the view too
    return () => {
      alive = false
      off()
    }
  }, [])
  // No part under the pointer takes clicks once the view changes under it (the label or the button went away).
  useEffect(() => {
    window.knackPill.setInteractive(false)
  }, [view.kind, view.stop, view.open])
  return <PillView view={view} onAction={(a) => window.knackPill.action(a)} onInteractive={(on) => window.knackPill.setInteractive(on)} />
}
